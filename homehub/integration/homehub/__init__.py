"""HomeHub: the family dashboard add-on's lists, calendar and spending in Home Assistant.

Shopping list and chores become to-do lists, so Assist's built-in sentences work
("add milk to my shopping list"). The calendar becomes a calendar entity, spending a
sensor, and "add an expense" a service and an Assist sentence.
"""
from __future__ import annotations

import voluptuous as vol

from homeassistant.const import CONF_API_KEY, CONF_URL, Platform
from homeassistant.core import Context, HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv, intent
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import HomeHubClient, HomeHubError
from .const import DOMAIN, INTENT_ADD_EXPENSE, SERVICE_ADD_EXPENSE
from .coordinator import HomeHubConfigEntry, HomeHubCoordinator

PLATFORMS = [Platform.CALENDAR, Platform.SENSOR, Platform.TODO]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

ADD_EXPENSE_SCHEMA = vol.Schema(
    {
        vol.Required("title"): cv.string,
        vol.Required("amount"): vol.All(vol.Coerce(float), vol.Range(min=0, min_included=False)),
        vol.Optional("person"): cv.string,
        vol.Optional("category"): cv.string,
    }
)


def person_for_context(hass: HomeAssistant, context: Context | None) -> str | None:
    """The household member (person entity name) behind a service call or voice command."""
    user_id = context.user_id if context else None
    if not user_id:
        return None
    for state in hass.states.async_all("person"):
        if state.attributes.get("user_id") == user_id:
            return state.name
    return None


def _coordinator(hass: HomeAssistant) -> HomeHubCoordinator:
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entries:
        raise ServiceValidationError("HomeHub is not set up")
    return entries[0].runtime_data


async def _add_expense(hass: HomeAssistant, title: str, amount: float, person: str | None,
                       category: str | None) -> dict:
    coordinator = _coordinator(hass)
    try:
        expense = await coordinator.client.add_expense(title, amount, person, category)
    except HomeHubError as err:
        raise HomeAssistantError(str(err)) from err
    await coordinator.async_refresh()
    return expense


class AddExpenseIntent(intent.IntentHandler):
    """Assist: "add an expense of 20 dollars for groceries"."""

    intent_type = INTENT_ADD_EXPENSE
    description = "Adds an expense to HomeHub's expense tracker"
    slot_schema = {vol.Required("amount"): cv.positive_float, vol.Required("title"): cv.string}

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        hass = intent_obj.hass
        slots = self.async_validate_slots(intent_obj.slots)
        amount = float(slots["amount"]["value"])
        title = str(slots["title"]["value"]).strip()
        await _add_expense(hass, title, amount, person_for_context(hass, intent_obj.context), None)
        currency = (_coordinator(hass).data.expenses or {}).get("currency") or "$"
        response = intent_obj.create_response()
        response.async_set_speech(f"Added {currency}{amount:g} for {title}.")
        return response


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async def handle_add_expense(call: ServiceCall) -> dict:
        person = call.data.get("person") or person_for_context(hass, call.context)
        expense = await _add_expense(hass, call.data["title"], call.data["amount"], person, call.data.get("category"))
        return {"expense": expense}

    hass.services.async_register(
        DOMAIN, SERVICE_ADD_EXPENSE, handle_add_expense, schema=ADD_EXPENSE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    intent.async_register(hass, AddExpenseIntent())
    return True


async def async_setup_entry(hass: HomeAssistant, entry: HomeHubConfigEntry) -> bool:
    client = HomeHubClient(async_get_clientsession(hass), entry.data[CONF_URL], entry.data[CONF_API_KEY])
    coordinator = HomeHubCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: HomeHubConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
