"""Start HomeHub as a Home Assistant add-on.

Reads the add-on options (/data/options.json), writes the config.yml HomeHub reads, takes
the time zone, location and units from Home Assistant, applies the admin password, then
hands over to gunicorn. Run with ``python -m app.addon``.
"""
import json
import logging
import os
import sys

import yaml

from . import homeassistant

log = logging.getLogger('homehub.addon')

OPTIONS_PATH = os.environ.get('HOMEHUB_ADDON_OPTIONS', '/data/options.json')

FEATURES = (
    'shopping_list', 'media_downloader', 'pdf_compressor', 'qr_generator', 'notes',
    'shared_cloud', 'who_is_home', 'personal_status', 'chores', 'recipes',
    'expiry_tracker', 'url_shortener', 'expense_tracker', 'calendar',
)

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


def build_config(options: dict, ha_config: dict) -> dict:
    """The config.yml contents for these add-on options."""
    features = options.get('features') or {}
    weather_on = bool(options.get('weather', True))
    config = {
        'instance_name': options.get('instance_name') or ha_config.get('location_name') or 'HomeHub',
        # Only asked for when HomeHub is opened on its own port; Home Assistant signs people in for the sidebar panel
        'password': options.get('direct_access_password') or '',
        'admin_name': options.get('admin_name') or 'Administrator',
        'max_upload_mb': options.get('max_upload_mb', 1024),
        'language': options.get('language') or 'en',
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
    _write_config(build_config(options, ha_config), config_path)
    log.info('Wrote %s', config_path)

    _sync_admin_password(str(options.get('admin_password') or ''))

    sys.stdout.flush()
    os.execvp(GUNICORN_COMMAND[0], GUNICORN_COMMAND)


if __name__ == '__main__':
    main()
