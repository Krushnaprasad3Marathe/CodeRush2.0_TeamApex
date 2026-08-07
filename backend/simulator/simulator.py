"""
Aegis MOS — Simulation Loop (The Single Source of Truth).

This module owns the 1Hz physics loop and is the ONLY thing allowed to
mutate spacecraft state. Every other backend service is a consumer of its
broadcast stream, never a second writer of physical state.

This is what makes F2's determinism/consistency guarantees possible:
one writer, many readers, all keyed to state.t.

The tick loop now includes:
  1. Apply system-tier faults (before physics)
  2. Step physics
  3. Apply sensor-tier faults (after physics, overlay on reported values)
  4. Run anomaly detection
  5. Run root-cause correlation
  6. Serialize + broadcast
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from anomaly.correlator import RootCauseCorrelator
from anomaly.detector import AnomalyDetector
from faults.engine import FaultEngine
from simulator.broadcast import BroadcastManager
from simulator.clock import SelfCorrectingClock
from simulator.physics import CubeSatParams, PhysicsEngine
from simulator.state import ScheduledFault, SpacecraftState

if TYPE_CHECKING:
    from db.persistence import TelemetryPersistence

logger = logging.getLogger("aegis.simulator")


class Simulator:
    """
    The core simulation engine.

    Runs a continuous 1Hz physics loop that:
      1. Waits for the next clock tick
      2. Applies system-tier faults (before physics)
      3. Steps the physics engine
      4. Applies sensor-tier faults (after physics)
      5. Runs anomaly detection
      6. Runs root-cause correlation
      7. Increments state.t
      8. Serializes state ONCE
      9. Broadcasts the same bytes to all connected WS clients
    """

    def __init__(
        self,
        hz: float = 1.0,
        params: CubeSatParams | None = None,
        persistence: "TelemetryPersistence | None" = None,
    ):
        self.clock = SelfCorrectingClock(hz=hz)
        self.state = SpacecraftState.initial()
        self.physics = PhysicsEngine(params=params)
        self.broadcast = BroadcastManager()
        self.persistence = persistence
        self.pending_faults: list[ScheduledFault] = []
        self._running = False

        # F3 — Fault Injection Engine
        self.fault_engine = FaultEngine()

        # F4 — Anomaly Detection + F1 Root-Cause Correlation
        self.correlator = RootCauseCorrelator()
        self.anomaly_detector = AnomalyDetector(correlator=self.correlator)

    @property
    def is_running(self) -> bool:
        """Whether the simulation loop is currently active."""
        return self._running

    async def run(self) -> None:
        """
        Main simulation loop — runs indefinitely until stop() is called.

        CRITICAL INVARIANT: This is the ONLY coroutine that mutates self.state.
        No other backend service should write physical state.
        """
        self._running = True
        logger.info("Simulation loop started at %.1f Hz", self.clock.hz)

        # Start a DB session if persistence is configured
        if self.persistence:
            await self.persistence.start_session(
                config={"hz": self.clock.hz, "params": "default"}
            )

        while self._running:
            await self.clock.wait_for_next_tick()

            # Apply any legacy scheduled faults (backward compat)
            self._apply_pending_faults()

            # ── F3: Apply system-tier faults BEFORE physics ─────────
            self.state = self.fault_engine.apply_system_faults(self.state)

            # ── Advance physics by one tick ──────────────────────────
            self.state = self.physics.step(self.state)

            # ── F3: Apply sensor-tier faults AFTER physics ──────────
            reported = self.fault_engine.apply_sensor_faults(self.state)

            # Write sensor-fault overlays into state for broadcast
            for var, val in reported.items():
                reported_field = f"reported_{var}"
                if hasattr(self.state, reported_field):
                    setattr(self.state, reported_field, val)

            # Clear reported fields for variables without sensor faults
            for field_name in [
                "reported_battery_soc", "reported_bus_voltage",
                "reported_solar_input_w", "reported_temp_c",
                "reported_attitude_deg", "reported_storage_used_mb",
                "reported_link_margin_db", "reported_power_draw_w",
                "reported_slew_rate_dps",
            ]:
                base_var = field_name.replace("reported_", "")
                if base_var not in reported:
                    setattr(self.state, field_name, None)

            # ── F4: Run anomaly detection ───────────────────────────
            new_alerts = self.anomaly_detector.check_tick(
                self.state, reported if reported else None
            )

            # Update state with anomaly data for broadcast
            self.state.active_anomalies = self.anomaly_detector.get_alerts_summary()
            self.state.suspect_streams = list(self.anomaly_detector.suspect_streams)

            # Root-cause diagnosis
            latest_diag = self.correlator.latest_diagnosis
            self.state.root_cause_diagnosis = (
                latest_diag.to_dict() if latest_diag else None
            )

            # Fault engine state for sandbox UI
            self.state.active_faults = self.fault_engine.get_active_faults_summary()
            self.state.sandbox_mode = self.fault_engine.sandbox_mode
            self.state.scorecard = self.fault_engine.get_scorecard()

            # Increment simulation clock
            self.state.t += 1
            self.state.timestamp = time.time()

            # Serialize ONCE — all clients get the same bytes
            payload = self.state.model_dump_json().encode("utf-8")
            await self.broadcast.publish(payload)

            # Persist telemetry to database (non-blocking, batched)
            if self.persistence:
                await self.persistence.record_tick(self.state)

            # Periodic logging
            if self.state.t % 60 == 0:
                logger.info(
                    "t=%d | SOC=%.2f | Temp=%.1f°C | Hz=%.4f | Clients=%d | Alerts=%d",
                    self.state.t,
                    self.state.battery_soc,
                    self.state.temp_c,
                    self.clock.observed_hz,
                    self.broadcast.client_count,
                    len(self.anomaly_detector.active_alerts),
                )

    async def stop(self) -> None:
        """Stop the simulation loop gracefully and flush remaining data."""
        self._running = False
        logger.info("Simulation loop stopping at t=%d", self.state.t)

        # Flush remaining telemetry and mark session as stopped
        if self.persistence:
            await self.persistence.stop_session()

    def schedule_fault(self, fault: ScheduledFault) -> None:
        """
        Schedule a fault to fire at a specific simulation tick.

        Faults are keyed to state.t, not wall-clock time, so they
        reproduce identically in real-time and accelerated replay.
        """
        self.pending_faults.append(fault)
        self.pending_faults.sort(key=lambda f: f.trigger_t)
        logger.info(
            "Fault %s scheduled for t=%d (%s on %s.%s)",
            fault.fault_id,
            fault.trigger_t,
            fault.fault_type,
            fault.target_subsystem,
            fault.target_variable,
        )

    def _apply_pending_faults(self) -> None:
        """
        Apply any faults whose trigger_t matches the current simulation tick.

        Faults are applied BEFORE physics computation on their trigger tick,
        ensuring deterministic behavior regardless of execution speed.
        """
        current_t = self.state.t
        faults_to_apply = [
            f for f in self.pending_faults
            if f.trigger_t == current_t and not f.applied
        ]

        for fault in faults_to_apply:
            self._apply_fault(fault)
            fault.applied = True
            logger.info(
                "Fault %s applied at t=%d: %s on %s.%s",
                fault.fault_id,
                current_t,
                fault.fault_type,
                fault.target_subsystem,
                fault.target_variable,
            )

        # Clean up old applied faults to prevent unbounded list growth
        self.pending_faults = [
            f for f in self.pending_faults
            if not f.applied or f.trigger_t > current_t
        ]

    def _apply_fault(self, fault: ScheduledFault) -> None:
        """
        Apply a single fault to the spacecraft state.

        For Phase 1, this is a basic implementation that directly modifies
        state variables. Phase 2 (F3) will expand this with the full
        fault catalog (bias, drift, noise, stuck, dropout, step_change)
        and the sensor-tier vs system-tier distinction.
        """
        target = fault.target_variable
        params = fault.parameters

        if not hasattr(self.state, target):
            logger.warning(
                "Fault %s targets unknown variable '%s' — skipped",
                fault.fault_id,
                target,
            )
            return

        current_value = getattr(self.state, target)

        if fault.fault_type == "bias" and isinstance(current_value, (int, float)):
            offset = params.get("offset", 0.0)
            setattr(self.state, target, current_value + offset)

        elif fault.fault_type == "step_change" and isinstance(current_value, (int, float)):
            delta = params.get("delta", 0.0)
            setattr(self.state, target, current_value + delta)

        elif fault.fault_type == "stuck":
            # Value is already "stuck" — physics won't overwrite it
            # because we apply faults before physics, and the physics
            # step creates a new state. For true stuck behavior,
            # we'll need the full fault engine in Phase 2.
            pass

        elif fault.fault_type == "dropout":
            if isinstance(current_value, (int, float)):
                setattr(self.state, target, 0.0)
            elif isinstance(current_value, bool):
                setattr(self.state, target, False)

        else:
            logger.warning(
                "Fault type '%s' not yet implemented (Phase 2)",
                fault.fault_type,
            )
