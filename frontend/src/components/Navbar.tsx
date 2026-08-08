import React from 'react';
import { OrbitMarkIcon, RadioIcon, AlertTriangleIcon, PauseIcon } from './icons';
import type { SpacecraftState } from '../types';

interface NavbarProps {
  state: SpacecraftState;
  backendConnected: boolean;
  activeView: string;
  isPaused?: boolean;
}

export const Navbar: React.FC<NavbarProps> = ({ state, backendConnected, activeView, isPaused }) => {
  const formatTime = (epochSeconds: number) => {
    const d = new Date(epochSeconds * 1000);
    return d.toISOString().replace('T', ' ').slice(0, 19) + ' UTC';
  };

  const getFlightMode = () => {
    if (state.active_anomalies && state.active_anomalies.length > 0) {
      const hasCritical = state.active_anomalies.some((a) => a.severity === 'critical');
      return hasCritical ? { label: 'CRITICAL FAULT', class: 'badge-red' } : { label: 'DEGRADED / CAUTION', class: 'badge-amber' };
    }
    if (state.in_eclipse) return { label: 'ECLIPSE PASS', class: 'badge-plum' };
    if (state.is_observing) return { label: 'PAYLOAD OPS', class: 'badge-teal' };
    return { label: 'NOMINAL SUNLIT', class: 'badge-green' };
  };

  const flightMode = getFlightMode();
  const activeAlertCount = state.active_anomalies?.filter((a) => !a.acknowledged).length || 0;

  return (
    <header className="topnav">
      {/* Left: Brand + Wordmark + Mission Indicators */}
      <div className="topnav-left">
        <div className="brand" style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <OrbitMarkIcon size={26} color="var(--amber)" strokeWidth={2.2} />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
            <span className="brand-wordmark" style={{ lineHeight: '1.2' }}>Space Aegis</span>
            <span className="brand-sub" style={{ lineHeight: '1.1', marginTop: '1px' }}>OPERATOR CONSOLE</span>
          </div>
        </div>

        {/* Mission Status Strip — separated with hairline vertical dividers */}
        <div className="mission-strip">
          <div className="mission-item">
            <span className="lbl">Vehicle</span>
            <span className="val" style={{ fontFamily: 'var(--font-mono)' }}>AEGIS-CS1</span>
          </div>

          <div className="mission-item">
            <span className="lbl">Sim Clock</span>
            <span className="val" style={{ fontFamily: 'var(--font-mono)', color: 'var(--amber)' }}>
              T+{(state.t || 0).toString().padStart(6, '0')}s
            </span>
          </div>

          <div className="mission-item">
            <span className="lbl">Flight Mode</span>
            <div>
              <span className={`badge ${flightMode.class}`}>
                <span className="badge-dot" />
                {flightMode.label}
              </span>
            </div>
          </div>

          <div className="mission-item">
            <span className="lbl">Orbit Phase</span>
            <span className="val" style={{ fontFamily: 'var(--font-mono)' }}>
              {((state.orbit_phase || 0) * 100).toFixed(1)}% {state.in_eclipse ? '(UMBRA)' : '(SUNLIT)'}
            </span>
          </div>

          <div className="mission-item">
            <span className="lbl">Active View</span>
            <span className="val" style={{ fontFamily: 'var(--font-mono)', color: 'var(--paper-dim)' }}>
              {activeView.toUpperCase()}
            </span>
          </div>
        </div>
      </div>

      {/* Right: Telemetry stream indicator, pause status, alert pill, clock */}
      <div className="topnav-right">
        {isPaused && (
          <span className="badge badge-amber" style={{ animation: 'pulse 1.4s infinite' }}>
            <PauseIcon size={12} color="var(--amber)" />
            SIM CLOCK PAUSED
          </span>
        )}

        {state.sandbox_mode && (
          <span className="badge badge-amber" style={{ animation: 'pulse 1.8s infinite' }}>
            <span className="badge-dot" />
            SANDBOX ACTIVE
          </span>
        )}

        {activeAlertCount > 0 && (
          <span className="badge badge-red">
            <AlertTriangleIcon size={12} color="var(--status-red)" />
            {activeAlertCount} UNACKED ALERT{activeAlertCount > 1 ? 'S' : ''}
          </span>
        )}

        {/* Backend / Stream Status */}
        <div
          className={`status-pill ${backendConnected ? 'badge-green' : 'badge-amber'}`}
          title={backendConnected ? 'Connected to FastAPI WebSocket' : 'Running internal Digital Twin engine'}
        >
          <RadioIcon size={12} color={backendConnected ? 'var(--status-green)' : 'var(--status-amber)'} />
          <span style={{ fontSize: '10px' }}>
            {backendConnected ? (isPaused ? 'STREAM: WS (PAUSED)' : 'STREAM: 1.0 Hz (WS)') : isPaused ? 'STREAM: LOCAL (PAUSED)' : 'STREAM: LOCAL TWIN'}
          </span>
        </div>

        {/* Wall Clock */}
        <div className="clock-display">
          <div className="time">{formatTime(state.timestamp || Date.now() / 1000)}</div>
          <div className="date">{isPaused ? 'CLOCK FROZEN' : 'SIM-LOCKED 1.00 Hz'}</div>
        </div>
      </div>
    </header>
  );
};
