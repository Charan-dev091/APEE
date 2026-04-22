"""
APEE — Natural Language Intent Router
======================================
Sits between the user (chat interface) and the domain pipelines.

Instead of clicking "Trading" or "E-Commerce" buttons, the user types
their goal in plain text. This module classifies the intent and extracts
a structured configuration that the framework uses to route to the
correct domain plugin.

Examples
--------
"I want to invest in NVDA and TSLA"
→ {"domain": "trading", "assets": ["NVDA", "TSLA"], "interval_minutes": 5}

"Find me a cheap RTX 4090 under $700"
→ {"domain": "ecommerce", "wishlist": [{"product": "RTX 4090", "max_price": 700}]}

"Buy BTC and watch for Air Max 90s on sale"
→ {"domain": "both", "trading": {...}, "ecommerce": {...}}
"""

import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Default fallback config per domain
_TRADING_DEFAULTS = {
    "assets":            ["NVDA", "AAPL", "TSLA"],
    "interval_minutes":  5,
    "initial_balance":   10000,
    "max_alloc":         1000,
    "daily_cap":         3000,
}

_ECOMMERCE_DEFAULTS = {
    "wishlist":          [{"product": "RTX 4090", "max_price": 800}],
    "interval_minutes":  30,
    "budget":            2000,
}

# Intent classification prompt sent to LLM
_SYSTEM_PROMPT = """
You are an intent classifier for a personal economy engine.

Given a user message, return ONLY a JSON object with:
{
  "domain": "trading" | "ecommerce" | "both" | "unknown",
  "trading": {
    "assets": ["TICKER1", "TICKER2"],
    "interval_minutes": <int>,
    "initial_balance": <float>,
    "max_alloc": <float>,
    "daily_cap": <float>
  },
  "ecommerce": {
    "wishlist": [{"product": "<name>", "max_price": <float or null>}],
    "interval_minutes": <int>,
    "budget": <float>
  },
  "confidence": 0.0-1.0,
  "raw_intent": "<one-line summary>"
}

Rules:
- If user mentions stocks, crypto, invest, trade, buy/sell → domain = "trading"
- If user mentions products, find, shop, price, deal, cheap → domain = "ecommerce"
- If both → domain = "both", fill both sections
- If unclear → domain = "unknown"
- Omit the section that doesn't apply
- Never add prose, only return the JSON object
"""


class IntentRouter:
    """
    Natural Language Intent Router.

    Accepts free-form user text, uses an LLM to extract structured intent,
    and returns a config dict the framework can directly pass to the correct
    domain pipeline.

    Production path   : LLM-based extraction via Groq/Llama
    Fallback path     : Keyword heuristic (no API key needed)
    """

    def __init__(self, groq_client=None):
        self.client = groq_client
        self.model  = "llama-3.3-70b-versatile"

    def route(self, user_message: str) -> dict:
        """
        Classify user intent and return structured domain config.

        Returns
        -------
        dict with keys: domain, config, confidence, raw_intent
        """
        if self.client:
            result = self._llm_route(user_message)
        else:
            result = self._heuristic_route(user_message)

        logger.info(
            "[Router] '%s' → domain=%s (conf=%.2f)",
            user_message[:60], result.get("domain"), result.get("confidence", 0)
        )
        return result

    # ── LLM-based routing ─────────────────────────────────────────────────────

    def _llm_route(self, user_message: str) -> dict:
        """Use Groq/Llama to extract structured intent from free text."""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system",  "content": _SYSTEM_PROMPT},
                    {"role": "user",    "content": user_message},
                ],
                temperature=0.1,
                max_tokens=512,
            )
            raw = response.choices[0].message.content.strip()
            if raw.startswith("```"):
                raw = raw[raw.index("\n") + 1:]
            if raw.endswith("```"):
                raw = raw[:-3].rstrip()

            parsed = json.loads(raw)
            return self._build_result(parsed, source="llm")

        except Exception as e:
            logger.warning("[Router] LLM classification failed: %s — falling back to heuristic", e)
            return self._heuristic_route(user_message)

    # ── Keyword heuristic fallback ────────────────────────────────────────────

    def _heuristic_route(self, user_message: str) -> dict:
        """
        Keyword-based intent classification — no API key required.
        Used as fallback when LLM is unavailable.
        """
        msg = user_message.lower()

        trading_keywords   = ["invest", "trade", "stock", "crypto", "btc", "eth", "nvda",
                               "aapl", "tsla", "buy stock", "sell", "portfolio", "market"]
        ecommerce_keywords = ["buy", "find", "cheap", "deal", "shop", "product", "price",
                               "gpu", "laptop", "phone", "sneaker", "rtx", "macbook"]

        is_trading   = any(k in msg for k in trading_keywords)
        is_ecommerce = any(k in msg for k in ecommerce_keywords)

        if is_trading and is_ecommerce:
            domain = "both"
        elif is_trading:
            domain = "trading"
        elif is_ecommerce:
            domain = "ecommerce"
        else:
            domain = "unknown"

        return self._build_result({"domain": domain}, source="heuristic")

    # ── Config builder ────────────────────────────────────────────────────────

    def _build_result(self, parsed: dict, source: str) -> dict:
        """Merge LLM output with defaults to produce a complete config."""
        domain = parsed.get("domain", "unknown")

        trading_cfg   = {**_TRADING_DEFAULTS,   **(parsed.get("trading",   {}) or {})}
        ecommerce_cfg = {**_ECOMMERCE_DEFAULTS,  **(parsed.get("ecommerce", {}) or {})}

        return {
            "domain":     domain,
            "trading":    trading_cfg   if domain in ("trading",   "both") else None,
            "ecommerce":  ecommerce_cfg if domain in ("ecommerce", "both") else None,
            "confidence": parsed.get("confidence", 0.6 if source == "heuristic" else 0.0),
            "raw_intent": parsed.get("raw_intent", ""),
            "source":     source,
        }
