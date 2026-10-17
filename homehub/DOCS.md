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
| Time zone, weather location, units, currency | Your Home Assistant general settings (dollars and month/day/year dates unless you change them) |

People without a Home Assistant login (kids, a partner who doesn't use HA) can still be
added as a person in **Settings → People** with no user. They will show up in HomeHub and
can be picked from the user menu.

## Setup

1. Install the add-on and start it.
2. Turn on **Show in sidebar**.
3. Open **HomeHub** from the sidebar.

Everything else is optional and lives on the add-on's **Configuration** tab.

## Assist, automations and dashboards

The add-on puts a **HomeHub integration** into Home Assistant (switch it off with
*Install the Home Assistant integration*). One-time setup:

1. Start the add-on. A notification says HomeHub is ready.
2. Restart Home Assistant (**Settings → System → Restart**).
3. **Settings → Devices & services → Add integration → HomeHub**. The form is already
   filled in. Select **Submit**.

You then get:

| Entity | What it is |
| --- | --- |
| `todo.shopping_list` | HomeHub's shopping list |
| `todo.chores` | HomeHub's chores (ticking a repeating chore moves it to its next date) |
| `calendar.homehub` | HomeHub's calendar |
| `sensor.homehub_spending_this_month` | This month's spending, split per person in its attributes |

And an action, **HomeHub: Add expense** (`homehub.add_expense`).

### Talking to it with Assist

Once you set up a voice assistant (**Settings → Voice assistants**), check the
**Expose** tab lists the entities above. Then you can say:

- "Add milk to my shopping list"
- "Add mow the lawn to my chores"
- "Add an expense of 20 dollars for groceries" / "I spent 35 dollars on gas"

Expenses are saved under whoever is talking, when their Home Assistant user is linked to a person.

If Home Assistant's own **Shopping List** integration is also installed, there are two
lists with the same name and Assist can't tell them apart. Delete the built-in one under
**Settings → Devices & services** if you don't use it.

### n8n and other tools

HomeHub has a JSON API. Every request needs the header
`Authorization: Bearer <API key>`. The key is printed in the add-on **Log** each time it
starts (or set your own with *API key*).

Address:

- n8n running as a Home Assistant add-on: the address in the HomeHub integration
  (looks like `http://xxxxxxxx-homehub:5000`).
- n8n somewhere else: give port 5000/tcp a host port in the add-on's **Network** section
  and use `http://<your Home Assistant IP>:5000`.

| Method and path | What it does | Body (JSON) |
| --- | --- | --- |
| `GET /api/v1/status` | Name, household, currency, enabled features | |
| `GET /api/v1/who` | Who is home | |
| `GET /api/v1/shopping` | Shopping list | |
| `POST /api/v1/shopping` | Add an item | `{"item": "Milk", "user": "Logan"}` |
| `PATCH /api/v1/shopping/<id>` | Tick or rename | `{"checked": true}` |
| `DELETE /api/v1/shopping/<id>` | Remove | |
| `GET /api/v1/chores` | Chores | |
| `POST /api/v1/chores` | Add a chore | `{"description": "Trash", "due_date": "2026-10-20"}` |
| `PATCH /api/v1/chores/<id>` | Tick, rename or move | `{"done": true}` |
| `DELETE /api/v1/chores/<id>` | Remove | |
| `GET /api/v1/calendar?start=2026-10-01&end=2026-10-31` | Events in a date range | |
| `POST /api/v1/calendar` | Add an event | `{"title": "Vet", "date": "2026-10-20", "time": "14:30"}` |
| `GET /api/v1/expenses/summary?year=2026&month=10` | Month total, per person and category | |
| `POST /api/v1/expenses` | Add an expense | `{"title": "Gas", "amount": 35.25, "user": "Logan"}` |

`user` is optional everywhere; it defaults to "Home Assistant".

You can also skip the API and use n8n's Home Assistant node with the `todo.add_item`,
`calendar.create_event` and `homehub.add_expense` actions.

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
