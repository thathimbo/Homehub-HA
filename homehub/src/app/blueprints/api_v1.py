"""Token-protected JSON API for Home Assistant, Assist, n8n and other automations.

Every request needs ``Authorization: Bearer <api_key>`` (config.yml ``api_key``; the
add-on creates one). A valid key also opens HomeHub's other /api/ endpoints.
"""
import calendar as _calendar
import hmac
import json
import math
from datetime import date, datetime, timedelta

from flask import current_app, jsonify, request

from ..blueprints import main_bp
from ..models import Chore, ExpenseEntry, GroceryHistory, RecurringChore, ShoppingItem, db
from ..security import sanitize_html, sanitize_text

API_VERSION = 1


def api_key() -> str:
    return str((current_app.config.get('HOMEHUB_CONFIG') or {}).get('api_key') or '')


def has_valid_api_key() -> bool:
    """True when the request carries this hub's API key."""
    key = api_key()
    header = request.headers.get('Authorization', '')
    if not key or not header.startswith('Bearer '):
        return False
    return hmac.compare_digest(header[len('Bearer '):].strip().encode(), key.encode())


@main_bp.before_app_request
def _require_api_key():
    if request.path.startswith('/api/v1/') and not has_valid_api_key():
        return jsonify({'ok': False, 'error': 'A valid API key is required (Authorization: Bearer <key>).'}), 401


def _body() -> dict:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _user(data: dict) -> str:
    return sanitize_text(str(data.get('user') or data.get('creator') or 'Home Assistant'))


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], '%Y-%m-%d').date()
    except ValueError:
        return None


def _bad(message, status=400):
    return jsonify({'ok': False, 'error': message}), status


# --- Status ---------------------------------------------------------------------------------

@main_bp.route('/api/v1/status')
def api_v1_status():
    cfg = current_app.config['HOMEHUB_CONFIG']
    from .expenses import _load_expense_settings
    return jsonify({
        'ok': True,
        'api_version': API_VERSION,
        'name': cfg.get('instance_name') or 'HomeHub',
        'household': cfg.get('family_members') or [],
        'currency': _load_expense_settings().get('currency'),
        'currency_code': cfg.get('currency_code') or 'USD',
        'features': cfg.get('feature_toggles') or {},
    })


@main_bp.route('/api/v1/who')
def api_v1_who():
    cfg = current_app.config['HOMEHUB_CONFIG']
    from .dashboard import _who_statuses
    family = list(dict.fromkeys(cfg.get('family_members') or []))
    return jsonify({'ok': True, 'who': _who_statuses(cfg, set(family))})


# --- Shopping list --------------------------------------------------------------------------

def _shopping_dict(i: ShoppingItem) -> dict:
    try:
        tags = json.loads(i.tags or '[]')
    except ValueError:
        tags = []
    return {'id': i.id, 'item': i.item, 'checked': bool(i.checked), 'creator': i.creator, 'tags': tags}


@main_bp.route('/api/v1/shopping', methods=['GET', 'POST'])
def api_v1_shopping():
    if request.method == 'POST':
        data = _body()
        item = sanitize_text(str(data.get('item') or ''))
        if not item:
            return _bad('item is required')
        user = _user(data)
        row = ShoppingItem(item=item, creator=user, tags='[]')
        db.session.add(row)
        db.session.add(GroceryHistory(item=item, creator=user))
        db.session.commit()
        return jsonify({'ok': True, 'item': _shopping_dict(row)}), 201
    items = ShoppingItem.query.order_by(ShoppingItem.checked.asc(), ShoppingItem.timestamp.desc()).all()
    return jsonify({'ok': True, 'items': [_shopping_dict(i) for i in items]})


@main_bp.route('/api/v1/shopping/<int:item_id>', methods=['PATCH', 'DELETE'])
def api_v1_shopping_item(item_id):
    row = db.get_or_404(ShoppingItem, item_id)
    if request.method == 'DELETE':
        db.session.delete(row)
        db.session.commit()
        return jsonify({'ok': True})
    data = _body()
    if 'item' in data:
        text = sanitize_text(str(data.get('item') or ''))
        if not text:
            return _bad('item cannot be empty')
        row.item = text
    if 'checked' in data:
        row.checked = bool(data.get('checked'))
    db.session.commit()
    return jsonify({'ok': True, 'item': _shopping_dict(row)})


# --- Chores ---------------------------------------------------------------------------------

def _chore_dict(c: Chore, rules: dict, today: date) -> dict:
    from .chores import _ticked_for_now
    ticked = bool(c.recurring_id) and _ticked_for_now(c, rules.get(c.recurring_id), today)
    return {
        'id': c.id,
        'description': c.description,
        # A ticked recurring chore waits for its next date with done still false
        'done': bool(c.done) or ticked,
        'due_date': c.due_date.isoformat() if c.due_date else None,
        'creator': c.creator,
        'recurring': bool(c.recurring_id),
    }


@main_bp.route('/api/v1/chores', methods=['GET', 'POST'])
def api_v1_chores():
    from .chores import _ensure_current_recurring_chores
    today = date.today()
    if request.method == 'POST':
        data = _body()
        description = sanitize_text(str(data.get('description') or ''))
        if not description:
            return _bad('description is required')
        row = Chore(description=description, creator=_user(data), due_date=_parse_date(data.get('due_date')), tags='[]')
        db.session.add(row)
        db.session.commit()
        return jsonify({'ok': True, 'chore': _chore_dict(row, {}, today)}), 201
    _ensure_current_recurring_chores(today)
    rules = {r.id: r for r in RecurringChore.query.all()}
    chores = Chore.query.order_by(Chore.done.asc(), Chore.due_date.asc(), Chore.timestamp.desc()).all()
    return jsonify({'ok': True, 'chores': [_chore_dict(c, rules, today) for c in chores]})


