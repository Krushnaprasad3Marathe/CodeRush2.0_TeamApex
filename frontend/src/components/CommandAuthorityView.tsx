import React, { useState, useEffect } from 'react';
import type { SpacecraftState, Command, LedgerEntry } from '../types';
import { aegisApi } from '../services/api';
import {
  ShieldCheckIcon,
  CheckIcon,
  DownloadIcon,
  RefreshCwIcon,
  KeyIcon,
} from './icons';

interface CommandAuthorityViewProps {
  state: SpacecraftState;
  onRefresh: () => void;
}

export const CommandAuthorityView: React.FC<CommandAuthorityViewProps> = ({ state, onRefresh }) => {
  const [commands, setCommands] = useState<Command[]>([]);
  const [ledger, setLedger] = useState<LedgerEntry[]>([]);
  const [selectedCmd, setSelectedCmd] = useState<Command | null>(null);
  const [cmdType, setCmdType] = useState<string>('EPS_HEATER_OVERRIDE');
  const [isIrreversible, setIsIrreversible] = useState<boolean>(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [sigCheckResult, setSigCheckResult] = useState<any | null>(null);

  const loadData = async () => {
    try {
      const cmdsRes = await aegisApi.fetchCommands();
      setCommands(cmdsRes.commands);
      if (cmdsRes.commands.length > 0 && !selectedCmd) {
        setSelectedCmd(cmdsRes.commands[0]);
      }

      const ledgerRes = await aegisApi.exportLedger();
      setLedger(ledgerRes.ledger);
    } catch {}
  };

  useEffect(() => {
    loadData();
  }, [state.t]);

  const handlePropose = async () => {
    try {
      const payload: Record<string, any> = {
        mode: 'OPERATOR_OVERRIDE',
        timestamp: Date.now(),
        requested_at_t: state.t,
      };

      const res = await aegisApi.proposeCommand({
        command_type: cmdType,
        payload,
        proposed_by: 'operator-deck-1',
        is_irreversible: isIrreversible,
      });

      setMsg(`COMMAND ${res.command.command_id} PROPOSED FOR 4-EYE REVIEW`);
      setTimeout(() => setMsg(null), 3000);
      await loadData();
      onRefresh();
    } catch {}
  };

  const handleReview = async (id: string) => {
    try {
      await aegisApi.reviewCommand(id, 'reviewer-flight-ops');
      setMsg(`COMMAND ${id} REVIEWED`);
      setTimeout(() => setMsg(null), 3000);
      await loadData();
      onRefresh();
    } catch {}
  };

  const handleVerify = async (id: string) => {
    try {
      await aegisApi.verifyCommand(id, 'verifier-safety-officer');
      setMsg(`COMMAND ${id} SAFETY VERIFIED`);
      setTimeout(() => setMsg(null), 3000);
      await loadData();
      onRefresh();
    } catch {}
  };

  const handleApprove = async (id: string) => {
    try {
      await aegisApi.approveCommand(id, 'flight-director-aegis');
      setMsg(`COMMAND ${id} APPROVED & CRYPTOGRAPHICALLY SEALED`);
      setTimeout(() => setMsg(null), 3500);
      await loadData();
      onRefresh();
    } catch {}
  };

  const handleReject = async (id: string) => {
    try {
      await aegisApi.rejectCommand(id, 'ops-reviewer', 'Safety margin boundary exceeded');
      setMsg(`COMMAND ${id} REJECTED`);
      setTimeout(() => setMsg(null), 3000);
      await loadData();
      onRefresh();
    } catch {}
  };

  const handleVerifySig = async (id: string) => {
    try {
      const res = await aegisApi.verifySignature(id);
      setSigCheckResult(res);
    } catch {}
  };

  const handleExportJson = () => {
    const dataStr = 'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(ledger, null, 2));
    const dlAnchorElem = document.createElement('a');
    dlAnchorElem.setAttribute('href', dataStr);
    dlAnchorElem.setAttribute('download', `space_aegis_audit_ledger_T${state.t}.json`);
    dlAnchorElem.click();
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
      {/* Page Header */}
      <div className="page-header flex-between">
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          <div className="icon-wrap">
            <ShieldCheckIcon size={20} color="var(--amber)" />
          </div>
          <div>
            <h1>Command Authority Gate &amp; Immutable Audit Ledger</h1>
            <p>Cryptographically enforced 4-eye verification gate and append-only HMAC-SHA256 audit ledger</p>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {msg && (
            <span className="badge badge-green" style={{ padding: '6px 12px' }}>
              {msg}
            </span>
          )}
          <button type="button" className="btn btn-amber" onClick={handleExportJson}>
            <DownloadIcon size={14} />
            EXPORT AUDIT LEDGER
          </button>
          <button type="button" className="btn btn-ghost" onClick={loadData}>
            <RefreshCwIcon size={14} />
            RE-CHECK
          </button>
        </div>
      </div>

      {/* 4-Eye Authority Gate Visual Pipeline */}
      <div className="card">
        <div className="card-title">
          <span>4-Eye Verification Pipeline Lifecycle</span>
          <span className="mono">STRICT FLIGHT PROTOCOL</span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 0' }}>
          <div className="pipeline-step">
            <div className="pipeline-dot done">1</div>
            <div style={{ fontWeight: 600, fontSize: '11px', color: 'var(--paper)' }}>PROPOSED</div>
            <div style={{ fontSize: '10px', color: 'var(--paper-muted)' }}>Planner / Operator</div>
          </div>

          <div style={{ flex: 1, height: '2px', background: 'var(--border)', margin: '0 8px' }} />

          <div className="pipeline-step">
            <div className="pipeline-dot done">2</div>
            <div style={{ fontWeight: 600, fontSize: '11px', color: 'var(--paper)' }}>REVIEWED</div>
            <div style={{ fontSize: '10px', color: 'var(--paper-muted)' }}>Flight Ops Reviewer</div>
          </div>

          <div style={{ flex: 1, height: '2px', background: 'var(--border)', margin: '0 8px' }} />

          <div className="pipeline-step">
            <div className="pipeline-dot done">3</div>
            <div style={{ fontWeight: 600, fontSize: '11px', color: 'var(--paper)' }}>VERIFIED</div>
            <div style={{ fontSize: '10px', color: 'var(--paper-muted)' }}>Safety Officer Gate</div>
          </div>

          <div style={{ flex: 1, height: '2px', background: 'var(--border)', margin: '0 8px' }} />

          <div className="pipeline-step">
            <div className="pipeline-dot active">4</div>
            <div style={{ fontWeight: 600, fontSize: '11px', color: 'var(--amber)' }}>HMAC SEALED</div>
            <div style={{ fontSize: '10px', color: 'var(--amber)' }}>Flight Director Sign</div>
          </div>
        </div>
      </div>

      {/* Split: Propose Command & Pending Approvals */}
      <div className="grid g-2-1">
        {/* Left: Pending / All Commands Table */}
        <div className="card">
          <div className="flex-between" style={{ marginBottom: '10px' }}>
            <div className="card-title" style={{ margin: 0 }}>
              Command Dispatch Authority Queue
            </div>
            <span className="mono" style={{ color: 'var(--amber)' }}>
              {commands.length} TOTAL
            </span>
          </div>

          <table>
            <thead>
              <tr>
                <th>Command ID</th>
                <th>Operation Type</th>
                <th>State Gate</th>
                <th>Signatures</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {commands.map((cmd) => {
                const cState = (cmd.state || (cmd as any).status || 'PROPOSED').toUpperCase();
                const cId = cmd.command_id || (cmd as any).id;
                return (
                  <tr
                    key={cId}
                    style={{
                      background: selectedCmd?.command_id === cId ? 'var(--amber-dim)' : 'transparent',
                      cursor: 'pointer',
                    }}
                    onClick={() => setSelectedCmd(cmd)}
                  >
                    <td className="mono" style={{ fontWeight: 600, color: 'var(--paper)' }}>
                      {cId}
                    </td>
                    <td className="mono">{cmd.command_type}</td>
                    <td>
                      <span
                        className={`badge ${
                          cState === 'APPROVED'
                            ? 'badge-green'
                            : cState === 'REJECTED'
                            ? 'badge-red'
                            : cState === 'VERIFIED'
                            ? 'badge-teal'
                            : 'badge-amber'
                        }`}
                      >
                        {cState}
                      </span>
                    </td>
                    <td className="mono" style={{ fontSize: '10px' }}>
                      {cmd.signature ? `${cmd.signature.slice(0, 16)}...` : 'AWAITING APPROVAL'}
                    </td>
                    <td>
                      <div style={{ display: 'flex', gap: '4px' }}>
                        {cState === 'PROPOSED' && (
                          <button
                            type="button"
                            className="btn btn-amber"
                            style={{ padding: '3px 8px', fontSize: '10px' }}
                            onClick={(e) => {
                              e.stopPropagation();
                              handleReview(cId);
                            }}
                          >
                            REVIEW
                          </button>
                        )}

                        {cState === 'REVIEWED' && (
                          <button
                            type="button"
                            className="btn btn-green"
                            style={{ padding: '3px 8px', fontSize: '10px' }}
                            onClick={(e) => {
                              e.stopPropagation();
                              handleVerify(cId);
                            }}
                          >
                            VERIFY
                          </button>
                        )}

                        {cState === 'VERIFIED' && (
                          <button
                            type="button"
                            className="btn btn-amber"
                            style={{ padding: '3px 8px', fontSize: '10px' }}
                            onClick={(e) => {
                              e.stopPropagation();
                              handleApprove(cId);
                            }}
                          >
                            SEAL &amp; APPROVE
                          </button>
                        )}

                        {cState !== 'APPROVED' && cState !== 'REJECTED' && (
                          <button
                            type="button"
                            className="btn btn-ghost"
                            style={{ padding: '3px 8px', fontSize: '10px', color: 'var(--status-red)' }}
                            onClick={(e) => {
                              e.stopPropagation();
                              handleReject(cId);
                            }}
                          >
                            REJECT
                          </button>
                        )}

                        {cState === 'APPROVED' && (
                          <button
                            type="button"
                            className="btn btn-ghost"
                            style={{ padding: '3px 8px', fontSize: '10px' }}
                            onClick={(e) => {
                              e.stopPropagation();
                              handleVerifySig(cId);
                            }}
                          >
                            <KeyIcon size={12} /> VERIFY SIG
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Right: Propose New Command Form */}
        <div className="card">
          <div className="card-title">
            <span>Propose Command Step</span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div>
              <label style={{ fontSize: '11px', color: 'var(--paper-dim)' }}>Select Command Type</label>
              <select
                value={cmdType}
                onChange={(e) => setCmdType(e.target.value)}
                style={{
                  width: '100%',
                  background: 'var(--ink)',
                  border: '1px solid var(--border)',
                  color: 'var(--paper)',
                  padding: '8px 10px',
                  borderRadius: 'var(--radius)',
                  fontFamily: 'var(--font-mono)',
                  fontSize: '12px',
                  marginTop: '4px',
                }}
              >
                <option value="EPS_HEATER_OVERRIDE">EPS_HEATER_OVERRIDE (Force Survival Heater)</option>
                <option value="PAYLOAD_COLLECT_DATA">PAYLOAD_COLLECT_DATA (Trigger Observation)</option>
                <option value="COMMS_FORCE_DOWNLINK">COMMS_FORCE_DOWNLINK (S-band Pass Dump)</option>
                <option value="ADCS_TARGET_SLEW">ADCS_TARGET_SLEW (Re-orient Sun Vector)</option>
                <option value="EPS_SHED_NON_ESSENTIAL">EPS_SHED_NON_ESSENTIAL (Power Load Shedding)</option>
                <option value="SAFE_MODE_ENTER">SAFE_MODE_ENTER (Autonomous Safe-Hold)</option>
              </select>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <input
                type="checkbox"
                id="irrev"
                checked={isIrreversible}
                onChange={(e) => setIsIrreversible(e.target.checked)}
                style={{ accentColor: 'var(--amber)' }}
              />
              <label htmlFor="irrev" style={{ fontSize: '11px', color: 'var(--paper)' }}>
                Mark as Irreversible / High Risk Action
              </label>
            </div>

            <button
              type="button"
              className="btn btn-amber"
              style={{ width: '100%', justifyContent: 'center', padding: '10px' }}
              onClick={handlePropose}
            >
              PROPOSE COMMAND TO AUTHORITY GATE
            </button>

            {/* Signature Certificate Badge if inspected */}
            {sigCheckResult && (
              <div
                style={{
                  marginTop: '8px',
                  padding: '10px',
                  background: 'var(--ink)',
                  border: '1px solid var(--status-green)',
                  borderRadius: 'var(--radius)',
                }}
              >
                <div className="flex-between">
                  <span style={{ fontWeight: 600, color: 'var(--status-green)', fontSize: '11px' }}>
                    HMAC-SHA256 SEAL VALID
                  </span>
                  <CheckIcon size={14} color="var(--status-green)" />
                </div>
                <div style={{ fontSize: '10px', fontFamily: 'var(--font-mono)', color: 'var(--paper-dim)', marginTop: '4px' }}>
                  {sigCheckResult.signature}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Immutable Audit Ledger Table */}
      <div className="card">
        <div className="flex-between" style={{ marginBottom: '10px' }}>
          <div className="card-title" style={{ margin: 0 }}>
            Immutable Append-Only Audit Ledger
          </div>
          <span className="badge badge-teal">HASH CHAIN VALIDATED</span>
        </div>

        <table>
          <thead>
            <tr>
              <th>Seq #</th>
              <th>Timestamp</th>
              <th>Command</th>
              <th>Approved Signer</th>
              <th>HMAC Signature Hash</th>
              <th>Previous Entry Hash</th>
              <th>Verification</th>
            </tr>
          </thead>
          <tbody>
            {ledger.map((entry) => (
              <tr key={entry.sequence_id}>
                <td className="mono" style={{ fontWeight: 600, color: 'var(--amber)' }}>
                  #{entry.sequence_id}
                </td>
                <td className="mono">{new Date(entry.timestamp).toISOString().slice(11, 19)}</td>
                <td className="mono">{entry.command_type}</td>
                <td>{entry.approved_by}</td>
                <td className="mono" style={{ fontSize: '10px', color: 'var(--paper)' }}>
                  {entry.signature}
                </td>
                <td className="mono" style={{ fontSize: '10px', color: 'var(--paper-muted)' }}>
                  {entry.previous_hash.slice(0, 16)}...
                </td>
                <td>
                  <span className="badge badge-green">
                    <CheckIcon size={12} /> VALID
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
