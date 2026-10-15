import json
from pathlib import Path

import pytest

from awaz_agent.backend import BackendError, OrderResult, Quote, StandaloneBackend
from awaz_agent.menu import Menu, MenuItem

AGENT_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture
def menu() -> Menu:
    data = json.loads((AGENT_DIR / "sample_menu.json").read_text("utf-8"))
    return Menu([MenuItem.from_api(item) for item in data])


class FakeBackend(StandaloneBackend):
    """The standalone backend, plus a record of everything the agent sent."""

    def __init__(self, tmp_path: Path):
        super().__init__(AGENT_DIR / "sample_menu.json", tmp_path)
        self.orders: list[dict] = []
        self.quotes: list[list[dict]] = []
        self.calls: list[dict] = []
        self.fail_orders = False

    async def quote(self, items: list[dict]) -> Quote:
        self.quotes.append(items)
        return await super().quote(items)

    async def create_order(self, order: dict) -> OrderResult:
        if self.fail_orders:
            raise BackendError("database down", "unreachable")
        self.orders.append(order)
        return await super().create_order(order)

    async def record_call(self, call: dict) -> None:
        self.calls.append(call)


@pytest.fixture
def fake_backend(tmp_path: Path) -> FakeBackend:
    return FakeBackend(tmp_path)
