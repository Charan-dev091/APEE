"""
APEE — Commerce Agent (Trading Mode)
======================================
Tracks commerce-related spending generated from trading profits.
Used in the trading pipeline to convert profits into purchases.
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class CommerceAgent:
    """
    Tracks commerce activity funded by trading profits.
    Provides a summary for the dashboard.
    """

    def __init__(self):
        self._purchases: list  = []
        self._total_spent: float = 0.0
        self._profit_threshold: float = 500.0

    def check_and_buy(self, trading_profit: float, wishlist: list) -> list:
        """Check if trading profits justify purchasing wishlist items."""
        purchases = []
        if trading_profit < self._profit_threshold:
            return purchases

        for item in wishlist:
            price = item.get("price", 0)
            name  = item.get("name", "")
            if price and trading_profit >= price:
                receipt = self._buy(name, price, source="trading_profit")
                purchases.append(receipt)
                trading_profit -= price

        return purchases

    def _buy(self, item: str, price: float, source: str = "manual") -> dict:
        receipt = {
            "item":      item,
            "price":     round(price, 2),
            "source":    source,
            "status":    "purchased",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._purchases.append(receipt)
        self._total_spent += price
        logger.info("[Commerce] Purchased '%s' for $%.2f from %s", item, price, source)
        return receipt

    def get_summary(self) -> dict:
        """Dashboard-ready summary of all commerce activity."""
        return {
            "total_purchases": len(self._purchases),
            "total_spent":     round(self._total_spent, 2),
            "recent":          self._purchases[-5:] if self._purchases else [],
        }
