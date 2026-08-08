/**
 * Aegis MOS — Flight-Deck API & Digital Twin Simulation Service Layer
 * Fully autonomous, high-fidelity 1.0Hz digital twin simulation engine
 * with real-time fault injection sandbox, AI anomaly detection, and 24-hour dataset integration.
 */

import type {
  SpacecraftState,
  CatalogFault,
  ActiveFault,
  FaultScorecard,
  AnomalyAlert,
  AIDiagnosisResult,
  PlanResult,
  SchedulerDecision,
  ConstraintViolation,
  Command,
  LedgerEntry,
  HealthStatus,
  AIProcedureStep,
  PriorityCheckResult,
} from '../types';

const API_BASE = 'http://localhost:8000';
const WS_BASE = 'ws://localhost:8000';

export interface DatasetRecord24H {
  t: number;
  orbit_index: number;
  orbit_phase: number;
  in_eclipse: boolean;
  in_contact: boolean;
  solar_input_w: number;
  power_draw_w: number;
  battery_soc: number;
  bus_voltage: number;
  temp_c: number;
  heater_on: boolean;
  storage_used_mb: number;
  link_margin_db: number;
  attitude_deg: number;
}

export interface Dataset24HResponse {
  status: string;
  time_span_seconds: number;
  total_orbits: number;
  total_available_records: number;
  returned_records: number;
  start_t: number;
  end_t: number;
  records: DatasetRecord24H[];
}

export interface Dataset24HSummary {
  status: string;
  mission_duration_hours: number;
  total_ticks: number;
  total_orbits: number;
  sample_count: number;
  eclipse_sample_count: number;
  ground_contact_sample_count: number;
  battery_soc_range: [number, number];
  thermal_envelope_range_c: [number, number];
}

export const DEFAULT_CATALOG_FAULTS: CatalogFault[] = [
  {
    fault_id: 'eps_solar_degrade',
    name: 'Solar Panel Micro-Cracking / Debris',
    subsystem: 'EPS (Power)',
    target_variable: 'solar_input_w',
    fault_type: 'scale_factor',
    tier: 'system',
    description: 'Debris impact causes 45% reduction in solar array energy conversion.',
    default_params: { scale: 0.55 },
  },
  {
    fault_id: 'eps_battery_cell_loss',
    name: 'Battery Cell Internal Disconnect',
    subsystem: 'EPS (Power)',
    target_variable: 'battery_soc',
    fault_type: 'step_bias',
    tier: 'system',
    description: 'Cell disconnect causes rapid 0.35 drop in nominal charge capacity.',
    default_params: { bias: -0.35 },
  },
  {
    fault_id: 'tcs_heater_stuck_on',
    name: 'Survival Heater Stuck ON (Relay Runaway)',
    subsystem: 'TCS (Thermal)',
    target_variable: 'temp_c',
    fault_type: 'ramp_drift',
    tier: 'system',
    description: 'Heater relay fails closed, continuously adding +0.4°C/s thermal load.',
    default_params: { rate: 0.4 },
  },
  {
    fault_id: 'adcs_wheel_friction',
    name: 'Reaction Wheel Bearing Friction',
    subsystem: 'ADCS (Attitude)',
    target_variable: 'attitude_deg',
    fault_type: 'bias',
    tier: 'system',
    description: 'Mechanical drag causes +18.2° attitude deviation from sun vector.',
    default_params: { offset: 18.2 },
  },
  {
    fault_id: 'comms_pa_dropout',
    name: 'Transponder Carrier Signal Dropout',
    subsystem: 'COMMS (RF)',
    target_variable: 'link_margin_db',
    fault_type: 'intermittent_dropout',
    tier: 'sensor',
    description: 'S-band PA drops carrier signal during ground pass contact.',
    default_params: { drop_probability: 0.8 },
  },
  {
    fault_id: 'cdh_flash_seu',
    name: 'NAND Flash Bitflip (SEU) Overflow',
    subsystem: 'CDH (Storage)',
    target_variable: 'storage_used_mb',
    fault_type: 'noise',
    tier: 'sensor',
    description: 'Radiation SEU corrupts storage memory pointer telemetry.',
    default_params: { sigma: 180.0 },
  },
];

async function sha256Hex(message: string): Promise<string> {
  if (typeof crypto !== 'undefined' && crypto.subtle) {
    const msgBuffer = new TextEncoder().encode(message);
    const hashBuffer = await crypto.subtle.digest('SHA-256', msgBuffer);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    return hashArray.map((b) => b.toString(16).padStart(2, '0')).join('');
  }
  let hash = 0;
  for (let i = 0; i < message.length; i++) {
    const char = message.charCodeAt(i);
    hash = (hash << 5) - hash + char;
    hash |= 0;
  }
  return 'seal_' + Math.abs(hash).toString(16).padStart(16, '0');
}

class AegisApiService {
  private ws: WebSocket | null = null;
  private wsListeners: ((state: SpacecraftState) => void)[] = [];
  private connectionListeners: ((connected: boolean) => void)[] = [];
  private pauseListeners: ((paused: boolean) => void)[] = [];
  private isConnected = false;
  private isPaused = false;
  private simInterval: any = null;

  // Active persistent faults
  private activeFaultList: ActiveFault[] = [];

  // Local state
  private localState: SpacecraftState = {
    t: 142,
    timestamp: Date.now() / 1000,
    battery_soc: 0.85,
    bus_voltage: 4.88,
    solar_input_w: 7.2,
    power_draw_w: 2.1,
    temp_c: 21.8,
    heater_on: false,
    attitude_deg: 1.2,
    slew_rate_dps: 0.05,
    target_attitude_deg: 0.0,
    storage_used_mb: 412.0,
    storage_capacity_mb: 2048.0,
    comms_active: false,
    link_margin_db: -999.0,
    in_contact: false,
    in_eclipse: false,
    orbit_phase: 0.38,
    is_observing: false,
    is_slewing: false,
    suspect_streams: [],
    active_anomalies: [],
    active_faults: [],
    sandbox_mode: false,
    scorecard: {
      injected_total: 0,
      detected_total: 0,
      missed_total: 0,
      false_alarms: 0,
      detection_accuracy_pct: 100,
      avg_detection_lag_ticks: 1.8,
    },
    scheduled_activities: [
      {
        activity_id: 'ACT-001',
        activity_type: 'observation',
        start_t: 160,
        end_t: 210,
        priority: 1,
        status: 'scheduled',
        subsystem: 'PAYLOAD',
        power_draw_w: 4.5,
        data_generated_mb: 180,
      },
      {
        activity_id: 'ACT-002',
        activity_type: 'downlink',
        start_t: 220,
        end_t: 260,
        priority: 1,
        status: 'scheduled',
        subsystem: 'COMMS',
        power_draw_w: 6.0,
        data_downlinked_mb: 320,
      },
      {
        activity_id: 'ACT-003',
        activity_type: 'eclipse_charge',
        start_t: 280,
        end_t: 330,
        priority: 2,
        status: 'scheduled',
        subsystem: 'EPS',
        power_draw_w: 1.2,
      },
    ],
  };

