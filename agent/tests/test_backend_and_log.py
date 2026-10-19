import json

import httpx
import pytest

from awaz_agent.backend import BackendError, HttpBackend, StandaloneBackend
from awaz_agent.call_log import CostRates, UsageTracker, transcript_from_messages
from tests.conftest import AGENT_DIR

MENU = [
    {
        "id": 1,
        "slug": "mantu",
        "nameFa": "منتو",
        "nameEn": "Mantu",
        "category": "main",
        "priceAfn": 200,
        "aliases": ["مانتو"],
        "available": True,
        "sortOrder": 0,
    },
]


def make_http_backend(handler):
    return HttpBackend("http://backend.test/", "agent-key-0123456789", transport=httpx.MockTransport(handler))


async def test_http_backend_sends_the_agent_key_and_caches_the_menu():
    seen = []

    def handler(request: httpx.Request):
        seen.append(request)
        return httpx.Response(200, json=MENU)

    backend = make_http_backend(handler)
    menu = await backend.get_menu()
    await backend.get_menu()
    assert menu.by_slug("mantu").price_afn == 200
    assert len(seen) == 1
    assert seen[0].headers["x-agent-key"] == "agent-key-0123456789"
    assert seen[0].url == "http://backend.test/menu"


async def test_http_backend_turns_refusals_into_backend_errors():
    def handler(request: httpx.Request):
        return httpx.Response(400, json={"message": '"pizza" is not on the menu.', "code": "unknown_item"})

    backend = make_http_backend(handler)
    with pytest.raises(BackendError) as error:
        await backend.quote([{"slug": "pizza", "quantity": 1}])
    assert error.value.code == "unknown_item"


async def test_http_backend_quote_and_order_parsing():
    def handler(request: httpx.Request):
        if request.url.path == "/orders/quote":
            assert json.loads(request.content) == {"items": [{"slug": "mantu", "quantity": 2}]}
            return httpx.Response(
                200,
                json={
                    "lines": [{"nameFa": "منتو", "quantity": 2, "note": None, "lineTotalAfn": 400}],
                    "subtotalAfn": 400,
                    "deliveryFeeAfn": 50,
                    "totalAfn": 450,
                },
            )
        return httpx.Response(
            201, json={"id": 3, "code": "1003", "totalAfn": 450, "etaMinutes": 40, "created": True}
        )

    backend = make_http_backend(handler)
    quote = await backend.quote([{"slug": "mantu", "quantity": 2}])
    assert quote.readback() == "2 منتو، 400 افغانی؛ هزینه انتقال 50 افغانی؛ مجموع 450 افغانی"
    order = await backend.create_order({"status": "new"})
    assert (order.code, order.eta_minutes) == ("1003", 40)


async def test_call_logs_never_break_a_call():
    def handler(request: httpx.Request):
        raise httpx.ConnectError("refused")

    await make_http_backend(handler).record_call({"sessionId": "s"})  # must not raise


async def test_standalone_backend_prices_like_the_server(tmp_path):
    backend = StandaloneBackend(AGENT_DIR / "sample_menu.json", tmp_path, delivery_fee_afn=50)
    quote = await backend.quote([{"slug": "qabuli-palaw", "quantity": 2}, {"slug": "doogh", "quantity": 1}])
    assert (quote.subtotal_afn, quote.total_afn) == (550, 600)
    with pytest.raises(BackendError):
        await backend.quote([{"slug": "pizza", "quantity": 1}])
    first = await backend.create_order({"status": "new", "items": [{"slug": "naan", "quantity": 2}]})
    second = await backend.create_order({"status": "callback", "items": []})
    assert (first.code, first.total_afn, second.code, second.total_afn) == ("1001", 90, "1002", 0)
    assert len((tmp_path / "orders.jsonl").read_text("utf-8").splitlines()) == 2


def test_cost_estimate_adds_listening_thinking_and_speaking():
    tracker = UsageTracker(CostRates())
    tracker.add_llm(30_000, 600)
    tracker.add_tts(1400)  # about 100 seconds of speech
    # LLM 0.0225 + 0.00225, STT 3 min x 0.009, TTS 100 s x 25 tok x $6/M
    assert tracker.estimate_usd(180) == pytest.approx(0.02475 + 0.027 + 0.015, abs=1e-5)


def test_transcript_keeps_only_spoken_turns():
    messages = [
        {"role": "system", "content": "You are..."},
        {"role": "developer", "content": "Greet the caller"},
        {"role": "assistant", "content": "سلام، چه میل دارید؟"},
        {"role": "user", "content": [{"type": "text", "text": "دو منتو"}]},
        {"role": "assistant", "tool_calls": [{"id": "1"}]},
        {"role": "tool", "content": '{"status": "added"}'},
    ]
    assert transcript_from_messages(messages) == [
        {"role": "assistant", "text": "سلام، چه میل دارید؟"},
        {"role": "user", "text": "دو منتو"},
    ]
