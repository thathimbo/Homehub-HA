"""Set up HomeHub. The add-on leaves its address and API key in addon.json, so the form is filled in."""
from __future__ import annotations

import json
import os
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_API_KEY, CONF_URL
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import HomeHubAuthError, HomeHubClient, HomeHubError
from .const import DOMAIN

ADDON_HINT = os.path.join(os.path.dirname(__file__), "addon.json")


def _addon_hint() -> dict[str, str]:
    try:
        with open(ADDON_HINT, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


class HomeHubConfigFlow(ConfigFlow, domain=DOMAIN):
    """One HomeHub per Home Assistant."""

    VERSION = 1

    async def _check(self, user_input: dict[str, Any]) -> tuple[dict[str, str], dict[str, Any]]:
        client = HomeHubClient(async_get_clientsession(self.hass), user_input[CONF_URL], user_input[CONF_API_KEY])
        try:
            return {}, await client.status()
        except HomeHubAuthError:
            return {"base": "invalid_auth"}, {}
        except HomeHubError:
            return {"base": "cannot_connect"}, {}

    def _schema(self, defaults: dict[str, Any]) -> vol.Schema:
        return vol.Schema(
            {
                vol.Required(CONF_URL, default=defaults.get(CONF_URL, "")): str,
                vol.Required(CONF_API_KEY, default=defaults.get(CONF_API_KEY, "")): str,
            }
        )

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        errors: dict[str, str] = {}
        if user_input is not None:
            errors, status = await self._check(user_input)
            if not errors:
                return self.async_create_entry(title=status.get("name") or "HomeHub", data=user_input)
        defaults = user_input or await self.hass.async_add_executor_job(_addon_hint)
        return self.async_show_form(step_id="user", data_schema=self._schema(defaults), errors=errors)

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            errors, _status = await self._check(user_input)
            if not errors:
                return self.async_update_reload_and_abort(entry, data=user_input)
        hint = await self.hass.async_add_executor_job(_addon_hint)
        defaults = user_input or {**entry.data, **hint}
        return self.async_show_form(step_id="reauth_confirm", data_schema=self._schema(defaults), errors=errors)
