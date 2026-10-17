"""Client for HomeHub's /api/v1 endpoints."""
from __future__ import annotations

from datetime import date
from typing import Any

import aiohttp


class HomeHubError(Exception):
    """HomeHub could not be reached or answered with an error."""


class HomeHubAuthError(HomeHubError):
    """The API key was refused."""


class HomeHubClient:
    """Talks to one HomeHub add-on."""

    def __init__(self, session: aiohttp.ClientSession, url: str, api_key: str) -> None:
        self._session = session
        self._url = url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {api_key}"}

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            async with self._session.request(
                method,
                f"{self._url}/api/v1{path}",
                headers=self._headers,
                timeout=aiohttp.ClientTimeout(total=15),
                **kwargs,
            ) as resp:
                if resp.status == 401:
                    raise HomeHubAuthError("HomeHub refused the API key")
                data = await resp.json(content_type=None)
                if resp.status >= 400 or not isinstance(data, dict) or not data.get("ok", False):
                    message = data.get("error") if isinstance(data, dict) else None
                    raise HomeHubError(message or f"HomeHub answered {resp.status}")
                return data
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise HomeHubError(f"Could not reach HomeHub: {err}") from err

    async def status(self) -> dict[str, Any]:
        return await self._request("GET", "/status")

    async def shopping(self) -> list[dict[str, Any]]:
        return (await self._request("GET", "/shopping"))["items"]

    async def add_shopping(self, item: str, user: str | None = None) -> dict[str, Any]:
        return (await self._request("POST", "/shopping", json={"item": item, "user": user}))["item"]

    async def update_shopping(self, item_id: str, **changes: Any) -> None:
        await self._request("PATCH", f"/shopping/{item_id}", json=changes)

    async def delete_shopping(self, item_id: str) -> None:
        await self._request("DELETE", f"/shopping/{item_id}")

    async def chores(self) -> list[dict[str, Any]]:
        return (await self._request("GET", "/chores"))["chores"]

    async def add_chore(self, description: str, due_date: date | None = None, user: str | None = None) -> None:
        await self._request(
            "POST",
            "/chores",
            json={"description": description, "due_date": due_date.isoformat() if due_date else None, "user": user},
        )

    async def update_chore(self, chore_id: str, **changes: Any) -> None:
        await self._request("PATCH", f"/chores/{chore_id}", json=changes)

    async def delete_chore(self, chore_id: str) -> None:
        await self._request("DELETE", f"/chores/{chore_id}")

    async def events(self, start: date, end: date) -> list[dict[str, Any]]:
        data = await self._request("GET", "/calendar", params={"start": start.isoformat(), "end": end.isoformat()})
        return data["events"]

    async def add_event(self, payload: dict[str, Any]) -> None:
        await self._request("POST", "/calendar", json=payload)

    async def expense_summary(self) -> dict[str, Any]:
        return await self._request("GET", "/expenses/summary")

    async def add_expense(self, title: str, amount: float, user: str | None = None,
                          category: str | None = None) -> dict[str, Any]:
        payload = {"title": title, "amount": amount, "user": user, "category": category}
        return (await self._request("POST", "/expenses", json=payload))["expense"]
