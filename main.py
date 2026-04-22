"""
APEE — Unified Orchestrator  ★ CANONICAL ENTRY POINT ★
=======================================================
This is the primary application entry point (see START.md).
Run with:  python main.py

One application. Two modes.

  MODE=trading    → Stocks/crypto pipeline (yfinance + Groq/Llama)
  MODE=ecommerce  → Product price monitoring (SerpAPI / Best Buy / Walmart)

Mode is set via:
  1. POST /api/mode  (from chat interface on the dashboard)
  2. logs/app_config.json written by the chat UI
  3. python main.py --mode trading   (CLI shortcut)

Do NOT confuse with src/main.py which is the Hyperliquid+Claude
(advanced) variant that requires additional modules not yet
committed (risk_manager, config_loader, hyperliquid_api, etc.).
See src/main.py header for its status.

The framework components are identical across both modes.
Only the data source and execution backend differ.
"""

import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

LOG_DIR = Path(os.getenv("LOG_DIR", "./logs"))
LOG_DIR.mkdir(exist_ok=True)

# ── Framework core imports ───────────────────────────────────────────────────
from src.core.consensus_gate      import consensus_gate
from src.security.passkey         import BiometricPasskey
from src.security.mandate_manager import AsyncMandateManager
from src.security.webhook_server  import start_webhook_server
from src.alerts                   import AlertSystem
from src.router.intent_router     import IntentRouter

# ── Config ────────────────────────────────────────────────────────────────────
GROQ_API_KEY     = os.getenv("GROQ_API_KEY", "")
WS_PORT          = int(os.getenv("WS_PORT", "8765"))
WEBHOOK_PORT     = int(os.getenv("WEBHOOK_PORT", "8766"))
STOP_CHECK_SECS  = int(os.getenv("STOP_CHECK_SECS", "30"))
TAU_QUANT        = float(os.getenv("GATE_TAU_QUANT",        "0.55"))
TAU_VISIONARY    = float(os.getenv("GATE_TAU_VISIONARY",    "0.55"))
TAU_COMBINED     = float(os.getenv("GATE_TAU_COMBINED",     "0.58"))
DELTA_DIVERGENCE = float(os.getenv("GATE_DELTA_DIVERGENCE", "0.25"))
DELTA_HARD       = float(os.getenv("GATE_DELTA_HARD",       "0.35"))

# ── App State ─────────────────────────────────────────────────────────────────
APP_STATE = {
    "mode":        None,        # "trading" | "ecommerce" | None
    "status":      "chat",      # "chat" | "running" | "stopped"
    "config":      {},          # mode-specific config
    "cycle":       0,
    "pipeline":    None,        # running pipeline task
    "started_at":  None,
}


