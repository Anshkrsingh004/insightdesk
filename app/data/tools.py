"""Deterministic tools over SQLite (R7). These are the ONLY source of account facts,
usage-vs-limit, invoice status, refund eligibility and platform status — never LLM
arithmetic. Refunds/credits/account changes are NEVER executed here; create_handoff
hands them to a human.

Light PII care: lookup_account masks owner_email in its returned value (the full
redaction pass over responses/bundles/logs is Phase 5). send_password_reset never
returns a token or link (R9).
"""
from __future__ import annotations

import json
import uuid
from datetime import date

from ..config import today_str
from ..db import connection
from . import policy


def _mask_email(e: str) -> str:
    if not e or "@" not in e:
        return e
    local, dom = e.split("@", 1)
    return (local[0] + "***") + "@" + dom


def _days_between(a: str, b: str) -> int:
    ya, ma, da = map(int, a.split("-"))
    yb, mb, db = map(int, b.split("-"))
    return (date(ya, ma, da) - date(yb, mb, db)).days


# ---------------------------------------------------------------------------
def lookup_account(account_id: str) -> dict | None:
    with connection() as c:
        r = c.execute("SELECT * FROM accounts WHERE account_id=?", (account_id,)).fetchone()
    if not r:
        return None
    d = dict(r)
    d["owner_email"] = _mask_email(d.get("owner_email", ""))  # do not echo PII
    return d


def get_plan_limits(plan: str) -> dict | None:
    with connection() as c:
        r = c.execute("SELECT * FROM plan_limits WHERE plan=?", (plan,)).fetchone()
    return dict(r) if r else None


def get_usage(account_id: str, period: str | None = None) -> dict:
    with connection() as c:
        if period:
            rows = c.execute("SELECT * FROM usage WHERE account_id=? AND period=?",
                             (account_id, period)).fetchall()
        else:
            rows = c.execute("SELECT * FROM usage WHERE account_id=? ORDER BY period DESC",
                             (account_id,)).fetchall()
        acc = c.execute("SELECT plan FROM accounts WHERE account_id=?", (account_id,)).fetchone()
    usage = [dict(r) for r in rows]
    limits = get_plan_limits(acc["plan"]) if acc else None
    flags = {}
    if usage and limits:
        u = usage[0]
        flags = {
            "runs_at_or_over_limit": u["workflow_runs"] >= limits["monthly_workflow_runs"],
            "runs_over_limit": u["workflow_runs"] > limits["monthly_workflow_runs"],
            "rate_over_limit": u["api_calls_peak_per_min"] > limits["api_rate_limit_per_min"],
            "seats_over_limit": u["seats_used"] > limits["seats"],
        }
    return {"usage": usage, "limits": limits, "flags": flags}


def get_invoices(account_id: str) -> list[dict]:
    with connection() as c:
        rows = c.execute("SELECT * FROM invoices WHERE account_id=? ORDER BY charged_on DESC",
                         (account_id,)).fetchall()
    return [dict(r) for r in rows]


def check_refund_eligibility(account_id: str, invoice_id: str | None = None,
                             as_of: str | None = None) -> dict:
    as_of = as_of or today_str()
    window, cite = policy.get_refund_window_days()
    invs = get_invoices(account_id)
    if invoice_id:
        invs = [i for i in invs if i["invoice_id"] == invoice_id]
    results = []
    for i in invs:
        days = _days_between(as_of, i["charged_on"])
        within = 0 <= days <= window
        results.append({
            "invoice_id": i["invoice_id"], "amount": i["amount"], "currency": i["currency"],
            "charged_on": i["charged_on"], "status": i["status"], "days_since_charge": days,
            "within_window": within,
            # eligibility is advisory; a human still approves/issues the refund
            "eligible_for_review": within and i["status"] in ("paid", "failed"),
        })
    return {"refund_window_days": window, "policy_citation": cite, "as_of_date": as_of,
            "invoices": results,
            "note": "Eligibility checked by tool. Refunds are approved and issued by a human, "
                    "never by the assistant."}


def check_platform_status(component: str | None = None) -> list[dict]:
    with connection() as c:
        if component:
            rows = c.execute("SELECT * FROM platform_status WHERE component=?", (component,)).fetchall()
        else:
            rows = c.execute("SELECT * FROM platform_status").fetchall()
    return [dict(r) for r in rows]


def send_password_reset(account_id: str) -> dict:
    """Mocked. Triggers the reset workflow to the owner email. NEVER returns a token/link."""
    with connection() as c:
        r = c.execute("SELECT account_id FROM accounts WHERE account_id=?", (account_id,)).fetchone()
    if not r:
        return {"sent": False, "reason": "account_not_found"}
    return {"sent": True, "channel": "email",
            "note": "A password-reset link was sent to the account owner's email on file. "
                    "The link and token are never shown in chat (R9)."}


def create_handoff(conversation_id: str, account_id: str | None, queue: str,
                   priority: str, bundle: dict) -> dict:
    hid = f"H-{uuid.uuid4().hex[:6]}"
    with connection() as c:
        c.execute("INSERT INTO handoffs (handoff_id, conversation_id, account_id, queue, priority, "
                  "created_at, bundle_json) VALUES (?,?,?,?,?,datetime('now'),?)",
                  (hid, conversation_id, account_id, queue, priority, json.dumps(bundle)))
    return {"handoff_id": hid, "queue": queue, "priority": priority}


# registry for the tools node
TOOLS = {
    "lookup_account": lambda aid, **k: lookup_account(aid),
    "get_plan_limits": lambda aid, **k: get_plan_limits((lookup_account(aid) or {}).get("plan", "")),
    "get_usage": lambda aid, **k: get_usage(aid),
    "get_invoices": lambda aid, **k: get_invoices(aid),
    "check_refund_eligibility": lambda aid, **k: check_refund_eligibility(aid, as_of=k.get("as_of")),
    "check_platform_status": lambda aid, **k: check_platform_status(),
    "send_password_reset": lambda aid, **k: send_password_reset(aid),
}
