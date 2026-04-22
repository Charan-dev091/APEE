"""
APEE — Agent 4: The Auditor
============================
Pure rule-based validation layer.
No ML. No AI. Deterministic checks only.
Validates every proposed action before it reaches Paymaster.
"""

import logging

logger = logging.getLogger(__name__)


class AuditorAgent:
    """
    The Auditor: rule enforcement before execution.
    All checks are deterministic — no model can override these.
    """

    def __init__(
        self,
        max_position_pct:    float = 20.0,
        max_total_exposure:  float = 60.0,
        max_daily_loss_pct:  float = 10.0,
        max_positions:       int   = 5,
        min_balance_reserve: float = 20.0,
    ):
        self.max_position_pct    = max_position_pct
        self.max_total_exposure  = max_total_exposure
        self.max_daily_loss_pct  = max_daily_loss_pct
        self.max_positions       = max_positions
        self.min_balance_reserve = min_balance_reserve

    def validate(
        self,
        asset:         str,
        action:        str,
        alloc_usd:     float,
        price:         float,
        portfolio:     dict,
        initial_balance: float,
    ) -> tuple[bool, str, float, float]:
        """
        Run all checks. Returns (approved, reason, adjusted_alloc, confidence).
        confidence reflects headroom: 1.0 = well within limits, 0.0 = rejected.
        """
        if action == "hold":
            return True, "Hold — no validation needed", 0.0, 1.0

        balance     = portfolio.get("balance", 0)
        total_value = portfolio.get("total_value", balance)
        positions   = portfolio.get("positions", {})

        # 1. Minimum balance reserve
        min_bal = initial_balance * (self.min_balance_reserve / 100)
        if balance < min_bal:
            return False, f"Balance ${balance:.0f} below reserve ${min_bal:.0f}", 0.0, 0.0

        # 2. Max concurrent positions
        if len(positions) >= self.max_positions and asset not in positions:
            return False, f"Max {self.max_positions} positions reached", 0.0, 0.0

        # 3. Cap position size
        max_alloc = total_value * (self.max_position_pct / 100)
        if alloc_usd > max_alloc:
            logger.info("[Auditor] Capping %s from $%.0f to $%.0f",
                        asset, alloc_usd, max_alloc)
            alloc_usd = max_alloc

        # 4. Minimum order size
        if alloc_usd < 11.0:
            return False, f"Allocation ${alloc_usd:.2f} below minimum $11", 0.0, 0.0

        # 5. Total exposure check
        current_exposure = sum(
            p.get("alloc_usd", 0) for p in positions.values()
        )
        max_exposure_usd = total_value * (self.max_total_exposure / 100)
        if (current_exposure + alloc_usd) > max_exposure_usd:
            return False, f"Total exposure would exceed {self.max_total_exposure}%", 0.0, 0.0

        # Confidence = how much headroom remains after this trade (0.1–1.0)
        used_after   = (current_exposure + alloc_usd) / max_exposure_usd if max_exposure_usd > 0 else 1.0
        pos_used     = (len(positions) + 1) / self.max_positions
        confidence   = round(max(0.1, 1.0 - max(used_after, pos_used) * 0.6), 4)

        logger.info("[Auditor] %s %s $%.0f — APPROVED (conf=%.2f)", action, asset, alloc_usd, confidence)
        return True, "Approved", alloc_usd, confidence
