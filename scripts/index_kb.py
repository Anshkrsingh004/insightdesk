"""Index all seeded sources into ChromaDB.

    python scripts/index_kb.py

First run downloads the all-MiniLM-L6-v2 ONNX model (~80 MB) once. Re-running replaces
each source's chunks cleanly (idempotent).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.retrieval.ingest import index_all_from_sqlite  # noqa: E402
from app.retrieval import vectorstore as vs  # noqa: E402

if __name__ == "__main__":
    n = index_all_from_sqlite()
    print(f"Indexed {n} chunks into ChromaDB. Collection now holds {vs.count()} chunks.")