# ── WebSocket Broadcaster ─────────────────────────────────────────────────────
class WSBroadcaster:
    def __init__(self):
        self._clients = set()
        self._queue   = asyncio.Queue()

    async def handler(self, websocket):
        self._clients.add(websocket)
        try:
            await websocket.send(json.dumps({
                "type": "CONNECTED",
                "data": {"app_state": APP_STATE},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }))
            async for _ in websocket:
                pass
        except Exception:
            pass
        finally:
            self._clients.discard(websocket)

    async def broadcaster(self):
        while True:
            event = await self._queue.get()
            if not self._clients:
                continue
            msg  = json.dumps(event)
            dead = set()
            for client in self._clients.copy():
                try:
                    await client.send(msg)
                except Exception:
                    dead.add(client)
            self._clients -= dead

    def push(self, event_type: str, data: dict):
        event = {
            "type":      event_type,
            "data":      data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        try:
            self._queue.put_nowait(event)
        except Exception:
            pass
        with open(LOG_DIR / "events.jsonl", "a") as f:
            f.write(json.dumps(event) + "\n")


# ── Gate Logger ───────────────────────────────────────────────────────────────
class GateLogger:
    def __init__(self):
        self.path  = LOG_DIR / "gate_decisions.jsonl"
        self.stats = {"EXECUTE": 0, "HOLD": 0, "REVIEW": 0}

    def log(self, gate_result: dict, action: str):
        with open(self.path, "a") as f:
            f.write(json.dumps({
                **gate_result, "action_taken": action,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }) + "\n")
        self.stats[gate_result["decision"]] = \
            self.stats.get(gate_result["decision"], 0) + 1

    def summary(self):
        total = sum(self.stats.values())
        return {**self.stats, "total": total,
                "execute_rate": round(self.stats.get("EXECUTE",0)/max(total,1)*100,1)}


# ── Trading Pipeline ──────────────────────────────────────────────────────────
async def run_trading(ws: WSBroadcaster, mandate_mgr: AsyncMandateManager,
                      alerts: AlertSystem, config: dict):
    # ── POC 1: Trading domain plugin ─────────────────────────────────────────
    from src.domains.trading.feed      import MCPHub
    from src.domains.trading.scout     import DataScout
    from src.domains.trading.quant     import QuantAgent
    from src.domains.trading.visionary import VisionaryAgent
    from src.domains.trading.paymaster import Paymaster
    # ── Framework core components ────────────────────────────────────────────
    from src.core.sentiment            import SentimentAnalyzer
    from src.core.auditor              import AuditorAgent
    from src.commerce.checkout         import CommerceAgent

    groq_client = None
    if GROQ_API_KEY:
        from groq import Groq
        groq_client = Groq(api_key=GROQ_API_KEY)

    assets    = config.get("assets", ["NVDA","AAPL","TSLA"])
    interval  = config.get("interval_minutes", 5)
    balance   = config.get("initial_balance", 10000)
    max_alloc = config.get("max_alloc", 1000)
    daily_cap = config.get("daily_cap", 3000)

    mcp       = MCPHub()
    scout     = DataScout(mcp)
    quant     = QuantAgent()
    visionary = VisionaryAgent(groq_client) if groq_client else None
    sentiment = SentimentAnalyzer(groq_client) if groq_client else None
    auditor   = AuditorAgent(max_position_pct=20.0, max_total_exposure=60.0, max_positions=5)
    passkey   = BiometricPasskey(allowed_assets=assets, max_alloc_per_trade=max_alloc,
                                  daily_cap=daily_cap, auto_approve=True)
    paymaster = Paymaster(balance)
    commerce  = CommerceAgent()
    gate_log  = GateLogger()

    APP_STATE["status"] = "running"
    APP_STATE["mode"]   = "trading"

    logger.info("[Trading] Starting — assets: %s", assets)
    ws.push("MODE_STARTED", {"mode":"trading","assets":assets})

    cycle = 0
    while APP_STATE["status"] == "running":
        cycle += 1
        APP_STATE["cycle"] = cycle
        start         = time.monotonic()
        prices        = {}
        agent_signals = {}

        async def eval_asset(asset):
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, scout.fetch_all, asset)
            price_p = data.get("price",{}).get("payload",{})
            price   = price_p.get("price",0) if price_p else 0
            prices[asset] = price

            scout_conf = 1.0 if price > 0 else 0.0
            if price <= 0:
                agent_signals[asset] = {"scout": 0.0, "quant": 0.0, "visionary": 0.0,
                                        "sentiment": 0.0, "auditor": None, "gate": 0.0}
                return

            sent = await loop.run_in_executor(None, sentiment.analyze, asset, data, cycle) \
                   if sentiment else {"sentiment":"neutral","score":0.0,"confidence":0.3}
            q_sig = quant.analyze(data)
            v_sig = await loop.run_in_executor(None, visionary.analyze, data, sent, cycle) \
                    if visionary else {
                        "structural_bias": q_sig["direction"].replace("long","bullish").replace("short","bearish"),
                        "confidence": q_sig["confidence"]*0.9, "regime":"uncertain", "rationale":"disabled"
                    }
            gate = consensus_gate(q_sig, v_sig, sent,
                                  tau_quant=TAU_QUANT, tau_visionary=TAU_VISIONARY,
                                  tau_combined=TAU_COMBINED,
                                  delta_divergence=DELTA_DIVERGENCE, delta_hard=DELTA_HARD)
            ws.push(f"GATE_{gate['decision']}", {**gate, "price": price})

            aud_conf = None
            action   = "none"
            if gate["decision"] == "EXECUTE":
                alloc = 300 * gate["combined_confidence"]
                portfolio = paymaster.get_portfolio(prices)
                approved, reason, adjusted, aud_conf = auditor.validate(
                    asset, gate["action"], alloc, price, portfolio, balance)
                if approved:
                    try:
                        oracle_price, _ = await asyncio.get_event_loop().run_in_executor(
                            None, lambda: passkey.oracle.get_consensus_price(asset))
                    except Exception:
                        oracle_price = price

                    mandate = await mandate_mgr.request(
                        asset=asset, action=gate["action"],
                        alloc_usd=adjusted, oracle_price=oracle_price, gate_result=gate)
                    ws.push("BIOMETRIC_PENDING", mandate.to_ui_payload())

                    approved_m = await mandate_mgr.wait_for_approval(mandate.mandate_id)
                    if approved_m.get("approved"):
                        receipt = paymaster.execute(approved_m, price)
                        if receipt.get("status") == "filled":
                            trade_data = {"direction":gate["action"],"asset":asset,
                                         "alloc_usd":adjusted,"price":price}
                            alerts.alert("TRADE_EXECUTED", asset, trade_data)
                            ws.push("TRADE_EXECUTED", trade_data)
                            action = f"executed_{gate['action']}"
                    else:
                        alerts.alert("BIOMETRIC_REJECTED", asset, approved_m)
                        ws.push("BIOMETRIC_REJECTED", approved_m)
                        action = "passkey_rejected"

            gate_log.log(gate, action)

            agent_signals[asset] = {
                "scout":     round(scout_conf, 4),
                "quant":     round(q_sig.get("confidence", 0.0), 4),
                "visionary": round(v_sig.get("confidence", 0.0), 4),
                "sentiment": round(sent.get("confidence", 0.3), 4),
                "auditor":   round(aud_conf, 4) if aud_conf is not None else None,
                "gate":      round(gate["combined_confidence"], 4),
            }

        await asyncio.gather(*[eval_asset(a) for a in assets], return_exceptions=True)

        portfolio  = paymaster.get_portfolio(prices)
        gate_stats = gate_log.summary()
        state = {
            "mode": "trading", "cycle": cycle,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "prices": {k:round(v,4) for k,v in prices.items()},
            "portfolio": portfolio, "gate_stats": gate_stats,
            "agent_signals": agent_signals,
            "commerce": commerce.get_summary(),
        }
        with open(LOG_DIR/"state.json","w") as f:
            json.dump(state, f, indent=2)
        with open(LOG_DIR/"portfolio_history.jsonl","a") as f:
            f.write(json.dumps({"cycle":cycle,"timestamp":datetime.now(timezone.utc).isoformat(),**portfolio})+"\n")

        ws.push("CYCLE_COMPLETE", {"cycle":cycle,"portfolio":portfolio,"gate_stats":gate_stats})
        await asyncio.sleep(interval * 60)


