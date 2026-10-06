# InsightDesk — Self-Serve Customer Support with Safe Escalation

**HCLTech Future Ready AI Engineer Hackathon · Use Case 2** · Team **Overfitting Squad**

An agentic support assistant for the fictional SaaS product **CloudFlow**. It
classifies a customer message, retrieves grounded help content, runs deterministic
tools for account facts, composes a cited answer, **critiques its own draft**, and
then **either answers or hands off to a human** with a complete context bundle.

## Core design principle

> **LLMs produce structured signals. Deterministic code makes policy decisions.
> Tools produce facts.**

- **LLM** → intent classification, draft answer, critic scores (all Pydantic-validated)
- **Code** → Source Precedence Engine (Annex A.1/A.2), Escalation Policy Engine
  (Annex A.3), PII redaction, authorisation
- **Tools over SQLite** → every account / billing / usage / refund / status fact

The answer-or-escalate decision is **code applying the Escalation Policy to the
critic's scores** (R5), not the model.

## Status

Built in a 4-hour window. Runs fully in `LLM_PROVIDER=mock` (no model required);
Ollama is the mandated primary and a cloud LLM is a disclosed fallback.

| Phase | Status |
|---|---|
| 0 — Scaffold + API contract | ✅ |
| 1 — Knowledge base + synthetic accounts | ⏳ |
| 2 — Retrieval + cited answers | ⏳ |
| 3 — Tools + critic + escalation | ⏳ |
| 4 — Evaluation + UI + packaging | ⏳ |

## Quick start (local)

```bash
py -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.txt
cp .env.example .env            # defaults to LLM_PROVIDER=mock
./.venv/Scripts/python.exe -m uvicorn app.main:app --reload
# -> http://localhost:8000/health   http://localhost:8000/docs
```

## API (Section 6 contract)

| Endpoint | Purpose |
|---|---|
| `POST /support` | Handle a customer message (header `X-Account-Id`) |
| `POST /ingest` | Add an article or ticket while running |
| `GET /health` | Readiness of API, SQLite, vector store, LLM |
| `GET /conversations/{id}` | Conversation history + routes |
| `GET /handoffs/{id}` | Handoff bundle |
| `GET /audit/{trace_id}` | Full audit record for one response |
| `GET /sources` | Source Register |

_Architecture diagram, curl samples, assumptions, limitations and AI-usage
disclosure are completed in Phase 4._
