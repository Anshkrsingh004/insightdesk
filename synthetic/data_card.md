# Synthetic Data Card — CloudFlow (Annex E)

## Purpose
Exercise the InsightDesk support system end-to-end: grounded answers over a
version-aware knowledge base, deterministic account/billing tools, source precedence
(documentation beats outdated tickets), and safe escalation. The data is built so that
every one of those behaviours has a concrete, testable case.

## Generator
- **Model:** none at runtime. Content is produced by **deterministic Python generators**
  (`synthetic/generate_kb.py`, `synthetic/generate_accounts.py`), seeded (`random.Random(42)`).
- **Why not a live LLM:** no Ollama was available in the 4-hour window, and — more
  importantly — the version conflicts, the future-dated deprecation and the
  ticket-vs-documentation contradictions must be **exactly controlled** so Source
  Precedence (Annex A) and the evaluation set are precisely testable. Free-text LLM
  output would make those cases non-deterministic.
- **AI-usage disclosure:** the generator *code* was written with an AI coding assistant
  (Claude). Verified by running the validator and inspecting outputs (see below).

## Prompts
Verbatim prompts a team would feed to `qwen2.5:7b-instruct` / `llama3.1:8b` to
regenerate equivalent content:
- `synthetic/prompts/kb_generation_prompt.md`
- `synthetic/prompts/account_generation_prompt.md`

## Schema enforcement
- Accounts/usage/invoices/plan_limits/platform_status follow the **exact Annex C**
  column names and types; the loader (`scripts/load_accounts.py`) inserts straight into
  those tables, so judges can load their own data in the same schema.
- `synthetic/validate_accounts.py` enforces id formats, enums, `@example.com` domain,
  date formats, `amount > 0`, `card_last4 ≤ 4 digits`, reserved-range avoidance, FK
  integrity, `seats_used ≤ plan seats`, and status↔invoice consistency. Run output is
  saved to `synthetic/validation_output.txt` (**RESULT: PASS, 0 violations**).

## Row counts and distributions
- **Accounts:** 30, spanning all 4 plans (Free/Pro/Business/Enterprise) and all 4
  statuses (active/past_due/suspended/cancelled).
- **Invoices:** 43 (paid / failed / refunded). **Usage:** 30 rows (period 2026-10).
- **Plan limits:** 4. **Platform status:** 4 components (connectors = degraded, INC-2041).
- **Knowledge base:** 34 articles (incl. 4 policy + 1 release note) + 25 tickets = 59
  sources. 2 product versions (3.x legacy, 4.x current).
- **Policy registry:** 12 rules, each cited to a `KB-POL-*` article.

## Edge cases included (account IDs that carry them)
| Edge case | Account(s) | Detail |
|---|---|---|
| Usage **exactly at** plan limit | **A1002** | workflow_runs = 10,000 (Pro limit) |
| **One unit over** | **A1003** | runs 10,001; api_peak 61 (> 60) |
| **Failed payment** → past_due | **A1004** | INV failed, `card_declined` |
| **Duplicate charge** | **A1005** | two $199 invoices, same day |
| Charge on **last day of refund window** + **one day after** | **A1006** | 2026-09-22 (eligible) & 2026-09-21 (just outside), vs as_of 2026-10-06 |
| **Suspended** account | **A1007** | Business, failed invoice |
| **Old product version** | **A1008** | CloudFlow 3.9 |
| Enterprise happy-path | A1009 | large usage |
| **Cancelled** account | **A1010** | refunded invoice |
| Knowledge-base conflicts (outdated ticket vs current doc) | TKT-2025-0411 / 0590 / 0633 | contradict KB-TRB-503-001 / KB-API-RATE-001 / KB-API-EXPORT-001 |
| Angry → must escalate | TKT-2026-0820 / 0845 / 0866 | duplicate-charge rage, repeated refund demand, suspended+billed |
| Future-dated deprecation | RN-2026-09-01 | v3 export API removed 2026-12-01 (announced, not yet in effect) |

## Validation results
`RESULT: PASS` — 0 hard violations, 0 soft warnings. See `synthetic/validation_output.txt`.

## What the generator got wrong (caught during the build)
- **Mis-indexed the plan tuple** so invoice `amount` initially became `"standard"`
  (support_tier) instead of the price. Caught by the validator's `amount > 0` check; fixed.
- **Emails were subdomains** (`owner@acme.example.com`) rather than the `@example.com`
  domain. Caught by the validator's domain check; fixed to `<slug>.<aid>@example.com`.
- **Free past_due/suspended accounts lacked a failed invoice** (status/invoice
  inconsistency). Caught by the consistency rule; fixed with a prior-charge failed invoice.

## Known limitations
- No reserved-range data (A9000–A9999, INV-J*, JD-*) — left free for judges.
- Usage is modelled for the current period (2026-10) only; no long historical series.
- Content is intentionally synthetic/stylised rather than scraped from real help centers.
