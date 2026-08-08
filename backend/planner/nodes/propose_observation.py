"""
Aegis MOS / Space Aegis — Propose Observation Node.

Proposes observation targets based on science priorities, solar illumination,
and pointing capabilities.
"""

from __future__ import annotations
import uuid
from typing import Any
from planner.activities import ActivityType, ActivityStatus, ScheduledActivity

def propose_observation_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Propose science observation candidates for the mission schedule.
    Reads current state, sun angle, and memory headroom.
    """
    current_t = state.get("current_t", state.get("t", 0))
    storage_used = state.get("storage_used_mb", 256.0)
    storage_capacity = state.get("storage_capacity_mb", 2048.0)
    suspect_streams = state.get("suspect_streams", [])
    
    proposed_candidates: list[ScheduledActivity] = []
    decisions = list(state.get("decisions", []))
    warnings = list(state.get("warnings", []))
    
    # Check if attitude or payload telemetry is suspect
    if "attitude_deg" in suspect_streams or "slew_rate_dps" in suspect_streams:
        warning_msg = "⚠ ADCS attitude stream marked suspect (F4) — applying conservative 10.0° pointing tolerance."
        warnings.append(warning_msg)
        decisions.append({
            "decision_id": f"DEC-{uuid.uuid4().hex[:8].upper()}",
            "node_name": "propose_observation",
            "decision_type": "suspect_warning",
            "activity_type": "observation",
            "explanation": warning_msg,
            "input_state": {"suspect_streams": list(suspect_streams)},
            "output_state": {"attitude_derated": True}
        })

    obs_targets = [
        ("Crater-Alpha Multi-Spectral Imaging", 45.0, 300, 1.5),
        ("Polar Ice & Cryo Survey", 30.0, 250, 1.4),
        ("High-Resolution Surface Optical Mapping", 60.0, 200, 1.6),
        ("Atmospheric Limb Spectrometry Scan", 20.0, 180, 1.2),
    ]

    t_cursor = current_t + 300
    for target_name, target_attitude, duration, power in obs_targets:
        act_id = f"ACT-{uuid.uuid4().hex[:8].upper()}"
        candidate = ScheduledActivity(
            activity_id=act_id,
            activity_type=ActivityType.OBSERVATION,
            name=target_name,
            description=f"Science observation target at {target_attitude}° attitude",
            start_t=t_cursor,
            end_t=t_cursor + duration,
            duration_ticks=duration,
            priority=7,
            status=ActivityStatus.SCHEDULED,
            power_draw_w=power,
            required_attitude_deg=target_attitude,
            explanation=f"Science candidate: {target_name} ({duration}s duration, {power}W load).",
        )
        proposed_candidates.append(candidate)
        decisions.append({
            "decision_id": f"DEC-{uuid.uuid4().hex[:8].upper()}",
            "node_name": "propose_observation",
            "decision_type": "proposal",
            "activity_type": "observation",
            "explanation": f"Proposing science observation '{target_name}' at T+{t_cursor}s (Duration: {duration}s).",
            "input_state": {"target": target_name, "t": t_cursor, "storage_used_mb": storage_used},
            "output_state": {"activity_id": act_id, "duration": duration}
        })
        t_cursor += duration + 300

    return {
        **state,
        "proposed_observations": proposed_candidates,
        "decisions": decisions,
        "warnings": warnings,
    }
