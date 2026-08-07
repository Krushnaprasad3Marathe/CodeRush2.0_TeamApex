"""
Aegis MOS — Mission Scheduler (F5).

Graph-based workflow scheduler that produces a conflict-free daily plan
for observations, downlinks, and solar charging. Each scheduling decision
node is inspectable and produces a human-readable explanation.

The scheduler is implemented as a step-wise state machine rather than
requiring the full LangGraph dependency — this gives us the same
inspectable, explainable node-by-node workflow without the heavy dep.

Workflow nodes:
  assess_resources → schedule_charging → schedule_observations →
  schedule_downlinks → resolve_conflicts → finalize
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from planner.activities import (
    ActivityType,
    ActivityStatus,
    ScheduledActivity,
    Observation,
    Downlink,
    SolarCharging,
)
from planner.constraints import ConstraintChecker, ConstraintViolation

logger = logging.getLogger("aegis.scheduler")


class PlanDecision:
    """A single decision made by a scheduler node."""

    def __init__(
        self,
        node_name: str,
        decision_type: str,
        activity_type: str | None = None,
        explanation: str = "",
        input_state: dict | None = None,
        output_state: dict | None = None,
    ):
        self.decision_id = f"DEC-{uuid.uuid4().hex[:8].upper()}"
        self.node_name = node_name
        self.decision_type = decision_type
        self.activity_type = activity_type
        self.explanation = explanation
        self.input_state = input_state or {}
        self.output_state = output_state or {}

    def to_dict(self) -> dict:
        return {
            "decision_id": self.decision_id,
            "node_name": self.node_name,
            "decision_type": self.decision_type,
            "activity_type": self.activity_type,
            "explanation": self.explanation,
            "input_state": self.input_state,
            "output_state": self.output_state,
        }


class MissionScheduler:
    """
    Step-wise mission scheduler.

    Generates a daily plan by running through a sequence of scheduling
    nodes, each producing one or more ScheduledActivities and PlanDecisions.
    """

    def __init__(self, suspect_streams: set[str] | None = None):
        self.constraint_checker = ConstraintChecker()
        self.suspect_streams = suspect_streams or set()
        self._activities: list[ScheduledActivity] = []
        self._decisions: list[PlanDecision] = []
        self._violations: list[ConstraintViolation] = []

    @property
    def activities(self) -> list[ScheduledActivity]:
        return list(self._activities)

    @property
    def decisions(self) -> list[PlanDecision]:
        return list(self._decisions)

    @property
    def violations(self) -> list[ConstraintViolation]:
        return list(self._violations)

    def generate_plan(
        self,
        current_state: dict,
        mission_day_ticks: int = 86400,
    ) -> dict:
        """
        Generate a full daily plan.

        Runs through all scheduler nodes sequentially.
        Returns the plan as a dict with activities, decisions, and violations.
        """
        self._activities.clear()
        self._decisions.clear()
        self._violations.clear()

        # Node 1: Assess resources
        self._assess_resources(current_state)

        # Node 2: Schedule charging windows
        self._schedule_charging(current_state, mission_day_ticks)

        # Node 3: Schedule observations
        self._schedule_observations(current_state, mission_day_ticks)

        # Node 4: Schedule downlinks
        self._schedule_downlinks(current_state, mission_day_ticks)

        # Node 5: Resolve conflicts
        self._resolve_conflicts(current_state)

        # Node 6: Finalize
        self._finalize(current_state)

        return {
            "activities": [a.to_dict() for a in self._activities],
            "decisions": [d.to_dict() for d in self._decisions],
            "violations": [v.to_dict() for v in self._violations],
            "total_activities": len(self._activities),
            "constraint_violations": len(self._violations),
        }

    def _assess_resources(self, state: dict):
        """Node 1: Assess current resources and determine priorities."""
        soc = state.get("battery_soc", 0.85)
        storage_pct = state.get("storage_used_mb", 256) / state.get("storage_capacity_mb", 2048)

        # Check for suspect streams
        warnings = []
        if self.suspect_streams:
            for stream in self.suspect_streams:
                warnings.append(
                    f"⚠ Data stream '{stream}' marked suspect — "
                    f"scheduling around it with caution"
                )

        priorities = {
            "charging_urgent": soc < 0.30,
            "storage_full": storage_pct > 0.80,
            "storage_low": storage_pct < 0.20,
        }

        explanation = (
            f"Resource assessment: SOC={soc:.0%}, Storage={storage_pct:.0%}. "
        )
        if priorities["charging_urgent"]:
            explanation += "URGENT: Battery below 30%, prioritizing charging. "
        if priorities["storage_full"]:
            explanation += "Storage above 80%, prioritizing downlink. "
        if warnings:
            explanation += " | ".join(warnings)

        self._decisions.append(PlanDecision(
            node_name="assess_resources",
            decision_type="assessment",
            explanation=explanation,
            input_state={"soc": soc, "storage_pct": storage_pct},
            output_state={"priorities": priorities},
        ))

    def _schedule_charging(self, state: dict, day_ticks: int):
        """Node 2: Schedule solar charging windows."""
        soc = state.get("battery_soc", 0.85)
        current_t = state.get("t", 0)
        orbit_period = 5400

        # Schedule charging at the start of each sunlit period
        charge_windows = []
        t = current_t
        while t < current_t + day_ticks:
            orbit_tick = t % orbit_period
            eclipse_start = int(orbit_period * 0.65)

            # If SOC is low, schedule a charging session at the next sunlit window
            if soc < 0.70:
                # Find next sunlit window start
                if orbit_tick >= eclipse_start:
                    # Currently in eclipse — wait for next orbit's sunlit
                    next_sun = t + (orbit_period - orbit_tick)
                else:
                    next_sun = t

                duration = min(1800, eclipse_start - (next_sun % orbit_period))
                if duration > 300:
                    act_id = f"ACT-{uuid.uuid4().hex[:8].upper()}"
                    activity = ScheduledActivity(
                        activity_id=act_id,
                        activity_type=ActivityType.CHARGING,
                        name="Solar Charging",
                        description=f"Recharge battery from {soc:.0%}",
                        start_t=next_sun,
                        end_t=next_sun + duration,
                        duration_ticks=duration,
                        priority=8 if soc < 0.30 else 6,
                        status=ActivityStatus.SCHEDULED,
                        requires_sunlight=True,
                        explanation=f"Battery at {soc:.0%}, charging for {duration}s to restore capacity.",
                    )
                    self._activities.append(activity)
                    charge_windows.append(activity)

                    self._decisions.append(PlanDecision(
                        node_name="schedule_charging",
                        decision_type="schedule",
                        activity_type="charging",
                        explanation=f"Scheduled charging at t={next_sun} for {duration} ticks (SOC={soc:.0%}).",
                        input_state={"soc": soc, "t": t},
                        output_state={"activity_id": act_id},
                    ))

                    # Estimate SOC recovery
                    soc = min(1.0, soc + (7.0 * duration) / (40.0 * 3600.0))

            t += orbit_period  # Move to next orbit

    def _schedule_observations(self, state: dict, day_ticks: int):
        """Node 3: Schedule observation windows."""
        current_t = state.get("t", 0)
        orbit_period = 5400
        storage = state.get("storage_used_mb", 256)
        capacity = state.get("storage_capacity_mb", 2048)

        # Schedule 3-4 observations per day
        obs_targets = [
            ("Crater-Alpha Imaging", 45.0, 300),
            ("Polar Ice Survey", 30.0, 250),
            ("Surface Mapping", 60.0, 200),
            ("Spectrometry Scan", 20.0, 180),
        ]

        t = current_t + 300  # Start 5 min from now
        for i, (target, attitude, duration) in enumerate(obs_targets):
            if storage + (5.0 * duration) > capacity * 0.90:
                self._decisions.append(PlanDecision(
                    node_name="schedule_observations",
                    decision_type="reject",
                    activity_type="observation",
                    explanation=f"Observation '{target}' rejected: storage would exceed 90% ({storage:.0f}/{capacity:.0f}MB).",
                    input_state={"storage_mb": storage, "capacity_mb": capacity},
                ))
                continue

            # Check for conflicts with existing activities
            conflict = self._check_time_conflict(t, t + duration)
            if conflict:
                # Delay past the conflict
                t = conflict.end_t + 60
                self._decisions.append(PlanDecision(
                    node_name="schedule_observations",
                    decision_type="delay",
                    activity_type="observation",
                    explanation=f"Observation '{target}' delayed to t={t}: conflict with '{conflict.name}'.",
                ))

            act_id = f"ACT-{uuid.uuid4().hex[:8].upper()}"
            activity = ScheduledActivity(
                activity_id=act_id,
                activity_type=ActivityType.OBSERVATION,
                name=target,
                description=f"Observation target at {attitude}° attitude",
                start_t=t,
                end_t=t + duration,
                duration_ticks=duration,
                priority=7,
                status=ActivityStatus.SCHEDULED,
                power_draw_w=1.5,
                required_attitude_deg=attitude,
                explanation=f"Science observation of {target} for {duration}s.",
            )
            self._activities.append(activity)

            self._decisions.append(PlanDecision(
                node_name="schedule_observations",
                decision_type="schedule",
                activity_type="observation",
                explanation=f"Scheduled '{target}' at t={t} for {duration} ticks.",
                input_state={"t": t, "storage_mb": storage},
                output_state={"activity_id": act_id, "data_generated_mb": 5.0 * duration},
            ))

            storage += 5.0 * duration
            t += duration + 300  # Gap between observations

    def _schedule_downlinks(self, state: dict, day_ticks: int):
        """Node 4: Schedule downlinks during contact windows."""
        current_t = state.get("t", 0)
        orbit_period = 5400
        contact_start = 1200
        contact_window = 600

        # Schedule a downlink in each available contact window
        t = current_t
        dl_count = 0
        while t < current_t + day_ticks and dl_count < 4:
            orbit_tick = t % orbit_period
            # Find next contact window
            if orbit_tick < contact_start:
                next_contact = t + (contact_start - orbit_tick)
            elif orbit_tick < contact_start + contact_window:
                next_contact = t  # Currently in window
            else:
                next_contact = t + (orbit_period - orbit_tick) + contact_start

            # Check for conflicts
            dl_end = next_contact + contact_window
            conflict = self._check_time_conflict(next_contact, dl_end)
            if conflict:
                self._decisions.append(PlanDecision(
                    node_name="schedule_downlinks",
                    decision_type="delay",
                    activity_type="downlink",
                    explanation=f"Downlink delayed: conflict with '{conflict.name}' during contact window.",
                ))
                t = next_contact + orbit_period
                continue

            act_id = f"ACT-{uuid.uuid4().hex[:8].upper()}"
            activity = ScheduledActivity(
                activity_id=act_id,
                activity_type=ActivityType.DOWNLINK,
                name=f"Downlink Pass #{dl_count + 1}",
                description="Data transfer to ground station",
                start_t=next_contact,
                end_t=dl_end,
                duration_ticks=contact_window,
                priority=8,
                status=ActivityStatus.SCHEDULED,
                power_draw_w=3.5,
                requires_contact=True,
                explanation=f"Downlink during ground pass at t={next_contact}.",
            )
            self._activities.append(activity)

            self._decisions.append(PlanDecision(
                node_name="schedule_downlinks",
                decision_type="schedule",
                activity_type="downlink",
                explanation=f"Scheduled downlink pass #{dl_count + 1} at t={next_contact}.",
                input_state={"contact_start": next_contact},
                output_state={"activity_id": act_id},
            ))

            dl_count += 1
            t = next_contact + orbit_period

    def _resolve_conflicts(self, state: dict):
        """Node 5: Detect and resolve any remaining conflicts."""
        violations = self.constraint_checker.validate_plan(self._activities, state)
        self._violations = violations

        if violations:
            # Attempt automatic resolution for overlaps
            for v in violations:
                if v.constraint_type == "overlap":
                    # Find the conflicting activity and try to reschedule
                    for act in self._activities:
                        if act.activity_id == v.activity_id:
                            # Shift it forward
                            old_start = act.start_t
                            act.start_t = act.end_t + 60
                            act.end_t = act.start_t + act.duration_ticks

                            self._decisions.append(PlanDecision(
                                node_name="resolve_conflicts",
                                decision_type="reschedule",
                                activity_type=act.activity_type.value,
                                explanation=(
                                    f"Rescheduled '{act.name}' from t={old_start} "
                                    f"to t={act.start_t} to resolve overlap."
                                ),
                            ))
                            break

            # Re-validate after resolution
            self._violations = self.constraint_checker.validate_plan(
                self._activities, state
            )

        conflict_text = (
            f"{len(self._violations)} remaining constraint violation(s)"
            if self._violations
            else "All constraints satisfied"
        )
        self._decisions.append(PlanDecision(
            node_name="resolve_conflicts",
            decision_type="validation",
            explanation=f"Conflict resolution complete. {conflict_text}.",
            output_state={"violations": len(self._violations)},
        ))

    def _finalize(self, state: dict):
        """Node 6: Finalize the plan and sort activities."""
        self._activities.sort(key=lambda a: a.start_t)

        self._decisions.append(PlanDecision(
            node_name="finalize",
            decision_type="complete",
            explanation=(
                f"Plan finalized with {len(self._activities)} activities. "
                f"{len(self._violations)} constraint violations remaining."
            ),
            output_state={
                "total_activities": len(self._activities),
                "total_violations": len(self._violations),
            },
        ))

        logger.info(
            "Plan generated: %d activities, %d violations",
            len(self._activities),
            len(self._violations),
        )

    def _check_time_conflict(
        self, start_t: int, end_t: int
    ) -> ScheduledActivity | None:
        """Check if a time range conflicts with any existing activity."""
        for act in self._activities:
            if start_t < act.end_t and end_t > act.start_t:
                return act
        return None

    def get_decision(self, decision_id: str) -> PlanDecision | None:
        """Retrieve a specific decision by ID."""
        for d in self._decisions:
            if d.decision_id == decision_id:
                return d
        return None