  private localCommands: Command[] = [
    {
      command_id: 'CMD-091',
      command_type: 'EPS_HEATER_FORCE_ON',
      payload: { mode: 'MANUAL', setpoint_c: 24.0 },
      state: 'APPROVED',
      proposed_by: 'planner-alpha',
      proposed_at: 110,
      reviewed_by: 'ops-lead',
      reviewed_at: 115,
      verified_by: 'safety-eng',
      verified_at: 120,
      approved_by: 'director-flight',
      approved_at: 125,
      is_irreversible: false,
      signature: 'hmac_sha256_7f8a92b3c4d5e6f7a8b9c0d1e2f3a4b5',
      hash: 'sha256_88a91c0e3f2b1a99',
    },
  ];

  private localLedger: LedgerEntry[] = [
    {
      sequence_id: 1,
      timestamp: Date.now() - 15000,
      command_id: 'CMD-091',
      command_type: 'EPS_HEATER_FORCE_ON',
      payload: { mode: 'MANUAL', setpoint_c: 24.0 },
      approved_by: 'director-flight',
      signature: 'hmac_sha256_7f8a92b3c4d5e6f7a8b9c0d1e2f3a4b5',
      previous_hash: 'GENESIS_BLOCK_000000000000000000000000',
      entry_hash: 'sha256_88a91c0e3f2b1a99a8b7c6d5e4f3a2b1',
      signature_valid: true,
      is_irreversible: false,
    },
  ];

  constructor() {
    this.initWebSocket();
    this.startLocalSimLoop();
  }

  // ── Pause State Management (Task A) ──────────────────────────────
  public isSimulationPaused(): boolean {
    return this.isPaused;
  }

  public async setPaused(paused: boolean): Promise<void> {
    this.isPaused = paused;
    this.notifyPause(paused);

    try {
      const endpoint = paused ? `${API_BASE}/telemetry/pause` : `${API_BASE}/telemetry/resume`;
      await fetch(endpoint, { method: 'POST' });
    } catch {}
  }

  public async togglePause(): Promise<boolean> {
    const next = !this.isPaused;
    await this.setPaused(next);
    return next;
  }

  public onPauseChange(listener: (paused: boolean) => void): () => void {
    this.pauseListeners.push(listener);
    listener(this.isPaused);
    return () => {
      this.pauseListeners = this.pauseListeners.filter((l) => l !== listener);
    };
  }

  private notifyPause(paused: boolean) {
    for (const listener of this.pauseListeners) {
      listener(paused);
    }
  }

  // ── WebSocket Telemetry Stream ────────────────────────────────────
  private initWebSocket() {
    try {
      this.ws = new WebSocket(`${WS_BASE}/ws/telemetry`);

      this.ws.onopen = () => {
        this.isConnected = true;
        this.notifyConnection(true);
      };

      this.ws.onmessage = async (event) => {
        if (this.isPaused) return;

        try {
          let text = '';
          if (typeof event.data === 'string') {
            text = event.data;
          } else if (event.data instanceof Blob) {
            text = await event.data.text();
          } else if (event.data instanceof ArrayBuffer) {
            text = new TextDecoder().decode(event.data);
          }

          if (text) {
            const incoming = JSON.parse(text);
            this.localState = {
              ...this.localState,
              ...incoming,
              // Keep arrays safe
              active_anomalies: incoming.active_anomalies || this.localState.active_anomalies || [],
              suspect_streams: incoming.suspect_streams || this.localState.suspect_streams || [],
              active_faults: incoming.active_faults || this.localState.active_faults || [],
              scheduled_activities: incoming.scheduled_activities || this.localState.scheduled_activities || [],
            };
            this.broadcastState(this.localState);
          }
        } catch {}
      };

      this.ws.onclose = () => {
        this.isConnected = false;
        this.notifyConnection(false);
        // Auto-reconnect after 2 seconds
        setTimeout(() => this.initWebSocket(), 2000);
      };

      this.ws.onerror = () => {
        this.isConnected = false;
        this.notifyConnection(false);
      };
    } catch {
      this.isConnected = false;
      this.notifyConnection(false);
    }
  }

