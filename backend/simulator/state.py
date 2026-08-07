"""
Aegis MOS — Spacecraft State Model.

Defines the complete spacecraft state at a single simulation tick.
This is the single source of truth data shape that every component consumes.

Design decisions:
  - Flat structure (no nested objects) for clean JSON serialization over WS
  - Every field is a primitive that serializes to JSON without custom encoders
  - `t` is the universal clock reference — all fault timing, anomaly detection,
    and replay keying uses this, never wall-clock time
  - `timestamp` is wall-clock for logging/display only, never for simulation logic
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SpacecraftState(BaseModel):
    """Complete spacecraft state at a single simulation tick."""

    # ── Simulation clock ────────────────────────────────────────────
    t: int = Field(default=0, description="Simulation tick counter (monotonic, 0-indexed)")
    timestamp: float = Field(default=0.0, description="Wall-clock time when tick was computed (epoch)")

    # ── Power subsystem ─────────────────────────────────────────────
    battery_soc: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        description="Battery state of charge [0.0 – 1.0]",
    )
    bus_voltage: float = Field(
        default=4.85,
        description="Bus voltage [V] — varies with SOC",
    )
    solar_input_w: float = Field(
        default=7.0,
        ge=0.0,
        description="Current solar power input [W]",
    )
    power_draw_w: float = Field(
        default=2.0,
        ge=0.0,
        description="Current total power draw [W]",
    )

    # ── Thermal subsystem (lumped single zone for v1) ───────────────
    temp_c: float = Field(
        default=22.0,
        description="Bus temperature [°C] — single lumped zone",
    )
    heater_on: bool = Field(
        default=False,
        description="Whether the survival heater is active",
    )

    # ── Attitude / pointing ─────────────────────────────────────────
    attitude_deg: float = Field(
        default=0.0,
        description="Current pointing angle [degrees from sun-pointing]",
    )
    slew_rate_dps: float = Field(
        default=0.0,
        description="Current slew rate [deg/s]",
    )
    target_attitude_deg: float = Field(
        default=0.0,
        description="Commanded target attitude [degrees from sun-pointing]",
    )

    # ── Onboard storage ─────────────────────────────────────────────
    storage_used_mb: float = Field(
        default=256.0,
        ge=0.0,
        description="Onboard storage used [MB]",
    )
    storage_capacity_mb: float = Field(
        default=2048.0,
        gt=0.0,
        description="Total onboard storage capacity [MB]",
    )

    # ── Communications ──────────────────────────────────────────────
    comms_active: bool = Field(
        default=False,
        description="Whether downlink is currently active",
    )
    link_margin_db: float = Field(
        default=-999.0,
        description="Current link margin [dB] — -999 when out of contact",
    )
    in_contact: bool = Field(
        default=False,
        description="Whether a ground station is in view",
    )

    # ── Orbital context ─────────────────────────────────────────────
    in_eclipse: bool = Field(
        default=False,
        description="Whether spacecraft is in Earth's shadow",
    )
    orbit_phase: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Orbital phase [0.0 – 1.0] — 0 = start of sunlit, wraps at 1.0",
    )

    # ── Activity flags ──────────────────────────────────────────────────
    is_observing: bool = Field(
        default=False,
        description="Whether the science instrument is actively collecting data",
    )
    is_slewing: bool = Field(
        default=False,
        description="Whether the spacecraft is actively slewing to a target attitude",
    )

    # ── Sensor-fault reported values (overlay) ──────────────────────────
    # When sensor-tier faults are active, these hold the corrupted
    # "reported" values. None = no sensor fault on this variable.
    reported_battery_soc: float | None = Field(default=None)
    reported_bus_voltage: float | None = Field(default=None)
    reported_solar_input_w: float | None = Field(default=None)
    reported_temp_c: float | None = Field(default=None)
    reported_attitude_deg: float | None = Field(default=None)
    reported_storage_used_mb: float | None = Field(default=None)
    reported_link_margin_db: float | None = Field(default=None)
    reported_power_draw_w: float | None = Field(default=None)
    reported_slew_rate_dps: float | None = Field(default=None)

    # ── Anomaly / Diagnosis state (broadcast to frontend) ───────────────
    active_anomalies: list[dict] = Field(
        default_factory=list,
        description="Currently active anomaly alerts",
    )
    root_cause_diagnosis: dict | None = Field(
        default=None,
        description="Latest root-cause diagnosis (if any)",
    )
    suspect_streams: list[str] = Field(
        default_factory=list,
        description="Variables currently marked suspect",
    )

    # ── Active faults (broadcast to sandbox UI) ─────────────────────────
    active_faults: list[dict] = Field(
        default_factory=list,
        description="Currently active injected faults",
    )
    sandbox_mode: bool = Field(
        default=False,
        description="Whether fault injection sandbox is active",
    )

    # ── Scorecard (broadcast for sandbox display) ───────────────────────
    scorecard: dict | None = Field(
        default=None,
        description="Fault detection scorecard stats",
    )

    # ── Schedule (broadcast for timeline display) ───────────────────────
    scheduled_activities: list[dict] = Field(
        default_factory=list,
        description="Current scheduled activities from the planner",
    )

    @classmethod
    def initial(cls) -> SpacecraftState:
        """
        Create the initial spacecraft state for simulation start.

        Represents a healthy CubeSat in sunlit LEO with:
        - Battery at 85% charge
        - Nominal temperature
        - Sun-pointing attitude
        - Some data already in storage (from previous orbit)
        - No active comms/observations
        """
        return cls(
            t=0,
            timestamp=0.0,
            battery_soc=0.85,
            bus_voltage=4.85,
            solar_input_w=7.0,
            power_draw_w=2.0,
            temp_c=22.0,
            heater_on=False,
            attitude_deg=0.0,
            slew_rate_dps=0.0,
            target_attitude_deg=0.0,
            storage_used_mb=256.0,
            storage_capacity_mb=2048.0,
            comms_active=False,
            link_margin_db=-999.0,
            in_contact=False,
            in_eclipse=False,
            orbit_phase=0.0,
            is_observing=False,
            is_slewing=False,
        )

    def clone(self) -> SpacecraftState:
        """Return a deep copy of this state for branching/forking."""
        return self.model_copy(deep=True)


class ScheduledFault(BaseModel):
    """
    A fault scheduled to fire at a specific simulation tick.

    Faults are keyed to `trigger_t` (simulation time), never wall-clock.
    This ensures deterministic replay: the same fault fires at the same
    simulated tick in both real-time and accelerated modes.
    """

    fault_id: str = Field(description="Unique identifier for this fault instance")
    trigger_t: int = Field(ge=0, description="Simulation tick at which to fire the fault")
    fault_type: str = Field(description="Fault type from catalog: bias, drift, noise, stuck, dropout, step_change")
    target_subsystem: str = Field(description="Subsystem to apply fault to: power, thermal, attitude, storage, comms")
    target_variable: str = Field(description="Specific state variable to affect")
    tier: str = Field(description="'sensor' (reporting only) or 'system' (affects physics)")
    parameters: dict = Field(default_factory=dict, description="Fault-specific parameters (offset, rate, sigma, etc.)")
    applied: bool = Field(default=False, description="Whether this fault has been applied")
