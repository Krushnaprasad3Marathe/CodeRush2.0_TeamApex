"""
Aegis MOS — Fault Type Catalog (F3).

Defines the six canonical fault types that can be injected into any
numeric telemetry variable. Every fault is keyed to simulation time
(state.t) for deterministic replay.

Fault types:
  bias        — constant offset added to the true value
  drift       — linearly increasing offset over time
  noise       — Gaussian jitter added per tick
  stuck       — value frozen at the moment of injection (or a fixed value)
  dropout     — value intermittently drops to zero
  step_change — instantaneous jump at injection time
"""

from __future__ import annotations

import math
import random
from abc import ABC, abstractmethod
from enum import Enum

from pydantic import BaseModel, Field


class FaultType(str, Enum):
    BIAS = "bias"
    DRIFT = "drift"
    NOISE = "noise"
    STUCK = "stuck"
    DROPOUT = "dropout"
    STEP_CHANGE = "step_change"


class FaultTier(str, Enum):
    SENSOR = "sensor"    # Only corrupts reported telemetry
    SYSTEM = "system"    # Modifies actual physics state


class Subsystem(str, Enum):
    POWER = "power"
    THERMAL = "thermal"
    ATTITUDE = "attitude"
    STORAGE = "storage"
    COMMS = "comms"


# ── Map subsystems to injectable variables ──────────────────────────
SUBSYSTEM_VARIABLES: dict[str, list[str]] = {
    "power": ["battery_soc", "bus_voltage", "solar_input_w", "power_draw_w"],
    "thermal": ["temp_c"],
    "attitude": ["attitude_deg", "slew_rate_dps"],
    "storage": ["storage_used_mb"],
    "comms": ["link_margin_db"],
}


# ── Abstract base for fault behaviors ───────────────────────────────
class FaultBehavior(ABC):
    """Base class for fault application logic."""

    @abstractmethod
    def apply(self, true_value: float, t: int, trigger_t: int) -> float:
        """
        Compute the faulted value.

        Args:
            true_value: The ground-truth value from physics.
            t: Current simulation tick.
            trigger_t: Tick at which this fault was activated.

        Returns:
            The corrupted value.
        """


class BiasFault(FaultBehavior):
    """Constant offset added to the true value."""

    def __init__(self, offset: float = 5.0):
        self.offset = offset

    def apply(self, true_value: float, t: int, trigger_t: int) -> float:
        return true_value + self.offset


class DriftFault(FaultBehavior):
    """Linearly increasing offset over time since activation."""

    def __init__(self, rate: float = 0.1, direction: str = "up"):
        self.rate = rate
        self.sign = 1.0 if direction == "up" else -1.0

    def apply(self, true_value: float, t: int, trigger_t: int) -> float:
        elapsed = max(0, t - trigger_t)
        return true_value + self.sign * self.rate * elapsed


class NoiseFault(FaultBehavior):
    """Gaussian jitter added per tick (deterministic via seeded RNG)."""

    def __init__(self, sigma: float = 1.0, seed: int | None = None):
        self.sigma = sigma
        self._rng = random.Random(seed)

    def apply(self, true_value: float, t: int, trigger_t: int) -> float:
        noise = self._rng.gauss(0.0, self.sigma)
        return true_value + noise


class StuckFault(FaultBehavior):
    """
    Value frozen at injection time or at a fixed value.

    If stuck_value is None, the value at the moment of first application
    is captured and replayed forever.
    """

    def __init__(self, stuck_value: float | None = None):
        self.stuck_value = stuck_value
        self._captured = False

    def apply(self, true_value: float, t: int, trigger_t: int) -> float:
        if self.stuck_value is None and not self._captured:
            self.stuck_value = true_value
            self._captured = True
        return self.stuck_value if self.stuck_value is not None else true_value


class DropoutFault(FaultBehavior):
    """
    Value intermittently drops to zero.

    Uses a deterministic pattern based on tick modulus so replays
    produce identical dropout sequences.
    """

    def __init__(self, probability: float = 0.3, duration_ticks: int = 1):
        self.probability = max(0.0, min(1.0, probability))
        self.duration_ticks = max(1, duration_ticks)

    def apply(self, true_value: float, t: int, trigger_t: int) -> float:
        # Deterministic "random" based on tick — same tick always
        # produces the same dropout decision for replay fidelity
        hash_val = ((t * 2654435761) & 0xFFFFFFFF) / 0xFFFFFFFF
        if hash_val < self.probability:
            return 0.0
        return true_value


