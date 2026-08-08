"""
Aegis MOS — Subsystem Physics Engine.

Implements coupled CubeSat subsystem equations for the digital twin.
All parameters are plausible 3U CubeSat-class reference values.

Subsystem coupling chain (what makes this non-trivial):
  Attitude → Solar input → SOC → Bus voltage → Can we afford to slew/downlink?
  Power draw → Heat → Temperature → Heater activates → More power draw (feedback)
  Eclipse → No solar → SOC drops → Thermal drops → Heater kicks in → Faster SOC drain
  Downlink → Power draw up + Storage down → Can't downlink if SOC too low

These couplings are what make fault injection and anomaly detection meaningful —
a single fault propagates through multiple subsystems.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from simulator.state import SpacecraftState


@dataclass(frozen=True)
class CubeSatParams:
    """
    Reference parameters for a 3U CubeSat-class spacecraft.

    All values are plausible starting points from publicly documented
    CubeSat subsystem specifications. They are tunable, not exact.
    """

    # ── Power ────────────────────────────────────────────────────────
    battery_capacity_wh: float = 40.0       # Mid-range 3U CubeSat battery
    bus_voltage_nominal: float = 5.0         # Standard CubeSat bus voltage
    solar_panel_max_w: float = 7.0           # ~30% efficiency, 3U body-mount panels
    solar_efficiency: float = 0.28           # Multi-junction cell efficiency
    baseline_power_draw_w: float = 2.0       # Housekeeping load (OBC, sensors, etc.)
    downlink_power_draw_w: float = 3.5       # S-band transmitter
    slew_power_draw_w: float = 1.0           # Reaction wheel torquing
    observation_power_draw_w: float = 1.5    # Science instrument active
    heater_power_w: float = 1.5              # Survival heater

    # ── Thermal ──────────────────────────────────────────────────────
    thermal_mass_factor: float = 0.08        # °C change per W of net heat per tick
    heat_dissipation_coeff: float = 0.015    # Radiative dissipation rate
    space_temp_c: float = -270.0             # Deep space background temp
    heater_on_threshold_c: float = 5.0       # Heater activates below this
    heater_off_threshold_c: float = 10.0     # Heater deactivates above this (hysteresis)
    heat_fraction: float = 0.6              # Fraction of power draw that becomes heat

    # ── Attitude ─────────────────────────────────────────────────────
    max_slew_rate_dps: float = 2.0           # Max reaction wheel slew rate
    slew_gain: float = 0.3                   # Proportional control gain
    attitude_tolerance_deg: float = 0.5      # Dead-band tolerance

    # ── Storage ──────────────────────────────────────────────────────
    storage_capacity_mb: float = 2048.0      # 2 GB onboard storage
    observation_data_rate_mb: float = 5.0    # MB per tick during observation
    downlink_data_rate_mb: float = 8.0       # MB per tick during contact

    # ── Orbit ────────────────────────────────────────────────────────
    orbit_period_ticks: int = 5400           # ~90 min LEO orbit at 1Hz
    eclipse_fraction: float = 0.35           # ~35% of orbit in shadow
    contact_window_ticks: int = 600          # ~10 min ground pass per orbit
    contact_start_offset: int = 1200         # Ticks into orbit when pass starts

    # ── Comms ────────────────────────────────────────────────────────
    link_margin_nominal_db: float = 6.0      # Nominal link margin during contact
    link_margin_edge_db: float = 2.0         # Margin at edges of pass window


class PhysicsEngine:
    """
    Advances spacecraft state by one tick using coupled subsystem equations.

    This is a pure function of (current_state, params) → next_state.
    No side effects, no external state — deterministic for any given input.
    """

    def __init__(self, params: CubeSatParams | None = None):
        self.params = params or CubeSatParams()

    def step(self, state: SpacecraftState) -> SpacecraftState:
        """
        Compute the next spacecraft state from the current state.

        The order of operations matters:
          1. Orbital context (eclipse, contact windows)
          2. Attitude dynamics
          3. Solar input (depends on attitude + eclipse)
          4. Power budget (depends on all active subsystems)
          5. Battery SOC and bus voltage
          6. Thermal dynamics
          7. Storage dynamics
          8. Communications state
        """
        p = self.params

        # Work on a copy to avoid mutating the input
        s = state.model_copy(deep=True)

        # ── 1. Orbital context ──────────────────────────────────────
        s.orbit_phase = (s.t % p.orbit_period_ticks) / p.orbit_period_ticks
        s.in_eclipse = s.orbit_phase > (1.0 - p.eclipse_fraction)

        # Contact window: repeating ground pass window within each orbit
        orbit_tick = s.t % p.orbit_period_ticks
        contact_end = p.contact_start_offset + p.contact_window_ticks
        s.in_contact = p.contact_start_offset <= orbit_tick < contact_end
        s.comms_active = s.in_contact

        # Scheduled science observation pass in daylight
        s.is_observing = (2000 <= orbit_tick < 3200) and not s.in_eclipse

        # ── 2. Attitude dynamics ────────────────────────────────────
        attitude_error = s.target_attitude_deg - s.attitude_deg

        if abs(attitude_error) > p.attitude_tolerance_deg:
            # Proportional control with rate limiting
            commanded_rate = attitude_error * p.slew_gain
            s.slew_rate_dps = max(
                -p.max_slew_rate_dps,
                min(p.max_slew_rate_dps, commanded_rate),
            )
            s.attitude_deg += s.slew_rate_dps  # 1 tick = 1 second at 1Hz
            s.is_slewing = True
        else:
            s.slew_rate_dps = 0.0
            s.attitude_deg = s.target_attitude_deg  # Snap to target in dead-band
            s.is_slewing = False

        # ── 3. Solar input (Realistic Orbital Sunlight Arc) ─────────
        if s.in_eclipse:
            s.solar_input_w = 0.0
        else:
            # Smooth diurnal solar insolation arc along sunlit orbit segment
            sunlit_fraction = max(0.01, 1.0 - p.eclipse_fraction)
            sun_progress = s.orbit_phase / sunlit_fraction
            diurnal_curve = max(0.0, math.sin(math.pi * sun_progress))
            
            # Attitude pointing factor
            angle_rad = math.radians(abs(s.attitude_deg))
            pointing_eff = max(0.25, math.cos(angle_rad))
            s.solar_input_w = round(p.solar_panel_max_w * diurnal_curve * pointing_eff, 2)

        # ── 4. Power budget ─────────────────────────────────────────
        power_draw = p.baseline_power_draw_w

        if s.comms_active and s.in_contact:
            power_draw += p.downlink_power_draw_w

        if s.is_slewing:
            power_draw += p.slew_power_draw_w

        if s.is_observing:
            power_draw += p.observation_power_draw_w

        if s.heater_on:
            power_draw += p.heater_power_w

        s.power_draw_w = round(power_draw, 2)

        # ── 5. Battery SOC & bus voltage ────────────────────────────
        net_power_w = s.solar_input_w - s.power_draw_w

        # SOC change per tick (1 second at 1Hz) with internal series resistance
        delta_soc = net_power_w / (p.battery_capacity_wh * 1800.0)
        s.battery_soc = max(0.18, min(0.95, s.battery_soc + delta_soc))

        # Dynamic Bus Voltage: nominal 4.75V .. 5.00V
        s.bus_voltage = round(p.bus_voltage_nominal * (0.84 + 0.16 * s.battery_soc), 2)

        # ── 6. Thermal dynamics (Calibrated Single-Zone 24H Dataset Model) ──
        # In sunlight: radiative equilibrium warms to nominal +25°C .. +36°C
        # In eclipse: radiative cooling drops toward -12°C .. -18°C
        # Survival heater hysteresis maintains internal bus above safe thresholds
        target_temp = 28.5 if not s.in_eclipse else (-14.0 if not s.heater_on else 7.5)
        target_temp += (s.power_draw_w - p.baseline_power_draw_w) * 2.2

        # Smooth thermal capacitance relaxation (orbital time constant)
        alpha = 0.004
        s.temp_c = round(s.temp_c + alpha * (target_temp - s.temp_c), 2)

        # Heater control with hysteresis to prevent rapid cycling
        if s.temp_c < p.heater_on_threshold_c:
            s.heater_on = True
        elif s.temp_c > p.heater_off_threshold_c:
            s.heater_on = False
        # Between thresholds: heater stays in its current state (hysteresis)

        # ── 7. Storage dynamics ─────────────────────────────────────
        if s.is_observing:
            s.storage_used_mb += p.observation_data_rate_mb

        if s.comms_active and s.in_contact:
            s.storage_used_mb -= p.downlink_data_rate_mb

        # Clamp to valid range
        s.storage_used_mb = max(120.0, min(p.storage_capacity_mb, s.storage_used_mb))

        # ── 8. Communications state ─────────────────────────────────
        if s.in_contact:
            # Link margin varies across the pass window
            orbit_tick = s.t % p.orbit_period_ticks
            pass_progress = (orbit_tick - p.contact_start_offset) / p.contact_window_ticks
            # Parabolic profile: strongest at center of pass, weaker at edges
            edge_factor = 1.0 - 4.0 * (pass_progress - 0.5) ** 2
            s.link_margin_db = (
                p.link_margin_edge_db
                + (p.link_margin_nominal_db - p.link_margin_edge_db) * edge_factor
            )
        else:
            s.link_margin_db = -999.0
            # Auto-deactivate comms when out of contact
            if s.comms_active:
                s.comms_active = False

        return s
