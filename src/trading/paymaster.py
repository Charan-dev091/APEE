"""
APEE — Paymaster (Trading)
===========================
Portfolio manager and trade executor for the trading pipeline.
Tracks positions, computes P&L, and executes approved mandates.

Called only after all 6 biometric conditions pass.
No trade is executed without a fully approved mandate.
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class Paymaster:
    """
    Simulated trade executor and portfolio tracker.
    In production: replace execute() with broker API calls
    (Alpaca, IBKR, Coinbase, etc.)
    """

    def __init__(self, initial_balance: float = 10_000.0):
        self.initial_balance = initial_balance
        self.balance         = initial_balance
        self.positions: dict = {}   # asset → {shares, alloc_usd, avg_price, direction}
        self.trade_log: list = []
        self.daily_pnl       = 0.0

    # ── Portfolio Snapshot ─────────────────────────────────────────────────────

    def get_portfolio(self, current_prices: dict) -> dict:
        """
        Compute current portfolio value using live prices.
        Returns a snapshot dict consumed by Auditor + Dashboard.
        """
        position_value = 0.0
        positions_snap = {}

        for asset, pos in self.positions.items():
            price = current_prices.get(asset, pos["avg_price"])
            value = pos["shares"] * price
            pnl   = value - pos["alloc_usd"]
            pnl_pct = (pnl / pos["alloc_usd"] * 100) if pos["alloc_usd"] else 0.0
            position_value += value
            positions_snap[asset] = {
                "shares":        round(pos["shares"], 6),
                "avg_price":     round(pos["avg_price"], 4),
                "current_price": round(price, 4),
                "alloc_usd":     round(pos["alloc_usd"], 2),
                "value":         round(value, 2),
                "pnl":           round(pnl, 2),
                "pnl_pct":       round(pnl_pct, 2),
                "direction":     pos["direction"],
            }

        total_value   = self.balance + position_value
        total_return  = total_value - self.initial_balance
        total_ret_pct = (total_return / self.initial_balance * 100) if self.initial_balance else 0.0

        return {
            "balance":          round(self.balance, 2),
            "position_value":   round(position_value, 2),
            "total_value":      round(total_value, 2),
            "total_return":     round(total_return, 2),
            "total_return_pct": round(total_ret_pct, 2),
            "positions":        positions_snap,
            "trade_count":      len(self.trade_log),
            "timestamp":        datetime.now(timezone.utc).isoformat(),
        }

    # ── Trade Execution ────────────────────────────────────────────────────────

    def execute(self, approved_mandate: dict, current_price: float) -> dict:
        """
        Execute a fully approved mandate.
        Returns a trade receipt — status "filled" on success.
        """
        asset     = approved_mandate.get("asset", "")
        action    = approved_mandate.get("action", "")
        alloc_usd = float(approved_mandate.get("alloc_usd", 0))

        if not asset or not action or alloc_usd <= 0:
            return self._receipt(asset, action, alloc_usd, current_price,
                                 "rejected", "Invalid mandate parameters")

        if action in ("long", "buy"):
            return self._open_long(asset, alloc_usd, current_price, approved_mandate)
        elif action in ("short", "sell"):
            return self._close_position(asset, current_price, approved_mandate)
        else:
            return self._receipt(asset, action, alloc_usd, current_price,
                                 "rejected", f"Unknown action: {action}")

    def _open_long(self, asset, alloc_usd, price, mandate):
        if alloc_usd > self.balance:
            alloc_usd = self.balance * 0.95

        if alloc_usd < 1.0:
            return self._receipt(asset, "long", alloc_usd, price,
                                 "rejected", "Insufficient balance")

        shares = alloc_usd / price

        if asset in self.positions:
            pos = self.positions[asset]
            total_cost   = pos["alloc_usd"] + alloc_usd
            total_shares = pos["shares"] + shares
            pos["avg_price"] = total_cost / total_shares
            pos["shares"]    = total_shares
            pos["alloc_usd"] = total_cost
        else:
            self.positions[asset] = {
                "shares":    shares,
                "avg_price": price,
                "alloc_usd": alloc_usd,
                "direction": "long",
                "opened_at": datetime.now(timezone.utc).isoformat(),
            }

        self.balance -= alloc_usd
        receipt = self._receipt(asset, "long", alloc_usd, price, "filled",
                                f"Bought {shares:.6f} shares @ ${price:.2f}")
        self.trade_log.append(receipt)
        logger.info("[Paymaster] BUY %s — %.6f shares @ $%.2f | balance: $%.2f",
                    asset, shares, price, self.balance)
        return receipt

    def _close_position(self, asset, price, mandate):
        if asset not in self.positions:
            alloc_usd = float(mandate.get("alloc_usd", 0))
            shares    = alloc_usd / price if price else 0
            receipt   = self._receipt(asset, "short", alloc_usd, price, "filled",
                                      f"Short {shares:.6f} shares @ ${price:.2f}")
            self.trade_log.append(receipt)
            return receipt

        pos      = self.positions.pop(asset)
        proceeds = pos["shares"] * price
        pnl      = proceeds - pos["alloc_usd"]
        self.balance   += proceeds
        self.daily_pnl += pnl

        receipt = self._receipt(asset, "short", proceeds, price, "filled",
                                f"Sold {pos['shares']:.6f} @ ${price:.2f} | P&L: ${pnl:+.2f}")
        self.trade_log.append(receipt)
        logger.info("[Paymaster] SELL %s — P&L $%.2f | balance: $%.2f",
                    asset, pnl, self.balance)
        return receipt

    def _receipt(self, asset, action, alloc_usd, price, status, message):
        return {
            "asset":     asset,
            "action":    action,
            "alloc_usd": round(alloc_usd, 2),
            "price":     round(price, 4),
            "status":    status,
            "message":   message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
