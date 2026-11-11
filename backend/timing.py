"""Non-sensitive per-turn latency telemetry (monotonic durations only)."""
import contextvars
import logging
import os
import time
from pathlib import Path

logger = logging.getLogger('gnani.timing')
# This file contains stage names and elapsed milliseconds only.
handler = logging.FileHandler(Path(__file__).resolve().parent / 'timing.log', encoding='utf-8')
handler.setFormatter(logging.Formatter('%(message)s'))
logger.addHandler(handler)
current = contextvars.ContextVar('gnani_timing', default=None)

class Timing:
    def __init__(self):
        self.start = time.monotonic()
        self.events = {}
    def mark(self, event):
        if event not in self.events:
            ms = round((time.monotonic() - self.start) * 1000)
            self.events[event] = ms
            if os.getenv('GNANI_TESTING')!='1':logger.warning('stage=%s elapsed_ms=%s', event, ms)
    def snapshot(self):
        return dict(self.events)

def mark(event):
    timing = current.get()
    if timing:
        timing.mark(event)
