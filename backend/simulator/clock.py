"""
Aegis MOS — Self-Correcting Monotonic Clock.

Implements the TRD's clock design to guarantee observed Hz ∈ [0.996, 1.001].

Key idea: accumulate the target tick time (`next_tick += period`) rather than
repeatedly sleeping a fixed duration. This prevents processing-overhead drift
from compounding across ticks.

If we fall behind schedule (processing took longer than one period), we resync
`next_tick` to the current time instead of trying to "catch up" — this avoids
a burst of zero-delay ticks that would break downstream consumers expecting
~1 second between ticks.
"""

from __future__ import annotations

import asyncio
import time


class SelfCorrectingClock:
    """
    Monotonic, self-correcting async clock for the simulation loop.

    Guarantees:
      - Average tick rate converges to target Hz
      - Individual tick jitter stays within ~1–5ms under normal load
      - No drift accumulation over long runs
      - Graceful recovery from processing delays
    """

    def __init__(self, hz: float = 1.0):
        self.period: float = 1.0 / hz
        self.hz: float = hz
        self.tick_count: int = 0
        self.start_time: float | None = None
        self.next_tick: float = 0.0
        self._last_tick_time: float = 0.0

    async def wait_for_next_tick(self) -> None:
        """
        Sleep until the next tick boundary.

        On the very first call, records the start time and returns immediately
        (tick 0 fires instantly). Subsequent calls sleep the precise amount
        needed to land on the next accumulated tick boundary.
        """
        now = time.monotonic()

        if self.start_time is None:
            # First tick — initialize timing baseline
            self.start_time = now
            self.next_tick = now + self.period
            self._last_tick_time = now
            return

        # Accumulate the exact target time for the next tick
        self.next_tick += self.period
        delay = self.next_tick - time.monotonic()

        if delay > 0:
            await asyncio.sleep(delay)
        elif delay < -self.period:
            # We're more than one full period behind — resync
            # This prevents a burst of catch-up ticks
            self.next_tick = time.monotonic() + self.period

        self._last_tick_time = time.monotonic()
        self.tick_count += 1

    @property
    def observed_hz(self) -> float:
        """
        Calculate the observed average tick rate since start.

        Returns the target Hz if insufficient ticks have elapsed
        for a meaningful measurement.
        """
        if self.tick_count < 2 or self.start_time is None:
            return self.hz
        elapsed = time.monotonic() - self.start_time
        if elapsed <= 0:
            return self.hz
        return self.tick_count / elapsed

    @property
    def elapsed_seconds(self) -> float:
        """Total wall-clock seconds since the clock started."""
        if self.start_time is None:
            return 0.0
        return time.monotonic() - self.start_time

    def reset(self) -> None:
        """Reset the clock to its initial state."""
        self.tick_count = 0
        self.start_time = None
        self.next_tick = 0.0
        self._last_tick_time = 0.0
