"""
APEE — Agent 1: Data Scout
===========================
Fetches all market data via MCP Hub.
Outputs normalized DataPackets to other agents.
"""

import logging
from src.mcp.hub_trading import MCPHub

logger = logging.getLogger(__name__)


class DataScout:
    """
    The Scout: pure data ingestion via MCP.
    No analysis. No opinions. Just data.
    """

    def __init__(self, mcp: MCPHub):
        self.mcp = mcp

    def fetch_all(self, asset: str) -> dict:
        """
        Fetch complete market context for one asset.
        Returns all data needed by Quant + Visionary.
        """
        logger.info("[Scout] Fetching data for %s", asset)

        candles_15m = self.mcp.request("candles", asset, interval="15m", limit=100)
        candles_4h  = self.mcp.request("candles", asset, interval="4h",  limit=100)
        price       = self.mcp.request("price",   asset)
        orderbook   = self.mcp.request("orderbook", asset)
        news        = self.mcp.request("news",    asset)

        failed = [k for k, v in {
            "candles_15m": candles_15m,
            "candles_4h":  candles_4h,
            "price":       price,
        }.items() if v["status"] == "FAILED"]

        if failed:
            logger.warning("[Scout] Failed fetches for %s: %s", asset, failed)

        return {
            "asset":       asset,
            "candles_15m": candles_15m,
            "candles_4h":  candles_4h,
            "price":       price,
            "orderbook":   orderbook,
            "news":        news,
            "status":      "PARTIAL" if failed else "OK",
        }

    def fetch(self, asset: str) -> dict:
        """Alias for fetch_all — matches test interface."""
        return self.fetch_all(asset)

    def fetch_many(self, assets: list) -> dict:
        """Fetch context for multiple assets. Returns {asset: report}."""
        return {asset: self.fetch_all(asset) for asset in assets}
