"""Collects token and speech usage from Pipecat's metrics for the call log."""

from pipecat.frames.frames import MetricsFrame
from pipecat.metrics.metrics import LLMUsageMetricsData, TTSUsageMetricsData
from pipecat.observers.base_observer import BaseObserver, FramePushed

from .call_log import UsageTracker


class UsageObserver(BaseObserver):
    """Adds every LLM and TTS usage report to a tracker, once per frame.

    Observers see a frame each time it moves between two processors, so the
    same metrics frame passes by several times; its id makes sure it counts once.
    """

    def __init__(self, tracker: UsageTracker, **kwargs):
        super().__init__(**kwargs)
        self._tracker = tracker
        self._seen: set[int] = set()

    async def on_push_frame(self, data: FramePushed):
        frame = data.frame
        if not isinstance(frame, MetricsFrame) or frame.id in self._seen:
            return
        self._seen.add(frame.id)
        for item in frame.data:
            if isinstance(item, LLMUsageMetricsData):
                self._tracker.add_llm(item.value.prompt_tokens or 0, item.value.completion_tokens or 0)
            elif isinstance(item, TTSUsageMetricsData):
                self._tracker.add_tts(item.value or 0)
