"""
Aegis MOS — Anomaly detection API routes (F4).

Endpoints:
  GET  /anomalies                — Active + historical anomalies
  GET  /anomalies/{id}/diagnosis — Full root-cause diagnosis
  POST /anomalies/{id}/ack      — Acknowledge/clear an anomaly (audited)
  GET  /anomalies/suspect        — Currently suspect data streams
  POST /anomalies/trigger-manual — Manually trigger/schedule anomaly for live demonstration
"""

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from typing import Optional

router = APIRouter(prefix="/anomalies", tags=["anomalies"])


class AckRequest(BaseModel):
    operator_id: str = "operator-1"


class ManualTriggerRequest(BaseModel):
    variable: str = Field(default="battery_soc", description="State variable to fault")
    subsystem: str = Field(default="EPS (Power)", description="Target subsystem name")
    severity: str = Field(default="critical", description="'critical' or 'warning'")
    description: str = Field(
        default="Manual anomaly override injected for live demonstration",
        description="Human-readable explanation",
    )
    z_score: float = Field(default=4.2, description="Statistical residual deviation Z-score")
    residual: float = Field(default=0.45, description="Absolute error residual")
    delay_seconds: int = Field(default=0, description="0 for immediate, or seconds into future")


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


@router.post("/trigger-manual")
async def trigger_manual_anomaly(request: Request, body: ManualTriggerRequest):
    """
    Manually trigger or schedule an anomaly at an exact timestamp for live demos.
    Overrides background inference loop and instantly injects state perturbation.
    """
    sim = request.app.state.simulator
    t_fire = sim.state.t + body.delay_seconds

    from anomaly.correlator import AnomalyAlert, RootCauseDiagnosis
    import time

    sim.anomaly_detector._alert_counter += 1
    alert_id = f"ANOM-{sim.anomaly_detector._alert_counter:04d}"
    diag_id = f"DIAG-MANUAL-{sim.anomaly_detector._alert_counter:04d}"

    # Instantly apply physical data deviation on current state
    var = body.variable
    if var == "battery_soc":
        sim.state.battery_soc = max(0.12, sim.state.battery_soc - body.residual)
        sim.state.bus_voltage = 4.18
    elif var == "temp_c":
        sim.state.temp_c = 46.8
        sim.state.heater_on = True
    elif var == "solar_input_w":
        sim.state.solar_input_w = 0.8
    elif var == "bus_voltage":
        sim.state.bus_voltage = 4.12
    elif var == "attitude_deg":
        sim.state.attitude_deg = 18.5
        sim.state.slew_rate_dps = 1.8
    elif var == "storage_used_mb":
        sim.state.storage_used_mb = 1980.0
    elif var == "link_margin_db":
        sim.state.link_margin_db = -999.0

    alert = AnomalyAlert(
        alert_id=alert_id,
        subsystem=body.subsystem,
        variable=body.variable,
        severity=body.severity,
        description=body.description,
        detected_at_t=t_fire,
        is_suspect=True,
        root_cause_id=diag_id,
    )

    sim.anomaly_detector._active_alerts[alert_id] = alert
    sim.anomaly_detector._alert_history.append(alert)
    sim.anomaly_detector._suspect_streams.add(body.variable)

    # Attach Root-Cause diagnosis
    diagnosis = RootCauseDiagnosis(
        diagnosis_id=diag_id,
        timestamp=time.time(),
        tick=t_fire,
        root_subsystem=body.subsystem,
        root_variable=body.variable,
        confidence=0.96,
        downstream_effects=["battery_soc", "bus_voltage", "temp_c"] if "EPS" in body.subsystem else [body.variable],
        chain=[f"Injected {body.variable} failure", "Subsystem coupling propagation", "Telemetry out-of-envelope alert"],
        summary=f"Manual Demonstration Alert: {body.description}",
    )
    sim.correlator._diagnoses.append(diagnosis)
    sim.state.root_cause_diagnosis = diagnosis.to_dict()
    sim.state.active_anomalies = sim.anomaly_detector.get_alerts_summary()
    sim.state.suspect_streams = list(sim.anomaly_detector.suspect_streams)

    # Broadcast state immediately
    payload = sim.state.model_dump_json().encode("utf-8")
    await sim.broadcast.publish(payload)

    return {
        "status": "triggered",
        "alert_id": alert_id,
        "diagnosis_id": diag_id,
        "variable": body.variable,
        "trigger_t": t_fire,
        "alert": {
            "alert_id": alert.alert_id,
            "subsystem": alert.subsystem,
            "variable": alert.variable,
            "severity": alert.severity,
            "description": alert.description,
            "detected_at_t": alert.detected_at_t,
        },
    }


@router.get("/{anomaly_id}/diagnosis")
async def get_diagnosis(request: Request, anomaly_id: str):
    """Return the full root-cause diagnosis for an anomaly."""
    sim = request.app.state.simulator

    alerts = sim.anomaly_detector.get_alerts_summary()
    alert = next((a for a in alerts if a["alert_id"] == anomaly_id), None)
    if alert is None:
        return {"status": "error", "message": f"Anomaly {anomaly_id} not found"}

    root_cause_id = alert.get("root_cause_id")
    diagnosis = None
    if root_cause_id:
        for diag in sim.correlator.all_diagnoses:
            if diag.diagnosis_id == root_cause_id:
                diagnosis = diag.to_dict()
                break

    ai_explanation = None
    try:
        from ai.gemini_client import diagnose_anomaly
        state_dict = sim.state.model_dump()
        ai_explanation = await diagnose_anomaly([alert], state_dict, diagnosis)
    except Exception:
        pass

    return {
        "alert": alert,
        "diagnosis": diagnosis,
        "ai_explanation": ai_explanation,
    }


@router.post("/{anomaly_id}/ack")
async def acknowledge_anomaly(request: Request, anomaly_id: str, body: AckRequest):
    """Acknowledge/clear an anomaly. This action is audited."""
    sim = request.app.state.simulator
    success = sim.anomaly_detector.acknowledge_alert(anomaly_id, body.operator_id, sim.state.t)
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
