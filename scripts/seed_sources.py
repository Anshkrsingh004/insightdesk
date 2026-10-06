"""Load the generated KB into the SQLite `sources` table (Source Register + body).

Reads kb/source_register.csv and the matching kb/articles/*.md / kb/tickets/*.json,
then upserts into `sources`. This powers GET /sources now and is the source of truth
that Phase 2 indexes into ChromaDB.

Run:  python scripts/seed_sources.py
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.db import connection, init_db  # noqa: E402

KB = ROOT / "kb"
COLS = ["source_id", "doc_type", "title", "authority_level", "product_versions",
        "last_updated", "effective_from", "deprecated_on", "supersedes",
        "provenance", "synthetic", "body"]


def body_for(source_id: str, doc_type: str) -> str:
    if doc_type == "ticket":
        p = KB / "tickets" / f"{source_id}.json"
        if p.exists():
            t = json.loads(p.read_text(encoding="utf-8"))
            return (f"{t.get('subject','')}\n\nCustomer: {t.get('customer_question','')}\n\n"
                    f"Resolution: {t.get('resolution','')}\n\nTags: {', '.join(t.get('tags', []))}")
        return ""
    p = KB / "articles" / f"{source_id}.md"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def seed() -> int:
    init_db()
    reg = list(csv.DictReader((KB / "source_register.csv").open(encoding="utf-8")))
    with connection() as conn:
        for r in reg:
            r["body"] = body_for(r["source_id"], r["doc_type"])
            conn.execute(
                f"INSERT OR REPLACE INTO sources ({','.join(COLS)}) "
                f"VALUES ({','.join(['?'] * len(COLS))})",
                tuple(r[c] for c in COLS),
            )
    return len(reg)


if __name__ == "__main__":
    n = seed()
    print(f"Seeded {n} sources into SQLite (articles + policies + release note + tickets).")
