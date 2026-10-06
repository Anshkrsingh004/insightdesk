"""Deterministic CloudFlow knowledge-base generator.

Writes:
  kb/articles/<id>.md       help-center articles, policy articles, release note
  kb/tickets/<id>.json      resolved support tickets
  kb/source_register.csv    Annex B register (one row per document)

Why deterministic (not a live LLM): we need the version differences, the future-dated
deprecation, and the ticket-vs-documentation contradictions to be *exactly* controlled
so Source Precedence (Annex A) and the evaluation set are precisely testable. See
synthetic/data_card.md and synthetic/prompts/kb_generation_prompt.md.

Run:  python synthetic/generate_kb.py
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KB = ROOT / "kb"
ART = KB / "articles"
TKT = KB / "tickets"

PROV = "generator: synthetic/generate_kb.py (deterministic); prompt: synthetic/prompts/kb_generation_prompt.md"
AS_OF_HINT = "2026-10-06"  # deprecation is future-dated relative to this

# ---------------------------------------------------------------------------
# Register row helper
# ---------------------------------------------------------------------------
REGISTER_COLS = [
    "source_id", "doc_type", "title", "authority_level", "product_versions",
    "last_updated", "effective_from", "deprecated_on", "supersedes",
    "provenance", "synthetic",
]


def row(source_id, doc_type, title, authority_level, product_versions,
        last_updated, effective_from="", deprecated_on="", supersedes=""):
    return {
        "source_id": source_id, "doc_type": doc_type, "title": title,
        "authority_level": authority_level, "product_versions": product_versions,
        "last_updated": last_updated, "effective_from": effective_from,
        "deprecated_on": deprecated_on, "supersedes": supersedes,
        "provenance": PROV, "synthetic": "Y",
    }


register: list[dict] = []
articles: list[tuple[str, str]] = []   # (source_id, markdown body)
tickets: list[dict] = []               # ticket JSON objects


def article(source_id, title, category, versions, last_updated, body,
            doc_type="article", authority=1, effective_from="", deprecated_on="",
            supersedes=""):
    md = f"# {title}\n\n_CloudFlow help center · {category} · applies to {versions}_\n\n{body.strip()}\n"
    articles.append((source_id, md))
    register.append(row(source_id, doc_type, title, authority, versions,
                        last_updated, effective_from, deprecated_on, supersedes))


def ticket(source_id, subject, question, intent, resolution, tags, resolved_at,
           product_version, outdated=False, conflicts_with="", angry=False,
           required_human=False):
    obj = {
        "id": source_id, "subject": subject, "customer_question": question,
        "intent": intent, "resolution": resolution, "tags": tags,
        "resolved_at": resolved_at, "product_version": product_version,
        "outdated": outdated, "conflicts_with": conflicts_with,
        "angry": angry, "required_human": required_human,
    }
    tickets.append(obj)
    register.append(row(source_id, "ticket", subject, 4, product_version, resolved_at))


# ===========================================================================
# HERO ARTICLES (hand-authored; these are what demo + judges hit)
# ===========================================================================

article(
    "KB-HOW-EXPORT-001", "Export your workflow run history", "Getting started",
    "3.x;4.x", "2026-09-10",
    """
## Overview
You can export the run history of any workflow as a CSV for reporting or audits. The
steps differ between CloudFlow 3.x and 4.x.

## Steps (CloudFlow 4.x) — current
1. Open **Workflows** and select the workflow.
2. Click the **Run History** tab.
3. Click **Export → CSV** in the top-right.
4. Choose a date range and click **Download**. Large exports are emailed as a link.

## Steps (CloudFlow 3.x) — legacy
1. Open the workflow and go to **Activity**.
2. Use **More → Download runs**. Only the last 90 days are available in 3.x.

## Version notes
- In 4.x the menu is **Run History → Export**; in 3.x it is **Activity → Download runs**.
- The programmatic export endpoint changed in 4.x — see *Export runs via the API* (KB-API-EXPORT-001).

