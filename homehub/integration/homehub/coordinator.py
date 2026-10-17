"""Keeps HomeHub's lists, calendar and spending fresh for the entities."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import HomeHubAuthError, HomeHubClient, HomeHubError
from .const import CALENDAR_LOOKAHEAD_DAYS, DOMAIN, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


@dataclass
class HomeHubData:
    status: dict[str, Any] = field(default_factory=dict)
    shopping: list[dict[str, Any]] = field(default_factory=list)
    chores: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    expenses: dict[str, Any] = field(default_factory=dict)


type HomeHubConfigEntry = ConfigEntry[HomeHubCoordinator]


class HomeHubCoordinator(DataUpdateCoordinator[HomeHubData]):
    """Polls HomeHub every SCAN_INTERVAL."""

    config_entry: HomeHubConfigEntry

    def __init__(self, hass: HomeAssistant, entry: HomeHubConfigEntry, client: HomeHubClient) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=SCAN_INTERVAL)
        self.client = client

    def feature(self, name: str) -> bool:
        features = (self.data.status if self.data else {}).get("features") or {}
        return bool(features.get(name, True))

    async def _async_update_data(self) -> HomeHubData:
        today = dt_util.now().date()
        try:
            status, shopping, chores, events, expenses = await asyncio.gather(
                self.client.status(),
                self.client.shopping(),
                self.client.chores(),
                self.client.events(today, today + timedelta(days=CALENDAR_LOOKAHEAD_DAYS)),
                self.client.expense_summary(),
            )
        except HomeHubAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except HomeHubError as err:
            raise UpdateFailed(str(err)) from err
        return HomeHubData(status=status, shopping=shopping, chores=chores, events=events, expenses=expenses)
