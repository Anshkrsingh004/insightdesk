# Verbatim prompt — CloudFlow knowledge base

> **Disclosure (read `synthetic/data_card.md`):** In this build we executed a
> **deterministic Python generator** (`synthetic/generate_kb.py`) rather than a live
> LLM, because (a) no Ollama was available in the 4-hour window, and (b) we need the
> version conflicts, deprecation dates, and ticket-vs-documentation contradictions to
> be *exactly* controlled so the Source Precedence (Annex A) and evaluation
> requirements are precisely testable. This file is the prompt a team would feed to
> `qwen2.5:7b-instruct` / `llama3.1:8b` to regenerate equivalent content; the
> generator encodes the same structure and constraints.

## System
You are a senior technical writer producing a customer-support knowledge base for a
fictional SaaS workflow-automation product called **CloudFlow**. All content is
synthetic. Never use real company names, real people, or real personal data. Use only
`@example.com` email domains. Output must be realistic, specific, and internally
consistent.

## Product facts (must stay consistent across all documents)
- CloudFlow automates workflows made of **steps** connected to **connectors**
  (Salesforce, Slack, HTTP/webhooks, databases).
- **Versions:** `3.x` is legacy (latest 3.9), `4.x` is current (latest 4.3). Some
  features and UI paths **differ by version** — call these out explicitly.
- **Error codes:** CF-401 (auth/token), CF-403 (permission), CF-422 (validation),
  CF-429 (rate limit), CF-500 (internal), CF-503 (connector/dependency failure,
  e.g. Salesforce).
- **Plans & limits:** Free (10 API req/min, 100 runs/mo, 1 seat, $0),
  Pro (60/min, 10 000 runs, 5 seats, $49), Business (300/min, 100 000 runs, 25 seats,
  $199), Enterprise (1 000/min, 1 000 000 runs, 100 seats, $999).
- **Refund window:** 14 days. **Billing SLA:** 1 business day. **Security SLA:** 4 h.

## Produce
1. **≥30 help-center articles** (markdown) across: Getting started, Account & billing,
   API & integrations, Troubleshooting (with error-code tables), Advanced features.
   Include **version-specific** articles where 3.x and 4.x differ.
2. **4 policy articles** (doc_type=policy): Refund policy, Escalation & SLA policy,
   Plan-limits policy, Acceptable-use/out-of-scope policy. Every numeric value a tool
   needs (refund window, plan limits, SLAs, critic threshold) must appear here so it
   can be cited.
3. **≥1 release note** containing a **deprecation that takes effect on a FUTURE date**
   relative to 2026-10-06 (e.g. the legacy v3 export API).
4. **≥25 resolved support tickets** (JSON: id, customer_question, intent in
   {how_to,bug,billing,account,complaint}, resolution, tags, resolved_at,
   product_version). Among them:
   - **≥3 angry complaints** that genuinely required human escalation.
   - **≥3 whose documented workaround is now OUTDATED and contradicted by a current
     article** (so documentation must win over the ticket — Annex A authority rule).

## Rules
- Every document carries Source Register metadata (Annex B): source_id, doc_type,
  title, authority_level (articles/policy=1, release_note=2, ticket=4), product_versions,
  last_updated, effective_from, deprecated_on, supersedes, provenance, synthetic=Y.
- Outdated tickets must be dated earlier and reference a fix the current article
  explicitly reverses.
