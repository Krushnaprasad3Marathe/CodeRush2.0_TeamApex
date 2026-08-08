import React, { useState, useEffect } from 'react';
import type { SpacecraftState, AnomalyAlert, AIDiagnosisResult } from '../types';
import { aegisApi } from '../services/api';
import {
  AlertTriangleIcon,
  SparklesIcon,
  CheckIcon,
  ShieldCheckIcon,
  RefreshCwIcon,
  GitBranchIcon,
  ZapIcon,
  PlayIcon,
} from './icons';

interface AnomalyAIViewProps {
  state: SpacecraftState;
  onRefresh: () => void;
}

export const AnomalyAIView: React.FC<AnomalyAIViewProps> = ({ state, onRefresh }) => {
  const [alerts, setAlerts] = useState<AnomalyAlert[]>([]);
  const [suspectStreams, setSuspectStreams] = useState<string[]>([]);
  const [aiDiagnosis, setAiDiagnosis] = useState<AIDiagnosisResult | null>(null);
  const [selectedAlert, setSelectedAlert] = useState<AnomalyAlert | null>(null);
  const [loadingAI, setLoadingAI] = useState<boolean>(false);
  const [operatorAckMsg, setOperatorAckMsg] = useState<string | null>(null);
  const [geminiApiKey, setGeminiApiKey] = useState<string>(() => (typeof localStorage !== 'undefined' ? localStorage.getItem('AEGIS_GEMINI_API_KEY') || '' : ''));
  const [keySavedMsg, setKeySavedMsg] = useState<string | null>(null);
  const [showKeyConfig, setShowKeyConfig] = useState<boolean>(false);
  const [isConfiguringKey, setIsConfiguringKey] = useState<boolean>(false);

  // Demo Timing Controls State (Task B)
  const [demoVariable, setDemoVariable] = useState<string>('battery_soc');
  const [demoSubsystem, setDemoSubsystem] = useState<string>('EPS (Power)');
  const [demoSeverity, setDemoSeverity] = useState<'critical' | 'warning'>('critical');
  const [demoZScore, setDemoZScore] = useState<number>(4.2);
  const [demoResidual, setDemoResidual] = useState<number>(0.45);
  const [customTimestamp, setCustomTimestamp] = useState<number>(state.t + 5);
  const [demoTriggerMode, setDemoTriggerMode] = useState<'immediate' | 'timestamp'>('immediate');
  const [demoSuccessMsg, setDemoSuccessMsg] = useState<string | null>(null);
  const [showDemoTimingPanel, setShowDemoTimingPanel] = useState<boolean>(true);

  const loadAnomaliesAndAI = async () => {
    try {
      const res = await aegisApi.fetchAnomalies();
      setAlerts(res.active.filter((a) => !a.acknowledged));
      if (res.active.length > 0 && !selectedAlert) {
        setSelectedAlert(res.active[0]);
      }

      const suspectRes = await aegisApi.fetchSuspectStreams();
      setSuspectStreams(suspectRes.suspect_streams);

      const aiRes = await aegisApi.diagnoseAI('operator_dashboard', geminiApiKey);
      setAiDiagnosis(aiRes);
    } catch {}
  };

  useEffect(() => {
    loadAnomaliesAndAI();
  }, [state.t]);

  const handleSaveApiKey = async () => {
    const key = geminiApiKey.trim();
    if (!key) return;
    setIsConfiguringKey(true);
    try {
      localStorage.setItem('AEGIS_GEMINI_API_KEY', key);
      await fetch('http://localhost:8000/ai/configure-key', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: key }),
      });
      setKeySavedMsg('GEMINI API KEY CONNECTED & ACTIVE');
      setTimeout(() => setKeySavedMsg(null), 3500);
      await handleRunAIDiagnosis();
    } catch {}
    setIsConfiguringKey(false);
  };

  const handleRunAIDiagnosis = async () => {
    setLoadingAI(true);
    try {
      const aiRes = await aegisApi.diagnoseAI('manual_trigger', geminiApiKey);
      setAiDiagnosis(aiRes);
    } catch {}
    setLoadingAI(false);
  };

  const handleAcknowledge = async (alertId: string) => {
    // 1. Immediately dismiss alert visually from active alerts list
    setAlerts((prev) => prev.filter((a) => a.alert_id !== alertId));
    if (selectedAlert?.alert_id === alertId) {
      setSelectedAlert(null);
    }
    setOperatorAckMsg(`ALERT ${alertId} AUDITED & ACKNOWLEDGED`);
    setTimeout(() => setOperatorAckMsg(null), 3000);

    // 2. Persist acknowledge to backend
    try {
      await aegisApi.acknowledgeAnomaly(alertId, 'operator-deck-1');
      await loadAnomaliesAndAI();
      onRefresh();
    } catch {}
  };

  const handleStepStatus = (stepIdx: number) => {
    if (!aiDiagnosis) return;
    const updated = [...aiDiagnosis.suggested_procedures];
    const current = updated[stepIdx].status;
    updated[stepIdx].status =
      current === 'completed' ? 'pending' : current === 'pending' ? 'in_progress' : 'completed';
    setAiDiagnosis({ ...aiDiagnosis, suggested_procedures: updated });
  };

  // Preset demonstration scenario picker
  const handleSelectPreset = (scenario: string) => {
    if (scenario === 'eps') {
      setDemoVariable('battery_soc');
      setDemoSubsystem('EPS (Power)');
      setDemoSeverity('critical');
      setDemoZScore(4.6);
      setDemoResidual(0.48);
    } else if (scenario === 'tcs') {
      setDemoVariable('temp_c');
      setDemoSubsystem('TCS (Thermal)');
      setDemoSeverity('critical');
      setDemoZScore(4.1);
      setDemoResidual(26.5);
    } else if (scenario === 'adcs') {
      setDemoVariable('attitude_deg');
      setDemoSubsystem('ADCS (Attitude)');
      setDemoSeverity('warning');
      setDemoZScore(3.4);
      setDemoResidual(18.2);
    } else if (scenario === 'comms') {
      setDemoVariable('link_margin_db');
      setDemoSubsystem('COMMS (RF)');
      setDemoSeverity('critical');
      setDemoZScore(5.2);
      setDemoResidual(999.0);
    } else if (scenario === 'cdh') {
      setDemoVariable('storage_used_mb');
      setDemoSubsystem('CDH (Storage)');
      setDemoSeverity('warning');
      setDemoZScore(3.8);
      setDemoResidual(180.0);
    }
  };

  // Task B: Manual Trigger Action
  const handleTriggerManualAnomaly = async () => {
    const delay = demoTriggerMode === 'immediate' ? 0 : Math.max(0, customTimestamp - state.t);
    const descMap: Record<string, string> = {
      battery_soc: 'Primary EPS solar generation failure causing rapid battery SOC depletion to 28.0%',
      temp_c: 'TCS survival heater stuck closed causing bus thermal runaway to +48.5°C',
      attitude_deg: 'Reaction wheel friction causing +18.2° attitude deviation from solar normal vector',
      link_margin_db: 'Transponder intermittent carrier dropout during critical ground station pass',
      storage_used_mb: 'NAND flash radiation SEU causing telemetry buffer pointer overflow',
    };

    const res = await aegisApi.triggerManualAnomaly({
      variable: demoVariable,
      subsystem: demoSubsystem,
      severity: demoSeverity,
      description: descMap[demoVariable] || `Manual demo override for ${demoVariable}`,
      z_score: demoZScore,
      residual: demoResidual,
      delay_seconds: delay,
    });

    setDemoSuccessMsg(`DEMO OVERRIDE FIRED: ${res.alert.alert_id} (${demoVariable})`);
    setTimeout(() => setDemoSuccessMsg(null), 4000);
    await loadAnomaliesAndAI();
    onRefresh();
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
      {/* Visual Anomaly Alert Popup Banner */}
      {alerts.length > 0 && (
        <div
          className="alert-box flex-between"
          style={{
            background: 'var(--red-dim)',
            borderColor: 'var(--status-red)',
            color: 'var(--paper)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <AlertTriangleIcon size={20} color="var(--status-red)" />
            <div>
              <div style={{ fontWeight: 700, fontFamily: 'var(--font-mono)' }}>
                {alerts.length} ACTIVE ANOMALY ALERT{alerts.length > 1 ? 'S' : ''} DETECTED
              </div>
              <div style={{ fontSize: '11px', color: 'var(--paper-dim)' }}>
                {alerts[0].description} (Z-Score: {alerts[0].z_score?.toFixed(1) || '4.2'}σ at T+{alerts[0].detected_at_t}s)
              </div>
            </div>
          </div>
          <button
            type="button"
            className="btn btn-red"
            onClick={() => handleAcknowledge(alerts[0].alert_id)}
          >
            ACKNOWLEDGE ALERT
          </button>
        </div>
      )}

      {/* Page Header */}
      <div className="page-header flex-between">
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          <div className="icon-wrap">
            <AlertTriangleIcon size={20} color="var(--amber)" />
          </div>
          <div>
            <h1>AI Anomaly Detection &amp; Explainable Root-Cause</h1>
            <p>Physics-residual Z-score anomaly detector coupled with Google Gemini explainable diagnostics &amp; live demo timing controls</p>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {operatorAckMsg && (
            <span className="badge badge-green" style={{ padding: '6px 12px' }}>
              {operatorAckMsg}
            </span>
          )}
          {keySavedMsg && (
            <span className="badge badge-green" style={{ padding: '6px 12px' }}>
              {keySavedMsg}
            </span>
          )}
          {demoSuccessMsg && (
            <span className="badge badge-amber" style={{ padding: '6px 12px', animation: 'pulse 1.4s infinite' }}>
              {demoSuccessMsg}
            </span>
          )}
          <button
            type="button"
            className={`btn ${showKeyConfig ? 'btn-amber' : 'btn-ghost'}`}
            onClick={() => setShowKeyConfig(!showKeyConfig)}
          >
            <SparklesIcon size={14} />
            {geminiApiKey ? 'GEMINI API: CONNECTED' : 'SET GEMINI API KEY'}
          </button>
          <button
            type="button"
            className={`btn ${showDemoTimingPanel ? 'btn-amber' : 'btn-ghost'}`}
            onClick={() => setShowDemoTimingPanel(!showDemoTimingPanel)}
          >
            <ZapIcon size={14} />
            {showDemoTimingPanel ? 'HIDE DEMO CONTROLS' : 'CONFIG DEMO TIMING'}
          </button>
          <button
            type="button"
            className="btn btn-ghost"
            onClick={handleRunAIDiagnosis}
            disabled={loadingAI}
          >
            <SparklesIcon size={14} />
            {loadingAI ? 'ANALYZING TELEMETRY...' : 'RUN GEMINI DIAGNOSIS'}
          </button>
          <button type="button" className="btn btn-ghost" onClick={loadAnomaliesAndAI}>
            <RefreshCwIcon size={14} />
            POLL ALERTS
          </button>
        </div>
      </div>

      {/* Gemini API Key Configuration Card */}
      {showKeyConfig && (
        <div className="card" style={{ border: '1px solid var(--status-teal)', background: 'var(--ink)' }}>
          <div className="flex-between" style={{ marginBottom: '10px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <SparklesIcon size={16} color="var(--status-teal)" />
              <div style={{ fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--status-teal)' }}>
                GOOGLE GEMINI API KEY CONFIGURATION
              </div>
            </div>
            <span className={`badge ${geminiApiKey ? 'badge-green' : 'badge-amber'}`}>
              {geminiApiKey ? 'KEY CONFIGURED' : 'RUNNING ON TEMPLATE FALLBACK'}
            </span>
          </div>

          <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
            <input
              type="password"
              placeholder="Paste your Google Gemini API Key (e.g. AIzaSy...)"
              value={geminiApiKey}
              onChange={(e) => setGeminiApiKey(e.target.value)}
              style={{
                flex: 1,
                background: 'var(--panel)',
                border: '1px solid var(--border)',
                color: 'var(--paper)',
                padding: '8px 12px',
                fontFamily: 'var(--font-mono)',
                fontSize: '12px',
                borderRadius: 'var(--radius)',
              }}
            />
            <button
              type="button"
              className="btn btn-teal"
              style={{ padding: '8px 16px', fontWeight: 600, fontSize: '12px' }}
              onClick={handleSaveApiKey}
              disabled={isConfiguringKey}
            >
              <CheckIcon size={14} />
              CONNECT GEMINI API
            </button>
          </div>
          <div style={{ fontSize: '11px', color: 'var(--paper-dim)', marginTop: '8px' }}>
            Your key is stored securely in your local browser and session memory. Aegis MOS directly sends telemetry states &amp; active anomaly alerts to Gemini for live root-cause synthesis and dynamic recovery procedure step generation.
          </div>
        </div>
      )}

      {/* Dedicated Demo Timing & Manual Trigger Panel (Task B) */}
      {showDemoTimingPanel && (
        <div className="card" style={{ border: '1px solid var(--amber)' }}>
          <div className="flex-between" style={{ marginBottom: '12px' }}>
            <div className="card-title" style={{ margin: 0, color: 'var(--amber)' }}>
              Presenter Live Demo Timing &amp; Manual AI Anomaly Injector
            </div>
            <span className="badge badge-amber">LIVE DEMO OVERRIDE ENABLED</span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            {/* Presets Row */}
            <div>
              <div className="label-mono" style={{ marginBottom: '6px' }}>
                SELECT PRESENTATION PRESET SCENARIO:
              </div>
              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                <button
                  type="button"
                  className={`btn ${demoVariable === 'battery_soc' ? 'btn-amber' : 'btn-ghost'}`}
                  onClick={() => handleSelectPreset('eps')}
                  style={{ fontSize: '11px', padding: '5px 10px' }}
                >
                  ⚡ EPS Solar Loss &amp; Battery Drain
                </button>
                <button
                  type="button"
                  className={`btn ${demoVariable === 'temp_c' ? 'btn-amber' : 'btn-ghost'}`}
                  onClick={() => handleSelectPreset('tcs')}
                  style={{ fontSize: '11px', padding: '5px 10px' }}
                >
                  🔥 TCS Thermal Heater Spike
                </button>
                <button
                  type="button"
                  className={`btn ${demoVariable === 'attitude_deg' ? 'btn-amber' : 'btn-ghost'}`}
                  onClick={() => handleSelectPreset('adcs')}
                  style={{ fontSize: '11px', padding: '5px 10px' }}
                >
                  🧭 ADCS Reaction Wheel Slew Offset
                </button>
                <button
                  type="button"
                  className={`btn ${demoVariable === 'link_margin_db' ? 'btn-amber' : 'btn-ghost'}`}
                  onClick={() => handleSelectPreset('comms')}
                  style={{ fontSize: '11px', padding: '5px 10px' }}
                >
                  📡 COMMS Ground Pass Carrier Dropout
                </button>
                <button
                  type="button"
                  className={`btn ${demoVariable === 'storage_used_mb' ? 'btn-amber' : 'btn-ghost'}`}
                  onClick={() => handleSelectPreset('cdh')}
                  style={{ fontSize: '11px', padding: '5px 10px' }}
                >
                  💾 CDH Flash Memory SEU Bitflip
                </button>
              </div>
            </div>

            {/* Timing Controls Grid */}
            <div className="grid g3">
              {/* Trigger Mode */}
              <div style={{ background: 'var(--ink)', padding: '12px', borderRadius: 'var(--radius)', border: '1px solid var(--border)' }}>
                <div className="label-mono">TIMING TRIGGER MODE</div>
                <div style={{ display: 'flex', gap: '6px', marginTop: '6px' }}>
                  <button
                    type="button"
                    className={`btn ${demoTriggerMode === 'immediate' ? 'btn-amber' : 'btn-ghost'}`}
                    style={{ flex: 1, padding: '4px', fontSize: '11px' }}
                    onClick={() => setDemoTriggerMode('immediate')}
                  >
                    IMMEDIATE NOW
                  </button>
                  <button
                    type="button"
                    className={`btn ${demoTriggerMode === 'timestamp' ? 'btn-amber' : 'btn-ghost'}`}
                    style={{ flex: 1, padding: '4px', fontSize: '11px' }}
                    onClick={() => setDemoTriggerMode('timestamp')}
                  >
                    EXACT TIMESTAMP
                  </button>
                </div>
                <div style={{ fontSize: '10px', color: 'var(--paper-dim)', marginTop: '6px' }}>
                  {demoTriggerMode === 'immediate'
                    ? 'Instantly fires anomaly & forces AI alert on current tick.'
                    : `Fires precisely at programmed timestamp T+${customTimestamp}s.`}
                </div>
              </div>

              {/* Exact Timestamp / Delay Tuning */}
              <div style={{ background: 'var(--ink)', padding: '12px', borderRadius: 'var(--radius)', border: '1px solid var(--border)' }}>
                <div className="flex-between">
                  <span className="label-mono">TARGET SIM TIMESTAMP</span>
                  <span className="mono" style={{ color: 'var(--amber)', fontSize: '11px' }}>Current: T+{state.t}s</span>
                </div>
                <input
                  type="number"
                  value={customTimestamp}
                  onChange={(e) => setCustomTimestamp(parseInt(e.target.value) || state.t + 5)}
                  disabled={demoTriggerMode === 'immediate'}
                  style={{
                    width: '100%',
                    background: 'var(--panel)',
                    border: '1px solid var(--border)',
                    color: 'var(--paper)',
                    padding: '6px 10px',
                    fontFamily: 'var(--font-mono)',
                    borderRadius: 'var(--radius)',
                    marginTop: '6px',
                  }}
                />
              </div>

              {/* Severity & Z-Score Residual */}
              <div style={{ background: 'var(--ink)', padding: '12px', borderRadius: 'var(--radius)', border: '1px solid var(--border)' }}>
                <div className="flex-between">
                  <span className="label-mono">STATISTICAL Z-SCORE</span>
                  <span className="mono" style={{ color: 'var(--status-red)', fontSize: '11px' }}>{demoZScore}σ</span>
                </div>
                <input
                  type="range"
                  min="2.5"
                  max="6.0"
                  step="0.1"
                  value={demoZScore}
                  onChange={(e) => setDemoZScore(parseFloat(e.target.value))}
                  style={{ width: '100%', accentColor: 'var(--status-red)', marginTop: '10px' }}
                />
              </div>
            </div>

            {/* Action Trigger Button */}
            <button
              type="button"
              className="btn btn-amber"
              onClick={handleTriggerManualAnomaly}
              style={{
                width: '100%',
                justifyContent: 'center',
                padding: '12px',
                fontSize: '13px',
                fontWeight: 700,
                letterSpacing: '1px',
                boxShadow: '0 0 14px rgba(255, 122, 51, 0.3)',
              }}
            >
              <PlayIcon size={16} />
              {demoTriggerMode === 'immediate'
                ? `TRIGGER ${demoVariable.toUpperCase()} ANOMALY NOW (DEMO OVERRIDE)`
                : `SCHEDULE ${demoVariable.toUpperCase()} FOR T+${customTimestamp}s`}
            </button>
          </div>
        </div>
      )}

      {/* Metric Summary Cards */}
      <div className="grid g4">
        <div className="card metric-card">
          <div className="metric-label">
            <AlertTriangleIcon size={14} color="var(--status-red)" />
            <span>Active Alerts</span>
          </div>
          <div
            className="metric-value"
            style={{ color: alerts.length > 0 ? 'var(--status-red)' : 'var(--status-green)' }}
          >
            {alerts.length}
          </div>
          <div className="metric-sub">Debounced 3-tick threshold window</div>
        </div>

        <div className="card metric-card">
          <div className="metric-label">
            <GitBranchIcon size={14} color="var(--amber)" />
            <span>Suspect Streams</span>
          </div>
          <div className="metric-value" style={{ color: 'var(--amber)' }}>
            {suspectStreams.length > 0 ? suspectStreams.length : 'NONE'}
          </div>
          <div className="metric-sub">Telemetry channels flagged for bypass</div>
        </div>

        <div className="card metric-card">
          <div className="metric-label">
            <SparklesIcon size={14} color="var(--status-teal)" />
            <span>Root-Cause Confidence</span>
          </div>
          <div className="metric-value" style={{ color: 'var(--status-teal)' }}>
            {state.root_cause_diagnosis ? `${(state.root_cause_diagnosis.confidence * 100).toFixed(0)}%` : '100% NOM'}
          </div>
          <div className="metric-sub">Coupling graph correlation</div>
        </div>

        <div className="card metric-card">
          <div className="metric-label">
            <ShieldCheckIcon size={14} color="var(--status-plum)" />
            <span>AI Procedure Status</span>
          </div>
          <div className="metric-value" style={{ color: 'var(--paper)' }}>
            {aiDiagnosis?.suggested_procedures.filter((p) => p.status === 'completed').length || 0} /{' '}
            {aiDiagnosis?.suggested_procedures.length || 0}
          </div>
          <div className="metric-sub">Operator recovery checklist items</div>
        </div>
      </div>

      {/* Main Split: Anomalies Table + AI Explainable Diagnosis Panel */}
      <div className="grid g-2-1">
        {/* Left: Active Anomalies Table */}
        <div className="card">
          <div className="card-title">
            <span>Real-Time Anomaly Alert Log</span>
            <span className="mono">{alerts.length} ACTIVE</span>
          </div>

          {alerts.length > 0 ? (
            <table>
              <thead>
                <tr>
                  <th>Severity</th>
                  <th>Subsystem</th>
                  <th>Variable</th>
                  <th>Residual</th>
                  <th>Z-Score</th>
                  <th>Detected Tick</th>
                  <th>Authority Action</th>
                </tr>
              </thead>
              <tbody>
                {alerts.map((alert) => (
                  <tr
                    key={alert.alert_id}
                    style={{
                      background: selectedAlert?.alert_id === alert.alert_id ? 'var(--amber-dim)' : 'transparent',
                      cursor: 'pointer',
                    }}
                    onClick={() => setSelectedAlert(alert)}
                  >
                    <td>
                      <span
                        className={`badge ${
                          alert.severity === 'critical'
                            ? 'badge-red'
                            : alert.severity === 'warning'
                            ? 'badge-amber'
                            : 'badge-teal'
                        }`}
                      >
                        <span className="badge-dot" />
                        {alert.severity.toUpperCase()}
                      </span>
                    </td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, color: 'var(--paper)' }}>
                      {alert.subsystem}
                    </td>
                    <td className="mono">{alert.variable}</td>
                    <td className="mono" style={{ color: 'var(--status-red)' }}>
                      {alert.residual ? alert.residual.toFixed(3) : 'Δ > 2.5σ'}
                    </td>
                    <td className="mono">{alert.z_score ? alert.z_score.toFixed(1) : '3.8σ'}</td>
                    <td className="mono" style={{ color: 'var(--amber)' }}>
                      T+{alert.detected_at_t}s
                    </td>
                    <td>
                      {alert.acknowledged ? (
                        <span className="badge badge-green">ACKNOWLEDGED</span>
                      ) : (
                        <button
                          type="button"
                          className="btn btn-ghost"
                          style={{ padding: '3px 8px', fontSize: '10px' }}
                          onClick={(e) => {
                            e.stopPropagation();
                            handleAcknowledge(alert.alert_id);
                          }}
                        >
                          <CheckIcon size={12} /> ACK
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div style={{ textAlign: 'center', padding: '32px', color: 'var(--paper-muted)' }}>
              <CheckIcon size={24} color="var(--status-green)" />
              <div style={{ marginTop: '8px', color: 'var(--paper)', fontWeight: 600 }}>All Telemetry Nominal</div>
              <div style={{ fontSize: '11px', marginTop: '4px' }}>
                Use the Presenter Demo Timing panel above to trigger instant or scheduled anomaly scenarios.
              </div>
            </div>
          )}

          {/* Avionics Coupling & Cascade Visualization */}
          <div style={{ marginTop: '20px', paddingTop: '16px', borderTop: '1px solid var(--border)' }}>
            <div className="card-title">
              <span>Avionics Coupling &amp; Root-Cause Cascade Graph</span>
            </div>

            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '12px 16px',
                background: 'var(--ink)',
                borderRadius: 'var(--radius)',
                border: '1px solid var(--border)',
              }}
            >
              <div style={{ textAlign: 'center' }}>
                <div className="label-mono">ORIGIN</div>
                <div
                  className="badge badge-red"
                  style={{ marginTop: '4px', fontSize: '11px', padding: '4px 10px' }}
                >
                  Solar Flux Drop
                </div>
              </div>

              <span style={{ color: 'var(--amber)', fontFamily: 'var(--font-mono)' }}>➔ 140s</span>

              <div style={{ textAlign: 'center' }}>
                <div className="label-mono">CASCADE 1</div>
                <div
                  className="badge badge-amber"
                  style={{ marginTop: '4px', fontSize: '11px', padding: '4px 10px' }}
                >
                  Battery SOC Discharge
                </div>
              </div>

              <span style={{ color: 'var(--amber)', fontFamily: 'var(--font-mono)' }}>➔ 142s</span>

              <div style={{ textAlign: 'center' }}>
                <div className="label-mono">CASCADE 2</div>
                <div
                  className="badge badge-amber"
                  style={{ marginTop: '4px', fontSize: '11px', padding: '4px 10px' }}
                >
                  Bus Undervoltage
                </div>
              </div>

              <span style={{ color: 'var(--amber)', fontFamily: 'var(--font-mono)' }}>➔ 145s</span>

              <div style={{ textAlign: 'center' }}>
                <div className="label-mono">EFFECT</div>
                <div
                  className="badge badge-teal"
                  style={{ marginTop: '4px', fontSize: '11px', padding: '4px 10px' }}
                >
                  TCS Heater Throttle
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Right: Gemini AI Explainable Diagnostics Panel */}
        <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <div className="card-title">
            <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <SparklesIcon size={14} color="var(--amber)" />
              Gemini Explainable Diagnosis
            </span>
            <span className="mono" style={{ color: 'var(--amber)' }}>
              LLM REASONING
            </span>
          </div>

          <div
            style={{
              padding: '12px',
              background: 'var(--ink)',
              borderRadius: 'var(--radius)',
              border: '1px solid var(--border)',
              lineHeight: 1.6,
              color: 'var(--paper)',
              fontSize: '12px',
            }}
          >
            {aiDiagnosis ? (
              aiDiagnosis.diagnosis
            ) : (
              <span style={{ color: 'var(--paper-muted)' }}>
                Click &quot;Run Gemini Diagnosis&quot; to generate plain-language technical root cause analysis.
              </span>
            )}
          </div>

          {/* AI Recommended Recovery Checklist */}
          <div>
            <div className="label-mono" style={{ marginBottom: '8px' }}>
              RECOMMENDED RECOVERY PROCEDURES
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {(aiDiagnosis?.suggested_procedures || []).map((proc, idx) => (
                <div
                  key={proc.step}
                  onClick={() => handleStepStatus(idx)}
                  style={{
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: '10px',
                    padding: '8px 10px',
                    background: proc.status === 'completed' ? 'var(--status-green-bg)' : 'var(--panel-hover)',
                    borderRadius: 'var(--radius)',
                    border: `1px solid ${proc.status === 'completed' ? 'rgba(107,155,110,0.3)' : 'var(--border)'}`,
                    cursor: 'pointer',
                  }}
                >
                  <div
                    style={{
                      width: '18px',
                      height: '18px',
                      borderRadius: 'var(--radius)',
                      border: `1px solid ${proc.status === 'completed' ? 'var(--status-green)' : 'var(--border)'}`,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      flexShrink: 0,
                      marginTop: '2px',
                    }}
                  >
                    {proc.status === 'completed' && <CheckIcon size={12} color="var(--status-green)" />}
                  </div>

                  <div>
                    <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--paper)' }}>
                      Step {proc.step}: {proc.title}
                    </div>
                    <div style={{ fontSize: '10px', color: 'var(--paper-dim)', marginTop: '2px' }}>
                      {proc.description}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
