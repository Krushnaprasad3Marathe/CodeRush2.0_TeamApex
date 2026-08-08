import React from 'react';
import type { SpacecraftState } from '../types';

interface FooterProps {
  state: SpacecraftState;
  backendConnected: boolean;
  isPaused?: boolean;
}

export const Footer: React.FC<FooterProps> = ({ state, backendConnected, isPaused }) => {
  const activeFaultCount = (state.active_faults || []).filter((f) => !f.cleared).length;
  const activeAlertCount = (state.active_anomalies || []).filter((a) => !a.acknowledged).length;

  return (
    <footer className="footer-bar">
      <div className="fb-section">
        <div className="fb-item">
          <span className="live-dot" style={{ background: isPaused ? 'var(--amber)' : 'var(--status-green)' }} />
          <span>
            VEHICLE LINK: {backendConnected ? (isPaused ? 'WS (PAUSED)' : 'ACTIVE (1.0 Hz WS)') : isPaused ? 'LOCAL (PAUSED)' : 'LOCAL SIMULATOR'}
          </span>
        </div>

        <div className="fb-item">
          <span className="rec-dot" style={{ animation: isPaused ? 'none' : 'blink 1.4s infinite' }} />
          <span>
            {isPaused ? 'TELEMETRY PAUSED AT T+' : 'TELEMETRY RECORDING: MONOTONIC T+'}
            {state.t || 0}
          </span>
        </div>

        <div className="fb-item">
          <span>SAMPLING RATE:</span>
          <span style={{ color: isPaused ? 'var(--amber)' : 'var(--paper)', fontWeight: 600 }}>
            {isPaused ? '0.000 Hz (PAUSED)' : '1.000 Hz'}
          </span>
        </div>
      </div>

      <div className="fb-section">
        <div className="fb-item">
          <span>ACTIVE FAULTS:</span>
          <span style={{ color: activeFaultCount > 0 ? 'var(--amber)' : 'var(--paper-dim)', fontWeight: 600 }}>
            {activeFaultCount}
          </span>
        </div>

        <div className="fb-item">
          <span>ANOMALY ALERTS:</span>
          <span style={{ color: activeAlertCount > 0 ? 'var(--status-red)' : 'var(--status-green)', fontWeight: 600 }}>
            {activeAlertCount}
          </span>
        </div>

        <div className="fb-item">
          <span>AUTHORITY GATE:</span>
          <span style={{ color: 'var(--status-plum)', fontWeight: 600 }}>HMAC-SHA256 SEALED</span>
        </div>

        <div className="fb-item">
          <span>SECURITY LEDGER:</span>
          <span style={{ color: 'var(--status-teal)', fontWeight: 600 }}>IMMUTABLE</span>
        </div>
      </div>
    </footer>
  );
};
