"""
APEE — E-Commerce Paymaster
==============================
Budget manager and purchase executor for the e-commerce pipeline.
Tracks spending against a user-defined budget.

Called only when Consensus Gate returns EXECUTE for a product.
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class EcommercePaymaster:
    """
    Manages e-commerce budget and executes approved buy signals.

    In production: replace execute() with retailer API / browser automation.
    """

    def __init__(self, budget: float = 2000.0):
        self.budget          = budget
        self.spent           = 0.0
        self.purchases: list = []
        self.skipped: list   = []

    # ── Purchase Execution ─────────────────────────────────────────────────────

    def execute(self, mandate: dict, product: dict) -> dict:
        """
        Execute a buy signal for a product.

        Args:
            mandate: Approved mandate dict (from consensus gate)
            product: Product payload from ProductScout
        Returns:
            receipt dict with status "purchased" | "skipped" | "rejected"
        """
        query  = mandate.get("query", product.get("query", "Unknown"))
        price  = float(product.get("current_price", 0))
        title  = product.get("title", query)
        url    = product.get("url", "")
        source = product.get("source", "unknown")

        if price <= 0:
            return self._receipt(query, price, "rejected", "No valid price")

        # Budget check
        if self.spent + price > self.budget:
            remaining = self.budget - self.spent
            msg = (f"Budget ${self.budget:.0f} exceeded — "
                   f"spent ${self.spent:.0f}, remaining ${remaining:.0f}")
            logger.warning("[EcPaymaster] %s | %s", query, msg)
            receipt = self._receipt(query, price, "skipped", msg, title, url, source)
            self.skipped.append(receipt)
            return receipt

        # Duplicate check
        already_bought = any(p["query"] == query for p in self.purchases)
        if already_bought:
            receipt = self._receipt(query, price, "skipped",
                                    "Already purchased today", title, url, source)
            self.skipped.append(receipt)
            return receipt

        # Execute purchase
        self.spent += price
        receipt = self._receipt(query, price, "purchased",
                                f"Bought from {source} at ${price:.2f}",
                                title, url, source)
        self.purchases.append(receipt)

        logger.info("[EcPaymaster] BOUGHT '%s' $%.2f | spent $%.2f / $%.2f budget",
                    title[:40], price, self.spent, self.budget)
        return receipt

    # ── Status ─────────────────────────────────────────────────────────────────

    def get_status(self) -> dict:
        """Dashboard-ready budget and purchase status."""
        return {
            "budget":          round(self.budget, 2),
            "spent":           round(self.spent, 2),
            "remaining":       round(self.budget - self.spent, 2),
            "utilization_pct": round(self.spent / self.budget * 100, 1) if self.budget else 0,
            "purchases":       len(self.purchases),
            "skipped":         len(self.skipped),
            "recent_buys":     self.purchases[-5:] if self.purchases else [],
        }

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _receipt(self, query, price, status, message,
                 title="", url="", source="unknown") -> dict:
        return {
            "query":     query,
            "title":     title or query,
            "price":     round(price, 2),
            "url":       url,
            "source":    source,
            "status":    status,
            "message":   message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
