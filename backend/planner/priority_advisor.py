"""
Aegis MOS — Mission Planner Priority Advisor.

Evaluates scheduled mission activities against the data-driven priority dataset
(priority_dataset.json) to validate whether assigned priorities match true mission urgency.
Flags mis-prioritized activities and generates explainable recommendations.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("aegis.planner.advisor")


@dataclass
class PriorityRule:
    rule_id: str
    condition: str
    activity_type: str
    recommended_priority: int
    severity: str
    reason: str


@dataclass
class PriorityMismatch:
    activity_id: str
    activity_type: str
    title: str
    assigned_priority: int
    recommended_priority: int
    delta: int
    direction: str  # "increase" or "decrease"
    matched_rule_id: str
    severity: str  # "critical", "high", "medium", "low"
    reason: str
    ai_recommendation: str = ""

    def to_dict(self) -> dict:
        return {
            "activity_id": self.activity_id,
            "activity_type": self.activity_type,
            "title": self.title,
            "assigned_priority": self.assigned_priority,
            "recommended_priority": self.recommended_priority,
            "delta": self.delta,
            "direction": self.direction,
            "matched_rule_id": self.matched_rule_id,
            "severity": self.severity,
            "reason": self.reason,
            "ai_recommendation": self.ai_recommendation,
        }


class PriorityAdvisor:
    """Evaluates planned activities against mission urgency rules."""

    def __init__(self, dataset_path: str | Path | None = None, mismatch_threshold: int = 2):
        self.mismatch_threshold = mismatch_threshold
        self.rules: list[PriorityRule] = []
        self._load_dataset(dataset_path)

    def _load_dataset(self, path: str | Path | None):
        if path is None:
            # Look in same directory
            path = Path(__file__).parent / "priority_dataset.json"
        else:
            path = Path(path)

        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item in data:
                        self.rules.append(
                            PriorityRule(
                                rule_id=item.get("rule_id", "UNKNOWN"),
                                condition=item.get("condition", ""),
                                activity_type=item.get("activity_type", "any"),
                                recommended_priority=int(item.get("recommended_priority", 5)),
                                severity=item.get("severity", "medium"),
                                reason=item.get("reason", ""),
                            )
                        )
                logger.info("Loaded %d priority rules from %s", len(self.rules), path.name)
            except Exception as e:
                logger.error("Failed to load priority dataset: %e", e)
        else:
            logger.warning("Priority dataset not found at %s", path)

    def evaluate(
        self,
        activities: list[dict | Any],
        state: dict,
        anomalies: list[dict] | None = None,
    ) -> list[PriorityMismatch]:
        """
        Evaluate all activities in a mission plan against the rule dataset.

        Returns a list of PriorityMismatch recommendations for any activities where
        |recommended - assigned| >= mismatch_threshold.
        """
        mismatches: list[PriorityMismatch] = []
        anomalies = anomalies or []

        # Extract space state context
        battery_soc = float(state.get("battery_soc", 0.8))
        storage_used = float(state.get("storage_used_mb", 0.0))
        storage_cap = float(state.get("storage_capacity_mb", 2048.0))
        storage_pct = storage_used / storage_cap if storage_cap > 0 else 0.0
        t = int(state.get("t", 0))

        # Orbit-relative calculations
        orbit_pos = t % 5400
        # Sunlight duration is approx 3300s, eclipse 2100s
        ticks_until_eclipse = max(0, 3300 - orbit_pos) if orbit_pos < 3300 else 0
        # Contact starts at 1200, lasts 600s
        if 1200 <= orbit_pos < 1800:
            ticks_until_contact_loss = 1800 - orbit_pos
        elif orbit_pos < 1200:
            ticks_until_contact_loss = 1800 - orbit_pos
        else:
            ticks_until_contact_loss = 5400 - orbit_pos + 1800

        # Subsystem anomaly map
        subsystem_anomaly_map: dict[str, bool] = {}
        for a in anomalies:
            sub = (a.get("subsystem") or "").lower()
            sev = (a.get("severity") or "").lower()
            if "crit" in sev or not a.get("acknowledged"):
                subsystem_anomaly_map[sub] = True

        for act in activities:
            if hasattr(act, "to_dict"):
                act_data = act.to_dict()
            elif isinstance(act, dict):
                act_data = act
            else:
                continue

            act_id = str(act_data.get("activity_id", "ACT-001"))
            act_type = str(act_data.get("activity_type", "activity")).lower()
            assigned_pri = int(act_data.get("priority", 5))
            title = str(act_data.get("title", act_data.get("description", act_id)))

            # Map activity to target subsystem
            target_sub = "eps" if "charg" in act_type else "comms" if "downlink" in act_type else "adcs"
            crit_sub_anomaly = (
                subsystem_anomaly_map.get(target_sub, False)
                or subsystem_anomaly_map.get("power", False)
                or subsystem_anomaly_map.get("thermal", False)
            )

            # Evaluate matching rules
            matching_mismatches: list[PriorityMismatch] = []

            for rule in self.rules:
                if rule.activity_type != "any" and rule.activity_type.lower() not in act_type:
                    continue

                cond_met = False
                if rule.condition == "battery_soc < 0.20" and battery_soc < 0.20:
                    cond_met = True
                elif rule.condition == "battery_soc < 0.40" and battery_soc < 0.40:
                    cond_met = True
                elif rule.condition == "battery_soc >= 0.85" and battery_soc >= 0.85:
                    cond_met = True
                elif rule.condition == "storage_pct > 0.90" and storage_pct > 0.90:
                    cond_met = True
                elif rule.condition == "storage_pct > 0.70" and storage_pct > 0.70:
                    cond_met = True
                elif rule.condition == "storage_pct < 0.15" and storage_pct < 0.15:
                    cond_met = True
                elif rule.condition == "ticks_until_contact_loss < 300" and ticks_until_contact_loss < 300:
                    cond_met = True
                elif rule.condition == "ticks_until_eclipse < 120" and ticks_until_eclipse < 120:
                    cond_met = True
                elif rule.condition == "battery_soc < 0.25" and battery_soc < 0.25:
                    cond_met = True
                elif rule.condition == "critical_anomaly_in_subsystem" and crit_sub_anomaly:
                    cond_met = True

                if cond_met:
                    delta = abs(rule.recommended_priority - assigned_pri)
                    if delta >= self.mismatch_threshold:
                        direction = "increase" if rule.recommended_priority > assigned_pri else "decrease"
                        rec = PriorityMismatch(
                            activity_id=act_id,
                            activity_type=act_type,
                            title=title,
                            assigned_priority=assigned_pri,
                            recommended_priority=rule.recommended_priority,
                            delta=delta,
                            direction=direction,
                            matched_rule_id=rule.rule_id,
                            severity=rule.severity,
                            reason=rule.reason,
                            ai_recommendation=(
                                f"Adjust {title} priority from {assigned_pri} to {rule.recommended_priority} "
                                f"({direction}) because {rule.reason.lower()}."
                            ),
                        )
                        matching_mismatches.append(rec)

            if matching_mismatches:
                # Critical severity rules win outright; otherwise rule with largest delta wins
                crit_matches = [m for m in matching_mismatches if m.severity == "critical"]
                if crit_matches:
                    best = max(crit_matches, key=lambda m: m.delta)
                else:
                    best = max(matching_mismatches, key=lambda m: m.delta)
                mismatches.append(best)

        return mismatches
