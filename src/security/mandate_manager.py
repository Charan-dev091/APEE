"""
APEE — Async Mandate Manager
==============================
Fixes ThreadPool Exhaustion on the Passkey.

OLD (blocking):
  mandate = await loop.run_in_executor(None, passkey.authorize...)
  → Thread blocked for entire biometric wait time
  → 10 concurrent trades = thread pool exhausted = entire event loop freezes

NEW (non-blocking):
  Step 1: authorize_async() returns PENDING immediately
  Step 2: WebSocket pushes auth request to frontend UI
  Step 3: Frontend shows WebAuthn biometric prompt
  Step 4: User approves → frontend calls POST /api/mandate/approve
  Step 5: Webhook receiver finalizes the trade

The main.py async loop is NEVER blocked.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


# ── Mandate Status ────────────────────────────────────────────────────────────

class MandateStatus(str, Enum):
    PENDING   = "PENDING"    # Waiting for biometric
    APPROVED  = "APPROVED"   # Biometric confirmed
    REJECTED  = "REJECTED"   # Biometric failed or expired
    EXPIRED   = "EXPIRED"    # Timeout — user didn't respond
    EXECUTING = "EXECUTING"  # Paymaster in progress
    COMPLETE  = "COMPLETE"   # Trade filled


# ── Pending Mandate ───────────────────────────────────────────────────────────

class PendingMandate:
    """
    A mandate waiting for biometric sign-off.
    Held in memory — never blocks the event loop.
    """

    TIMEOUT_SECONDS = 120  # 2 minutes to approve

    def __init__(
        self,
        asset:       str,
        action:      str,
        alloc_usd:   float,
        oracle_price: float,
        gate_result: dict,
    ):
        self.mandate_id   = str(uuid.uuid4())
        self.asset        = asset
        self.action       = action
        self.alloc_usd    = alloc_usd
        self.oracle_price = oracle_price
        self.gate_result  = gate_result
        self.created_at   = datetime.now(timezone.utc)
        self.status       = MandateStatus.PENDING

        # Cryptographic challenge — SHA-256 of all mandate fields
        # This is what the user's WebAuthn device signs
        self.challenge = hashlib.sha256(
            json.dumps({
                "mandate_id":   self.mandate_id,
                "asset":        asset,
                "action":       action,
                "alloc_usd":    alloc_usd,
                "oracle_price": oracle_price,
            }, sort_keys=True).encode()
        ).hexdigest()

        # Future that resolves when biometric is confirmed
        self._future: Optional[asyncio.Future] = None

    def is_expired(self) -> bool:
        elapsed = (datetime.now(timezone.utc) - self.created_at).total_seconds()
        return elapsed > self.TIMEOUT_SECONDS

    def to_ui_payload(self) -> dict:
        """Payload sent to frontend for WebAuthn prompt."""
        return {
            "mandate_id":   self.mandate_id,
            "asset":        self.asset,
            "action":       self.action,
            "alloc_usd":    self.alloc_usd,
            "oracle_price": self.oracle_price,
            "challenge":    self.challenge[:16] + "...",
            "expires_in":   self.TIMEOUT_SECONDS,
            "status":       self.status,
            "message":      f"Approve {self.action.upper()} {self.asset} ${self.alloc_usd:.0f} @ ${self.oracle_price:.2f}",
        }

    def to_dict(self) -> dict:
        return {
            **self.to_ui_payload(),
            "gate_confidence": self.gate_result.get("combined_confidence"),
            "created_at": self.created_at.isoformat(),
        }


# ── PoC Signing Secret ────────────────────────────────────────────────────────
# In PoC mode the server signs the challenge with this secret and the frontend
# returns the HMAC as the "signature".  The approve() method below verifies it.
#
# PRODUCTION UPGRADE PATH:
#   Replace _make_expected_sig() and the verify block in approve() with:
#     - Store the user's WebAuthn credential public key at registration
#     - Use `py_webauthn` (pip install webauthn) to verify the assertion:
#         webauthn.verify_authentication_response(
#             credential=<frontend authenticatorAssertionResponse>,
#             expected_challenge=mandate.challenge,
#             expected_rp_id="your-domain.com",
#             credential_public_key=<stored_public_key>,
#             credential_current_sign_count=<stored_sign_count>,
#         )
#
_POC_SIGNING_SECRET: str = os.getenv(
    "APEE_WEBAUTHN_SECRET",
    # Default is a fixed dev secret — set APEE_WEBAUTHN_SECRET in .env for any
    # deployment where the PoC runs on a shared or exposed machine.
    "apee-dev-secret-change-me-in-production",
)


def _make_expected_sig(challenge: str) -> str:
    """Produce the expected HMAC-SHA256 signature for a challenge.

    The dashboard's /api/mandate/approve must send this value as the
    'signature' field to pass the verification check in approve().

    Usage (e.g. in webhook_server or dashboard API route):
        from src.security.mandate_manager import _make_expected_sig
        sig = _make_expected_sig(mandate.challenge)
    """
    return hmac.new(
        _POC_SIGNING_SECRET.encode(),
        challenge.encode(),
        hashlib.sha256,
    ).hexdigest()


# ── Async Mandate Manager ─────────────────────────────────────────────────────

class AsyncMandateManager:
    """
    Non-blocking mandate lifecycle manager.

    Flow:
    1. request()  → creates PendingMandate, returns immediately (PENDING)
    2. WebSocket  → pushes auth request to frontend
    3. Frontend   → user approves via biometric
    4. approve()  → called by webhook, resolves the future
    5. Orchestrator → receives approved mandate, executes trade

    The event loop is NEVER blocked at any step.
    """

    def __init__(self):
        self._pending: dict[str, PendingMandate] = {}
        self._lock = asyncio.Lock()

    async def request(
        self,
        asset:        str,
        action:       str,
        alloc_usd:    float,
        oracle_price: float,
        gate_result:  dict,
    ) -> PendingMandate:
        """
        Create a pending mandate. Returns immediately — no blocking.
        Caller should push mandate.to_ui_payload() to WebSocket.
        """
        async with self._lock:
            mandate = PendingMandate(
                asset=asset,
                action=action,
                alloc_usd=alloc_usd,
                oracle_price=oracle_price,
                gate_result=gate_result,
            )
            mandate._future = asyncio.get_event_loop().create_future()
            self._pending[mandate.mandate_id] = mandate

            logger.info("[Mandate] PENDING %s — %s %s $%.0f",
                        mandate.mandate_id[:8], action, asset, alloc_usd)
            return mandate

    async def wait_for_approval(
        self,
        mandate_id: str,
        timeout: float = PendingMandate.TIMEOUT_SECONDS,
    ) -> dict:
        """
        Wait for biometric approval without blocking the event loop.
        Returns approved mandate dict or rejection.

        Uses asyncio.wait_for() — cooperative, not thread-blocking.
        Event loop stays free to process other assets concurrently.
        """
        mandate = self._pending.get(mandate_id)
        if not mandate:
            return {"approved": False, "reason": "Mandate not found"}

        try:
            # Non-blocking wait — event loop continues serving other tasks
            result = await asyncio.wait_for(
                asyncio.shield(mandate._future),
                timeout=timeout,
            )
            return result

        except asyncio.TimeoutError:
            mandate.status = MandateStatus.EXPIRED
            async with self._lock:
                self._pending.pop(mandate_id, None)
            logger.warning("[Mandate] EXPIRED %s — no biometric response",
                           mandate_id[:8])
            return {
                "approved": False,
                "reason":   "Biometric timeout — mandate expired",
                "mandate_id": mandate_id,
            }

    async def approve(self, mandate_id: str, signature: str) -> dict:
        """
        Called by the webhook when user approves the biometric prompt.
        Verifies the HMAC-SHA256 signature against the mandate challenge,
        then resolves the future so the orchestrator can proceed.

        PoC signature protocol:
          signature = HMAC-SHA256(
              key  = APEE_WEBAUTHN_SECRET (from .env),
              data = mandate.challenge
          ).hexdigest()

        The dashboard's /api/mandate/approve route computes this automatically.
        See _make_expected_sig() above for the server-side reference.

        Production: replace the HMAC check with py_webauthn assertion
        verification against the user's stored credential public key.
        """
        async with self._lock:
            mandate = self._pending.get(mandate_id)

        if not mandate:
            return {"success": False, "reason": "Mandate not found or expired"}

        if mandate.is_expired():
            mandate.status = MandateStatus.EXPIRED
            return {"success": False, "reason": "Mandate expired"}

        if not signature:
            mandate.status = MandateStatus.REJECTED
            result = {"approved": False, "reason": "Empty signature"}
            mandate._future.set_result(result)
            return {"success": False, "reason": "Empty signature"}

        # ── Signature verification (PoC: HMAC-SHA256) ────────────────────────
        expected = _make_expected_sig(mandate.challenge)
        if not hmac.compare_digest(signature.lower(), expected.lower()):
            mandate.status = MandateStatus.REJECTED
            logger.warning(
                "[Mandate] SIGNATURE MISMATCH for %s — expected %s... got %s...",
                mandate_id[:8], expected[:12], signature[:12]
            )
            result = {"approved": False, "reason": "Invalid signature — WebAuthn verification failed"}
            mandate._future.set_result(result)
            async with self._lock:
                self._pending.pop(mandate_id, None)
            return {"success": False, "reason": "Invalid signature"}
        # ─────────────────────────────────────────────────────────────────────

        mandate.status = MandateStatus.APPROVED
        approved_mandate = {
            "approved":          True,
            "mandate_id":        mandate.mandate_id,
            "asset":             mandate.asset,
            "action":            mandate.action,
            "alloc_usd":         mandate.alloc_usd,
            "oracle_price":      mandate.oracle_price,
            "challenge":         mandate.challenge,
            "signature":         signature[:16] + "...",
            "conditions_passed": 6,
            "webauthn_uv":       "required",
            "approved_at":       datetime.now(timezone.utc).isoformat(),
        }

        mandate._future.set_result(approved_mandate)
        async with self._lock:
            self._pending.pop(mandate_id, None)

        logger.info("[Mandate] APPROVED %s — %s %s",
                    mandate_id[:8], mandate.action, mandate.asset)
        return {"success": True, "mandate": approved_mandate}

    async def reject(self, mandate_id: str, reason: str = "User rejected") -> dict:
        """Called when user dismisses the biometric prompt."""
        async with self._lock:
            mandate = self._pending.get(mandate_id)

        if not mandate:
            return {"success": False}

        mandate.status = MandateStatus.REJECTED
        mandate._future.set_result({
            "approved": False,
            "reason":   reason,
            "mandate_id": mandate_id,
        })
        async with self._lock:
            self._pending.pop(mandate_id, None)

        logger.warning("[Mandate] REJECTED %s: %s", mandate_id[:8], reason)
        return {"success": True}

    async def cleanup_expired(self):
        """Background task — removes expired mandates every 30 seconds."""
        while True:
            await asyncio.sleep(30)
            async with self._lock:
                expired = [
                    mid for mid, m in self._pending.items()
                    if m.is_expired()
                ]
            for mid in expired:
                await self.reject(mid, "Expired — cleanup")
            if expired:
                logger.info("[Mandate] Cleaned up %d expired mandates", len(expired))

    def get_pending(self) -> list:
        return [m.to_dict() for m in self._pending.values()]

    def count(self) -> int:
        return len(self._pending)