# ── E-Commerce Pipeline ───────────────────────────────────────────────────────
async def run_ecommerce(ws: WSBroadcaster, alerts: AlertSystem, config: dict):
    # ── POC 2: E-Commerce domain plugin ─────────────────────────────────────
    from src.domains.ecommerce.feed      import EcommerceMCPHub
    from src.domains.ecommerce.scout     import ProductScout
    from src.domains.ecommerce.quant     import PriceQuant
    from src.domains.ecommerce.visionary import PriceVisionary
    from src.domains.ecommerce.paymaster import EcommercePaymaster
    # ── Framework core (shared, unchanged) ──────────────────────────────────
    from src.core.consensus_gate         import consensus_gate as ec_gate

    groq_client = None
    if GROQ_API_KEY:
        from groq import Groq
        groq_client = Groq(api_key=GROQ_API_KEY)

    mcp       = EcommerceMCPHub()
    scout     = ProductScout(mcp)
    quant     = PriceQuant()
    visionary = PriceVisionary(groq_client) if groq_client else None
    paymaster = EcommercePaymaster(config.get("budget", 2000))
    gate_log  = GateLogger()

    wishlist  = config.get("wishlist", [])
    interval  = config.get("interval_minutes", 30)

    APP_STATE["status"] = "running"
    APP_STATE["mode"]   = "ecommerce"

    logger.info("[ECommerce] Starting — watching %d products", len(wishlist))
    ws.push("MODE_STARTED", {"mode":"ecommerce","products":[w["product"] for w in wishlist]})

    cycle         = 0
    while APP_STATE["status"] == "running":
        cycle += 1
        APP_STATE["cycle"] = cycle
        loop          = asyncio.get_event_loop()
        agent_signals = {}

        async def eval_product(item):
            query    = item["product"]
            data     = await loop.run_in_executor(None, scout.fetch_all, query)
            product  = data.get("current",{}).get("payload",{}) or {}
            price    = product.get("current_price", 0)

            scout_conf = 1.0 if price > 0 else 0.0
            if not price:
                agent_signals[query] = {"scout": 0.0, "quant": 0.0, "visionary": 0.0,
                                        "sentiment": 0.3, "auditor": None, "gate": 0.0}
                return

            q_sig = quant.analyze(data, item)
            v_sig = await loop.run_in_executor(None, visionary.analyze, data, item, cycle) \
                    if visionary else {
                        "recommendation": q_sig["direction"],
                        "structural_bias": q_sig["direction"],
                        "confidence": q_sig["confidence"]*0.9,
                        "trend":"stable","regime":"stable","rationale":"disabled"
                    }

            # Map ecommerce directions to framework
            q_mapped = {"buy":"long","wait":"neutral","overpriced":"short"}.get(q_sig["direction"],"neutral")
            v_mapped = {"buy":"bullish","wait":"neutral","overpriced":"bearish"}.get(v_sig.get("recommendation","wait"),"neutral")

            q_fw = {**q_sig, "direction":q_mapped, "asset":query}
            v_fw = {**v_sig, "structural_bias":v_mapped}
            sent = {"sentiment":"neutral","score":0.0,"confidence":0.3}

            gate = consensus_gate(q_fw, v_fw, sent,
                                  tau_quant=TAU_QUANT, tau_visionary=TAU_VISIONARY,
                                  tau_combined=TAU_COMBINED,
                                  delta_divergence=DELTA_DIVERGENCE, delta_hard=DELTA_HARD)

            ws.push(f"GATE_{gate['decision']}", {
                **gate, "query":query, "price":price,
                "action": "buy" if gate["decision"]=="EXECUTE" else "wait"
            })

            if gate["decision"] == "EXECUTE":
                tax   = item.get("tax_pct",0)
                total = price * (1 + tax/100)
                alert_msg = (
                    f"${price:.2f} (${total:.2f} with tax) matches your "
                    f"${item['min_price']}-${item['max_price']} range | "
                    f"{v_sig.get('rationale','')[:60]}"
                )
                alerts.alert("TRADE_EXECUTED", query, {
                    "direction":"BUY","asset":query,
                    "alloc_usd":price,"price":price,"message":alert_msg
                })
                ws.push("BUY_SIGNAL", {"query":query,"price":price,"total":total,"message":alert_msg})
                mandate = {"approved":True,"mandate_id":f"EC-{int(time.time())}","query":query}
                paymaster.execute(mandate, product)

            gate_log.log({**gate,"asset":query}, "buy" if gate["decision"]=="EXECUTE" else "wait")

            agent_signals[query] = {
                "scout":     round(scout_conf, 4),
                "quant":     round(q_sig.get("confidence", 0.0), 4),
                "visionary": round(v_sig.get("confidence", 0.0), 4),
                "sentiment": 0.3,   # ecommerce pipeline does not run sentiment analysis
                "auditor":   None,  # no auditor in ecommerce mode
                "gate":      round(gate["combined_confidence"], 4),
            }

        await asyncio.gather(*[eval_product(w) for w in wishlist], return_exceptions=True)

        state = {
            "mode":"ecommerce","cycle":cycle,
            "timestamp":datetime.now(timezone.utc).isoformat(),
            "wishlist":wishlist,"gate_stats":gate_log.summary(),
            "agent_signals": agent_signals,
            "paymaster":paymaster.get_status(),
        }
        with open(LOG_DIR/"state.json","w") as f:
            json.dump(state, f, indent=2)
        ws.push("CYCLE_COMPLETE", {"cycle":cycle,"gate_stats":gate_log.summary()})
        await asyncio.sleep(interval * 60)


