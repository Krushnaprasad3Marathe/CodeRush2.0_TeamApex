"""
Aegis MOS — Fault Type Catalog (F3).

Defines canonical fault types that can be injected into any numeric telemetry variable.
Every fault is keyed to simulation time (state.t) for deterministic replay and sandbox execution.

Fault types:
  bias / step_bias           — constant offset added to the true value
  scale_factor / scale       — proportional scaling of value
  drift / ramp_drift         — linearly increasing offset over time
  noise                      — Gaussian jitter added per tick
  stuck                      — value frozen at injection time
  dropout / intermittent     — value intermittently drops to zero
  step_change                — instantaneous jump at injection time
"""

from __future__ import annotations

import math
import random
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class FaultType(str, Enum):
    BIAS = "bias"
    STEP_BIAS = "step_bias"
    SCALE_FACTOR = "scale_factor"
    DRIFT = "drift"
    RAMP_DRIFT = "ramp_drift"
    NOISE = "noise"
    STUCK = "stuck"
    DROPOUT = "dropout"
    INTERMITTENT_DROPOUT = "intermittent_dropout"
    STEP_CHANGE = "step_change"


class FaultTier(str, Enum):
    SENSOR = "sensor"    # Corrupts reported telemetry overlay
    SYSTEM = "system"    # Modifies ground-truth physics state


class Subsystem(str, Enum):
    POWER = "power"
    EPS = "EPS (Power)"
    THERMAL = "thermal"
    TCS = "TCS (Thermal)"
    ATTITUDE = "attitude"
    ADCS = "ADCS (Attitude)"
    STORAGE = "storage"
    CDH = "CDH (Storage)"
    COMMS = "comms"
    RF = "COMMS (RF)"


SUBSYSTEM_VARIABLES: dict[str, list[str]] = {
    "power": ["battery_soc", "bus_voltage", "solar_input_w", "power_draw_w"],
    "thermal": ["temp_c", "heater_on"],
    "attitude": ["attitude_deg", "slew_rate_dps", "target_attitude_deg"],
    "storage": ["storage_used_mb", "storage_capacity_mb"],
    "comms": ["link_margin_db", "comms_active", "in_contact"],
}


class FaultBehavior(ABC):
    """Base class for fault application logic."""

    @abstractmethod
    def apply(self, true_value: float, t: int, trigger_t: int) -> float:
        """Compute the corrupted value."""


class BiasFault(FaultBehavior):
    """Constant offset added to true value."""

    def __init__(self, offset: float = 5.0, bias: float | None = None, **kwargs):
        self.offset = bias if bias is not None else offset

    def apply(self, true_value: float, t: int, trigger_t: int) -> float:
        return true_value + self.offset


class ScaleFactorFault(FaultBehavior):
    """Multiplicative scaling factor."""

    def __init__(self, scale: float = 0.5, **kwargs):
        self.scale = scale

    def apply(self, true_value: float, t: int, trigger_t: int) -> float:
        return true_value * self.scale


class DriftFault(FaultBehavior):
    """Linearly increasing or decreasing offset over time."""

    def __init__(self, rate: float = 0.1, direction: str = "up", **kwargs):
        self.rate = rate
        self.sign = 1.0 if direction == "up" else -1.0

    def apply(self, true_value: float, t: int, trigger_t: int) -> float:
        elapsed = max(0, t - trigger_t)
        return true_value + self.sign * self.rate * elapsed


class NoiseFault(FaultBehavior):
    """Gaussian jitter added per tick."""

    def __init__(self, sigma: float = 1.0, seed: int | None = None, **kwargs):
        self.sigma = sigma
        self._rng = random.Random(seed)

    def apply(self, true_value: float, t: int, trigger_t: int) -> float:
        return true_value + self._rng.gauss(0.0, self.sigma)


class StuckFault(FaultBehavior):
    """Value frozen at injection time or fixed constant."""

    def __init__(self, stuck_value: float | None = None, **kwargs):
        self.stuck_value = stuck_value
        self._captured = False

    def apply(self, true_value: float, t: int, trigger_t: int) -> float:
        if self.stuck_value is None and not self._captured:
            self.stuck_value = true_value
            self._captured = True
        return self.stuck_value if self.stuck_value is not None else true_value


class DropoutFault(FaultBehavior):
    """Value intermittently drops to zero."""

    def __init__(self, probability: float = 0.3, drop_probability: float | None = None, duration_ticks: int = 1, **kwargs):
        p = drop_probability if drop_probability is not None else probability
        self.probability = max(0.0, min(1.0, p))
        self.duration_ticks = max(1, duration_ticks)

    def apply(self, true_value: float, t: int, trigger_t: int) -> float:
        hash_val = ((t * 2654435761) & 0xFFFFFFFF) / 0xFFFFFFFF
        if hash_val < self.probability:
            return 0.0
        return true_value


class StepChangeFault(FaultBehavior):
    """Instantaneous permanent delta jump."""

    def __init__(self, delta: float = 10.0, **kwargs):
        self.delta = delta

    def apply(self, true_value: float, t: int, trigger_t: int) -> float:
        if t >= trigger_t:
            return true_value + self.delta
        return true_value


