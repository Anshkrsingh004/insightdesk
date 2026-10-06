"""Seed the policy_registry (Annex C) from the policy articles.

Every value a tool or the escalation engine relies on lives here and is linked to a
cited policy article (source_id + source_section) so judges can open the source. The
numeric values mirror the policy articles KB-POL-* and the plan_limits table.

Run:  python scripts/seed_policy.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.db import connection, init_db  # noqa: E402

# rule_id, description, parameter, operator, value, scope_plans, effective_from, source_id, source_section
RULES = [
    ("REFUND-WINDOW-01", "Refunds allowed within 14 days of charge",
     "refund_window_days", "<=", "14", "ALL", "2026-01-01", "KB-POL-REFUND-001", "Refund window"),
    ("CRITIC-MIN-GROUNDEDNESS-01", "Minimum critic groundedness to answer without escalation",
     "critic_min_groundedness", ">=", "0.6", "ALL", "2026-01-01", "KB-POL-ESCALATION-001", "Registry values"),
    ("ESCALATION-SLA-BILLING-01", "Billing handoff first response within 1 business day",
     "billing_response_sla_hours", "<=", "24", "ALL", "2026-01-01", "KB-POL-ESCALATION-001", "SLAs"),
    ("ESCALATION-SLA-SECURITY-01", "Security handoff first response within 4 hours",
     "security_response_sla_hours", "<=", "4", "ALL", "2026-01-01", "KB-POL-ESCALATION-001", "SLAs"),
    # Per-plan API rate limits (cited to the plan-limits policy)
    ("RATE-LIMIT-FREE-01", "Free plan API rate limit per minute",
     "api_rate_limit_per_min", "==", "10", "Free", "2026-01-01", "KB-POL-LIMITS-001", "Authoritative plan limits"),
    ("RATE-LIMIT-PRO-01", "Pro plan API rate limit per minute",
     "api_rate_limit_per_min", "==", "60", "Pro", "2026-01-01", "KB-POL-LIMITS-001", "Authoritative plan limits"),
    ("RATE-LIMIT-BUSINESS-01", "Business plan API rate limit per minute",
     "api_rate_limit_per_min", "==", "300", "Business", "2026-01-01", "KB-POL-LIMITS-001", "Authoritative plan limits"),
    ("RATE-LIMIT-ENTERPRISE-01", "Enterprise plan API rate limit per minute",
     "api_rate_limit_per_min", "==", "1000", "Enterprise", "2026-01-01", "KB-POL-LIMITS-001", "Authoritative plan limits"),
    # Per-plan monthly workflow-run limits
    ("RUNS-LIMIT-FREE-01", "Free plan monthly workflow runs",
     "monthly_workflow_runs", "==", "100", "Free", "2026-01-01", "KB-POL-LIMITS-001", "Authoritative plan limits"),
    ("RUNS-LIMIT-PRO-01", "Pro plan monthly workflow runs",
     "monthly_workflow_runs", "==", "10000", "Pro", "2026-01-01", "KB-POL-LIMITS-001", "Authoritative plan limits"),
    ("RUNS-LIMIT-BUSINESS-01", "Business plan monthly workflow runs",
     "monthly_workflow_runs", "==", "100000", "Business", "2026-01-01", "KB-POL-LIMITS-001", "Authoritative plan limits"),
    ("RUNS-LIMIT-ENTERPRISE-01", "Enterprise plan monthly workflow runs",
     "monthly_workflow_runs", "==", "1000000", "Enterprise", "2026-01-01", "KB-POL-LIMITS-001", "Authoritative plan limits"),
]

COLS = ["rule_id", "description", "parameter", "operator", "value", "scope_plans",
        "effective_from", "source_id", "source_section"]


def seed() -> int:
    init_db()
    with connection() as conn:
        conn.executemany(
            f"INSERT OR REPLACE INTO policy_registry ({','.join(COLS)}) "
            f"VALUES ({','.join(['?'] * len(COLS))})",
            RULES,
        )
    return len(RULES)


if __name__ == "__main__":
    n = seed()
    print(f"Seeded {n} policy rules into policy_registry (all cited to KB-POL-* articles).")
