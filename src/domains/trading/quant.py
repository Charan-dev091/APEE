"""
APEE — Agent 2: The Quant
==========================
Fast directional signal from technical indicators.
Uses heuristic rules (LightGBM when model is trained).
Runs on 15m candles — speed over depth.
"""

import logging
from src.agents.indicators import compute_all, latest

logger = logging.getLogger(__name__)


class QuantAgent:
    """
    The Quant: fast statistical signal.
    Output: direction (long/short/neutral) + confidence (0-1)
    """

    def __init__(self, model_path: str = None):
        self.model = None
        self.model_id = "heuristic_v1"
        if model_path:
            self._load_lgbm(model_path)

    def _load_lgbm(self, path):
        try:
            import lightgbm as lgb
            self.model = lgb.Booster(model_file=path)
            self.model_id = f"lightgbm:{path}"
            logger.info("[Quant] LightGBM loaded from %s", path)
        except Exception as e:
            logger.warning("[Quant] LightGBM load failed: %s — using heuristic", e)

    def analyze(self, scout_data: dict) -> dict:
        """
        Main entry. Takes Scout data, returns signal.
        """
        asset = scout_data["asset"]

        candles = scout_data.get("candles_15m", {}).get("payload", [])
        if not candles or len(candles) < 20:
            return self._signal(asset, "neutral", 0.0, "Insufficient candle data")

        ind = compute_all(candles)
        if not ind:
            return self._signal(asset, "neutral", 0.0, "Indicator computation failed")

        if self.model:
            direction, confidence = self._lgbm_predict(ind)
        else:
            direction, confidence = self._heuristic(ind)

        logger.info("[Quant] %s → %s @ %.2f", asset, direction, confidence)
        return self._signal(asset, direction, confidence, self.model_id)

    def _heuristic(self, ind: dict) -> tuple:
        score = 0.0

        # RSI
        rsi = ind.get("rsi14", 50) or 50
        if rsi < 35:   score += 0.30
        elif rsi > 65: score -= 0.30
        else:          score += (50 - rsi) / 50 * 0.20

        # MACD
        mh = ind.get("macd_hist", 0) or 0
        m  = ind.get("macd", 0) or 0
        if mh > 0 and m > 0:   score += 0.25
        elif mh < 0 and m < 0: score -= 0.25

        # EMA cross
        ec = ind.get("ema_cross", 0) or 0
        score += 0.25 if ec > 0 else -0.25

        # Momentum
        r1 = ind.get("return_1", 0) or 0
        r5 = ind.get("return_5", 0) or 0
        if r1 > 0 and r5 > 0:   score += 0.10
        elif r1 < 0 and r5 < 0: score -= 0.10

        # Bollinger
        price = ind.get("current_price", 0)
        bbu   = ind.get("bb_upper")
        bbl   = ind.get("bb_lower")
        if bbu and price > bbu: score -= 0.10
        elif bbl and price < bbl: score += 0.10

        if score > 0.20:   return "long",    min(0.50 + score, 0.90)
        elif score < -0.20: return "short",  min(0.50 + abs(score), 0.90)
        else:               return "neutral", 0.50

    def _lgbm_predict(self, ind: dict) -> tuple:
        import numpy as np
        names = self.model.feature_name()
        vec   = np.array([[ind.get(f, 0.0) for f in names]])
        prob  = self.model.predict(vec)[0]
        if prob > 0.55:   return "long",    float(prob)
        elif prob < 0.45: return "short",   float(1 - prob)
        else:             return "neutral", float(max(prob, 1-prob))

    def _signal(self, asset, direction, confidence, source):
        return {
            "agent":      "quant",
            "asset":      asset,
            "direction":  direction,
            "confidence": round(confidence, 4),
            "source":     source,
        }
