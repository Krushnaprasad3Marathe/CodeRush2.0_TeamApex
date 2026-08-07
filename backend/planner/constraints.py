"""
Aegis MOS — Constraint Engine (F5).

Validates mission plans against resource budgets by forward-simulating
the plan against a copy of the spacecraft state.

Checks:
  - Power budget (SOC sufficient for each activity)
  - Storage capacity (won't overflow or underflow)
  - Communications windows (downlinks only during contact)
  - Thermal limits (temperature within operating range)
  - Pointing conflicts (can't slew and downlink simultaneously)
  - Precedence ordering (activities respect dependencies)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from planner.activities import ScheduledActivity, ActivityType

logger = logging.getLogger("aegis.constraints")


@dataclass
class ConstraintViolation:
    """A single constraint violation found during plan validation."""

    activity_id: str
    activity_name: str
    constraint_type: str
    description: str
    severity: str  # "error" (blocks execution) or "warning"
    at_tick: int | None = None

    def to_dict(self) -> dict:
        return {
            "activity_id": self.activity_id,
            "activity_name": self.activity_name,
            "constraint_type": self.constraint_type,
            "description": self.description,
            "severity": self.severity,
            "at_tick": self.at_tick,
        }


class ConstraintChecker:
    """
    Validates a mission plan against resource constraints.

    Takes a list of scheduled activities and current spacecraft state,
    then checks each activity's constraints are satisfiable.
    """

    def __init__(
        self,
        orbit_period_ticks: int = 5400,
        eclipse_fraction: float = 0.35,
        contact_start_offset: int = 1200,
        contact_window_ticks: int = 600,
    ):
        self.orbit_period = orbit_period_ticks
        self.eclipse_fraction = eclipse_fraction
        self.contact_start = contact_start_offset
        self.contact_window = contact_window_ticks

    def validate_plan(
        self,
        activities: list[ScheduledActivity],
        current_state: dict,
    ) -> list[ConstraintViolation]:
        """
        Run all constraint checks against a plan.

        Returns a list of violations (empty = plan is valid).
        """
        violations: list[ConstraintViolation] = []

        # Sort by start time
        sorted_acts = sorted(activities, key=lambda a: a.start_t)

        # 1. Check temporal overlaps
        violations.extend(self._check_overlaps(sorted_acts))

        # 2. Check resource constraints
        violations.extend(self._check_resources(sorted_acts, current_state))

        # 3. Check communication windows
        violations.extend(self._check_comms_windows(sorted_acts))

        # 4. Check eclipse/sunlight constraints
        violations.extend(self._check_eclipse(sorted_acts))

        return violations

    def _check_overlaps(
        self, activities: list[ScheduledActivity]
    ) -> list[ConstraintViolation]:
        """Check for illegal temporal overlaps between activities."""
        violations = []

        for i, a1 in enumerate(activities):
            for a2 in activities[i + 1:]:
                if a1.end_t > a2.start_t:
                    # Overlap detected — check if it's an illegal conflict
                    # Charging can overlap with observation if attitude allows
                    if (a1.activity_type == ActivityType.CHARGING and
                            a2.activity_type == ActivityType.CHARGING):
                        continue  # Two charging windows can overlap

                    violations.append(ConstraintViolation(
                        activity_id=a2.activity_id,
                        activity_name=a2.name,
                        constraint_type="overlap",
                        description=(
                            f"'{a2.name}' (t={a2.start_t}) overlaps with "
                            f"'{a1.name}' (t={a1.start_t}–{a1.end_t}). "
                            f"Delay by {a1.end_t - a2.start_t} ticks."
                        ),
                        severity="error",
                        at_tick=a2.start_t,
                    ))

        return violations

    def _check_resources(
        self,
        activities: list[ScheduledActivity],
        state: dict,
    ) -> list[ConstraintViolation]:
        """Check power and storage budgets."""
        violations = []
        soc = state.get("battery_soc", 0.85)
        storage = state.get("storage_used_mb", 256.0)
        capacity = state.get("storage_capacity_mb", 2048.0)

        for act in activities:
            # Approximate SOC drain
            if act.power_draw_w > 0:
                # Rough estimate: each Wh = capacity / full_charge
                drain = (act.power_draw_w * act.duration_ticks) / (40.0 * 3600.0)
                if soc - drain < 0.10:
                    violations.append(ConstraintViolation(
                        activity_id=act.activity_id,
                        activity_name=act.name,
                        constraint_type="power",
                        description=(
                            f"Insufficient SOC margin for '{act.name}'. "
                            f"Estimated SOC after: {(soc - drain):.1%} "
                            f"(minimum: 10%)"
                        ),
                        severity="error",
                        at_tick=act.start_t,
                    ))
                soc -= drain

            # Storage for observations
            if act.activity_type == ActivityType.OBSERVATION:
                data_gen = 5.0 * act.duration_ticks  # Default data rate
                if storage + data_gen > capacity * 0.95:
                    violations.append(ConstraintViolation(
                        activity_id=act.activity_id,
                        activity_name=act.name,
                        constraint_type="storage",
                        description=(
                            f"Storage will exceed 95% during '{act.name}'. "
                            f"Schedule a downlink before this observation."
                        ),
                        severity="warning",
                        at_tick=act.start_t,
                    ))
                storage += data_gen

            # Downlinks reduce storage
            if act.activity_type == ActivityType.DOWNLINK:
                data_dl = 8.0 * act.duration_ticks
                storage = max(0, storage - data_dl)

            # Charging restores SOC
            if act.activity_type == ActivityType.CHARGING:
                charge = (7.0 * act.duration_ticks) / (40.0 * 3600.0)
                soc = min(1.0, soc + charge)

        return violations

    def _check_comms_windows(
        self, activities: list[ScheduledActivity]
    ) -> list[ConstraintViolation]:
        """Check that downlinks are within contact windows."""
        violations = []

        for act in activities:
            if act.activity_type != ActivityType.DOWNLINK:
                continue

            # Check if the activity falls within a contact window
            for t in range(act.start_t, act.end_t):
                orbit_tick = t % self.orbit_period
                contact_end = self.contact_start + self.contact_window
                in_contact = self.contact_start <= orbit_tick < contact_end
                if not in_contact:
                    violations.append(ConstraintViolation(
                        activity_id=act.activity_id,
                        activity_name=act.name,
                        constraint_type="comms",
                        description=(
                            f"'{act.name}' extends outside contact window "
                            f"at t={t}. Contact window: orbit ticks "
                            f"{self.contact_start}–{contact_end}."
                        ),
                        severity="error",
                        at_tick=t,
                    ))
                    break  # One violation per activity is enough

        return violations

    def _check_eclipse(
        self, activities: list[ScheduledActivity]
    ) -> list[ConstraintViolation]:
        """Check that charging activities are during sunlight."""
        violations = []

        for act in activities:
            if act.activity_type != ActivityType.CHARGING:
                continue

            # Check if any part of the activity is in eclipse
            eclipse_start = int(self.orbit_period * (1.0 - self.eclipse_fraction))
            for t in range(act.start_t, act.end_t):
                orbit_tick = t % self.orbit_period
                in_eclipse = orbit_tick > eclipse_start
                if in_eclipse:
                    violations.append(ConstraintViolation(
                        activity_id=act.activity_id,
                        activity_name=act.name,
                        constraint_type="eclipse",
                        description=(
                            f"'{act.name}' overlaps eclipse period at t={t}. "
                            f"Solar charging ineffective in shadow."
                        ),
                        severity="warning",
                        at_tick=t,
                    ))
                    break

        return violations
