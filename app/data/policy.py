"""Read values from the policy_registry. Every value is returned WITH its citation
(rule_id + source article) so answers and the escalation engine can prove where a
threshold came from (R7, and 'every value linked to a cited policy article')."""
from __future__ import annotations

from typing import Optional

from ..config import get_settings
from ..db import connection


def get_policy_value(parameter: str, plan: str = "ALL") -> Optional[dict]:
    """Prefer a plan-specific rule, else an ALL-scope rule."""
    with connection() as c:
        r = c.execute(
            "SELECT * FROM policy_registry WHERE parameter=? AND (scope_plans=? OR scope_plans='ALL') "
            "ORDER BY CASE WHEN scope_plans=? THEN 0 ELSE 1 END LIMIT 1",
            (parameter, plan, plan),
        ).fetchone()
    if not r:
        return None
    d = dict(r)
    return {"value": d["value"], "operator": d["operator"], "rule_id": d["rule_id"],
            "source_id": d["source_id"], "source_section": d["source_section"]}


def _cite(v: dict) -> dict:
    return {"rule_id": v["rule_id"], "source_id": v["source_id"], "source_section": v["source_section"]}


def get_refund_window_days() -> tuple[int, dict]:
    v = get_policy_value("refund_window_days")
    return (int(v["value"]), _cite(v)) if v else (14, {})


def get_critic_threshold() -> tuple[float, dict]:
    v = get_policy_value("critic_min_groundedness")
    return (float(v["value"]), _cite(v)) if v else (get_settings().critic_min_groundedness, {})


def get_sla_hours(kind: str) -> tuple[int, dict]:
    """kind: 'billing' or 'security'."""
    param = "billing_response_sla_hours" if kind == "billing" else "security_response_sla_hours"
    v = get_policy_value(param)
    return (int(v["value"]), _cite(v)) if v else (24, {})