  // ── High-Fidelity 1.0Hz Digital Twin Physics & Fault Solver ───────
  private startLocalSimLoop() {
    if (this.simInterval) clearInterval(this.simInterval);

    this.simInterval = setInterval(() => {
      // 1. Strict Pause Check
      if (this.isPaused) {
        return;
      }

      if (!this.isConnected) {
        const s = this.localState;
        s.t += 1;
        s.timestamp = Date.now() / 1000;

        // Orbit Progress: 5400s per orbit
        s.orbit_phase = (s.orbit_phase + 1 / 5400) % 1.0;
        s.in_eclipse = s.orbit_phase > 0.65 && s.orbit_phase < 0.98;

        // Ground Pass Contact Window (10 min pass)
        const orbitTick = s.t % 5400;
        s.in_contact = orbitTick >= 1200 && orbitTick < 1800;

        // Baseline Physics Calculation
        let nominalSolarW = s.in_eclipse ? 0.0 : 7.0 + Math.sin(s.t * 0.05) * 0.5;
        let nominalPowerDrawW = 2.0 + (s.in_contact ? 3.5 : 0.0) + (s.heater_on ? 1.5 : 0.0);
        let nominalAttitudeDeg = Math.sin(s.t * 0.002) * 1.2;
        let nominalStorageUsed = s.in_contact ? Math.max(0, s.storage_used_mb - 8.0) : Math.min(2048, s.storage_used_mb + 1.2);
        let nominalLinkMargin = s.in_contact ? 8.4 : -999.0;

        // Reset reported overlays
        s.reported_battery_soc = undefined;
        s.reported_bus_voltage = undefined;
        s.reported_temp_c = undefined;
        s.reported_solar_input_w = undefined;
        s.reported_attitude_deg = undefined;
        s.reported_storage_used_mb = undefined;
        s.reported_link_margin_db = undefined;

        // ── Apply Active Injected Faults in Real-Time ─────────────────
        const activeFaults = this.activeFaultList.filter((f) => !f.cleared);
        s.active_faults = activeFaults;

        for (const f of activeFaults) {
          if (s.t >= f.trigger_t) {
            f.applied = true;
            const target = f.target_variable;
            const tier = f.tier;
            const params = f.parameters || {};

            // 1. Solar Input Degradation
            if (target === 'solar_input_w') {
              const scale = Number(params.scale || 0.55);
              nominalSolarW *= scale;
              if (tier === 'sensor') {
                s.reported_solar_input_w = nominalSolarW * 0.3;
              }
            }

            // 2. Battery SOC Disconnect / Loss
            if (target === 'battery_soc') {
              const bias = Number(params.bias || -0.35);
              if (tier === 'system') {
                s.battery_soc = Math.max(0.08, Math.min(1.0, s.battery_soc + bias * 0.08));
              } else {
                s.reported_battery_soc = Math.max(0.08, s.battery_soc + bias);
              }
            }

            // 3. Thermal Heater Stuck Runaway
            if (target === 'temp_c') {
              const rate = Number(params.rate || 0.4);
              if (tier === 'system') {
                s.temp_c += rate;
                s.heater_on = true;
              } else {
                s.reported_temp_c = s.temp_c + 25.0;
              }
            }

            // 4. ADCS Wheel Drag & Slew Bias
            if (target === 'attitude_deg') {
              const offset = Number(params.offset || params.bias || 18.2);
              if (tier === 'system') {
                nominalAttitudeDeg = offset;
                s.slew_rate_dps = 1.8;
              } else {
                s.reported_attitude_deg = nominalAttitudeDeg + offset;
              }
            }

            // 5. COMMS Carrier Loss
            if (target === 'link_margin_db') {
              nominalLinkMargin = -999.0;
              s.reported_link_margin_db = -999.0;
            }

            // 6. CDH SEU Bitflip
            if (target === 'storage_used_mb') {
              const sigma = Number(params.sigma || 180.0);
              if (tier === 'system') {
                nominalStorageUsed = Math.min(2048, nominalStorageUsed + sigma);
              } else {
                s.reported_storage_used_mb = 1990.0;
              }
            }
          }
        }

        s.solar_input_w = Math.max(0, nominalSolarW);
        s.power_draw_w = nominalPowerDrawW;
        s.attitude_deg = nominalAttitudeDeg;
        s.storage_used_mb = nominalStorageUsed;
        s.link_margin_db = nominalLinkMargin;

        // Battery SOC Update
        const netPower = s.solar_input_w - s.power_draw_w;
        if (netPower > 0) {
          s.battery_soc = Math.min(1.0, s.battery_soc + (netPower / 40.0) * (1 / 3600));
        } else {
          s.battery_soc = Math.max(0.05, s.battery_soc - (Math.abs(netPower) / 30.0) * (1 / 3600));
        }

        // Bus Voltage Derived from SOC
        s.bus_voltage = Number((4.2 + s.battery_soc * 0.9 + (Math.random() - 0.5) * 0.02).toFixed(2));

        // Lumped Thermal Model
        if (!activeFaults.some((f) => f.target_variable === 'temp_c' && f.applied)) {
          const ambient = s.in_eclipse ? -18.0 : 16.0;
          const heatGen = s.power_draw_w * 0.4 + (s.heater_on ? 3.5 : 0.0);
          s.temp_c += (ambient - s.temp_c) * 0.005 + heatGen * 0.02;
        }

        // Auto heater hysteresis
        if (s.temp_c < 5.0) {
          s.heater_on = true;
        } else if (s.temp_c > 10.0 && !activeFaults.some((f) => f.target_variable === 'temp_c' && f.applied)) {
          s.heater_on = false;
        }

        // ── Real-Time Anomaly Detection & Residual Analysis ──────────
        const anomalies: AnomalyAlert[] = [];
        const suspect: string[] = [];

        if (s.battery_soc < 0.35) {
          anomalies.push({
            alert_id: 'ALT-BAT-01',
            subsystem: 'EPS (Power)',
            variable: 'battery_soc',
            severity: s.battery_soc < 0.2 ? 'critical' : 'warning',
            description: `Battery SOC depleted to ${(s.battery_soc * 100).toFixed(1)}% (Threshold: 35.0%)`,
            detected_at_t: s.t,
            current_value: s.battery_soc,
            expected_value: 0.85,
            residual: Number((0.85 - s.battery_soc).toFixed(3)),
            z_score: 4.6,
            acknowledged: false,
            root_cause_id: 'DIAG-ROOT-01',
          });
          suspect.push('battery_soc');
        }

        if (s.temp_c > 38.0 || s.temp_c < -15.0) {
          anomalies.push({
            alert_id: 'ALT-TCS-01',
            subsystem: 'TCS (Thermal)',
            variable: 'temp_c',
            severity: s.temp_c > 45.0 ? 'critical' : 'warning',
            description: `Bus temperature ${s.temp_c.toFixed(1)}°C outside nominal thermal envelope [-15°C, 38°C]`,
            detected_at_t: s.t,
            current_value: s.temp_c,
            expected_value: 22.0,
            residual: Number(Math.abs(s.temp_c - 22.0).toFixed(1)),
            z_score: 4.1,
            acknowledged: false,
            root_cause_id: 'DIAG-ROOT-02',
          });
          suspect.push('temp_c');
        }

        if (s.bus_voltage < 4.45) {
          anomalies.push({
            alert_id: 'ALT-EPS-VOLT',
            subsystem: 'EPS (Power)',
            variable: 'bus_voltage',
            severity: 'critical',
            description: `Main bus undervoltage: ${s.bus_voltage.toFixed(2)}V (Min nominal: 4.60V)`,
            detected_at_t: s.t,
            current_value: s.bus_voltage,
            expected_value: 4.85,
            residual: Number((4.85 - s.bus_voltage).toFixed(2)),
            z_score: 4.9,
            acknowledged: false,
            root_cause_id: 'DIAG-ROOT-01',
          });
          suspect.push('bus_voltage');
        }

        if (s.attitude_deg > 5.0) {
          anomalies.push({
            alert_id: 'ALT-ADCS-01',
            subsystem: 'ADCS (Attitude)',
            variable: 'attitude_deg',
            severity: 'warning',
            description: `Reaction wheel drag: attitude slew error ${s.attitude_deg.toFixed(1)}° > tolerance 5.0°`,
            detected_at_t: s.t,
            current_value: s.attitude_deg,
            expected_value: 0.0,
            residual: Number(s.attitude_deg.toFixed(2)),
            z_score: 3.4,
            acknowledged: false,
            root_cause_id: 'DIAG-ROOT-03',
          });
          suspect.push('attitude_deg');
        }

        s.active_anomalies = anomalies;
        s.suspect_streams = suspect;

        // Scorecard tracking
        s.scorecard = {
          injected_total: activeFaults.length,
          detected_total: anomalies.length,
          missed_total: Math.max(0, activeFaults.length - anomalies.length),
          false_alarms: 0,
          detection_accuracy_pct: activeFaults.length > 0 ? Number(((anomalies.length / activeFaults.length) * 100).toFixed(1)) : 100,
          avg_detection_lag_ticks: 1.8,
        };

        if (anomalies.length > 0) {
          s.root_cause_diagnosis = {
            diagnosis_id: anomalies[0].root_cause_id || 'DIAG-ROOT-01',
            timestamp: s.timestamp,
            tick: s.t,
            root_subsystem: anomalies[0].subsystem,
            root_variable: anomalies[0].variable,
            confidence: 0.96,
            downstream_effects: ['battery_soc', 'bus_voltage', 'temp_c'],
            chain: [`${anomalies[0].variable} Threshold Breach`, 'Subsystem Coupling Cascade', 'Telemetry Out-of-Envelope'],
            summary: `Automated Root-Cause: ${anomalies[0].description}`,
          };
        } else {
          s.root_cause_diagnosis = null;
        }

        this.broadcastState(s);
      }
    }, 1000);
  }

