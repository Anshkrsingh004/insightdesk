"""Load account CSVs (Annex C schema) into SQLite. Judges use this with their own data.

    python scripts/load_accounts.py --dir synthetic/test_accounts

Loads any of these files that are present in --dir, upserting by primary key:
  accounts.csv  plan_limits.csv  usage.csv  invoices.csv  platform_status.csv

Idempotent: re-running replaces rows with the same primary key.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.db import connection, init_db  # noqa: E402

# file -> (table, columns, conflict-target used for REPLACE semantics)
SPECS = {
    "accounts.csv": ("accounts",
                     ["account_id", "company_name", "owner_email", "plan", "status",
                      "product_version", "created_at"]),
    "plan_limits.csv": ("plan_limits",
                        ["plan", "api_rate_limit_per_min", "monthly_workflow_runs",
                         "seats", "support_tier", "monthly_price"]),
    "usage.csv": ("usage",
                 ["account_id", "period", "workflow_runs", "api_calls_peak_per_min",
                  "seats_used"]),
    "invoices.csv": ("invoices",
                    ["invoice_id", "account_id", "amount", "currency", "charged_on",
                     "status", "failure_reason", "card_last4"]),
    "platform_status.csv": ("platform_status",
                           ["component", "status", "incident_id", "updated_at"]),
}


def load(directory: Path) -> dict:
    init_db()
    counts: dict[str, int] = {}
    with connection() as conn:
        for fname, (table, cols) in SPECS.items():
            path = directory / fname
            if not path.exists():
                continue
            with path.open(newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            placeholders = ",".join(["?"] * len(cols))
            collist = ",".join(cols)
            conn.executemany(
                f"INSERT OR REPLACE INTO {table} ({collist}) VALUES ({placeholders})",
                [tuple(r[c] for c in cols) for r in rows],
            )
            counts[table] = len(rows)
    return counts


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="synthetic/test_accounts")
    args = ap.parse_args()
    counts = load(Path(args.dir))
    print("Loaded into SQLite:")
    for t, n in counts.items():
        print(f"  {t}: {n} rows")
    if not counts:
        print("  (no CSVs found in", args.dir, ")")