## Related
- KB-API-EXPORT-001 Export runs via the API
- KB-ADV-VERSIONS-001 What changed between CloudFlow 3.x and 4.x
""",
)

article(
    "KB-TRB-503-001", "Resolve CF-503 errors on a Salesforce step", "Troubleshooting",
    "4.x", "2026-09-18",
    """
## Symptom
A Salesforce step fails with **CF-503 (connector dependency unavailable)**. The run
stops and shows `CF-503: upstream connector returned 503`.

## Cause
In CloudFlow 4.x, CF-503 on a Salesforce step is almost always an **expired or revoked
OAuth connection**, not an API-version mismatch.

## Fix (CloudFlow 4.x) — current
1. Go to **Settings → Connectors → Salesforce**.
2. Click **Re-authorise** and complete the OAuth login.
3. Re-run the workflow.

> **Important:** Do **not** manually edit the Salesforce API version in the step config.
> That was a CloudFlow 3.x workaround. In 4.x the API version is managed automatically
> and editing it will break the step. (This supersedes older guidance in ticket
> TKT-2025-0411.)

## Error-code quick reference
| Code | Meaning | First action |
|------|---------|--------------|
| CF-401 | Auth/token invalid | Rotate or re-authorise the connector |
| CF-429 | Rate limit exceeded | See KB-API-RATE-001 |
| CF-503 | Connector dependency down | Re-authorise the connector (above) |

## Related
- KB-API-TOKENS-001 API authentication and tokens
""",
)

article(
    "KB-API-RATE-001", "API rate limits and CF-429 / HTTP 429 errors",
    "API & integrations", "3.x;4.x", "2026-09-22",
    """
## Overview
CloudFlow enforces a **per-minute API rate limit** that depends on your plan. Exceeding
it returns **HTTP 429** (CloudFlow code **CF-429**).

## Per-plan limits
| Plan | API requests / minute | Monthly workflow runs |
|------|-----------------------|-----------------------|
| Free | 10 | 100 |
| Pro | 60 | 10,000 |
| Business | 300 | 100,000 |
| Enterprise | 1,000 | 1,000,000 |

These are the authoritative limits (see policy KB-POL-LIMITS-001).

## What to do about 429s — current guidance
1. **Add exponential backoff** with jitter and honour the `Retry-After` header.
2. **Batch** requests where possible instead of polling tightly.
3. If you are legitimately at capacity, **upgrade your plan** for a higher limit.

> Support does **not** permanently raise an account's rate limit outside of its plan.
> Any temporary increase recorded in an old ticket (e.g. TKT-2025-0590) was a one-off
> incident mitigation and is not a supported configuration.

## Related
- KB-POL-LIMITS-001 Plan limits policy
- KB-ACC-USAGE-001 Check your usage against plan limits
""",
)

article(
    "KB-BIL-DUP-001", "Duplicate charges on your invoice", "Account & billing",
    "all", "2026-09-05",
    """
## Overview
A duplicate charge is two invoices for the **same amount on the same day** for your
account. CloudFlow's billing system occasionally retries a payment and can create a
duplicate during an outage.

## What we do
1. Our billing team verifies the two invoices (same amount, same `charged_on`).
2. If confirmed, the duplicate is refunded to the original card.
3. Refunds are **approved and issued by a human** in billing — the assistant cannot
   issue refunds. See the refund policy (KB-POL-REFUND-001).

## What you can do
- Note both invoice IDs. The support assistant can look them up and attach them to a
  billing handoff with the evidence, but the refund itself requires billing approval.

## Related
- KB-POL-REFUND-001 Refund policy
- KB-BIL-FAILED-001 Failed payments and past_due status
""",
)

article(
    "KB-API-EXPORT-001", "Export runs via the API", "API & integrations",
    "3.x;4.x", "2026-09-12",
    """
## Overview
You can export workflow runs programmatically.

## CloudFlow 4.x — current endpoint
`GET /api/v4/workflows/{id}/runs/export?format=csv&from=YYYY-MM-DD&to=YYYY-MM-DD`
Authenticated with a Bearer API token (see KB-API-TOKENS-001).

