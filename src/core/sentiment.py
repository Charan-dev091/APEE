"""
APEE — Sentiment Analysis
==========================
Shared layer used by both Quant and Visionary.
Uses Groq/Llama for fast sentiment analysis.
"""

import json
import logging

logger = logging.getLogger(__name__)


class SentimentAnalyzer:
    """
    Shared sentiment layer.
    Called by Orchestrator before Quant + Visionary run.
    """

    def __init__(self, groq_client, model="llama-3.3-70b-versatile"):
        self.client         = groq_client
        self.model          = model
        self._cache         = {}
        self._cache_cycles  = {}
        self.cache_duration = 12

    def analyze(self, asset: str, scout_data: dict, cycle: int) -> dict:
        age = cycle - self._cache_cycles.get(asset, 0)
        if age < self.cache_duration and asset in self._cache:
            return self._cache[asset]

        if not self.client:
            result = self._neutral(asset, "No API key")
            self._cache[asset] = result
            self._cache_cycles[asset] = cycle
            return result

        try:
            candles  = scout_data.get("candles_15m", {}).get("payload", [])
            recent   = [c["close"] for c in candles[-5:]] if candles else []
            ob       = scout_data.get("orderbook", {}).get("payload", {})

            context = {
                "asset":         asset,
                "recent_prices": recent,
                "bids":          ob.get("bids", [])[:3] if ob else [],
                "asks":          ob.get("asks", [])[:3] if ob else [],
            }

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a market sentiment analyzer. "
                            "Return ONLY a JSON object: "
                            '{"sentiment": "bullish"|"bearish"|"neutral", '
                            '"score": -1.0 to 1.0, '
                            '"confidence": 0.0-1.0, '
                            '"reason": "one sentence"}. No markdown.'
                        )
                    },
                    {
                        "role": "user",
                        "content": f"Analyze sentiment for {asset}:\n{json.dumps(context)}"
                    }
                ],
                temperature=0.1,
                max_tokens=256,
            )

            raw = response.choices[0].message.content.strip()
            if raw.startswith("```"):
                raw = raw[raw.index("\n")+1:]
            if raw.endswith("```"):
                raw = raw[:-3].rstrip()

            parsed = json.loads(raw)
            result = {
                "agent":      "sentiment",
                "asset":      asset,
                "sentiment":  parsed.get("sentiment", "neutral"),
                "score":      float(parsed.get("score", 0.0)),
                "confidence": float(parsed.get("confidence", 0.5)),
                "reason":     parsed.get("reason", ""),
            }

        except Exception as e:
            logger.warning("[Sentiment] %s failed: %s", asset, e)
            result = self._neutral(asset, str(e))

        self._cache[asset] = result
        self._cache_cycles[asset] = cycle
        logger.info("[Sentiment] %s → %s (%.2f)", asset, result["sentiment"], result["score"])
        return result

    def _neutral(self, asset, reason):
        return {
            "agent":      "sentiment",
            "asset":      asset,
            "sentiment":  "neutral",
            "score":      0.0,
            "confidence": 0.3,
            "reason":     reason,
        }
