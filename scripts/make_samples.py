"""Generate the Section 8 sample deliverables:
  deliverables/audit_*.json      (3 full audit records, R11)
  deliverables/handoff_*.json    (2 handoff bundles, Annex D)

    python scripts/make_samples.py
Uses whatever LLM_PROVIDER is configured (.env). Run after bootstrap.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

OUT = ROOT / "deliverables"
OUT.mkdir(exist_ok=True)
c = TestClient(app)


def ask(message, account, version=None):
    body = {"message": message, "as_of_date": "2026-10-06"}
    if version:
        body["product_version"] = version
    return c.post("/support", headers={"X-Account-Id": account}, json=body).json()


SAMPLES = [
    ("audit_howto", "How do I export my workflow run history?", "A1001", None),
    ("audit_tooled_429", "Why are my API calls failing with 429 errors?", "A1003", None),
    ("audit_escalation", "Third time writing! You charged me twice this month. Get me a manager now!", "A1005", None),
]

if __name__ == "__main__":
    handoffs = []
    for i, (name, msg, acct, ver) in enumerate(SAMPLES, 1):
        r = ask(msg, acct, ver)
        audit = c.get(f"/audit/{r['trace_id']}").json()
        (OUT / f"{i}_{name}.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
        print(f"audit  -> {name}: {r['answer_type']} trace={r['trace_id']}")
        if r.get("handoff_id"):
            handoffs.append(r["handoff_id"])

    # a second handoff: a refund request
    r2 = ask("I want a refund for this month's charge.", "A1006")
    if r2.get("handoff_id"):
        handoffs.append(r2["handoff_id"])
    for j, hid in enumerate(handoffs[:2], 1):
        hb = c.get(f"/handoffs/{hid}").json()
        (OUT / f"{j}_handoff_{hid}.json").write_text(json.dumps(hb, indent=2), encoding="utf-8")
        print(f"handoff -> {hid}: {hb['queue']}/{hb['priority']}")
    print(f"\nWrote samples to {OUT}")
