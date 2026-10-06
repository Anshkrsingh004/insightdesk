"""Indexing pipeline shared by the batch build and live POST /ingest (R12).

add_source(meta, body)  -> upsert the Source Register row in SQLite + (re)index chunks
index_all_from_sqlite() -> (re)index every source already in SQLite

Articles are markdown (chunked by section). Tickets arrive as JSON (Annex F shape); we
parse out the text and the precedence flags (outdated / conflicts_with) so the Source
Precedence Engine can make documentation win over an outdated ticket (Annex A.2).
"""
from __future__ import annotations

import json

from ..db import connection, init_db
from . import vectorstore as vs
from .chunking import split_markdown

SOURCE_COLS = ["source_id", "doc_type", "title", "authority_level", "product_versions",
               "last_updated", "effective_from", "deprecated_on", "supersedes",
               "provenance", "synthetic", "body"]


def _ticket_text_and_flags(body: str) -> tuple[str, bool, str]:
    """Parse a ticket JSON body -> (searchable text, outdated, conflicts_with).
    Falls back to treating the body as plain text."""
    try:
        t = json.loads(body)
        text = (f"{t.get('subject','')}\n\nCustomer: {t.get('customer_question','')}\n\n"
                f"Resolution: {t.get('resolution','')}\n\nTags: {', '.join(t.get('tags', []))}")
        return text, bool(t.get("outdated", False)), str(t.get("conflicts_with", ""))
    except Exception:
        return body, False, ""


def _chunks_for(meta: dict, body: str) -> tuple[list[str], list[str], list[dict]]:
    sid = meta["source_id"]
    doc_type = meta["doc_type"]
    outdated, conflicts_with = False, ""
    if doc_type == "ticket":
        text, outdated, conflicts_with = _ticket_text_and_flags(body)
        sections = [("Ticket", text)]
    else:
        sections = split_markdown(body)

    ids, docs, metas = [], [], []
    for i, (section, text) in enumerate(sections):
        ids.append(f"{sid}::{i}")
        docs.append(text)
        metas.append({
            "source_id": sid, "doc_type": doc_type, "title": meta.get("title", ""),
            "section": section,
            "authority_level": int(meta.get("authority_level", 5) or 5),
            "product_versions": meta.get("product_versions", "") or "",
            "last_updated": meta.get("last_updated", "") or "",
            "effective_from": meta.get("effective_from", "") or "",
            "deprecated_on": meta.get("deprecated_on", "") or "",
            "supersedes": meta.get("supersedes", "") or "",
            "outdated": outdated, "conflicts_with": conflicts_with,
        })
    return ids, docs, metas


def index_source(meta: dict, body: str) -> int:
    vs.delete_source(meta["source_id"])
    ids, docs, metas = _chunks_for(meta, body)
    if ids:
        vs.add_chunks(ids, docs, metas)
    return len(ids)


def add_source(meta: dict, body: str) -> int:
    """Upsert the Source Register row + (re)index. Used by live POST /ingest."""
    init_db()
    row = {c: meta.get(c, "") for c in SOURCE_COLS}
    row["body"] = body
    with connection() as conn:
        conn.execute(
            f"INSERT OR REPLACE INTO sources ({','.join(SOURCE_COLS)}) "
            f"VALUES ({','.join(['?'] * len(SOURCE_COLS))})",
            tuple(row[c] for c in SOURCE_COLS),
        )
    return index_source(meta, body)


def index_all_from_sqlite() -> int:
    with connection() as conn:
        rows = [dict(r) for r in conn.execute(f"SELECT {','.join(SOURCE_COLS)} FROM sources")]
    total = 0
    for r in rows:
        total += index_source(r, r["body"] or "")
    return total
