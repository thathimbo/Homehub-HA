# HomeHub

A family dashboard for the people in your home: shared notes, shopping list, chores,
calendar and reminders, expenses, recipes, expiry tracker, shared files, media downloader
and more. It opens from the Home Assistant sidebar.

## What comes from Home Assistant

| HomeHub | Home Assistant |
| --- | --- |
| Household members | Every person in **Settings → People** (plus *Extra household members*, minus *Leave out these people*) |
| Who is Home? | Each person's state: `home` → Home, `not_home` → Away, a zone → the zone's name |
| Current user | The Home Assistant user who opened the panel (matched through their person) |
| Sign-in | Home Assistant's own login |
| Time zone, weather location, units | Your Home Assistant general settings |

People without a Home Assistant login (kids, a partner who doesn't use HA) can still be
added as a person in **Settings → People** with no user. They will show up in HomeHub and
can be picked from the user menu.

## Setup

1. Install the add-on and start it.
2. Turn on **Show in sidebar**.
3. Open **HomeHub** from the sidebar.

Everything else is optional and lives on the add-on's **Configuration** tab.

## Where your files go

| What | Where |
| --- | --- |
| Database, settings, compressed PDFs | Add-on storage (included in add-on backups) |
| Shared Cloud uploads | `/share/homehub/uploads` |
| Media Downloader files | `/media/homehub` (shows in **Media → My media**) |

## Admin

The admin user can edit or delete anything. Set **Admin password** so switching to the
admin user asks for it. Leaving it blank removes the password.

## Opening HomeHub without Home Assistant

Not needed for normal use. If you want it on its own address (for example a wall tablet
without a Home Assistant login), go to the **Network** section, give port 5000/tcp a host
port, and set **Direct access password**.

## Good to know

- Renaming a person in Home Assistant gives them a new name in HomeHub. Items they created
  stay under the old name.
- If Home Assistant restarts, HomeHub keeps the last list of people it read.
