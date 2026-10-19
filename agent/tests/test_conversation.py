"""Whole calls through the real flow.yaml, FlowManager and handlers.

No network and no API key: instead of Gemini deciding which tool to call,
each test calls the tools the way the LLM would, in the order a caller's
conversation would trigger them, and checks where the flow goes and what
reaches the backend.
"""

from unittest.mock import AsyncMock, MagicMock, Mock, PropertyMock

import pytest
from pipecat.flows import Flow, FlowConfig, FlowManager
from pipecat.frames.frames import EndFrame, LLMSetToolsFrame
from pipecat.services.google.llm import GoogleLLMService
from pipecat.services.llm_service import FunctionCallParams

import handlers
from tests.conftest import AGENT_DIR


def make_mock_worker():
    """A stand-in PipelineWorker whose queued frames 'reach' the end at once."""
    worker = AsyncMock()

    async def queue_frame(frame):
        handler = getattr(worker, "on_frame_reached_downstream", None)
        if handler:
            await handler(worker, frame)

    worker.queue_frame = AsyncMock(side_effect=queue_frame)
    worker.set_reached_downstream_filter = Mock()

    def event_handler(name):
        def decorator(func):
            setattr(worker, name, func)
            return func

        return decorator

    worker.event_handler = event_handler
    return worker


class Call:
    """One simulated phone call."""

    def __init__(self, backend, *, channel="web", caller_phone=None):
        handlers.configure(backend)
        self.backend = backend
        self.worker = make_mock_worker()
        assistant = MagicMock()
        type(assistant).has_function_calls_in_progress = PropertyMock(return_value=False)
        aggregator = MagicMock()
        aggregator.user = MagicMock(return_value=MagicMock())
        aggregator.assistant = MagicMock(return_value=assistant)
        self.llm = GoogleLLMService(api_key="test-key")
        self.flow = Flow(FlowConfig.from_file(AGENT_DIR / "flow.yaml"), handlers=handlers)
        self.fm = FlowManager(
            worker=self.worker,
            llm=self.llm,
            context_aggregator=aggregator,
            global_functions=self.flow.global_functions,
        )
        self.channel = channel
        self.caller_phone = caller_phone

    async def start(self):
        menu = await self.backend.get_menu()
        self.fm.state.update(
            handlers.initial_state(
                restaurant_name="رستوران نمونه هرات",
                menu_text=menu.prompt_text(),
                session_id="session-1",
                channel=self.channel,
                caller_phone=self.caller_phone,
            )
        )
        await self.fm.initialize(self.flow.initial_node)
        return self

    @property
    def node(self):
        return self.fm.current_node

    def tools(self) -> set[str]:
        frames = [
            frame
            for call in self.worker.queue_frames.call_args_list
            for frame in call[0][0]
            if isinstance(frame, LLMSetToolsFrame)
        ]
        return {schema.name for schema in frames[-1].tools.standard_tools}

    def prompts(self) -> str:
        texts = []
        for call in self.worker.queue_frames.call_args_list:
            for frame in call[0][0]:
                for message in getattr(frame, "messages", None) or []:
                    texts.append(str(message.get("content", "")))
                # The role message is sent as the LLM's system instruction.
                delta = getattr(frame, "delta", None)
                instruction = getattr(delta, "system_instruction", None)
                if isinstance(instruction, str):
                    texts.append(instruction)
        return "\n".join(texts)

    async def say(self, tool: str, **arguments):
        """The LLM calls `tool`; returns what the tool reported back."""
        frames = [
            frame
            for call in self.worker.queue_frames.call_args_list
            for frame in call[0][0]
            if isinstance(frame, LLMSetToolsFrame)
        ]
        handler = {s.name: s.handler for s in frames[-1].tools.standard_tools}[tool]
        results = []

        async def result_callback(result, *, properties=None):
            results.append(result)
            if properties is not None and properties.on_context_updated is not None:
                await properties.on_context_updated()

        await handler(
            FunctionCallParams(
                function_name=tool,
                tool_call_id="t1",
                arguments=arguments,
                llm=self.llm,
                pipeline_worker=self.worker,
                context=None,
                result_callback=result_callback,
            )
        )
        return results[0]

    def ended(self) -> bool:
        return any(isinstance(call[0][0], EndFrame) for call in self.worker.queue_frame.call_args_list)


