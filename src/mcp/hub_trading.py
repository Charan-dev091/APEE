"""
APEE — MCP Hub
==============
Model Context Protocol router.
Uses yfinance for all data — stocks AND crypto.
No API key needed. No geo-restrictions. No rate limits.
"""

import logging
import time
import requests
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Crypto symbol mapping for yfinance
CRYPTO_MAP = {
    "BTC": "BTC-USD", "ETH": "ETH-USD", "SOL": "SOL-USD",
    "BNB": "BNB-USD", "XRP": "XRP-USD", "ADA": "ADA-USD",
    "AVAX": "AVAX-USD", "DOT": "DOT-USD", "MATIC": "MATIC-USD",
}

# Interval mapping
INTERVAL_MAP = {
    "1m": "1m", "5m": "5m", "15m": "15m",
    "30m": "30m", "1h": "60m", "4h": "1h",
    "1d": "1d",
}

# Period mapping for interval
PERIOD_MAP = {
    "1m": "1d", "5m": "5d", "15m": "5d",
    "30m": "1mo", "60m": "1mo", "1h": "1mo",
    "1d": "2y",
}


class MCPHub:
    """
    Central data router using yfinance.
    Works for all US stocks and crypto.
    No API key. No geo-restrictions.
    """

    def request(self, data_type: str, asset: str, **kwargs) -> dict:
        """Main interface. Routes all requests through yfinance."""
        start = time.monotonic()
        try:
            if data_type == "price":
                payload, data_range = self._get_price(asset)
            elif data_type == "candles":
                payload, data_range = self._get_candles(asset, **kwargs)
            elif data_type == "orderbook":
                payload, data_range = {"bids": [], "asks": []}, ("", "")
            elif data_type == "news":
                payload, data_range = {"headlines": []}, ("", "")
            else:
                return self._packet(asset, data_type, None, "FAILED",
                                    f"Unknown: {data_type}")

            latency = int((time.monotonic() - start) * 1000)
            return self._packet(asset, data_type, payload, "OK",
                                None, data_range, latency, "yfinance")

        except Exception as e:
            latency = int((time.monotonic() - start) * 1000)
            logger.error("[MCP] %s/%s failed: %s", data_type, asset, e)
            return self._packet(asset, data_type, None, "FAILED", str(e))

    def _yf_symbol(self, asset: str) -> str:
        """Convert asset name to yfinance symbol."""
        return CRYPTO_MAP.get(asset.upper(), asset.upper())

    def _get_price(self, asset: str) -> tuple:
        """Get current price via yfinance."""
        try:
            import yfinance as yf
        except ImportError:
            raise ImportError("Run: pip install yfinance")

        symbol = self._yf_symbol(asset)
        ticker = yf.Ticker(symbol)
        info   = ticker.fast_info

        # Try multiple price fields
        price = (
            getattr(info, "last_price", None) or
            getattr(info, "regular_market_price", None) or
            getattr(info, "previous_close", None)
        )

        if not price or price <= 0:
            # Fallback: get from recent history
            hist = ticker.history(period="1d", interval="1m")
            if hist.empty:
                raise ValueError(f"No price data for {symbol}")
            price = float(hist["Close"].iloc[-1])

        return {"price": float(price), "asset": asset}, ("now", "now")

    def _get_candles(self, asset: str, interval="15m", limit=100, **kwargs) -> tuple:
        """Get OHLCV candles via yfinance."""
        try:
            import yfinance as yf
        except ImportError:
            raise ImportError("Run: pip install yfinance")

        symbol   = self._yf_symbol(asset)
        yf_int   = INTERVAL_MAP.get(interval, "15m")
        period   = PERIOD_MAP.get(yf_int, "5d")

        ticker = yf.Ticker(symbol)
        hist   = ticker.history(period=period, interval=yf_int)

        if hist.empty:
            raise ValueError(f"No candle data for {symbol}")

        # Take last `limit` bars
        hist = hist.tail(limit)

        candles = [
            {
                "time":   str(idx),
                "open":   float(row["Open"]),
                "high":   float(row["High"]),
                "low":    float(row["Low"]),
                "close":  float(row["Close"]),
                "volume": float(row["Volume"]),
            }
            for idx, row in hist.iterrows()
        ]

        start = candles[0]["time"]  if candles else ""
        end   = candles[-1]["time"] if candles else ""
        return candles, (start, end)

    def _packet(self, asset, data_type, payload, status,
                error=None, data_range=("",""), latency=0, source="yfinance"):
        return {
            "asset":      asset,
            "data_type":  data_type,
            "payload":    payload,
            "status":     status,
            "error":      error,
            "source":     source,
            "data_range": data_range,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "latency_ms": latency,
        }
