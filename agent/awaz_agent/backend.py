"""How the agent reaches the orders backend.

`HttpBackend` talks to the Nest.js service. `StandaloneBackend` keeps
everything in local files, so the agent can be tried with nothing but a
Gemini key; it mirrors the backend's pricing rules.
"""

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import httpx
from loguru import logger

from .menu import Menu, MenuItem


class BackendError(Exception):
    """A refusal the agent can explain, e.g. an item that is sold out."""

    def __init__(self, message: str, code: str = "error"):
        super().__init__(message)
        self.code = code


@dataclass
class QuoteLine:
    name_fa: str
    quantity: int
    note: str | None
    line_total_afn: int


@dataclass
class Quote:
    lines: list[QuoteLine]
    subtotal_afn: int
    delivery_fee_afn: int
    total_afn: int

    def readback(self) -> str:
        """The exact Dari text the agent reads to the caller before they confirm."""
        parts = []
        for line in self.lines:
            note = f" ({line.note})" if line.note else ""
            parts.append(f"{line.quantity} {line.name_fa}{note}، {line.line_total_afn} افغانی")
        return (
            "؛ ".join(parts) + f"؛ هزینه انتقال {self.delivery_fee_afn} افغانی؛ مجموع {self.total_afn} افغانی"
        )

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "Quote":
        return cls(
            lines=[
                QuoteLine(
                    name_fa=line["nameFa"],
                    quantity=int(line["quantity"]),
                    note=line.get("note"),
                    line_total_afn=int(line["lineTotalAfn"]),
                )
                for line in data["lines"]
            ],
            subtotal_afn=int(data["subtotalAfn"]),
            delivery_fee_afn=int(data["deliveryFeeAfn"]),
            total_afn=int(data["totalAfn"]),
        )


@dataclass
class OrderResult:
    id: int
    code: str
    total_afn: int
    eta_minutes: int | None
    created: bool


class Backend(Protocol):
    async def get_menu(self) -> Menu: ...

    async def quote(self, items: list[dict]) -> Quote: ...

    async def create_order(self, order: dict) -> OrderResult: ...

    async def record_call(self, call: dict) -> None: ...


class HttpBackend:
    """Client for the Nest.js backend. The menu is cached for a minute."""

    def __init__(self, base_url: str, agent_key: str, *, transport: httpx.AsyncBaseTransport | None = None):
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"x-agent-key": agent_key},
            timeout=httpx.Timeout(10.0),
            transport=transport,
        )
        self._menu: Menu | None = None
        self._menu_loaded_at = 0.0

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs) -> Any:
        try:
            response = await self._client.request(method, path, **kwargs)
        except httpx.HTTPError as error:
            raise BackendError(f"backend unreachable: {error}", "unreachable") from error
        if response.status_code >= 400:
            try:
                body = response.json()
            except ValueError:
                body = {}
            message = body.get("message") if isinstance(body, dict) else None
            if isinstance(message, list):
                message = "; ".join(map(str, message))
            raise BackendError(
                str(message or f"backend returned {response.status_code}"),
                str(body.get("code", "error")) if isinstance(body, dict) else "error",
            )
        return response.json()

    async def get_menu(self) -> Menu:
        if self._menu and time.monotonic() - self._menu_loaded_at < 60:
            return self._menu
        data = await self._request("GET", "/menu")
        self._menu = Menu([MenuItem.from_api(item) for item in data])
        self._menu_loaded_at = time.monotonic()
        return self._menu

    async def quote(self, items: list[dict]) -> Quote:
        return Quote.from_api(await self._request("POST", "/orders/quote", json={"items": items}))

    async def create_order(self, order: dict) -> OrderResult:
        data = await self._request("POST", "/orders", json=order)
        return OrderResult(
            id=int(data["id"]),
            code=str(data["code"]),
            total_afn=int(data["totalAfn"]),
            eta_minutes=data.get("etaMinutes"),
            created=bool(data.get("created", True)),
        )

    async def record_call(self, call: dict) -> None:
        """Saves the call log. Never raises: a lost log must not break a call."""
        try:
            await self._request("POST", "/calls", json=call)
        except BackendError as error:
            logger.warning(f"Could not save call log: {error}")


class StandaloneBackend:
    """No server needed: menu from a JSON file, orders and calls appended to JSON-lines files."""

    def __init__(self, menu_file: Path, data_dir: Path, *, delivery_fee_afn: int = 50, eta_minutes: int = 40):
        self._menu = Menu([MenuItem.from_api(item) for item in json.loads(menu_file.read_text("utf-8"))])
        self._data_dir = data_dir
        self._delivery_fee = delivery_fee_afn
        self._eta = eta_minutes
        data_dir.mkdir(parents=True, exist_ok=True)

    async def get_menu(self) -> Menu:
        return self._menu

    async def quote(self, items: list[dict]) -> Quote:
        if not items:
            raise BackendError("The order has no items.", "empty_order")
        lines = []
        for requested in items:
            item = self._menu.by_slug(requested["slug"])
            if item is None:
                raise BackendError(f'"{requested["slug"]}" is not on the menu.', "unknown_item")
            if not item.available:
                raise BackendError(f"{item.name_fa} is not available today.", "unavailable_item")
            quantity = int(requested["quantity"])
            if quantity < 1 or quantity > 50:
                raise BackendError("Quantity must be between 1 and 50.", "bad_quantity")
            lines.append(QuoteLine(item.name_fa, quantity, requested.get("note"), item.price_afn * quantity))
        subtotal = sum(line.line_total_afn for line in lines)
        return Quote(lines, subtotal, self._delivery_fee, subtotal + self._delivery_fee)

    def _append(self, name: str, record: dict) -> int:
        path = self._data_dir / name
        count = sum(1 for _ in path.open("r", encoding="utf-8")) if path.exists() else 0
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return count + 1

    async def create_order(self, order: dict) -> OrderResult:
        if order["status"] == "callback" and not order["items"]:
            total = 0
        else:
            total = (await self.quote(order["items"])).total_afn
        number = self._append("orders.jsonl", {**order, "totalAfn": total, "at": time.time()})
        code = str(1000 + number)
        eta = self._eta if order["status"] == "new" else None
        logger.info(f"Standalone mode: saved {order['status']} order #{code} ({total} AFN)")
        return OrderResult(number, code, total, eta, True)

    async def record_call(self, call: dict) -> None:
        self._append("calls.jsonl", call)
