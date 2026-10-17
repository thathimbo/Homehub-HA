# Changelog

## 1.1.0

- US formats: amounts in dollars (or Home Assistant's currency) with 1,234.50 style
  numbers, and month/day/year dates. *Date format* option for ISO or day/month/year.
- New Home Assistant integration, installed by the add-on: shopping list and chores as
  to-do lists, the calendar as a calendar entity, a "spending this month" sensor, and a
  "HomeHub: Add expense" action.
- Assist: "add milk to my shopping list", "add an expense of 20 dollars for groceries".
- JSON API with an API key, for n8n and other tools.

## 1.0.0

- First release as a Home Assistant add-on, based on HomeHub by surajverma.
- Opens from the Home Assistant sidebar (ingress); Home Assistant handles sign-in.
- Household members come from Home Assistant people, plus any extra names in the options.
- "Who is Home?" follows each person's home/away/zone state.
- The person signed in to Home Assistant is picked as the HomeHub user automatically.
- Time zone, location (weather) and units come from Home Assistant.
- Settings move to the add-on Configuration tab. Data lives in add-on storage (backed up with the add-on); Shared Cloud files in /share/homehub/uploads; downloads in /media/homehub.
