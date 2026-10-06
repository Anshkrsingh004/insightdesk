# Team contribution statement & declaration of original work

Team **Overfitting Squad** · InsightDesk (Use Case 2)

> Hiring decisions are individual (Section 9.4). Each member owns components below and can
> explain both their part and the system as a whole. **Fill in names and sign before submission.**

## Suggested module ownership
(Adjust to match who actually built what — this is the split we designed around.)

| Member | Primary components | Key files |
|---|---|---|
| **_____________** | **Data & KB engineering** — generators, validator, policy registry, Source Register; Source Precedence Engine | `synthetic/`, `scripts/seed_*`, `app/core/precedence.py` |
| **_____________** | **Retrieval & orchestration** — ChromaDB, chunking, LangGraph graph, classify/compose, live ingestion | `app/retrieval/`, `app/graph/build.py`, `app/graph/nodes.py` (classify/compose/retrieve) |
| **_____________** | **Tools, API & observability** — Section 6 contract, SQLite schema, 8 deterministic tools, audit/conversations | `app/api/`, `app/db.py`, `app/data/`, `app/graph/nodes.py` (tools/finalize) |
| **_____________** | **Safety, critic & evaluation** — critic + Escalation Policy Engine, PII redaction & injection backstop, eval harness, Streamlit UI | `app/core/escalation.py`, `app/core/pii.py`, `app/graph/nodes.py` (critic/escalate), `eval/`, `ui/` |

All members committed throughout the build (see `git log`).

## Declaration of original work
We declare that this project is our own original work, built during the hackathon window.
Open-source libraries are used under their licences and credited via `requirements.txt`. No
code was shared with other teams, and no real personal data is used anywhere in the system. We
used AI coding assistants as disclosed in `AI_USAGE.md` and can explain all code we submit.

| Member (print name) | Signature | Date |
|---|---|---|
| ____________________ | ____________________ | __________ |
| ____________________ | ____________________ | __________ |
| ____________________ | ____________________ | __________ |
| ____________________ | ____________________ | __________ |
