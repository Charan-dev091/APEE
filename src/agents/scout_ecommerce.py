"""
APEE E-Commerce — Agent 1: Product Scout
==========================================
Same role as trading Scout — pure data ingestion.
Fetches product prices and history via MCP Hub.
No analysis. No opinions. Just data.
"""

import logging
from src.mcp.hub_ecommerce import EcommerceMCPHub

logger = logging.getLogger(__name__)


class ProductScout:
    """
    Fetches product price data for a given search query.
    Output feeds into Quant + Visionary agents.
    Identical interface to trading DataScout.
    """

    def __init__(self, mcp: EcommerceMCPHub):
        self.mcp = mcp

    def fetch_all(self, query: str) -> dict:
        """
        Fetch complete product context.
        Returns all data needed by Quant + Visionary.
        """
        logger.info("[Scout] Fetching product data for: %s", query)

        current     = self.mcp.request("price",         query)
        history     = self.mcp.request("price_history", query, days=30)
        product_info= self.mcp.request("product_info",  query)

        failed = [k for k,v in {
            "current": current, "history": history
        }.items() if v["status"] == "FAILED"]

        if failed:
            logger.warning("[Scout] Failed fetches for %s: %s", query, failed)

        return {
            "query":        query,
            "current":      current,
            "history":      history,
            "product_info": product_info,
            "status":       "PARTIAL" if failed else "OK",
        }

    def fetch(self, query: str) -> dict:
        return self.fetch_all(query)

    def fetch_many(self, queries: list) -> dict:
        return {q: self.fetch_all(q) for q in queries}