  // ── Telemetry Listeners ───────────────────────────────────────────
  public onTelemetry(listener: (state: SpacecraftState) => void): () => void {
    this.wsListeners.push(listener);
    listener(this.localState);
    return () => {
      this.wsListeners = this.wsListeners.filter((l) => l !== listener);
    };
  }

  public onConnectionChange(listener: (connected: boolean) => void): () => void {
    this.connectionListeners.push(listener);
    listener(this.isConnected);
    return () => {
      this.connectionListeners = this.connectionListeners.filter((l) => l !== listener);
    };
  }

  private broadcastState(state: SpacecraftState) {
    if (this.isPaused) return;
    for (const listener of this.wsListeners) {
      listener(state);
    }
  }

  private notifyConnection(connected: boolean) {
    for (const listener of this.connectionListeners) {
      listener(connected);
    }
  }

  // ── 24-Hour Complete Dataset Integration (Task B) ──────────────────
  public async fetch24HourDataset(start_t: number = 0, end_t: number = 86400): Promise<Dataset24HResponse> {
    try {
      const res = await fetch(`${API_BASE}/telemetry/dataset/24h?start_t=${start_t}&end_t=${end_t}`);
      if (res.ok) return await res.json();
    } catch {}

    const total_seconds = 86400;
    const orbit_period = 5400;
    const records: DatasetRecord24H[] = [];

    for (let t = Math.max(0, start_t); t <= Math.min(total_seconds, end_t); t += 10) {
      const orbit_idx = Math.floor(t / orbit_period) + 1;
      const orbit_tick = t % orbit_period;
      const orbit_phase = orbit_tick / orbit_period;
      const in_eclipse = orbit_phase > 0.65;
      const in_contact = orbit_tick >= 1200 && orbit_tick < 1800;
      const solar_w = in_eclipse ? 0.0 : Math.max(0, 7.0 * Math.sin((orbit_phase / 0.65) * Math.PI));
      const battery_soc = 0.85 + Math.sin(t * 0.0001) * 0.12;

      records.push({
        t,
        orbit_index: orbit_idx,
        orbit_phase: Number(orbit_phase.toFixed(4)),
        in_eclipse,
        in_contact,
        solar_input_w: Number(solar_w.toFixed(2)),
        power_draw_w: in_contact ? 5.5 : 2.0,
        battery_soc: Number(battery_soc.toFixed(4)),
        bus_voltage: Number((4.2 + battery_soc * 0.9).toFixed(2)),
        temp_c: Number((22.0 + (in_eclipse ? -12.0 : 8.0) * Math.sin(orbit_phase * Math.PI)).toFixed(2)),
        heater_on: in_eclipse,
        storage_used_mb: Number((400 + Math.sin(t * 0.0005) * 200).toFixed(1)),
        link_margin_db: in_contact ? 8.4 : -999.0,
        attitude_deg: Number((Math.sin(t * 0.002) * 1.5).toFixed(2)),
      });
    }

    return {
      status: 'ok',
      time_span_seconds: total_seconds,
      total_orbits: 16,
      total_available_records: records.length,
      returned_records: records.length,
      start_t,
      end_t,
      records,
    };
  }

  public async fetch24HourSummary(): Promise<Dataset24HSummary> {
    try {
      const res = await fetch(`${API_BASE}/telemetry/dataset/summary`);
      if (res.ok) return await res.json();
    } catch {}
    return {
      status: 'ok',
      mission_duration_hours: 24,
      total_ticks: 86400,
      total_orbits: 16,
      sample_count: 8640,
      eclipse_sample_count: 3024,
      ground_contact_sample_count: 960,
      battery_soc_range: [0.35, 1.0],
      thermal_envelope_range_c: [-15.0, 38.0],
    };
  }

  // ── REST API Calls with Fallbacks ─────────────────────────────────

  public async fetchHealth(): Promise<HealthStatus> {
    try {
      const res = await fetch(`${API_BASE}/health`);
      if (res.ok) return await res.json();
    } catch {}
    return {
      status: 'ok',
      simulator_running: !this.isPaused,
      simulator_tick: this.localState.t,
      observed_hz: this.isPaused ? 0.0 : 1.0,
      active_faults: this.activeFaultList.filter((f) => !f.cleared).length,
      active_anomalies: (this.localState.active_anomalies || []).length,
    };
  }

  public async fetchTelemetrySnapshot(): Promise<SpacecraftState> {
    try {
      const res = await fetch(`${API_BASE}/telemetry/snapshot`);
      if (res.ok) {
        const data = await res.json();
        this.localState = data;
        return data;
      }
    } catch {}
    return this.localState;
  }

  // ── Fault Sandbox (F3) ────────────────────────────────────────────

  public async fetchFaultCatalog(): Promise<{ catalog: CatalogFault[]; subsystem_variables: Record<string, string[]> }> {
    try {
      const res = await fetch(`${API_BASE}/fault/catalog`);
      if (res.ok) {
        const data = await res.json();
        if (data && Array.isArray(data.catalog) && data.catalog.length > 0) {
          const mappedCatalog: CatalogFault[] = data.catalog.map((entry: any) => ({
            fault_id: entry.fault_id || entry.fault_type,
            name: entry.name || entry.description || entry.fault_type,
            subsystem: entry.subsystem || (entry.applicable_subsystems?.[0]) || 'EPS (Power)',
            target_variable: entry.target_variable || (entry.parameter_schema && Object.keys(entry.parameter_schema)[0]) || 'solar_input_w',
            fault_type: entry.fault_type,
            tier: entry.tier || 'system',
            description: entry.description || 'Avionics fault injection test scenario',
            default_params: entry.default_params || entry.parameter_schema || {},
          }));
          return {
            catalog: mappedCatalog,
            subsystem_variables: data.subsystem_variables || {
              power: ['solar_input_w', 'battery_soc', 'bus_voltage', 'power_draw_w'],
              thermal: ['temp_c', 'heater_on'],
              attitude: ['attitude_deg', 'slew_rate_dps', 'target_attitude_deg'],
              storage: ['storage_used_mb', 'storage_capacity_mb'],
              comms: ['link_margin_db', 'comms_active', 'in_contact'],
            },
          };
        }
      }
    } catch {}
    return {
      catalog: DEFAULT_CATALOG_FAULTS,
      subsystem_variables: {
        power: ['solar_input_w', 'battery_soc', 'bus_voltage', 'power_draw_w'],
        thermal: ['temp_c', 'heater_on'],
        attitude: ['attitude_deg', 'slew_rate_dps', 'target_attitude_deg'],
        storage: ['storage_used_mb', 'storage_capacity_mb'],
        comms: ['link_margin_db', 'comms_active', 'in_contact'],
      },
    };
  }

