"""Deterministic synthetic account generator (Annex C schema).

Writes five CSVs to synthetic/test_accounts/ loadable by scripts/load_accounts.py.
Seeded (reproducible). Every required edge case is pinned to a known account_id and
documented in synthetic/data_card.md.

Constraints honoured:
  * account_id = 'A' + 4 digits, NOT in reserved A9000-A9999
  * invoice_id NOT starting 'INV-J'  (reserved for judges)
  * owner_email @example.com only; card_last4 is 4 digits only (never a full PAN)
  * amounts > 0; failure_reason empty unless status=failed
  * status <-> invoice consistency (past_due/suspended have a failed invoice)

Run:  python synthetic/generate_accounts.py
"""
from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "synthetic" / "test_accounts"

AS_OF = date(2026, 10, 6)          # anchor for refund-window edge cases
REFUND_WINDOW_DAYS = 14
rng = random.Random(42)

PLAN_LIMITS = [
    # plan, api_rate_limit_per_min, monthly_workflow_runs, seats, support_tier, monthly_price
    ("Free", 10, 100, 1, "community", 0.0),
    ("Pro", 60, 10_000, 5, "standard", 49.0),
    ("Business", 300, 100_000, 25, "priority", 199.0),
    ("Enterprise", 1_000, 1_000_000, 100, "priority", 999.0),
]
PRICE = {p[0]: p[5] for p in PLAN_LIMITS}   # monthly_price is index 5, not 4 (support_tier)
RUNLIMIT = {p[0]: p[2] for p in PLAN_LIMITS}
RATELIMIT = {p[0]: p[1] for p in PLAN_LIMITS}
SEATS = {p[0]: p[3] for p in PLAN_LIMITS}

COMPANIES = [
    "Acme Logistics", "Northwind Retail", "Globex Analytics", "Initech Software",
    "Umbrella Health", "Soylent Foods", "Hooli Media", "Stark Industrial",
    "Wayne Supplies", "Wonka Confectionery", "Cyberdyne Robotics", "Tyrell Data",
    "Gekko Capital", "Vandelay Imports", "Pied Piper Cloud", "Dunder Paper",
    "Prestige Worldwide", "Oscorp Labs", "Monarch Travel", "Bluth Property",
    "Sterling Design", "Paper Street Co", "Nakatomi Trading", "Massive Dynamic",
    "Aperture Science", "Black Mesa", "Virtucon Group", "Enersoft", "Zenith Works",
    "Lumon Industries", "Primatech", "Rekall Media", "Weyland Freight", "Oceanic Air",
    "Combine Energy", "Abstergo Retail",
]

accounts: list[dict] = []
usage: list[dict] = []
invoices: list[dict] = []
_inv = 6000  # invoice counter -> INV-6001.. (never INV-J)


def next_inv() -> str:
    global _inv
    _inv += 1
    return f"INV-{_inv}"


def card() -> str:
    return f"{rng.randint(0, 9999):04d}"


def add_account(aid, plan, status, version, company, created="2026-01-15"):
    slug = company.lower().replace(" ", "")
    accounts.append({
        "account_id": aid, "company_name": company,
        # Domain must be exactly example.com (not a subdomain); local part is unique.
        "owner_email": f"{slug}.{aid.lower()}@example.com",
        "plan": plan, "status": status, "product_version": version, "created_at": created,
    })


def add_usage(aid, period, runs, peak, seats_used):
    usage.append({"account_id": aid, "period": period, "workflow_runs": runs,
                  "api_calls_peak_per_min": peak, "seats_used": seats_used})


def add_invoice(aid, amount, charged_on, status, currency="USD", failure_reason=""):
    invoices.append({
        "invoice_id": next_inv(), "account_id": aid, "amount": amount,
        "currency": currency, "charged_on": charged_on, "status": status,
        "failure_reason": failure_reason if status == "failed" else "",
        "card_last4": card(),
    })


def normal_usage(aid, plan, fraction=0.4):
    """A within-limits usage row for the current period."""
    runs = int(RUNLIMIT[plan] * fraction)
    peak = max(1, int(RATELIMIT[plan] * fraction))
    seats_used = max(1, min(SEATS[plan], rng.randint(1, SEATS[plan])))
    add_usage(aid, "2026-10", runs, peak, seats_used)


