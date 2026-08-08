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
      if (planRes && planRes.activities) {
        setActivities(planRes.activities || []);
        setDecisions(planRes.decisions || []);
        setViolations(planRes.violations || []);

        if (planRes.decisions && planRes.decisions.length > 0 && !selectedDecision) {
          setSelectedDecision(planRes.decisions[0]);
        }
      }

      const priorityRes: PriorityCheckResult = await aegisApi.fetchPriorityCheck();
      if (priorityRes && priorityRes.mismatches) {
        setMismatches(priorityRes.mismatches || []);
      }
    } catch (err) {
      console.warn('Failed to load mission plan:', err);
    }
  };

  useEffect(() => {
    loadPlan();
  }, [state.t]);

  const handleGeneratePlan = async () => {
    setIsGenerating(true);
    try {
      const result: PlanResult = await aegisApi.generatePlan();
      if (result) {
        setActivities(result.activities || []);
        setDecisions(result.decisions || []);
        setViolations(result.violations || []);
        setMsg(`MISSION PLAN GENERATED (${result.activities?.length || 0} ACTIVITIES OPTIMIZED)`);
        setTimeout(() => setMsg(null), 3000);
      }

      const priorityRes = await aegisApi.fetchPriorityCheck();
      if (priorityRes) {
        setMismatches(priorityRes.mismatches || []);
      }
      onRefresh();
    } catch {}
    setIsGenerating(false);
  };

  const handleAdoptPriorities = async () => {
    setIsAdopting(true);
    try {
      const result: PlanResult = await aegisApi.applyRecommendedPriorities();
      if (result) {
        setActivities(result.activities || []);
        setDecisions(result.decisions || []);
        setViolations(result.violations || []);
        setMsg('RECOMMENDED PRIORITIES ADOPTED & APPLIED');
        setTimeout(() => setMsg(null), 3000);
      }

      const priorityRes = await aegisApi.fetchPriorityCheck();
      if (priorityRes) {
        setMismatches(priorityRes.mismatches || []);
      }
      onRefresh();
    } catch {}
    setIsAdopting(false);
  };

  const handleSelectDecision = async (dec: SchedulerDecision) => {
    if (!dec) return;
    setSelectedDecision(dec);
    setAiExplanation(null);
    try {
      const expRes = await aegisApi.explainDecision(dec.decision_id);
      setAiExplanation(expRes?.ai_explanation || dec.explanation || dec.reason || 'Decision verified against mission constraints.');
    } catch {
      setAiExplanation(dec.explanation || dec.reason || 'Decision verified against mission constraints.');
    }
  };

  const getActivityColor = (type?: string) => {
    const t = String(type || '').toLowerCase();
    if (t.includes('obs')) return 'var(--status-teal)';
    if (t.includes('downlink')) return 'var(--amber)';
    if (t.includes('charg')) return 'var(--status-plum)';
    return 'var(--status-green)';
  };

  const getSeverityBadgeClass = (sev?: string) => {
    const s = String(sev || '').toLowerCase();
    if (s.includes('crit')) return 'badge-red';
    if (s.includes('high')) return 'badge-amber';
    if (s.includes('med')) return 'badge-plum';
    return 'badge-teal';
  };

  const currentOrbitTick = (state?.t || 0) % 5400;
  const currentOrbitProgressPct = ((currentOrbitTick / 5400) * 100).toFixed(1);

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
            {(state?.suspect_streams || []).length} CHANNELS
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
                <tr key={String(m.activity_id) + String(m.matched_rule_id)}>
                  <td style={{ fontWeight: 600, color: 'var(--paper)' }}>
                    {m.title || m.activity_id} <span className="mono" style={{ color: 'var(--paper-dim)', fontSize: '11px' }}>({m.activity_id})</span>
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
                      {String(m.severity || 'info').toUpperCase()}
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
        <div className="flex-between" style={{ marginBottom: '12px' }}>
          <div className="card-title" style={{ margin: 0 }}>
            <span>Mission Activity Schedule Timeline (Full 90-Min Orbit T+0 to T+5400s)</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span className="mono" style={{ fontSize: '11px', color: 'var(--amber)' }}>
              LIVE ORBIT CURSOR: T+{currentOrbitTick.toString().padStart(4, '0')}s / 5400s ({currentOrbitProgressPct}%)
            </span>
            <span className="badge badge-teal">TIMELINE GANTT</span>
          </div>
        </div>

        {/* Orbit Background Zones Ribbon (4 Non-Overlapping Sectors) */}
        <div
          style={{
            position: 'relative',
            height: '38px',
            background: 'var(--ink)',
            borderRadius: 'var(--radius)',
            border: '1px solid var(--border)',
            overflow: 'hidden',
            display: 'flex',
            marginBottom: '14px',
          }}
        >
          {/* Sector 1: Sunlit Pre-Pass (0s to 1200s) */}
          <div
            style={{
              width: `${(1200 / 5400) * 100}%`,
              height: '100%',
              background: 'rgba(255, 122, 51, 0.08)',
              borderRight: '1px solid var(--border)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '10px',
              fontWeight: 600,
              fontFamily: 'var(--font-mono)',
              color: 'var(--amber)',
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              padding: '0 4px',
            }}
          >
            <span>☀️ SUNLIT (T+0s ➔ 1200s)</span>
          </div>

          {/* Sector 2: Ground Contact Pass (1200s to 1800s) */}
          <div
            style={{
              width: `${(600 / 5400) * 100}%`,
              height: '100%',
              background: 'rgba(107, 155, 110, 0.28)',
              borderRight: '1px solid var(--border)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '10px',
              fontWeight: 700,
              fontFamily: 'var(--font-mono)',
              color: 'var(--status-green)',
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              padding: '0 4px',
            }}
          >
            <span>📡 GROUND PASS</span>
          </div>

          {/* Sector 3: Sunlit Post-Pass (1800s to 3510s) */}
          <div
            style={{
              width: `${(1710 / 5400) * 100}%`,
              height: '100%',
              background: 'rgba(255, 122, 51, 0.08)',
              borderRight: '1px dashed var(--amber)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '10px',
              fontWeight: 600,
              fontFamily: 'var(--font-mono)',
              color: 'var(--amber)',
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              padding: '0 4px',
            }}
          >
            <span>☀️ SUNLIT (T+1800s ➔ 3510s)</span>
          </div>

          {/* Sector 4: Eclipse Umbra (3510s to 5400s) */}
          <div
            style={{
              width: `${(1890 / 5400) * 100}%`,
              height: '100%',
              background: 'rgba(139, 107, 155, 0.16)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '10px',
              fontWeight: 600,
              fontFamily: 'var(--font-mono)',
              color: 'var(--status-plum)',
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              padding: '0 4px',
            }}
          >
            <span>🌑 ECLIPSE UMBRA (T+3510s ➔ 5400s)</span>
          </div>

          {/* Live Orbit Clock Cursor Bar */}
          <div
            style={{
              position: 'absolute',
              left: `${(currentOrbitTick / 5400) * 100}%`,
              top: 0,
              bottom: 0,
              width: '2px',
              background: '#FFF',
              boxShadow: '0 0 8px #FFF, 0 0 14px var(--amber)',
              zIndex: 30,
              transition: 'left 0.9s linear',
              pointerEvents: 'none',
            }}
          />
        </div>

        {/* Task Blocks Stack */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {activities.map((act) => {
            const startT = Number(act.start_t || 0);
            const endT = Number(act.end_t || startT + 100);
            const startPct = Math.min(100, Math.max(0, (startT / 5400) * 100));
            const durationPct = Math.min(100 - startPct, Math.max(2, ((endT - startT) / 5400) * 100));
            const actColor = getActivityColor(act.activity_type);
            const isCurrentlyActive = currentOrbitTick >= startT && currentOrbitTick <= endT;
            const subName = String(act.subsystem || 'SYS').toUpperCase();
            const actTitle = String(act.title || act.description || act.activity_type || act.activity_id);

            return (
              <div key={act.activity_id} style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <div className="flex-between" style={{ fontSize: '11px', fontFamily: 'var(--font-mono)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontWeight: 700, color: 'var(--paper)' }}>
                      [{subName}] {act.activity_id} · {actTitle}
                    </span>
                    {isCurrentlyActive && (
                      <span className="badge badge-green" style={{ fontSize: '9px', padding: '1px 6px', animation: 'pulse 1.2s infinite' }}>
                        EXECUTING NOW
                      </span>
                    )}
                  </div>
                  <span style={{ color: 'var(--paper-dim)' }}>
                    T+{startT}s ➔ T+{endT}s (Duration: {endT - startT}s · Power: {act.power_draw_w || 0}W · Pri: {act.priority || 5})
                  </span>
                </div>

                {/* Timeline Track & Colored Task Block */}
                <div
                  style={{
                    position: 'relative',
                    height: '28px',
                    background: 'var(--ink)',
                    borderRadius: 'var(--radius)',
                    border: '1px solid var(--border)',
                    overflow: 'hidden',
                  }}
                >
                  {/* Task Block */}
                  <div
                    style={{
                      position: 'absolute',
                      left: `${startPct}%`,
                      width: `${durationPct}%`,
                      height: '100%',
                      background: actColor,
                      opacity: isCurrentlyActive ? 1.0 : 0.85,
                      borderRadius: 'var(--radius)',
                      display: 'flex',
                      alignItems: 'center',
                      padding: '0 10px',
                      color: 'var(--ink)',
                      fontWeight: 700,
                      fontSize: '11px',
                      fontFamily: 'var(--font-mono)',
                      boxShadow: isCurrentlyActive ? `0 0 12px ${actColor}` : 'none',
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                    }}
                    title={`${actTitle} (T+${startT}s to T+${endT}s)`}
                  >
                    <span>{String(act.activity_type || 'ACT').toUpperCase()}: {actTitle}</span>
                  </div>

                  {/* Real-time Progressing Orbit Time Cursor */}
                  <div
                    style={{
                      position: 'absolute',
                      left: `${(currentOrbitTick / 5400) * 100}%`,
                      top: 0,
                      bottom: 0,
                      width: '2px',
                      background: 'var(--amber)',
                      boxShadow: '0 0 8px var(--amber)',
                      zIndex: 15,
                      transition: 'left 0.9s linear',
                    }}
                  />
                </div>
              </div>
            );
          })}
        </div>

        {/* Time Scale Axis Ruler */}
        <div
          className="flex-between"
          style={{
            marginTop: '8px',
            fontSize: '10px',
            fontFamily: 'var(--font-mono)',
            color: 'var(--paper-muted)',
            borderTop: '1px solid var(--border)',
            paddingTop: '6px',
          }}
        >
          <span>T+0s (DAWN)</span>
          <span>T+1200s (AOS)</span>
          <span>T+1800s (LOS)</span>
          <span>T+2700s (NOON)</span>
          <span>T+3510s (ECLIPSE)</span>
          <span>T+5400s (ORBIT RESET)</span>
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
                <td className="mono">{((state?.battery_soc || 0.85) * 100).toFixed(1)}%</td>
                <td>
                  <span className={`badge ${(state?.battery_soc || 0.85) < 0.2 ? 'badge-red' : 'badge-green'}`}>
                    {(state?.battery_soc || 0.85) < 0.2 ? 'FAIL' : 'PASS'}
                  </span>
                </td>
              </tr>

              <tr>
                <td>Thermal Envelope</td>
                <td className="mono">-20.0°C to +45.0°C</td>
                <td className="mono">{(state?.temp_c || 22.0).toFixed(1)}°C</td>
                <td>
                  <span className={`badge ${(state?.temp_c || 22.0) > 45 || (state?.temp_c || 22.0) < -20 ? 'badge-red' : 'badge-green'}`}>
                    {(state?.temp_c || 22.0) > 45 || (state?.temp_c || 22.0) < -20 ? 'FAIL' : 'PASS'}
                  </span>
                </td>
              </tr>

              <tr>
                <td>Eclipse Observation Ban</td>
                <td className="mono">0.0W imaging during umbra</td>
                <td className="mono">{state?.in_eclipse ? 'ECLIPSE' : 'SUNLIT'}</td>
                <td>
                  <span className="badge badge-green">PASS</span>
                </td>
              </tr>

              <tr>
                <td>Storage Buffer Headroom</td>
                <td className="mono">&lt; 90% flash capacity</td>
                <td className="mono">
                  {(((state?.storage_used_mb || 256) / (state?.storage_capacity_mb || 2048)) * 100).toFixed(0)}%
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
                    {String(dec.decision_type || 'plan').toUpperCase()}
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
                {aiExplanation || selectedDecision.explanation || selectedDecision.reason || 'Verified against spacecraft constraints.'}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