class StepChangeFault(FaultBehavior):
    """Instantaneous jump at injection time, persists thereafter."""

    def __init__(self, delta: float = 10.0):
        self.delta = delta

    def apply(self, true_value: float, t: int, trigger_t: int) -> float:
        if t >= trigger_t:
            return true_value + self.delta
        return true_value


# ── Factory ─────────────────────────────────────────────────────────
def create_fault_behavior(fault_type: str, parameters: dict) -> FaultBehavior:
    """Create a FaultBehavior instance from type string and parameters."""
    factories: dict[str, type[FaultBehavior]] = {
        "bias": BiasFault,
        "drift": DriftFault,
        "noise": NoiseFault,
        "stuck": StuckFault,
        "dropout": DropoutFault,
        "step_change": StepChangeFault,
    }
    cls = factories.get(fault_type)
    if cls is None:
        raise ValueError(f"Unknown fault type: {fault_type}")
    return cls(**parameters)


# ── Pydantic request model for API ──────────────────────────────────
class FaultInjectionRequest(BaseModel):
    """API request body for injecting a fault."""

    fault_type: FaultType = Field(description="One of: bias, drift, noise, stuck, dropout, step_change")
    tier: FaultTier = Field(description="'sensor' (reporting only) or 'system' (affects physics)")
    target_subsystem: Subsystem = Field(description="Subsystem to target")
    target_variable: str = Field(description="Specific state variable to affect")
    trigger_t: int = Field(ge=0, description="Simulation tick at which to fire")
    parameters: dict = Field(default_factory=dict, description="Fault-specific parameters")
    description: str = Field(default="", description="Human-readable description")


class FaultCatalogEntry(BaseModel):
    """A single entry in the fault catalog for UI display."""

    fault_type: FaultType
    description: str
    applicable_subsystems: list[Subsystem]
    parameter_schema: dict = Field(default_factory=dict)
    severity_hint: str = "medium"


# Pre-built catalog for the UI
FAULT_CATALOG: list[FaultCatalogEntry] = [
    FaultCatalogEntry(
        fault_type=FaultType.BIAS,
        description="Constant offset added to sensor reading",
        applicable_subsystems=list(Subsystem),
        parameter_schema={"offset": {"type": "float", "default": 5.0, "description": "Constant offset value"}},
        severity_hint="low",
    ),
    FaultCatalogEntry(
        fault_type=FaultType.DRIFT,
        description="Linearly increasing offset over time",
        applicable_subsystems=list(Subsystem),
        parameter_schema={
            "rate": {"type": "float", "default": 0.1, "description": "Drift rate per tick"},
            "direction": {"type": "str", "default": "up", "options": ["up", "down"]},
        },
        severity_hint="medium",
    ),
    FaultCatalogEntry(
        fault_type=FaultType.NOISE,
        description="Gaussian jitter added per tick",
        applicable_subsystems=list(Subsystem),
        parameter_schema={
            "sigma": {"type": "float", "default": 1.0, "description": "Standard deviation"},
        },
        severity_hint="low",
    ),
    FaultCatalogEntry(
        fault_type=FaultType.STUCK,
        description="Value frozen at injection time or fixed value",
        applicable_subsystems=list(Subsystem),
        parameter_schema={
            "stuck_value": {"type": "float|null", "default": None, "description": "Fixed value (null = freeze current)"},
        },
        severity_hint="high",
    ),
    FaultCatalogEntry(
        fault_type=FaultType.DROPOUT,
        description="Value intermittently drops to zero",
        applicable_subsystems=list(Subsystem),
        parameter_schema={
            "probability": {"type": "float", "default": 0.3, "description": "Dropout probability per tick"},
            "duration_ticks": {"type": "int", "default": 1, "description": "Duration of each dropout"},
        },
        severity_hint="high",
    ),
    FaultCatalogEntry(
        fault_type=FaultType.STEP_CHANGE,
        description="Instantaneous permanent jump in value",
        applicable_subsystems=list(Subsystem),
        parameter_schema={
            "delta": {"type": "float", "default": 10.0, "description": "Step change magnitude"},
        },
        severity_hint="medium",
    ),
]