async def test_a_full_order_from_greeting_to_goodbye(fake_backend):
    call = await Call(fake_backend).start()
    assert call.node == "take_order"
    assert call.tools() == {"add_item", "update_item", "finish_items", "request_callback"}
    assert "قابلی پلو" in call.prompts() and "رستوران نمونه هرات" in call.prompts()

    # "دو قابلی پلو، یکی بدون کشمش، و یک دوغ"
    assert (await call.say("add_item", item="qabuli-palaw", quantity=1))["status"] == "added"
    await call.say("add_item", item="قابلی پلو", quantity=1, note="بدون کشمش")
    added = await call.say("add_item", item="دوغ")
    assert added["order_so_far"] == "1 × قابلی پلو، 1 × قابلی پلو (بدون کشمش)، 1 × دوغ"
    # "نه، دوغ دو تا باشد"
    assert (await call.say("update_item", item="doogh", quantity=2))["status"] == "updated"

    assert (await call.say("finish_items"))["status"] == "ok"
    assert call.node == "get_details"
    assert "phone number the restaurant can call back on" in call.prompts()

    details = await call.say(
        "set_customer_details",
        name="احمد",
        address="جاده محبس، کوچه دوم",
        landmark="نزدیک مسجد جامع",
        phone="۰۷۹۹ ۱۲۳ ۴۵۶",
    )
    assert details == {"status": "ok", "total_afn": 650}
    assert call.node == "confirm"
    assert "مجموع 650 افغانی" in call.prompts()

    confirmed = await call.say("confirm_order")
    assert confirmed["status"] == "ok"
    assert call.node == "done"
    assert "1001" in call.prompts()
    assert call.ended()

    [order] = fake_backend.orders
    assert order == {
        "sessionId": "session-1",
        "channel": "web",
        "status": "new",
        "items": [
            {"slug": "qabuli-palaw", "quantity": 1},
            {"slug": "qabuli-palaw", "quantity": 1, "note": "بدون کشمش"},
            {"slug": "doogh", "quantity": 2},
        ],
        "customerName": "احمد",
        "customerPhone": "0799123456",
        "address": "جاده محبس، کوچه دوم",
        "landmark": "نزدیک مسجد جامع",
    }
    assert "price" not in str(order).lower()
    assert call.fm.state["outcome"] == "ordered"


async def test_whatsapp_callers_are_not_asked_for_their_number(fake_backend):
    call = await Call(fake_backend, channel="whatsapp", caller_phone="+93700111222").start()
    await call.say("add_item", item="mantu", quantity=2)
    await call.say("finish_items")
    assert "already known" in call.prompts()
    result = await call.say("set_customer_details", name="زهرا", address="شهر نو")
    assert result["status"] == "ok"
    await call.say("confirm_order")
    assert fake_backend.orders[0]["customerPhone"] == "+93700111222"
    assert fake_backend.orders[0]["channel"] == "whatsapp"


async def test_finishing_with_nothing_ordered_stays_on_the_order_step(fake_backend):
    call = await Call(fake_backend).start()
    assert (await call.say("finish_items"))["status"] == "empty"
    assert call.node == "take_order"


async def test_unknown_and_ambiguous_items_are_not_added_and_lead_to_a_hint(fake_backend):
    call = await Call(fake_backend).start()
    first = await call.say("add_item", item="پیتزا")
    assert first["status"] == "unknown_item" and "hint" not in first
    second = await call.say("add_item", item="کباب")
    assert second["status"] == "ambiguous"
    assert set(second["options"]) == {"کباب تکه", "کباب کوبیده"}
    assert "request_callback" in second["hint"]
    assert call.fm.state["cart"] == []
    # A success resets the miss counter.
    await call.say("add_item", item="kabab-kobide")
    assert call.fm.state["misunderstood"] == 0


