"""HomeHub's calendar and reminders as a Home Assistant calendar."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

from homeassistant.components.calendar import CalendarEntity, CalendarEntityFeature, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import person_for_context
from .api import HomeHubError
from .coordinator import HomeHubConfigEntry, HomeHubCoordinator
from .entity import HomeHubEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: HomeHubConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    if coordinator.feature("calendar"):
        async_add_entities([HomeHubCalendar(coordinator)])


def _clock(value: str | None) -> time | None:
    try:
        return time.fromisoformat(value) if value else None
    except ValueError:
        return None


def to_event(reminder: dict[str, Any]) -> CalendarEvent | None:
    """A HomeHub reminder as a calendar event: all-day, or timed in Home Assistant's time zone."""
    try:
        start_day = date.fromisoformat(reminder.get("start_date") or reminder["date"])
        end_day = date.fromisoformat(reminder["end_date"]) if reminder.get("end_date") else start_day
    except (KeyError, TypeError, ValueError):
        return None
    end_day = max(end_day, start_day)
    start_clock = _clock(reminder.get("start_time") or reminder.get("time"))
    common = {
        "summary": reminder.get("title") or "",
        "description": reminder.get("description") or None,
        "uid": f"{reminder.get('id')}-{start_day.isoformat()}",
    }
    if reminder.get("all_day") or start_clock is None:
        # Calendar end dates are exclusive
        return CalendarEvent(start=start_day, end=end_day + timedelta(days=1), **common)
    tz = dt_util.get_default_time_zone()
    start = datetime.combine(start_day, start_clock, tz)
    end_clock = _clock(reminder.get("end_time"))
    end = datetime.combine(end_day, end_clock, tz) if end_clock else start + timedelta(hours=1)
    if end <= start:
        end = start + timedelta(hours=1)
    return CalendarEvent(start=start, end=end, **common)


def _events(reminders: list[dict[str, Any]]) -> list[CalendarEvent]:
    return [event for event in (to_event(r) for r in reminders) if event is not None]


class HomeHubCalendar(HomeHubEntity, CalendarEntity):
    """HomeHub's shared family calendar."""

    _attr_name = "HomeHub"
    _attr_supported_features = CalendarEntityFeature.CREATE_EVENT

    def __init__(self, coordinator: HomeHubCoordinator) -> None:
        super().__init__(coordinator, "calendar")

    @property
    def event(self) -> CalendarEvent | None:
        now = dt_util.now()
        upcoming = [e for e in _events(self.coordinator.data.events) if e.end_datetime_local > now]
        return min(upcoming, key=lambda e: e.start_datetime_local, default=None)

    async def async_get_events(self, hass: HomeAssistant, start_date: datetime, end_date: datetime) -> list[CalendarEvent]:
        try:
            reminders = await self.coordinator.client.events(
                dt_util.as_local(start_date).date(), dt_util.as_local(end_date).date()
            )
        except HomeHubError as err:
            raise HomeAssistantError(str(err)) from err
        return [
            e for e in _events(reminders)
            if e.end_datetime_local > start_date and e.start_datetime_local < end_date
        ]

    async def async_create_event(self, **kwargs: Any) -> None:
        start, end = kwargs["dtstart"], kwargs["dtend"]
        payload: dict[str, Any] = {
            "title": kwargs.get("summary") or "",
            "description": kwargs.get("description") or "",
            "user": person_for_context(self.hass, self._context),
        }
        if isinstance(start, datetime):
            start, end = dt_util.as_local(start), dt_util.as_local(end)
            payload.update(start_date=start.date().isoformat(), start_time=start.strftime("%H:%M"),
                           end_date=end.date().isoformat(), end_time=end.strftime("%H:%M"))
        else:
            last_day = end - timedelta(days=1) if end > start else start
            payload["start_date"] = start.isoformat()
            if last_day > start:
                payload["end_date"] = last_day.isoformat()
        try:
            await self.coordinator.client.add_event(payload)
        except HomeHubError as err:
            raise HomeAssistantError(str(err)) from err
        await self.coordinator.async_refresh()
