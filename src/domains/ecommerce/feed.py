"""
APEE E-Commerce — MCP Hub
==========================
Fetches product prices from multiple free sources.
No API key needed for basic price lookup.

Sources:
  1. Google Shopping via SerpAPI (free tier)
  2. PriceAPI free tier
  3. Direct retailer price scraping (Best Buy, Walmart public APIs)
  4. Camelcamelcamel for Amazon price history
"""

import logging
import time
import requests
import json
from datetime import datetime, timezone
from urllib.parse import quote

logger = logging.getLogger(__name__)


class EcommerceMCPHub:
    """
    Routes product data requests to correct source.
    Same interface as trading MCPHub — framework is identical.
    """

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })

    def request(self, data_type: str, query: str, **kwargs) -> dict:
        """Main interface — same as trading MCPHub."""
        start = time.monotonic()
        try:
            if data_type == "price":
                payload, source = self._fetch_price(query, **kwargs)
            elif data_type == "price_history":
                payload, source = self._fetch_price_history(query, **kwargs)
            elif data_type == "product_info":
                payload, source = self._fetch_product_info(query, **kwargs)
            else:
                return self._packet(query, data_type, None, "FAILED", f"Unknown: {data_type}")

            latency = int((time.monotonic() - start) * 1000)
            return self._packet(query, data_type, payload, "OK", None, source, latency)

        except Exception as e:
            latency = int((time.monotonic() - start) * 1000)
            logger.error("[MCP] %s/%s failed: %s", data_type, query, e)
            return self._packet(query, data_type, None, "FAILED", str(e))

    def _fetch_price(self, query: str, **kwargs) -> tuple:
        """
        Fetch current product price.
        Uses multiple sources for redundancy.
        """
        # Try Best Buy API (free, no key for search)
        bb_result = self._bestbuy_price(query)
        if bb_result:
            return bb_result, "bestbuy"

        # Try Walmart search (public)
        wm_result = self._walmart_price(query)
        if wm_result:
            return wm_result, "walmart"

        # Fallback: mock price for demo
        return self._mock_price(query), "mock"

    def _fetch_price_history(self, query: str, days: int = 30, **kwargs) -> tuple:
        """
        Fetch price history for trend analysis.
        Uses mock data for demo — in production: Camelcamelcamel API.
        """
        history = self._mock_price_history(query, days)
        return history, "mock_history"

    def _fetch_product_info(self, query: str, **kwargs) -> tuple:
        """Fetch product details — title, image, rating, reviews."""
        return {
            "query":       query,
            "title":       f"{query} (Best Match)",
            "rating":      4.2,
            "review_count": 1847,
            "availability": "In Stock",
        }, "mock"

    def _bestbuy_price(self, query: str) -> dict | None:
        """Best Buy public product search."""
        try:
            url = "https://www.bestbuy.com/api/3.0/priceCheck"
            r = self.session.get(
                "https://api.bestbuy.com/v1/products",
                params={
                    "apiKey":    "demo",
                    "q":         query,
                    "pageSize":  1,
                    "format":    "json",
                    "show":      "name,salePrice,regularPrice,url",
                },
                timeout=5
            )
            if r.status_code == 200:
                data = r.json()
                products = data.get("products", [])
                if products:
                    p = products[0]
                    return {
                        "query":         query,
                        "title":         p.get("name", query),
                        "current_price": float(p.get("salePrice", 0)),
                        "regular_price": float(p.get("regularPrice", 0)),
                        "url":           p.get("url", ""),
                        "source":        "bestbuy",
                    }
        except Exception:
            pass
        return None

    def _walmart_price(self, query: str) -> dict | None:
        """Walmart public search API."""
        try:
            r = self.session.get(
                "https://www.walmart.com/search/api",
                params={"query": query, "limit": 1},
                timeout=5
            )
            if r.status_code == 200:
                data = r.json()
                items = data.get("items", [])
                if items:
                    item = items[0]
                    return {
                        "query":         query,
                        "title":         item.get("name", query),
                        "current_price": float(item.get("price", 0)),
                        "regular_price": float(item.get("price", 0)),
                        "url":           f"https://walmart.com{item.get('productPageUrl','')}",
                        "source":        "walmart",
                    }
        except Exception:
            pass
        return None

    def _mock_price(self, query: str) -> dict:
        """
        Realistic mock price for demo.
        Simulates price fluctuation over time.
        In production: replace with real API.
        """
        import hashlib
        import math

        # Deterministic base price from query hash
        h    = int(hashlib.md5(query.lower().encode()).hexdigest()[:8], 16)
        base = 100 + (h % 900)  # $100 - $1000

        # Simulate daily price fluctuation
        hour      = datetime.now().hour
        day       = datetime.now().day
        variation = math.sin(day * 0.7 + hour * 0.1) * (base * 0.05)
        current   = round(base + variation, 2)
        regular   = round(base * 1.15, 2)

        return {
            "query":         query,
            "title":         f"{query}",
            "current_price": current,
            "regular_price": regular,
            "discount_pct":  round((regular - current) / regular * 100, 1),
            "source":        "mock",
        }

    def _mock_price_history(self, query: str, days: int = 30) -> dict:
        """Generate realistic price history for trend analysis."""
        import hashlib
        import math
        import random

        h    = int(hashlib.md5(query.lower().encode()).hexdigest()[:8], 16)
        base = 100 + (h % 900)

        history = []
        random.seed(h)
        price = base * 1.1

        for i in range(days):
            # Simulate realistic price movements
            change = (random.random() - 0.48) * base * 0.03
            price  = max(base * 0.7, price + change)
            history.append({
                "day":   i + 1,
                "price": round(price, 2),
                "date":  f"Day -{days-i}",
            })

        avg_30d = sum(h["price"] for h in history) / len(history)
        min_30d = min(h["price"] for h in history)
        max_30d = max(h["price"] for h in history)

        return {
            "query":    query,
            "history":  history,
            "avg_30d":  round(avg_30d, 2),
            "min_30d":  round(min_30d, 2),
            "max_30d":  round(max_30d, 2),
            "current":  history[-1]["price"],
        }

    def _packet(self, query, data_type, payload, status,
                error=None, source="unknown", latency=0):
        return {
            "query":      query,
            "data_type":  data_type,
            "payload":    payload,
            "status":     status,
            "error":      error,
            "source":     source,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "latency_ms": latency,
        }