async def test_missing_details_keep_asking(fake_backend):
    call = await Call(fake_backend).start()
    await call.say("add_item", item="bolani")
    await call.say("finish_items")
    assert (await call.say("set_customer_details", name="", address="کارته"))["missing"] == ["name"]
    assert (await call.say("set_customer_details", name="علی", address="کارته"))["missing"] == ["phone"]
    assert (await call.say("set_customer_details", name="علی", address="کارته", phone="123"))[
        "status"
    ] == "bad_phone"
    assert call.node == "get_details"


async def test_caller_can_change_the_food_after_hearing_the_total(fake_backend):
    call = await Call(fake_backend).start()
    await call.say("add_item", item="mantu")
    await call.say("finish_items")
    await call.say("set_customer_details", name="علی", address="کارته", phone="0799123456")
    assert call.node == "confirm"

    await call.say("change_items")
    assert call.node == "edit_items"
    assert "1 × منتو" in call.prompts()
    await call.say("add_item", item="firni", quantity=2)
    await call.say("finish_items")
    await call.say("set_customer_details", name="علی", address="کارته")
    assert "مجموع 410 افغانی" in call.prompts()  # 200 + 2 x 80 + 50 delivery
    await call.say("confirm_order")
    assert fake_backend.orders[0]["items"] == [
        {"slug": "mantu", "quantity": 1},
        {"slug": "firni", "quantity": 2},
    ]


async def test_callback_hands_the_caller_to_staff(fake_backend):
    call = await Call(fake_backend).start()
    await call.say("add_item", item="ashak")
    # Web callers must give a number before staff can call them.
    assert (await call.say("request_callback", reason="caller asked for a person"))["status"] == "need_phone"
    assert call.node == "take_order"
    result = await call.say("request_callback", reason="caller asked for a person", phone="0700 111 222")
    assert result["status"] == "ok"
    assert call.node == "callback_done"
    assert call.ended()
    [order] = fake_backend.orders
    assert order["status"] == "callback"
    assert order["callbackReason"] == "caller asked for a person"
    assert order["customerPhone"] == "0700111222"
    assert order["items"] == [{"slug": "ashak", "quantity": 1}]
    assert call.fm.state["outcome"] == "callback"


async def test_callback_with_a_garbled_number_asks_again(fake_backend):
    call = await Call(fake_backend).start()
    await call.say("add_item", item="shorwa")
    await call.say("finish_items")
    await call.say("set_customer_details", name="علی", address="کارته", phone="0799123456")
    # A number the caller just gave must not be swapped for the one heard earlier.
    result = await call.say("request_callback", reason="caller asked for a person", phone="07")
    assert result["status"] == "bad_phone"
    assert call.node == "confirm"
    assert fake_backend.orders == []
    # A blank number still falls back to the one already known.
    assert (await call.say("request_callback", reason="caller asked for a person"))["status"] == "ok"
    assert fake_backend.orders[0]["customerPhone"] == "0799123456"


async def test_a_failed_save_does_not_claim_success(fake_backend):
    call = await Call(fake_backend).start()
    await call.say("add_item", item="shorwa")
    await call.say("finish_items")
    await call.say("set_customer_details", name="علی", address="کارته", phone="0799123456")
    fake_backend.fail_orders = True
    result = await call.say("confirm_order")
    assert result["status"] == "error"
    assert "request_callback" in result["say"]
    assert call.node == "confirm"
    assert call.fm.state["outcome"] == "abandoned"


@pytest.mark.parametrize(
    "node", ["take_order", "edit_items", "get_details", "confirm", "done", "callback_done"]
)
def test_every_node_exists(node):
    flow = Flow(FlowConfig.from_file(AGENT_DIR / "flow.yaml"), handlers=handlers)
    assert flow.node(node) is not None


def test_eval_scenarios_are_valid():
    from pipecat.evals.scenario import EvalScenarioFile

    scenarios = EvalScenarioFile.load(AGENT_DIR / "evals" / "order_in_dari.yaml").scenarios
    assert {s.name.split("/")[-1] for s in scenarios} == {
        "simple_order",
        "mixed_dari_english",
        "asks_for_a_person",
    }
