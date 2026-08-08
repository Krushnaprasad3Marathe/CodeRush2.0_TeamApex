"""
Aegis MOS / Space Aegis — Resolve Conflict Node.

Detects and resolves temporal collisions, power deficits, pointing conflicts,
and minimum inter-task buffer rules. Generates human-readable explanations for every decision.
"""

from __future__ import annotations
import uuid
from typing import Any
from planner.activities import ScheduledActivity, ActivityType
from planner.constraints import ConstraintChecker, ConstraintViolation

def resolve_conflict_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Validates candidates against hard constraints. Automatically reschedules
    overlapping activities and produces human-readable explanations.
    """
    checker = ConstraintChecker()
    raw_activities: list[ScheduledActivity] = []
    
    # Collect all proposed activities
    raw_activities.extend(state.get("charging_activities", []))
    raw_activities.extend(state.get("verified_observations", []))
    raw_activities.extend(state.get("downlink_activities", []))
    
    # Sort strictly by start time
    raw_activities.sort(key=lambda a: a.start_t)
    
    resolved_activities: list[ScheduledActivity] = []
    decisions = list(state.get("decisions", []))
    min_inter_task_buffer = 60  # 60s minimum guard time between major operations
    
    current_time_cursor = 0
    for act in raw_activities:
        # Check if start_t overlaps with preceding activity + buffer
        if resolved_activities:
            last_act = resolved_activities[-1]
            earliest_allowed = last_act.end_t + min_inter_task_buffer
            
            if act.start_t < earliest_allowed:
                delay_seconds = earliest_allowed - act.start_t
                delay_mins = max(1, delay_seconds // 60)
                old_start = act.start_t
                act.start_t = earliest_allowed
                act.end_t = act.start_t + act.duration_ticks
                
                explanation = (
                    f"Activity '{act.name}' delayed by {delay_mins} min (to T+{act.start_t}s): "
                    f"maintaining {min_inter_task_buffer}s inter-task buffer after '{last_act.name}'."
                )
                decisions.append({
                    "decision_id": f"DEC-{uuid.uuid4().hex[:8].upper()}",
                    "node_name": "resolve_conflict",
                    "decision_type": "delay",
                    "activity_type": act.activity_type.value if hasattr(act.activity_type, 'value') else str(act.activity_type),
                    "explanation": explanation,
                    "input_state": {"original_start_t": old_start, "conflict_with": last_act.name},
                    "output_state": {"new_start_t": act.start_t, "delay_seconds": delay_seconds}
                })
        
        resolved_activities.append(act)

    # Perform full forward constraint verification
    violations = checker.validate_plan(resolved_activities, state)
    
    decisions.append({
        "decision_id": f"DEC-{uuid.uuid4().hex[:8].upper()}",
        "node_name": "resolve_conflict",
        "decision_type": "validation",
        "activity_type": "all",
        "explanation": (
            f"Conflict resolution pass finished: {len(resolved_activities)} activities verified with "
            f"{len(violations)} remaining constraint violations."
        ),
        "input_state": {"total_candidates": len(raw_activities)},
        "output_state": {"resolved_count": len(resolved_activities), "violations_count": len(violations)}
    })

    return {
        **state,
        "resolved_activities": resolved_activities,
        "violations": violations,
        "decisions": decisions,
    }
