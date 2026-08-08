"""
Aegis MOS — Activity Definitions (F5).

Pydantic models for the three primary activity classes that the
scheduler manages: observations, downlinks, and solar charging.

Each activity declares its resource requirements so the constraint
engine can validate plans against available budgets.
"""

from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field


class ActivityType(str, Enum):
    OBSERVATION = "observation"
    DOWNLINK = "downlink"
    CHARGING = "charging"


class ActivityStatus(str, Enum):
    PENDING = "pending"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"


class Constraint(BaseModel):
    """A single constraint that an activity requires."""

    resource: str = Field(description="Resource type: power, storage, comms, thermal, attitude")
    requirement: str = Field(description="Human-readable constraint description")
    min_value: float | None = None
    max_value: float | None = None


class ScheduledActivity(BaseModel):
    """A fully scheduled activity with timing and constraints."""

    activity_id: str
    activity_type: ActivityType
    name: str
    description: str = ""
    start_t: int = Field(ge=0)
    end_t: int = Field(ge=0)
    duration_ticks: int = Field(ge=1)
    priority: int = Field(default=5, ge=1, le=10)
    status: ActivityStatus = ActivityStatus.PENDING
    constraints_satisfied: bool = True
    explanation: str = ""

    # Resource requirements
    power_draw_w: float = 0.0
    required_attitude_deg: float | None = None
    requires_contact: bool = False
    requires_sunlight: bool = False

    def to_dict(self) -> dict:
        return self.model_dump()


class Observation(BaseModel):
    """Observation activity — science data collection."""

    name: str = "Observation"
    target: str = Field(default="Target-1", description="Observation target")
    duration_ticks: int = Field(default=300, ge=1)
    required_attitude_deg: float = Field(default=45.0)
    power_draw_w: float = Field(default=1.5)
    data_rate_mb: float = Field(default=5.0)
    priority: int = Field(default=7, ge=1, le=10)

    def constraints(self) -> list[Constraint]:
        return [
            Constraint(
                resource="power",
                requirement=f"Requires {self.power_draw_w}W sustained power",
                min_value=0.20,  # Min SOC 20%
            ),
            Constraint(
                resource="storage",
                requirement=f"Generates {self.data_rate_mb}MB/tick ({self.data_rate_mb * self.duration_ticks}MB total)",
                max_value=0.90,  # Max 90% storage used
            ),
            Constraint(
                resource="attitude",
                requirement=f"Requires attitude at {self.required_attitude_deg}°",
            ),
        ]


class Downlink(BaseModel):
    """Downlink activity — data transfer to ground station."""

    name: str = "Downlink"
    window_start_t: int = Field(default=0, ge=0)
    window_end_t: int = Field(default=600)
    data_rate_mb: float = Field(default=8.0)
    power_draw_w: float = Field(default=3.5)
    priority: int = Field(default=8, ge=1, le=10)

    def constraints(self) -> list[Constraint]:
        return [
            Constraint(
                resource="comms",
                requirement="Requires ground station contact window",
            ),
            Constraint(
                resource="power",
                requirement=f"Requires {self.power_draw_w}W for transmitter",
                min_value=0.15,  # Min SOC 15%
            ),
        ]


class SolarCharging(BaseModel):
    """Solar charging activity — battery recharge."""

    name: str = "Solar Charging"
    target_soc: float = Field(default=0.90, ge=0.0, le=1.0)
    max_duration_ticks: int = Field(default=1800)
    priority: int = Field(default=6, ge=1, le=10)

    def constraints(self) -> list[Constraint]:
        return [
            Constraint(
                resource="attitude",
                requirement="Requires sun-pointing attitude (0°)",
            ),
            Constraint(
                resource="power",
                requirement="Must be in sunlight (not in eclipse)",
            ),
        ]