## CloudFlow 3.x — legacy endpoint (being deprecated)
`GET /api/v3/export/runs?workflow={id}` still works today but is **deprecated** and will
be removed — see release note **RN-2026-09-01**. Migrate to the v4 endpoint above.

## Related
- RN-2026-09-01 Deprecation of the legacy v3 export API
- KB-HOW-EXPORT-001 Export your workflow run history (UI)
""",
)

article(
    "RN-2026-09-01", "Release note: deprecation of the legacy v3 export API",
    "Release notes", "3.x", "2026-09-15",
    doc_type="release_note", authority=2,
    effective_from="2026-09-15", deprecated_on="2026-12-01",
    supersedes="",
    body="""
## Summary
The legacy **v3 export API** (`GET /api/v3/export/runs`) is **deprecated as of
2026-09-15** and will be **removed on 2026-12-01**. Until then it continues to work.

## Action required
Migrate to the v4 export endpoint: `GET /api/v4/workflows/{id}/runs/export`
(see KB-API-EXPORT-001). After 2026-12-01, calls to the v3 endpoint will return CF-410.

## Notes
- As of today (2026-10-06) the deprecation has been **announced but has not yet taken
  effect** — v3 still responds. Mention the upcoming removal date when advising users.
""",
)

article(
    "KB-SEC-TOKENS-001", "Rotate API tokens and reset your password",
    "API & integrations", "all", "2026-09-20",
    """
## Rotate an API token
1. Go to **Settings → API tokens**.
2. Click **Rotate** next to the token. The new token is shown **once** — store it in a
   secret manager.
3. Update your integrations with the new token.

## Reset your password
Use **Sign in → Forgot password**. CloudFlow emails a reset link to the account owner.

> **Security:** Support never sends a password-reset link or token in a chat or ticket.
> The assistant can *trigger* the reset workflow to the account owner's email, but it
> will **never display the token or link**. Never share a full API token with support.

## Related
- KB-POL-ESCALATION-001 Escalation and SLA policy (security SLA)
""",
)

article(
    "KB-ACC-USAGE-001", "Check your usage against plan limits", "Account & billing",
    "all", "2026-09-08",
    """
## Overview
See how much of your plan you've used this month under **Settings → Usage**.

## What counts
- **Workflow runs** this period vs your plan's monthly limit.
- **Peak API requests per minute** vs your plan's per-minute limit (429s happen when
  this is exceeded — see KB-API-RATE-001).
- **Seats used** vs seats included.

When you are **at or over** a limit, workflows may be throttled or queued. The support
assistant reads these numbers from your account with a tool — it does not estimate them.

## Related
- KB-API-RATE-001 API rate limits and 429 errors
- KB-POL-LIMITS-001 Plan limits policy
""",
)

# --- Policy articles (doc_type=policy, authority 1; values go to policy_registry) ---

article(
    "KB-POL-REFUND-001", "Refund policy", "Policy", "all", "2026-08-01",
    doc_type="policy", authority=1,
    body="""
## Refund window
CloudFlow issues refunds for charges made within the last **14 days** (the *refund
window*). Requests outside the window are reviewed case-by-case by billing.

## How refunds are handled
- Eligibility is checked by a **tool** against the invoice date and status.
- Refunds, credits and account changes are **executed by a human** in billing, never by
  the assistant. The assistant may prepare a billing handoff with the invoice evidence.

## Registry values
- `refund_window_days = 14` (rule REFUND-WINDOW-01).
""",
)

article(
    "KB-POL-LIMITS-001", "Plan limits policy", "Policy", "all", "2026-08-01",
    doc_type="policy", authority=1,
    body="""
## Authoritative plan limits
| Plan | API req/min | Monthly runs | Seats | Support tier | Price (USD/mo) |
|------|-------------|--------------|-------|--------------|----------------|
| Free | 10 | 100 | 1 | community | 0 |
| Pro | 60 | 10,000 | 5 | standard | 49 |
| Business | 300 | 100,000 | 25 | priority | 199 |
| Enterprise | 1,000 | 1,000,000 | 100 | priority | 999 |

