"""
Aegis MOS — Fault injection API routes (F3).

Endpoints:
  POST /fault/inject       — Schedule a fault keyed to trigger_t
  POST /fault/inject-now   — Inject a fault at the current tick
  GET  /fault/catalog      — Available fault types per subsystem
  GET  /fault/active       — Currently active faults
  GET  /fault/scorecard    — Aggregate detection success/failure stats
  POST /fault/clear/{id}   — Clear a specific fault
  POST /fault/clear-all    — Clear all faults
  POST /fault/sandbox/on   — Enter sandbox mode
  POST /fault/sandbox/off  — Exit sandbox mode
"""

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from faults.catalog import (
    FAULT_CATALOG,
    SUBSYSTEM_VARIABLES,
    FaultInjectionRequest,
)

router = APIRouter(prefix="/fault", tags=["faults"])


@router.post("/inject")
async def inject_fault(request: Request, body: FaultInjectionRequest):
    """Schedule a fault injection at a specific simulation tick."""
    sim = request.app.state.simulator
    active_fault = sim.fault_engine.inject_fault(body)
    return {
        "status": "scheduled",
        "fault": active_fault.to_dict(),
    }


@router.post("/inject-now")
async def inject_fault_now(request: Request, body: FaultInjectionRequest):
    """Inject a fault at the current tick + 1."""
    sim = request.app.state.simulator
    body.trigger_t = sim.state.t + 1
    active_fault = sim.fault_engine.inject_fault(body)
    return {
        "status": "scheduled",
        "fault": active_fault.to_dict(),
        "fires_at_t": body.trigger_t,
    }


@router.get("/catalog")
async def get_catalog():
    """Return the full fault catalog for UI display."""
    return {
        "catalog": [entry.model_dump() for entry in FAULT_CATALOG],
        "subsystem_variables": SUBSYSTEM_VARIABLES,
    }


@router.get("/active")
async def get_active_faults(request: Request):
    """Return currently active faults."""
    sim = request.app.state.simulator
    return {
        "active_faults": sim.fault_engine.get_active_faults_summary(),
        "count": sim.fault_engine.active_fault_count,
        "sandbox_mode": sim.fault_engine.sandbox_mode,
    }


@router.get("/scorecard")
async def get_scorecard(request: Request):
    """Return aggregate fault detection success/failure stats."""
    sim = request.app.state.simulator
    return sim.fault_engine.get_scorecard()


@router.post("/clear/{fault_id}")
async def clear_fault(request: Request, fault_id: str):
    """Clear (deactivate) a specific fault by ID."""
    sim = request.app.state.simulator
    cleared = sim.fault_engine.clear_fault(fault_id)
    if not cleared:
        return {"status": "error", "message": f"Fault {fault_id} not found"}
    return {"status": "cleared", "fault_id": fault_id}


@router.post("/clear-all")
async def clear_all_faults(request: Request):
    """Clear all active faults."""
    sim = request.app.state.simulator
    sim.fault_engine.clear_all()
    return {"status": "cleared", "message": "All faults cleared"}


@router.post("/sandbox/on")
async def sandbox_on(request: Request):
    """Enter sandbox mode."""
    sim = request.app.state.simulator
    sim.fault_engine.sandbox_mode = True
    return {"sandbox_mode": True}


@router.post("/sandbox/off")
async def sandbox_off(request: Request):
    """Exit sandbox mode and clear all faults."""
    sim = request.app.state.simulator
    sim.fault_engine.sandbox_mode = False
    sim.fault_engine.clear_all()
    return {"sandbox_mode": False}
