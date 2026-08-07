"""
Aegis MOS — Mission planner API routes (F5).

Endpoints:
  GET  /plan                       — Current schedule
  POST /plan/generate              — Generate a new plan
  GET  /plan/explain/{decision_id} — Human-readable reasoning for a decision
  GET  /plan/validate              — Run constraint checker against current plan
  GET  /plan/decisions             — All scheduling decisions
"""

from fastapi import APIRouter, Request

from planner.scheduler import MissionScheduler

router = APIRouter(prefix="/plan", tags=["planner"])

# Module-level scheduler instance
_scheduler: MissionScheduler | None = None


def _get_scheduler(request: Request) -> MissionScheduler:
    """Get or create the scheduler instance."""
    global _scheduler
    if _scheduler is None:
        sim = request.app.state.simulator
        suspect = sim.anomaly_detector.suspect_streams
        _scheduler = MissionScheduler(suspect_streams=suspect)
    return _scheduler


@router.get("/")
async def get_plan(request: Request):
    """Return the current mission schedule."""
    scheduler = _get_scheduler(request)
    if not scheduler.activities:
        return {
            "status": "empty",
            "message": "No plan generated yet. Use POST /plan/generate.",
            "activities": [],
            "decisions": [],
        }
    return {
        "activities": [a.to_dict() for a in scheduler.activities],
        "decisions": [d.to_dict() for d in scheduler.decisions],
        "violations": [v.to_dict() for v in scheduler.violations],
        "total_activities": len(scheduler.activities),
        "constraint_violations": len(scheduler.violations),
    }


@router.post("/generate")
async def generate_plan(request: Request):
    """Generate a new mission plan based on current spacecraft state."""
    global _scheduler
    sim = request.app.state.simulator

    # Create fresh scheduler with current suspect streams
    suspect = sim.anomaly_detector.suspect_streams
    _scheduler = MissionScheduler(suspect_streams=suspect)

    # Generate plan
    state_dict = sim.state.model_dump()
    plan = _scheduler.generate_plan(state_dict)

    # Update simulator state with scheduled activities
    sim.state.scheduled_activities = plan["activities"]

    # Try AI-enriched explanations for key decisions
    try:
        from ai.gemini_client import explain_scheduling_decision
        for decision in _scheduler.decisions:
            if decision.decision_type in ("reject", "delay", "reschedule"):
                ai_explanation = await explain_scheduling_decision(decision.to_dict())
                if ai_explanation:
                    decision.explanation = ai_explanation
    except Exception:
        pass  # Fallback explanations already in place

    return plan


@router.get("/explain/{decision_id}")
async def explain_decision(request: Request, decision_id: str):
    """Return human-readable reasoning for a scheduling decision."""
    scheduler = _get_scheduler(request)
    decision = scheduler.get_decision(decision_id)

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
        ai_explanation = await explain_scheduling_decision(decision.to_dict())
    except Exception:
        pass

    return {
        "decision": decision.to_dict(),
        "ai_explanation": ai_explanation,
    }


@router.get("/validate")
async def validate_plan(request: Request):
    """Run the constraint checker against the current plan."""
    scheduler = _get_scheduler(request)
    sim = request.app.state.simulator

    if not scheduler.activities:
        return {"status": "empty", "message": "No plan to validate"}

    from planner.constraints import ConstraintChecker
    checker = ConstraintChecker()
    violations = checker.validate_plan(
        scheduler.activities,
        sim.state.model_dump(),
    )

    return {
        "valid": len(violations) == 0,
        "violations": [v.to_dict() for v in violations],
        "total_violations": len(violations),
    }


@router.get("/decisions")
async def list_decisions(request: Request):
    """Return all scheduling decisions for inspection."""
    scheduler = _get_scheduler(request)
    return {
        "decisions": [d.to_dict() for d in scheduler.decisions],
        "total": len(scheduler.decisions),
    }
