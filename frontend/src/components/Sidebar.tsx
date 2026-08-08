import React from 'react';
import {
  ActivityIcon,
  ZapIcon,
  AlertTriangleIcon,
  CalendarIcon,
  ShieldCheckIcon,
} from './icons';
import type { SpacecraftState } from '../types';

interface SidebarProps {
  currentView: string;
  onSelectView: (view: string) => void;
  state: SpacecraftState;
}

export const Sidebar: React.FC<SidebarProps> = ({ currentView, onSelectView, state }) => {
  const activeAlerts = (state.active_anomalies || []).filter((a) => !a.acknowledged).length;
  const activeFaults = (state.active_faults || []).filter((f) => !f.cleared).length;

  const navItems = [
    {
      id: 'telemetry',
      label: 'Digital Twin Stream',
      icon: <ActivityIcon size={16} />,
      badge: `${(state.bus_voltage || 4.85).toFixed(2)}V`,
      badgeClass: state.bus_voltage < 4.5 ? 'badge-red' : 'badge-green',
    },
    {
      id: 'sandbox',
      label: 'Fault Sandbox',
      icon: <ZapIcon size={16} />,
      badge: activeFaults > 0 ? `${activeFaults} ACTIVE` : 'READY',
      badgeClass: activeFaults > 0 ? 'badge-amber' : 'badge-teal',
    },
    {
      id: 'anomalies',
      label: 'AI Anomaly Detector',
      icon: <AlertTriangleIcon size={16} />,
      badge: activeAlerts > 0 ? `${activeAlerts} ALERTS` : 'NOMINAL',
      badgeClass: activeAlerts > 0 ? 'badge-red' : 'badge-green',
    },
    {
      id: 'planner',
      label: 'Mission Planner',
      icon: <CalendarIcon size={16} />,
      badge: `${(state.scheduled_activities || []).length} ACT`,
      badgeClass: 'badge-teal',
    },
    {
      id: 'authority',
      label: 'Command Authority',
      icon: <ShieldCheckIcon size={16} />,
      badge: '4-EYE SEAL',
      badgeClass: 'badge-plum',
    },
  ];

  return (
    <aside className="sidebar">
      <div style={{ padding: '4px 8px 10px', borderBottom: '1px solid var(--border)' }}>
        <div className="label-mono" style={{ fontSize: '9px', marginBottom: '4px' }}>
          CONTROL CHANNELS
        </div>
      </div>

      <nav style={{ display: 'flex', flexDirection: 'column', gap: '2px', marginTop: '6px' }}>
        {navItems.map((item) => {
          const isActive = currentView === item.id;
          return (
            <button
              key={item.id}
              type="button"
              className={`nav-item ${isActive ? 'active' : ''}`}
              onClick={() => onSelectView(item.id)}
              style={{
                width: '100%',
                textAlign: 'left',
                border: 'none',
                background: isActive ? 'var(--amber-dim)' : 'transparent',
                borderLeft: isActive ? '3px solid var(--amber)' : '3px solid transparent',
              }}
            >
              {item.icon}
              <span style={{ flex: 1 }}>{item.label}</span>
              <span className={`badge ${item.badgeClass}`} style={{ fontSize: '9px', padding: '1px 5px' }}>
                {item.badge}
              </span>
            </button>
          );
        })}
      </nav>

      {/* Avionics Bus Matrix Summary */}
      <div style={{ marginTop: 'auto', paddingTop: '16px', borderTop: '1px solid var(--border)' }}>
        <div className="label-mono" style={{ fontSize: '9px', marginBottom: '8px', padding: '0 8px' }}>
          AVIONICS BUS MATRIX
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '5px', padding: '0 8px' }}>
          <div className="flex-between" style={{ fontSize: '11px', fontFamily: 'var(--font-mono)' }}>
            <span style={{ color: 'var(--paper-dim)' }}>EPS (Power)</span>
            <span style={{ color: state.battery_soc < 0.3 ? 'var(--status-red)' : 'var(--status-green)' }}>
              {((state.battery_soc || 0.85) * 100).toFixed(0)}%
            </span>
          </div>

          <div className="flex-between" style={{ fontSize: '11px', fontFamily: 'var(--font-mono)' }}>
            <span style={{ color: 'var(--paper-dim)' }}>TCS (Thermal)</span>
            <span style={{ color: state.temp_c > 38 || state.temp_c < -15 ? 'var(--status-red)' : 'var(--status-green)' }}>
              {(state.temp_c || 22.0).toFixed(1)}°C
            </span>
          </div>

          <div className="flex-between" style={{ fontSize: '11px', fontFamily: 'var(--font-mono)' }}>
            <span style={{ color: 'var(--paper-dim)' }}>ADCS (Attitude)</span>
            <span style={{ color: 'var(--status-green)' }}>
              {(state.attitude_deg || 0.0).toFixed(1)}°
            </span>
          </div>

          <div className="flex-between" style={{ fontSize: '11px', fontFamily: 'var(--font-mono)' }}>
            <span style={{ color: 'var(--paper-dim)' }}>CDH (Storage)</span>
            <span style={{ color: 'var(--status-teal)' }}>
              {((state.storage_used_mb || 400) / (state.storage_capacity_mb || 2048) * 100).toFixed(0)}%
            </span>
          </div>

          <div className="flex-between" style={{ fontSize: '11px', fontFamily: 'var(--font-mono)' }}>
            <span style={{ color: 'var(--paper-dim)' }}>COMMS (Link)</span>
            <span style={{ color: state.in_contact ? 'var(--status-green)' : 'var(--paper-muted)' }}>
              {state.in_contact ? '+8.4 dB' : 'AOS SEEK'}
            </span>
          </div>
        </div>
      </div>
    </aside>
  );
};