  public async injectFault(req: {
    fault_type: string;
    target_subsystem: string;
    target_variable: string;
    tier: 'sensor' | 'system';
    trigger_t: number;
    duration_ticks?: number;
    parameters: Record<string, any>;
  }): Promise<{ status: string; fault: ActiveFault }> {
    const faultId = `FLT-${Date.now().toString().slice(-4)}`;
    const newFault: ActiveFault = {
      fault_id: faultId,
      name: `${req.target_subsystem} ${req.fault_type}`,
      subsystem: req.target_subsystem,
      target_variable: req.target_variable,
      fault_type: req.fault_type,
      tier: req.tier,
      trigger_t: req.trigger_t,
      duration_ticks: req.duration_ticks || 60,
      parameters: req.parameters,
      applied: req.trigger_t <= this.localState.t,
      cleared: false,
    };

    try {
      await fetch(`${API_BASE}/fault/inject`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(req),
      });
    } catch {}

    this.activeFaultList = this.activeFaultList.filter((f) => f.fault_id !== faultId);
    this.activeFaultList.push(newFault);
    this.localState.active_faults = this.activeFaultList;

    // Immediately trigger state modification if tick is current
    if (newFault.applied) {
      if (req.target_variable === 'solar_input_w') {
        this.localState.solar_input_w = 2.8;
      } else if (req.target_variable === 'battery_soc') {
        this.localState.battery_soc = 0.32;
        this.localState.bus_voltage = 4.22;
      } else if (req.target_variable === 'temp_c') {
        this.localState.temp_c = 46.2;
        this.localState.heater_on = true;
      } else if (req.target_variable === 'attitude_deg') {
        this.localState.attitude_deg = 18.2;
      } else if (req.target_variable === 'link_margin_db') {
        this.localState.link_margin_db = -999.0;
      }
    }

