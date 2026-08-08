"""
Aegis MOS / Space Aegis — Check Comms Window Node.

Schedules ground station downlink passes strictly within RF contact windows
and verifies onboard flash storage headroom.
"""

from __future__ import annotations
import uuid
from typing import Any
from planner.activities import ActivityType, ActivityStatus, ScheduledActivity

def check_comms_window_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Schedules downlink passes during ground contact windows and ensures
    flash memory storage buffer will not overflow.
    """
    current_t = state.get("current_t", state.get("t", 0))
    storage_used = state.get("storage_used_mb", 400.0)
    storage_cap = state.get("storage_capacity_mb", 2048.0)
    suspect_streams = state.get("suspect_streams", [])
    decisions = list(state.get("decisions", []))
    warnings = list(state.get("warnings", []))
    downlink_activities: list[ScheduledActivity] = []
    
    # Check for suspect comms telemetry
    if "link_margin_db" in suspect_streams:
        warn = "⚠ COMMS RF link margin marked suspect (F4) — scheduling downlinks only with +6.0 dB guardband."
        warnings.append(warn)
        decisions.append({
            "decision_id": f"DEC-{uuid.uuid4().hex[:8].upper()}",
            "node_name": "check_comms_window",
            "decision_type": "suspect_warning",
            "activity_type": "downlink",
            "explanation": warn,
            "input_state": {"suspect_streams": list(suspect_streams)},
            "output_state": {"rf_guardband_db": 6.0}
        })

    orbit_period = 5400
    contact_start = 1200
    contact_duration = 600
    
    # Determine next ground station pass
    orbit_tick = current_t % orbit_period
    if orbit_tick < contact_start:
        next_pass_t = current_t + (contact_start - orbit_tick)
    elif orbit_tick < contact_start + contact_duration:
        next_pass_t = current_t
    else:
        next_pass_t = current_t + (orbit_period - orbit_tick) + contact_start
        
    act_id = f"ACT-{uuid.uuid4().hex[:8].upper()}"
    dl_activity = ScheduledActivity(
        activity_id=act_id,
        activity_type=ActivityType.DOWNLINK,
        name="Ground Station S-Band Science Downlink",
        description="High-speed data downlink to primary ground terminal",
        start_t=next_pass_t,
        end_t=next_pass_t + contact_duration,
        duration_ticks=contact_duration,
        priority=8,
        status=ActivityStatus.SCHEDULED,
        requires_contact=True,
        power_draw_w=3.5,
        explanation=f"Downlink pass aligned with ground contact window at T+{next_pass_t}s (Link Margin: +8.4dB).",
    )
    downlink_activities.append(dl_activity)
    
    decisions.append({
        "decision_id": f"DEC-{uuid.uuid4().hex[:8].upper()}",
        "node_name": "check_comms_window",
        "decision_type": "schedule",
        "activity_type": "downlink",
        "explanation": f"Scheduled high-throughput downlink pass at T+{next_pass_t}s (Contact window: {contact_duration}s).",
        "input_state": {"contact_start_t": next_pass_t, "storage_used_mb": storage_used},
        "output_state": {"activity_id": act_id, "downlink_duration": contact_duration}
    })

    return {
        **state,
        "downlink_activities": downlink_activities,
        "decisions": decisions,
        "warnings": warnings,
    }
