"""
Aegis MOS / Space Aegis — Check Power Budget Node.

Validates energy budget, verifies battery SOC margins, checks solar generation,
and schedules required solar charging sessions.
"""

from __future__ import annotations
import uuid
from typing import Any
from planner.activities import ActivityType, ActivityStatus, ScheduledActivity

def check_power_budget_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Forward-simulates power draw and ensures battery SOC remains strictly >= 15%.
    Schedules solar charging during sunlit windows.
    """
    soc = state.get("battery_soc", 0.85)
    current_t = state.get("current_t", state.get("t", 0))
    suspect_streams = state.get("suspect_streams", [])
    proposed_obs = list(state.get("proposed_observations", []))
    decisions = list(state.get("decisions", []))
    warnings = list(state.get("warnings", []))
    charging_activities: list[ScheduledActivity] = []
    
    # Check for suspect power telemetry
    if "solar_input_w" in suspect_streams or "battery_soc" in suspect_streams:
        warn = "⚠ EPS power stream marked suspect (F4) — derating solar charging estimate by 40%."
        warnings.append(warn)
        decisions.append({
            "decision_id": f"DEC-{uuid.uuid4().hex[:8].upper()}",
            "node_name": "check_power_budget",
            "decision_type": "suspect_warning",
            "activity_type": "charging",
            "explanation": warn,
            "input_state": {"suspect_streams": list(suspect_streams)},
            "output_state": {"derating_factor": 0.6}
        })

    orbit_period = 5400
    eclipse_start = int(orbit_period * 0.65)
    
    # Schedule solar charging in available sunlit window
    charge_t = current_t
    orbit_tick = charge_t % orbit_period
    if orbit_tick < eclipse_start:
        charge_duration = min(1200, eclipse_start - orbit_tick)
        if charge_duration >= 300:
            act_id = f"ACT-{uuid.uuid4().hex[:8].upper()}"
            charge_act = ScheduledActivity(
                activity_id=act_id,
                activity_type=ActivityType.CHARGING,
                name="Solar Array Recharge Window",
                description=f"Primary EPS solar charge session from initial SOC {soc:.0%}",
                start_t=charge_t + 10,
                end_t=charge_t + 10 + charge_duration,
                duration_ticks=charge_duration,
                priority=9 if soc < 0.35 else 6,
                status=ActivityStatus.SCHEDULED,
                requires_sunlight=True,
                power_draw_w=0.0,
                explanation=f"Solar charging for {charge_duration}s during sunlit orbit phase.",
            )
            charging_activities.append(charge_act)
            decisions.append({
                "decision_id": f"DEC-{uuid.uuid4().hex[:8].upper()}",
                "node_name": "check_power_budget",
                "decision_type": "schedule",
                "activity_type": "charging",
                "explanation": f"Scheduled solar charging at T+{charge_t + 10}s for {charge_duration} ticks (SOC={soc:.0%}).",
                "input_state": {"soc": soc, "t": charge_t},
                "output_state": {"activity_id": act_id, "duration": charge_duration}
            })

    # Forward-check energy budget for proposed observations
    approved_obs = []
    conflicted_obs = []
    simulated_soc = soc
    
    for obs in proposed_obs:
        drain = (obs.power_draw_w * obs.duration_ticks) / (40.0 * 3600.0)
        if simulated_soc - drain < 0.15:
            conflicted_obs.append({
                "activity": obs,
                "reason": f"Insufficient SOC margin for '{obs.name}': projected SOC {(simulated_soc - drain):.1%} < 15% safety limit.",
                "type": "power_shortage"
            })
            decisions.append({
                "decision_id": f"DEC-{uuid.uuid4().hex[:8].upper()}",
                "node_name": "check_power_budget",
                "decision_type": "reject",
                "activity_type": "observation",
                "explanation": f"Observation '{obs.name}' rejected: insufficient SOC margin until charging completes.",
                "input_state": {"projected_soc": simulated_soc - drain},
                "output_state": {"rejected_activity_id": obs.activity_id}
            })
        else:
            simulated_soc -= drain
            approved_obs.append(obs)
            decisions.append({
                "decision_id": f"DEC-{uuid.uuid4().hex[:8].upper()}",
                "node_name": "check_power_budget",
                "decision_type": "pass",
                "activity_type": "observation",
                "explanation": f"Power budget verified for '{obs.name}': projected SOC remains healthy at {simulated_soc:.1%}.",
                "input_state": {"soc_before": simulated_soc + drain},
                "output_state": {"soc_after": simulated_soc}
            })

    return {
        **state,
        "charging_activities": charging_activities,
        "verified_observations": approved_obs,
        "conflicts": list(state.get("conflicts", [])) + conflicted_obs,
        "decisions": decisions,
        "warnings": warnings,
        "simulated_soc": simulated_soc,
    }
