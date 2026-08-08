"""
Aegis MOS — 24-Hour Telemetry Dataset Generator.
Generates full 86,400-second (24-hour, 16 LEO orbits) reference dataset
with complete deterministic physics for testing, validation, and dashboard queries.
"""

import json
import math
import os

def generate_24h_dataset():
    total_seconds = 86400  # 24 hours @ 1Hz
    orbit_period = 5400    # 90 minutes
    eclipse_fraction = 0.35
    contact_offset = 1200
    contact_window = 600

    dataset = []

    # Initial state
    battery_soc = 0.85
    temp_c = 22.0
    heater_on = False
    storage_mb = 256.0
    storage_capacity = 2048.0

    # Store sampled keypoints for fast JSON size while preserving complete 24h timeline
    for t in range(0, total_seconds, 10):  # Sample every 10s for 8,640 high-density records across 24h
        orbit_idx = t // orbit_period
        orbit_tick = t % orbit_period
        orbit_phase = orbit_tick / orbit_period
        in_eclipse = orbit_phase > (1.0 - eclipse_fraction)

        # Contact pass
        in_contact = contact_offset <= orbit_tick < (contact_offset + contact_window)

        # Solar input
        if in_eclipse:
            solar_w = 0.0
        else:
            angle_rad = math.sin((orbit_phase / (1.0 - eclipse_fraction)) * math.pi)
            solar_w = max(0.0, 7.0 * angle_rad)

        # Power draw
        power_draw_w = 2.0
        if in_contact:
            power_draw_w += 3.5
        if heater_on:
            power_draw_w += 1.5

        # Battery dynamics (10s step)
        net_power = solar_w - power_draw_w
        delta_soc = (net_power * 10) / (40.0 * 3600.0)
        battery_soc = max(0.05, min(1.0, battery_soc + delta_soc))

        # Bus voltage
        bus_voltage = 5.0 * (0.8 + 0.2 * battery_soc) + math.sin(t * 0.01) * 0.02

        # Thermal dynamics
        ambient = -18.0 if in_eclipse else 16.0
        heat_gen = power_draw_w * 0.6 + (3.5 if heater_on else 0.0)
        temp_c += ((ambient - temp_c) * 0.005 + heat_gen * 0.02) * 10

        if temp_c < 5.0:
            heater_on = True
        elif temp_c > 10.0:
            heater_on = False

        # Storage
        if in_contact:
            storage_mb = max(0.0, storage_mb - 8.0 * 10)
        else:
            storage_mb = min(storage_capacity, storage_mb + 1.2 * 10)

        # Link margin
        if in_contact:
            pass_prog = (orbit_tick - contact_offset) / contact_window
            link_margin = 2.0 + (6.0 - 2.0) * (1.0 - 4.0 * (pass_prog - 0.5) ** 2)
        else:
            link_margin = -999.0

        dataset.append({
            "t": t,
            "orbit_index": orbit_idx + 1,
            "orbit_phase": round(orbit_phase, 4),
            "in_eclipse": in_eclipse,
            "in_contact": in_contact,
            "solar_input_w": round(solar_w, 2),
            "power_draw_w": round(power_draw_w, 2),
            "battery_soc": round(battery_soc, 4),
            "bus_voltage": round(bus_voltage, 2),
            "temp_c": round(temp_c, 2),
            "heater_on": heater_on,
            "storage_used_mb": round(storage_mb, 1),
            "link_margin_db": round(link_margin, 1),
            "attitude_deg": round(math.sin(t * 0.002) * 1.5, 2)
        })

    output_path = os.path.join(os.path.dirname(__file__), "orbit_24h_telemetry.json")
    with open(output_path, "w") as f:
        json.dump({
            "total_records": len(dataset),
            "time_span_seconds": total_seconds,
            "total_orbits": 16,
            "sample_step_seconds": 10,
            "records": dataset
        }, f)
    print(f"Generated 24-hour reference dataset with {len(dataset)} records at {output_path}")

if __name__ == "__main__":
    generate_24h_dataset()
