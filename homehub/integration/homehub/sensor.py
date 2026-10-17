"""This month's household spending from HomeHub's expense tracker."""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import HomeHubConfigEntry, HomeHubCoordinator
from .entity import HomeHubEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: HomeHubConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    if coordinator.feature("expense_tracker"):
        async_add_entities([SpendingSensor(coordinator)])


class SpendingSensor(HomeHubEntity, SensorEntity):
    """Total spent this month, with the split per person and category as attributes."""

    _attr_name = "HomeHub spending this month"
    _attr_icon = "mdi:cash-multiple"
    _attr_device_class = SensorDeviceClass.MONETARY

    def __init__(self, coordinator: HomeHubCoordinator) -> None:
        super().__init__(coordinator, "spending_this_month")

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.expenses.get("total")

    @property
    def native_unit_of_measurement(self) -> str:
        return self.coordinator.data.expenses.get("currency_code") or "USD"

    @property
    def extra_state_attributes(self) -> dict:
        expenses = self.coordinator.data.expenses
        return {
            "by_person": expenses.get("by_person") or {},
            "by_category": expenses.get("by_category") or {},
            "entries": expenses.get("count", 0),
        }
