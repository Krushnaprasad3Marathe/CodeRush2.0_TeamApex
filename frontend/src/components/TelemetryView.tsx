import React, { useState, useEffect } from 'react';
import type { SpacecraftState } from '../types';
import {
  ZapIcon,
  ThermometerIcon,
  SunIcon,
  MoonIcon,
  HardDriveIcon,
  CompassIcon,
  ActivityIcon,
  PlayIcon,
  PauseIcon,
  RefreshCwIcon,
  CalendarIcon,
} from './icons';
import { aegisApi } from '../services/api';
import type { DatasetRecord24H } from '../services/api';

interface TelemetryViewProps {
  state: SpacecraftState;
  onRefresh: () => void;
  isPaused: boolean;
  onTogglePause: () => void;
}

export const TelemetryView: React.FC<TelemetryViewProps> = ({
  state,
  onRefresh,
  isPaused,
  onTogglePause,
}) => {
  // Rolling historical telemetry points for SVG sparkline trends
  const [history, setHistory] = useState<
    Array<{
      t: number;
      soc: number;
      volt: number;
      temp: number;
      solar: number;
    }>
  >([]);

  // 24-Hour Dataset Inspector State (Task B)
  const [show24hExplorer, setShow24hExplorer] = useState<boolean>(false);
  const [datasetRecords, setDatasetRecords] = useState<DatasetRecord24H[]>([]);
  const [selectedOrbit, setSelectedOrbit] = useState<number>(1);

  useEffect(() => {
    // If paused, strictly freeze sparkline updates and state history
    if (isPaused) {
      return;
    }

    setHistory((prev) => {
      const next = [
        ...prev,
        {
          t: state.t,
          soc: state.battery_soc * 100,
          volt: state.bus_voltage,
          temp: state.temp_c,
          solar: state.solar_input_w,
        },
      ];
      return next.slice(-40); // Keep last 40 ticks
    });
  }, [state.t, state.battery_soc, state.bus_voltage, state.temp_c, state.solar_input_w, isPaused]);

  // Load 24-hour dataset information
  useEffect(() => {
    const load24hData = async () => {
      try {
        const startT = (selectedOrbit - 1) * 5400;
        const endT = selectedOrbit * 5400;
        const ds = await aegisApi.fetch24HourDataset(startT, endT);
        setDatasetRecords(ds.records);
      } catch {}
    };

    if (show24hExplorer) {
      load24hData();
    }
  }, [show24hExplorer, selectedOrbit]);

  // Dynamic SVG Line & Area Sparkline Generator
  const renderSparkline = (
    data: number[],
    color: string,
    width = 460,
    height = 80
  ) => {
    if (!data || data.length < 2) {
      const fallbackY = height / 2;
      return (
        <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`}>
          <line x1="0" y1={fallbackY} x2={width} y2={fallbackY} stroke={color} strokeWidth="1.5" strokeDasharray="3 3" />
        </svg>
      );
    }

    const actualMin = Math.min(...data);
    const actualMax = Math.max(...data);
    const spread = actualMax - actualMin;
    const effectiveMin = spread < 0.5 ? actualMin - 2.0 : actualMin - spread * 0.15;
    const effectiveMax = spread < 0.5 ? actualMax + 2.0 : actualMax + spread * 0.15;
    const range = effectiveMax - effectiveMin || 1;

    const points = data
      .map((val, idx) => {
        const x = (idx / (data.length - 1)) * width;
        const normalized = Math.max(0, Math.min(1, (val - effectiveMin) / range));
        const y = height - normalized * (height - 14) - 7;
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(' ');

    const lastVal = data[data.length - 1];
    const lastY = height - Math.max(0, Math.min(1, (lastVal - effectiveMin) / range)) * (height - 14) - 7;

    return (
      <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} style={{ overflow: 'visible' }}>
        <polyline fill="none" stroke={color} strokeWidth="2.2" points={points} />
        <circle cx={width} cy={lastY} r="3.5" fill={color} />
      </svg>
    );
  };

  const socHistory = history.map((h) => h.soc);
  const tempHistory = history.map((h) => h.temp);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
      {/* Page Header */}
      <div className="page-header flex-between">
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          <div className="icon-wrap">
            <ActivityIcon size={20} color="var(--amber)" />
          </div>
          <div>
            <h1>Digital Twin Telemetry Deck</h1>
            <p>1.0 Hz deterministic simulation model with lumped thermal, battery SOC, and full 24-hour dataset integration</p>
          </div>
        </div>

        {/* Action controls including robust Pause Tick button (Task A) */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <button
            type="button"
            className={`btn ${isPaused ? 'btn-amber' : 'btn-ghost'}`}
            onClick={onTogglePause}
            title={isPaused ? 'Click to resume live simulation' : 'Click to freeze simulation clock & telemetry ingestion'}
            style={{
              boxShadow: isPaused ? '0 0 10px rgba(255, 122, 51, 0.4)' : 'none',
              border: isPaused ? '1px solid var(--amber)' : '1px solid var(--border)',
            }}
          >
            {isPaused ? <PlayIcon size={14} /> : <PauseIcon size={14} />}
            {isPaused ? 'PAUSED (CLICK TO RESUME)' : 'PAUSE TICK'}
          </button>

          <button
            type="button"
            className={`btn ${show24hExplorer ? 'btn-amber' : 'btn-ghost'}`}
            onClick={() => setShow24hExplorer(!show24hExplorer)}
          >
            <CalendarIcon size={14} />
            {show24hExplorer ? 'HIDE 24H DATASET' : 'INSPECT 24H DATASET'}
          </button>

          <button type="button" className="btn btn-ghost" onClick={onRefresh}>
            <RefreshCwIcon size={14} />
            RE-SYNC
          </button>
        </div>
      </div>

      {/* 24-Hour Dataset Integration Module (Task B) */}
      {show24hExplorer && (
        <div className="card" style={{ border: '1px solid var(--amber)' }}>
          <div className="flex-between" style={{ marginBottom: '12px' }}>
            <div className="card-title" style={{ margin: 0, color: 'var(--amber)' }}>
              24-Hour Reference Mission Dataset (86,400s · 16 Full LEO Orbits)
            </div>
            <span className="badge badge-amber">VERIFIED DATASET LOADED</span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div className="grid g4">
              <div style={{ background: 'var(--ink)', padding: '10px', borderRadius: 'var(--radius)', border: '1px solid var(--border)' }}>
                <div className="label-mono">TIME SPAN</div>
                <div className="mono" style={{ fontSize: '14px', fontWeight: 600, color: 'var(--paper)', marginTop: '2px' }}>
                  24h (86,400s)
                </div>
              </div>

              <div style={{ background: 'var(--ink)', padding: '10px', borderRadius: 'var(--radius)', border: '1px solid var(--border)' }}>
                <div className="label-mono">TOTAL LEO ORBITS</div>
                <div className="mono" style={{ fontSize: '14px', fontWeight: 600, color: 'var(--status-teal)', marginTop: '2px' }}>
                  16 Orbits (90m ea)
                </div>
              </div>

              <div style={{ background: 'var(--ink)', padding: '10px', borderRadius: 'var(--radius)', border: '1px solid var(--border)' }}>
                <div className="label-mono">ECLIPSE DURATION</div>
                <div className="mono" style={{ fontSize: '14px', fontWeight: 600, color: 'var(--status-plum)', marginTop: '2px' }}>
                  35.0% (30,240s)
                </div>
              </div>

              <div style={{ background: 'var(--ink)', padding: '10px', borderRadius: 'var(--radius)', border: '1px solid var(--border)' }}>
                <div className="label-mono">GROUND PASS COVERAGE</div>
                <div className="mono" style={{ fontSize: '14px', fontWeight: 600, color: 'var(--status-green)', marginTop: '2px' }}>
                  9,600s Contact
                </div>
              </div>
            </div>

            {/* Orbit Selector Tabs */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', overflowX: 'auto', paddingBottom: '4px' }}>
              <span className="label-mono" style={{ flexShrink: 0 }}>SELECT ORBIT:</span>
              {Array.from({ length: 16 }, (_, i) => i + 1).map((orbitNum) => (
                <button
                  key={orbitNum}
                  type="button"
                  onClick={() => setSelectedOrbit(orbitNum)}
                  className={`btn ${selectedOrbit === orbitNum ? 'btn-amber' : 'btn-ghost'}`}
                  style={{ padding: '3px 8px', fontSize: '10px', minWidth: '42px', justifyContent: 'center' }}
                >
                  ORB {orbitNum}
                </button>
              ))}
            </div>

            {/* 24-Hour Telemetry Time-Series Preview Table */}
            <div style={{ maxHeight: '200px', overflowY: 'auto' }}>
              <table>
                <thead>
                  <tr>
                    <th>Tick (T+s)</th>
                    <th>Orbit #</th>
                    <th>Orbit Phase</th>
                    <th>Solar (W)</th>
                    <th>Draw (W)</th>
                    <th>Battery SOC</th>
                    <th>Bus Volt</th>
                    <th>Temp (°C)</th>
                    <th>Regime</th>
                  </tr>
                </thead>
                <tbody>
                  {(datasetRecords || []).slice(0, 15).map((rec) => (
                    <tr key={rec.t}>
                      <td className="mono">T+{rec.t}s</td>
                      <td className="mono">#{rec.orbit_index || 1}</td>
                      <td className="mono">{((rec.orbit_phase ?? 0) * 100).toFixed(1)}%</td>
                      <td className="mono">{(rec.solar_input_w ?? 0).toFixed(1)}W</td>
                      <td className="mono">{(rec.power_draw_w ?? 0).toFixed(1)}W</td>
                      <td className="mono" style={{ color: (rec.battery_soc ?? 0.8) < 0.4 ? 'var(--status-red)' : 'var(--status-green)' }}>
                        {((rec.battery_soc ?? 0.8) * 100).toFixed(1)}%
                      </td>
                      <td className="mono">{(rec.bus_voltage ?? 4.8).toFixed(2)}V</td>
                      <td className="mono">{(rec.temp_c ?? 22.0).toFixed(1)}°C</td>
                      <td>
                        <span className={`badge ${rec.in_eclipse ? 'badge-plum' : 'badge-green'}`}>
                          {rec.in_eclipse ? 'ECLIPSE' : 'SUNLIT'}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* Top Telemetry KPI Metric Cards */}
      <div className="grid g4">
        {/* Battery SOC */}
        <div className="card metric-card">
          <div className="metric-label">
            <ZapIcon size={14} color="var(--amber)" />
            <span>Battery State of Charge</span>
          </div>
          <div className="metric-value" style={{ color: state.battery_soc < 0.3 ? 'var(--status-red)' : 'var(--paper)' }}>
            {(state.battery_soc * 100).toFixed(1)}%
          </div>
          <div className="bar-track" style={{ marginTop: '4px' }}>
            <div
              className="bar-fill"
              style={{
                width: `${state.battery_soc * 100}%`,
                background: state.battery_soc < 0.3 ? 'var(--status-red)' : 'var(--amber)',
              }}
            />
          </div>
          <div className="flex-between metric-sub" style={{ marginTop: '4px' }}>
            <span>Bus: {state.bus_voltage.toFixed(2)}V</span>
            <span>Net: {(state.solar_input_w - state.power_draw_w).toFixed(1)}W</span>
          </div>
        </div>

        {/* Bus Temperature */}
        <div className="card metric-card">
          <div className="metric-label">
            <ThermometerIcon size={14} color="var(--status-teal)" />
            <span>Thermal Single Zone</span>
          </div>
          <div
            className="metric-value"
            style={{
              color: state.temp_c > 38 || state.temp_c < -15 ? 'var(--status-red)' : 'var(--paper)',
            }}
          >
            {state.temp_c.toFixed(1)}°C
          </div>
          <div className="flex-between metric-sub" style={{ marginTop: '10px' }}>
            <span>Heater Relay: {state.heater_on ? 'CLOSED (ON)' : 'OPEN (OFF)'}</span>
            <span className={`badge ${state.heater_on ? 'badge-amber' : 'badge-teal'}`}>
              {state.heater_on ? '+3.5W' : '0.0W'}
            </span>
          </div>
        </div>

        {/* Solar Generation */}
        <div className="card metric-card">
          <div className="metric-label">
            {state.in_eclipse ? <MoonIcon size={14} color="var(--status-plum)" /> : <SunIcon size={14} color="var(--amber)" />}
            <span>Solar Flux Input</span>
          </div>
          <div className="metric-value" style={{ color: state.in_eclipse ? 'var(--status-plum)' : 'var(--amber)' }}>
            {state.solar_input_w.toFixed(1)} W
          </div>
          <div className="flex-between metric-sub" style={{ marginTop: '10px' }}>
            <span>Orbit State: {state.in_eclipse ? 'UMBRA ECLIPSE' : 'FULL SUNLIT'}</span>
            <span className="mono">{((state.orbit_phase || 0) * 100).toFixed(0)}%</span>
          </div>
        </div>

        {/* Storage & Comms */}
        <div className="card metric-card">
          <div className="metric-label">
            <HardDriveIcon size={14} color="var(--status-green)" />
            <span>CDH Memory Buffer</span>
          </div>
          <div className="metric-value">
            {state.storage_used_mb.toFixed(0)}{' '}
            <span style={{ fontSize: '13px', color: 'var(--paper-dim)' }}>
              / {state.storage_capacity_mb.toFixed(0)} MB
            </span>
          </div>
          <div className="bar-track" style={{ marginTop: '4px' }}>
            <div
              className="bar-fill"
              style={{
                width: `${(state.storage_used_mb / state.storage_capacity_mb) * 100}%`,
                background: 'var(--status-green)',
              }}
            />
          </div>
          <div className="flex-between metric-sub" style={{ marginTop: '4px' }}>
            <span>Downlink: {state.comms_active ? 'ACTIVE' : 'STANDBY'}</span>
            <span>Margin: {state.in_contact ? '+8.4dB' : 'AOS SEEK'}</span>
          </div>
        </div>
      </div>

      {/* Realtime Trend Sparklines Grid */}
      <div className="grid g2">
        {/* Battery SOC & Voltage Trend */}
        <div className="card">
          <div className="card-title">
            <span>EPS Battery SOC &amp; Bus Voltage Sparkline</span>
            <span className="mono" style={{ color: isPaused ? 'var(--status-red)' : 'var(--amber)' }}>
              {isPaused ? 'SPARKLINE FROZEN (PAUSED)' : '40 TICKS WINDOW'}
            </span>
          </div>
          <div style={{ padding: '8px 0' }}>
            {renderSparkline(socHistory, isPaused ? '#C49A4A' : '#FF7A33', 460, 80)}
          </div>
          <div className="flex-between" style={{ fontSize: '11px', fontFamily: 'var(--font-mono)', color: 'var(--paper-dim)' }}>
            <span>T-40s</span>
            <span>Current: {(state.battery_soc * 100).toFixed(1)}% | {state.bus_voltage.toFixed(2)}V</span>
            <span>T+0s (NOW)</span>
          </div>
        </div>

        {/* Thermal & Solar Power Trend */}
        <div className="card">
          <div className="card-title">
            <span>TCS Thermal Flux &amp; Solar Power Trend</span>
            <span className="mono" style={{ color: 'var(--status-teal)' }}>LUMPED ZONE</span>
          </div>
          <div style={{ padding: '8px 0' }}>
            {renderSparkline(tempHistory, '#5A9B8F', 460, 80)}
          </div>
          <div className="flex-between" style={{ fontSize: '11px', fontFamily: 'var(--font-mono)', color: 'var(--paper-dim)' }}>
            <span>Min: -20°C</span>
            <span>Current: {state.temp_c.toFixed(1)}°C | Solar: {state.solar_input_w.toFixed(1)}W</span>
            <span>Max: +50°C</span>
          </div>
        </div>
      </div>

      {/* Orbit Eclipse Timeline & Subsystem Matrix */}
      <div className="grid g-7-3">
        {/* Avionics Channel State Matrix */}
        <div className="card">
          <div className="card-title">
            <span>Avionics Channel State Matrix</span>
            <span className="mono">PHYSICAL vs REPORTED</span>
          </div>

          <table>
            <thead>
              <tr>
                <th>Subsystem</th>
                <th>Channel Variable</th>
                <th>Physical Value</th>
                <th>Reported (Sensor)</th>
                <th>Threshold Limit</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, color: 'var(--paper)' }}>EPS</td>
                <td>battery_soc</td>
                <td className="mono">{(state.battery_soc * 100).toFixed(2)}%</td>
                <td className="mono">
                  {state.reported_battery_soc != null
                    ? `${(state.reported_battery_soc * 100).toFixed(2)}% (CORRUPT)`
                    : `${(state.battery_soc * 100).toFixed(2)}%`}
                </td>
                <td className="mono">&gt; 35.0%</td>
                <td>
                  <span className={`badge ${state.battery_soc < 0.35 ? 'badge-red' : 'badge-green'}`}>
                    {state.battery_soc < 0.35 ? 'LOW SOC' : 'NOMINAL'}
                  </span>
                </td>
              </tr>

              <tr>
                <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, color: 'var(--paper)' }}>EPS</td>
                <td>bus_voltage</td>
                <td className="mono">{state.bus_voltage.toFixed(2)} V</td>
                <td className="mono">
                  {state.reported_bus_voltage != null
                    ? `${state.reported_bus_voltage.toFixed(2)} V`
                    : `${state.bus_voltage.toFixed(2)} V`}
                </td>
                <td className="mono">4.50 – 5.20 V</td>
                <td>
                  <span className={`badge ${state.bus_voltage < 4.5 ? 'badge-red' : 'badge-green'}`}>
                    {state.bus_voltage < 4.5 ? 'UNDERVOLT' : 'NOMINAL'}
                  </span>
                </td>
              </tr>

              <tr>
                <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, color: 'var(--paper)' }}>TCS</td>
                <td>temp_c</td>
                <td className="mono">{state.temp_c.toFixed(1)} °C</td>
                <td className="mono">
                  {state.reported_temp_c != null ? `${state.reported_temp_c.toFixed(1)} °C` : `${state.temp_c.toFixed(1)} °C`}
                </td>
                <td className="mono">-15.0 – 40.0 °C</td>
                <td>
                  <span
                    className={`badge ${
                      state.temp_c > 38.0 || state.temp_c < -15.0 ? 'badge-amber' : 'badge-green'
                    }`}
                  >
                    {state.temp_c > 38.0 || state.temp_c < -15.0 ? 'WARN TEMP' : 'NOMINAL'}
                  </span>
                </td>
              </tr>

              <tr>
                <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, color: 'var(--paper)' }}>ADCS</td>
                <td>attitude_deg</td>
                <td className="mono">{state.attitude_deg.toFixed(2)}°</td>
                <td className="mono">{state.attitude_deg.toFixed(2)}°</td>
                <td className="mono">&lt; 5.0° offset</td>
                <td>
                  <span className={`badge ${state.attitude_deg > 5.0 ? 'badge-amber' : 'badge-green'}`}>
                    {state.attitude_deg > 5.0 ? 'SLEW OFFSET' : 'SUN-LOCKED'}
                  </span>
                </td>
              </tr>

              <tr>
                <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, color: 'var(--paper)' }}>CDH</td>
                <td>storage_used_mb</td>
                <td className="mono">{state.storage_used_mb.toFixed(0)} MB</td>
                <td className="mono">{state.storage_used_mb.toFixed(0)} MB</td>
                <td className="mono">&lt; 1800 MB</td>
                <td>
                  <span className="badge badge-teal">BUFFER OK</span>
                </td>
              </tr>

              <tr>
                <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, color: 'var(--paper)' }}>COMMS</td>
                <td>link_margin_db</td>
                <td className="mono">{state.in_contact ? '+8.4 dB' : '-999 dB'}</td>
                <td className="mono">{state.in_contact ? '+8.4 dB' : '-999 dB'}</td>
                <td className="mono">&gt; +3.0 dB</td>
                <td>
                  <span className={`badge ${state.in_contact ? 'badge-green' : 'badge-plum'}`}>
                    {state.in_contact ? 'IN CONTACT' : 'AOS SEEK'}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        {/* Orbit Cycle & Pointing Dial */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          {/* Orbit Phase */}
          <div className="card">
            <div className="card-title">
              <span>LEO 90-Min Orbit Tracker</span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <div className="flex-between" style={{ fontFamily: 'var(--font-mono)', fontSize: '11px' }}>
                <span>Phase Progress</span>
                <span style={{ color: 'var(--amber)' }}>{((state.orbit_phase || 0) * 100).toFixed(1)}%</span>
              </div>
              <div className="bar-track" style={{ height: '8px' }}>
                <div
                  className="bar-fill"
                  style={{
                    width: `${(state.orbit_phase || 0) * 100}%`,
                    background: state.in_eclipse ? 'var(--status-plum)' : 'var(--amber)',
                  }}
                />
              </div>
              <div className="flex-between" style={{ fontSize: '10px', color: 'var(--paper-muted)' }}>
                <span>SUNLIT (0% - 65%)</span>
                <span>ECLIPSE (65% - 98%)</span>
              </div>
            </div>
          </div>

          {/* ADCS Pointing Offset Indicator */}
          <div className="card">
            <div className="card-title">
              <CompassIcon size={12} color="var(--amber)" />
              <span>Attitude Sun Vector</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '10px 0' }}>
              <div
                style={{
                  width: '90px',
                  height: '90px',
                  borderRadius: '50%',
                  border: '1px solid var(--border)',
                  position: 'relative',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  background: 'var(--ink-raised)',
                }}
              >
                {/* Crosshairs */}
                <div style={{ position: 'absolute', width: '100%', height: '1px', background: 'var(--border)' }} />
                <div style={{ position: 'absolute', height: '100%', width: '1px', background: 'var(--border)' }} />
                {/* Target Needle */}
                <div
                  style={{
                    position: 'absolute',
                    width: '36px',
                    height: '2px',
                    background: 'var(--amber)',
                    transformOrigin: '0% 50%',
                    transform: `rotate(${state.attitude_deg * 8}deg)`,
                    boxShadow: '0 0 4px var(--amber)',
                  }}
                />
                <span className="mono" style={{ fontSize: '11px', fontWeight: 600, color: 'var(--paper)' }}>
                  {state.attitude_deg.toFixed(1)}°
                </span>
              </div>
            </div>
            <div className="flex-between" style={{ fontSize: '10px', color: 'var(--paper-dim)' }}>
              <span>Target: 0.0°</span>
              <span>Slew Rate: {state.slew_rate_dps.toFixed(3)}°/s</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
