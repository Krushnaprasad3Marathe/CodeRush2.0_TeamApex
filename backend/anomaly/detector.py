"""
Aegis MOS — Anomaly Detector (F4).

Continuously compares actual telemetry against expected behavior envelopes
for active tasks. Flags divergence within 2 ticks of threshold breach.

The detector:
  1. Maintains per-variable thresholds and expected envelopes
  2. Uses a configurable debounce window (default 3 ticks) to avoid
     transient false positives
  3. Marks affected data streams as "suspect" on confirmed anomaly
  4. Integrates with the RootCauseCorrelator for multi-subsystem diagnosis
  5. Tracks anomaly lifecycle: active → acknowledged → cleared
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from anomaly.correlator import (
    AnomalyAlert,
    RootCauseDiagnosis,
    RootCauseCorrelator,
    VARIABLE_TO_SUBSYSTEM,
)
from simulator.state import SpacecraftState

logger = logging.getLogger("aegis.anomaly")


@dataclass
class ThresholdConfig:
    """Threshold configuration for a single state variable."""

    variable: str
    min_value: float | None = None
    max_value: float | None = None
    rate_of_change_max: float | None = None  # Max allowed change per tick
    description: str = ""


@dataclass
class TaskEnvelope:
    """Expected behavior envelope for a commanded task."""

    task_name: str
    expected_variable: str
    expected_trajectory: list[float] | None = None  # Expected values over time
    tolerance: float = 0.1                           # Acceptable deviation
    start_t: int = 0
    end_t: int | None = None


# ── Default thresholds ──────────────────────────────────────────────
DEFAULT_THRESHOLDS: list[ThresholdConfig] = [
    ThresholdConfig("battery_soc", min_value=0.10, max_value=1.0,
                    rate_of_change_max=0.05,
                    description="Battery charge outside safe range"),
    ThresholdConfig("bus_voltage", min_value=3.5, max_value=5.5,
                    rate_of_change_max=0.3,
                    description="Bus voltage outside nominal band"),
    ThresholdConfig("temp_c", min_value=-20.0, max_value=60.0,
                    rate_of_change_max=5.0,
                    description="Temperature outside operating range"),
    ThresholdConfig("solar_input_w", min_value=0.0, max_value=10.0,
                    description="Solar input anomaly"),
    ThresholdConfig("storage_used_mb", min_value=0.0, max_value=2048.0,
                    rate_of_change_max=50.0,
                    description="Storage usage anomaly"),
    ThresholdConfig("attitude_deg", min_value=-180.0, max_value=180.0,
                    rate_of_change_max=5.0,
                    description="Unexpected attitude deviation"),
    ThresholdConfig("link_margin_db", min_value=-30.0,
                    description="Link margin critically low"),
]


class AnomalyDetector:
    """
    Monitors spacecraft telemetry for out-of-envelope behavior.

    On each tick:
      1. Check all thresholds against current state (or reported values
         if sensor faults are active)
      2. Track consecutive threshold breaches (debounce)
      3. Fire alerts after debounce window expires
      4. Pass alerts to the RootCauseCorrelator
    """

    def __init__(
        self,
        correlator: RootCauseCorrelator | None = None,
        debounce_ticks: int = 3,
        thresholds: list[ThresholdConfig] | None = None,
    ):
        self.correlator = correlator or RootCauseCorrelator()
        self.debounce_ticks = debounce_ticks
        self.thresholds = {t.variable: t for t in (thresholds or DEFAULT_THRESHOLDS)}

        # Tracking state
        self._breach_counts: dict[str, int] = {}     # variable → consecutive breach ticks
        self._previous_values: dict[str, float] = {}  # variable → last tick value
        self._active_alerts: dict[str, AnomalyAlert] = {}  # alert_id → alert
        self._suspect_streams: set[str] = set()        # variables currently suspect
        self._alert_counter = 0
        self._alert_history: list[AnomalyAlert] = []
        self._task_envelopes: list[TaskEnvelope] = []

    @property
    def active_alerts(self) -> list[AnomalyAlert]:
        return [a for a in self._active_alerts.values() if not a.acknowledged]

    @property
    def all_alerts(self) -> list[AnomalyAlert]:
        return list(self._alert_history)

    @property
    def suspect_streams(self) -> set[str]:
        return set(self._suspect_streams)

    def add_task_envelope(self, envelope: TaskEnvelope):
        """Register an expected behavior envelope for a task."""
        self._task_envelopes.append(envelope)

    def remove_task_envelope(self, task_name: str):
        """Remove task envelope when task completes."""
        self._task_envelopes = [
            e for e in self._task_envelopes if e.task_name != task_name
        ]

    def check_tick(
        self,
        state: SpacecraftState,
        reported_overrides: dict[str, float] | None = None,
    ) -> list[AnomalyAlert]:
        """
        Run anomaly detection for a single tick.

        Args:
            state: Current spacecraft state (ground truth).
            reported_overrides: Sensor-faulted reported values (if any).

        Returns:
            List of newly fired alerts (empty if no new anomalies).
        """
        new_alerts: list[AnomalyAlert] = []
        values = reported_overrides or {}

        for variable, threshold in self.thresholds.items():
            # Use reported value if available (sensor fault), else ground truth
            if variable in values:
                current = values[variable]
            elif hasattr(state, variable):
                current = getattr(state, variable)
            else:
                continue

            if not isinstance(current, (int, float)):
                continue

            # Check threshold breach
            breach = False
            breach_reason = ""

            if threshold.min_value is not None and current < threshold.min_value:
                breach = True
                breach_reason = (
                    f"{variable} = {current:.3f} below minimum "
                    f"{threshold.min_value}"
                )
            elif threshold.max_value is not None and current > threshold.max_value:
                breach = True
                breach_reason = (
                    f"{variable} = {current:.3f} above maximum "
                    f"{threshold.max_value}"
                )

            # Rate-of-change check
            if (
                not breach
                and threshold.rate_of_change_max is not None
                and variable in self._previous_values
            ):
                delta = abs(current - self._previous_values[variable])
                if delta > threshold.rate_of_change_max:
                    breach = True
                    breach_reason = (
                        f"{variable} rate of change {delta:.3f}/tick exceeds "
                        f"limit {threshold.rate_of_change_max}"
                    )

            self._previous_values[variable] = current

            if breach:
                self._breach_counts[variable] = (
                    self._breach_counts.get(variable, 0) + 1
                )

                # Fire alert after debounce window (but within 2 ticks for
                # clear threshold violations)
                effective_debounce = min(self.debounce_ticks, 2)
                if self._breach_counts[variable] >= effective_debounce:
                    # Only fire if no active alert for this variable
                    existing = any(
                        a.variable == variable and not a.acknowledged
                        for a in self._active_alerts.values()
                    )
                    if not existing:
                        alert = self._create_alert(
                            variable, state.t, breach_reason, threshold
                        )
                        new_alerts.append(alert)
            else:
                # Reset breach counter on clean tick
                self._breach_counts[variable] = 0

        # Check task envelopes
        for envelope in self._task_envelopes:
            task_alerts = self._check_envelope(state, envelope)
            new_alerts.extend(task_alerts)

        # Feed new alerts to correlator
        for alert in new_alerts:
            diagnosis = self.correlator.add_alert(alert)
            if diagnosis:
                logger.info(
                    "Root-cause diagnosis: %s → %s",
                    diagnosis.diagnosis_id,
                    diagnosis.explanation,
                )

        return new_alerts

    def _create_alert(
        self,
        variable: str,
        t: int,
        reason: str,
        threshold: ThresholdConfig,
    ) -> AnomalyAlert:
        """Create a new anomaly alert."""
        self._alert_counter += 1
        alert_id = f"ANOM-{self._alert_counter:04d}"

        subsystem = VARIABLE_TO_SUBSYSTEM.get(variable, "unknown")
        severity = "critical" if "below minimum" in reason or "above maximum" in reason else "warning"

        alert = AnomalyAlert(
            alert_id=alert_id,
            subsystem=subsystem,
            variable=variable,
            severity=severity,
            description=f"{threshold.description}: {reason}",
            detected_at_t=t,
            is_suspect=True,
        )

        self._active_alerts[alert_id] = alert
        self._alert_history.append(alert)
        self._suspect_streams.add(variable)

        logger.warning(
            "ANOMALY %s: %s (%s) at t=%d",
            alert_id, reason, severity, t,
        )

        return alert

    def _check_envelope(
        self, state: SpacecraftState, envelope: TaskEnvelope
    ) -> list[AnomalyAlert]:
        """Check a task's expected behavior envelope."""
        alerts: list[AnomalyAlert] = []

        if not hasattr(state, envelope.expected_variable):
            return alerts

        current = getattr(state, envelope.expected_variable)
        if not isinstance(current, (int, float)):
            return alerts

        # If trajectory is defined, check against expected position
        if envelope.expected_trajectory:
            idx = state.t - envelope.start_t
            if 0 <= idx < len(envelope.expected_trajectory):
                expected = envelope.expected_trajectory[idx]
                deviation = abs(current - expected)
                if deviation > envelope.tolerance:
                    self._alert_counter += 1
                    alert_id = f"ANOM-{self._alert_counter:04d}"
                    subsystem = VARIABLE_TO_SUBSYSTEM.get(
                        envelope.expected_variable, "unknown"
                    )
                    alert = AnomalyAlert(
                        alert_id=alert_id,
                        subsystem=subsystem,
                        variable=envelope.expected_variable,
                        severity="warning",
                        description=(
                            f"Task '{envelope.task_name}': "
                            f"{envelope.expected_variable} deviates by "
                            f"{deviation:.3f} from expected {expected:.3f} "
                            f"(tolerance: {envelope.tolerance})"
                        ),
                        detected_at_t=state.t,
                    )
                    self._active_alerts[alert_id] = alert
                    self._alert_history.append(alert)
                    self._suspect_streams.add(envelope.expected_variable)
                    alerts.append(alert)

        return alerts

    def acknowledge_alert(
        self,
        alert_id: str,
        operator_id: str,
        t: int,
    ) -> bool:
        """
        Acknowledge/clear an anomaly. This is an audited action.

        Returns True if the alert was found and acknowledged.
        """
        alert = self._active_alerts.get(alert_id)
        if alert is None:
            return False

        alert.acknowledged = True
        alert.acknowledged_by = operator_id
        alert.acknowledged_at_t = t
        alert.is_suspect = False

        # Un-suspect the stream if no other active alerts on it
        other_active = any(
            a.variable == alert.variable and not a.acknowledged
            for a in self._active_alerts.values()
        )
        if not other_active:
            self._suspect_streams.discard(alert.variable)

        logger.info(
            "Alert %s acknowledged by %s at t=%d",
            alert_id, operator_id, t,
        )
        return True

    def get_alerts_summary(self) -> list[dict]:
        """Return all alerts as dicts for the API/broadcast."""
        result = []
        for alert in self._alert_history:
            result.append({
                "alert_id": alert.alert_id,
                "subsystem": alert.subsystem,
                "variable": alert.variable,
                "severity": alert.severity,
                "description": alert.description,
                "detected_at_t": alert.detected_at_t,
                "is_suspect": alert.is_suspect,
                "acknowledged": alert.acknowledged,
                "acknowledged_by": alert.acknowledged_by,
                "acknowledged_at_t": alert.acknowledged_at_t,
                "root_cause_id": alert.root_cause_id,
            })
        return result

    def is_stream_suspect(self, variable: str) -> bool:
        """Check if a data stream is currently marked suspect."""
        return variable in self._suspect_streams
