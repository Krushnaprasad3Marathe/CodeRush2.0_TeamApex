"""
Aegis MOS — Root-Cause Correlator (F1/F4).

When multiple anomaly alerts fire within a configurable time window,
this module traverses the subsystem dependency graph to find the
upstream-most fault — the single root cause.

The dependency graph mirrors the physics coupling chain in physics.py:
  Attitude → Solar input → SOC → Bus voltage
  Power draw → Heat → Temperature
  Eclipse → No solar → SOC drops → Thermal drops → Heater → Faster SOC drain
  Downlink → Power draw + Storage change

A fault at any node propagates downstream. The correlator finds the
highest node in the graph that has an active alert.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger("aegis.correlator")


# ── Subsystem Dependency Graph ──────────────────────────────────────
# An edge (A, B) means "A fault can cause B symptoms".
# The graph is a DAG (directed acyclic graph).
DEPENDENCY_EDGES: list[tuple[str, str]] = [
    ("attitude", "solar_input"),
    ("solar_input", "power"),
    ("power", "bus_voltage"),
    ("power", "thermal"),
    ("thermal", "heater"),
    ("heater", "power"),       # Feedback loop — handled by depth limit
    ("comms", "power"),
    ("comms", "storage"),
    ("eclipse", "solar_input"),
    ("eclipse", "thermal"),
]

# Variable → subsystem mapping
VARIABLE_TO_SUBSYSTEM: dict[str, str] = {
    "battery_soc": "power",
    "bus_voltage": "bus_voltage",
    "solar_input_w": "solar_input",
    "power_draw_w": "power",
    "temp_c": "thermal",
    "attitude_deg": "attitude",
    "slew_rate_dps": "attitude",
    "storage_used_mb": "storage",
    "link_margin_db": "comms",
    "comms_active": "comms",
    "in_eclipse": "eclipse",
    "heater_on": "heater",
}

# Build adjacency lists
_downstream: dict[str, set[str]] = {}
_upstream: dict[str, set[str]] = {}
for src, dst in DEPENDENCY_EDGES:
    _downstream.setdefault(src, set()).add(dst)
    _upstream.setdefault(dst, set()).add(src)


@dataclass
class AnomalyAlert:
    """A single anomaly alert from the detector."""

    alert_id: str
    subsystem: str
    variable: str
    severity: str          # "warning", "critical"
    description: str
    detected_at_t: int
    is_suspect: bool = True
    acknowledged: bool = False
    acknowledged_by: str | None = None
    acknowledged_at_t: int | None = None
    root_cause_id: str | None = None   # Link to root-cause diagnosis


@dataclass
class RootCauseDiagnosis:
    """Result of root-cause correlation across multiple alerts."""

    diagnosis_id: str
    root_subsystem: str
    root_variable: str | None
    downstream_effects: list[str]
    alert_ids: list[str]
    explanation: str               # Plain-language, enriched by AI later
    confidence: float              # 0.0–1.0
    diagnosed_at_t: int

    def to_dict(self) -> dict:
        return {
            "diagnosis_id": self.diagnosis_id,
            "root_subsystem": self.root_subsystem,
            "root_variable": self.root_variable,
            "downstream_effects": self.downstream_effects,
            "alert_ids": self.alert_ids,
            "explanation": self.explanation,
            "confidence": self.confidence,
            "diagnosed_at_t": self.diagnosed_at_t,
        }


class RootCauseCorrelator:
    """
    Correlates multiple anomaly alerts to a single root cause.

    Algorithm:
      1. Collect all alerts within the correlation window
      2. Map each alert's variable to its subsystem
      3. For each alerted subsystem, compute "root score" = how many
         other alerted subsystems are reachable downstream from it
      4. The subsystem with the highest root score is the root cause
      5. Generate a plain-language explanation
    """

    def __init__(self, correlation_window_ticks: int = 5):
        self.correlation_window = correlation_window_ticks
        self._recent_alerts: list[AnomalyAlert] = []
        self._diagnoses: list[RootCauseDiagnosis] = []
        self._diagnosis_counter = 0

    def add_alert(self, alert: AnomalyAlert) -> RootCauseDiagnosis | None:
        """
        Register a new alert and attempt correlation.

        Returns a RootCauseDiagnosis if correlation was performed,
        None if waiting for more data.
        """
        self._recent_alerts.append(alert)
        # Prune old alerts outside the correlation window
        cutoff = alert.detected_at_t - self.correlation_window
        self._recent_alerts = [
            a for a in self._recent_alerts if a.detected_at_t >= cutoff
        ]

        # Need at least 2 alerts across different subsystems to correlate
        subsystems = set(a.subsystem for a in self._recent_alerts)
        if len(subsystems) >= 2:
            return self._correlate(alert.detected_at_t)
        elif len(self._recent_alerts) == 1:
            # Single alert — root cause is itself
            return self._single_alert_diagnosis(alert)

        return None

    def _single_alert_diagnosis(self, alert: AnomalyAlert) -> RootCauseDiagnosis:
        """Create a simple diagnosis for a single isolated alert."""
        self._diagnosis_counter += 1
        diag_id = f"DIAG-{self._diagnosis_counter:04d}"

        diagnosis = RootCauseDiagnosis(
            diagnosis_id=diag_id,
            root_subsystem=alert.subsystem,
            root_variable=alert.variable,
            downstream_effects=[],
            alert_ids=[alert.alert_id],
            explanation=(
                f"Anomaly detected in {alert.subsystem} subsystem: "
                f"{alert.description}"
            ),
            confidence=0.9,
            diagnosed_at_t=alert.detected_at_t,
        )
        alert.root_cause_id = diag_id
        self._diagnoses.append(diagnosis)
        return diagnosis

    def _correlate(self, current_t: int) -> RootCauseDiagnosis:
        """
        Perform root-cause correlation across recent alerts.

        Finds the upstream-most subsystem in the dependency graph
        that has an active alert.
        """
        # Map alerts to subsystems
        alert_subsystems: dict[str, list[AnomalyAlert]] = {}
        for alert in self._recent_alerts:
            alert_subsystems.setdefault(alert.subsystem, []).append(alert)

        alerted_set = set(alert_subsystems.keys())

        # Score each alerted subsystem: how many other alerted subsystems
        # can be reached downstream from it?
        scores: dict[str, int] = {}
        for subsystem in alerted_set:
            reachable = self._get_downstream(subsystem, max_depth=6)
            downstream_alerted = reachable & alerted_set - {subsystem}
            scores[subsystem] = len(downstream_alerted)

        # Also compute upstream score: subsystems with fewer upstream
        # alerts are more likely to be root causes
        upstream_scores: dict[str, int] = {}
        for subsystem in alerted_set:
            upstream = self._get_upstream(subsystem, max_depth=6)
            upstream_alerted = upstream & alerted_set - {subsystem}
            upstream_scores[subsystem] = len(upstream_alerted)

        # Root cause = highest downstream score, lowest upstream score
        # Tiebreaker: earliest alert
        def root_score(s: str) -> tuple:
            earliest = min(a.detected_at_t for a in alert_subsystems[s])
            return (-scores.get(s, 0), upstream_scores.get(s, 0), earliest)

        root_subsystem = min(alerted_set, key=root_score)
        downstream = [s for s in alerted_set if s != root_subsystem]

        # Build explanation
        all_alert_ids = [a.alert_id for a in self._recent_alerts]
        total_alerts = len(self._recent_alerts)
        total_subsystems = len(alerted_set)

        explanation = (
            f"{total_alerts} alert{'s' if total_alerts > 1 else ''} across "
            f"{total_subsystems} subsystem{'s' if total_subsystems > 1 else ''} — "
            f"root cause: {root_subsystem} subsystem fault"
        )
        if downstream:
            explanation += f" causing cascading effects in: {', '.join(downstream)}"

        # Confidence based on how many downstream subsystems are explained
        confidence = scores.get(root_subsystem, 0) / max(1, len(alerted_set) - 1)
        confidence = min(1.0, max(0.5, confidence))

        self._diagnosis_counter += 1
        diag_id = f"DIAG-{self._diagnosis_counter:04d}"

        diagnosis = RootCauseDiagnosis(
            diagnosis_id=diag_id,
            root_subsystem=root_subsystem,
            root_variable=None,  # May be enriched later
            downstream_effects=downstream,
            alert_ids=all_alert_ids,
            explanation=explanation,
            confidence=confidence,
            diagnosed_at_t=current_t,
        )

        # Link alerts to this diagnosis
        for alert in self._recent_alerts:
            alert.root_cause_id = diag_id

        self._diagnoses.append(diagnosis)

        logger.info(
            "Root-cause diagnosis %s: %s (confidence=%.2f, %d alerts)",
            diag_id, root_subsystem, confidence, total_alerts,
        )

        # Clear recent alerts after correlation
        self._recent_alerts.clear()

        return diagnosis

    def _get_downstream(self, subsystem: str, max_depth: int = 6) -> set[str]:
        """BFS to find all downstream subsystems from a given node."""
        visited: set[str] = set()
        queue = [subsystem]
        depth = 0
        while queue and depth < max_depth:
            next_queue = []
            for node in queue:
                if node in visited:
                    continue
                visited.add(node)
                next_queue.extend(_downstream.get(node, set()))
            queue = next_queue
            depth += 1
        visited.discard(subsystem)
        return visited

    def _get_upstream(self, subsystem: str, max_depth: int = 6) -> set[str]:
        """BFS to find all upstream subsystems from a given node."""
        visited: set[str] = set()
        queue = [subsystem]
        depth = 0
        while queue and depth < max_depth:
            next_queue = []
            for node in queue:
                if node in visited:
                    continue
                visited.add(node)
                next_queue.extend(_upstream.get(node, set()))
            queue = next_queue
            depth += 1
        visited.discard(subsystem)
        return visited

    @property
    def latest_diagnosis(self) -> RootCauseDiagnosis | None:
        return self._diagnoses[-1] if self._diagnoses else None

    @property
    def all_diagnoses(self) -> list[RootCauseDiagnosis]:
        return list(self._diagnoses)
