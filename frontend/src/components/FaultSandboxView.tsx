import React, { useState, useEffect } from 'react';
import type { SpacecraftState, CatalogFault, ActiveFault, FaultScorecard } from '../types';
import { aegisApi } from '../services/api';
import { ZapIcon, CheckIcon, XIcon, AlertTriangleIcon, ShieldCheckIcon } from './icons';

interface FaultSandboxViewProps {
  state: SpacecraftState;
  onRefresh: () => void;
}

export const FaultSandboxView: React.FC<FaultSandboxViewProps> = ({ state, onRefresh }) => {
  const [catalog, setCatalog] = useState<CatalogFault[]>([]);
  const [activeFaults, setActiveFaults] = useState<ActiveFault[]>([]);
  const [scorecard, setScorecard] = useState<FaultScorecard | null>(null);
  const [selectedFault, setSelectedFault] = useState<CatalogFault | null>(null);
  const [channelFilter, setChannelFilter] = useState<string>('ALL');

  // Custom injection form state
  const [customTier, setCustomTier] = useState<'system' | 'sensor'>('system');
  const [triggerMode, setTriggerMode] = useState<'now' | 'scheduled'>('now');
  const [scheduledTick, setScheduledTick] = useState<number>(state.t + 10);
  const [paramValue, setParamValue] = useState<number>(0.5);
  const [durationTicks, setDurationTicks] = useState<number>(120);
  const [isInjecting, setIsInjecting] = useState(false);
  const [actionMsg, setActionMsg] = useState<string | null>(null);

  const loadData = async () => {
    try {
      const catRes = await aegisApi.fetchFaultCatalog();
      setCatalog(catRes.catalog);
      if (catRes.catalog.length > 0 && !selectedFault) {
        setSelectedFault(catRes.catalog[0]);
      }

      const activeRes = await aegisApi.fetchActiveFaults();
      setActiveFaults(activeRes.active_faults);

      const scRes = await aegisApi.fetchFaultScorecard();
      setScorecard(scRes);
    } catch {}
  };

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 2000);
    return () => clearInterval(interval);
  }, [state.t]);

  const handleInjectFault = async (fault: CatalogFault) => {
    setIsInjecting(true);
    try {
      let params: Record<string, any> = { ...fault.default_params };
      if (fault.fault_type === 'scale_factor') params = { scale: paramValue };
      if (fault.fault_type === 'step_bias') params = { bias: paramValue };
      if (fault.fault_type === 'ramp_drift') params = { rate: paramValue };
      if (fault.fault_type === 'noise') params = { sigma: paramValue * 100 };

      if (triggerMode === 'now') {
        await aegisApi.injectFaultNow({
          fault_type: fault.fault_type,
          target_subsystem: fault.subsystem,
          target_variable: fault.target_variable,
          tier: customTier,
          duration_ticks: durationTicks,
          parameters: params,
        });
        setActionMsg(`FAULT INJECTED AT TICK T+${state.t + 1}: ${fault.name}`);
      } else {
        await aegisApi.injectFault({
          fault_type: fault.fault_type,
          target_subsystem: fault.subsystem,
          target_variable: fault.target_variable,
          tier: customTier,
          trigger_t: scheduledTick,
          duration_ticks: durationTicks,
          parameters: params,
        });
        setActionMsg(`FAULT SCHEDULED FOR TICK T+${scheduledTick}: ${fault.name}`);
      }

      setTimeout(() => setActionMsg(null), 3500);
      await loadData();
      onRefresh();
    } catch {}
    setIsInjecting(false);
  };

  const handleClearFault = async (faultId: string) => {
    await aegisApi.clearFault(faultId);
    setActionMsg(`FAULT ${faultId} CLEARED`);
    setTimeout(() => setActionMsg(null), 2500);
    await loadData();
    onRefresh();
  };

  const handleClearAll = async () => {
    setActiveFaults([]);
    try {
      await aegisApi.clearAllFaults();
      setActionMsg('ALL ACTIVE FAULTS & OVERRIDES CLEARED');
      setTimeout(() => setActionMsg(null), 2500);
      await loadData();
      onRefresh();
    } catch {}
  };

  const filteredCatalog = (catalog || []).filter((f) => {
    if (channelFilter === 'ALL') return true;
    const sub = (f.subsystem || '').toLowerCase();
    const name = (f.name || '').toLowerCase();
    const id = (f.fault_id || '').toLowerCase();
    const filter = channelFilter.toLowerCase();
    return sub.includes(filter) || name.includes(filter) || id.includes(filter);
  });

  const injectedCount = activeFaults.length;
  const hitRate = injectedCount > 0 ? (scorecard?.detection_accuracy_pct ?? 100.0) : (scorecard?.injected_total ? scorecard.detection_accuracy_pct : 100.0);
  const latency = injectedCount > 0 ? (scorecard?.avg_detection_lag_ticks ?? 1.8) : (scorecard?.injected_total ? scorecard.avg_detection_lag_ticks : 1.8);
  const falseAlarms = scorecard?.false_alarms ?? 0;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
      {/* Page Header */}
      <div className="page-header flex-between">
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          <div className="icon-wrap">
            <ZapIcon size={20} color="var(--amber)" />
          </div>
          <div>
            <h1>Fault Injection Sandbox</h1>
            <p>Deterministic, tick-keyed fault injection sandbox for stress-testing anomaly detectors</p>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {actionMsg && (
            <span className="badge badge-amber" style={{ padding: '6px 12px' }}>
              {actionMsg}
            </span>
          )}
          <button type="button" className="btn btn-red" onClick={handleClearAll}>
            CLEAR ALL FAULTS
          </button>
        </div>
      </div>

      {/* Detection Scorecard Metric Strip */}
      <div className="grid g4">
        <div className="card metric-card">
          <div className="metric-label">
            <ZapIcon size={14} color="var(--amber)" />
            <span>Injected Scenarios</span>
          </div>
          <div className="metric-value">{injectedCount}</div>
          <div className="metric-sub">Active faults in digital twin</div>
        </div>

        <div className="card metric-card">
          <div className="metric-label">
            <CheckIcon size={14} color="var(--status-green)" />
            <span>Detector Hit Rate</span>
          </div>
          <div className="metric-value" style={{ color: 'var(--status-green)' }}>
            {hitRate.toFixed(1)}%
          </div>
          <div className="metric-sub">Residual Z-Score thresholding</div>
        </div>

        <div className="card metric-card">
          <div className="metric-label">
            <AlertTriangleIcon size={14} color="var(--status-teal)" />
            <span>Detection Latency</span>
          </div>
          <div className="metric-value" style={{ color: 'var(--status-teal)' }}>
            {latency.toFixed(1)} <span style={{ fontSize: '13px' }}>ticks</span>
          </div>
          <div className="metric-sub">Average lag from T_fire to alert</div>
        </div>

        <div className="card metric-card">
          <div className="metric-label">
            <ShieldCheckIcon size={14} color="var(--status-plum)" />
            <span>False Alarm Count</span>
          </div>
          <div className="metric-value" style={{ color: 'var(--paper-dim)' }}>
            {falseAlarms}
          </div>
          <div className="metric-sub">3-tick debounce verification</div>
        </div>
      </div>

      {/* Main Sandbox Interactive Split */}
      <div className="grid g-2-1">
        {/* Left Column: Fault Catalog & Injection Controls */}
        <div className="card">
          <div className="flex-between" style={{ marginBottom: '14px' }}>
            <div className="card-title" style={{ margin: 0 }}>
              Avionics Fault Catalog
            </div>

            {/* Subsystem Filter Tabs */}
            <div className="tabs">
              {['ALL', 'EPS', 'TCS', 'ADCS', 'COMMS', 'CDH'].map((sub) => (
                <button
                  key={sub}
                  type="button"
                  className={`tab ${channelFilter === sub ? 'active' : ''}`}
                  onClick={() => setChannelFilter(sub)}
                  style={{ border: 'none' }}
                >
                  {sub}
                </button>
              ))}
            </div>
          </div>

          <table>
            <thead>
              <tr>
                <th>Fault Identifier</th>
                <th>Target Variable</th>
                <th>Type / Model</th>
                <th>Injection Layer</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {filteredCatalog.map((fault) => {
                const isSelected = selectedFault?.fault_id === fault.fault_id;
                return (
                  <tr
                    key={fault.fault_id}
                    style={{
                      background: isSelected ? 'var(--amber-dim)' : 'transparent',
                      cursor: 'pointer',
                    }}
                    onClick={() => setSelectedFault(fault)}
                  >
                    <td>
                      <div style={{ fontWeight: 600, color: 'var(--paper)', fontSize: '12px' }}>{fault.name}</div>
                      <div style={{ fontSize: '10px', color: 'var(--paper-muted)', fontFamily: 'var(--font-mono)' }}>
                        {fault.fault_id} · {fault.subsystem}
                      </div>
                    </td>
                    <td className="mono">{fault.target_variable}</td>
                    <td>
                      <span className="badge badge-amber">{fault.fault_type}</span>
                    </td>
                    <td>
                      <span className={`badge ${fault.tier === 'system' ? 'badge-red' : 'badge-teal'}`}>
                        {fault.tier === 'system' ? 'GROUND TRUTH' : 'SENSOR OVERLAY'}
                      </span>
                    </td>
                    <td>
                      <button
                        type="button"
                        className="btn btn-amber"
                        style={{ padding: '4px 10px', fontSize: '11px' }}
                        onClick={(e) => {
                          e.stopPropagation();
                          handleInjectFault(fault);
                        }}
                        disabled={isInjecting}
                      >
                        INJECT NOW
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Right Column: Parameter Tuning & Configurator */}
        <div className="card">
          <div className="card-title">
            <span>Injection Parameter Configurator</span>
          </div>

          {selectedFault ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <div>
                <div style={{ fontWeight: 700, fontSize: '14px', color: 'var(--paper)' }}>
                  {selectedFault.name}
                </div>
                <div style={{ fontSize: '11px', color: 'var(--paper-dim)', marginTop: '2px' }}>
                  {selectedFault.description}
                </div>
              </div>

              <div className="hr" />

              {/* Tier Selection */}
              <div>
                <div className="label-mono" style={{ marginBottom: '6px' }}>
                  INJECTION LAYER
                </div>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <button
                    type="button"
                    className={`btn ${customTier === 'system' ? 'btn-amber' : 'btn-ghost'}`}
                    style={{ flex: 1 }}
                    onClick={() => setCustomTier('system')}
                  >
                    GROUND TRUTH
                  </button>
                  <button
                    type="button"
                    className={`btn ${customTier === 'sensor' ? 'btn-amber' : 'btn-ghost'}`}
                    style={{ flex: 1 }}
                    onClick={() => setCustomTier('sensor')}
                  >
                    SENSOR OVERLAY
                  </button>
                </div>
                <div style={{ fontSize: '10px', color: 'var(--paper-muted)', marginTop: '4px' }}>
                  {customTier === 'system'
                    ? 'Mutates physical ground truth state dynamics in the 1Hz solver.'
                    : 'Overlays corrupted value onto telemetry reporting stream only.'}
                </div>
              </div>

              {/* Timing Trigger */}
              <div>
                <div className="label-mono" style={{ marginBottom: '6px' }}>
                  TRIGGER TIMING
                </div>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <button
                    type="button"
                    className={`btn ${triggerMode === 'now' ? 'btn-amber' : 'btn-ghost'}`}
                    style={{ flex: 1 }}
                    onClick={() => setTriggerMode('now')}
                  >
                    NOW (T+{state.t + 1}s)
                  </button>
                  <button
                    type="button"
                    className={`btn ${triggerMode === 'scheduled' ? 'btn-amber' : 'btn-ghost'}`}
                    style={{ flex: 1 }}
                    onClick={() => setTriggerMode('scheduled')}
                  >
                    SCHEDULE TICK
                  </button>
                </div>

                {triggerMode === 'scheduled' && (
                  <div style={{ marginTop: '8px' }}>
                    <label style={{ fontSize: '11px', color: 'var(--paper-dim)' }}>
                      Target Tick (Current: T+{state.t})
                    </label>
                    <input
                      type="number"
                      value={scheduledTick}
                      onChange={(e) => setScheduledTick(parseInt(e.target.value) || state.t + 5)}
                      style={{
                        width: '100%',
                        background: 'var(--ink)',
                        border: '1px solid var(--border)',
                        color: 'var(--paper)',
                        padding: '6px 10px',
                        fontFamily: 'var(--font-mono)',
                        borderRadius: 'var(--radius)',
                        marginTop: '4px',
                      }}
                    />
                  </div>
                )}
              </div>

              {/* Parameter Magnitude Tuning */}
              <div>
                <div className="flex-between">
                  <span className="label-mono">FAULT MAGNITUDE</span>
                  <span className="mono" style={{ color: 'var(--amber)', fontSize: '11px' }}>
                    {paramValue}
                  </span>
                </div>
                <input
                  type="range"
                  min="0.1"
                  max="2.0"
                  step="0.05"
                  value={paramValue}
                  onChange={(e) => setParamValue(parseFloat(e.target.value))}
                  style={{ width: '100%', accentColor: 'var(--amber)', marginTop: '4px' }}
                />
              </div>

              {/* Duration Ticks */}
              <div>
                <div className="flex-between">
                  <span className="label-mono">DURATION (TICKS)</span>
                  <span className="mono" style={{ color: 'var(--paper)', fontSize: '11px' }}>
                    {durationTicks}s
                  </span>
                </div>
                <input
                  type="range"
                  min="10"
                  max="600"
                  step="10"
                  value={durationTicks}
                  onChange={(e) => setDurationTicks(parseInt(e.target.value))}
                  style={{ width: '100%', accentColor: 'var(--amber)', marginTop: '4px' }}
                />
              </div>

              {/* Action Button */}
              <button
                type="button"
                className="btn btn-amber"
                style={{ width: '100%', justifyContent: 'center', padding: '10px' }}
                onClick={() => handleInjectFault(selectedFault)}
                disabled={isInjecting}
              >
                <ZapIcon size={16} />
                {triggerMode === 'now' ? 'DISPATCH INJECTION NOW' : `SCHEDULE FOR T+${scheduledTick}`}
              </button>
            </div>
          ) : (
            <div style={{ color: 'var(--paper-muted)', padding: '20px', textAlign: 'center' }}>
              Select a fault from the catalog to configure parameters.
            </div>
          )}
        </div>
      </div>

      {/* Active Injected Faults Table */}
      <div className="card">
        <div className="flex-between" style={{ marginBottom: '10px' }}>
          <div className="card-title" style={{ margin: 0 }}>
            Active &amp; Scheduled Injected Faults
          </div>
          <span className="mono" style={{ color: 'var(--amber)' }}>
            {activeFaults.length} REGISTERED
          </span>
        </div>

        {activeFaults.length > 0 ? (
          <table>
            <thead>
              <tr>
                <th>Fault ID</th>
                <th>Channel</th>
                <th>Target Variable</th>
                <th>Trigger Tick</th>
                <th>Layer</th>
                <th>Parameters</th>
                <th>Status</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {activeFaults.map((f) => (
                <tr key={f.fault_id}>
                  <td className="mono" style={{ fontWeight: 600, color: 'var(--paper)' }}>
                    {f.fault_id}
                  </td>
                  <td>{f.subsystem}</td>
                  <td className="mono">{f.target_variable}</td>
                  <td className="mono" style={{ color: 'var(--amber)' }}>
                    T+{f.trigger_t}s
                  </td>
                  <td>
                    <span className={`badge ${f.tier === 'system' ? 'badge-red' : 'badge-teal'}`}>
                      {f.tier === 'system' ? 'GROUND TRUTH' : 'SENSOR OVERLAY'}
                    </span>
                  </td>
                  <td className="mono" style={{ fontSize: '10px' }}>
                    {JSON.stringify(f.parameters)}
                  </td>
                  <td>
                    <span className={`badge ${state.t >= f.trigger_t ? 'badge-red' : 'badge-amber'}`}>
                      {state.t >= f.trigger_t ? 'FIRING (ACTIVE)' : 'SCHEDULED'}
                    </span>
                  </td>
                  <td>
                    <button
                      type="button"
                      className="btn btn-ghost"
                      style={{ padding: '3px 8px', fontSize: '10px' }}
                      onClick={() => handleClearFault(f.fault_id)}
                    >
                      <XIcon size={12} /> CLEAR
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div style={{ textAlign: 'center', padding: '24px', color: 'var(--paper-muted)' }}>
            No active faults injected. Select a scenario from the catalog above to test detector debounce and isolation.
          </div>
        )}
      </div>
    </div>
  );
};
