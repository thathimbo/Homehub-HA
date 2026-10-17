"""Base entity for HomeHub."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import HomeHubCoordinator


class HomeHubEntity(CoordinatorEntity[HomeHubCoordinator]):
    """An entity on the HomeHub device."""

    def __init__(self, coordinator: HomeHubCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="HomeHub",
            entry_type=DeviceEntryType.SERVICE,
        )
