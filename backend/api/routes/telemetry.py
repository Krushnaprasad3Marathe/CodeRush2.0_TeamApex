"""
Aegis MOS — Telemetry API routes (F1/F2/F7).

The primary telemetry endpoints (WS /ws/telemetry and GET /telemetry/snapshot)
are defined in main.py for direct access to the simulator instance.
This router is reserved for future telemetry-specific routes.
"""

from fastapi import APIRouter

router = APIRouter(tags=["telemetry"])
