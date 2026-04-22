"""
APEE — Agent 1: The Scout
=========================
Domain-agnostic data ingestion layer.

Single responsibility: fetch data from any configured source and
deliver a raw, timestamped, source-attributed DataPacket to the
Orchestrator. The Scout has no opinion about what the data means.

Modes:
  BATCH  — historical pull (2010 → present) for model training
  STREAM — live continuous feed for inference

Both modes produce identical DataPacket output schema, ensuring
downstream agent independence from ingestion mode.

Formal definition:
  S: (SourceConfig, t) → DataPacket
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# ── Enumerations ──────────────────────────────────────────────────────────────

class DataType(str, Enum):
    OHLCV       = "OHLCV"
    NEWS        = "NEWS"
    ORDER_BOOK  = "ORDER_BOOK"
    SEC_FILING  = "SEC_FILING"
    SENTIMENT   = "SENTIMENT"
    FUNDING     = "FUNDING"
    OPEN_INT    = "OPEN_INTEREST"


class IngestionMode(str, Enum):
    BATCH  = "BATCH"
    STREAM = "STREAM"


class PacketStatus(str, Enum):
    OK      = "OK"
    PARTIAL = "PARTIAL"
    FAILED  = "FAILED"


# ── Data Contracts ────────────────────────────────────────────────────────────

@dataclass
class SourceConfig:
    """
    Plugin configuration object. Swap this to point the Scout
    at any data source without changing downstream agent logic.
    """
    source_id:      str               # e.g. "hyperliquid", "yfinance", "sec_edgar"
    asset:          str               # e.g. "BTC", "NVDA", "CIK_0001045810"
    data_type:      DataType
    mode:           IngestionMode
    interval:       str = "1d"        # "1m", "5m", "1h", "4h", "1d"
    start:          str | None = None # ISO date string, BATCH mode
    end:            str | None = None # ISO date string, BATCH mode
    limit:          int = 100         # number of candles for STREAM mode
    backup_source:  str | None = None # fallback source_id on failure
    auth:           dict = field(default_factory=dict)  # injected at runtime, never stored


@dataclass
class DataPacket:
    """
    Standardised output from the Scout regardless of source or mode.
    The Orchestrator reads status + staleness_flag to decide
    how to handle failures — the Scout never makes that call itself.
    """
    packet_id:          str
    source_id:          str
    asset:              str
    data_type:          DataType
    mode:               IngestionMode
    fetched_at:         str           # ISO timestamp of fetch
    data_range:         tuple         # (start, end) as ISO strings
    payload:            Any           # raw untouched source data
    staleness_flag:     bool = False  # True if backup source was used
    source_latency_ms:  int  = 0
    status:             PacketStatus = PacketStatus.OK
    error:              str | None = None


# ── Scout Agent ───────────────────────────────────────────────────────────────

class ScoutAgent:
    """
    The Scout: stateless data ingestion agent.

    Registered data source plugins:
      - hyperliquid : OHLCV + order book + funding via Hyperliquid SDK
      - yfinance    : OHLCV for US stocks (batch, 2010→present)
      - coingecko   : BTC/USD back to 2010 (batch)
      - ccxt        : Crypto OHLCV via Binance (batch, 2017→present)

    Plugins are registered via register_plugin(). Adding a new domain
    (real estate, forex, commodities) requires only a new plugin function
    — no changes to the Scout's core logic.
    """

    def __init__(self, hyperliquid_api=None):
        self._hl = hyperliquid_api
        self._plugins: dict[str, callable] = {}
        self._register_default_plugins()

    # ── Plugin Registration ───────────────────────────────────────────────────

    def register_plugin(self, source_id: str, handler: callable) -> None:
        """Register a new data source plugin. handler(config) → raw data."""
        self._plugins[source_id] = handler
        logger.info("[Scout] Registered plugin: %s", source_id)

    def _register_default_plugins(self) -> None:
        """Wire up built-in plugins."""
        self._plugins["hyperliquid"] = self._fetch_hyperliquid
        self._plugins["yfinance"]    = self._fetch_yfinance
        self._plugins["coingecko"]   = self._fetch_coingecko_btc
        self._plugins["ccxt"]        = self._fetch_ccxt

    # ── Primary Interface ─────────────────────────────────────────────────────

    async def fetch(self, config: SourceConfig) -> DataPacket:
        """
        Main entry point. Fetches data according to config,
        falls back to backup_source on failure, reports status
        to Orchestrator via DataPacket.
        """
        start_ms = time.monotonic()
        packet_id = str(uuid.uuid4())

        try:
            raw, data_range = await self._dispatch(config)
            latency = int((time.monotonic() - start_ms) * 1000)

            return DataPacket(
                packet_id=packet_id,
                source_id=config.source_id,
                asset=config.asset,
                data_type=config.data_type,
                mode=config.mode,
                fetched_at=datetime.now(timezone.utc).isoformat(),
                data_range=data_range,
                payload=raw,
                source_latency_ms=latency,
                status=PacketStatus.OK,
            )

        except Exception as primary_err:
            logger.warning(
                "[Scout] Primary source '%s' failed for %s: %s",
                config.source_id, config.asset, primary_err
            )

            # Try backup source if configured
            if config.backup_source and config.backup_source in self._plugins:
                try:
                    backup_config = SourceConfig(
                        source_id=config.backup_source,
                        asset=config.asset,
                        data_type=config.data_type,
                        mode=config.mode,
                        interval=config.interval,
                        start=config.start,
                        end=config.end,
                        limit=config.limit,
                        auth=config.auth,
                    )
                    raw, data_range = await self._dispatch(backup_config)
                    latency = int((time.monotonic() - start_ms) * 1000)

                    logger.info(
                        "[Scout] Backup source '%s' succeeded for %s",
                        config.backup_source, config.asset
                    )
                    return DataPacket(
                        packet_id=packet_id,
                        source_id=config.backup_source,
                        asset=config.asset,
                        data_type=config.data_type,
                        mode=config.mode,
                        fetched_at=datetime.now(timezone.utc).isoformat(),
                        data_range=data_range,
                        payload=raw,
                        staleness_flag=True,  # Signal to Orchestrator
                        source_latency_ms=latency,
                        status=PacketStatus.PARTIAL,
                    )

                except Exception as backup_err:
                    logger.error(
                        "[Scout] Backup source '%s' also failed for %s: %s",
                        config.backup_source, config.asset, backup_err
                    )

            # Both sources failed — report FAILED, let Orchestrator decide
            latency = int((time.monotonic() - start_ms) * 1000)
            return DataPacket(
                packet_id=packet_id,
                source_id=config.source_id,
                asset=config.asset,
                data_type=config.data_type,
                mode=config.mode,
                fetched_at=datetime.now(timezone.utc).isoformat(),
                data_range=("", ""),
                payload=None,
                source_latency_ms=latency,
                status=PacketStatus.FAILED,
                error=str(primary_err),
            )

    async def fetch_many(self, configs: list[SourceConfig]) -> list[DataPacket]:
        """Fetch multiple sources concurrently."""
        tasks = [self.fetch(cfg) for cfg in configs]
        return await asyncio.gather(*tasks, return_exceptions=False)

    # ── Plugin Dispatch ───────────────────────────────────────────────────────

    async def _dispatch(self, config: SourceConfig) -> tuple[Any, tuple]:
        """Route to the correct plugin handler."""
        handler = self._plugins.get(config.source_id)
        if not handler:
            raise ValueError(f"No plugin registered for source: '{config.source_id}'")

        if asyncio.iscoroutinefunction(handler):
            return await handler(config)
        else:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, handler, config)

    # ── Plugin: Hyperliquid (primary for live trading) ────────────────────────

    async def _fetch_hyperliquid(self, config: SourceConfig) -> tuple[Any, tuple]:
        """
        Fetch OHLCV candles from Hyperliquid via the existing SDK.
        This is the primary live-stream source for the APEE PoC.
        """
        if self._hl is None:
            raise RuntimeError("HyperliquidAPI not injected into Scout")

        if config.data_type == DataType.OHLCV:
            candles = await self._hl.get_candles(
                config.asset,
                config.interval,
                config.limit,
            )
            if not candles:
                raise ValueError(f"No candles returned for {config.asset}")

            start = candles[0].get("time", "") if candles else ""
            end   = candles[-1].get("time", "") if candles else ""
            return candles, (str(start), str(end))

        elif config.data_type == DataType.FUNDING:
            funding = await self._hl.get_funding_rate(config.asset)
            return {"funding_rate": funding}, ("", "")

        elif config.data_type == DataType.OPEN_INT:
            oi = await self._hl.get_open_interest(config.asset)
            return {"open_interest": oi}, ("", "")

        else:
            raise ValueError(
                f"Hyperliquid plugin does not support data_type: {config.data_type}"
            )

    # ── Plugin: yfinance (US stocks, batch, 2010→present) ────────────────────

    def _fetch_yfinance(self, config: SourceConfig) -> tuple[Any, tuple]:
        """
        Fetch historical US stock OHLCV via yfinance.
        Batch mode only. Data available from 2010 → present.
        """
        try:
            import yfinance as yf
        except ImportError:
            raise ImportError("yfinance not installed. Run: pip install yfinance")

        ticker = yf.Ticker(config.asset)
        df = ticker.history(
            start=config.start or "2010-01-01",
            end=config.end,
            interval=config.interval,
            auto_adjust=True,
        )

        if df.empty:
            raise ValueError(f"yfinance returned empty DataFrame for {config.asset}")

        records = df.reset_index().to_dict(orient="records")
        start_date = str(df.index[0].date())
        end_date   = str(df.index[-1].date())
        return records, (start_date, end_date)

    # ── Plugin: CoinGecko (BTC back to 2010) ─────────────────────────────────

    def _fetch_coingecko_btc(self, config: SourceConfig) -> tuple[Any, tuple]:
        """
        Fetch BTC/USD historical data back to 2010 from CoinGecko.
        The only public source with true 2010 Bitcoin data.
        """
        try:
            import requests
        except ImportError:
            raise ImportError("requests not installed. Run: pip install requests")

        url = "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart"
        params = {
            "vs_currency": "usd",
            "days": "max",
            "interval": "daily",
        }
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        prices  = data.get("prices", [])
        volumes = data.get("total_volumes", [])

        if not prices:
            raise ValueError("CoinGecko returned empty price data")

        records = [
            {
                "timestamp": p[0],
                "close":     p[1],
                "volume":    volumes[i][1] if i < len(volumes) else 0,
                "open":      p[1],
                "high":      p[1],
                "low":       p[1],
            }
            for i, p in enumerate(prices)
        ]

        start_ts = datetime.fromtimestamp(prices[0][0] / 1000).strftime("%Y-%m-%d")
        end_ts   = datetime.fromtimestamp(prices[-1][0] / 1000).strftime("%Y-%m-%d")
        return records, (start_ts, end_ts)

    # ── Plugin: ccxt (Crypto via Binance, 2017→present) ──────────────────────

    def _fetch_ccxt(self, config: SourceConfig) -> tuple[Any, tuple]:
        """
        Fetch crypto OHLCV via ccxt/Binance.
        Supports all major pairs. Data from 2017 → present.
        """
        try:
            import ccxt
        except ImportError:
            raise ImportError("ccxt not installed. Run: pip install ccxt")

        exchange = ccxt.binance({"enableRateLimit": True})
        since_ms = None
        if config.start:
            import pandas as pd
            since_ms = int(pd.Timestamp(config.start).timestamp() * 1000)

        # Map interval format if needed (yfinance uses "1d", ccxt uses "1d" too)
        ohlcv = exchange.fetch_ohlcv(
            config.asset,
            timeframe=config.interval,
            since=since_ms,
            limit=config.limit,
        )

        if not ohlcv:
            raise ValueError(f"ccxt/Binance returned no data for {config.asset}")

        records = [
            {
                "timestamp": row[0],
                "open":      row[1],
                "high":      row[2],
                "low":       row[3],
                "close":     row[4],
                "volume":    row[5],
            }
            for row in ohlcv
        ]

        from datetime import datetime
        start_ts = datetime.fromtimestamp(ohlcv[0][0] / 1000).strftime("%Y-%m-%d")
        end_ts   = datetime.fromtimestamp(ohlcv[-1][0] / 1000).strftime("%Y-%m-%d")
        return records, (start_ts, end_ts)


# ── Convenience Factory ────────────────────────────────────────────────────────

def make_live_configs(assets: list[str], interval: str = "5m") -> list[SourceConfig]:
    """
    Build standard SourceConfig objects for live OHLCV ingestion
    across a list of Hyperliquid assets. Used by the Orchestrator
    at the start of each trading loop iteration.
    """
    return [
        SourceConfig(
            source_id="hyperliquid",
            asset=asset,
            data_type=DataType.OHLCV,
            mode=IngestionMode.STREAM,
            interval=interval,
            limit=100,
            backup_source=None,
        )
        for asset in assets
    ]


def make_batch_configs(
    assets: list[str],
    start: str = "2010-01-01",
    end: str | None = None,
    source: str = "yfinance",
) -> list[SourceConfig]:
    """
    Build SourceConfig objects for historical batch ingestion.
    Used by the data pipeline for model training.
    """
    return [
        SourceConfig(
            source_id=source,
            asset=asset,
            data_type=DataType.OHLCV,
            mode=IngestionMode.BATCH,
            interval="1d",
            start=start,
            end=end,
            backup_source="yfinance" if source != "yfinance" else None,
        )
        for asset in assets
    ]