# ── Mode Controller ───────────────────────────────────────────────────────────
async def mode_controller(ws: WSBroadcaster, mandate_mgr: AsyncMandateManager, alerts: AlertSystem):
    """Watches for mode changes from chat interface and starts correct pipeline."""
    config_path = LOG_DIR / "app_config.json"

    while True:
        await asyncio.sleep(2)

        if APP_STATE["status"] != "chat":
            continue

        if not config_path.exists():
            continue

        try:
            config = json.loads(config_path.read_text())
            mode   = config.get("mode")

            if mode == "trading":
                APP_STATE["config"] = config
                asyncio.create_task(run_trading(ws, mandate_mgr, alerts, config))

            elif mode == "ecommerce":
                APP_STATE["config"] = config
                asyncio.create_task(run_ecommerce(ws, alerts, config))

            # Delete config file so we don't restart
            config_path.unlink()

        except Exception as e:
            logger.error("[Controller] %s", e)


# ── Entry Point ───────────────────────────────────────────────────────────────
async def main():
    ws          = WSBroadcaster()
    mandate_mgr = AsyncMandateManager()
    alerts      = AlertSystem(enabled=True)

    # Save initial state
    with open(LOG_DIR/"state.json","w") as f:
        json.dump({"mode":None,"status":"chat","cycle":0,
                   "timestamp":datetime.now(timezone.utc).isoformat()}, f, indent=2)

    coroutines = [
        ws.broadcaster(),
        start_webhook_server(mandate_mgr, ws, WEBHOOK_PORT),
        mandate_mgr.cleanup_expired(),
        mode_controller(ws, mandate_mgr, alerts),
    ]

    try:
        import websockets
        logger.info("[WS] Starting on ws://localhost:%d", WS_PORT)
        async with websockets.serve(ws.handler, "localhost", WS_PORT):
            await asyncio.gather(*coroutines)
    except ImportError:
        logger.warning("pip install websockets")
        await asyncio.gather(*coroutines)


if __name__ == "__main__":
    # Allow --mode flag to skip chat and start directly
    if "--mode" in sys.argv:
        idx  = sys.argv.index("--mode")
        mode = sys.argv[idx+1] if idx+1 < len(sys.argv) else None
        if mode in ("trading","ecommerce"):
            LOG_DIR.mkdir(exist_ok=True)
            default_config = {
                "trading": {
                    "mode":"trading","assets":["NVDA","AAPL","TSLA"],
                    "interval_minutes":5,"initial_balance":10000,
                    "max_alloc":1000,"daily_cap":3000,
                },
                "ecommerce": {
                    "mode":"ecommerce",
                    "wishlist":[{"id":1,"product":"RTX 4070","min_price":400,
                                 "max_price":550,"tax_pct":8,"deadline_days":10}],
                    "interval_minutes":30,"budget":2000,
                },
            }
            Path(LOG_DIR/"app_config.json").write_text(
                json.dumps(default_config[mode], indent=2))

    asyncio.run(main())
