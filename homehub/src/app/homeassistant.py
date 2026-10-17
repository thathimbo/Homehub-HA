"""Home Assistant integration, used when HomeHub runs as a Home Assistant add-on.

Three things come from Home Assistant:

* the household: every ``person.*`` entity becomes a family member,
* "Who is Home?": each person's home/away/zone state,
* the signed-in user: Home Assistant's ingress proxy says which user opened the panel.

All of it is switched on from the ``home_assistant`` section of config.yml, which the
add-on writes from its options. Outside Home Assistant (no SUPERVISOR_TOKEN) nothing here
changes how the app behaves.
"""
import logging
import os
import re
import threading
import time

import requests
from flask import g, has_request_context, request

log = logging.getLogger(__name__)

SUPERVISOR_URL = os.environ.get('SUPERVISOR_URL', 'http://supervisor')
# The Supervisor's ingress proxy always connects from this address
INGRESS_PROXY_ADDRESSES = {'172.30.32.2'}
_INGRESS_PATH_RE = re.compile(r'^/api/hassio_ingress/[A-Za-z0-9_\-]+$')

PEOPLE_CACHE_SECONDS = 30
REQUEST_TIMEOUT_SECONDS = 5

# Person states that say nothing about where someone is
_UNKNOWN_STATES = {'unknown', 'unavailable', ''}
PRESENCE_LABELS = {'home': 'Home', 'not_home': 'Away'}

_people_lock = threading.Lock()
_people_cache = {'at': 0.0, 'people': None}


def supervisor_token() -> str | None:
    return os.environ.get('SUPERVISOR_TOKEN') or None


def available() -> bool:
    return bool(supervisor_token())


