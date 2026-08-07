"""
Aegis MOS — Authority Gate (F6).

Implements the propose → review → verify → approve pipeline.
No command marked "irreversible" can skip review + verification.

Self-approval (same operator proposes and approves) is flagged
but not blocked in v1.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from authority.signer import CommandSigner

logger = logging.getLogger("aegis.authority")


class CommandRecord:
    """In-memory command record (mirrors DB Command model)."""

    def __init__(
        self,
        command_type: str,
        payload: dict,
        proposed_by: str,
        is_irreversible: bool = False,
    ):
        self.id = str(uuid.uuid4())
        self.command_type = command_type
        self.payload = payload
        self.is_irreversible = is_irreversible
        self.status = "proposed"
        self.proposed_by = proposed_by
        self.reviewed_by: str | None = None
        self.verified_by: str | None = None
        self.approved_by: str | None = None
        self.self_approval = False
        self.created_at = datetime.now(timezone.utc)
        self.reviewed_at: datetime | None = None
        self.verified_at: datetime | None = None
        self.approved_at: datetime | None = None
        self.rejected_at: datetime | None = None
        self.rejection_reason: str | None = None
        self.ledger_entry: dict | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "command_type": self.command_type,
            "payload": self.payload,
            "is_irreversible": self.is_irreversible,
            "status": self.status,
            "proposed_by": self.proposed_by,
            "reviewed_by": self.reviewed_by,
            "verified_by": self.verified_by,
            "approved_by": self.approved_by,
            "self_approval": self.self_approval,
            "created_at": self.created_at.isoformat(),
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "verified_at": self.verified_at.isoformat() if self.verified_at else None,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "rejected_at": self.rejected_at.isoformat() if self.rejected_at else None,
            "rejection_reason": self.rejection_reason,
            "ledger_entry": self.ledger_entry,
        }


class AuthorityGate:
    """
    Command authority pipeline.

    Enforces:
      1. No irreversible command can be auto-approved
      2. Every approval produces an HMAC-sealed audit ledger entry
      3. Self-approval is flagged (same person proposes + approves)
    """

    def __init__(self, signer: CommandSigner | None = None):
        self.signer = signer or CommandSigner()
        self._commands: dict[str, CommandRecord] = {}
        self._ledger: list[dict] = []

    @property
    def pending_commands(self) -> list[CommandRecord]:
        return [c for c in self._commands.values() if c.status in ("proposed", "reviewed", "verified")]

    @property
    def all_commands(self) -> list[CommandRecord]:
        return list(self._commands.values())

    @property
    def ledger(self) -> list[dict]:
        return list(self._ledger)

    def propose_command(
        self,
        command_type: str,
        payload: dict,
        proposed_by: str,
        is_irreversible: bool = False,
    ) -> CommandRecord:
        """Create a new command proposal."""
        cmd = CommandRecord(
            command_type=command_type,
            payload=payload,
            proposed_by=proposed_by,
            is_irreversible=is_irreversible,
        )
        self._commands[cmd.id] = cmd

        logger.info(
            "Command proposed: %s (%s) by %s [irreversible=%s]",
            cmd.id[:8], command_type, proposed_by, is_irreversible,
        )
        return cmd

    def review_command(
        self,
        command_id: str,
        reviewed_by: str,
    ) -> CommandRecord:
        """Mark a command as reviewed."""
        cmd = self._get_command(command_id)
        if cmd.status != "proposed":
            raise ValueError(f"Command {command_id} is not in 'proposed' state (current: {cmd.status})")

        cmd.status = "reviewed"
        cmd.reviewed_by = reviewed_by
        cmd.reviewed_at = datetime.now(timezone.utc)

        logger.info("Command %s reviewed by %s", command_id[:8], reviewed_by)
        return cmd

    def verify_command(
        self,
        command_id: str,
        verified_by: str,
    ) -> CommandRecord:
        """Mark a command as verified."""
        cmd = self._get_command(command_id)
        if cmd.status != "reviewed":
            raise ValueError(f"Command {command_id} is not in 'reviewed' state (current: {cmd.status})")

        cmd.status = "verified"
        cmd.verified_by = verified_by
        cmd.verified_at = datetime.now(timezone.utc)

        logger.info("Command %s verified by %s", command_id[:8], verified_by)
        return cmd

    def approve_command(
        self,
        command_id: str,
        approved_by: str,
    ) -> tuple[CommandRecord, dict]:
        """
        Approve a command, seal with HMAC, and write audit ledger.

        For irreversible commands: MUST have passed review + verify.
        Returns the (command, ledger_entry) tuple.
        """
        cmd = self._get_command(command_id)

        # Enforcement: irreversible commands must pass review + verify
        if cmd.is_irreversible and cmd.status != "verified":
            raise ValueError(
                f"Irreversible command {command_id} cannot be approved "
                f"without review + verification (current status: {cmd.status})"
            )

        # Non-irreversible commands can be approved from any pre-approved state
        if not cmd.is_irreversible and cmd.status not in ("proposed", "reviewed", "verified"):
            raise ValueError(f"Command {command_id} cannot be approved (current: {cmd.status})")

        # Check for self-approval
        cmd.self_approval = (cmd.proposed_by == approved_by)
        if cmd.self_approval:
            logger.warning(
                "SELF-APPROVAL FLAGGED: %s proposed and approved by '%s'",
                command_id[:8], approved_by,
            )

        cmd.status = "approved"
        cmd.approved_by = approved_by
        cmd.approved_at = datetime.now(timezone.utc)

        # Seal with HMAC
        payload_json = json.dumps(cmd.payload, sort_keys=True)
        timestamp = cmd.approved_at.isoformat()
        signature = self.signer.seal(payload_json, approved_by, timestamp)

        # Create audit ledger entry
        ledger_entry = {
            "entry_id": str(uuid.uuid4()),
            "command_id": cmd.id,
            "payload_json": payload_json,
            "approver_id": approved_by,
            "action": "approve",
            "timestamp": timestamp,
            "signature": signature,
            "key_version": self.signer.key_version,
            "self_approval": cmd.self_approval,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        self._ledger.append(ledger_entry)
        cmd.ledger_entry = ledger_entry

        logger.info(
            "Command %s APPROVED by %s (sig=%s...%s%s)",
            command_id[:8],
            approved_by,
            signature[:8],
            signature[-8:],
            " [SELF-APPROVAL]" if cmd.self_approval else "",
        )

        return cmd, ledger_entry

    def reject_command(
        self,
        command_id: str,
        rejected_by: str,
        reason: str = "",
    ) -> CommandRecord:
        """Reject a command with a reason."""
        cmd = self._get_command(command_id)
        cmd.status = "rejected"
        cmd.rejected_at = datetime.now(timezone.utc)
        cmd.rejection_reason = reason

        # Log rejection in ledger too
        payload_json = json.dumps(cmd.payload, sort_keys=True)
        timestamp = datetime.now(timezone.utc).isoformat()
        signature = self.signer.seal(payload_json, rejected_by, timestamp)

        ledger_entry = {
            "entry_id": str(uuid.uuid4()),
            "command_id": cmd.id,
            "payload_json": payload_json,
            "approver_id": rejected_by,
            "action": "reject",
            "timestamp": timestamp,
            "signature": signature,
            "key_version": self.signer.key_version,
            "self_approval": False,
            "rejection_reason": reason,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._ledger.append(ledger_entry)

        logger.info("Command %s REJECTED by %s: %s", command_id[:8], rejected_by, reason)
        return cmd

    def verify_signature(self, command_id: str) -> dict:
        """Re-verify a command's HMAC signature from the ledger."""
        cmd = self._get_command(command_id)

        # Find the approval ledger entry
        approval_entries = [
            e for e in self._ledger
            if e["command_id"] == command_id and e["action"] == "approve"
        ]

        if not approval_entries:
            return {
                "command_id": command_id,
                "verified": False,
                "reason": "No approval ledger entry found",
            }

        entry = approval_entries[-1]  # Latest approval
        is_valid = self.signer.verify(
            entry["payload_json"],
            entry["approver_id"],
            entry["timestamp"],
            entry["signature"],
        )

        return {
            "command_id": command_id,
            "verified": is_valid,
            "entry_id": entry["entry_id"],
            "approver_id": entry["approver_id"],
            "timestamp": entry["timestamp"],
            "signature_prefix": entry["signature"][:16] + "...",
        }

    def export_ledger(self) -> list[dict]:
        """Export the full audit ledger with verification status."""
        results = []
        for entry in self._ledger:
            is_valid = self.signer.verify(
                entry["payload_json"],
                entry["approver_id"],
                entry["timestamp"],
                entry["signature"],
            )
            results.append({
                **entry,
                "signature_valid": is_valid,
            })
        return results

    def _get_command(self, command_id: str) -> CommandRecord:
        """Retrieve a command by ID or raise ValueError."""
        cmd = self._commands.get(command_id)
        if cmd is None:
            raise ValueError(f"Command not found: {command_id}")
        return cmd
