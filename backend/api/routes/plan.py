"""
Aegis MOS / Space Aegis — Mission Planner API routes (F5).

Endpoints:
  GET  /plan                       — Current schedule
  POST /plan/generate              — Generate a new plan via LangGraph StateGraph
  GET  /plan/explain/{decision_id} — Human-readable reasoning for a decision
  GET  /plan/validate              — Run constraint checker against current plan
  GET  /plan/decisions             — All scheduling decisions
"""

from fastapi import APIRouter, Request

from planner.graph import MissionPlannerGraph

router = APIRouter(prefix="/plan", tags=["planner"])

# Module-level planner graph instance
_planner_graph: MissionPlannerGraph | None = None


def _get_graph(request: Request) -> MissionPlannerGraph:
    """Get or create the MissionPlannerGraph instance."""
    global _planner_graph
    if _planner_graph is None:
        sim = request.app.state.simulator
        suspect = sim.anomaly_detector.suspect_streams
        _planner_graph = MissionPlannerGraph(suspect_streams=suspect)
    return _planner_graph


@router.get("/")
async def get_plan(request: Request):
    """Return the current mission schedule."""
    planner = _get_graph(request)
    sim = request.app.state.simulator
    if not planner.activities:
        # Automatically generate initial plan on startup
        plan = await planner.run(sim.state.model_dump())
        sim.state.scheduled_activities = plan.get("activities", [])

    return {
        "activities": planner.activities,
        "decisions": planner.decisions,
        "violations": planner.violations,
        "total_activities": len(planner.activities),
        "constraint_violations": len(planner.violations),
    }


@router.post("/generate")
async def generate_plan(request: Request):
    """Generate a new mission plan based on current spacecraft state using LangGraph."""
    global _planner_graph
    sim = request.app.state.simulator

    # Create fresh planner graph with current suspect streams
    suspect = sim.anomaly_detector.suspect_streams
    _planner_graph = MissionPlannerGraph(suspect_streams=suspect)

    # Generate plan via StateGraph
    state_dict = sim.state.model_dump()
    plan = await _planner_graph.run(state_dict)

    # Update simulator state with scheduled activities
    sim.state.scheduled_activities = plan.get("activities", [])

    # Try AI-enriched explanations for key decisions
    try:
        from ai.gemini_client import explain_scheduling_decision
        for decision in _planner_graph.decisions:
            if decision.get("decision_type") in ("reject", "delay", "reschedule", "suspect_warning"):
                ai_explanation = await explain_scheduling_decision(decision)
                if ai_explanation:
                    decision["explanation"] = ai_explanation
    except Exception:
        pass  # Fallback explanations already in place

    return plan


@router.get("/priority-check")
async def priority_check(request: Request):
    """Flags mis-prioritized activities with recommendations based on priority_dataset.json."""
    planner = _get_graph(request)
    sim = request.app.state.simulator
    state_dict = sim.state.model_dump()
    alerts = sim.anomaly_detector.get_alerts_summary()

    from planner.priority_advisor import PriorityAdvisor
    advisor = PriorityAdvisor()
    mismatches = advisor.evaluate(planner.activities, state_dict, alerts)

    return {
        "status": "ok",
        "total_activities": len(planner.activities),
        "total_mismatches": len(mismatches),
        "critical_mismatches": sum(1 for m in mismatches if m.severity == "critical"),
        "mismatches": [m.to_dict() for m in mismatches],
    }


@router.post("/apply-priorities")
async def apply_priorities(request: Request):
    """Adopt recommended priority levels across all activities in the current plan."""
    planner = _get_graph(request)
    sim = request.app.state.simulator
    state_dict = sim.state.model_dump()
    alerts = sim.anomaly_detector.get_alerts_summary()

    from planner.priority_advisor import PriorityAdvisor
    advisor = PriorityAdvisor()
    mismatches = advisor.evaluate(planner.activities, state_dict, alerts)
    mismatch_map = {m.activity_id: m.recommended_priority for m in mismatches}

    applied_count = 0
    for act in planner.activities:
        act_id = act.get("activity_id") if isinstance(act, dict) else getattr(act, "activity_id", None)
        if act_id in mismatch_map:
            if isinstance(act, dict):
                act["priority"] = mismatch_map[act_id]
            else:
                setattr(act, "priority", mismatch_map[act_id])
            applied_count += 1

    sim.state.scheduled_activities = planner.activities

    return {
        "status": "applied",
        "applied_count": applied_count,
        "activities": planner.activities,
        "decisions": planner.decisions,
        "violations": planner.violations,
    }


@router.get("/explain/{decision_id}")
async def explain_decision(request: Request, decision_id: str):
    """Return human-readable reasoning for a scheduling decision."""
    planner = _get_graph(request)
    decision = planner.get_decision(decision_id)

    if decision is None:
        return {
            "status": "error",
            "decision_id": decision_id,
            "message": "Decision not found",
        }

    # Try AI-enriched explanation
    ai_explanation = None
    try:
        from ai.gemini_client import explain_scheduling_decision
        ai_explanation = await explain_scheduling_decision(decision)
    except Exception:
        pass

    return {
        "decision": decision,
        "ai_explanation": ai_explanation or decision.get("explanation"),
    }


@router.get("/validate")
async def validate_plan(request: Request):
    """Run the constraint checker against the current plan."""
    planner = _get_graph(request)
    sim = request.app.state.simulator

    if not planner.activities:
        return {"status": "empty", "message": "No plan to validate"}

    from planner.constraints import ConstraintChecker
    checker = ConstraintChecker()
    violations = checker.validate_plan(
        planner.activities,
        sim.state.model_dump(),
    )

    return {
        "valid": len(violations) == 0,
        "violations": [v.to_dict() if hasattr(v, "to_dict") else v for v in violations],
        "total_violations": len(violations),
    }


@router.get("/decisions")
async def list_decisions(request: Request):
    """Return all scheduling decisions for inspection."""
    planner = _get_graph(request)
    return {
        "decisions": planner.decisions,
        "total": len(planner.decisions),
    }