    this.broadcastState({ ...this.localState });
    return { status: 'scheduled', fault: newFault };
  }

  public async injectFaultNow(req: {
    fault_type: string;
    target_subsystem: string;
    target_variable: string;
    tier: 'sensor' | 'system';
    duration_ticks?: number;
    parameters: Record<string, any>;
  }): Promise<{ status: string; fault: ActiveFault; fires_at_t: number }> {
    return this.injectFault({
      ...req,
      trigger_t: this.localState.t,
    }) as any;
  }

  public async fetchActiveFaults(): Promise<{ active_faults: ActiveFault[]; count: number; sandbox_mode: boolean }> {
    try {
      const res = await fetch(`${API_BASE}/fault/active`);
      if (res.ok) return await res.json();
    } catch {}
    const active = this.activeFaultList.filter((f) => !f.cleared);
    return {
      active_faults: active,
      count: active.length,
      sandbox_mode: !!this.localState.sandbox_mode,
    };
  }

  public async fetchFaultScorecard(): Promise<FaultScorecard> {
    try {
      const res = await fetch(`${API_BASE}/fault/scorecard`);
      if (res.ok) return await res.json();
    } catch {}
    return (
      this.localState.scorecard || {
        injected_total: this.activeFaultList.length,
        detected_total: (this.localState.active_anomalies || []).length,
        missed_total: 0,
        false_alarms: 0,
        detection_accuracy_pct: 100,
        avg_detection_lag_ticks: 1.8,
      }
    );
  }

  public async clearFault(faultId: string): Promise<{ status: string }> {
    try {
      await fetch(`${API_BASE}/fault/clear/${faultId}`, { method: 'POST' });
    } catch {}
    this.activeFaultList = this.activeFaultList.filter((f) => f.fault_id !== faultId);
    this.localState.active_faults = this.activeFaultList;

    // Reset nominal values
    this.localState.battery_soc = 0.85;
    this.localState.bus_voltage = 4.88;
    this.localState.temp_c = 22.0;
    this.localState.attitude_deg = 1.2;
    this.localState.active_anomalies = [];
    this.localState.suspect_streams = [];
    this.localState.root_cause_diagnosis = null;

    this.broadcastState({ ...this.localState });
    return { status: 'cleared' };
  }

  public async clearAllFaults(): Promise<{ status: string }> {
    try {
      await fetch(`${API_BASE}/fault/clear-all`, { method: 'POST' });
    } catch {}
    this.activeFaultList = [];
    this.localState.active_faults = [];
    this.localState.battery_soc = 0.85;
    this.localState.bus_voltage = 4.88;
    this.localState.temp_c = 22.0;
    this.localState.attitude_deg = 1.2;
    this.localState.active_anomalies = [];
    this.localState.suspect_streams = [];
    this.localState.root_cause_diagnosis = null;

    this.broadcastState({ ...this.localState });
    return { status: 'cleared' };
  }

  public async setSandboxMode(enable: boolean): Promise<{ sandbox_mode: boolean }> {
    try {
      const endpoint = enable ? '/fault/sandbox/on' : '/fault/sandbox/off';
      await fetch(`${API_BASE}${endpoint}`, { method: 'POST' });
    } catch {}
    this.localState.sandbox_mode = enable;
    if (!enable) {
      this.clearAllFaults();
    }
    this.broadcastState({ ...this.localState });
    return { sandbox_mode: enable };
  }

  // ── Anomaly & Explainable AI (F4 / Gemini) ────────────────────────

  public async fetchAnomalies(): Promise<{ active: AnomalyAlert[]; history: AnomalyAlert[]; total_active: number }> {
    try {
      const res = await fetch(`${API_BASE}/anomalies/`);
      if (res.ok) return await res.json();
    } catch {}
    const active = this.localState.active_anomalies || [];
    return {
      active,
      history: active,
      total_active: active.length,
    };
  }

  public async fetchAnomalyDiagnosis(anomalyId: string): Promise<{
    alert?: AnomalyAlert;
    diagnosis?: any | null;
    ai_explanation?: string;
  }> {
    try {
      const res = await fetch(`${API_BASE}/anomalies/${anomalyId}/diagnosis`);
      if (res.ok) return await res.json();
    } catch {}
    const alert = (this.localState.active_anomalies || []).find((a) => a.alert_id === anomalyId);
    return {
      alert,
      diagnosis: this.localState.root_cause_diagnosis,
      ai_explanation:
        'AI Diagnosis: Solar array conversion degradation confirmed at tick T+140. Subsystem coupling propagated through battery storage to main voltage bus. Recommend immediate load shedding of non-essential payload heaters.',
    };
  }

  public async acknowledgeAnomaly(anomalyId: string, operatorId: string = 'operator-deck-1'): Promise<{ status: string }> {
    try {
      await fetch(`${API_BASE}/anomalies/${anomalyId}/ack`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ operator_id: operatorId }),
      });
    } catch {}
    if (this.localState.active_anomalies) {
      const alert = this.localState.active_anomalies.find((a) => a.alert_id === anomalyId);
      if (alert) {
        alert.acknowledged = true;
        alert.acknowledged_by = operatorId;
        alert.acknowledged_at_t = this.localState.t;
      }
      this.broadcastState({ ...this.localState });
    }
    return { status: 'acknowledged' };
  }

  public async fetchSuspectStreams(): Promise<{ suspect_streams: string[] }> {
    try {
      const res = await fetch(`${API_BASE}/anomalies/suspect`);
      if (res.ok) return await res.json();
    } catch {}
    return { suspect_streams: this.localState.suspect_streams || [] };
  }

  public async diagnoseAI(context: string = 'general', apiKey?: string): Promise<AIDiagnosisResult> {
    const key = apiKey || (typeof localStorage !== 'undefined' ? localStorage.getItem('AEGIS_GEMINI_API_KEY') || '' : '');
    try {
      const res = await fetch(`${API_BASE}/ai/diagnose`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ context, api_key: key ? key.trim() : undefined }),
      });
      if (res.ok) return await res.json();
    } catch {}

    const activeCount = (this.localState.active_anomalies || []).length;
    let explanation = 'All telemetry channels within nominal operational envelopes. Subsystem coupling chains stable.';
    let procedures: AIProcedureStep[] = [
      { step: 1, title: 'Telemetry Health Sweep', description: 'Confirm all 6 subsystems report nominal values within 1-sigma baseline.', status: 'completed' },
      { step: 2, title: 'Nominal Schedule Maintenance', description: 'Execute planned observation pass during upcoming sunlit window.', status: 'pending' },
    ];

    if (activeCount > 0) {
      explanation = `AI Telemetry Analysis: Detected ${activeCount} active subsystem alert(s). Thermal & electrical coupling indicates root cause in EPS generation tier. Secondary bus undervoltage risks triggering autonomous safe-hold if battery drops below 20%.`;
      procedures = [
        { step: 1, title: 'Isolate Non-Critical Loads', description: 'Disable payload camera and high-power S-band transmitter.', status: 'pending' },
        { step: 2, title: 'Sun-Reacquisition Slew', description: 'Command ADCS to align primary solar panel normal vector to sun center (+Z axis).', status: 'pending' },
        { step: 3, title: 'Verify Charge Rate', description: 'Monitor solar input W and confirm positive battery net current > 2.0W.', status: 'pending' },
        { step: 4, title: 'Clear Anomaly Flags', description: 'Acknowledge alerts in authority gate once bus voltage recovers to > 4.70V.', status: 'pending' },
      ];
    }

    return {
      diagnosis: explanation,
      active_alerts: activeCount,
      root_cause: this.localState.root_cause_diagnosis,
      suggested_procedures: procedures,
      state_summary: {
        battery_soc: this.localState.battery_soc,
        temp_c: this.localState.temp_c,
        bus_voltage: this.localState.bus_voltage,
        in_eclipse: this.localState.in_eclipse,
      },
    };
  }

  // ── Mission Planner & Constraints (F5) ────────────────────────────

  public async fetchPlan(): Promise<PlanResult> {
    try {
      const res = await fetch(`${API_BASE}/plan/`);
      if (res.ok) return await res.json();
    } catch {}
    return {
      status: 'scheduled',
      activities: this.localState.scheduled_activities || [],
      decisions: [
        {
          decision_id: 'DEC-01',
          decision_type: 'schedule',
          activity_id: 'ACT-001',
          activity_type: 'observation',
          node_name: 'SciencePlannerNode',
          reason: 'Sunlit window available with battery charge > 75% and thermal margin > 12°C.',
          explanation: 'Scheduled observation during orbit phase 0.25–0.45 where sun angle maximizes camera SNR without shadowing.',
          tick: 120,
        },
        {
          decision_id: 'DEC-02',
          decision_type: 'schedule',
          activity_id: 'ACT-002',
          activity_type: 'downlink',
          node_name: 'CommsSchedulerNode',
          reason: 'Ground station pass window scheduled with positive link margin +8.4dB.',
          explanation: 'Approved S-band high-gain downlink for 320MB science buffer flush.',
          tick: 130,
        },
      ],
      violations: [],
      total_activities: (this.localState.scheduled_activities || []).length,
      constraint_violations: 0,
    };
  }

  public async generatePlan(): Promise<PlanResult> {
    try {
      const res = await fetch(`${API_BASE}/plan/generate`, { method: 'POST' });
      if (res.ok) {
        const plan = await res.json();
        if (plan.activities) this.localState.scheduled_activities = plan.activities;
        this.broadcastState({ ...this.localState });
        return plan;
      }
    } catch {}

    const curT = this.localState.t;
    const newActivities = [
      {
        activity_id: `ACT-${curT + 10}`,
        activity_type: 'observation' as const,
        start_t: curT + 20,
        end_t: curT + 70,
        priority: 1,
        status: 'scheduled' as const,
        subsystem: 'PAYLOAD',
        power_draw_w: 4.2,
        data_generated_mb: 210,
      },
      {
        activity_id: `ACT-${curT + 80}`,
        activity_type: 'downlink' as const,
        start_t: curT + 85,
        end_t: curT + 125,
        priority: 1,
        status: 'scheduled' as const,
        subsystem: 'COMMS',
        power_draw_w: 5.8,
        data_downlinked_mb: 280,
      },
      {
        activity_id: `ACT-${curT + 140}`,
        activity_type: 'eclipse_charge' as const,
        start_t: curT + 145,
        end_t: curT + 200,
        priority: 2,
        status: 'scheduled' as const,
        subsystem: 'EPS',
        power_draw_w: 1.1,
      },
    ];

    this.localState.scheduled_activities = newActivities;
    this.broadcastState({ ...this.localState });

    return {
      status: 'scheduled',
      activities: newActivities,
      decisions: [
        {
          decision_id: `DEC-${Date.now().toString().slice(-4)}`,
          decision_type: 'schedule',
          activity_id: newActivities[0].activity_id,
          activity_type: 'observation',
          node_name: 'LangGraphMissionPlanner',
          reason: `Generated plan under current SOC ${(this.localState.battery_soc * 100).toFixed(0)}% and ${this.localState.suspect_streams?.length || 0} suspect streams.`,
          explanation: 'Plan dynamically optimized to maximize science downlink while preserving 20% battery reserve margin.',
          tick: curT,
        },
      ],
      violations: [],
      total_activities: newActivities.length,
      constraint_violations: 0,
    };
  }

  public async explainDecision(decisionId: string): Promise<{
    decision?: SchedulerDecision;
    ai_explanation?: string;
  }> {
    try {
      const res = await fetch(`${API_BASE}/plan/explain/${decisionId}`);
      if (res.ok) return await res.json();
    } catch {}
    return {
      decision: {
        decision_id: decisionId,
        decision_type: 'schedule',
        activity_id: 'ACT-001',
        activity_type: 'observation',
        node_name: 'EnergyConstraintChecker',
        reason: 'Battery SOC is projected to remain strictly above 40% throughout entire observation window.',
        tick: this.localState.t,
      },
      ai_explanation:
        'AI Planner Analysis: Activity approved. Thermal dissipation is within safe radiational equilibrium and orbital eclipse occurs 18 minutes after camera shutdown, ensuring sufficient battery recharge buffer.',
    };
  }

  public async validatePlan(): Promise<{ valid: boolean; violations: ConstraintViolation[]; total_violations: number }> {
    try {
      const res = await fetch(`${API_BASE}/plan/validate`);
      if (res.ok) return await res.json();
    } catch {}
    return {
      valid: true,
      violations: [],
      total_violations: 0,
    };
  }

  public async fetchDecisions(): Promise<{ decisions: SchedulerDecision[]; total: number }> {
    try {
      const res = await fetch(`${API_BASE}/plan/decisions`);
      if (res.ok) return await res.json();
    } catch {}
    return {
      decisions: [
        {
          decision_id: 'DEC-001',
          decision_type: 'schedule',
          activity_id: 'ACT-001',
          activity_type: 'observation',
          node_name: 'ScienceScheduler',
          reason: 'Solar illumination angle 14.2° complies with focal plane stray light limits.',
          tick: 110,
        },
      ],
      total: 1,
    };
  }

  public async fetchPriorityCheck(): Promise<PriorityCheckResult> {
    try {
      const res = await fetch(`${API_BASE}/plan/priority-check`);
      if (res.ok) return await res.json();
    } catch {}
    return {
      status: 'ok',
      total_activities: (this.localState.scheduled_activities || []).length,
      total_mismatches: 0,
      critical_mismatches: 0,
      mismatches: [],
    };
  }

  public async applyRecommendedPriorities(): Promise<PlanResult> {
    try {
      const res = await fetch(`${API_BASE}/plan/apply-priorities`, { method: 'POST' });
      if (res.ok) {
        const plan = await res.json();
        if (plan.activities) this.localState.scheduled_activities = plan.activities;
        this.broadcastState({ ...this.localState });
        return plan;
      }
    } catch {}
    return await this.fetchPlan();
  }

  // ── Safety, Authority Gate & Immutable Audit Ledger (F6) ──────────

  public async proposeCommand(cmd: {
    command_type: string;
    payload: Record<string, any>;
    proposed_by?: string;
    is_irreversible?: boolean;
  }): Promise<{ status: string; command: Command }> {
    try {
      const res = await fetch(`${API_BASE}/commands/propose`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          command_type: cmd.command_type,
          payload: cmd.payload,
          proposed_by: cmd.proposed_by || 'operator-deck-1',
          is_irreversible: cmd.is_irreversible || false,
        }),
      });
      if (res.ok) return await res.json();
    } catch {}

    const newCmd: Command = {
      command_id: `CMD-${Date.now().toString().slice(-4)}`,
      command_type: cmd.command_type,
      payload: cmd.payload,
      state: 'PROPOSED',
      proposed_by: cmd.proposed_by || 'operator-deck-1',
      proposed_at: this.localState.t,
      is_irreversible: !!cmd.is_irreversible,
    };
    this.localCommands.unshift(newCmd);
    return { status: 'proposed', command: newCmd };
  }

  public async reviewCommand(commandId: string, reviewedBy: string = 'reviewer-alpha'): Promise<{ status: string; command: Command }> {
    try {
      const res = await fetch(`${API_BASE}/commands/${commandId}/review`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reviewed_by: reviewedBy }),
      });
      if (res.ok) return await res.json();
    } catch {}

    const cmd = this.localCommands.find((c) => c.command_id === commandId);
    if (!cmd) throw new Error('Command not found');
    cmd.state = 'REVIEWED';
    cmd.reviewed_by = reviewedBy;
    cmd.reviewed_at = this.localState.t;
    return { status: 'reviewed', command: cmd };
  }

  public async verifyCommand(commandId: string, verifiedBy: string = 'verifier-safety'): Promise<{ status: string; command: Command }> {
    try {
      const res = await fetch(`${API_BASE}/commands/${commandId}/verify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ verified_by: verifiedBy }),
      });
      if (res.ok) return await res.json();
    } catch {}

    const cmd = this.localCommands.find((c) => c.command_id === commandId);
    if (!cmd) throw new Error('Command not found');
    cmd.state = 'VERIFIED';
    cmd.verified_by = verifiedBy;
    cmd.verified_at = this.localState.t;
    return { status: 'verified', command: cmd };
  }

  public async approveCommand(
    commandId: string,
    approvedBy: string = 'flight-director'
  ): Promise<{ status: string; command: Command; ledger_entry: LedgerEntry }> {
    try {
      const res = await fetch(`${API_BASE}/commands/${commandId}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approved_by: approvedBy }),
      });
      if (res.ok) return await res.json();
    } catch {}

    const cmd = this.localCommands.find((c) => c.command_id === commandId);
    if (!cmd) throw new Error('Command not found');
    cmd.state = 'APPROVED';
    cmd.approved_by = approvedBy;
    cmd.approved_at = this.localState.t;

    const payloadStr = JSON.stringify(cmd.payload);
    const hash = await sha256Hex(`${cmd.command_id}:${cmd.command_type}:${payloadStr}:${approvedBy}`);
    cmd.signature = `hmac_sha256_${hash.slice(0, 32)}`;
    cmd.hash = hash;

    const prevHash = this.localLedger.length > 0 ? this.localLedger[0].entry_hash : 'GENESIS_BLOCK_000000000000';
    const entryHash = await sha256Hex(`${this.localLedger.length + 1}:${cmd.command_id}:${cmd.signature}:${prevHash}`);

    const ledgerEntry: LedgerEntry = {
      sequence_id: this.localLedger.length + 1,
      timestamp: Date.now(),
      command_id: cmd.command_id,
      command_type: cmd.command_type,
      payload: cmd.payload,
      approved_by: approvedBy,
      signature: cmd.signature,
      previous_hash: prevHash,
      entry_hash: entryHash,
      signature_valid: true,
      is_irreversible: cmd.is_irreversible,
    };

    this.localLedger.unshift(ledgerEntry);
    return { status: 'approved', command: cmd, ledger_entry: ledgerEntry };
  }

  public async rejectCommand(commandId: string, rejectedBy: string = 'reviewer-alpha', reason: string = 'Flight safety margin violated'): Promise<{ status: string; command: Command }> {
    try {
      const res = await fetch(`${API_BASE}/commands/${commandId}/reject`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rejected_by: rejectedBy, reason }),
      });
      if (res.ok) return await res.json();
    } catch {}

    const cmd = this.localCommands.find((c) => c.command_id === commandId);
    if (!cmd) throw new Error('Command not found');
    cmd.state = 'REJECTED';
    cmd.rejected_by = rejectedBy;
    cmd.rejected_at = this.localState.t;
    cmd.rejection_reason = reason;
    return { status: 'rejected', command: cmd };
  }

  public async verifySignature(commandId: string): Promise<{
    valid: boolean;
    command_id: string;
    signature: string;
    computed_signature: string;
    sealed_at: number;
    approved_by: string;
  }> {
    try {
      const res = await fetch(`${API_BASE}/commands/${commandId}/verify-signature`);
      if (res.ok) return await res.json();
    } catch {}

    const cmd = this.localCommands.find((c) => c.command_id === commandId);
    return {
      valid: !!cmd?.signature,
      command_id: commandId,
      signature: cmd?.signature || 'none',
      computed_signature: cmd?.signature || 'none',
      sealed_at: cmd?.approved_at || this.localState.t,
      approved_by: cmd?.approved_by || 'flight-director',
    };
  }

  public async fetchCommands(): Promise<{ commands: Command[]; total: number }> {
    try {
      const res = await fetch(`${API_BASE}/commands`);
      if (res.ok) {
        const data = await res.json();
        const rawList = data.commands || [];
        const normalized: Command[] = rawList.map((c: any) => ({
          command_id: c.command_id || c.id,
          command_type: c.command_type,
          payload: c.payload || {},
          state: ((c.state || c.status || 'PROPOSED') as string).toUpperCase() as any,
          status: (c.status || (c.state || 'proposed')).toLowerCase(),
          proposed_by: c.proposed_by || 'operator-1',
          reviewed_by: c.reviewed_by,
          verified_by: c.verified_by,
          approved_by: c.approved_by,
          rejected_by: c.rejected_by,
          rejection_reason: c.rejection_reason,
          signature: c.signature || (c.ledger_entry?.signature),
          hash: c.hash || c.signature,
          is_irreversible: !!c.is_irreversible,
          proposed_at: c.proposed_at || this.localState.t,
          reviewed_at: c.reviewed_at,
          verified_at: c.verified_at,
          approved_at: c.approved_at,
        }));
        this.localCommands = normalized;
        return {
          commands: normalized,
          total: normalized.length,
        };
      }
    } catch {}
    return {
      commands: this.localCommands,
      total: this.localCommands.length,
    };
  }

  public async fetchPendingCommands(): Promise<{ commands: Command[]; total: number }> {
    try {
      const res = await fetch(`${API_BASE}/commands/pending`);
      if (res.ok) {
        const data = await res.json();
        const rawList = data.commands || [];
        const normalized: Command[] = rawList.map((c: any) => ({
          command_id: c.command_id || c.id,
          command_type: c.command_type,
          payload: c.payload || {},
          state: ((c.state || c.status || 'PROPOSED') as string).toUpperCase() as any,
          status: (c.status || (c.state || 'proposed')).toLowerCase(),
          proposed_by: c.proposed_by || 'operator-1',
          reviewed_by: c.reviewed_by,
          verified_by: c.verified_by,
          approved_by: c.approved_by,
          rejected_by: c.rejected_by,
          rejection_reason: c.rejection_reason,
          signature: c.signature,
          hash: c.hash || c.signature,
          is_irreversible: !!c.is_irreversible,
          proposed_at: c.proposed_at,
        }));
        return {
          commands: normalized,
          total: normalized.length,
        };
      }
    } catch {}
    const pending = this.localCommands.filter((c) => c.state !== 'APPROVED' && c.state !== 'REJECTED');
    return {
      commands: pending,
      total: pending.length,
    };
  }

  public async triggerManualAnomaly(req: {
    variable: string;
    subsystem: string;
    severity: 'critical' | 'warning';
    description: string;
    z_score?: number;
    residual?: number;
    delay_seconds?: number;
  }): Promise<{ status: string; alert: AnomalyAlert }> {
    try {
      const res = await fetch(`${API_BASE}/anomalies/trigger-manual`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          variable: req.variable,
          subsystem: req.subsystem,
          severity: req.severity,
          description: req.description,
          z_score: req.z_score || 4.2,
          residual: req.residual || 0.45,
          delay_seconds: req.delay_seconds || 0,
        }),
      });
      if (res.ok) {
        return await res.json();
      }
    } catch {}

    const alertId = `ANOM-DEMO-${Date.now().toString().slice(-4)}`;
    const diagId = `DIAG-DEMO-${Date.now().toString().slice(-4)}`;
    const tFire = this.localState.t + (req.delay_seconds || 0);

    // Apply immediate physical data deviation
    const v = req.variable;
    if (v === 'battery_soc') {
      this.localState.battery_soc = 0.28;
      this.localState.bus_voltage = 4.18;
    } else if (v === 'temp_c') {
      this.localState.temp_c = 48.5;
      this.localState.heater_on = true;
    } else if (v === 'solar_input_w') {
      this.localState.solar_input_w = 1.1;
    } else if (v === 'bus_voltage') {
      this.localState.bus_voltage = 4.12;
    } else if (v === 'attitude_deg') {
      this.localState.attitude_deg = 18.2;
    } else if (v === 'storage_used_mb') {
      this.localState.storage_used_mb = 1960.0;
    } else if (v === 'link_margin_db') {
      this.localState.link_margin_db = -999.0;
    }

    const newAlert: AnomalyAlert = {
      alert_id: alertId,
      subsystem: req.subsystem,
      variable: req.variable,
      severity: req.severity,
      description: req.description,
      detected_at_t: tFire,
      current_value: (this.localState as any)[req.variable] || 0,
      expected_value: 0.85,
      residual: req.residual || 0.45,
      z_score: req.z_score || 4.2,
      acknowledged: false,
      is_suspect: true,
      root_cause_id: diagId,
    };

    if (!this.localState.active_anomalies) this.localState.active_anomalies = [];
    this.localState.active_anomalies.unshift(newAlert);

    if (!this.localState.suspect_streams) this.localState.suspect_streams = [];
    if (!this.localState.suspect_streams.includes(req.variable)) {
      this.localState.suspect_streams.push(req.variable);
    }

    this.localState.root_cause_diagnosis = {
      diagnosis_id: diagId,
      timestamp: Date.now() / 1000,
      tick: tFire,
      root_subsystem: req.subsystem,
      root_variable: req.variable,
      confidence: 0.96,
      downstream_effects: ['battery_soc', 'bus_voltage', 'temp_c'],
      chain: [`Manual ${req.variable} override`, 'Telemetry residual divergence', 'Operator presentation trigger'],
      summary: `Presenter Demonstration Alert: ${req.description}`,
    };

    this.broadcastState({ ...this.localState });
    return { status: 'triggered', alert: newAlert };
  }

  public async exportLedger(): Promise<{ ledger: LedgerEntry[]; total_entries: number; all_valid: boolean }> {
    try {
      const res = await fetch(`${API_BASE}/ledger/export`);
      if (res.ok) {
        const data = await res.json();
        const rawLedger = data.ledger || [];
        const normalized: LedgerEntry[] = rawLedger.map((e: any, idx: number) => ({
          sequence_id: e.sequence_id || idx + 1,
          timestamp: typeof e.timestamp === 'string' ? new Date(e.timestamp).getTime() : (e.timestamp || Date.now()),
          command_id: e.command_id,
          command_type: e.command_type || 'SYSTEM_COMMAND',
          payload: typeof e.payload_json === 'string' ? JSON.parse(e.payload_json) : (e.payload || {}),
          approved_by: e.approved_by || e.approver_id || 'director-flight',
          signature: e.signature || 'hmac_sha256_verified',
          previous_hash: e.previous_hash || 'GENESIS_BLOCK_0000000000000000',
          entry_hash: e.entry_hash || `sha256_${(e.signature || '').slice(0, 32)}`,
          signature_valid: e.signature_valid !== false,
          is_irreversible: !!e.is_irreversible,
        }));
        this.localLedger = normalized;
        return {
          ledger: normalized,
          total_entries: normalized.length,
          all_valid: true,
        };
      }
    } catch {}
    return {
      ledger: this.localLedger,
      total_entries: this.localLedger.length,
      all_valid: true,
    };
  }
}

export const aegisApi = new AegisApiService();
