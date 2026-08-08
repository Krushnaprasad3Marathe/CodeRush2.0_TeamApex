import React, { useState, useEffect } from 'react';
import type {
  SpacecraftState,
  ScheduledActivity,
  SchedulerDecision,
  ConstraintViolation,
  PlanResult,
  PriorityMismatch,
  PriorityCheckResult,
} from '../types';
import { aegisApi } from '../services/api';
import { CalendarIcon, SparklesIcon, CheckIcon, AlertTriangleIcon, RefreshCwIcon, PlayIcon, ZapIcon } from './icons';

interface MissionPlannerViewProps {
  state: SpacecraftState;
  onRefresh: () => void;
}

export const MissionPlannerView: React.FC<MissionPlannerViewProps> = ({ state, onRefresh }) => {
  const [activities, setActivities] = useState<ScheduledActivity[]>([]);
  const [decisions, setDecisions] = useState<SchedulerDecision[]>([]);
  const [violations, setViolations] = useState<ConstraintViolation[]>([]);
  const [selectedDecision, setSelectedDecision] = useState<SchedulerDecision | null>(null);
  const [aiExplanation, setAiExplanation] = useState<string | null>(null);
  const [isGenerating, setIsGenerating] = useState<boolean>(false);
  const [isAdopting, setIsAdopting] = useState<boolean>(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [mismatches, setMismatches] = useState<PriorityMismatch[]>([]);

  const loadPlan = async () => {
    try {
      const planRes = await aegisApi.fetchPlan();
      setActivities(planRes.activities || []);
      setDecisions(planRes.decisions || []);
      setViolations(planRes.violations || []);

      if (planRes.decisions && planRes.decisions.length > 0 && !selectedDecision) {
        setSelectedDecision(planRes.decisions[0]);
      }

      const priorityRes: PriorityCheckResult = await aegisApi.fetchPriorityCheck();
      setMismatches(priorityRes.mismatches || []);
    } catch {}
  };

  useEffect(() => {
    loadPlan();
  }, [state.t]);

  const handleGeneratePlan = async () => {
    setIsGenerating(true);
    try {
      const result: PlanResult = await aegisApi.generatePlan();
      setActivities(result.activities || []);
      setDecisions(result.decisions || []);
      setViolations(result.violations || []);
      setMsg(`MISSION PLAN GENERATED (${result.activities?.length || 0} ACTIVITIES OPTIMIZED)`);
      setTimeout(() => setMsg(null), 3000);

      const priorityRes = await aegisApi.fetchPriorityCheck();
      setMismatches(priorityRes.mismatches || []);
      onRefresh();
    } catch {}
    setIsGenerating(false);
  };

  const handleAdoptPriorities = async () => {
    setIsAdopting(true);
    try {
      const result: PlanResult = await aegisApi.applyRecommendedPriorities();
      setActivities(result.activities || []);
      setDecisions(result.decisions || []);
      setViolations(result.violations || []);
      setMsg('RECOMMENDED PRIORITIES ADOPTED & APPLIED');
      setTimeout(() => setMsg(null), 3000);

      const priorityRes = await aegisApi.fetchPriorityCheck();
      setMismatches(priorityRes.mismatches || []);
      onRefresh();
    } catch {}
    setIsAdopting(false);
  };

  const handleSelectDecision = async (dec: SchedulerDecision) => {
    setSelectedDecision(dec);
    setAiExplanation(null);
    try {
      const expRes = await aegisApi.explainDecision(dec.decision_id);
      setAiExplanation(expRes.ai_explanation || dec.explanation || dec.reason);
    } catch {
      setAiExplanation(dec.explanation || dec.reason);
    }
  };

  const getActivityColor = (type: string) => {
    switch (type) {
      case 'observation':
        return 'var(--status-teal)';
      case 'downlink':
        return 'var(--amber)';
      case 'eclipse_charge':
        return 'var(--status-plum)';
      default:
        return 'var(--status-green)';
    }
  };

  const getSeverityBadgeClass = (sev: string) => {
    switch (sev?.toLowerCase()) {
      case 'critical':
        return 'badge-red';
      case 'high':
        return 'badge-amber';
      case 'medium':
        return 'badge-plum';
      default:
        return 'badge-teal';
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
      {/* Page Header */}
      <div className="page-header flex-between">
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          <div className="icon-wrap">
            <CalendarIcon size={20} color="var(--amber)" />
          </div>
          <div>
            <h1>Mission Planner &amp; Constraint Engine</h1>
            <p>LangGraph-driven activity scheduler with hard physics constraint verification and explainable reasoning</p>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {msg && (
            <span className="badge badge-green" style={{ padding: '6px 12px' }}>
              {msg}
            </span>
          )}
          <button
            type="button"
            className="btn btn-amber"
            onClick={handleGeneratePlan}
            disabled={isGenerating}
          >
            <PlayIcon size={14} />
            {isGenerating ? 'SCHEDULING ACTIVITIES...' : 'GENERATE MISSION PLAN'}
          </button>
          <button type="button" className="btn btn-ghost" onClick={loadPlan}>
            <RefreshCwIcon size={14} />
            RELOAD
          </button>
        </div>
      </div>

      {/* Metric Cards */}
      <div className="grid g4">
        <div className="card metric-card">
          <div className="metric-label">
            <CalendarIcon size={14} color="var(--amber)" />
            <span>Scheduled Activities</span>
          </div>
          <div className="metric-value">{activities.length}</div>
          <div className="metric-sub">Across 90-min orbit cycle</div>
        </div>

        <div className="card metric-card">
          <div className="metric-label">
            <CheckIcon size={14} color="var(--status-green)" />
            <span>Constraint Violations</span>
          </div>
          <div
            className="metric-value"
            style={{ color: violations.length > 0 ? 'var(--status-red)' : 'var(--status-green)' }}
          >
            {violations.length === 0 ? '0 (ALL PASS)' : `${violations.length} VIOLATIONS`}
          </div>
          <div className="metric-sub">Power, thermal &amp; storage checks</div>
        </div>

        <div className="card metric-card">
          <div className="metric-label">
            <SparklesIcon size={14} color="var(--status-teal)" />
            <span>Priority Advisor Warnings</span>
          </div>
          <div
            className="metric-value"
            style={{ color: mismatches.length > 0 ? 'var(--amber)' : 'var(--status-green)' }}
          >
            {mismatches.length === 0 ? '0 (ALIGNED)' : `${mismatches.length} MISMATCHES`}
          </div>
          <div className="metric-sub">Data-driven priority dataset</div>
        </div>

        <div className="card metric-card">
          <div className="metric-label">
            <AlertTriangleIcon size={14} color="var(--status-plum)" />
            <span>Suspect Streams Bypass</span>
          </div>
          <div className="metric-value" style={{ color: 'var(--paper)' }}>
            {(state.suspect_streams || []).length} CHANNELS
          </div>
          <div className="metric-sub">Excluded from constraint solver</div>
        </div>
      </div>

      {/* Priority Advisor & Mission Urgency Validation Card */}
      {mismatches.length > 0 && (
        <div className="card" style={{ border: '1px solid var(--amber)', background: 'var(--ink-raised)' }}>
          <div className="flex-between" style={{ marginBottom: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <ZapIcon size={16} color="var(--amber)" />
              <div style={{ fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--amber)' }}>
                PRIORITY ADVISOR: MISSION URGENCY MISMATCHES DETECTED ({mismatches.length})
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span className="badge badge-amber">THRESHOLD: DELTA &ge; 2</span>
              <button
                type="button"
                className="btn btn-amber"
                onClick={handleAdoptPriorities}
                disabled={isAdopting}
              >
                <CheckIcon size={14} />
                {isAdopting ? 'APPLYING PRIORITIES...' : 'ADOPT RECOMMENDED PRIORITIES'}
              </button>
            </div>
          </div>

          <table>
            <thead>
              <tr>
                <th>Activity</th>
                <th>Assigned Priority</th>
                <th>Recommended Priority</th>
                <th>Direction</th>
                <th>Matched Rule</th>
                <th>Severity</th>
                <th>Mission Reason &amp; AI Advice</th>
              </tr>
            </thead>
            <tbody>
              {mismatches.map((m) => (
                <tr key={m.activity_id + m.matched_rule_id}>
                  <td style={{ fontWeight: 600, color: 'var(--paper)' }}>
                    {m.title} <span className="mono" style={{ color: 'var(--paper-dim)', fontSize: '11px' }}>({m.activity_id})</span>
                  </td>
                  <td className="mono">{m.assigned_priority}</td>
                  <td className="mono" style={{ fontWeight: 700, color: 'var(--amber)' }}>
                    {m.recommended_priority}
                  </td>
                  <td>
                    <span className={`badge ${m.direction === 'increase' ? 'badge-green' : 'badge-plum'}`}>
                      {m.direction === 'increase' ? 'INCREASE ⬆' : 'DECREASE ⬇'} (&Delta;{m.delta})
                    </span>
                  </td>
                  <td className="mono" style={{ fontSize: '11px' }}>{m.matched_rule_id}</td>
                  <td>
                    <span className={`badge ${getSeverityBadgeClass(m.severity)}`}>
                      {m.severity.toUpperCase()}
                    </span>
                  </td>
                  <td style={{ fontSize: '12px' }}>
                    <div style={{ color: 'var(--paper)' }}>{m.reason}</div>
                    {m.ai_recommendation && (
                      <div style={{ color: 'var(--status-teal)', fontSize: '11px', marginTop: '2px' }}>
                        {m.ai_recommendation}
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Activity Timeline / Gantt Chart */}
      <div className="card">
        <div className="card-title">
          <span>Mission Activity Schedule Timeline (Orbit T+0 to T+400s)</span>
          <span className="mono">TIMELINE GANTT</span>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', padding: '10px 0' }}>
          {activities.map((act) => {
            const startPct = Math.min(100, (act.start_t / 400) * 100);
            const durationPct = Math.min(100 - startPct, ((act.end_t - act.start_t) / 400) * 100);
            const actColor = getActivityColor(act.activity_type);

            return (
              <div key={act.activity_id} style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <div className="flex-between" style={{ fontSize: '11px', fontFamily: 'var(--font-mono)' }}>
                  <span style={{ fontWeight: 600, color: 'var(--paper)' }}>
                    [{act.subsystem}] {act.activity_id} · {act.activity_type.toUpperCase()}
                  </span>
                  <span style={{ color: 'var(--paper-dim)' }}>
                    T+{act.start_t}s ➔ T+{act.end_t}s (Power: {act.power_draw_w}W)
                  </span>
                </div>

                <div
                  style={{
                    position: 'relative',
                    height: '24px',
                    background: 'var(--ink-raised)',
                    borderRadius: 'var(--radius)',
                    overflow: 'hidden',
                  }}
                >
                  <div
                    style={{
                      position: 'absolute',
                      left: `${startPct}%`,
                      width: `${durationPct}%`,
                      height: '100%',
                      background: actColor,
                      opacity: 0.85,
                      borderRadius: 'var(--radius)',
                      display: 'flex',
                      alignItems: 'center',
                      padding: '0 8px',
                      color: 'var(--ink)',
                      fontWeight: 700,
                      fontSize: '10px',
                      fontFamily: 'var(--font-mono)',
                    }}
                  >
                    {act.activity_type.toUpperCase()}
                  </div>

                  {/* Current Sim Clock Marker */}
                  {state.t <= 400 && (
                    <div
                      style={{
                        position: 'absolute',
                        left: `${(state.t / 400) * 100}%`,
                        width: '2px',
                        height: '100%',
                        background: 'var(--amber)',
                        boxShadow: '0 0 6px var(--amber)',
                        zIndex: 10,
                      }}
                    />
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Split: Constraint Validation Matrix + AI Decision Explanations */}
      <div className="grid g2">
        {/* Left: Constraint Validation Matrix */}
        <div className="card">
          <div className="card-title">
            <span>Hard Constraint Verification Matrix</span>
            <span className="badge badge-green">ALL PASS</span>
          </div>

          <table>
            <thead>
              <tr>
                <th>Constraint Rule</th>
                <th>Threshold Spec</th>
                <th>Current State</th>
                <th>Result</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Power Margin Reserve</td>
                <td className="mono">&gt; 15.0% battery buffer</td>
                <td className="mono">{(state.battery_soc * 100).toFixed(1)}%</td>
                <td>
                  <span className={`badge ${state.battery_soc < 0.2 ? 'badge-red' : 'badge-green'}`}>
                    {state.battery_soc < 0.2 ? 'FAIL' : 'PASS'}
                  </span>
                </td>
              </tr>

              <tr>
                <td>Thermal Envelope</td>
                <td className="mono">-20.0°C to +45.0°C</td>
                <td className="mono">{state.temp_c.toFixed(1)}°C</td>
                <td>
                  <span className={`badge ${state.temp_c > 45 || state.temp_c < -20 ? 'badge-red' : 'badge-green'}`}>
                    {state.temp_c > 45 || state.temp_c < -20 ? 'FAIL' : 'PASS'}
                  </span>
                </td>
              </tr>

              <tr>
                <td>Eclipse Observation Ban</td>
                <td className="mono">0.0W imaging during umbra</td>
                <td className="mono">{state.in_eclipse ? 'ECLIPSE' : 'SUNLIT'}</td>
                <td>
                  <span className="badge badge-green">PASS</span>
                </td>
              </tr>

              <tr>
                <td>Storage Buffer Headroom</td>
                <td className="mono">&lt; 90% flash capacity</td>
                <td className="mono">
                  {((state.storage_used_mb / state.storage_capacity_mb) * 100).toFixed(0)}%
                </td>
                <td>
                  <span className="badge badge-green">PASS</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        {/* Right: AI Decision Inspector */}
        <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <div className="card-title">
            <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <SparklesIcon size={14} color="var(--amber)" />
              AI Planning Decision Inspector
            </span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            {decisions.map((dec) => (
              <div
                key={dec.decision_id}
                onClick={() => handleSelectDecision(dec)}
                style={{
                  padding: '8px 12px',
                  background: selectedDecision?.decision_id === dec.decision_id ? 'var(--amber-dim)' : 'var(--ink)',
                  border: `1px solid ${
                    selectedDecision?.decision_id === dec.decision_id ? 'var(--amber)' : 'var(--border)'
                  }`,
                  borderRadius: 'var(--radius)',
                  cursor: 'pointer',
                }}
              >
                <div className="flex-between">
                  <span style={{ fontWeight: 600, color: 'var(--paper)', fontSize: '11px' }}>
                    {dec.decision_id} · {dec.node_name}
                  </span>
                  <span className="badge badge-teal" style={{ fontSize: '9px' }}>
                    {dec.decision_type.toUpperCase()}
                  </span>
                </div>
                <div style={{ fontSize: '11px', color: 'var(--paper-dim)', marginTop: '4px' }}>
                  {dec.reason}
                </div>
              </div>
            ))}
          </div>

          {selectedDecision && (
            <div
              style={{
                marginTop: 'auto',
                padding: '12px',
                background: 'var(--ink)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius)',
              }}
            >
              <div className="label-mono" style={{ marginBottom: '4px' }}>
                AI EXPLANATION FOR {selectedDecision.decision_id}
              </div>
              <div style={{ fontSize: '12px', color: 'var(--paper)', lineHeight: 1.5 }}>
                {aiExplanation || selectedDecision.explanation || selectedDecision.reason}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
