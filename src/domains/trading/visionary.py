"""
APEE — Agent 3: The Visionary
==============================
Deep structural pattern recognition via Groq (Llama 3.3 70B).
Analyzes 4h candles + sentiment context.
Cached for 24 cycles — slow but deep.

Groq replaces Anthropic — same logic, faster inference, free tier.
"""

import json
import logging
import time
from src.agents.indicators import compute_all, latest

logger = logging.getLogger(__name__)


class VisionaryAgent:
    """
    The Visionary: structural market analysis.
    Uses Groq/Llama to identify regime, key levels, structural bias.
    Complements the Quant's fast statistical signal.
    """

    def __init__(self, groq_client, model="llama-3.3-70b-versatile"):
        self.client  = groq_client
        self.model   = model
        self._cache  = {}
        self._cycles = {}
        self.cache_duration = 24

    def analyze(self, scout_data: dict, sentiment: dict, cycle: int) -> dict:
        asset = scout_data["asset"]
        age   = cycle - self._cycles.get(asset, 0)

        if age < self.cache_duration and asset in self._cache:
            logger.info("[Visionary] %s using cached signal (age: %d cycles)", asset, age)
            return self._cache[asset]

        candles_4h = scout_data.get("candles_4h", {}).get("payload", [])
        if not candles_4h or len(candles_4h) < 20:
            return self._signal(asset, "neutral", 0.0, "uncertain", "Insufficient 4h data")

        ind    = compute_all(candles_4h)
        result = self._call_groq(asset, ind, sentiment)

        self._cache[asset]  = result
        self._cycles[asset] = cycle
        return result

    def _call_groq(self, asset: str, ind: dict, sentiment: dict) -> dict:
        if not self.client:
            return self._signal(asset, "neutral", 0.0, "uncertain", "No API key")

        try:
            ctx = {
                "asset":           asset,
                "current_price":   ind.get("current_price"),
                "ema20":           ind.get("ema20"),
                "ema50":           ind.get("ema50"),
                "rsi14":           ind.get("rsi14"),
                "macd":            ind.get("macd"),
                "macd_hist":       ind.get("macd_hist"),
                "bb_upper":        ind.get("bb_upper"),
                "bb_lower":        ind.get("bb_lower"),
                "atr14":           ind.get("atr14"),
                "ema_cross":       ind.get("ema_cross"),
                "return_5":        ind.get("return_5"),
                "return_20":       ind.get("return_20"),
                "recent_closes":   ind.get("recent_closes", []),
                "sentiment":       sentiment.get("sentiment"),
                "sentiment_score": sentiment.get("score"),
            }

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a quantitative market analyst specializing in "
                            "structural pattern recognition across 4-hour timeframes. "
                            "Return ONLY a JSON object with these exact fields: "
                            '{"structural_bias": "bullish"|"bearish"|"neutral", '
                            '"confidence": 0.0-1.0, '
                            '"regime": "trending"|"ranging"|"volatile"|"uncertain", '
                            '"key_support": number, '
                            '"key_resistance": number, '
                            '"signal_valid_hours": integer, '
                            '"rationale": "one sentence"}. No markdown. No extra text.'
                        )
                    },
                    {
                        "role": "user",
                        "content": f"Analyze {asset} structural pattern:\n{json.dumps(ctx, indent=2)}"
                    }
                ],
                temperature=0.1,
                max_tokens=512,
            )

            raw = response.choices[0].message.content.strip()
            if raw.startswith("```"):
                raw = raw[raw.index("\n")+1:]
            if raw.endswith("```"):
                raw = raw[:-3].rstrip()

            p = json.loads(raw)
            result = {
                "agent":              "visionary",
                "asset":              asset,
                "structural_bias":    p.get("structural_bias", "neutral"),
                "confidence":         float(p.get("confidence", 0.5)),
                "regime":             p.get("regime", "uncertain"),
                "key_support":        p.get("key_support"),
                "key_resistance":     p.get("key_resistance"),
                "signal_valid_hours": int(p.get("signal_valid_hours", 24)),
                "rationale":          p.get("rationale", ""),
            }
            logger.info("[Visionary] %s → %s @ %.2f (%s)",
                        asset, result["structural_bias"],
                        result["confidence"], result["regime"])
            return result

        except Exception as e:
            logger.error("[Visionary] %s error: %s", asset, e)
            return self._signal(asset, "neutral", 0.0, "uncertain", str(e))

    def _signal(self, asset, bias, conf, regime, rationale):
        return {
            "agent":              "visionary",
            "asset":              asset,
            "structural_bias":    bias,
            "confidence":         conf,
            "regime":             regime,
            "key_support":        None,
            "key_resistance":     None,
            "signal_valid_hours": 1,
            "rationale":          rationale,
        }
