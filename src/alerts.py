"""
APEE — Emergency Desktop Notifications
========================================
Uses Windows Message Box (msg.exe) for CRITICAL alerts.
Uses PowerShell balloon tooltip for normal alerts.
No extra packages needed — works on all Windows machines.
"""

import logging
import subprocess
import sys
from datetime import datetime

logger = logging.getLogger(__name__)


def _powershell_toast(title: str, message: str, urgency: str = "INFO"):
    """Send Windows balloon notification via PowerShell BurntToast or fallback."""
    try:
        # Method 1: PowerShell balloon tooltip — works on all Windows
        ps = f"""
Add-Type -AssemblyName System.Windows.Forms
$notify = New-Object System.Windows.Forms.NotifyIcon
$notify.Icon = [System.Drawing.SystemIcons]::Information
$notify.BalloonTipTitle = "{title}"
$notify.BalloonTipText = "{message}"
$notify.Visible = $True
$notify.ShowBalloonTip(5000)
Start-Sleep -Seconds 6
$notify.Dispose()
"""
        subprocess.Popen(
            ["powershell", "-WindowStyle", "Hidden", "-Command", ps],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except Exception as e:
        logger.warning("[Alert] Balloon toast failed: %s", e)


def _msgbox(title: str, message: str):
    """
    Windows MessageBox — modal popup user MUST click OK.
    Used only for CRITICAL events like stop-loss.
    """
    try:
        ps = f"""
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.MessageBox]::Show(
    "{message}\\n\\nTime: {datetime.now().strftime('%H:%M:%S')}",
    "🚨 APEE ALERT — {title}",
    [System.Windows.Forms.MessageBoxButtons]::OK,
    [System.Windows.Forms.MessageBoxIcon]::Warning
)
"""
        subprocess.Popen(
            ["powershell", "-WindowStyle", "Hidden", "-Command", ps],
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except Exception as e:
        logger.warning("[Alert] MessageBox failed: %s", e)


def _console_alert(urgency: str, title: str, message: str):
    """Always print to console as fallback."""
    icons = {"CRITICAL":"🚨","WARNING":"⚠️","SUCCESS":"✅","INFO":"ℹ️"}
    icon  = icons.get(urgency, "ℹ️")
    print(f"\n{'='*60}")
    print(f"  {icon} {title}")
    print(f"  {message}")
    print(f"  {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*60}\n")


class AlertSystem:
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._log    = []

    def alert(self, event_type: str, asset: str, data: dict):
        if not self.enabled:
            return
        handlers = {
            "STOP_TRIGGERED":     self._stop_loss,
            "TRADE_EXECUTED":     self._trade_executed,
            "BIOMETRIC_REJECTED": self._biometric_rejected,
            "AUDITOR_BLOCKED":    self._auditor_blocked,
            "GATE_REVIEW":        self._gate_review,
            "COMMERCE_PURCHASE":  self._commerce,
            "CYCLE_COMPLETE":     self._cycle,
            "EXEC_FAILED":        self._exec_failed,
        }
        h = handlers.get(event_type)
        if h:
            h(asset, data)

    def _stop_loss(self, asset, data):
        pnl   = data.get("pnl", 0)
        price = data.get("price", 0)
        title = f"STOP-LOSS — {asset}"
        msg   = f"Position closed at ${price:,.2f} | P&L: ${pnl:+.2f}"
        _console_alert("CRITICAL", title, msg)
        _powershell_toast(f"🚨 {title}", msg, "CRITICAL")
        _msgbox(title, msg)  # modal — cannot be missed
        self._log.append({"type":"STOP_LOSS","asset":asset,"pnl":pnl})

    def _trade_executed(self, asset, data):
        direction = data.get("direction","").upper()
        alloc     = data.get("alloc_usd", 0)
        price     = data.get("price", 0)
        title     = f"TRADE EXECUTED — {asset}"
        msg       = f"{direction} {asset} | ${alloc:.0f} @ ${price:,.2f} | 6/6 conditions"
        _console_alert("SUCCESS", title, msg)
        _powershell_toast(f"✅ {title}", msg, "SUCCESS")
        self._log.append({"type":"TRADE","asset":asset,"direction":direction})

    def _biometric_rejected(self, asset, data):
        reason = data.get("reason","")
        title  = f"AUTH FAILED — {asset}"
        msg    = f"Mandate blocked | {reason}"
        _console_alert("CRITICAL", title, msg)
        _powershell_toast(f"🔴 {title}", msg, "CRITICAL")
        self._log.append({"type":"AUTH_FAILED","asset":asset})

    def _auditor_blocked(self, asset, data):
        title = f"TRADE BLOCKED — {asset}"
        msg   = f"Auditor rejected | {data.get('reason','')}"
        _console_alert("WARNING", title, msg)
        _powershell_toast(f"⚠️ {title}", msg, "WARNING")

    def _gate_review(self, asset, data):
        title = f"GATE REVIEW — {asset}"
        msg   = data.get("reason","")[:80]
        _console_alert("WARNING", title, msg)

    def _commerce(self, asset, data):
        item  = data.get("item","")
        price = data.get("price", 0)
        title = "PURCHASE COMPLETE"
        msg   = f"'{item}' bought for ${price:.2f} from {asset} profits"
        _console_alert("SUCCESS", title, msg)
        _powershell_toast(f"🛒 {title}", msg, "SUCCESS")

    def _exec_failed(self, asset, data):
        title = f"EXECUTION FAILED — {asset}"
        msg   = data.get("reason","Unknown error")
        _console_alert("CRITICAL", title, msg)
        _powershell_toast(f"🔴 {title}", msg, "CRITICAL")

    def _cycle(self, asset, data):
        portfolio = data.get("portfolio", {})
        ret       = portfolio.get("total_return_pct", 0)
        value     = portfolio.get("total_value", 0)
        cycle     = data.get("cycle", 0)
        # Only notify on significant P&L change
        if abs(ret) >= 1.0:
            title = f"Cycle {cycle} — Notable P&L"
            msg   = f"Portfolio: ${value:,.2f} | Return: {ret:+.2f}%"
            _powershell_toast(title, msg, "INFO")

    def get_log(self):
        return self._log