def create_fault_behavior(fault_type: str, parameters: dict) -> FaultBehavior:
    """Create a FaultBehavior instance with flexible type matching and parameter defaults."""
    ft = fault_type.lower().strip()
    if ft in ("bias", "step_bias"):
        return BiasFault(**parameters)
    elif ft in ("scale", "scale_factor"):
        return ScaleFactorFault(**parameters)
    elif ft in ("drift", "ramp_drift"):
        return DriftFault(**parameters)
    elif ft in ("noise", "gaussian"):
        return NoiseFault(**parameters)
    elif ft in ("stuck", "freeze"):
        return StuckFault(**parameters)
    elif ft in ("dropout", "intermittent", "intermittent_dropout"):
        return DropoutFault(**parameters)
    elif ft in ("step_change", "step"):
        return StepChangeFault(**parameters)
    else:
        # Fallback to bias
        return BiasFault(offset=float(parameters.get("bias", parameters.get("offset", 1.0))))


class FaultInjectionRequest(BaseModel):
    """API request body for injecting a fault."""

    fault_type: str = Field(description="Fault type identifier")
    tier: str = Field(default="system", description="'sensor' or 'system'")
    target_subsystem: str = Field(default="power", description="Subsystem to target")
    target_variable: str = Field(description="Specific state variable to affect")
    trigger_t: int = Field(default=0, ge=0, description="Simulation tick to fire")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Parameters for fault behavior")
    description: str = Field(default="", description="Human-readable description")
    duration_ticks: int = Field(default=60, description="Duration before clear")


class FaultCatalogEntry(BaseModel):
    fault_id: str
    name: str
    subsystem: str
    target_variable: str
    fault_type: str
    tier: str = "system"
    description: str
    default_params: dict[str, Any] = Field(default_factory=dict)
    applicable_subsystems: list[str] = Field(default_factory=list)
    parameter_schema: dict[str, Any] = Field(default_factory=dict)
    severity_hint: str = "medium"


FAULT_CATALOG: list[FaultCatalogEntry] = [
    FaultCatalogEntry(
        fault_id="eps_solar_degrade",
        name="Solar Panel Micro-Cracking / Debris",
        subsystem="EPS (Power)",
        target_variable="solar_input_w",
        fault_type="scale_factor",
        tier="system",
        description="Debris impact causes 45% reduction in solar array energy conversion.",
        default_params={"scale": 0.55},
        applicable_subsystems=["power", "EPS (Power)", "EPS"],
        parameter_schema={"scale": {"type": "float", "default": 0.55, "description": "Power scaling coefficient"}},
        severity_hint="high",
    ),
    FaultCatalogEntry(
        fault_id="eps_battery_cell_loss",
        name="Battery Cell Internal Disconnect",
        subsystem="EPS (Power)",
        target_variable="battery_soc",
        fault_type="step_bias",
        tier="system",
        description="Cell disconnect causes rapid 0.35 drop in nominal charge capacity.",
        default_params={"bias": -0.35},
        applicable_subsystems=["power", "EPS (Power)", "EPS"],
        parameter_schema={"bias": {"type": "float", "default": -0.35, "description": "Charge delta bias"}},
        severity_hint="critical",
    ),
    FaultCatalogEntry(
        fault_id="tcs_heater_stuck_on",
        name="Survival Heater Stuck ON (Relay Runaway)",
        subsystem="TCS (Thermal)",
        target_variable="temp_c",
        fault_type="ramp_drift",
        tier="system",
        description="Heater relay fails closed, continuously adding +0.4°C/s thermal load.",
        default_params={"rate": 0.4},
        applicable_subsystems=["thermal", "TCS (Thermal)", "TCS"],
        parameter_schema={"rate": {"type": "float", "default": 0.4, "description": "Thermal drift rate per tick"}},
        severity_hint="critical",
    ),
    FaultCatalogEntry(
        fault_id="adcs_wheel_friction",
        name="Reaction Wheel Bearing Friction",
        subsystem="ADCS (Attitude)",
        target_variable="attitude_deg",
        fault_type="bias",
        tier="system",
        description="Mechanical drag causes +18.2° attitude deviation from sun vector.",
        default_params={"offset": 18.2},
        applicable_subsystems=["attitude", "ADCS (Attitude)", "ADCS"],
        parameter_schema={"offset": {"type": "float", "default": 18.2, "description": "Attitude degree offset"}},
        severity_hint="medium",
    ),
    FaultCatalogEntry(
        fault_id="comms_pa_dropout",
        name="Transponder Carrier Signal Dropout",
        subsystem="COMMS (RF)",
        target_variable="link_margin_db",
        fault_type="intermittent_dropout",
        tier="sensor",
        description="S-band PA drops carrier signal during ground pass contact.",
        default_params={"drop_probability": 0.8},
        applicable_subsystems=["comms", "COMMS (RF)", "COMMS"],
        parameter_schema={"drop_probability": {"type": "float", "default": 0.8, "description": "Carrier loss probability"}},
        severity_hint="high",
    ),
    FaultCatalogEntry(
        fault_id="cdh_flash_seu",
        name="NAND Flash Bitflip (SEU) Overflow",
        subsystem="CDH (Storage)",
        target_variable="storage_used_mb",
        fault_type="noise",
        tier="sensor",
        description="Radiation SEU corrupts storage memory pointer telemetry.",
        default_params={"sigma": 180.0},
        applicable_subsystems=["storage", "CDH (Storage)", "CDH"],
        parameter_schema={"sigma": {"type": "float", "default": 180.0, "description": "Gaussian noise sigma"}},
        severity_hint="medium",
    ),
]
