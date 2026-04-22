"""APEE RAG Server — python rag_server.py"""
import json, logging, os, sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

from dotenv import load_dotenv
load_dotenv()

LOG_DIR  = Path(os.getenv("LOG_DIR", "./logs"))
LOG_DIR.mkdir(exist_ok=True)
RAG_PATH = LOG_DIR / "rag_result.json"

sys.path.insert(0, str(Path(__file__).parent))
from src.rag.rag_engine import APEERagEngine

rag   = APEERagEngine()
count = rag._collection.count() if rag._collection else 0
logger.info("[RAG] Ready — %d documents indexed", count)

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        q = parse_qs(parsed.query).get("q", [""])[0]
        if parsed.path == "/rag/query" and q:
            ctx = rag.get_context(q)
            res = {"query": q, "context": ctx}
            RAG_PATH.write_text(json.dumps(res, indent=2))
            logger.info("[RAG] '%s' -> %s (%.2f)", q[:40], ctx.get("category","?"), ctx.get("similarity",0))
            self._ok(res)
        elif parsed.path == "/rag/health":
            self._ok({"status": "ok", "documents": count})
        else:
            self._ok({"error": "not found"}, 404)

    def do_POST(self):
        n    = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n)) if n else {}
        if self.path == "/rag/query":
            q   = body.get("query", "")
            ctx = rag.get_context(q)
            res = {"query": q, "context": ctx}
            RAG_PATH.write_text(json.dumps(res, indent=2))
            self._ok(res)
        else:
            self._ok({"error": "not found"}, 404)

    def _ok(self, data, code=200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args): pass

if __name__ == "__main__":
    port   = int(os.getenv("RAG_PORT", "8767"))
    server = HTTPServer(("localhost", port), Handler)
    logger.info("[RAG Server] http://localhost:%d/rag/query?q=RTX+4070", port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("[RAG Server] Stopped")
