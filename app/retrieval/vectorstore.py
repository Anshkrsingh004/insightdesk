"""ChromaDB wrapper (persisted to disk). One collection, cosine space.

Chunk ids are `{source_id}::{i}`. Metadata carries the Source Register fields so the
Source Precedence Engine can filter and rank without re-reading SQLite.
"""
from __future__ import annotations

from typing import Optional

from ..config import Settings, get_settings
from .embeddings import get_embedding_function

COLLECTION = "insightdesk"
_client = None
_collection = None


def get_collection(settings: Optional[Settings] = None):
    global _client, _collection
    if _collection is not None:
        return _collection
    import chromadb

    s = settings or get_settings()
    _client = chromadb.PersistentClient(path=str(s.chroma_abspath))
    _collection = _client.get_or_create_collection(
        name=COLLECTION,
        embedding_function=get_embedding_function(s),
        metadata={"hnsw:space": "cosine"},
    )
    return _collection


def _clean_meta(meta: dict) -> dict:
    """Chroma metadata values must be str/int/float/bool (no None/lists)."""
    out = {}
    for k, v in meta.items():
        if v is None:
            out[k] = ""
        elif isinstance(v, (str, int, float, bool)):
            out[k] = v
        else:
            out[k] = str(v)
    return out


def add_chunks(ids: list[str], documents: list[str], metadatas: list[dict]) -> None:
    col = get_collection()
    col.add(ids=ids, documents=documents, metadatas=[_clean_meta(m) for m in metadatas])


def delete_source(source_id: str) -> None:
    """Remove all chunks for a source_id (so re-ingest replaces cleanly)."""
    col = get_collection()
    try:
        col.delete(where={"source_id": source_id})
    except Exception:
        pass


def query(text: str, n_results: int = 8, where: Optional[dict] = None) -> list[dict]:
    col = get_collection()
    res = col.query(query_texts=[text], n_results=n_results, where=where)
    out: list[dict] = []
    ids = res.get("ids", [[]])[0]
    docs = res.get("documents", [[]])[0]
    metas = res.get("metadatas", [[]])[0]
    dists = res.get("distances", [[]])[0]
    for i in range(len(ids)):
        out.append({
            "chunk_id": ids[i],
            "text": docs[i],
            "metadata": metas[i],
            "distance": dists[i] if i < len(dists) else None,
        })
    return out


def count() -> int:
    try:
        return get_collection().count()
    except Exception:
        return 0


def healthcheck() -> tuple[bool, int]:
    try:
        return True, count()
    except Exception:
        return False, 0