# ===========================================================================
# EDGE-CASE ACCOUNTS (fixed IDs — see data_card.md)
# ===========================================================================
# A1001 happy-path Pro (demo account)
add_account("A1001", "Pro", "active", "4.3", "Acme Logistics")
normal_usage("A1001", "Pro", 0.35)
add_invoice("A1001", PRICE["Pro"], "2026-10-01", "paid")

# A1002 usage EXACTLY at monthly run limit
add_account("A1002", "Pro", "active", "4.3", "Northwind Retail")
add_usage("A1002", "2026-10", RUNLIMIT["Pro"], 55, 3)           # 10000 == limit
add_invoice("A1002", PRICE["Pro"], "2026-10-01", "paid")

# A1003 ONE unit over (runs and rate both over)
add_account("A1003", "Pro", "active", "4.3", "Globex Analytics")
add_usage("A1003", "2026-10", RUNLIMIT["Pro"] + 1, RATELIMIT["Pro"] + 1, 5)  # 10001, 61
add_invoice("A1003", PRICE["Pro"], "2026-10-01", "paid")

# A1004 failed payment -> past_due (status/invoice consistency)
add_account("A1004", "Pro", "past_due", "4.3", "Initech Software")
normal_usage("A1004", "Pro", 0.5)
add_invoice("A1004", PRICE["Pro"], "2026-09-01", "paid")
add_invoice("A1004", PRICE["Pro"], "2026-10-01", "failed", failure_reason="card_declined")

# A1005 DUPLICATE charge (two identical invoices, same day)
add_account("A1005", "Business", "active", "4.3", "Umbrella Health")
normal_usage("A1005", "Business", 0.3)
add_invoice("A1005", PRICE["Business"], "2026-10-01", "paid")   # INV-6006
add_invoice("A1005", PRICE["Business"], "2026-10-01", "paid")   # INV-6007 duplicate

# A1006 refund-window boundary: last eligible day & one day after
last_eligible = (AS_OF - timedelta(days=REFUND_WINDOW_DAYS)).isoformat()   # 2026-09-22
just_outside = (AS_OF - timedelta(days=REFUND_WINDOW_DAYS + 1)).isoformat()  # 2026-09-21
add_account("A1006", "Pro", "active", "4.3", "Soylent Foods")
normal_usage("A1006", "Pro", 0.45)
add_invoice("A1006", PRICE["Pro"], last_eligible, "paid")       # eligible (==14 days)
add_invoice("A1006", PRICE["Pro"], just_outside, "paid")        # NOT eligible (15 days)

# A1007 suspended (with a failed invoice for consistency)
add_account("A1007", "Business", "suspended", "4.3", "Hooli Media")
normal_usage("A1007", "Business", 0.2)
add_invoice("A1007", PRICE["Business"], "2026-09-15", "failed", failure_reason="insufficient_funds")

# A1008 OLD product version 3.x
add_account("A1008", "Business", "active", "3.9", "Stark Industrial")
normal_usage("A1008", "Business", 0.6)
add_invoice("A1008", PRICE["Business"], "2026-10-01", "paid")

# A1009 Enterprise happy
add_account("A1009", "Enterprise", "active", "4.3", "Wayne Supplies")
add_usage("A1009", "2026-10", 250_000, 420, 60)
add_invoice("A1009", PRICE["Enterprise"], "2026-10-01", "paid")

# A1010 cancelled Free (refunded last invoice on a prior paid plan)
add_account("A1010", "Free", "cancelled", "3.9", "Wonka Confectionery")
add_usage("A1010", "2026-10", 20, 4, 1)
add_invoice("A1010", 49.0, "2026-08-01", "refunded")           # was on Pro before cancelling

EDGE_IDS = {f"A100{i}" for i in range(1, 10)} | {"A1010"}

