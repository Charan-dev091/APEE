"""
APEE — The Orchestrator
========================
Replaces the original single-agent decision_maker.py.

The Orchestrator is not an agent — it is the hub. It:
  1. Receives assets + market context from main.py
  2. Dispatches Scout to fetch live data for each asset
  3. Runs Analyst (fast) and Strategist (deep) in parallel
  4. Passes both signals to the Consensus Gate
  5. Routes EXECUTE decisions to the Auditor
  6. Returns final trade decisions to main.py in the exact
     same format as the original TradingAgent.decide_trade()
     — ensuring zero changes to the execution layer

Drop-in replacement for src/agent/decision_maker.py.
Main.py calls orchestrator.decide_trade(assets, context)
and gets back the same JSON structure as before.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

import anthropic

from src.agents.analyst import AnalystAgent
from src.agents.consensus_gate import ConsensusGate, GateDecision
from src.agents.scout import (
    ScoutAgent, SourceConfig, DataType, IngestionMode, make_live_configs
)
from src.agents.strategist import StrategistAgent
from src.config_loader import CONFIG
from src.indicators.local_indicators import compute_all, latest, last_n

logger = logging.getLogger(__name__)


class APEEOrchestrator:
    """
    The APEE Orchestrator: hub-and-spoke multi-agent coordinator.

    Maintains the same public interface as the original TradingAgent
    so main.py requires minimal changes:
      orchestrator.decide_trade(assets, context) → dict

    Internal pipeline per asset:
      Scout → [Analyst ∥ Strategist] → ConsensusGate → decision
    """

    def __init__(self, hyperliquid=None, model_path: str | None = None):
        self.hyperliquid = hyperliquid

        # Anthropic client (shared across Strategist + sanitizer)
        self.client = anthropic.Anthropic(
            api_key=CONFIG["anthropic_api_key"]
        )
        self.model = CONFIG.get("llm_model", "claude-sonnet-4-20250514")
        self.sanitize_model = CONFIG.get("sanitize_model", "claude-haiku-4-5-20251001")
        self.max_tokens = int(CONFIG.get("max_tokens", 4096))

        # Initialize agents
        self.scout      = ScoutAgent(hyperliquid_api=hyperliquid)
        self.analyst    = AnalystAgent(model_path=model_path)
        self.strategist = StrategistAgent(
            anthropic_client=self.client,
            model=self.model,
        )
        self.gate = ConsensusGate(
            tau_analyst=float(CONFIG.get("gate_tau_analyst", 0.55)),
            tau_strategist=float(CONFIG.get("gate_tau_strategist", 0.55)),
            tau_combined=float(CONFIG.get("gate_tau_combined", 0.58)),
            delta_divergence=float(CONFIG.get("gate_delta_divergence", 0.20)),
            delta_hard=float(CONFIG.get("gate_delta_hard", 0.35)),
        )

        # Interval for live data fetching
        self.interval = CONFIG.get("interval", "5m")

        logger.info(
            "[Orchestrator] Initialized | Gate config: %s",
            self.gate.get_config()
        )

    # ── Public Interface (drop-in for TradingAgent.decide_trade) ─────────────

    def decide_trade(self, assets: list[str], context: str) -> dict:
        """
        Main entry point. Called by main.py every trading loop iteration.

        Args:
            assets:  List of asset symbols to evaluate
            context: JSON string with full market context from main.py

        Returns:
            Dict with "reasoning" and "trade_decisions" keys —
            identical schema to the original TradingAgent output.
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    result = pool.submit(
                        asyncio.run,
                        self._decide_async(assets, context)
                    ).result(timeout=120)
            else:
                result = asyncio.run(self._decide_async(assets, context))
            return result
        except Exception as e:
            logger.error("[Orchestrator] decide_trade failed: %s", e)
            return self._fallback_hold(assets, str(e))

    # ── Async Pipeline ────────────────────────────────────────────────────────

    async def _decide_async(self, assets: list[str], context: str) -> dict:
        """
        Full async multi-agent pipeline.
        Processes all assets concurrently for efficiency.
        """
        start = time.monotonic()

        # Parse context for current prices (passed from main.py)
        try:
            ctx = json.loads(context)
            market_data = {
                m["asset"]: m
                for m in ctx.get("market_data", [])
                if "asset" in m
            }
        except Exception:
            market_data = {}

        # Process all assets concurrently
        tasks = [
            self._process_asset(asset, market_data.get(asset, {}))
            for asset in assets
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        decisions = []
        reasoning_parts = []

        for asset, result in zip(assets, results):
            if isinstance(result, Exception):
                logger.error("[Orchestrator] Asset %s failed: %s", asset, result)
                decisions.append(self._hold_decision(asset, str(result)))
                continue

            decision, reasoning = result
            decisions.append(decision)
            if reasoning:
                reasoning_parts.append(f"[{asset}] {reasoning}")

        elapsed = int((time.monotonic() - start) * 1000)
        logger.info(
            "[Orchestrator] Processed %d assets in %dms",
            len(assets), elapsed
        )

        reasoning_summary = (
            f"APEE Multi-Agent Pipeline | {len(assets)} assets | {elapsed}ms\n\n" +
            "\n\n".join(reasoning_parts)
        )

        return {
            "reasoning":       reasoning_summary,
            "trade_decisions": decisions,
        }

    async def _process_asset(
        self,
        asset: str,
        market_ctx: dict,
    ) -> tuple[dict, str]:
        """
        Full pipeline for a single asset:
        Scout → [Analyst ∥ Strategist] → Gate → decision
        """
        # Step 1: Scout — fetch 5m candles (live stream)
        config_5m = SourceConfig(
            source_id="hyperliquid",
            asset=asset,
            data_type=DataType.OHLCV,
            mode=IngestionMode.STREAM,
            interval=self.interval,
            limit=100,
        )
        config_4h = SourceConfig(
            source_id="hyperliquid",
            asset=asset,
            data_type=DataType.OHLCV,
            mode=IngestionMode.STREAM,
            interval="4h",
            limit=100,
        )

        packet_5m, packet_4h = await asyncio.gather(
            self.scout.fetch(config_5m),
            self.scout.fetch(config_4h),
        )

        # Step 2: Analyst — fast inference on 5m data
        analyst_signal = self.analyst.analyze(packet_5m)

        # Step 3: Strategist — deep structural analysis on 4h data
        # Run in thread pool to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        strategist_signal = await loop.run_in_executor(
            None,
            lambda: self.strategist.analyze(packet_4h)
        )

        # Step 4: Consensus Gate
        gate_result = self.gate.evaluate(analyst_signal, strategist_signal)

        # Step 5: Build trade decision
        current_price = float(market_ctx.get("current_price", 0))
        decision = self._build_decision(asset, gate_result, current_price)

        # Step 6: Build reasoning string
        reasoning = (
            f"Analyst: {analyst_signal.direction}@{analyst_signal.confidence:.2f} "
            f"({analyst_signal.model_id}) | "
            f"Strategist: {strategist_signal.structural_bias}@{strategist_signal.confidence:.2f} "
            f"({strategist_signal.regime}) | "
            f"Gate: {gate_result.decision.value} | "
            f"{gate_result.reason}"
        )

        return decision, reasoning

    # ── Decision Builder ──────────────────────────────────────────────────────

    def _build_decision(
        self,
        asset: str,
        gate_result,
        current_price: float,
    ) -> dict:
        """
        Convert a ConsensusResult into the trade decision schema
        expected by main.py's execution loop.
        """
        if gate_result.decision != GateDecision.EXECUTE:
            return self._hold_decision(asset, gate_result.reason)

        action = "buy" if gate_result.action == "long" else "sell"
        is_buy = action == "buy"

        # Confidence-scaled allocation — higher confidence = larger position
        # Base allocation: 50 USD. Scaled by combined confidence.
        # Risk manager in main.py will cap this to MAX_POSITION_PCT anyway.
        base_alloc = float(CONFIG.get("base_allocation_usd", 50))
        allocation = base_alloc * gate_result.combined_confidence * 2

        # TP/SL based on ATR from Strategist context
        tp_price = None
        sl_price = None
        if current_price > 0:
            atr_estimate = current_price * 0.02  # 2% default if ATR unavailable
            if is_buy:
                tp_price = round(current_price + atr_estimate * 2, 4)
                sl_price = round(current_price - atr_estimate * 1, 4)
            else:
                tp_price = round(current_price - atr_estimate * 2, 4)
                sl_price = round(current_price + atr_estimate * 1, 4)

        strategist = gate_result.strategist_signal
        exit_plan = (
            f"APEE consensus exit: reverse if gate flips to HOLD or REVIEW. "
            f"Regime: {strategist.regime if strategist else 'unknown'}. "
            f"Combined confidence: {gate_result.combined_confidence:.2f}. "
            f"{strategist.rationale[:200] if strategist else ''}"
        )

        return {
            "asset":          asset,
            "action":         action,
            "allocation_usd": round(allocation, 2),
            "order_type":     "market",
            "limit_price":    None,
            "tp_price":       tp_price,
            "sl_price":       sl_price,
            "exit_plan":      exit_plan,
            "rationale": (
                f"APEE Gate: {gate_result.decision.value} | "
                f"conf={gate_result.combined_confidence:.2f} | "
                f"agreement={gate_result.agreement_score:.2f} | "
                f"divergence={gate_result.divergence:.2f}"
            ),
            "_apee_meta": {
                "gate_decision":           gate_result.decision.value,
                "combined_confidence":     gate_result.combined_confidence,
                "analyst_confidence":      gate_result.analyst_confidence,
                "strategist_confidence":   gate_result.strategist_confidence,
                "agreement_score":         gate_result.agreement_score,
                "divergence":              gate_result.divergence,
            }
        }

    def _hold_decision(self, asset: str, reason: str) -> dict:
        return {
            "asset":          asset,
            "action":         "hold",
            "allocation_usd": 0.0,
            "order_type":     "market",
            "limit_price":    None,
            "tp_price":       None,
            "sl_price":       None,
            "exit_plan":      "",
            "rationale":      reason,
        }

    def _fallback_hold(self, assets: list[str], error: str) -> dict:
        return {
            "reasoning":       f"Orchestrator error: {error}",
            "trade_decisions": [
                self._hold_decision(a, f"Orchestrator error: {error}")
                for a in assets
            ],
        }
