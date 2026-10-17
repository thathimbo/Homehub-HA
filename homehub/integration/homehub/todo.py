"""HomeHub's shopping list and chores as Home Assistant to-do lists (Assist can add to these)."""
from __future__ import annotations

from datetime import date

from homeassistant.components.todo import TodoItem, TodoItemStatus, TodoListEntity, TodoListEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import person_for_context
from .api import HomeHubError
from .coordinator import HomeHubConfigEntry, HomeHubCoordinator
from .entity import HomeHubEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: HomeHubConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    entities: list[TodoListEntity] = []
    if coordinator.feature("shopping_list"):
        entities.append(ShoppingListEntity(coordinator))
    if coordinator.feature("chores"):
        entities.append(ChoresEntity(coordinator))
    async_add_entities(entities)


def _status(done: bool) -> TodoItemStatus:
    return TodoItemStatus.COMPLETED if done else TodoItemStatus.NEEDS_ACTION


class _HomeHubTodo(HomeHubEntity, TodoListEntity):
    async def _call(self, coro) -> None:
        try:
            await coro
        except HomeHubError as err:
            raise HomeAssistantError(str(err)) from err
        await self.coordinator.async_refresh()

    def _user(self) -> str | None:
        return person_for_context(self.hass, self._context)


class ShoppingListEntity(_HomeHubTodo):
    """HomeHub's shopping list."""

    _attr_name = "Shopping List"
    _attr_icon = "mdi:cart"
    _attr_supported_features = (
        TodoListEntityFeature.CREATE_TODO_ITEM
        | TodoListEntityFeature.UPDATE_TODO_ITEM
        | TodoListEntityFeature.DELETE_TODO_ITEM
    )

    def __init__(self, coordinator: HomeHubCoordinator) -> None:
        super().__init__(coordinator, "shopping_list")

    @property
    def todo_items(self) -> list[TodoItem]:
        return [
            TodoItem(uid=str(i["id"]), summary=i["item"], status=_status(i["checked"]))
            for i in self.coordinator.data.shopping
        ]

    async def async_create_todo_item(self, item: TodoItem) -> None:
        await self._call(self.coordinator.client.add_shopping(item.summary or "", self._user()))

    async def async_update_todo_item(self, item: TodoItem) -> None:
        changes = {"checked": item.status == TodoItemStatus.COMPLETED}
        if item.summary:
            changes["item"] = item.summary
        await self._call(self.coordinator.client.update_shopping(item.uid, **changes))

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        for uid in uids:
            await self._call(self.coordinator.client.delete_shopping(uid))


class ChoresEntity(_HomeHubTodo):
    """HomeHub's chores. Completing a recurring chore moves it to its next date."""

    _attr_name = "Chores"
    _attr_icon = "mdi:broom"
    _attr_supported_features = (
        TodoListEntityFeature.CREATE_TODO_ITEM
        | TodoListEntityFeature.UPDATE_TODO_ITEM
        | TodoListEntityFeature.DELETE_TODO_ITEM
        | TodoListEntityFeature.SET_DUE_DATE_ON_ITEM
    )

    def __init__(self, coordinator: HomeHubCoordinator) -> None:
        super().__init__(coordinator, "chores")

    @property
    def todo_items(self) -> list[TodoItem]:
        return [
            TodoItem(
                uid=str(c["id"]),
                summary=c["description"],
                status=_status(c["done"]),
                due=date.fromisoformat(c["due_date"]) if c.get("due_date") else None,
            )
            for c in self.coordinator.data.chores
        ]

    async def async_create_todo_item(self, item: TodoItem) -> None:
        due = item.due if isinstance(item.due, date) else None
        await self._call(self.coordinator.client.add_chore(item.summary or "", due, self._user()))

    async def async_update_todo_item(self, item: TodoItem) -> None:
        changes: dict = {"done": item.status == TodoItemStatus.COMPLETED}
        if item.summary:
            changes["description"] = item.summary
        if isinstance(item.due, date):
            changes["due_date"] = item.due.isoformat()
        await self._call(self.coordinator.client.update_chore(item.uid, **changes))

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        for uid in uids:
            await self._call(self.coordinator.client.delete_chore(uid))
