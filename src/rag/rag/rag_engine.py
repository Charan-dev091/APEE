"""
APEE RAG — ChromaDB Vector Store
===================================
Embeds product knowledge into ChromaDB.
Retrieves relevant context for user queries.
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)
CHROMA_PATH = Path(os.getenv("LOG_DIR", "./logs")) / "chroma_db"


class APEERagEngine:
    def __init__(self):
        self._collection = None
        self._ready      = False
        self._init()

    def _init(self):
        try:
            import chromadb
            from chromadb.utils import embedding_functions
            CHROMA_PATH.mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(path=str(CHROMA_PATH))
            ef     = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name="all-MiniLM-L6-v2")
            self._collection = client.get_or_create_collection(
                name="apee_products", embedding_function=ef,
                metadata={"hnsw:space": "cosine"})
            if self._collection.count() == 0:
                self._populate()
            self._ready = True
            logger.info("[RAG] Ready — %d documents", self._collection.count())
        except Exception as e:
            logger.warning("[RAG] Init failed: %s", e)

    def _populate(self):
        from src.rag.knowledge_base import PRODUCTS
        self._collection.add(
            ids       =[p["id"]   for p in PRODUCTS],
            documents =[p["text"] for p in PRODUCTS],
            metadatas =[{"category":p["category"],"brand":p["brand"],
                         "typical_min":p["typical_min"],"typical_max":p["typical_max"],
                         "msrp":p["msrp"]} for p in PRODUCTS],
        )
        logger.info("[RAG] Populated %d products", len(PRODUCTS))

    def retrieve(self, query: str, n: int = 3) -> list:
        if not self._ready:
            return []
        try:
            r = self._collection.query(query_texts=[query],
                                       n_results=min(n, self._collection.count()))
            return [{"id":r["ids"][0][i],"text":r["documents"][0][i],
                     "metadata":r["metadatas"][0][i],
                     "similarity":round(1-r["distances"][0][i],3)}
                    for i in range(len(r["ids"][0]))]
        except Exception as e:
            logger.error("[RAG] Retrieve failed: %s", e)
            return []

    def get_context(self, query: str) -> dict:
        matches = self.retrieve(query, n=3)
        if not matches:
            return {}
        best = matches[0]
        meta = best["metadata"]
        return {
            "category":    meta.get("category","unknown"),
            "brand":       meta.get("brand",""),
            "typical_min": meta.get("typical_min",0),
            "typical_max": meta.get("typical_max",999),
            "msrp":        meta.get("msrp",0),
            "similarity":  best["similarity"],
            "all_matches": matches,
        }

    def is_stock(self, query: str) -> bool:
        matches = self.retrieve(query, n=1)
        return bool(matches) and matches[0]["metadata"].get("category") in ("stock","crypto")

    def is_product(self, query: str) -> bool:
        matches = self.retrieve(query, n=1)
        return bool(matches) and matches[0]["metadata"].get("category") not in ("stock","crypto")


_rag = None
def get_rag() -> APEERagEngine:
    global _rag
    if _rag is None:
        _rag = APEERagEngine()
    return _rag
