"""
APEE — Agent 2: The Analyst
============================
Fast inference agent. Single responsibility: receive a DataPacket
from the Scout, compute features, run the LightGBM model, and
return a confidence-scored directional signal.

This is the "Quant" in APEE terminology — optimised for speed.
Inference runs in < 50ms. Pluggable model layer: swap LightGBM
for any scikit-learn compatible estimator without changing the
Analyst's interface.

Output contract:
  AnalystSignal {
    asset, direction, confidence, features, model_id, latency_ms
  }
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from src.agents.scout import DataPacket, PacketStatus
from src.indicators.local_indicators import compute_all, latest

logger = logging.getLogger(__name__)


# ── Output Contract ───────────────────────────────────────────────────────────

@dataclass
class AnalystSignal:
    """
    Output from the Analyst agent. Consumed by the Consensus Gate.
    """
    asset:          str
    direction:      str         # "long" | "short" | "neutral"
    confidence:     float       # 0.0 → 1.0
    features:       dict        # feature vector used for this prediction
    model_id:       str         # which model produced this signal
    latency_ms:     int         # inference time
    error:          str | None = None


# ── Analyst Agent ─────────────────────────────────────────────────────────────

class AnalystAgent:
    """
    The Analyst: fast directional signal from technical features.

    Primary model: LightGBM (trained offline on 2010→present data).
    Fallback model: rule-based heuristic (RSI + MACD + EMA crossover).

    The fallback ensures the Analyst always produces a signal even
    when the LightGBM model is unavailable — critical for PoC demos
    and the paper's ablation study baseline.
    """

    def __init__(self, model_path: str | None = None):
        """
        Args:
            model_path: Path to trained LightGBM .txt model file.
                        If None, falls back to rule-based heuristic.
        """
        self.model = None
        self.model_id = "rule_based_heuristic"
        self.model_path = model_path

        if model_path:
            self._load_model(model_path)

    def _load_model(self, path: str) -> None:
        """Load a pre-trained LightGBM model from disk."""
        try:
            import lightgbm as lgb
            self.model = lgb.Booster(model_file=path)
            self.model_id = f"lightgbm:{path}"
            logger.info("[Analyst] LightGBM model loaded from %s", path)
        except ImportError:
            logger.warning(
                "[Analyst] lightgbm not installed. "
                "Falling back to rule-based heuristic. "
                "Run: pip install lightgbm"
            )
        except Exception as e:
            logger.error("[Analyst] Failed to load model from %s: %s", path, e)

    # ── Primary Interface ─────────────────────────────────────────────────────

    def analyze(self, packet: DataPacket) -> AnalystSignal:
        """
        Main entry point. Takes a Scout DataPacket and returns
        a directional signal with confidence score.
        """
        start_ms = time.monotonic()

        if packet.status == PacketStatus.FAILED or packet.payload is None:
            return AnalystSignal(
                asset=packet.asset,
                direction="neutral",
                confidence=0.0,
                features={},
                model_id=self.model_id,
                latency_ms=0,
                error=f"Scout packet failed: {packet.error}",
            )

        try:
            features = self._extract_features(packet)

            if self.model is not None:
                direction, confidence = self._lgbm_predict(features)
            else:
                direction, confidence = self._heuristic_predict(features)

            latency = int((time.monotonic() - start_ms) * 1000)

            logger.info(
                "[Analyst] %s → %s (conf: %.2f) via %s [%dms]",
                packet.asset, direction, confidence, self.model_id, latency
            )

            return AnalystSignal(
                asset=packet.asset,
                direction=direction,
                confidence=confidence,
                features=features,
                model_id=self.model_id,
                latency_ms=latency,
            )

        except Exception as e:
            latency = int((time.monotonic() - start_ms) * 1000)
            logger.error("[Analyst] Analysis failed for %s: %s", packet.asset, e)
            return AnalystSignal(
                asset=packet.asset,
                direction="neutral",
                confidence=0.0,
                features={},
                model_id=self.model_id,
                latency_ms=latency,
                error=str(e),
            )

    # ── Feature Engineering ───────────────────────────────────────────────────

    def _extract_features(self, packet: DataPacket) -> dict:
        """
        Extract the feature vector from raw OHLCV candles.
        These are the same features used during LightGBM training —
        consistency between training and inference is critical.
        """
        candles = packet.payload
        if not candles or len(candles) < 20:
            raise ValueError(
                f"Insufficient candles for {packet.asset}: {len(candles) if candles else 0}"
            )

        indicators = compute_all(candles)

        def safe_latest(key: str, default: float = 0.0) -> float:
            val = latest(indicators.get(key, []))
            return float(val) if val is not None else default

        def safe_prev(key: str, n: int = 1, default: float = 0.0) -> float:
            series = indicators.get(key, [])
            valid = [v for v in series if v is not None]
            if len(valid) > n:
                return float(valid[-(n + 1)])
            return default

        # Price
        closes  = [c["close"] for c in candles if c.get("close")]
        current = closes[-1] if closes else 0.0
        prev    = closes[-2] if len(closes) > 1 else current

        features = {
            # Momentum
            "rsi_14":       safe_latest("rsi14"),
            "rsi_7":        safe_latest("rsi7"),
            "macd":         safe_latest("macd"),
            "macd_signal":  safe_latest("macd_signal"),
            "macd_hist":    safe_latest("macd_histogram"),
            "stoch_rsi":    safe_latest("stoch_rsi"),

            # Trend
            "ema_20":       safe_latest("ema20"),
            "ema_50":       safe_latest("ema50"),
            "price_vs_ema20": (current / safe_latest("ema20") - 1) if safe_latest("ema20") else 0,
            "price_vs_ema50": (current / safe_latest("ema50") - 1) if safe_latest("ema50") else 0,
            "ema_cross":    safe_latest("ema20") - safe_latest("ema50"),  # + = bullish
            "adx":          safe_latest("adx"),

            # Volatility
            "atr_14":       safe_latest("atr14"),
            "atr_3":        safe_latest("atr3"),
            "bb_upper":     safe_latest("bbands_upper"),
            "bb_lower":     safe_latest("bbands_lower"),
            "bb_width":     (
                safe_latest("bbands_upper") - safe_latest("bbands_lower")
            ) / current if current else 0,
            "price_vs_bb_upper": (current / safe_latest("bbands_upper") - 1) if safe_latest("bbands_upper") else 0,
            "price_vs_bb_lower": (current / safe_latest("bbands_lower") - 1) if safe_latest("bbands_lower") else 0,

            # Volume
            "obv":          safe_latest("obv"),
            "vwap":         safe_latest("vwap"),
            "price_vs_vwap": (current / safe_latest("vwap") - 1) if safe_latest("vwap") else 0,

            # Returns
            "return_1":     (current / prev - 1) if prev else 0,
            "return_5":     (current / closes[-6] - 1) if len(closes) > 5 else 0,
            "return_20":    (current / closes[-21] - 1) if len(closes) > 20 else 0,

            # Candle structure
            "hl_ratio":     (candles[-1]["high"] - candles[-1]["low"]) / current if current else 0,
            "close_position": (
                (current - candles[-1]["low"]) /
                (candles[-1]["high"] - candles[-1]["low"])
            ) if (candles[-1]["high"] - candles[-1]["low"]) > 0 else 0.5,

            # Momentum changes (previous bar comparison)
            "rsi_delta":    safe_latest("rsi14") - safe_prev("rsi14"),
            "macd_delta":   safe_latest("macd_histogram") - safe_prev("macd_histogram"),
        }

        return features

    # ── LightGBM Inference ────────────────────────────────────────────────────

    def _lgbm_predict(self, features: dict) -> tuple[str, float]:
        """
        Run inference on the trained LightGBM model.
        Returns (direction, confidence).
        """
        import numpy as np

        feature_names = self.model.feature_name()
        feature_vector = np.array(
            [[features.get(f, 0.0) for f in feature_names]]
        )

        prob = self.model.predict(feature_vector)[0]

        if prob > 0.55:
            return "long", float(prob)
        elif prob < 0.45:
            return "short", float(1 - prob)
        else:
            return "neutral", float(max(prob, 1 - prob))

    # ── Rule-Based Heuristic (fallback + ablation baseline) ───────────────────

    def _heuristic_predict(self, features: dict) -> tuple[str, float]:
        """
        Rule-based directional heuristic. Used when:
          1. LightGBM model not loaded
          2. Ablation study: compare ML vs rules
          3. PoC demo before model is trained

        Logic: weighted vote across RSI, MACD, EMA cross, BB position.
        This mirrors classic retail technical analysis — deliberately
        simplistic to show LightGBM's improvement in the paper.
        """
        score = 0.0
        weight_total = 0.0

        # RSI (weight: 0.25)
        rsi = features.get("rsi_14", 50)
        if rsi < 30:
            score += 0.25      # oversold → bullish
        elif rsi > 70:
            score -= 0.25      # overbought → bearish
        else:
            score += 0.25 * ((rsi - 50) / 50) * -1  # linear scale
        weight_total += 0.25

        # MACD histogram (weight: 0.25)
        macd_hist = features.get("macd_hist", 0)
        macd_delta = features.get("macd_delta", 0)
        if macd_hist > 0 and macd_delta > 0:
            score += 0.25      # rising positive histogram → bullish
        elif macd_hist < 0 and macd_delta < 0:
            score -= 0.25      # falling negative histogram → bearish
        weight_total += 0.25

        # EMA cross (weight: 0.30)
        ema_cross = features.get("ema_cross", 0)
        if ema_cross > 0:
            score += 0.30      # EMA20 > EMA50 → bullish
        else:
            score -= 0.30
        weight_total += 0.30

        # Bollinger Band position (weight: 0.20)
        bb_pos = features.get("price_vs_bb_upper", 0)
        bb_lower_pos = features.get("price_vs_bb_lower", 0)
        if bb_pos > 0:
            score -= 0.10      # above upper band → slightly bearish
        elif bb_lower_pos < 0:
            score += 0.10      # below lower band → slightly bullish
        weight_total += 0.20

        normalised = score / weight_total if weight_total else 0

        if normalised > 0.15:
            return "long",    min(0.5 + normalised, 0.85)
        elif normalised < -0.15:
            return "short",   min(0.5 + abs(normalised), 0.85)
        else:
            return "neutral", 0.5


# ── Training Helper ───────────────────────────────────────────────────────────

def train_analyst_model(
    data_dir: str = "./apee_data/stocks",
    output_path: str = "./apee_data/models/analyst_lgbm.txt",
    tickers: list[str] | None = None,
) -> None:
    """
    Train the LightGBM model on historical parquet data.
    Run this once after the data pipeline has been executed.

    Usage:
        from src.agents.analyst import train_analyst_model
        train_analyst_model()

    Then load the trained model:
        analyst = AnalystAgent(model_path="./apee_data/models/analyst_lgbm.txt")
    """
    try:
        import lightgbm as lgb
        import numpy as np
        import pandas as pd
        from pathlib import Path
    except ImportError:
        raise ImportError(
            "Training dependencies not installed. "
            "Run: pip install lightgbm pandas pyarrow numpy"
        )

    import os
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    data_path = Path(data_dir)
    files = list(data_path.glob("*.parquet"))

    if tickers:
        files = [f for f in files if f.stem in tickers]

    if not files:
        raise FileNotFoundError(
            f"No parquet files found in {data_dir}. "
            "Run the data pipeline first: python apee_data_pipeline.py"
        )

    dfs = []
    for f in files:
        df = pd.read_parquet(f)
        df["ticker"] = f.stem
        dfs.append(df)

    combined = pd.concat(dfs, ignore_index=True)
    combined = combined.dropna(subset=["target_1d"])

    feature_cols = [
        "rsi_14", "macd", "macd_signal", "macd_diff",
        "ema_10", "ema_20", "ema_50", "adx_14",
        "bb_upper", "bb_lower", "bb_width", "atr_14",
        "obv", "vwap", "returns_1d", "returns_5d",
        "returns_20d", "hl_ratio", "gap",
    ]

    available_cols = [c for c in feature_cols if c in combined.columns]
    X = combined[available_cols].fillna(0)
    y = combined["target_1d"]

    # Temporal train/test split — never shuffle time series data
    split = int(len(X) * 0.8)
    X_train, X_test = X.iloc[:split], X.iloc[split:]
    y_train, y_test = y.iloc[:split], y.iloc[split:]

    train_data = lgb.Dataset(X_train, label=y_train)
    test_data  = lgb.Dataset(X_test, label=y_test, reference=train_data)

    params = {
        "objective":        "binary",
        "metric":           "binary_logloss",
        "learning_rate":    0.05,
        "num_leaves":       31,
        "max_depth":        6,
        "min_child_samples": 50,
        "feature_fraction": 0.8,
        "bagging_fraction": 0.8,
        "bagging_freq":     5,
        "verbose":          -1,
        "n_jobs":           -1,
    }

    model = lgb.train(
        params,
        train_data,
        num_boost_round=500,
        valid_sets=[test_data],
        callbacks=[
            lgb.early_stopping(stopping_rounds=50),
            lgb.log_evaluation(period=50),
        ],
    )

    model.save_model(output_path)

    # Quick accuracy report
    preds = model.predict(X_test)
    predicted_dir = (preds > 0.5).astype(int)
    accuracy = (predicted_dir == y_test.values).mean()
    print(f"\n[Analyst Training Complete]")
    print(f"  Model saved: {output_path}")
    print(f"  Test accuracy: {accuracy:.4f} ({accuracy*100:.2f}%)")
    print(f"  Baseline (always predict up): {y_test.mean():.4f}")
    print(f"  Improvement over baseline: {accuracy - y_test.mean():+.4f}")
    print(f"  Features used: {available_cols}")
