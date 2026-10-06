# InsightDesk — Evaluation Report (Section 7)

Team **Overfitting Squad** · CloudFlow self-serve support with safe escalation.

## Method

A labelled set of **27 requests** (`eval/eval_set.jsonl`) is replayed through the live `POST /support` pipeline by `eval/run_eval.py`. Each case carries an expected outcome (answer_type, expected sources/substrings, or escalation reasons). We measure answer correctness, citation validity, retrieval hit-rate, escalation precision/recall against the labels, critic agreement, PII leakage, and latency/cost. Results are reproducible: `mock` mode is deterministic; `ollama` runs use `qwen2.5:3b-instruct` locally.

## Eval set composition

| Category | Cases |
|---|---|
| conflict | 3 |
| cross_account | 2 |
| escalate | 5 |
| how_to | 6 |
| out_of_scope | 2 |
| pii | 2 |
| tool_billing | 4 |
| version_specific | 3 |

Covers the Section 7 minimums: ≥5 answerable how-to + 3 version-specific, ≥3 outdated-ticket conflicts, ≥4 account/billing (tools), ≥4 must-escalate, ≥2 PII, 2 out-of-scope, 2 cross-account.

## Results & configuration comparison

| Config | mode | params | Outcome | Retr.hit | Cite | Conflict | Esc P/R | CriticAgr | PII leaks | Latency p50/p95 ms | LLMcalls/tokens |
|---|---|---|---|---|---|---|---|---|---|---|---|
| default | mock/code-crit | k=5 thr=0.6 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0%/100.0% | 100.0% | 0 | 235/270 | 0/0 |
| topk3 | mock/code-crit | k=3 thr=0.6 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0%/100.0% | 100.0% | 0 | 179/203 | 0/0 |
| thr075 | mock/code-crit | k=5 thr=0.75 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0%/100.0% | 87.5% | 0 | 178/192 | 0/0 |
| ollama | ollama/code-crit | k=5 thr=0.6 | 96.3% | 100.0% | 99.0% | 100.0% | 100.0%/100.0% | 93.8% | 0 | 9912/13747 | 1.81/704.6 |
| ollama_criticllm | ollama/llm-crit | k=5 thr=0.6 | 77.8% | 100.0% | 99.0% | 100.0% | 45.5%/100.0% | 68.8% | 0 | 21194/25754 | 3.89/552.7 |

## Findings and final choice

- **PII leakage = 0** across all responses, bundles and logs (target zero) — customer-supplied emails/cards/secrets and account emails are redacted everywhere.
- **Escalation is well-calibrated**: precision 100.0%, recall 100.0% (no over- or under-escalation on the set); escalation reasons matched 100.0% of the time.
- **Grounding**: retrieval hit-rate 100.0%, citation validity 100.0%, outdated-ticket conflict detection 100.0%.
- **Critic threshold** 0.6 vs 0.75: critic agreement 100.0% vs 87.5% — 0.75 is too strict and disagrees with human grounding judgements. **Chose 0.6.**
- **top_k** 3 vs 5: retrieval hit-rate 100.0% vs 100.0% — k=3 is already sufficient on this KB; we keep k=5 for headroom on live-ingested content (simplest design that still meets the need).
- **Critic: deterministic vs LLM self-critique** (both on `qwen2.5:3b`): escalation precision 100.0% (code) vs 45.5% (LLM), outcome accuracy 96.3% vs 77.8%, latency p50 9912ms vs 21194ms. The small LLM judge **over-escalates grounded answers** and costs an extra call, so we default to the **deterministic critic**. (`CRITIC_LLM=true` enables the LLM critic.)
- **Latency/cost (local qwen2.5:3b, CPU)**: p50 9912ms, p95 13747ms, 1.81 LLM calls and 704.6 tokens per request on average. `mock` mode responds in ~235ms for routing/tool/escalation tests.

**Final configuration:** mock-capable pipeline; local `qwen2.5:3b-instruct` for fluency; top_k=5; deterministic critic; critic groundedness floor 0.6; relevance gate 0.58. Every number above is reproducible via `eval/run_eval.py`.

## Per-category outcome (primary config)

| Category | Cases | Outcome correct |
|---|---|---|
| conflict | 3 | 3/3 |
| cross_account | 2 | 2/2 |
| escalate | 5 | 5/5 |
| how_to | 6 | 6/6 |
| out_of_scope | 2 | 2/2 |
| pii | 2 | 2/2 |
| tool_billing | 4 | 4/4 |
| version_specific | 3 | 3/3 |
