"""
APEE E-Commerce — Paymaster
=============================
Instead of executing a trade, opens the product page for checkout.
User gets a direct link to buy at the detected price.

In production: integrates with browser automation or
Amazon/Walmart checkout API to add to cart automatically.
"""

import json
import logging
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
import os

logger = logging.getLogger(__name__)
SAVE_PATH = Path(os.getenv("LOG_DIR", "./logs")) / "purchase_state.json"


class EcommercePaymaster:
    """
    E-commerce execution agent.
    Opens product checkout URL when mandate is approved.
    Tracks purchase history and budget.
    """

    def __init__(self, total_budget: float = 1000.0):
        self.total_budget = total_budget
        self.spent        = 0.0
        self.purchases    = []
        self.pending      = {}  # query → product data
        self._load()

    def _load(self):
        try:
            if SAVE_PATH.exists():
                data       = json.loads(SAVE_PATH.read_text())
                self.spent = data.get("spent", 0.0)
                self.purchases = data.get("purchases", [])
                logger.info("[Paymaster] Loaded — spent: $%.2f", self.spent)
        except Exception as e:
            logger.warning("[Paymaster] Load failed: %s", e)

    def _save(self):
        try:
            SAVE_PATH.parent.mkdir(exist_ok=True)
            SAVE_PATH.write_text(json.dumps({
                "spent":     self.spent,
                "purchases": self.purchases[-50:],
                "saved_at":  datetime.now(timezone.utc).isoformat(),
            }, indent=2))
        except Exception as e:
            logger.warning("[Paymaster] Save failed: %s", e)

    def execute(self, mandate: dict, product_data: dict) -> dict:
        """
        Execute approved purchase mandate.
        Opens product URL in browser for final checkout.
        """
        if not mandate.get("approved"):
            return {"status": "rejected", "reason": "Mandate not approved"}

        query = mandate.get("query", "")
        price = product_data.get("current_price", 0)
        url   = product_data.get("url", "")
        title = product_data.get("title", query)

        # Build search URL if no direct URL
        if not url:
            search_q = query.replace(" ", "+")
            url = f"https://www.amazon.com/s?k={search_q}"

        # Open in browser
        try:
            webbrowser.open(url)
            logger.info("[Paymaster] Opened browser for %s @ $%.2f", query, price)
        except Exception as e:
            logger.warning("[Paymaster] Browser open failed: %s", e)

        # Record purchase
        purchase = {
            "status":       "opened_for_checkout",
            "query":        query,
            "title":        title,
            "price":        price,
            "url":          url,
            "mandate_id":   mandate.get("mandate_id"),
            "timestamp":    datetime.now(timezone.utc).isoformat(),
        }
        self.purchases.append(purchase)
        self._save()

        print(f"\n{'='*60}")
        print(f"  🛒 PRODUCT OPENED FOR CHECKOUT")
        print(f"  Product: {title}")
        print(f"  Price:   ${price:.2f}")
        print(f"  URL:     {url[:60]}...")
        print(f"{'='*60}\n")

        return purchase

    def get_status(self) -> dict:
        return {
            "total_budget":    self.total_budget,
            "spent":           round(self.spent, 2),
            "remaining":       round(self.total_budget - self.spent, 2),
            "total_purchases": len(self.purchases),
        }