# ===========================================================================
# FILLER ACCOUNTS A1011.. -> ensure all plan x status combos, >=30 total
# ===========================================================================
PLANS = ["Free", "Pro", "Business", "Enterprise"]
STATUSES = ["active", "past_due", "suspended", "cancelled"]
combos = [(p, s) for p in PLANS for s in STATUSES]  # 16 combos

idx = 11
for ci, (plan, status) in enumerate(combos):
    aid = f"A{1000 + idx}"
    idx += 1
    company = COMPANIES[(idx) % len(COMPANIES)]
    version = "3.9" if ci % 7 == 0 else "4.3"
    add_account(aid, plan, status, version, company)
    normal_usage(aid, plan, fraction=round(rng.uniform(0.1, 0.8), 2))
    if plan == "Free":
        # Free is $0 -> invoices only exist from a prior paid plan (keeps status consistent).
        if status == "cancelled":
            add_invoice(aid, 49.0, "2026-07-01", "refunded")
        elif status in ("past_due", "suspended"):
            add_invoice(aid, 49.0, "2026-10-01", "failed", failure_reason="card_declined")
    else:
        price = PRICE[plan]
        # a prior paid invoice
        add_invoice(aid, price, "2026-09-01", "paid")
        # current invoice reflects status
        if status in ("past_due", "suspended"):
            add_invoice(aid, price, "2026-10-01", "failed", failure_reason="card_declined")
        elif status == "cancelled":
            add_invoice(aid, price, "2026-10-01", "refunded")
        else:  # active
            add_invoice(aid, price, "2026-10-01", "paid", currency=("INR" if ci % 5 == 0 else "USD"))

# A few extra active accounts to pad distribution past 30 and add variety
for j in range(4):
    aid = f"A{1000 + idx}"
    idx += 1
    plan = PLANS[j % 4]
    add_account(aid, plan, "active", "4.3", COMPANIES[(idx * 3) % len(COMPANIES)])
    normal_usage(aid, plan, fraction=round(rng.uniform(0.2, 0.7), 2))
    if plan != "Free":
        add_invoice(aid, PRICE[plan], "2026-10-01", "paid")

# ===========================================================================
# PLATFORM STATUS
# ===========================================================================
platform = [
    {"component": "api", "status": "operational", "incident_id": "",
     "updated_at": "2026-10-06T08:00:00Z"},
    {"component": "workflow-engine", "status": "operational", "incident_id": "",
     "updated_at": "2026-10-06T08:00:00Z"},
    {"component": "connectors", "status": "degraded", "incident_id": "INC-2041",
     "updated_at": "2026-10-06T07:30:00Z"},   # Salesforce connector degraded (demo)
    {"component": "billing", "status": "operational", "incident_id": "",
     "updated_at": "2026-10-06T08:00:00Z"},
]


def write_csv(path: Path, rows: list[dict], cols: list[str]):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def main() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    write_csv(OUT / "accounts.csv", accounts,
              ["account_id", "company_name", "owner_email", "plan", "status",
               "product_version", "created_at"])
    write_csv(OUT / "plan_limits.csv",
              [dict(zip(["plan", "api_rate_limit_per_min", "monthly_workflow_runs",
                         "seats", "support_tier", "monthly_price"], p)) for p in PLAN_LIMITS],
              ["plan", "api_rate_limit_per_min", "monthly_workflow_runs", "seats",
               "support_tier", "monthly_price"])
    write_csv(OUT / "usage.csv", usage,
              ["account_id", "period", "workflow_runs", "api_calls_peak_per_min", "seats_used"])
    write_csv(OUT / "invoices.csv", invoices,
              ["invoice_id", "account_id", "amount", "currency", "charged_on",
               "status", "failure_reason", "card_last4"])
    write_csv(OUT / "platform_status.csv", platform,
              ["component", "status", "incident_id", "updated_at"])
    return {
        "accounts": len(accounts), "invoices": len(invoices),
        "usage_rows": len(usage), "plans": len(PLAN_LIMITS),
        "statuses_present": sorted({a["status"] for a in accounts}),
        "plans_present": sorted({a["plan"] for a in accounts}),
    }


if __name__ == "__main__":
    stats = main()
    print("Accounts generated:")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    print(f"  -> {OUT}")
