"""
Aegis MOS — Telemetry Persistence.

Handles writing spacecraft state to Supabase/PostgreSQL.
Runs as a background task alongside the simulator, batching writes
to avoid per-tick DB round-trips.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from db.models import SimulationSession, TelemetrySnapshot
from simulator.state import SpacecraftState

logger = logging.getLogger("aegis.persistence")


class TelemetryPersistence:
    """
    Batches and persists telemetry snapshots to the database.

    Features:
      - Configurable sample rate (every Nth tick)
      - Batched writes (flush every N ticks or on buffer full)
      - Creates a simulation session on startup
      - Non-blocking: runs in a background task
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        sample_rate: int | None = None,
        batch_size: int = 30,
    ):
        self.session_factory = session_factory
        self.sample_rate = sample_rate or int(os.getenv("TELEMETRY_SAMPLE_RATE", "1"))
        self.batch_size = batch_size
        self.session_id: uuid.UUID | None = None
        self._buffer: list[dict] = []
        self._tick_count = 0

    async def start_session(self, config: dict | None = None) -> uuid.UUID:
        """Create a new simulation session in the database."""
        self.session_id = uuid.uuid4()

        try:
            async with self.session_factory() as db:
                session = SimulationSession(
                    id=self.session_id,
                    status="running",
                    config=config or {},
                    total_ticks=0,
                )
                db.add(session)
                await db.commit()
                logger.info(f"Simulation session created: {self.session_id}")
        except Exception as e:
            logger.error(f"Failed to create session in DB: {e}")
            # Continue without persistence — don't block the simulator
            self.session_id = None

        return self.session_id

    async def record_tick(self, state: SpacecraftState) -> None:
        """
        Record a telemetry snapshot for the current tick.

        Only stores every Nth tick (controlled by sample_rate).
        Buffers writes and flushes in batches.
        """
        if self.session_id is None:
            return  # No DB session — skip persistence

        self._tick_count += 1

        # Only sample every Nth tick
        if self._tick_count % self.sample_rate != 0:
            return

        # Build snapshot dict (matches TelemetrySnapshot columns)
        snapshot = {
            "session_id": self.session_id,
            "t": state.t,
            "battery_soc": state.battery_soc,
            "bus_voltage": state.bus_voltage,
            "solar_input_w": state.solar_input_w,
            "power_draw_w": state.power_draw_w,
            "temp_c": state.temp_c,
            "heater_on": state.heater_on,
            "attitude_deg": state.attitude_deg,
            "slew_rate_dps": state.slew_rate_dps,
            "target_attitude_deg": state.target_attitude_deg,
            "storage_used_mb": state.storage_used_mb,
            "storage_capacity_mb": state.storage_capacity_mb,
            "comms_active": state.comms_active,
            "link_margin_db": state.link_margin_db,
            "in_contact": state.in_contact,
            "in_eclipse": state.in_eclipse,
            "orbit_phase": state.orbit_phase,
            "is_observing": state.is_observing,
            "is_slewing": state.is_slewing,
        }

        self._buffer.append(snapshot)

        # Flush when buffer is full
        if len(self._buffer) >= self.batch_size:
            await self._flush()

    async def stop_session(self) -> None:
        """Mark the simulation session as stopped and flush remaining data."""
        # Flush any remaining buffered data
        await self._flush()

        if self.session_id is None:
            return

        try:
            async with self.session_factory() as db:
                from sqlalchemy import update
                stmt = (
                    update(SimulationSession)
                    .where(SimulationSession.id == self.session_id)
                    .values(
                        status="stopped",
                        stopped_at=datetime.now(timezone.utc),
                        total_ticks=self._tick_count,
                    )
                )
                await db.execute(stmt)
                await db.commit()
                logger.info(
                    f"Session {self.session_id} stopped at tick {self._tick_count}"
                )
        except Exception as e:
            logger.error(f"Failed to update session status: {e}")

    async def _flush(self) -> None:
        """Write buffered snapshots to the database in a single batch insert."""
        if not self._buffer or self.session_id is None:
            return

        batch = self._buffer.copy()
        self._buffer.clear()

        try:
            async with self.session_factory() as db:
                stmt = insert(TelemetrySnapshot).values(batch)
                await db.execute(stmt)
                await db.commit()
                logger.debug(f"Flushed {len(batch)} telemetry snapshots to DB")
        except Exception as e:
            logger.error(f"Failed to flush telemetry batch ({len(batch)} rows): {e}")
            # Don't re-buffer — data is lost if DB is down, but simulator continues
