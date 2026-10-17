"""The HomeHub integration: setup, to-do lists, calendar, spending, add_expense and Assist."""
from datetime import date, timedelta
import json

import pytest

from homeassistant import config_entries
from homeassistant.const import CONF_API_KEY, CONF_URL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import intent
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.homehub import config_flow
from custom_components.homehub.const import DOMAIN

URL = "http://abc123-homehub:5000"
KEY = "secret"
API = f"{URL}/api/v1"
TODAY = date.today()

STATUS = {"ok": True, "api_version": 1, "name": "Our Home", "household": ["Logan"], "currency": "$",
          "currency_code": "USD", "features": {"shopping_list": True, "chores": True, "calendar": True,
                                               "expense_tracker": True}}
SHOPPING = {"ok": True, "items": [{"id": 1, "item": "Milk", "checked": False, "creator": "Logan", "tags": []},
                                  {"id": 2, "item": "Eggs", "checked": True, "creator": "Logan", "tags": []}]}
CHORES = {"ok": True, "chores": [{"id": 7, "description": "Trash", "done": False,
                                  "due_date": TODAY.isoformat(), "creator": "Logan", "recurring": True}]}
EVENTS = {"ok": True, "events": [
    {"id": 3, "date": (TODAY + timedelta(days=1)).isoformat(), "start_date": (TODAY + timedelta(days=1)).isoformat(),
     "start_time": "14:30", "end_date": None, "end_time": None, "all_day": False, "title": "Vet", "description": ""},
    {"id": 4, "date": (TODAY + timedelta(days=5)).isoformat(), "start_date": None, "start_time": None,
     "end_date": None, "end_time": None, "all_day": True, "title": "Trip", "description": "Lake"},
]}
SUMMARY = {"ok": True, "total": 72.5, "currency": "$", "currency_code": "USD", "count": 2,
           "by_person": {"Logan": 42.5, "Sam": 30.0}, "by_category": {"": 72.5}}


def mock_api(aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(f"{API}/status", json=STATUS)
    aioclient_mock.get(f"{API}/shopping", json=SHOPPING)
    aioclient_mock.post(f"{API}/shopping", json={"ok": True, "item": {}}, status=201)
    aioclient_mock.get(f"{API}/chores", json=CHORES)
    aioclient_mock.patch(f"{API}/chores/7", json={"ok": True, "chore": {}})
    aioclient_mock.get(f"{API}/calendar", json=EVENTS)
    aioclient_mock.post(f"{API}/calendar", json={"ok": True})
    aioclient_mock.get(f"{API}/expenses/summary", json=SUMMARY)
    aioclient_mock.post(f"{API}/expenses", json={"ok": True, "expense": {"id": 9}}, status=201)


def sent(aioclient_mock: AiohttpClientMocker, method: str, path: str) -> list:
    """Bodies of the requests made to one endpoint."""
    return [call[2] for call in aioclient_mock.mock_calls
            if call[0].upper() == method and str(call[1]).split("?")[0] == f"{API}{path}"]


async def setup_entry(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> MockConfigEntry:
    mock_api(aioclient_mock)
    entry = MockConfigEntry(domain=DOMAIN, title="Our Home", unique_id=DOMAIN, data={CONF_URL: URL, CONF_API_KEY: KEY})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_config_flow_is_filled_in_by_the_addon(hass, aioclient_mock, tmp_path, monkeypatch):
    hint = tmp_path / "addon.json"
    hint.write_text(json.dumps({"url": URL, "api_key": KEY}))
    monkeypatch.setattr(config_flow, "ADDON_HINT", str(hint))
    mock_api(aioclient_mock)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    schema = result["data_schema"]({})
    assert schema == {CONF_URL: URL, CONF_API_KEY: KEY}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], schema)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Our Home"
    assert aioclient_mock.mock_calls[0][3]["Authorization"] == f"Bearer {KEY}"


