# HomeHub for Home Assistant

A Home Assistant add-on version of [HomeHub](https://github.com/surajverma/homehub), the
self-hosted family dashboard: shared notes, shopping list, chores, calendar and reminders,
expenses, recipes, expiry tracker, shared files, media downloader and more.

This version:

- opens from the Home Assistant sidebar and uses your Home Assistant login,
- uses the people in Home Assistant as the household,
- fills "Who is Home?" from each person's home/away/zone state,
- picks up your time zone, location, units and currency from Home Assistant (US formats by default),
- adds a Home Assistant integration: shopping list and chores as to-do lists, the calendar,
  a spending sensor, and Assist voice commands,
- has a JSON API for n8n and other tools.

## Install

1. In Home Assistant go to **Settings → Add-ons → Add-on Store**.
2. Top-right menu (⋮) → **Repositories** → add `https://github.com/thathimbo/Homehub-HA` → **Add**.
3. Find **HomeHub** in the store → **Install** (the first build takes a few minutes).
4. **Start** it and turn on **Show in sidebar**.

Options and file locations are in [homehub/DOCS.md](homehub/DOCS.md).

## Layout

```
repository.yaml      Home Assistant add-on repository
homehub/             the add-on (config.yaml, Dockerfile, docs)
homehub/src/         the HomeHub app (Flask) and its tests
homehub/integration/ the Home Assistant integration the add-on installs, and its tests
```

## Development

```sh
cd homehub/src
pip install -r requirements-dev.txt
python -m pytest

# The Home Assistant integration (separate environment; it needs Home Assistant itself)
cd homehub/integration
pip install pytest-homeassistant-custom-component
python -m pytest
```

Run outside Home Assistant the same way as upstream HomeHub: copy `config-example.yml` to
`config.yml` and run `python run.py`. Without `SUPERVISOR_TOKEN` the Home Assistant parts
are off.

## Credits

HomeHub is by [surajverma](https://github.com/surajverma/homehub), MIT licensed (see `LICENSE`).
