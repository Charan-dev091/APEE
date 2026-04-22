"""
APEE — Commerce Checkout (Simulated)
======================================
The closed-loop economy: when a trade closes in profit,
gains are automatically routed to purchase wishlist items.

In production: UCP machine-to-machine merchant handshake.
In PoC: simulates purchase and logs the closed loop event.
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class CommerceAgent:
    """
    Simulated commerce checkout agent.
    Demonstrates the closed-loop concept for the paper.
    """

    def __init__(self, wishlist: list = None):
        self.wishlist    = wishlist or [
            {"item": "Mechanical keyboard",   "price": 150.0, "priority": 1},
            {"item": "Programming course",    "price": 49.0,  "priority": 2},
            {"item": "Cloud server (1 month)","price": 20.0,  "priority": 3},
        ]
        self.purchases   = []
        self.profit_pool = 0.0

    def receive_profit(self, asset: str, profit_usd: float, trade_receipt: dict):
        """
        Called by Orchestrator when a trade closes in profit.
        Routes profit to wishlist checkout.
        """
        if profit_usd <= 0:
            return None

        self.profit_pool += profit_usd
        logger.info("[Commerce] Received $%.2f profit from %s trade", profit_usd, asset)

        # Check if we can afford the next wishlist item
        next_item = self._get_next_item()
        if not next_item:
            logger.info("[Commerce] Wishlist empty — profit pooled ($%.2f)", self.profit_pool)
            return None

        if self.profit_pool >= next_item["price"]:
            return self._checkout(next_item, trade_receipt)

        logger.info("[Commerce] Pooling profit — need $%.2f more for '%s'",
                    next_item["price"] - self.profit_pool, next_item["item"])
        return None

    def _checkout(self, item: dict, trade_receipt: dict) -> dict:
        self.profit_pool -= item["price"]
        self.wishlist.remove(item)

        purchase = {
            "status":        "purchased",
            "item":          item["item"],
            "price":         item["price"],
            "funded_by":     trade_receipt.get("asset"),
            "trade_pnl":     trade_receipt.get("pnl"),
            "remaining_pool": round(self.profit_pool, 2),
            "timestamp":     datetime.now(timezone.utc).isoformat(),
            "note":          "Simulated UCP commerce checkout",
        }
        self.purchases.append(purchase)

        logger.info("[Commerce] PURCHASED '%s' for $%.2f — closed loop complete!",
                    item["item"], item["price"])
        return purchase

    def _get_next_item(self):
        if not self.wishlist:
            return None
        return min(self.wishlist, key=lambda x: x["priority"])

    def get_summary(self) -> dict:
        return {
            "purchases":    len(self.purchases),
            "profit_pool":  round(self.profit_pool, 2),
            "wishlist_remaining": len(self.wishlist),
            "total_spent":  round(sum(p["price"] for p in self.purchases), 2),
        }
