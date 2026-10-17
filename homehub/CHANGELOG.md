# Changelog

## 1.0.0

- First release as a Home Assistant add-on, based on HomeHub by surajverma.
- Opens from the Home Assistant sidebar (ingress); Home Assistant handles sign-in.
- Household members come from Home Assistant people, plus any extra names in the options.
- "Who is Home?" follows each person's home/away/zone state.
- The person signed in to Home Assistant is picked as the HomeHub user automatically.
- Time zone, location (weather) and units come from Home Assistant.
- Settings move to the add-on Configuration tab. Data lives in add-on storage (backed up with the add-on); Shared Cloud files in /share/homehub/uploads; downloads in /media/homehub.
