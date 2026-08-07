# Aegis MOS — Simulation-First Mission Operations System

A simulation-first mission-operations platform for spacecraft systems. Aegis MOS runs a continuous digital twin of the vehicle, detects and explains anomalies, schedules mission activities under real constraints, and lets operators draft and approve procedure steps — with every irreversible action passing through an explicit authority and verification gate.

## Architecture

```
┌─────────────────────────────────┐
│       simulator.py              │
│   1Hz async physics loop        │
│   (single source of truth)      │
└───────────────┬─────────────────┘
                │ broadcast (WS)
    ┌───────────┼───────────┐
    │           │           │
┌───▼───┐  ┌───▼───┐  ┌───▼───┐
│Anomaly│  │Mission│  │ Fault │
│Detect │  │Planner│  │Inject │
└───┬───┘  └───┬───┘  └───┬───┘
    └───────┬───┴───┬──────┘
            │       │
    ┌───────▼──┐ ┌──▼────────┐
    │ Authority│ │ REST + WS │
    │ Audit    │ │ API (Fast │
    │ Gate     │ │  API)     │
    └───────┬──┘ └──┬────────┘
            │       │
    ┌───────▼──┐    │
    │ Postgres │    │
    └──────────┘    │
              ┌─────▼──────────┐
              │ Operator       │
              │ Console (React)│
              └────────────────┘
```

## Quickstart

### Prerequisites
- Python 3.11+
- Node.js 18+
- Docker & Docker Compose (for PostgreSQL)

### Development (without Docker)

**Backend:**
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux
pip install -e ".[dev]"
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

**Database:**
```bash
docker compose up postgres -d
cd backend
alembic upgrade head
```

### Full Stack (Docker Compose)
```bash
docker compose up --build
```

- **Frontend:** http://localhost:5173
- **Backend API:** http://localhost:8000
- **API Docs:** http://localhost:8000/docs

## Project Structure

```
aegis-mos/
├── backend/
│   ├── simulator/       # F1+F2: Digital twin engine
│   ├── faults/          # F3: Fault injection sandbox
│   ├── anomaly/         # F4: Anomaly detection
│   ├── planner/         # F5: Mission planner (LangGraph)
│   ├── authority/       # F6: Authority/audit model
│   ├── api/             # FastAPI gateway
│   ├── db/              # Database models + migrations
│   └── tests/           # Backend test suite
├── frontend/            # React + TypeScript operator console
├── datasets/            # Generated test datasets
├── docs/                # PRD, TRD, ADRs
└── docker-compose.yml
```

## Key Design Principles

1. **Single writer**: `simulator.py` is the only thing that mutates spacecraft state
2. **Deterministic timing**: Faults keyed to simulation time (`state.t`), never wall-clock
3. **Byte-identical broadcast**: All WS clients receive the same serialized payload per tick
4. **Authority gate**: No irreversible command approved without explicit human review + HMAC seal

## Documentation

- [Product Requirements (PRD)](docs/PRD.md)
- [Technical Requirements (TRD)](docs/TRD.md)

## License

Proprietary — all rights reserved.
