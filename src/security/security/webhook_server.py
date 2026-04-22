"""
APEE — Webhook Server
======================
Receives biometric approval signals from the frontend.
Runs on port 8766 alongside the WebSocket server (8765).

Endpoints:
  POST /mandate/approve  → user approved biometric
  POST /mandate/reject   → user dismissed prompt
  GET  /mandate/pending  → list pending mandates
  GET  /health           → server health check
"""

import asyncio
import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


async def handle_request(reader, writer, mandate_manager, ws_broadcaster):
    """Handle a single HTTP request."""
    try:
        request_line = await asyncio.wait_for(reader.readline(), timeout=5.0)
        if not request_line:
            return

        method, path, _ = request_line.decode().strip().split(" ", 2)

        # Read headers
        headers = {}
        while True:
            line = await reader.readline()
            if line in (b"\r\n", b"\n", b""):
                break
            key, _, val = line.decode().partition(":")
            headers[key.strip().lower()] = val.strip()

        # Read body if present
        body = b""
        content_length = int(headers.get("content-length", 0))
        if content_length:
            body = await reader.read(content_length)

        # Route
        if method == "GET" and path == "/health":
            response_body = json.dumps({
                "status":   "ok",
                "pending":  mandate_manager.count(),
                "time":     datetime.now(timezone.utc).isoformat(),
            })
            status = "200 OK"

        elif method == "GET" and path == "/mandate/pending":
            response_body = json.dumps({
                "pending": mandate_manager.get_pending()
            })
            status = "200 OK"

        elif method == "POST" and path == "/mandate/approve":
            data        = json.loads(body) if body else {}
            mandate_id  = data.get("mandate_id", "")
            signature   = data.get("signature", "simulated_webauthn_sig")

            result = await mandate_manager.approve(mandate_id, signature)

            if result.get("success"):
                # Notify frontend via WebSocket
                ws_broadcaster.push("MANDATE_APPROVED", "system", {
                    "mandate_id": mandate_id,
                    "message":    "Biometric confirmed — executing trade",
                })
                response_body = json.dumps({"success": True})
                status = "200 OK"
            else:
                response_body = json.dumps(result)
                status = "400 Bad Request"

        elif method == "POST" and path == "/mandate/reject":
            data       = json.loads(body) if body else {}
            mandate_id = data.get("mandate_id", "")
            reason     = data.get("reason", "User rejected")

            await mandate_manager.reject(mandate_id, reason)
            ws_broadcaster.push("MANDATE_REJECTED", "system", {
                "mandate_id": mandate_id,
                "reason":     reason,
            })
            response_body = json.dumps({"success": True})
            status = "200 OK"

        else:
            response_body = json.dumps({"error": "Not found"})
            status = "404 Not Found"

        # Send response with CORS headers
        response = (
            f"HTTP/1.1 {status}\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(response_body)}\r\n"
            f"Access-Control-Allow-Origin: *\r\n"
            f"Access-Control-Allow-Methods: GET, POST, OPTIONS\r\n"
            f"Access-Control-Allow-Headers: Content-Type\r\n"
            f"Connection: close\r\n"
            f"\r\n"
            f"{response_body}"
        )
        writer.write(response.encode())
        await writer.drain()

    except Exception as e:
        logger.error("[Webhook] Request error: %s", e)
    finally:
        writer.close()


async def start_webhook_server(mandate_manager, ws_broadcaster, port=8766):
    """Start the webhook HTTP server."""

    async def handler(reader, writer):
        await handle_request(reader, writer, mandate_manager, ws_broadcaster)

    server = await asyncio.start_server(handler, "localhost", port)
    logger.info("[Webhook] Server started on http://localhost:%d", port)
    async with server:
        await server.serve_forever()
