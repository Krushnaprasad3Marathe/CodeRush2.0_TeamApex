"""
Aegis MOS — HMAC Command Signing (F6).

Produces HMAC-SHA256 signatures over command payloads, approver
identities, and timestamps. This is the cryptographic foundation
for the tamper-evident audit ledger.

The signature covers: payload_json | approver_id | timestamp
Any modification to any of these fields after signing will cause
verification to fail.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os

logger = logging.getLogger("aegis.signer")


class CommandSigner:
    """
    HMAC-SHA256 command signing and verification.

    The signing key is sourced from the HMAC_SECRET_KEY environment
    variable. In production this must be a strong, random 256-bit key.
    """

    def __init__(self, secret_key: bytes | None = None):
        if secret_key is None:
            key_str = os.getenv(
                "HMAC_SECRET_KEY", "dev-secret-key-change-in-production"
            )
            self._key = key_str.encode("utf-8")
        else:
            self._key = secret_key

        self._key_version = 1

    @property
    def key_version(self) -> int:
        """Current signing key version (for key rotation tracking)."""
        return self._key_version

    def seal(
        self,
        payload_json: str,
        approver_id: str,
        timestamp: str,
    ) -> str:
        """
        Produce an HMAC-SHA256 signature.

        The message is: payload_json|approver_id|timestamp
        Returns the hex-encoded signature string.
        """
        message = f"{payload_json}|{approver_id}|{timestamp}"
        signature = hmac.new(
            self._key,
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        logger.debug(
            "Sealed command: approver=%s, sig=%s...%s",
            approver_id,
            signature[:8],
            signature[-8:],
        )
        return signature

    def verify(
        self,
        payload_json: str,
        approver_id: str,
        timestamp: str,
        signature: str,
    ) -> bool:
        """
        Verify an HMAC-SHA256 signature.

        Re-computes the signature and compares using constant-time
        comparison to prevent timing attacks.
        """
        expected = self.seal(payload_json, approver_id, timestamp)
        is_valid = hmac.compare_digest(expected, signature)

        if not is_valid:
            logger.warning(
                "SIGNATURE VERIFICATION FAILED: command from %s",
                approver_id,
            )

        return is_valid