These values are the source of truth for the `plan_limits` table and the
`api_rate_limit_per_min` / `monthly_workflow_runs` registry rules. Support does not
raise limits outside the plan (see KB-API-RATE-001).
""",
)

article(
    "KB-POL-ESCALATION-001", "Escalation and SLA policy", "Policy", "all", "2026-08-01",
    doc_type="policy", authority=1,
    body="""
## When the assistant hands off to a human
Escalation is decided **in code** from the classifier and critic signals (Annex A.3):
- Groundedness below the threshold after one revision.
- Intent is a **refund, credit, billing dispute, legal matter, security incident or
  account deletion**.
- The customer **explicitly asks for a human**, or shows strong negative sentiment with
  repeated contact.
- A required **tool has failed**, or the knowledge base does not cover the question and
  the customer needs an outcome.

The assistant does **not** escalate answerable how-to / troubleshooting requests with
high groundedness and no policy risk — unnecessary escalation is a failure.

## SLAs
- Billing handoffs: first response within **1 business day (24 h)**.
- Security handoffs: first response within **4 hours**.

## Registry values
- `critic_min_groundedness = 0.6` (CRITIC-MIN-GROUNDEDNESS-01)
- `billing_response_sla_hours = 24` (ESCALATION-SLA-BILLING-01)
- `security_response_sla_hours = 4` (ESCALATION-SLA-SECURITY-01)
""",
)

article(
    "KB-POL-AUP-001", "Acceptable use and scope of support", "Policy", "all",
    "2026-08-01", doc_type="policy", authority=1,
    body="""
## In scope
Questions about using CloudFlow: workflows, connectors, the API, billing, account and
usage.

## Out of scope
- Integrations CloudFlow does not offer (the assistant says so and offers a handoff; it
  does not invent an answer).
- Requests unrelated to CloudFlow support (e.g. "write me a poem") are politely declined.
- Another account's data is **refused**; the account is taken only from the
  `X-Account-Id` header, never from the message text.
""",
)

article(
    "KB-ADV-VERSIONS-001", "What changed between CloudFlow 3.x and 4.x",
    "Advanced features", "3.x;4.x", "2026-09-01",
    """
## Key differences
| Area | CloudFlow 3.x | CloudFlow 4.x |
|------|---------------|---------------|
| Run history export | Activity → Download runs (90 days) | Run History → Export (full) |
| Export API | `/api/v3/export/runs` (deprecated) | `/api/v4/.../runs/export` |
| Salesforce CF-503 fix | Edit API version in step | Re-authorise connector |
| Connectors UI | Integrations tab | Settings → Connectors |
| Conditional branching | Basic | Advanced (nested, sub-workflows) |

## Upgrading
Most 3.x workflows import into 4.x automatically. Review any step that hard-codes an API
version, as 4.x manages versions for you.
""",
)

article(
    "KB-TRB-REF-001", "CloudFlow error-code reference", "Troubleshooting", "all",
    "2026-09-25",
    """
## Error codes
| Code | Category | Meaning | First action |
|------|----------|---------|--------------|
| CF-401 | Auth | API token invalid/expired | Rotate token (KB-SEC-TOKENS-001) |
| CF-403 | Auth | Insufficient permission | Check the connector's scopes |
| CF-422 | Validation | Step config invalid | Fix the highlighted field |
| CF-429 | Limits | Rate limit exceeded | Backoff / upgrade (KB-API-RATE-001) |
| CF-500 | Server | Internal error | Retry; if persistent, contact support |
| CF-503 | Connector | Dependency unavailable | Re-authorise connector (KB-TRB-503-001) |
| CF-410 | Deprecation | Endpoint removed | Migrate (see release notes) |

