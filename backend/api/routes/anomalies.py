"""
Aegis MOS — Anomaly detection API routes (F4).

Endpoints:
  GET  /anomalies                — Active + historical anomalies
  GET  /anomalies/{id}/diagnosis — Full root-cause diagnosis
  POST /anomalies/{id}/ack      — Acknowledge/clear an anomaly (audited)
  GET  /anomalies/suspect        — Currently suspect data streams
"""

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(prefix="/anomalies", tags=["anomalies"])


class AckRequest(BaseModel):
    operator_id: str = "operator-1"


@router.get("/")
async def list_anomalies(request: Request):
    """Return active and historical anomalies."""
    sim = request.app.state.simulator
    alerts = sim.anomaly_detector.get_alerts_summary()
    active = [a for a in alerts if not a.get("acknowledged")]
    return {
        "active": active,
        "history": alerts,
        "total_active": len(active),
        "total_all": len(alerts),
    }


@router.get("/{anomaly_id}/diagnosis")
async def get_diagnosis(request: Request, anomaly_id: str):
    """Return the full root-cause diagnosis for an anomaly."""
    sim = request.app.state.simulator

    # Find the alert
    alerts = sim.anomaly_detector.get_alerts_summary()
    alert = next((a for a in alerts if a["alert_id"] == anomaly_id), None)
    if alert is None:
        return {"status": "error", "message": f"Anomaly {anomaly_id} not found"}

    # Get associated diagnosis
    root_cause_id = alert.get("root_cause_id")
    diagnosis = None
    if root_cause_id:
        for diag in sim.correlator.all_diagnoses:
            if diag.diagnosis_id == root_cause_id:
                diagnosis = diag.to_dict()
                break

    # Try AI-powered explanation
    ai_explanation = None
    try:
        from ai.gemini_client import diagnose_anomaly
        state_dict = sim.state.model_dump()
        ai_explanation = await diagnose_anomaly(
            [alert], state_dict, diagnosis
        )
    except Exception:
        pass

    return {
        "alert": alert,
        "diagnosis": diagnosis,
        "ai_explanation": ai_explanation,
    }


@router.post("/{anomaly_id}/ack")
async def acknowledge_anomaly(
    request: Request, anomaly_id: str, body: AckRequest
):
    """Acknowledge/clear an anomaly. This action is audited."""
    sim = request.app.state.simulator
    success = sim.anomaly_detector.acknowledge_alert(
        anomaly_id, body.operator_id, sim.state.t
    )
    if not success:
        return {"status": "error", "message": f"Anomaly {anomaly_id} not found"}

    return {
        "status": "acknowledged",
        "anomaly_id": anomaly_id,
        "acknowledged_by": body.operator_id,
        "at_tick": sim.state.t,
    }


@router.get("/suspect")
async def get_suspect_streams(request: Request):
    """Return currently suspect data streams."""
    sim = request.app.state.simulator
    return {
        "suspect_streams": list(sim.anomaly_detector.suspect_streams),
    }
