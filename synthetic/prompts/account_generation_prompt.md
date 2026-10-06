# Verbatim prompt — synthetic customer-account data (Annex C schema)

> **Disclosure:** executed via `synthetic/generate_accounts.py` (deterministic, seeded)
> so the required edge cases land on known account IDs and validation is reproducible.
> This is the prompt a team would feed to an LLM for the same structured output; our
> generator enforces the identical schema and constraints in code (stronger schema
> discipline than free-text LLM output).

## System
Generate synthetic customer-account data for CloudFlow in the **exact Annex C SQLite
schema**. All data is fake. Emails use `@example.com` only. Store **only card last-4
digits**, never full card numbers. Amounts are positive. Do not use reserved ranges:
account IDs `A9000–A9999`, invoice IDs starting `INV-J`, source IDs starting `JD-`.

## Tables & columns (do not rename/remove)
- accounts(account_id 'A'+4 digits, company_name, owner_email, plan
  {Free|Pro|Business|Enterprise}, status {active|past_due|suspended|cancelled},
  product_version, created_at)
- plan_limits(plan PK, api_rate_limit_per_min, monthly_workflow_runs, seats,
  support_tier, monthly_price)
- usage(account_id, period YYYY-MM, workflow_runs, api_calls_peak_per_min, seats_used)
- invoices(invoice_id, account_id, amount>0, currency, charged_on, status
  {paid|failed|refunded}, failure_reason empty-unless-failed, card_last4)
- platform_status(component, status {operational|degraded|outage}, incident_id, updated_at)

## Requirements
- **≥30 accounts** spanning all 4 plans and all 4 statuses.
- Deliberate **edge cases**, each tagged to a specific account ID in the data card:
  usage **exactly at** a plan limit; **one unit over**; a **failed payment**; a
  **duplicate charge** (two identical invoices, same day); a charge on the **last day of
  the refund window** and **one day after**; a **suspended** account; an account on an
  **old product version** (3.x).
- **Logical consistency:** `past_due`/`suspended` accounts have a `failed` invoice;
  `seats_used ≤ plan seats`; invoice currency/amount plausible for the plan.

## Output
Five CSVs (accounts, plan_limits, usage, invoices, platform_status) in `test_accounts/`,
loadable by `python scripts/load_accounts.py --dir test_accounts/`.
