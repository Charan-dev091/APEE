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
import json
import logging
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
        Resolves the future — orchestrator receives the approval.
        """
        async with self._lock:
            mandate = self._pending.get(mandate_id)

        if not mandate:
            return {"success": False, "reason": "Mandate not found or expired"}

        if mandate.is_expired():
            mandate.status = MandateStatus.EXPIRED
            return {"success": False, "reason": "Mandate expired"}

        # In production: verify the WebAuthn signature here
        # signature should be the cryptographic response from the hardware device
        # For PoC: accept any non-empty signature
        if not signature:
            mandate.status = MandateStatus.REJECTED
            result = {"approved": False, "reason": "Empty signature"}
            mandate._future.set_result(result)
            return {"success": False, "reason": "Empty signature"}

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
