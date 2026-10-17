"""Running as a Home Assistant add-on: people, presence, the ingress panel and the add-on options."""
import pytest
import yaml

from app import addon, config as config_module, create_app, db, homeassistant

INGRESS = '/api/hassio_ingress/abc123'
PROXY = {'REMOTE_ADDR': '172.30.32.2'}

PEOPLE = [
    {'entity_id': 'person.logan', 'name': 'Logan', 'user_id': 'u-logan', 'state': 'home'},
    {'entity_id': 'person.sam', 'name': 'Sam', 'user_id': 'u-sam', 'state': 'Work'},
    {'entity_id': 'person.guest', 'name': 'Guest', 'user_id': None, 'state': 'not_home'},
]


def write_config(tmp_path, monkeypatch, **overrides):
    with open(config_module.EXAMPLE_CONFIG_PATH, encoding='utf-8') as f:
        cfg = yaml.safe_load(f)
    cfg['family_members'] = ['Grandma']
    cfg['home_assistant'] = {'people': True, 'presence': True, 'exclude_people': ['person.guest']}
    cfg.update(overrides)
    path = tmp_path / 'config.yml'
    path.write_text(yaml.safe_dump(cfg), encoding='utf-8')
    monkeypatch.setattr(config_module, 'CONFIG_PATH', str(path))
    monkeypatch.setattr(config_module, '_cache', {'key': None, 'config': None})


@pytest.fixture(autouse=True)
def home_assistant(monkeypatch):
    monkeypatch.setenv('SUPERVISOR_TOKEN', 'token')
    monkeypatch.setattr(homeassistant, '_people_cache', {'at': 0.0, 'people': None})
    monkeypatch.setattr(homeassistant, '_fetch_people', lambda: [dict(p) for p in PEOPLE])


@pytest.fixture()
def app(tmp_path, monkeypatch):
    write_config(tmp_path, monkeypatch)
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://', 'SECRET_KEY': 'test'})
    with app.app_context():
        db.create_all()
    return app


@pytest.fixture()
def client(app):
    return app.test_client()


def test_household_is_home_assistant_people_plus_extras(app):
    cfg = config_module.load_config()
    assert cfg['family_members'] == ['Logan', 'Sam', 'Grandma']


def test_people_are_left_alone_outside_home_assistant(app, monkeypatch):
    monkeypatch.delenv('SUPERVISOR_TOKEN')
    assert config_module.load_config()['family_members'] == ['Grandma']


def test_last_known_people_are_kept_when_home_assistant_is_unreachable(app, monkeypatch):
    assert 'Logan' in config_module.load_config()['family_members']

    def unreachable():
        raise ConnectionError('down')
    monkeypatch.setattr(homeassistant, '_fetch_people', unreachable)
    monkeypatch.setitem(homeassistant._people_cache, 'at', 0.0)
    assert config_module.load_config()['family_members'] == ['Logan', 'Sam', 'Grandma']


def test_who_is_home_comes_from_person_state(client):
    page = client.get('/', environ_base=PROXY, headers={'X-Ingress-Path': INGRESS}).get_data(as_text=True)
    assert 'Updated automatically from Home Assistant.' in page
    assert 'id="whoUnifiedForm"' not in page
    with client.application.test_request_context():
        cfg = config_module.load_config()
        assert homeassistant.presence_statuses(cfg) == {'Logan': 'Home', 'Sam': 'Work'}


def test_ingress_links_go_through_the_proxy(client):
    resp = client.get('/', environ_base=PROXY, headers={'X-Ingress-Path': INGRESS})
    page = resp.get_data(as_text=True)
    assert f'href="{INGRESS}/notes"' in page
    assert f'src="{INGRESS}/static/js/reminders_api.js"' in page
    # url_for() links already carry the path and are not prefixed twice
    assert f'{INGRESS}{INGRESS}' not in page
    assert 'href="/notes"' not in page


def test_ingress_redirects_stay_in_the_proxy(client):
    resp = client.get('/login', environ_base=PROXY, headers={'X-Ingress-Path': INGRESS})
    assert resp.status_code == 302
    assert resp.headers['Location'].startswith(INGRESS + '/')


def test_ingress_header_from_elsewhere_is_ignored(client):
    page = client.get('/', environ_base={'REMOTE_ADDR': '192.168.1.50'},
                      headers={'X-Ingress-Path': INGRESS}).get_data(as_text=True)
    assert INGRESS not in page
    assert 'href="/notes"' in page


def test_signed_in_home_assistant_user_is_picked(client):
    page = client.get('/', environ_base=PROXY,
                      headers={'X-Ingress-Path': INGRESS, 'X-Remote-User-Id': 'u-sam'}).get_data(as_text=True)
    assert "localStorage.setItem('username', \"Sam\")" in page


def test_site_password_applies_only_outside_home_assistant(tmp_path, monkeypatch):
    write_config(tmp_path, monkeypatch, password='secret')
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://', 'SECRET_KEY': 'test'})
    client = app.test_client()
    assert client.get('/', environ_base=PROXY, headers={'X-Ingress-Path': INGRESS}).status_code == 200
    direct = client.get('/', environ_base={'REMOTE_ADDR': '192.168.1.50'})
    assert direct.status_code == 302 and direct.headers['Location'].endswith('/login')


def test_prefix_html_leaves_external_and_prefixed_links():
    html = ('<a href="/notes"></a><a href="//cdn.example/x"></a><a href="https://x.example/"></a>'
            f'<a href="{INGRESS}/upload"></a><a href="{INGRESS}"></a><form action="/media">')
    out = homeassistant.prefix_html(html, INGRESS)
    assert out == (f'<a href="{INGRESS}/notes"></a><a href="//cdn.example/x"></a><a href="https://x.example/"></a>'
                   f'<a href="{INGRESS}/upload"></a><a href="{INGRESS}"></a><form action="{INGRESS}/media">')


def test_addon_options_become_config():
    options = {
        'instance_name': '', 'language': 'en', 'use_home_assistant_people': True,
        'who_is_home_from_home_assistant': False, 'exclude_people': ['person.guest'],
        'extra_household_members': ['Grandma', ' '], 'admin_name': 'Boss', 'direct_access_password': '',
        'time_format': '24h', 'calendar_start_day': 'monday', 'weather': True, 'weather_units': 'auto',
        'weather_view': 'detailed', 'max_upload_mb': 500, 'primary_color': '#ff0000',
        'features': {'url_shortener': True, 'recipes': False},
        'reminder_categories': [{'key': 'pets', 'label': 'Pets', 'color': '#00ff00'}],
    }
    ha = {'location_name': 'Himbo HQ', 'latitude': 1.5, 'longitude': 2.5, 'time_zone': 'America/Chicago',
          'unit_system': {'length': 'mi'}}
    cfg = addon.build_config(options, ha)
    assert cfg['instance_name'] == 'Himbo HQ'
    assert cfg['family_members'] == ['Grandma']
    assert cfg['home_assistant'] == {'people': True, 'presence': False, 'exclude_people': ['person.guest']}
    assert cfg['feature_toggles']['url_shortener'] is True
    assert cfg['feature_toggles']['recipes'] is False
    assert cfg['feature_toggles']['notes'] is True
    assert cfg['weather']['units'] == 'imperial'
    assert (cfg['weather']['latitude'], cfg['weather']['longitude']) == (1.5, 2.5)
    assert cfg['reminders'] == {'time_format': '24h', 'calendar_start_day': 'monday',
                                'categories': [{'key': 'pets', 'label': 'Pets', 'color': '#00ff00'}]}
    assert cfg['admin_name'] == 'Boss'
