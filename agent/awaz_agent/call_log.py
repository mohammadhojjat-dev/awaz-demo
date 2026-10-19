"""What gets saved about each call: the transcript and an estimated cost.

Costs are estimates from list prices you can change with environment
variables; check them against your real Google bill.
"""

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class CostRates:
    """US dollars. Defaults are list prices at the time of writing (October 2026)."""

    llm_input_per_million: float = 0.75  # gemini-3.6-flash input tokens
    llm_output_per_million: float = 3.75  # gemini-3.6-flash output tokens
    stt_per_minute: float = 0.009  # gemini-3.5-transcribe-live, streaming
    tts_per_million_audio_tokens: float = 6.0  # gemini-3.8-flash-lite-tts (intro price to 31 Dec 2026)
    tts_audio_tokens_per_second: float = 25.0
    tts_chars_per_second: float = 14.0  # rough speaking rate for Dari text

    @classmethod
    def from_env(cls) -> "CostRates":
        def number(name: str, default: float) -> float:
            raw = os.getenv(name, "").strip()
            return float(raw) if raw else default

        defaults = cls()
        return cls(
            llm_input_per_million=number("COST_LLM_INPUT_PER_M", defaults.llm_input_per_million),
            llm_output_per_million=number("COST_LLM_OUTPUT_PER_M", defaults.llm_output_per_million),
            stt_per_minute=number("COST_STT_PER_MIN", defaults.stt_per_minute),
            tts_per_million_audio_tokens=number(
                "COST_TTS_PER_M_AUDIO", defaults.tts_per_million_audio_tokens
            ),
        )


@dataclass
class UsageTracker:
    rates: CostRates = field(default_factory=CostRates)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    tts_characters: int = 0

    def add_llm(self, prompt_tokens: int, completion_tokens: int) -> None:
        self.prompt_tokens += max(0, prompt_tokens)
        self.completion_tokens += max(0, completion_tokens)

    def add_tts(self, characters: int) -> None:
        self.tts_characters += max(0, characters)

    def estimate_usd(self, call_seconds: float) -> float:
        r = self.rates
        llm = (
            self.prompt_tokens * r.llm_input_per_million + self.completion_tokens * r.llm_output_per_million
        ) / 1_000_000
        # Speech recognition listens for the whole call, silence included.
        stt = max(0.0, call_seconds) / 60 * r.stt_per_minute
        speech_seconds = self.tts_characters / r.tts_chars_per_second
        tts = speech_seconds * r.tts_audio_tokens_per_second * r.tts_per_million_audio_tokens / 1_000_000
        return round(llm + stt + tts, 5)


def _text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            part.get("text", "") for part in content if isinstance(part, dict) and part.get("type") == "text"
        )
    return ""


def transcript_from_messages(messages: list) -> list[dict]:
    """The spoken conversation only: caller and agent turns, no prompts or tool calls."""
    lines = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        if role not in ("user", "assistant"):
            continue
        text = _text_of(message.get("content")).strip()
        if text:
            lines.append({"role": role, "text": text[:4000]})
    return lines[-400:]
