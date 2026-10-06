"""Validate synthetic account CSVs against the Annex C schema + logical constraints.

Checks (reports every violation; exits non-zero if any HARD violation):
  schema   : id formats, enums, email domain, date formats, positive amounts,
             card_last4 is <=4 digits (never a full PAN), reserved-range avoidance
  integrity: usage/invoice account_ids exist in accounts
  logical  : past_due/suspended accounts have a failed invoice (status<->invoice);
             seats_used <= plan seats

Run:  python synthetic/validate_accounts.py --dir synthetic/test_accounts
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

ACCOUNT_RE = re.compile(r"^A\d{4}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PERIOD_RE = re.compile(r"^\d{4}-\d{2}$")
CARD_RE = re.compile(r"^\d{0,4}$")
PLANS = {"Free", "Pro", "Business", "Enterprise"}
STATUSES = {"active", "past_due", "suspended", "cancelled"}
INV_STATUSES = {"paid", "failed", "refunded"}

hard: list[str] = []
soft: list[str] = []


def read(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def validate(d: Path) -> bool:
    accounts = read(d / "accounts.csv")
    plan_limits = {r["plan"]: r for r in read(d / "plan_limits.csv")}
    usage = read(d / "usage.csv")
    invoices = read(d / "invoices.csv")

    acc_ids = {a["account_id"] for a in accounts}

    # plan_limits completeness
    for p in PLANS:
        if p not in plan_limits:
            hard.append(f"plan_limits missing plan: {p}")

    # accounts
    for a in accounts:
        aid = a["account_id"]
        if not ACCOUNT_RE.match(aid):
            hard.append(f"account_id bad format: {aid}")
        if 9000 <= int(aid[1:]) <= 9999:
            hard.append(f"account_id in RESERVED judge range A9000-A9999: {aid}")
        if a["plan"] not in PLANS:
            hard.append(f"{aid}: bad plan {a['plan']}")
        if a["status"] not in STATUSES:
            hard.append(f"{aid}: bad status {a['status']}")
        if not a["owner_email"].endswith("@example.com"):
            hard.append(f"{aid}: owner_email not @example.com -> possible real PII: {a['owner_email']}")
        if not a["product_version"]:
            soft.append(f"{aid}: empty product_version")

    # usage
    seats_of = {a["account_id"]: int(plan_limits[a["plan"]]["seats"]) for a in accounts
                if a["plan"] in plan_limits}
    for u in usage:
        if u["account_id"] not in acc_ids:
            hard.append(f"usage references unknown account {u['account_id']}")
        if not PERIOD_RE.match(u["period"]):
            hard.append(f"usage {u['account_id']}: bad period {u['period']}")
        for col in ("workflow_runs", "api_calls_peak_per_min", "seats_used"):
            if int(u[col]) < 0:
                hard.append(f"usage {u['account_id']}: negative {col}")
        if u["account_id"] in seats_of and int(u["seats_used"]) > seats_of[u["account_id"]]:
            hard.append(f"usage {u['account_id']}: seats_used {u['seats_used']} > plan seats {seats_of[u['account_id']]}")

    # invoices
    failed_by_acc: dict[str, int] = {}
    for inv in invoices:
        iid = inv["invoice_id"]
        if iid.startswith("INV-J"):
            hard.append(f"invoice_id in RESERVED judge range INV-J*: {iid}")
        if inv["account_id"] not in acc_ids:
            hard.append(f"invoice {iid} references unknown account {inv['account_id']}")
        if float(inv["amount"]) <= 0:
            hard.append(f"invoice {iid}: amount must be > 0 (got {inv['amount']})")
        if not DATE_RE.match(inv["charged_on"]):
            hard.append(f"invoice {iid}: bad charged_on {inv['charged_on']}")
        if inv["status"] not in INV_STATUSES:
            hard.append(f"invoice {iid}: bad status {inv['status']}")
        if inv["status"] != "failed" and inv["failure_reason"]:
            hard.append(f"invoice {iid}: failure_reason set but status={inv['status']}")
        if inv["status"] == "failed" and not inv["failure_reason"]:
            soft.append(f"invoice {iid}: failed but no failure_reason")
        if not CARD_RE.match(inv["card_last4"]):
            hard.append(f"invoice {iid}: card_last4 not <=4 digits -> possible full PAN: {inv['card_last4']}")
        if inv["status"] == "failed":
            failed_by_acc[inv["account_id"]] = failed_by_acc.get(inv["account_id"], 0) + 1

    # logical: past_due/suspended must have a failed invoice
    for a in accounts:
        if a["status"] in ("past_due", "suspended") and failed_by_acc.get(a["account_id"], 0) == 0:
            hard.append(f"{a['account_id']}: status {a['status']} but no failed invoice (inconsistent)")

    # report
    out = [
        "=== Synthetic account validation ===",
        f"accounts={len(accounts)} invoices={len(invoices)} usage_rows={len(usage)} plans={len(plan_limits)}",
        f"HARD violations: {len(hard)}",
        *[f"  [HARD] {m}" for m in hard],
        f"SOFT warnings: {len(soft)}",
        *[f"  [soft] {m}" for m in soft],
        "RESULT: " + ("FAIL" if hard else "PASS"),
    ]
    text = "\n".join(out)
    print(text)
    (Path(__file__).resolve().parent / "validation_output.txt").write_text(text + "\n", encoding="utf-8")
    return not hard


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="synthetic/test_accounts")
    args = ap.parse_args()
    ok = validate(Path(args.dir))
    sys.exit(0 if ok else 1)
