import { useState, useEffect } from 'react';
import { Navbar } from './components/Navbar';
import { Sidebar } from './components/Sidebar';
import { TelemetryView } from './components/TelemetryView';
import { FaultSandboxView } from './components/FaultSandboxView';
import { AnomalyAIView } from './components/AnomalyAIView';
import { MissionPlannerView } from './components/MissionPlannerView';
import { CommandAuthorityView } from './components/CommandAuthorityView';
import type { SpacecraftState } from './types';
import { aegisApi } from './services/api';
import './App.css';

export function App() {
  const [currentView, setCurrentView] = useState<string>('telemetry');
  const [backendConnected, setBackendConnected] = useState<boolean>(false);
  const [isPaused, setIsPaused] = useState<boolean>(false);
  const [state, setState] = useState<SpacecraftState>({
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
    active_anomalies: [],
    suspect_streams: [],
    active_faults: [],
    sandbox_mode: false,
  });

  useEffect(() => {
    const unsubTelemetry = aegisApi.onTelemetry((s) => {
      setState({ ...s });
    });

    const unsubConn = aegisApi.onConnectionChange((connected) => {
      setBackendConnected(connected);
    });

    const unsubPause = aegisApi.onPauseChange((paused) => {
      setIsPaused(paused);
    });

    return () => {
      unsubTelemetry();
      unsubConn();
      unsubPause();
    };
  }, []);

  const handleTogglePause = async () => {
    await aegisApi.togglePause();
  };

  const handleRefresh = async () => {
    const snap = await aegisApi.fetchTelemetrySnapshot();
    setState({ ...snap });
  };

  return (
    <div className="app-layout">
      {/* Top Nav with Orbit-Mark, Hazard-Tape Seam, and Pause Status */}
      <Navbar
        state={state}
        backendConnected={backendConnected}
        activeView={currentView}
        isPaused={isPaused}
      />

      {/* Main Body */}
      <div className="body-wrap">
        {/* Avionics-style Sidebar */}
        <Sidebar currentView={currentView} onSelectView={setCurrentView} state={state} />

        {/* View Router Main Content Container */}
        <main className="main-content">
          {currentView === 'telemetry' && (
            <TelemetryView
              state={state}
              onRefresh={handleRefresh}
              isPaused={isPaused}
              onTogglePause={handleTogglePause}
            />
          )}
          {currentView === 'sandbox' && <FaultSandboxView state={state} onRefresh={handleRefresh} />}
          {currentView === 'anomalies' && <AnomalyAIView state={state} onRefresh={handleRefresh} />}
          {currentView === 'planner' && <MissionPlannerView state={state} onRefresh={handleRefresh} />}
          {currentView === 'authority' && <CommandAuthorityView state={state} onRefresh={handleRefresh} />}
        </main>
      </div>
    </div>
  );
}

export default App;