Always cite the specific code article for the fix rather than guessing.
""",
)

# ===========================================================================
# FILLER ARTICLES (templated across categories to exceed 30; realistic)
# ===========================================================================
FILLERS = [
    ("KB-GS-001", "Create your CloudFlow account", "Getting started", "all",
     "sign up, verify your email, and choose a plan", "Settings → Account"),
    ("KB-GS-002", "Build your first workflow", "Getting started", "all",
     "add a trigger, add steps, and connect them in order", "Workflows → New"),
    ("KB-GS-003", "Add a connector", "Getting started", "4.x",
     "authorise Salesforce, Slack or an HTTP connector", "Settings → Connectors"),
    ("KB-GS-004", "Schedule a workflow", "Getting started", "all",
     "set a cron schedule or interval trigger", "Workflow → Triggers"),
    ("KB-GS-005", "Invite team members and manage seats", "Getting started", "all",
     "invite users up to your plan's seat limit", "Settings → Team"),
    ("KB-BIL-FAILED-001", "Failed payments and past_due status", "Account & billing", "all",
     "update your card to clear a failed charge and restore active status", "Settings → Billing"),
    ("KB-BIL-UPG-001", "Upgrade or downgrade your plan", "Account & billing", "all",
     "change plans; limits apply immediately and billing is prorated", "Settings → Billing"),
    ("KB-BIL-SEATS-001", "Add or remove seats", "Account & billing", "all",
     "adjust seats within your plan maximum", "Settings → Team"),
    ("KB-API-TOKENS-001", "API authentication and tokens", "API & integrations", "all",
     "create a Bearer token and authenticate API calls", "Settings → API tokens"),
    ("KB-API-WEBHOOK-001", "Set up webhooks", "API & integrations", "4.x",
     "register a webhook URL and verify the signature", "Settings → Webhooks"),
    ("KB-API-SF-001", "Salesforce connector setup", "API & integrations", "4.x",
     "authorise Salesforce via OAuth and map objects", "Settings → Connectors"),
    ("KB-API-SLACK-001", "Slack connector setup", "API & integrations", "all",
     "connect a Slack workspace and post to channels", "Settings → Connectors"),
    ("KB-TRB-401-001", "Fix CF-401 authentication errors", "Troubleshooting", "all",
     "rotate the API token and re-authenticate", "Settings → API tokens"),
    ("KB-TRB-422-001", "Fix CF-422 validation errors", "Troubleshooting", "all",
     "correct the invalid step field shown in the error", "Workflow editor"),
    ("KB-TRB-500-001", "Fix CF-500 internal errors", "Troubleshooting", "all",
     "retry the run; if it persists, open a ticket with the run ID", "Run History"),
    ("KB-TRB-QUEUE-001", "Workflow runs stuck in queued", "Troubleshooting", "all",
     "check platform status and your plan's run limit", "Run History"),
    ("KB-TRB-SYNC-001", "Connector sync failures", "Troubleshooting", "4.x",
     "re-authorise the connector and re-run the sync", "Settings → Connectors"),
    ("KB-ADV-BRANCH-001", "Conditional branching", "Advanced features", "4.x",
     "add if/else branches based on step output", "Workflow editor"),
    ("KB-ADV-SUB-001", "Sub-workflows", "Advanced features", "4.x",
     "call one workflow from another and pass data", "Workflow editor"),
    ("KB-ADV-AUDIT-001", "Audit logs and exports", "Advanced features", "4.x",
     "export admin audit logs for compliance", "Settings → Audit"),
]

for sid, title, cat, ver, action, where in FILLERS:
    body = f"""
## Overview
This article explains how to {action} in CloudFlow.

## Steps
1. Open **{where}**.
2. Follow the on-screen prompts to {action}.
3. Save your changes and verify the result.

## Notes
- Available on {ver}. If you are on an older version, some menus may differ — see
  KB-ADV-VERSIONS-001.

