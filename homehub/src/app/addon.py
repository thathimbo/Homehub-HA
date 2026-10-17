"""Start HomeHub as a Home Assistant add-on.

Reads the add-on options (/data/options.json), writes the config.yml HomeHub reads, takes
the time zone, location and units from Home Assistant, applies the admin password, then
hands over to gunicorn. Run with ``python -m app.addon``.
"""
import json
import logging
import os
import secrets
import shutil
import socket
import sys

import requests
import yaml

from . import homeassistant

log = logging.getLogger('homehub.addon')

OPTIONS_PATH = os.environ.get('HOMEHUB_ADDON_OPTIONS', '/data/options.json')

FEATURES = (
    'shopping_list', 'media_downloader', 'pdf_compressor', 'qr_generator', 'notes',
    'shared_cloud', 'who_is_home', 'personal_status', 'chores', 'recipes',
    'expiry_tracker', 'url_shortener', 'expense_tracker', 'calendar',
)

DATE_FORMATS = {'us': '%m/%d/%Y', 'iso': '%Y-%m-%d', 'eu': '%d/%m/%Y'}

# The Home Assistant integration (to-do lists, calendar, spending sensor for Assist and automations)
INTEGRATION_SOURCE = os.environ.get('HOMEHUB_INTEGRATION_SOURCE', '/integration/homehub')
HA_CONFIG_DIR = os.environ.get('HOMEHUB_HA_CONFIG_DIR', '/homeassistant')
API_PORT = 5000

GUNICORN_COMMAND = [
    'gunicorn', 'wsgi:app', '-w', '1', '-k', 'gthread', '--threads', '4',
    '-b', '0.0.0.0:5000', '--access-logfile', '-', '--error-logfile', '-',
]


def _clean_list(values) -> list[str]:
    return [str(v).strip() for v in (values or []) if str(v).strip()]


def _weather_units(choice: str, ha_config: dict) -> str:
    if choice in ('metric', 'imperial'):
        return choice
    # "auto": follow Home Assistant's unit system
    length = ((ha_config.get('unit_system') or {}).get('length') or '').lower()
    return 'imperial' if length == 'mi' else 'metric'


def _currency(ha_config: dict) -> tuple[str, str]:
    """Home Assistant's currency as (symbol, ISO code); US dollars when it has none."""
    code = str(ha_config.get('currency') or 'USD').upper()
    try:
        from babel.numbers import get_currency_symbol
        return get_currency_symbol(code, locale='en_US'), code
    except Exception:
        return '$', 'USD'


def build_config(options: dict, ha_config: dict, api_key: str = '') -> dict:
    """The config.yml contents for these add-on options."""
    features = options.get('features') or {}
    weather_on = bool(options.get('weather', True))
    currency, currency_code = _currency(ha_config)
    config = {
        'instance_name': options.get('instance_name') or ha_config.get('location_name') or 'HomeHub',
        # Only asked for when HomeHub is opened on its own port; Home Assistant signs people in for the sidebar panel
        'password': options.get('direct_access_password') or '',
        'admin_name': options.get('admin_name') or 'Administrator',
        'max_upload_mb': options.get('max_upload_mb', 1024),
        'language': options.get('language') or 'en',
        'currency': currency,
        'currency_code': currency_code,
        'date_format': DATE_FORMATS.get(options.get('date_format') or 'us', DATE_FORMATS['us']),
        'api_key': api_key,
        'feature_toggles': {name: bool(features.get(name, name != 'url_shortener')) for name in FEATURES},
        # Home Assistant people come first; these are extra names (e.g. someone without an HA account)
        'family_members': _clean_list(options.get('extra_household_members')),
        'home_assistant': {
            'people': bool(options.get('use_home_assistant_people', True)),
            'presence': bool(options.get('who_is_home_from_home_assistant', True)),
            'exclude_people': _clean_list(options.get('exclude_people')),
        },
        'reminders': {
            'time_format': options.get('time_format') or '12h',
            'calendar_start_day': options.get('calendar_start_day') or 'sunday',
            'categories': [
                {'key': c.get('key'), 'label': c.get('label') or c.get('key'), 'color': c.get('color')}
                for c in (options.get('reminder_categories') or []) if c.get('key')
            ],
        },
        'weather': {
            'enabled': weather_on,
            'label': ha_config.get('location_name') or '',
            'latitude': ha_config.get('latitude', '') if weather_on else '',
            'longitude': ha_config.get('longitude', '') if weather_on else '',
            'timezone': ha_config.get('time_zone') or '',
            'units': _weather_units(options.get('weather_units') or 'auto', ha_config),
            'view': options.get('weather_view') or 'compact',
        },
        'theme': {'primary_color': options.get('primary_color') or '#1d4ed8'},
    }
    return config


