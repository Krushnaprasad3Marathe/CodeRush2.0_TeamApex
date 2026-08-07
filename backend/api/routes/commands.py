"""
Aegis MOS — Command authority API routes (F6).

Endpoints:
  POST /commands/propose       — Propose a procedure step/command
  POST /commands/{id}/review   — Review a command
  POST /commands/{id}/verify   — Verify a command
  POST /commands/{id}/approve  — Approve (triggers HMAC seal + ledger write)
  POST /commands/{id}/reject   — Reject with reason
  GET  /commands/{id}/verify-signature — Re-verify a sealed command's signature
  GET  /commands                — List all commands
  GET  /commands/pending        — List pending commands
  GET  /ledger/export           — Export the full audit ledger for a run
"""

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from authority.gate import AuthorityGate

router = APIRouter(tags=["commands"])

# Module-level authority gate instance
_gate: AuthorityGate | None = None


def _get_gate() -> AuthorityGate:
    global _gate
    if _gate is None:
        _gate = AuthorityGate()
    return _gate


class ProposeRequest(BaseModel):
    command_type: str = Field(description="Type of command")
    payload: dict = Field(description="Command payload")
    proposed_by: str = Field(default="operator-1")
    is_irreversible: bool = Field(default=False)


class ReviewRequest(BaseModel):
    reviewed_by: str = Field(default="reviewer-1")


class VerifyRequest(BaseModel):
    verified_by: str = Field(default="verifier-1")


class ApproveRequest(BaseModel):
    approved_by: str = Field(default="approver-1")


class RejectRequest(BaseModel):
    rejected_by: str = Field(default="reviewer-1")
    reason: str = Field(default="")


@router.post("/commands/propose")
async def propose_command(body: ProposeRequest):
    """Propose a new procedure step/command for review."""
    gate = _get_gate()
    cmd = gate.propose_command(
        command_type=body.command_type,
        payload=body.payload,
        proposed_by=body.proposed_by,
        is_irreversible=body.is_irreversible,
    )
    return {"status": "proposed", "command": cmd.to_dict()}


@router.post("/commands/{command_id}/review")
async def review_command(command_id: str, body: ReviewRequest):
    """Review a proposed command."""
    gate = _get_gate()
    try:
        cmd = gate.review_command(command_id, body.reviewed_by)
        return {"status": "reviewed", "command": cmd.to_dict()}
    except ValueError as e:
        return {"status": "error", "message": str(e)}


@router.post("/commands/{command_id}/verify")
async def verify_command(command_id: str, body: VerifyRequest):
    """Verify a reviewed command."""
    gate = _get_gate()
    try:
        cmd = gate.verify_command(command_id, body.verified_by)
        return {"status": "verified", "command": cmd.to_dict()}
    except ValueError as e:
        return {"status": "error", "message": str(e)}


@router.post("/commands/{command_id}/approve")
async def approve_command(command_id: str, body: ApproveRequest):
    """Approve a command, triggering HMAC seal + audit ledger write."""
    gate = _get_gate()
    try:
        cmd, ledger_entry = gate.approve_command(command_id, body.approved_by)
        return {
            "status": "approved",
            "command": cmd.to_dict(),
            "ledger_entry": ledger_entry,
        }
    except ValueError as e:
        return {"status": "error", "message": str(e)}


@router.post("/commands/{command_id}/reject")
async def reject_command(command_id: str, body: RejectRequest):
    """Reject a command with a reason."""
    gate = _get_gate()
    try:
        cmd = gate.reject_command(command_id, body.rejected_by, body.reason)
        return {"status": "rejected", "command": cmd.to_dict()}
    except ValueError as e:
        return {"status": "error", "message": str(e)}


@router.get("/commands/{command_id}/verify-signature")
async def verify_signature(command_id: str):
    """Re-verify a sealed command's HMAC signature."""
    gate = _get_gate()
    try:
        result = gate.verify_signature(command_id)
        return result
    except ValueError as e:
        return {"status": "error", "message": str(e)}


@router.get("/commands")
async def list_commands():
    """List all commands."""
    gate = _get_gate()
    return {
        "commands": [c.to_dict() for c in gate.all_commands],
        "total": len(gate.all_commands),
    }


@router.get("/commands/pending")
async def list_pending():
    """List pending commands awaiting action."""
    gate = _get_gate()
    return {
        "commands": [c.to_dict() for c in gate.pending_commands],
        "total": len(gate.pending_commands),
    }


@router.get("/ledger/export")
async def export_ledger():
    """Export the full audit ledger for a mission run."""
    gate = _get_gate()
    entries = gate.export_ledger()
    return {
        "ledger": entries,
        "total_entries": len(entries),
        "all_valid": all(e.get("signature_valid", False) for e in entries),
    }