async def test_config_flow_reports_a_wrong_key(hass, aioclient_mock, monkeypatch):
    monkeypatch.setattr(config_flow, "ADDON_HINT", "/nonexistent/addon.json")
    aioclient_mock.get(f"{API}/status", status=401, json={"ok": False})
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_URL: URL, CONF_API_KEY: "bad"})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_entities(hass, aioclient_mock):
    await setup_entry(hass, aioclient_mock)
    assert hass.states.get("todo.shopping_list").state == "1"  # one item still to buy
    assert hass.states.get("todo.chores").state == "1"
    spending = hass.states.get("sensor.homehub_spending_this_month")
    assert spending.state == "72.5"
    assert spending.attributes["unit_of_measurement"] == "USD"
    assert spending.attributes["by_person"] == {"Logan": 42.5, "Sam": 30.0}
    calendar = hass.states.get("calendar.homehub")
    assert calendar.attributes["message"] == "Vet"


async def test_adding_to_the_shopping_list(hass, aioclient_mock):
    await setup_entry(hass, aioclient_mock)
    await hass.services.async_call("todo", "add_item", {"item": "Bread"}, target={"entity_id": "todo.shopping_list"},
                                   blocking=True)
    assert sent(aioclient_mock, "POST", "/shopping") == [{"item": "Bread", "user": None}]


async def test_completing_a_chore(hass, aioclient_mock):
    await setup_entry(hass, aioclient_mock)
    await hass.services.async_call("todo", "update_item", {"item": "Trash", "status": "completed"},
                                   target={"entity_id": "todo.chores"}, blocking=True)
    body = sent(aioclient_mock, "PATCH", "/chores/7")[0]
    assert body["done"] is True and body["description"] == "Trash"


async def test_calendar_events_and_creating_one(hass, aioclient_mock):
    await setup_entry(hass, aioclient_mock)
    start = TODAY.isoformat()
    end = (TODAY + timedelta(days=10)).isoformat()
    result = await hass.services.async_call(
        "calendar", "get_events", {"start_date_time": f"{start} 00:00:00", "end_date_time": f"{end} 00:00:00"},
        target={"entity_id": "calendar.homehub"}, blocking=True, return_response=True)
    events = result["calendar.homehub"]["events"]
    assert [e["summary"] for e in events] == ["Vet", "Trip"]
    trip = events[1]
    trip_day = TODAY + timedelta(days=5)
    assert (trip["start"], trip["end"]) == (trip_day.isoformat(), (trip_day + timedelta(days=1)).isoformat())
    await hass.services.async_call(
        "calendar", "create_event",
        {"summary": "Dentist", "start_date_time": f"{start} 09:00:00", "end_date_time": f"{start} 10:00:00"},
        target={"entity_id": "calendar.homehub"}, blocking=True)
    body = sent(aioclient_mock, "POST", "/calendar")[0]
    assert (body["title"], body["start_date"], body["start_time"], body["end_time"]) == ("Dentist", start, "09:00", "10:00")


async def test_add_expense_action(hass, aioclient_mock):
    await setup_entry(hass, aioclient_mock)
    response = await hass.services.async_call(DOMAIN, "add_expense", {"title": "Pizza", "amount": 18.5, "person": "Logan"},
                                              blocking=True, return_response=True)
    assert response == {"expense": {"id": 9}}
    assert sent(aioclient_mock, "POST", "/expenses") == [
        {"title": "Pizza", "amount": 18.5, "user": "Logan", "category": None}]


async def test_add_expense_by_voice(hass, aioclient_mock):
    await setup_entry(hass, aioclient_mock)
    response = await intent.async_handle(
        hass, "test", "HomeHubAddExpense", {"amount": {"value": 20}, "title": {"value": "groceries"}})
    assert response.speech["plain"]["speech"] == "Added $20 for groceries."
    assert sent(aioclient_mock, "POST", "/expenses")[0]["amount"] == 20.0


async def test_unload(hass, aioclient_mock):
    entry = await setup_entry(hass, aioclient_mock)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is config_entries.ConfigEntryState.NOT_LOADED
