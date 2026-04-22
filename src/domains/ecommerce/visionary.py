"""
APEE E-Commerce — Agent 3: Price Visionary
============================================
Deep price trend analysis via Groq/Llama.
Analyzes 30-day price history + product context.
Answers: Is now a good time to buy or should user wait?

Same interface as trading VisionaryAgent.
"""

import json
import logging
import time

logger = logging.getLogger(__name__)


class PriceVisionary:
    """
    Deep price trend analysis powered by Groq/Llama.
    Provides structural buy/wait signal with rationale.
    """

    def __init__(self, groq_client, model="llama-3.3-70b-versatile"):
        self.client         = groq_client
        self.model          = model
        self._cache         = {}
        self._cycles        = {}
        self.cache_duration = 6  # cache for 6 cycles (~3 hours)

    def analyze(self, scout_data: dict, user_config: dict, cycle: int) -> dict:
        query = scout_data.get("query", "")
        age   = cycle - self._cycles.get(query, 0)

        if age < self.cache_duration and query in self._cache:
            logger.info("[Visionary] %s using cached signal", query)
            return self._cache[query]

        if not self.client:
            return self._signal(query, "wait", 0.0, "uncertain", "No API key")

        result = self._call_groq(query, scout_data, user_config)
        self._cache[query]  = result
        self._cycles[query] = cycle
        return result

    def _call_groq(self, query: str, scout_data: dict, user_config: dict) -> dict:
        try:
            current = scout_data.get("current", {}).get("payload", {}) or {}
            history = scout_data.get("history", {}).get("payload", {}) or {}

            ctx = {
                "product":        query,
                "current_price":  current.get("current_price"),
                "regular_price":  current.get("regular_price"),
                "discount_pct":   current.get("discount_pct"),
                "avg_30d":        history.get("avg_30d"),
                "min_30d":        history.get("min_30d"),
                "max_30d":        history.get("max_30d"),
                "price_history":  history.get("history", [])[-7:],  # last 7 days
                "user_min":       user_config.get("min_price"),
                "user_max":       user_config.get("max_price"),
                "user_tax_pct":   user_config.get("tax_pct", 0),
                "deadline_days":  user_config.get("deadline_days", 10),
            }

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an expert price analyst helping a consumer decide "
                            "whether to buy a product now or wait for a better price. "
                            "Analyze the price trend and user constraints. "
                            "Return ONLY a JSON object: "
                            '{"recommendation": "buy"|"wait"|"overpriced", '
                            '"confidence": 0.0-1.0, '
                            '"trend": "dropping"|"stable"|"rising"|"volatile", '
                            '"urgency": "high"|"medium"|"low", '
                            '"expected_low_days": integer or null, '
                            '"rationale": "one clear sentence explaining the recommendation"}. '
                            "No markdown. No extra text."
                        )
                    },
                    {
                        "role": "user",
                        "content": f"Analyze purchase timing for:\n{json.dumps(ctx, indent=2)}"
                    }
                ],
                temperature=0.1,
                max_tokens=300,
            )

            raw = response.choices[0].message.content.strip()
            if raw.startswith("```"):
                raw = raw[raw.index("\n")+1:]
            if raw.endswith("```"):
                raw = raw[:-3].rstrip()

            p = json.loads(raw)
            result = {
                "agent":              "price_visionary",
                "query":              query,
                "recommendation":     p.get("recommendation", "wait"),
                "structural_bias":    p.get("recommendation", "wait"),  # framework compatibility
                "confidence":         float(p.get("confidence", 0.5)),
                "trend":              p.get("trend", "stable"),
                "regime":             p.get("trend", "stable"),          # framework compatibility
                "urgency":            p.get("urgency", "medium"),
                "expected_low_days":  p.get("expected_low_days"),
                "rationale":          p.get("rationale", ""),
            }
            logger.info("[Visionary] %s → %s @ %.2f (%s) | %s",
                        query, result["recommendation"],
                        result["confidence"], result["trend"],
                        result["rationale"][:60])
            return result

        except Exception as e:
            logger.error("[Visionary] %s error: %s", query, e)
            return self._signal(query, "wait", 0.0, "uncertain", str(e))

    def _signal(self, query, rec, conf, trend, rationale):
        return {
            "agent":             "price_visionary",
            "query":             query,
            "recommendation":    rec,
            "structural_bias":   rec,
            "confidence":        conf,
            "trend":             trend,
            "regime":            trend,
            "urgency":           "medium",
            "expected_low_days": None,
            "rationale":         rationale,
        }