@main_bp.route('/api/v1/chores/<int:chore_id>', methods=['PATCH', 'DELETE'])
def api_v1_chore(chore_id):
    from .chores import toggle_chore
    row = db.get_or_404(Chore, chore_id)
    today = date.today()
    if request.method == 'DELETE':
        db.session.delete(row)
        db.session.commit()
        return jsonify({'ok': True})
    data = _body()
    if 'description' in data:
        text = sanitize_text(str(data.get('description') or ''))
        if not text:
            return _bad('description cannot be empty')
        row.description = text
    if 'due_date' in data and not row.recurring_id:
        row.due_date = _parse_date(data.get('due_date'))
    db.session.commit()
    if 'done' in data:
        rules = {r.id: r for r in RecurringChore.query.all()}
        if bool(data['done']) != _chore_dict(row, rules, today)['done']:
            # The same tick as the Chores page, so recurring chores move on to their next date
            toggle_chore(chore_id)
            db.session.refresh(row)
    rules = {r.id: r for r in RecurringChore.query.all()}
    return jsonify({'ok': True, 'chore': _chore_dict(row, rules, today)})


# --- Calendar -------------------------------------------------------------------------------

def _months_between(start: date, end: date):
    cur = start.replace(day=1)
    while cur <= end:
        yield cur
        cur = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)


@main_bp.route('/api/v1/calendar', methods=['GET', 'POST'])
def api_v1_calendar():
    from .dashboard import api_reminders_create, api_reminders_list
    if request.method == 'POST':
        data = _body()
        payload = {
            'title': data.get('title') or data.get('summary') or '',
            'description': sanitize_html(str(data.get('description') or '')),
            'creator': _user(data),
            'start_date': data.get('start_date') or data.get('date'),
            'start_time': data.get('start_time') or data.get('time'),
            'end_date': data.get('end_date'),
            'end_time': data.get('end_time'),
            'category': data.get('category'),
        }
        with current_app.test_request_context('/api/reminders', method='POST', json=payload):
            return api_reminders_create()
    today = date.today()
    start = _parse_date(request.args.get('start')) or today
    end = _parse_date(request.args.get('end')) or (start + timedelta(days=30))
    if end < start:
        return _bad('end is before start')
    if (end - start).days > 400:
        return _bad('ask for at most 400 days at a time')
    events, seen = [], set()
    for month in _months_between(start, end):
        with current_app.test_request_context(f'/api/reminders?scope=month&date={month.isoformat()}'):
            listing = api_reminders_list().get_json()
        for r in listing.get('reminders') or []:
            key = (r.get('id'), r.get('date'))
            first = _parse_date(r.get('start_date') or r.get('date'))
            last = _parse_date(r.get('end_date')) or first
            if key in seen or not first or last < start or first > end:
                continue
            seen.add(key)
            events.append(r)
    return jsonify({'ok': True, 'start': start.isoformat(), 'end': end.isoformat(), 'events': events})


# --- Expenses -------------------------------------------------------------------------------

@main_bp.route('/api/v1/expenses/summary')
def api_v1_expenses_summary():
    from .expenses import _generate_recurring_entries_until, _load_expense_settings
    today = date.today()
    try:
        year = int(request.args.get('year') or today.year)
        month = int(request.args.get('month') or today.month)
        first = date(year, month, 1)
    except ValueError:
        return _bad('invalid year or month')
    last = date(year, month, _calendar.monthrange(year, month)[1])
    _generate_recurring_entries_until(min(today, last))
    rows = ExpenseEntry.query.filter(
        ExpenseEntry.date >= first, ExpenseEntry.date <= last,
        db.or_(ExpenseEntry.skipped.is_(None), ExpenseEntry.skipped == False),  # noqa: E712
        db.or_(ExpenseEntry.is_settlement.is_(None), ExpenseEntry.is_settlement == False),  # noqa: E712
    ).all()
    by_person, by_category = {}, {}
    for e in rows:
        by_person[e.payer or ''] = by_person.get(e.payer or '', 0.0) + (e.amount or 0.0)
        by_category[e.category or ''] = by_category.get(e.category or '', 0.0) + (e.amount or 0.0)
    settings = _load_expense_settings()
    places = settings.get('fraction_precision', 2)
    return jsonify({
        'ok': True,
        'year': year,
        'month': month,
        'currency': settings.get('currency'),
        'currency_code': current_app.config['HOMEHUB_CONFIG'].get('currency_code') or 'USD',
        'total': round(sum(e.amount or 0.0 for e in rows), places),
        'count': len(rows),
        'by_person': {k: round(v, places) for k, v in by_person.items()},
        'by_category': {k: round(v, places) for k, v in by_category.items()},
    })


@main_bp.route('/api/v1/expenses', methods=['POST'])
def api_v1_expenses_add():
    data = _body()
    title = sanitize_text(str(data.get('title') or data.get('description') or ''))
    try:
        amount = float(data.get('amount'))
    except (TypeError, ValueError):
        return _bad('amount must be a number')
    if not title:
        return _bad('title is required')
    if not math.isfinite(amount) or amount <= 0:
        return _bad('amount must be greater than zero')
    when = _parse_date(data.get('date')) or date.today()
    entry = ExpenseEntry(date=when, title=title, amount=amount, unit_price=amount, quantity=1.0,
                         category=sanitize_text(str(data.get('category') or '')) or None, payer=_user(data))
    db.session.add(entry)
    db.session.commit()
    return jsonify({'ok': True, 'expense': {'id': entry.id, 'date': when.isoformat(), 'title': title,
                                             'amount': amount, 'payer': entry.payer}}), 201

