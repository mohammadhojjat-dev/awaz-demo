"""Awaz voice ordering agent.

A caller talks in Dari (mixed with English is fine); the agent takes the
order through the steps in flow.yaml, reads it back with prices from the
backend, saves it, and the restaurant gets it on Telegram.

Pipeline: caller audio -> Gemini speech-to-text -> Gemini LLM (ordering flow)
-> Gemini text-to-speech -> caller.

Run:
    uv run bot.py                 # web call page at http://localhost:7860/order
    uv run bot.py --whatsapp      # also answer WhatsApp Business calls
    uv run bot.py -t eval         # for scripted text tests (see evals/)
"""

import asyncio
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv
from fastapi.responses import FileResponse
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.evals.transport import EvalTransportParams
from pipecat.flows import Flow, FlowConfig, FlowManager
from pipecat.frames.frames import EndFrame, TTSSpeakFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker, ProcessorUnusablePolicy
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.runner.types import EvalRunnerArguments, RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.google.gemini_live.stt import GeminiSTTService
from pipecat.services.google.llm import GoogleLLMService
from pipecat.services.google.tts import GeminiTTSService
from pipecat.transcriptions.language import Language
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.workers.runner import WorkerRunner

import handlers
from awaz_agent.backend import Backend, BackendError, HttpBackend, StandaloneBackend
from awaz_agent.call_log import CostRates, UsageTracker, transcript_from_messages
from awaz_agent.usage_observer import UsageObserver

load_dotenv(override=True)

HERE = Path(__file__).parent
FLOW = Flow(FlowConfig.from_file(HERE / "flow.yaml"), handlers=handlers)


def make_backend() -> Backend:
    """The Nest.js backend when BACKEND_URL is set, otherwise local files."""
    url = os.getenv("BACKEND_URL", "").strip()
    if url:
        key = os.getenv("AGENT_API_KEY", "").strip()
        if not key:
            raise RuntimeError("AGENT_API_KEY must be set when BACKEND_URL is set")
        logger.info(f"Using the orders backend at {url}")
        return HttpBackend(url, key)
    logger.warning("BACKEND_URL is not set: standalone mode, orders go to ./data/orders.jsonl")
    return StandaloneBackend(
        HERE / "sample_menu.json",
        Path(os.getenv("DATA_DIR", HERE / "data")),
        delivery_fee_afn=int(os.getenv("DELIVERY_FEE_AFN", "50")),
        eta_minutes=int(os.getenv("ETA_MINUTES", "40")),
    )


BACKEND = make_backend()
handlers.configure(BACKEND)

# Guard rails so a public call page cannot run up the Gemini bill.
MAX_CONCURRENT_CALLS = int(os.getenv("MAX_CONCURRENT_CALLS", "5"))
MAX_CALL_SECONDS = int(os.getenv("MAX_CALL_SECONDS", "600"))
_active_calls = 0

SORRY_UNAVAILABLE = "ببخشید، سیستم سفارش فعلاً در دسترس نیست. لطفاً کمی بعد دوباره زنگ بزنید."
SORRY_BUSY = "ببخشید، همه خط‌ها مصروف است. لطفاً چند دقیقه بعد دوباره زنگ بزنید."
SORRY_TOO_LONG = "ببخشید، وقت این تماس تمام شد. اگر سفارش‌تان ثبت نشده، لطفاً دوباره زنگ بزنید."

transport_params = {
    "webrtc": lambda: TransportParams(audio_in_enabled=True, audio_out_enabled=True),
    "eval": lambda: EvalTransportParams(audio_in_enabled=True, audio_out_enabled=True),
}


def call_details(runner_args: RunnerArguments) -> tuple[str, str | None]:
    """Which channel the call came from and, for WhatsApp, the caller's number."""
    if isinstance(runner_args, EvalRunnerArguments):
        return "eval", None
    body = getattr(runner_args, "body", None)
    caller = getattr(body, "from_", None)  # WhatsAppConnectCall from Meta's webhook
    if caller:
        return "whatsapp", f"+{caller}" if str(caller).isdigit() else str(caller)
    return "web", None