## Related
- KB-GS-002 Build your first workflow
"""
    article(sid, title, cat, ver, "2026-09-02", body)

# ===========================================================================
# TICKETS — 3 angry (require human), 3 outdated (contradict current docs), + normal
# ===========================================================================

# --- OUTDATED / CONFLICTING (authority 4, must lose to current articles) ---
ticket("TKT-2025-0411", "CF-503 on Salesforce step",
       "My Salesforce step keeps failing with CF-503.", "bug",
       "Workaround: manually set the Salesforce API version to 48.0 in the step config. "
       "That cleared the CF-503 for this customer.",
       ["cf-503", "salesforce", "connector"], "2025-07-14", "4.x",
       outdated=True, conflicts_with="KB-TRB-503-001")

ticket("TKT-2025-0590", "API returning 429 constantly",
       "Why are my API calls failing with 429 errors?", "bug",
       "We temporarily raised this account's per-minute rate limit above the Pro plan to "
       "unblock them during an incident.",
       ["cf-429", "rate-limit", "api"], "2025-09-02", "4.x",
       outdated=True, conflicts_with="KB-API-RATE-001")

ticket("TKT-2025-0633", "Export runs via API",
       "How do I export workflow runs with the API?", "how_to",
       "Use GET /api/v3/export/runs?workflow={id}. Works fine.",
       ["export", "api", "v3"], "2025-10-20", "3.x;4.x",
       outdated=True, conflicts_with="KB-API-EXPORT-001")

# --- ANGRY COMPLAINTS (required human escalation) ---
ticket("TKT-2026-0820", "Charged twice — get me a manager",
       "Third time writing. You charged me twice this month. Get me a manager now.",
       "complaint",
       "Escalated to billing. Confirmed duplicate charge, billing approved and issued a "
       "refund for the second invoice. Customer apologised to.",
       ["billing", "duplicate", "angry", "refund"], "2026-09-28", "4.x",
       angry=True, required_human=True)

ticket("TKT-2026-0845", "Refund now or I cancel",
       "I've asked three times for a refund and nobody replies. Refund me today or I'm "
       "cancelling and disputing the charge.", "complaint",
       "Escalated to billing with prior-contact history. Billing reviewed eligibility and "
       "processed the refund; retention followed up.",
       ["billing", "refund", "angry", "repeated-contact"], "2026-09-30", "4.x",
       angry=True, required_human=True)

ticket("TKT-2026-0866", "Locked out and still billed",
       "My account is suspended but you're still billing me. This is unacceptable, I want "
       "a human right now.", "complaint",
       "Escalated to billing + account team. Reviewed suspension and invoice, corrected "
       "billing, restored access after verification.",
       ["account", "suspended", "billing", "angry"], "2026-10-01", "4.x",
       angry=True, required_human=True)

# --- NORMAL RESOLVED TICKETS (historical, lower authority, still useful) ---
NORMAL = [
    ("TKT-2026-0701", "How to add a Slack connector", "How do I post workflow results to Slack?",
     "how_to", "Walked them through Settings → Connectors → Slack and channel mapping.",
     ["slack", "connector"], "2026-08-11", "4.x"),
    ("TKT-2026-0702", "Schedule a nightly workflow", "Can I run a workflow every night at 2am?",
     "how_to", "Showed cron trigger 0 2 * * * under Workflow → Triggers.",
     ["schedule", "cron"], "2026-08-12", "4.x"),
    ("TKT-2026-0703", "Upgrade from Pro to Business", "How do I upgrade to Business?",
     "account", "Upgraded via Settings → Billing; limits applied immediately.",
     ["billing", "upgrade"], "2026-08-15", "4.x"),
    ("TKT-2026-0704", "CF-401 after token change", "Getting CF-401 after I rotated my token.",
     "bug", "Updated the integration with the new token; CF-401 cleared.",
     ["cf-401", "token"], "2026-08-18", "4.x"),
    ("TKT-2026-0705", "Invite a teammate", "How do I invite a colleague?",
     "how_to", "Settings → Team → Invite; seat available on Pro.",
     ["team", "seats"], "2026-08-20", "4.x"),
    ("TKT-2026-0706", "Webhook signature failing", "My webhook verification fails.",
     "bug", "Pointed them to the signing-secret header; verification passed.",
     ["webhook", "api"], "2026-08-22", "4.x"),
    ("TKT-2026-0707", "Downgrade to Free", "Can I move to the Free plan?",
     "account", "Downgraded; noted reduced limits (100 runs/mo).",
     ["billing", "downgrade"], "2026-08-24", "4.x"),
    ("TKT-2026-0708", "CF-422 on HTTP step", "CF-422 when I save my HTTP step.",
     "bug", "Fixed the malformed URL field flagged by CF-422.",
     ["cf-422", "http"], "2026-08-26", "4.x"),
    ("TKT-2026-0709", "Where is run history", "Where do I find past runs?",
     "how_to", "Run History tab on the workflow (4.x).",
     ["runs", "history"], "2026-08-28", "4.x"),
    ("TKT-2026-0710", "Add seats", "I need two more seats.",
     "account", "Added seats within Business plan maximum.",
     ["seats", "team"], "2026-08-30", "4.x"),
    ("TKT-2026-0711", "Connector OAuth expired", "Salesforce stopped syncing.",
     "bug", "Re-authorised the Salesforce connector; sync resumed.",
     ["salesforce", "oauth"], "2026-09-01", "4.x"),
    ("TKT-2026-0712", "Change owner email", "How do I change the account owner email?",
     "account", "Updated owner email under Settings → Account.",
     ["account", "email"], "2026-09-03", "4.x"),
    ("TKT-2026-0713", "Export to CSV", "Can I export runs to CSV?",
     "how_to", "Run History → Export → CSV (4.x).",
     ["export", "csv"], "2026-09-04", "4.x"),
    ("TKT-2026-0714", "Rate limit on Free", "I hit 429 on the Free plan quickly.",
     "bug", "Explained Free is 10 req/min; suggested backoff or upgrade.",
     ["cf-429", "free"], "2026-09-06", "4.x"),
    ("TKT-2026-0715", "Sub-workflow data passing", "How do I pass data to a sub-workflow?",
     "how_to", "Mapped parent outputs to sub-workflow inputs.",
     ["sub-workflow", "advanced"], "2026-09-08", "4.x"),
    ("TKT-2026-0716", "Past due after card expiry", "My card expired and I'm past_due.",
     "billing", "Updated card; failed invoice retried and paid; status back to active.",
     ["past_due", "billing"], "2026-09-10", "4.x"),
    ("TKT-2026-0717", "Audit log export", "Can I export audit logs?",
     "how_to", "Settings → Audit → Export (Business/Enterprise).",
     ["audit", "export"], "2026-09-12", "4.x"),
    ("TKT-2026-0718", "Conditional branch", "How do I branch on a value?",
     "how_to", "Added if/else branch in the editor (4.x).",
     ["branching", "advanced"], "2026-09-14", "4.x"),
    ("TKT-2026-0719", "Reset password", "I forgot my password.",
     "account", "Directed to Sign in → Forgot password; reset link emailed to owner.",
     ["password", "security"], "2026-09-16", "4.x"),
]
for sid, subj, q, intent, res, tags, when, ver in NORMAL:
    ticket(sid, subj, q, intent, res, tags, when, ver)


# ===========================================================================
# WRITE EVERYTHING
# ===========================================================================
def write() -> dict:
    ART.mkdir(parents=True, exist_ok=True)
    TKT.mkdir(parents=True, exist_ok=True)
    for sid, md in articles:
        (ART / f"{sid}.md").write_text(md, encoding="utf-8")
    for obj in tickets:
        (TKT / f"{obj['id']}.json").write_text(json.dumps(obj, indent=2), encoding="utf-8")
    with (KB / "source_register.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=REGISTER_COLS)
        w.writeheader()
        w.writerows(register)
    n_articles = sum(1 for r in register if r["doc_type"] in ("article", "policy", "release_note"))
    n_tickets = sum(1 for r in register if r["doc_type"] == "ticket")
    return {
        "articles_md": len(articles),
        "articles_incl_policy_release": n_articles,
        "tickets": n_tickets,
        "angry": sum(1 for t in tickets if t["angry"]),
        "outdated": sum(1 for t in tickets if t["outdated"]),
        "register_rows": len(register),
    }


if __name__ == "__main__":
    stats = write()
    print("KB generated:")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    print(f"  -> {ART}")
    print(f"  -> {TKT}")
    print(f"  -> {KB / 'source_register.csv'}")
