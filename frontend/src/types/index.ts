/**
 * Aegis MOS — Flight-Deck Type Definitions
 * Complete types for Spacecraft Digital Twin, Fault Sandbox, Anomaly Detection,
 * AI Diagnostics, Mission Planner, and Command Authority Ledger.
 */

export interface SpacecraftState {
  t: number;
  timestamp: number;
  battery_soc: number; // 0.0 - 1.0
  bus_voltage: number; // Volts (approx 4.6 - 5.1V)
  solar_input_w: number; // Watts
  power_draw_w: number; // Watts
  temp_c: number; // Celsius (-20 to +45)
  heater_on: boolean;
  attitude_deg: number; // Degrees from sun-pointing
  slew_rate_dps: number; // Deg/s
  target_attitude_deg: number;
  storage_used_mb: number; // MB
  storage_capacity_mb: number; // MB (2048 default)
  comms_active: boolean;
  link_margin_db: number;
  in_contact: boolean;
  in_eclipse: boolean;
  orbit_phase: number; // 0.0 - 1.0
  is_observing: boolean;
  is_slewing: boolean;
  reported_battery_soc?: number | null;
  reported_bus_voltage?: number | null;
  reported_solar_input_w?: number | null;
  reported_temp_c?: number | null;
  reported_attitude_deg?: number | null;
  reported_storage_used_mb?: number | null;
  reported_link_margin_db?: number | null;
  reported_power_draw_w?: number | null;
  reported_slew_rate_dps?: number | null;
  active_anomalies?: AnomalyAlert[];
  root_cause_diagnosis?: RootCauseDiagnosis | null;
  suspect_streams?: string[];
  active_faults?: ActiveFault[];
  sandbox_mode?: boolean;
  scorecard?: FaultScorecard | null;
  scheduled_activities?: ScheduledActivity[];
}

export interface CatalogFault {
  fault_id: string;
  name: string;
  subsystem: string;
  target_variable: string;
  fault_type: string;
  tier: 'sensor' | 'system';
  description: string;
  default_params: Record<string, number | string | boolean>;
}

export interface ActiveFault {
  fault_id: string;
  name: string;
  subsystem: string;
  target_variable: string;
  fault_type: string;
  tier: 'sensor' | 'system';
  trigger_t: number;
  duration_ticks: number;
  parameters: Record<string, any>;
  applied: boolean;
  cleared: boolean;
  applied_at_t?: number;
}

export interface FaultScorecard {
  injected_total: number;
  detected_total: number;
  missed_total: number;
  false_alarms: number;
  detection_accuracy_pct: number;
  avg_detection_lag_ticks: number;
}

export interface AnomalyAlert {
  alert_id: string;
  subsystem: string;
  variable: string;
  severity: 'critical' | 'warning' | 'info';
  description: string;
  detected_at_t: number;
  current_value: number;
  expected_value: number;
  residual: number;
  z_score: number;
  acknowledged: boolean;
  acknowledged_by?: string;
  acknowledged_at_t?: number;
  root_cause_id?: string;
  is_suspect?: boolean;
}

export interface RootCauseDiagnosis {
  diagnosis_id: string;
  timestamp: number;
  tick: number;
  root_subsystem: string;
  root_variable: string;
  confidence: number;
  downstream_effects: string[];
  chain: string[];
  summary: string;
}

export interface AIDiagnosisResult {
  diagnosis: string;
  active_alerts: number;
  root_cause?: RootCauseDiagnosis | null;
  suggested_procedures: AIProcedureStep[];
  state_summary: {
    battery_soc?: number;
    temp_c?: number;
    bus_voltage?: number;
    in_eclipse?: boolean;
  };
}

export interface AIProcedureStep {
  step: number;
  title: string;
  description: string;
  status: 'pending' | 'in_progress' | 'completed' | 'skipped';
}

export interface ScheduledActivity {
  activity_id: string;
  activity_type: 'observation' | 'downlink' | 'eclipse_charge' | 'momentum_dump' | 'health_checkout';
  title?: string;
  description?: string;
  start_t: number;
  end_t: number;
  priority: number;
  status: 'scheduled' | 'active' | 'completed' | 'cancelled' | 'delayed';
  subsystem: string;
  power_draw_w: number;
  data_generated_mb?: number;
  data_downlinked_mb?: number;
}

export interface SchedulerDecision {
  decision_id: string;
  decision_type: 'schedule' | 'reject' | 'delay' | 'reschedule';
  activity_id: string;
  activity_type: string;
  node_name: string;
  reason: string;
  explanation?: string;
  tick: number;
  input_state?: Record<string, any>;
  output_state?: Record<string, any>;
}

export interface ConstraintViolation {
  constraint_name: string;
  subsystem: string;
  severity: 'critical' | 'warning';
  message: string;
  violating_activity_id?: string;
  tick: number;
}

export interface PriorityMismatch {
  activity_id: string;
  activity_type: string;
  title: string;
  assigned_priority: number;
  recommended_priority: number;
  delta: number;
  direction: 'increase' | 'decrease';
  matched_rule_id: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  reason: string;
  ai_recommendation?: string;
}

export interface PriorityCheckResult {
  status: string;
  total_activities: number;
  total_mismatches: number;
  critical_mismatches: number;
  mismatches: PriorityMismatch[];
}

export interface PlanResult {
  status: string;
  activities: ScheduledActivity[];
  decisions: SchedulerDecision[];
  violations: ConstraintViolation[];
  total_activities: number;
  constraint_violations: number;
}

export type CommandState = 'PROPOSED' | 'REVIEWED' | 'VERIFIED' | 'APPROVED' | 'REJECTED';

export interface Command {
  command_id: string;
  command_type: string;
  payload: Record<string, any>;
  state: CommandState;
  proposed_by: string;
  proposed_at: number;
  reviewed_by?: string;
  reviewed_at?: number;
  verified_by?: string;
  verified_at?: number;
  approved_by?: string;
  approved_at?: number;
  rejected_by?: string;
  rejected_at?: number;
  rejection_reason?: string;
  is_irreversible: boolean;
  signature?: string;
  hash?: string;
  executed_at_t?: number;
}

export interface LedgerEntry {
  sequence_id: number;
  timestamp: number;
  command_id: string;
  command_type: string;
  payload: Record<string, any>;
  approved_by: string;
  signature: string;
  previous_hash: string;
  entry_hash: string;
  signature_valid: boolean;
  is_irreversible: boolean;
}

export interface HealthStatus {
  status: string;
  simulator_running: boolean;
  simulator_tick: number;
  observed_hz: number;
  active_faults: number;
  active_anomalies: number;
}