def _core_get(path: str):
    response = requests.get(
        f'{SUPERVISOR_URL}/core/api{path}',
        headers={'Authorization': f'Bearer {supervisor_token()}'},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def core_config() -> dict:
    """Home Assistant's own settings (time zone, location, units); empty when unreachable."""
    if not available():
        return {}
    try:
        return _core_get('/config') or {}
    except Exception:
        log.warning('Could not read the Home Assistant configuration', exc_info=True)
        return {}


def _fetch_people() -> list[dict]:
    people = []
    for state in _core_get('/states'):
        entity_id = state.get('entity_id') or ''
        if not entity_id.startswith('person.'):
            continue
        attributes = state.get('attributes') or {}
        name = str(attributes.get('friendly_name') or entity_id.split('.', 1)[1]).strip()
        if not name:
            continue
        people.append({
            'entity_id': entity_id,
            'name': name,
            'user_id': attributes.get('user_id'),
            'state': str(state.get('state') or ''),
        })
    people.sort(key=lambda p: p['name'].lower())
    return people


def people() -> list[dict]:
    """The ``person.*`` entities, re-read at most every PEOPLE_CACHE_SECONDS.

    When Home Assistant can't be reached the last list read is kept, so a restart of
    Home Assistant does not empty the household for a moment.
    """
    if not available():
        return []
    with _people_lock:
        fresh = time.monotonic() - _people_cache['at'] < PEOPLE_CACHE_SECONDS
        if fresh and _people_cache['people'] is not None:
            return list(_people_cache['people'])
        try:
            _people_cache['people'] = _fetch_people()
        except Exception:
            log.warning('Could not read people from Home Assistant', exc_info=True)
            if _people_cache['people'] is None:
                return []
        _people_cache['at'] = time.monotonic()
        return list(_people_cache['people'])


def _settings(config: dict) -> dict:
    return config.get('home_assistant') or {}


def household(config: dict) -> list[dict]:
    """People from Home Assistant that belong to the household (exclusions removed)."""
    excluded = {str(x).strip().lower() for x in (_settings(config).get('exclude_people') or [])}
    return [p for p in people()
            if p['entity_id'].lower() not in excluded and p['name'].lower() not in excluded]


def apply_to_config(config: dict) -> dict:
    """Make Home Assistant's people the family members, followed by any extra names from config.yml."""
    settings = _settings(config)
    if not settings.get('people') or not available():
        return config
    names = [p['name'] for p in household(config)]
    extra = [str(x).strip() for x in (config.get('family_members') or []) if str(x).strip()]
    config['family_members'] = list(dict.fromkeys(names + extra))
    return config


def presence_enabled(config: dict) -> bool:
    return bool(_settings(config).get('presence')) and available()


def presence_statuses(config: dict) -> dict[str, str]:
    """"Who is Home?" statuses from each person's state: Home, Away, or the zone they are in."""
    statuses = {}
    for person in household(config):
        state = person['state']
        if state.lower() in _UNKNOWN_STATES:
            continue
        statuses[person['name']] = PRESENCE_LABELS.get(state, state)
    return statuses


# --- Ingress -------------------------------------------------------------------------------

class IngressMiddleware:
    """Serve the app under the path Home Assistant's ingress proxy gives it.

    The proxy strips its /api/hassio_ingress/<token> prefix before passing the request on
    and names it in X-Ingress-Path. Setting SCRIPT_NAME to it makes url_for() and redirects
    point back through the proxy. The header is only trusted from the proxy's own address.
    """

    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        ingress_path = environ.get('HTTP_X_INGRESS_PATH', '')
        if environ.get('REMOTE_ADDR') in INGRESS_PROXY_ADDRESSES and _INGRESS_PATH_RE.match(ingress_path):
            environ['SCRIPT_NAME'] = ingress_path
            environ['homehub.ingress'] = True
        return self.wsgi_app(environ, start_response)


def is_ingress() -> bool:
    return has_request_context() and bool(request.environ.get('homehub.ingress'))


def ingress_base() -> str:
    return request.script_root if is_ingress() else ''


def signed_in_person(config: dict) -> str | None:
    """The household member who opened HomeHub from the Home Assistant sidebar, if known."""
    if not is_ingress():
        return None
    if hasattr(g, '_ha_person'):
        return g._ha_person
    name = None
    user_id = request.headers.get('X-Remote-User-Id')
    family = set(config.get('family_members') or [])
    if user_id:
        for person in household(config):
            if person['user_id'] == user_id and person['name'] in family:
                name = person['name']
                break
    if not name:
        # A user without a person entity, or one whose person is excluded: match by display name
        display = (request.headers.get('X-Remote-User-Display-Name') or '').strip()
        if display in family:
            name = display
    g._ha_person = name
    return name


# Attributes holding a site-absolute path ("/notes", but not "//cdn.example")
_ABSOLUTE_ATTR_RE = re.compile(r'''(\s(?:href|src|action|formaction|poster)=)(["'])/(?!/)''')


def prefix_html(html: str, base: str) -> str:
    """Point site-absolute links in a page through the ingress path, leaving ones that already are."""
    already = base.lstrip('/') + '/'

    def fix(match):
        quote = match.group(2)
        rest = html[match.end():match.end() + len(already)]
        if rest == already or rest == already[:-1] + quote:
            return match.group(0)
        return f'{match.group(1)}{quote}{base}/'

    return _ABSOLUTE_ATTR_RE.sub(fix, html)


def init_app(app):
    app.wsgi_app = IngressMiddleware(app.wsgi_app)

    @app.after_request
    def route_through_ingress(response):
        if not is_ingress():
            return response
        base = request.script_root
        location = response.headers.get('Location', '')
        if location.startswith('/') and not location.startswith('//') and \
                location != base and not location.startswith(base + '/'):
            response.headers['Location'] = base + location
        # Only the app's own pages: files people uploaded are sent as they are
        if response.mimetype == 'text/html' and not response.direct_passthrough \
                and not response.is_streamed and 'Content-Disposition' not in response.headers:
            response.set_data(prefix_html(response.get_data(as_text=True), base))
        return response
