# AI-usage disclosure

Team **Overfitting Squad** · InsightDesk (Use Case 2)

Per the rules (Section 10), AI coding assistants are allowed and encouraged, and we must be
able to explain any code we submit. This document discloses how AI was used and how we
verified the output.

## What AI was used for
- **Code scaffolding and implementation.** We used an AI coding assistant (Anthropic Claude,
  via Claude Code) to help write the FastAPI app, the LangGraph nodes, the Source Precedence
  and Escalation Policy engines, the deterministic tools, the PII module, the data generators,
  and the evaluation harness. We drove the design decisions (the "LLM signals / code decisions /
  tool facts" split, code-owned escalation, deterministic critic default) and reviewed every file.
- **Synthetic data generation design.** The knowledge base and account data are produced by
  **deterministic Python generators we wrote** (with AI assistance), not by free-text LLM calls —
  chosen so version conflicts, deprecation dates and ticket-vs-doc contradictions are exactly
  controlled. The verbatim prompt a team *would* feed an LLM is in `synthetic/prompts/` for
  reproducibility (see `synthetic/data_card.md`).
- **The product's own LLM** at runtime is the local Ollama model `qwen2.5:3b-instruct`, used only
  for intent classification and answer fluency. It never produces account facts or the
  escalate/answer decision.

## How we verified the AI-generated code
- **End-to-end tests** after every phase (routing, tools, precedence, escalation, PII, ingest).
- **A 27-case evaluation** (`eval/`) with measured metrics and a confusion matrix; we fixed real
  bugs it surfaced (a mis-indexed invoice amount, subdomain emails, a false-positive escalation
  from an over-reported `explicit_human_request`, and an LLM prompt-injection that we closed with
  a code policy-risk backstop).
- **The data validator** (`synthetic/validate_accounts.py`) enforces the Annex C schema and
  logical constraints and reported `PASS` (0 violations).
- **Manual review** of every module; each team member owns and can explain their components
  (see `CONTRIBUTIONS.md`).

## What is *not* AI-decided (by design)
Source precedence, the answer-or-escalate decision, PII redaction, authorisation, and all
account/billing/refund facts are deterministic code and SQLite tools — not model output.
