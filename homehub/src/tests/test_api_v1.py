"""The token-protected API that Home Assistant, Assist and n8n use."""
from datetime import date, timedelta

import pytest
import yaml

from app import config as config_module, create_app, db
from app.models import RecurringChore

KEY = 'test-key-123'
AUTH = {'Authorization': f'Bearer {KEY}'}


@pytest.fixture()
def app(tmp_path, monkeypatch):
    with open(config_module.EXAMPLE_CONFIG_PATH, encoding='utf-8') as f:
        cfg = yaml.safe_load(f)
    cfg['api_key'] = KEY
    cfg['password'] = 'site-secret'
    path = tmp_path / 'config.yml'
    path.write_text(yaml.safe_dump(cfg), encoding='utf-8')
    monkeypatch.setattr(config_module, 'CONFIG_PATH', str(path))
    monkeypatch.setattr(config_module, '_cache', {'key': None, 'config': None})
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://', 'SECRET_KEY': 'test'})
    with app.app_context():
        db.create_all()
    return app


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.mark.parametrize('headers', [{}, {'Authorization': 'Bearer wrong'}, {'Authorization': KEY}])
def test_api_needs_the_key(client, headers):
    assert client.get('/api/v1/status', headers=headers).status_code == 401


def test_key_gets_past_the_site_password(client):
    resp = client.get('/api/v1/status', headers=AUTH)
    assert resp.status_code == 200
    assert resp.get_json()['currency'] == '$'
    # The older JSON endpoints open with the key too, and stay closed without it
    assert client.get('/api/chores', headers=AUTH).status_code == 200
    assert client.get('/api/chores').status_code == 302


def test_no_key_configured_means_no_api(client, app):
    app.config['HOMEHUB_CONFIG']['api_key'] = ''
    config_module._cache['config']['api_key'] = ''
    assert client.get('/api/v1/status', headers={'Authorization': 'Bearer '}).status_code == 401


def test_shopping_list_round_trip(client):
    resp = client.post('/api/v1/shopping', json={'item': 'Milk', 'user': 'Logan'}, headers=AUTH)
    assert resp.status_code == 201
    item = resp.get_json()['item']
    assert item['item'] == 'Milk' and item['creator'] == 'Logan' and not item['checked']
    client.patch(f"/api/v1/shopping/{item['id']}", json={'checked': True}, headers=AUTH)
    items = client.get('/api/v1/shopping', headers=AUTH).get_json()['items']
    assert items == [dict(item, checked=True)]
    assert client.delete(f"/api/v1/shopping/{item['id']}", headers=AUTH).get_json()['ok']
    assert client.get('/api/v1/shopping', headers=AUTH).get_json()['items'] == []


def test_shopping_item_is_required(client):
    assert client.post('/api/v1/shopping', json={'item': '  '}, headers=AUTH).status_code == 400


def test_chores_add_and_complete(client):
    chore = client.post('/api/v1/chores', json={'description': 'Take out trash', 'due_date': '2030-01-02'},
                        headers=AUTH).get_json()['chore']
    assert chore['due_date'] == '2030-01-02' and chore['creator'] == 'Home Assistant'
    done = client.patch(f"/api/v1/chores/{chore['id']}", json={'done': True}, headers=AUTH).get_json()['chore']
    assert done['done'] is True


def test_recurring_chore_moves_to_next_date_when_completed(client, app):
    today = date.today()
    with app.app_context():
        db.session.add(RecurringChore(description='Water plants', interval=1, unit='week', start_date=today))
        db.session.commit()
    chores = client.get('/api/v1/chores', headers=AUTH).get_json()['chores']
    chore = next(c for c in chores if c['description'] == 'Water plants')
    assert chore['recurring'] and not chore['done']
    after = client.patch(f"/api/v1/chores/{chore['id']}", json={'done': True}, headers=AUTH).get_json()['chore']
    assert after['due_date'] == (today + timedelta(weeks=1)).isoformat()


def test_calendar_add_and_list(client):
    when = date.today() + timedelta(days=3)
    resp = client.post('/api/v1/calendar', json={'title': 'Vet', 'date': when.isoformat(), 'time': '14:30'},
                       headers=AUTH)
    assert resp.get_json()['ok']
    events = client.get(f'/api/v1/calendar?start={date.today()}&end={when + timedelta(days=1)}',
                        headers=AUTH).get_json()['events']
    assert [(e['title'], e['date']) for e in events] == [('Vet', when.isoformat())]
    later = client.get(f'/api/v1/calendar?start={when + timedelta(days=1)}', headers=AUTH).get_json()['events']
    assert later == []


def test_expenses_add_and_summary(client):
    today = date.today()
    for title, amount, user in (('Groceries', 42.5, 'Logan'), ('Gas', 30, 'Sam')):
        assert client.post('/api/v1/expenses', json={'title': title, 'amount': amount, 'user': user},
                           headers=AUTH).status_code == 201
    summary = client.get('/api/v1/expenses/summary', headers=AUTH).get_json()
    assert (summary['year'], summary['month']) == (today.year, today.month)
    assert summary['total'] == 72.5
    assert summary['by_person'] == {'Logan': 42.5, 'Sam': 30.0}
    assert summary['currency'] == '$' and summary['currency_code'] == 'USD'


@pytest.mark.parametrize('amount', ['abc', -5, 0, 'nan'])
def test_bad_expense_amounts_are_refused(client, amount):
    assert client.post('/api/v1/expenses', json={'title': 'x', 'amount': amount}, headers=AUTH).status_code == 400
