"""
APEE — Agent 3: The Strategist
================================
Deep pattern recognition agent. Single responsibility: analyze
60-day historical OHLCV context and identify structural patterns,
regime changes, and multi-timeframe confluence signals.

This is the "Visionary" in APEE terminology — runs every 24h,
focuses on depth not speed. Uses Claude's extended thinking to
reason over long historical windows the Analyst cannot see.

Key difference from the Analyst:
  - Analyst: fast (< 50ms), single timeframe, statistical model
  - Strategist: slow (~5-10s), multi-timeframe, structural reasoning

Output contract:
  StrategistSignal {
    asset, structural_bias, regime, key_levels, confidence,
    rationale, timeframe, latency_ms
  }
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from src.agents.scout import DataPacket, PacketStatus
from src.indicators.local_indicators import compute_all, latest, last_n

logger = logging.getLogger(__name__)


# ── Output Contract ───────────────────────────────────────────────────────────

@dataclass
class StrategistSignal:
    """
    Output from the Strategist agent. Consumed by the Consensus Gate.
    """
    asset:             str
    structural_bias:   str        # "bullish" | "bearish" | "neutral"
    regime:            str        # "trending" | "ranging" | "volatile" | "uncertain"
    key_levels:        dict       # {"support": [...], "resistance": [...]}
    confidence:        float      # 0.0 → 1.0
    rationale:         str        # Claude's reasoning summary
    timeframe:         str        # "short" | "medium" | "long"
    signal_valid_hours: int       # how long this signal should be trusted
    latency_ms:        int
    error:             str | None = None


# ── Strategist Agent ──────────────────────────────────────────────────────────

class StrategistAgent:
    """
    The Strategist: structural market analysis via Claude.

    Uses the full 4h candle context (60 bars = 10 days) to identify:
    - Price structure (higher highs/lows, lower highs/lows)
    - EMA regime (price vs EMA20/50, EMA20 vs EMA50)
    - Volatility regime (ATR expansion/contraction)
    - Key support/resistance levels
    - Multi-timeframe confluence with 1d trend

    The Strategist's signal is intentionally slow-moving — it
    represents the structural backdrop against which the Analyst's
    fast signals are evaluated in the Consensus Gate.
    """

    def __init__(self, anthropic_client, model: str = "claude-sonnet-4-20250514"):
        self.client = anthropic_client
        self.model  = model
        self._signal_cache: dict[str, tuple[StrategistSignal, float]] = {}
        self.cache_duration_hours = 24  # Reuse signal for 24h unless invalidated

    # ── Primary Interface ─────────────────────────────────────────────────────

    def analyze(
        self,
        packet_4h: DataPacket,
        packet_1d: DataPacket | None = None,
        force_refresh: bool = False,
    ) -> StrategistSignal:
        """
        Main entry point. Takes 4h and optional 1d DataPackets.

        Uses cached signal if available and within cache_duration_hours.
        Forces a refresh if force_refresh=True or cache expired.
        """
        asset = packet_4h.asset
        cache_key = asset

        # Check cache
        if not force_refresh and cache_key in self._signal_cache:
            cached_signal, cached_at = self._signal_cache[cache_key]
            age_hours = (time.monotonic() - cached_at) / 3600
            if age_hours < self.cache_duration_hours:
                logger.info(
                    "[Strategist] Using cached signal for %s (%.1fh old)",
                    asset, age_hours
                )
                return cached_signal

        start_ms = time.monotonic()

        if packet_4h.status == PacketStatus.FAILED or packet_4h.payload is None:
            return StrategistSignal(
                asset=asset,
                structural_bias="neutral",
                regime="uncertain",
                key_levels={},
                confidence=0.0,
                rationale="Scout packet failed",
                timeframe="medium",
                signal_valid_hours=1,
                latency_ms=0,
                error=packet_4h.error,
            )

        try:
            context = self._build_context(packet_4h, packet_1d)
            signal  = self._call_claude(asset, context)

            latency = int((time.monotonic() - start_ms) * 1000)
            signal.latency_ms = latency

            # Cache the signal
            self._signal_cache[cache_key] = (signal, time.monotonic())

            logger.info(
                "[Strategist] %s → %s/%s (conf: %.2f) [%dms]",
                asset, signal.structural_bias, signal.regime,
                signal.confidence, latency
            )
            return signal

        except Exception as e:
            latency = int((time.monotonic() - start_ms) * 1000)
            logger.error("[Strategist] Analysis failed for %s: %s", asset, e)
            return StrategistSignal(
                asset=asset,
                structural_bias="neutral",
                regime="uncertain",
                key_levels={},
                confidence=0.0,
                rationale=f"Analysis failed: {e}",
                timeframe="medium",
                signal_valid_hours=1,
                latency_ms=latency,
                error=str(e),
            )

    # ── Context Builder ───────────────────────────────────────────────────────

    def _build_context(
        self,
        packet_4h: DataPacket,
        packet_1d: DataPacket | None,
    ) -> dict:
        """
        Build structured market context for Claude to analyze.
        Computes indicators locally, formats last 60 bars of 4h data.
        """
        candles_4h = packet_4h.payload or []
        indicators = compute_all(candles_4h)

        def s(key): return last_n(indicators.get(key, []), 15)
        def l(key): return latest(indicators.get(key, []))

        closes = [c["close"] for c in candles_4h if c.get("close")]
        highs  = [c["high"]  for c in candles_4h if c.get("high")]
        lows   = [c["low"]   for c in candles_4h if c.get("low")]

        # 1D context if available
        daily_context = {}
        if packet_1d and packet_1d.payload:
            ind_1d = compute_all(packet_1d.payload)
            daily_context = {
                "ema_20_1d": round(l("ema20") or 0, 2),
                "ema_50_1d": round(l("ema50") or 0, 2),
                "rsi_1d":    round(l("rsi14") or 0, 2),
                "adx_1d":    round(l("adx")   or 0, 2),
            }

        return {
            "asset":            packet_4h.asset,
            "current_price":    round(closes[-1], 2) if closes else 0,
            "timeframe":        "4h",
            "bars_analyzed":    len(candles_4h),
            "price_range_10d":  {
                "high": round(max(highs[-60:]), 2) if highs else 0,
                "low":  round(min(lows[-60:]),  2) if lows else 0,
            },
            "indicators_4h": {
                "ema_20":      round(l("ema20") or 0, 2),
                "ema_50":      round(l("ema50") or 0, 2),
                "rsi_14":      round(l("rsi14") or 0, 2),
                "macd":        round(l("macd")  or 0, 4),
                "macd_hist":   round(l("macd_histogram") or 0, 4),
                "atr_14":      round(l("atr14") or 0, 4),
                "adx":         round(l("adx")   or 0, 2),
                "bb_upper":    round(l("bbands_upper") or 0, 2),
                "bb_lower":    round(l("bbands_lower") or 0, 2),
                "ema_20_series": [round(v, 2) for v in s("ema20") if v],
                "ema_50_series": [round(v, 2) for v in s("ema50") if v],
                "rsi_series":    [round(v, 2) for v in s("rsi14") if v],
                "macd_series":   [round(v, 4) for v in s("macd")  if v],
            },
            "daily_context": daily_context,
            "recent_closes_4h": [round(c, 2) for c in closes[-20:]],
        }

    # ── Claude Inference ──────────────────────────────────────────────────────

    def _call_claude(self, asset: str, context: dict) -> StrategistSignal:
        """
        Call Claude to perform structural market analysis.
        Returns a parsed StrategistSignal.
        """
        system = (
            "You are a professional quantitative market analyst specializing in "
            "structural price analysis and multi-timeframe regime identification. "
            "Your role in the APEE framework is to identify the structural backdrop "
            "against which short-term trading signals are evaluated.\n\n"
            "Analyze the provided market data and return ONLY a strict JSON object "
            "with exactly these fields:\n"
            "{\n"
            '  "structural_bias": "bullish" | "bearish" | "neutral",\n'
            '  "regime": "trending" | "ranging" | "volatile" | "uncertain",\n'
            '  "confidence": 0.0-1.0,\n'
            '  "key_levels": {"support": [price1, price2], "resistance": [price1, price2]},\n'
            '  "timeframe": "short" | "medium" | "long",\n'
            '  "signal_valid_hours": integer (1-48),\n'
            '  "rationale": "concise one-paragraph structural analysis"\n'
            "}\n\n"
            "Base your analysis on: EMA structure, price action vs key levels, "
            "MACD regime, RSI trend, ATR regime, higher timeframe context. "
            "Do not emit markdown or extra fields."
        )

        user_msg = (
            f"Analyze the structural market context for {asset}:\n\n"
            f"{json.dumps(context, indent=2)}"
        )

        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
        )

        raw = ""
        for block in response.content:
            if block.type == "text":
                raw += block.text

        # Strip markdown fences if present
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned[cleaned.index("\n") + 1:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].rstrip()

        parsed = json.loads(cleaned)

        return StrategistSignal(
            asset=asset,
            structural_bias=parsed.get("structural_bias", "neutral"),
            regime=parsed.get("regime", "uncertain"),
            key_levels=parsed.get("key_levels", {"support": [], "resistance": []}),
            confidence=float(parsed.get("confidence", 0.5)),
            rationale=parsed.get("rationale", ""),
            timeframe=parsed.get("timeframe", "medium"),
            signal_valid_hours=int(parsed.get("signal_valid_hours", 24)),
            latency_ms=0,
        )

    def invalidate_cache(self, asset: str) -> None:
        """Force cache invalidation for an asset — call on significant news."""
        if asset in self._signal_cache:
            del self._signal_cache[asset]
            logger.info("[Strategist] Cache invalidated for %s", asset)
