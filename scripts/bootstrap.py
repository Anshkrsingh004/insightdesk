"""One-command setup: build the knowledge base, generate + validate + load synthetic
accounts, seed the policy registry and Source Register, and index ChromaDB.

    python scripts/bootstrap.py [--reset]

--reset wipes storage/ first (fresh SQLite + Chroma). Safe to re-run; idempotent.
Judges can run this, then `uvicorn app.main:app`.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable


def run(mod_args: list[str]):
    print(f"\n$ python {' '.join(mod_args)}")
    r = subprocess.run([PY, *mod_args], cwd=ROOT)
    if r.returncode != 0:
        sys.exit(f"step failed: {mod_args}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="wipe storage/ first")
    args = ap.parse_args()

    if args.reset:
        storage = ROOT / "storage"
        if storage.exists():
            shutil.rmtree(storage, ignore_errors=True)
        print("storage/ wiped.")

    run(["synthetic/generate_kb.py"])
    run(["synthetic/generate_accounts.py"])
    run(["synthetic/validate_accounts.py", "--dir", "synthetic/test_accounts"])
    run(["scripts/load_accounts.py", "--dir", "synthetic/test_accounts"])
    run(["scripts/seed_policy.py"])
    run(["scripts/seed_sources.py"])
    run(["scripts/index_kb.py"])
    print("\n✅ Bootstrap complete. Start the API with:  uvicorn app.main:app")
