"""
Aegis MOS — SQLAlchemy ORM Models.

These models mirror the Supabase schema exactly. The tables are created
via SQL in Supabase; these models are for ORM-based reads/writes from
the Python backend.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    ARRAY,
    Boolean,
    DateTime,
    Double,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


# ──────────────────────────────────────────────────────────────────────
# 1. SIMULATION SESSIONS
# ──────────────────────────────────────────────────────────────────────
class SimulationSession(Base):
    __tablename__ = "simulation_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String, default="running")
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    total_ticks: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(Text)

    # Relationships
    telemetry: Mapped[list[TelemetrySnapshot]] = relationship(back_populates="session")
    anomalies: Mapped[list[Anomaly]] = relationship(back_populates="session")
    commands: Mapped[list[Command]] = relationship(back_populates="session")


# ──────────────────────────────────────────────────────────────────────
# 2. TELEMETRY SNAPSHOTS
# ──────────────────────────────────────────────────────────────────────
class TelemetrySnapshot(Base):
    __tablename__ = "telemetry_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("simulation_sessions.id", ondelete="CASCADE")
    )
    t: Mapped[int] = mapped_column(Integer, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Power
    battery_soc: Mapped[float] = mapped_column(Double)
    bus_voltage: Mapped[float] = mapped_column(Double)
    solar_input_w: Mapped[float] = mapped_column(Double)
    power_draw_w: Mapped[float] = mapped_column(Double)

    # Thermal
    temp_c: Mapped[float] = mapped_column(Double)
    heater_on: Mapped[bool] = mapped_column(Boolean, default=False)

    # Attitude
    attitude_deg: Mapped[float] = mapped_column(Double)
    slew_rate_dps: Mapped[float] = mapped_column(Double)
    target_attitude_deg: Mapped[float] = mapped_column(Double)

    # Storage
    storage_used_mb: Mapped[float] = mapped_column(Double)
    storage_capacity_mb: Mapped[float] = mapped_column(Double)

    # Comms
    comms_active: Mapped[bool] = mapped_column(Boolean, default=False)
    link_margin_db: Mapped[float] = mapped_column(Double)
    in_contact: Mapped[bool] = mapped_column(Boolean, default=False)

    # Orbital
    in_eclipse: Mapped[bool] = mapped_column(Boolean, default=False)
    orbit_phase: Mapped[float] = mapped_column(Double)

    # Activity flags
    is_observing: Mapped[bool] = mapped_column(Boolean, default=False)
    is_slewing: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships
    session: Mapped[SimulationSession] = relationship(back_populates="telemetry")


# ──────────────────────────────────────────────────────────────────────
# 3. FAULT RUNS (F3)
# ──────────────────────────────────────────────────────────────────────
class FaultRun(Base):
    __tablename__ = "fault_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("simulation_sessions.id", ondelete="CASCADE")
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String, default="running")
    description: Mapped[str | None] = mapped_column(Text)

    events: Mapped[list[FaultEvent]] = relationship(back_populates="fault_run")


# ──────────────────────────────────────────────────────────────────────
# 4. FAULT EVENTS
# ──────────────────────────────────────────────────────────────────────
class FaultEvent(Base):
    __tablename__ = "fault_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    fault_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fault_runs.id", ondelete="CASCADE")
    )
    fault_type: Mapped[str] = mapped_column(String, nullable=False)
    tier: Mapped[str] = mapped_column(String, nullable=False)
    target_subsystem: Mapped[str] = mapped_column(String, nullable=False)
    target_variable: Mapped[str] = mapped_column(String, nullable=False)
    trigger_t: Mapped[int] = mapped_column(Integer, nullable=False)
    parameters: Mapped[dict] = mapped_column(JSONB, default=dict)
    applied: Mapped[bool] = mapped_column(Boolean, default=False)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    fault_run: Mapped[FaultRun] = relationship(back_populates="events")


# ──────────────────────────────────────────────────────────────────────
# 5. SCORECARD ENTRIES (F3)
# ──────────────────────────────────────────────────────────────────────
class ScorecardEntry(Base):
    __tablename__ = "scorecard_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    fault_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fault_runs.id", ondelete="CASCADE")
    )
    fault_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fault_events.id", ondelete="CASCADE")
    )
    detected: Mapped[bool] = mapped_column(Boolean, nullable=False)
    correctly_attributed: Mapped[bool | None] = mapped_column(Boolean)
    detection_latency_ticks: Mapped[int | None] = mapped_column(Integer)
    detector_diagnosis: Mapped[str | None] = mapped_column(Text)
    actual_root_cause: Mapped[str | None] = mapped_column(Text)
    scored_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ──────────────────────────────────────────────────────────────────────
# 6. ANOMALIES (F4)
# ──────────────────────────────────────────────────────────────────────
class Anomaly(Base):
    __tablename__ = "anomalies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("simulation_sessions.id", ondelete="CASCADE")
    )
    detected_at_t: Mapped[int] = mapped_column(Integer, nullable=False)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    anomaly_type: Mapped[str] = mapped_column(String, nullable=False)
    severity: Mapped[str] = mapped_column(String, default="warning")
    affected_subsystem: Mapped[str] = mapped_column(String, nullable=False)
    affected_variable: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    root_cause_subsystem: Mapped[str | None] = mapped_column(String)
    root_cause_explanation: Mapped[str | None] = mapped_column(Text)
    correlated_anomaly_ids: Mapped[list | None] = mapped_column(ARRAY(UUID(as_uuid=True)))
    status: Mapped[str] = mapped_column(String, default="active")
    acknowledged_by: Mapped[str | None] = mapped_column(String)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cleared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stream_marked_suspect: Mapped[bool] = mapped_column(Boolean, default=True)

    session: Mapped[SimulationSession] = relationship(back_populates="anomalies")


# ──────────────────────────────────────────────────────────────────────
# 7. PLAN RECORDS (F5)
# ──────────────────────────────────────────────────────────────────────
class PlanRecord(Base):
    __tablename__ = "plan_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("simulation_sessions.id", ondelete="CASCADE")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    status: Mapped[str] = mapped_column(String, default="draft")
    plan_data: Mapped[list] = mapped_column(JSONB, default=list)
    total_activities: Mapped[int] = mapped_column(Integer, default=0)
    constraint_violations: Mapped[int] = mapped_column(Integer, default=0)

    decisions: Mapped[list[PlanDecision]] = relationship(back_populates="plan")


# ──────────────────────────────────────────────────────────────────────
# 8. PLAN DECISIONS (F5)
# ──────────────────────────────────────────────────────────────────────
class PlanDecision(Base):
    __tablename__ = "plan_decisions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plan_records.id", ondelete="CASCADE")
    )
    node_name: Mapped[str] = mapped_column(String, nullable=False)
    decision_type: Mapped[str] = mapped_column(String, nullable=False)
    activity_type: Mapped[str | None] = mapped_column(String)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    input_state: Mapped[dict | None] = mapped_column(JSONB)
    output_state: Mapped[dict | None] = mapped_column(JSONB)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    plan: Mapped[PlanRecord] = relationship(back_populates="decisions")


# ──────────────────────────────────────────────────────────────────────
# 9. COMMANDS (F6)
# ──────────────────────────────────────────────────────────────────────
class Command(Base):
    __tablename__ = "commands"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("simulation_sessions.id", ondelete="CASCADE")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    command_type: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    is_irreversible: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String, default="proposed")
    proposed_by: Mapped[str] = mapped_column(String, nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(String)
    verified_by: Mapped[str | None] = mapped_column(String)
    approved_by: Mapped[str | None] = mapped_column(String)
    self_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(Text)

    session: Mapped[SimulationSession] = relationship(back_populates="commands")
    ledger_entries: Mapped[list[AuditLedgerEntry]] = relationship(back_populates="command")


# ──────────────────────────────────────────────────────────────────────
# 10. AUDIT LEDGER (F6 — append-only)
# ──────────────────────────────────────────────────────────────────────
class AuditLedgerEntry(Base):
    __tablename__ = "audit_ledger"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), unique=True, default=uuid.uuid4
    )
    command_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("commands.id")
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("simulation_sessions.id")
    )
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    approver_id: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)
    signature: Mapped[str] = mapped_column(String, nullable=False)
    key_version: Mapped[int] = mapped_column(Integer, default=1)
    corrects_entry: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    self_approval: Mapped[bool] = mapped_column(Boolean, default=False)

    command: Mapped[Command] = relationship(back_populates="ledger_entries")