def make_services(adaptation_phrases: list[str]):
    api_key = os.getenv("GOOGLE_API_KEY", "")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY is not set; get one at https://aistudio.google.com/apikey")

    stt_languages = [
        Language(code.strip()) for code in os.getenv("STT_LANGUAGES", "").split(",") if code.strip()
    ]
    stt = GeminiSTTService(
        api_key=api_key,
        settings=GeminiSTTService.Settings(
            model=os.getenv("GEMINI_STT_MODEL", "gemini-3.5-transcribe-live"),
            # Menu words are biased so "قابلی پلو" is not heard as something else.
            adaptation_phrases=adaptation_phrases,
            # Empty = automatic language detection, which handles Dari mixed with English.
            **({"languages": stt_languages} if stt_languages else {}),
        ),
    )
    llm = GoogleLLMService(
        api_key=api_key,
        settings=GoogleLLMService.Settings(
            model=os.getenv("GEMINI_LLM_MODEL", "gemini-3.6-flash"),
            # Little thinking keeps replies fast; the flow does the reasoning work.
            thinking=GoogleLLMService.ThinkingConfig(
                thinking_level=os.getenv("GEMINI_THINKING_LEVEL", "minimal")
            ),
        ),
    )
    tts = GeminiTTSService(
        api_key=api_key,
        settings=GeminiTTSService.Settings(
            model=os.getenv("GEMINI_TTS_MODEL", "gemini-3.8-flash-lite-tts"),
            voice=os.getenv("GEMINI_TTS_VOICE", "Kore"),
            # None lets the model detect Dari from the text. Set TTS_LANGUAGE to force a code.
            language=os.getenv("TTS_LANGUAGE", "").strip() or None,
        ),
    )
    return stt, llm, tts


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments) -> None:
    global _active_calls
    channel, caller_phone = call_details(runner_args)
    session_id = getattr(runner_args, "session_id", None) or str(uuid.uuid4())
    started_at = datetime.now(UTC)
    logger.info(f"New {channel} call, session {session_id}")

    refusal = None
    menu = None
    if _active_calls >= MAX_CONCURRENT_CALLS:
        logger.warning(f"{_active_calls} calls in progress, refusing a new one")
        refusal = SORRY_BUSY
    else:
        try:
            menu = await BACKEND.get_menu()
        except BackendError as error:
            logger.error(f"Cannot load the menu, refusing the call: {error}")
            refusal = SORRY_UNAVAILABLE

    tracker = UsageTracker(CostRates.from_env())
    stt, llm, tts = make_services(menu.adaptation_phrases() if menu else [])
    context = LLMContext()
    context_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(),
            filter_incomplete_user_turns=True,
        ),
    )
    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            context_aggregator.user(),
            llm,
            tts,
            transport.output(),
            context_aggregator.assistant(),
        ]
    )
    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(enable_metrics=True, enable_usage_metrics=True),
        idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
        # If Gemini rejects the key or goes down, end the call instead of leaving silence.
        processor_unusable_policy=ProcessorUnusablePolicy.END,
        observers=[UsageObserver(tracker)],
    )
    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)
    await runner.add_workers(worker)

    flow_manager = FlowManager(
        worker=worker,
        llm=llm,
        context_aggregator=context_aggregator,
        transport=transport,
        global_functions=FLOW.global_functions,
    )
    if menu is not None:
        flow_manager.state.update(
            handlers.initial_state(
                restaurant_name=os.getenv("RESTAURANT_NAME", "رستوران نمونه هرات"),
                menu_text=menu.prompt_text(),
                session_id=session_id,
                channel=channel,
                caller_phone=caller_phone,
            )
        )

    time_limit: asyncio.Task | None = None

    async def end_when_too_long():
        await asyncio.sleep(MAX_CALL_SECONDS)
        logger.warning(f"Call {session_id} reached {MAX_CALL_SECONDS}s, ending it")
        await worker.queue_frames([TTSSpeakFrame(SORRY_TOO_LONG), EndFrame()])

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        nonlocal time_limit
        if refusal is not None:
            await worker.queue_frames([TTSSpeakFrame(refusal), EndFrame()])
            return
        time_limit = asyncio.create_task(end_when_too_long())
        await flow_manager.initialize(FLOW.initial_node)

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info(f"Caller left, session {session_id}")
        await runner.cancel()

    if refusal is None:
        _active_calls += 1
    try:
        await runner.run()
    finally:
        if time_limit:
            time_limit.cancel()
        if refusal is None:
            _active_calls -= 1
        ended_at = datetime.now(UTC)
        seconds = (ended_at - started_at).total_seconds()
        state = flow_manager.state
        await BACKEND.record_call(
            {
                "sessionId": session_id,
                "channel": channel,
                **({"callerPhone": caller_phone} if caller_phone else {}),
                "outcome": state.get("outcome", "abandoned"),
                **({"orderId": state["order_id"]} if state.get("order_id") else {}),
                "startedAt": started_at.isoformat(),
                "endedAt": ended_at.isoformat(),
                "transcript": transcript_from_messages(context.get_messages()),
                "llmPromptTokens": tracker.prompt_tokens,
                "llmCompletionTokens": tracker.completion_tokens,
                "ttsCharacters": tracker.tts_characters,
                "estCostUsd": tracker.estimate_usd(seconds),
            }
        )
        logger.info(
            f"Call {session_id} ended after {seconds:.0f}s, outcome {state.get('outcome')}, "
            f"estimated cost ${tracker.estimate_usd(seconds):.4f}"
        )


async def bot(runner_args: RunnerArguments):
    """Entry point the Pipecat runner calls for every new call."""
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args)


def add_web_routes() -> None:
    """The Dari "call to order" page, served next to the runner's own routes."""
    from pipecat.runner.run import app

    @app.get("/order", include_in_schema=False)
    async def order_page():
        return FileResponse(HERE / "web" / "order.html")

    @app.get("/menu.json", include_in_schema=False)
    async def public_menu():
        """Names and prices for the call page. The menu is public; no keys are exposed."""
        menu = await BACKEND.get_menu()
        return {
            "restaurant": os.getenv("RESTAURANT_NAME", "رستوران نمونه هرات"),
            "items": [
                {"name": item.name_fa, "priceAfn": item.price_afn, "available": item.available}
                for item in menu.items
            ],
        }

    @app.get("/healthz", include_in_schema=False)
    async def healthz():
        return {"ok": True}


if __name__ == "__main__":
    from pipecat.runner.run import main

    add_web_routes()
    main()
