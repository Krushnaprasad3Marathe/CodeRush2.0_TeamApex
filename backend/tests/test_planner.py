"""
Tests for LangGraph Mission Planner & Constraint Engine (F5).

Verifies:
  1. No constraint violations across full simulated mission day.
  2. All 3 activity classes scheduled (observations, downlinks, solar charging).
  3. Every decision node produces human-readable explanations.
  4. Decisions are retrievable by decision_id for /plan/explain/{decision_id}.
  5. Suspect anomaly flags surface warnings and derating decisions.
"""

import pytest
import asyncio
from planner.graph import MissionPlannerGraph
from planner.constraints import ConstraintChecker
from planner.activities import ActivityType


@pytest.mark.asyncio
async def test_full_24h_plan_no_violations():
    """Verify that a full mission day plan has 0 hard constraint violations."""
    graph = MissionPlannerGraph()
    state = {
        "t": 140,
        "battery_soc": 0.85,
        "bus_voltage": 4.88,
        "solar_input_w": 7.2,
        "temp_c": 22.0,
        "storage_used_mb": 400.0,
        "storage_capacity_mb": 2048.0,
        "in_contact": False,
        "in_eclipse": False,
        "orbit_phase": 0.38,
        "suspect_streams": [],
    }

    result = await graph.run(state, mission_day_ticks=86400)

    activities = result.get("activities", [])
    violations = result.get("violations", [])

    assert len(activities) >= 3, "Must schedule at least 3 activities"
    assert len(violations) == 0, f"Expected 0 constraint violations, got {len(violations)}"

    # Check minimum 3 activity classes are present
    types_present = set()
    for act in activities:
        act_type = act.get("activity_type")
        types_present.add(act_type)

    assert "observation" in types_present, "Plan must include science observations"
    assert "downlink" in types_present, "Plan must include ground station downlinks"
    assert "charging" in types_present, "Plan must include solar battery charging"


@pytest.mark.asyncio
async def test_decision_reasoning_retrievable():
    """Verify that every decision node's reasoning is retrievable by decision_id."""
    graph = MissionPlannerGraph()
    state = {
        "t": 100,
        "battery_soc": 0.80,
        "storage_used_mb": 500.0,
        "storage_capacity_mb": 2048.0,
        "suspect_streams": [],
    }

    result = await graph.run(state)
    decisions = graph.decisions

    assert len(decisions) > 0, "Graph must produce scheduling decisions"

    for dec in decisions:
        dec_id = dec.get("decision_id")
        assert dec_id is not None, "Each decision must have a unique decision_id"
        assert dec_id.startswith("DEC-"), f"Decision ID must start with DEC-, got {dec_id}"

        # Retrieve via get_decision
        retrieved = graph.get_decision(dec_id)
        assert retrieved is not None, f"Decision {dec_id} must be retrievable"
        assert len(retrieved.get("explanation", "")) > 0, f"Decision {dec_id} must have human-readable explanation"


@pytest.mark.asyncio
async def test_suspect_stream_warning():
    """Verify that suspect anomaly streams surface warnings and adaptive decisions."""
    graph = MissionPlannerGraph(suspect_streams={"solar_input_w", "attitude_deg"})
    state = {
        "t": 200,
        "battery_soc": 0.40,
        "storage_used_mb": 600.0,
        "storage_capacity_mb": 2048.0,
    }

    result = await graph.run(state)
    warnings = result.get("warnings", [])
    decisions = graph.decisions

    assert len(warnings) > 0, "Must surface warnings when suspect streams are present"
    assert any("suspect" in d.get("decision_type", "") for d in decisions), "Must log suspect warning decisions"


def test_constraint_checker_overlap_prevention():
    """Verify ConstraintChecker catches and flags illegal temporal overlaps."""
    checker = ConstraintChecker()
    from planner.activities import ScheduledActivity, ActivityStatus

    act1 = ScheduledActivity(
        activity_id="ACT-001",
        activity_type=ActivityType.OBSERVATION,
        name="Imaging Pass",
        description="Test",
        start_t=100,
        end_t=300,
        duration_ticks=200,
        priority=7,
        status=ActivityStatus.SCHEDULED,
        power_draw_w=2.0,
    )
    act2 = ScheduledActivity(
        activity_id="ACT-002",
        activity_type=ActivityType.DOWNLINK,
        name="Downlink Pass",
        description="Test",
        start_t=250,  # Overlaps with act1 (100 to 300)
        end_t=450,
        duration_ticks=200,
        priority=8,
        status=ActivityStatus.SCHEDULED,
        power_draw_w=3.5,
    )

    violations = checker.validate_plan([act1, act2], {"battery_soc": 0.85, "storage_used_mb": 400})
    overlap_violations = [v for v in violations if v.constraint_type == "overlap"]

    assert len(overlap_violations) > 0, "Checker must flag illegal activity overlaps"
