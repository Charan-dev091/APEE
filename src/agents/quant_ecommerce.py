"""
APEE E-Commerce — Agent 2: Price Quant
========================================
Fast statistical signal on product pricing.
Checks if current price is within user's target range.
Computes price position relative to 30-day history.

Output: direction (buy/wait/overpriced) + confidence
Identical interface to trading QuantAgent.
"""

import logging

logger = logging.getLogger(__name__)


class PriceQuant:
    """
    The Price Quant — fast statistical price signal.
    Replaces trading Quant with e-commerce logic.
    Same output schema: direction + confidence.
    """

    def analyze(self, scout_data: dict, user_config: dict) -> dict:
        """
        Analyze if product price matches user requirements.

        Args:
            scout_data:  Output from ProductScout
            user_config: User's price range and requirements

        Returns:
            direction:  "buy" | "wait" | "overpriced"
            confidence: 0.0 - 1.0
        """
        query = scout_data.get("query", "")

        # Extract current price
        current_packet = scout_data.get("current", {})
        if current_packet.get("status") == "FAILED":
            return self._signal(query, "wait", 0.0, "Price fetch failed")

        product = current_packet.get("payload", {})
        if not product:
            return self._signal(query, "wait", 0.0, "No product data")

        current_price = product.get("current_price", 0)
        if not current_price:
            return self._signal(query, "wait", 0.0, "No price available")

        # Extract price history for context
        history_packet = scout_data.get("history", {})
        history_data   = history_packet.get("payload", {})
        avg_30d        = history_data.get("avg_30d", current_price) if history_data else current_price
        min_30d        = history_data.get("min_30d", current_price) if history_data else current_price

        # User config
        min_price  = user_config.get("min_price", 0)
        max_price  = user_config.get("max_price", float("inf"))
        tax_pct    = user_config.get("tax_pct", 0)

        # Apply tax
        max_with_tax = max_price * (1 + tax_pct / 100)
        total_price  = current_price * (1 + tax_pct / 100)

        score = 0.0

        # Check 1: Is price within user range?
        if total_price > max_with_tax:
            return self._signal(query, "overpriced", 0.9,
                                f"${total_price:.2f} (with tax) exceeds max ${max_with_tax:.2f}")

        if total_price < min_price:
            # Suspiciously cheap — might be wrong product
            score += 0.2
        else:
            # Within range
            range_size   = max_with_tax - min_price
            price_pos    = (max_with_tax - total_price) / range_size if range_size > 0 else 0
            score       += price_pos * 0.4  # Higher score = closer to min price

        # Check 2: Price vs 30-day average
        if avg_30d > 0:
            pct_below_avg = (avg_30d - current_price) / avg_30d
            if pct_below_avg >= 0.10:
                score += 0.35  # 10%+ below average — strong buy signal
            elif pct_below_avg >= 0.05:
                score += 0.25  # 5-10% below average
            elif pct_below_avg >= 0:
                score += 0.10  # Slightly below average
            else:
                score -= 0.15  # Above average — wait

        # Check 3: Near 30-day low?
        if min_30d > 0:
            pct_above_min = (current_price - min_30d) / min_30d
            if pct_above_min <= 0.03:
                score += 0.25  # Near all-time low for period

        score = max(0.0, min(score, 0.95))

        if score >= 0.55:
            direction = "buy"
        elif score >= 0.30:
            direction = "wait"
        else:
            direction = "overpriced"

        reason = (
            f"Price: ${current_price:.2f} (${total_price:.2f} with tax) | "
            f"30d avg: ${avg_30d:.2f} | "
            f"Range: ${min_price}-${max_price}"
        )

        logger.info("[Quant] %s → %s @ %.2f | %s", query, direction, score, reason[:60])
        return self._signal(query, direction, round(score, 4), reason)

    def _signal(self, query, direction, confidence, reason):
        return {
            "agent":      "price_quant",
            "query":      query,
            "direction":  direction,
            "confidence": confidence,
            "reason":     reason,
            "source":     "heuristic_v1",
        }