def _api_key(options: dict, data_dir: str) -> str:
    """The api_key option, or one made on first start and kept in add-on storage."""
    chosen = str(options.get('api_key') or '').strip()
    if chosen:
        return chosen
    path = os.path.join(data_dir, 'api_key')
    try:
        with open(path, encoding='utf-8') as f:
            existing = f.read().strip()
        if existing:
            return existing
    except FileNotFoundError:
        pass
    key = secrets.token_urlsafe(32)
    os.makedirs(data_dir, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(key)
    return key


def _addon_hostname() -> str:
    """The name Home Assistant reaches this add-on by on its internal network."""
    if homeassistant.available():
        try:
            response = requests.get(f'{homeassistant.SUPERVISOR_URL}/addons/self/info',
                                    headers={'Authorization': f'Bearer {homeassistant.supervisor_token()}'},
                                    timeout=homeassistant.REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            hostname = (response.json().get('data') or {}).get('hostname')
            if hostname:
                return hostname
        except Exception:
            log.warning('Could not read this add-on\'s hostname from the Supervisor', exc_info=True)
    return socket.gethostname()


def _manifest_version(folder: str) -> str | None:
    try:
        with open(os.path.join(folder, 'manifest.json'), encoding='utf-8') as f:
            return json.load(f).get('version')
    except (OSError, ValueError):
        return None


def install_integration(api_key: str, url: str) -> bool:
    """Put the HomeHub integration in Home Assistant's custom_components; True when it is new or updated.

    Next to it goes addon.json with this add-on's address and API key, so adding the
    integration in Home Assistant needs no typing.
    """
    if not os.path.isdir(INTEGRATION_SOURCE) or not os.path.isdir(HA_CONFIG_DIR):
        log.warning('Home Assistant\'s config folder is not available; skipping the integration install')
        return False
    target = os.path.join(HA_CONFIG_DIR, 'custom_components', 'homehub')
    changed = _manifest_version(target) != _manifest_version(INTEGRATION_SOURCE)
    if changed:
        if os.path.isdir(target):
            shutil.rmtree(target)
        shutil.copytree(INTEGRATION_SOURCE, target)
        log.info('Installed the HomeHub integration in %s', target)
    # Assist sentences ("add an expense of 20 dollars for groceries")
    sentences = os.path.join(INTEGRATION_SOURCE, 'sentences', 'en.yaml')
    if os.path.isfile(sentences):
        sentences_dir = os.path.join(HA_CONFIG_DIR, 'custom_sentences', 'en')
        os.makedirs(sentences_dir, exist_ok=True)
        shutil.copyfile(sentences, os.path.join(sentences_dir, 'homehub.yaml'))
    hint = os.path.join(target, 'addon.json')
    fd = os.open(hint, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        json.dump({'url': url, 'api_key': api_key}, f)
    return changed


def _notify(title: str, message: str) -> None:
    if not homeassistant.available():
        return
    try:
        requests.post(f'{homeassistant.SUPERVISOR_URL}/core/api/services/persistent_notification/create',
                      headers={'Authorization': f'Bearer {homeassistant.supervisor_token()}'},
                      json={'title': title, 'message': message, 'notification_id': 'homehub_integration'},
                      timeout=homeassistant.REQUEST_TIMEOUT_SECONDS)
    except Exception:
        log.warning('Could not post a notification to Home Assistant', exc_info=True)


def _write_config(config: dict, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        yaml.safe_dump(config, f, sort_keys=False, allow_unicode=True)
    os.replace(tmp, path)


def _sync_admin_password(password: str) -> None:
    """The admin password option is the source of truth: set it when given, remove it when blank."""
    from . import admin, create_app
    app = create_app()
    with app.app_context():
        if password:
            if len(password) < admin.ADMIN_PASSWORD_MIN_LENGTH:
                log.error('admin_password must be at least %s characters; leaving the admin password unchanged',
                          admin.ADMIN_PASSWORD_MIN_LENGTH)
                return
            admin.set_admin_password(password)
        elif admin.admin_password_enabled():
            admin.clear_admin_password()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format='[homehub] %(message)s')
    try:
        with open(OPTIONS_PATH, encoding='utf-8') as f:
            options = json.load(f)
    except (OSError, ValueError):
        log.warning('Could not read %s; starting with the default options', OPTIONS_PATH)
        options = {}

    ha_config = homeassistant.core_config()
    if ha_config.get('time_zone'):
        # Due dates and recurring items use the container's local time
        os.environ['TZ'] = ha_config['time_zone']

    config_path = os.environ.get('HOMEHUB_CONFIG') or os.path.join(os.getcwd(), 'config.yml')
    data_dir = os.environ.get('HOMEHUB_DATA_DIR') or os.path.dirname(config_path)
    key = _api_key(options, data_dir)
    _write_config(build_config(options, ha_config, key), config_path)
    log.info('Wrote %s', config_path)
    log.info('API key (for n8n and other tools, header "Authorization: Bearer <key>"): %s', key)

    if options.get('install_ha_integration', True):
        url = f'http://{_addon_hostname()}:{API_PORT}'
        try:
            if install_integration(key, url):
                _notify('HomeHub is ready for Home Assistant',
                        'The HomeHub integration was installed or updated. Restart Home Assistant '
                        '(Settings → System → Restart), then go to Settings → Devices & services → '
                        '**Add integration** → **HomeHub**. It fills itself in.')
        except Exception:
            log.exception('Could not install the HomeHub integration')

    _sync_admin_password(str(options.get('admin_password') or ''))

    sys.stdout.flush()
    os.execvp(GUNICORN_COMMAND[0], GUNICORN_COMMAND)


if __name__ == '__main__':
    main()
