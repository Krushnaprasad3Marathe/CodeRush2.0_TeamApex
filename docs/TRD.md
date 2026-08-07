# Technical Requirements Document (TRD)
# Simulation-First Mission Operations System (Aegis MOS)

> **Version:** 0.1 (Draft) — companion to PRD v0.1

*Full TRD content committed here for in-repo reference. See the original specification for complete details.*

## Resolved Technical Decisions (Phase 1)

| Question | Decision |
|----------|----------|
| Thermal zones | Single lumped thermal model (one `temp_c`) for v1 |
| Anomaly debounce window | 3 consecutive ticks (configurable) |
| Self-approval (F6) | Flagged but not blocked in v1 |

## Architecture

- **Single writer**: `simulator.py` owns all physical state mutation
- **1Hz self-correcting clock**: monotonic accumulation, not fixed sleep
- **Byte-identical broadcast**: serialize once, send same bytes to all WS clients
- **Fault timing**: keyed to `state.t` (simulation ticks), never wall-clock

## Tech Stack

| Layer | Choice |
|-------|--------|
| Simulation engine | Python 3.11+, asyncio |
| API gateway | FastAPI + uvicorn (ASGI) |
| Realtime transport | WebSockets (native) |
| Scheduler workflow | LangGraph (Phase 4) |
| Database | PostgreSQL |
| ORM/migrations | SQLAlchemy 2.0 (async) + Alembic |
| Audit signing | Python hmac + hashlib (SHA-256) |
| Frontend | React + TypeScript, Vite |
| Charts | Recharts |
| Frontend state | Zustand |
| Testing | pytest + pytest-asyncio (backend), vitest (frontend) |

## Build Sequencing

| Phase | Scope |
|-------|-------|
| 0 | Scaffolding |
| 1 | Digital Twin + Timing (F1+F2) |
| 2 | Fault Sandbox (F3) |
| 3 | Anomaly Detection (F4) |
| 4 | Mission Planner (F5) |
| 5 | Authority/Audit (F6) |
| 6 | Operator Console (F7) |
