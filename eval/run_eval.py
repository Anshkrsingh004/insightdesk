"""Evaluation harness (Section 7). Runs the labelled set against the live pipeline and
reports: answer correctness, citation validity, retrieval hit-rate, escalation
precision/recall (confusion matrix), critic agreement, PII leakage, and latency/cost.

    python eval/run_eval.py --label default
    TOP_K=3 python eval/run_eval.py --label topk3
    CRITIC_MIN_GROUNDEDNESS=0.75 python eval/run_eval.py --label thr075
    LLM_PROVIDER=ollama python eval/run_eval.py --label ollama

Writes eval/results_<label>.json. make_report.py combines runs into report.md.
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path

import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.core import pii as pii_mod  # noqa: E402

EVAL = Path(__file__).resolve().parent / "eval_set.jsonl"


def load_cases() -> list[dict]:
    if not EVAL.exists():
        import eval.build_eval_set  # noqa
    return [json.loads(l) for l in EVAL.read_text(encoding="utf-8").splitlines() if l.strip()]


def pct(n, d):
    return round(100.0 * n / d, 1) if d else None


def run(label: str) -> dict:
    s = get_settings()
    c = TestClient(app)
    valid_sources = {x["source_id"] for x in c.get("/sources").json()["sources"]}
    threshold = s.critic_min_groundedness

    cases = load_cases()
    rows, latencies, llm_calls, tokens = [], [], [], []

    # counters
    outcome_ok = 0
    content_total = content_ok = 0
    hit_total = hit_ok = 0
    cit_total = cit_valid = 0
    conf_total = conf_ok = 0
    reason_total = reason_ok = 0
    crit_total = crit_ok = 0
    pii_leaks = 0
    tp = fp = fn = tn = 0

    for cse in cases:
        t0 = time.time()
        body = {"message": cse["message"], "as_of_date": cse.get("as_of_date")}
        if cse.get("version"):
            body["product_version"] = cse["version"]
        resp = c.post("/support", headers={"X-Account-Id": cse["account"]}, json=body).json()
        dt = (time.time() - t0) * 1000
        latencies.append(dt)

        atype = resp.get("answer_type")
        audit = {}
        if resp.get("trace_id"):
            a = c.get(f"/audit/{resp['trace_id']}")
            if a.status_code == 200:
                audit = a.json()
        retrieved = set(audit.get("sources_retrieved") or [])
        llm_calls.append(audit.get("llm_calls", 0))
        tokens.append(audit.get("tokens", 0))

        # outcome
        otype_ok = (atype == cse["expect_type"])
        if otype_ok:
            outcome_ok += 1

        # answer correctness (content)
        ans_l = (resp.get("answer") or "").lower()
        if cse.get("expect_contains"):
            content_total += 1
            if all(sub.lower() in ans_l for sub in cse["expect_contains"]):
                content_ok += 1

        # retrieval hit
        if cse.get("expect_sources"):
            hit_total += 1
            if all(src in retrieved for src in cse["expect_sources"]):
                hit_ok += 1

        # citation validity
        for cit in resp.get("citations", []):
            cit_total += 1
            if cit["source_id"] in valid_sources and (cit["source_id"] in retrieved or not retrieved):
                cit_valid += 1

        # conflict detection
        if cse.get("expect_conflict"):
            conf_total += 1
            losers = {x.get("loser_source_id") for x in resp.get("conflicts_detected", [])}
            if all(x in losers for x in cse["expect_conflict"]):
                conf_ok += 1

        # escalation confusion + reasons
        exp_esc = (cse["expect_type"] == "escalated")
        act_esc = (atype == "escalated")
        tp += exp_esc and act_esc
        fp += (not exp_esc) and act_esc
        fn += exp_esc and (not act_esc)
        tn += (not exp_esc) and (not act_esc)
        if exp_esc and cse.get("expect_reasons"):
            reason_total += 1
            actual = set((resp.get("handoff") or {}).get("escalation_reasons", []))
            if set(cse["expect_reasons"]).issubset(actual):
                reason_ok += 1

        # critic agreement (vs human_grounded label)
        if cse.get("human_grounded") is not None and resp.get("critic"):
            crit_total += 1
            verdict = (resp["critic"].get("groundedness", 0) >= threshold)
            if verdict == bool(cse["human_grounded"]):
                crit_ok += 1

        # PII leakage: scan response + audit + conversation for case PII + generic patterns
        leak = 0
        scan_blobs = [json.dumps(resp), json.dumps(audit)]
        conv = c.get(f"/conversations/{resp.get('conversation_id')}")
        if conv.status_code == 200:
            scan_blobs.append(json.dumps(conv.json()))
        for p in cse.get("pii", []):
            if any(p in b for b in scan_blobs):
                leak += 1
        # generic: raw secrets/cards in the customer-facing answer
        if pii_mod.SECRET.search(resp.get("answer", "")) or pii_mod.CARD.search(resp.get("answer", "")):
            leak += 1
        pii_leaks += leak

        rows.append({"id": cse["id"], "category": cse["category"], "expect": cse["expect_type"],
                     "got": atype, "outcome_ok": otype_ok, "latency_ms": round(dt),
                     "conflict_ok": None if not cse.get("expect_conflict") else
                     all(x in {y.get('loser_source_id') for y in resp.get('conflicts_detected', [])}
                         for x in cse["expect_conflict"]),
                     "pii_leak": leak})

    prec = pct(tp, tp + fp)
    rec = pct(tp, tp + fn)
    f1 = round(2 * prec * rec / (prec + rec), 1) if prec and rec else 0.0

    metrics = {
        "label": label,
        "config": {"provider": s.llm_provider, "model": s.ollama_model, "top_k": s.top_k,
                   "critic_min_groundedness": s.critic_min_groundedness,
                   "critic_llm": s.critic_llm, "relevance_max_distance": s.relevance_max_distance},
        "n_cases": len(cases),
        "outcome_accuracy_pct": pct(outcome_ok, len(cases)),
        "answer_correctness_pct": pct(content_ok, content_total),
        "retrieval_hit_rate_pct": pct(hit_ok, hit_total),
        "citation_validity_pct": pct(cit_valid, cit_total),
        "conflict_detection_pct": pct(conf_ok, conf_total),
        "escalation": {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
                       "precision_pct": prec, "recall_pct": rec, "f1": f1,
                       "reason_match_pct": pct(reason_ok, reason_total)},
        "critic_agreement_pct": pct(crit_ok, crit_total),
        "pii_leaks": pii_leaks,
        "latency_ms": {"p50": round(statistics.median(latencies)),
                       "p95": round(sorted(latencies)[int(0.95 * (len(latencies) - 1))]),
                       "mean": round(statistics.mean(latencies))},
        "cost": {"llm_calls_mean": round(statistics.mean(llm_calls), 2),
                 "tokens_mean": round(statistics.mean(tokens), 1)},
        "rows": rows,
    }
    out = Path(__file__).resolve().parent / f"results_{label}.json"
    out.write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    m = metrics
    print(f"\n=== EVAL [{label}] cfg={m['config']} ===")
    print(f"  outcome accuracy     {m['outcome_accuracy_pct']}%   ({len(cases)} cases)")
    print(f"  answer correctness   {m['answer_correctness_pct']}%")
    print(f"  retrieval hit rate   {m['retrieval_hit_rate_pct']}%")
    print(f"  citation validity    {m['citation_validity_pct']}%")
    print(f"  conflict detection   {m['conflict_detection_pct']}%")
    print(f"  escalation           P={prec}% R={rec}% F1={f1}  (TP{tp} FP{fp} FN{fn} TN{tn})  reasons={m['escalation']['reason_match_pct']}%")
    print(f"  critic agreement     {m['critic_agreement_pct']}%")
    print(f"  PII leaks            {pii_leaks}   (target 0)")
    print(f"  latency ms           p50={m['latency_ms']['p50']} p95={m['latency_ms']['p95']}")
    print(f"  cost                 llm_calls={m['cost']['llm_calls_mean']} tokens={m['cost']['tokens_mean']}")
    print(f"  -> {out}")
    return metrics


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="default")
    args = ap.parse_args()
    run(args.label)
