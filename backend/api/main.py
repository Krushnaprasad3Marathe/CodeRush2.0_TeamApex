"""
Aegis MOS — FastAPI Application Entrypoint.

This is the main gateway for all API routes and the WebSocket telemetry stream.
The simulator is started as a background asyncio task during app lifespan and
is the single source of truth for spacecraft state.
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from api.routes import anomalies, commands, faults, plan, telemetry
from simulator.simulator import Simulator

load_dotenv()  # Load .env file if present

logger = logging.getLogger("aegis.api")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Start the simulator as a background task on startup.
    If DATABASE_URL is configured, telemetry is persisted to Supabase.
    """
    # Set up persistence if a database is configured
    persistence = None
    db_url = os.getenv("DATABASE_URL", "")
    if db_url and "localhost" not in db_url:
        try:
            from db.persistence import TelemetryPersistence
            from db.session import async_session_factory

            persistence = TelemetryPersistence(
                session_factory=async_session_factory,
                sample_rate=int(os.getenv("TELEMETRY_SAMPLE_RATE", "1")),
            )
            logger.info("Telemetry persistence enabled (Supabase)")
        except Exception as e:
            logger.warning(f"Persistence setup failed, running without DB: {e}")
            persistence = None
    else:
        logger.info("No remote DATABASE_URL — running without persistence")

    simulator = Simulator(persistence=persistence)
    app.state.simulator = simulator
    task = asyncio.create_task(simulator.run(), name="simulator-loop")
    logger.info("Simulator started as background task")

    yield

    # Shutdown: stop the simulator and cancel the task
    await simulator.stop()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    logger.info("Simulator stopped")


app = FastAPI(
    title="Aegis MOS",
    description="Simulation-First Mission Operations System",
    version="0.1.0",
    lifespan=lifespan,
)

# ── CORS (allow frontend dev server) ─────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Include all routers ──────────────────────────────────────────────
app.include_router(telemetry.router)
app.include_router(faults.router)
app.include_router(anomalies.router)
app.include_router(plan.router)
app.include_router(commands.router)


# ── Health check ─────────────────────────────────────────────────────
@app.get("/health", tags=["system"])
async def health_check():
    """Health check endpoint for Docker / load balancer probes."""
    sim: Simulator = app.state.simulator
    return {
        "status": "ok",
        "simulator_running": sim.is_running,
        "simulator_tick": sim.state.t,
        "observed_hz": round(sim.clock.observed_hz, 4),
        "active_faults": sim.fault_engine.active_fault_count,
        "active_anomalies": len(sim.anomaly_detector.active_alerts),
    }


# ── WebSocket telemetry stream (F2) ─────────────────────────────────
@app.websocket("/ws/telemetry")
async def telemetry_ws(websocket: WebSocket):
    """
    Live telemetry broadcast stream.

    On connect: immediately sends the current spacecraft state snapshot.
    Then: sends byte-identical state payloads on every simulation tick.
    """
    client_id = str(uuid4())
    sim: Simulator = app.state.simulator

    await sim.broadcast.connect(websocket, client_id)
    logger.info(f"WS client connected: {client_id}")

    try:
        # Keep connection alive — we only send, client just listens
        while True:
            # Wait for any client message (ping/pong keepalive)
            await websocket.receive_text()
    except WebSocketDisconnect:
        logger.info(f"WS client disconnected: {client_id}")
    except Exception as e:
        logger.warning(f"WS client {client_id} error: {e}")
    finally:
        await sim.broadcast.disconnect(client_id)


# ── REST telemetry snapshot ──────────────────────────────────────────
@app.get("/telemetry/snapshot", tags=["telemetry"])
async def telemetry_snapshot():
    """Return the current spacecraft state as a JSON snapshot."""
    sim: Simulator = app.state.simulator
    return sim.state.model_dump()


# ── AI Diagnostics endpoint ──────────────────────────────────────────
class DiagnoseRequest(BaseModel):
    context: str = "general"


@app.post("/ai/diagnose", tags=["ai"])
async def ai_diagnose(body: DiagnoseRequest):
    """
    Get AI-powered diagnosis of the current spacecraft state.

    Uses Google Gemini to analyze telemetry and active anomalies.
    """
    sim: Simulator = app.state.simulator
    state_dict = sim.state.model_dump()
    alerts = sim.anomaly_detector.get_alerts_summary()
    active_alerts = [a for a in alerts if not a.get("acknowledged")]

    diagnosis_dict = None
    latest_diag = sim.correlator.latest_diagnosis
    if latest_diag:
        diagnosis_dict = latest_diag.to_dict()

    try:
        from ai.gemini_client import diagnose_anomaly
        explanation = await diagnose_anomaly(
            active_alerts, state_dict, diagnosis_dict
        )
    except Exception as e:
        explanation = f"AI diagnosis unavailable: {e}"

    # Also get procedure suggestion if there are active anomalies
    procedures = []
    if active_alerts:
        try:
            from ai.gemini_client import suggest_procedure
            procedures = await suggest_procedure(active_alerts[0], state_dict)
        except Exception:
            pass

    return {
        "diagnosis": explanation,
        "active_alerts": len(active_alerts),
        "root_cause": diagnosis_dict,
        "suggested_procedures": procedures,
        "state_summary": {
            "battery_soc": state_dict.get("battery_soc"),
            "temp_c": state_dict.get("temp_c"),
            "bus_voltage": state_dict.get("bus_voltage"),
            "in_eclipse": state_dict.get("in_eclipse"),
        },
    }
