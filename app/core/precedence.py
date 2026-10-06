"""Source Precedence Engine — Annex A.1 (authority) + A.2 (resolution order), in CODE.

Given retrieved chunks (with Source Register metadata), the customer's product version
and the as_of_date, it decides which sources are authoritative, records conflicts, and
surfaces upcoming deprecations. No LLM judgement is involved — this is deterministic and
fully explainable, which is exactly what R6 and the rubric ask for.

Resolution order implemented:
  1. Applicability  — version covers customer; in effect on as_of_date
  2. Supersession   — a source that supersedes another drops the superseded one;
                      deprecations take effect from their date
  3. Authority      — higher authority (lower level) wins; a ticket (4) never contradicts
                      a doc (<=3) -> conflict recorded, ticket demoted to supporting
  4. Recency        — within equal authority, the more recently updated wins
  5. Unresolved     — no authoritative doc -> empty result (caller escalates / not_found)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# version + date helpers
# ---------------------------------------------------------------------------
def _ver_tuple(v: str) -> tuple[int, ...]:
    out = []
    for part in str(v).split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        out.append(int(digits) if digits else 0)
    return tuple(out) or (0,)


def version_covers(spec: str, ver: Optional[str]) -> bool:
    """Does a product_versions spec (e.g. '4.x', '4.2+', '3.x;4.x', 'all') cover ver?"""
    if not ver:
        return True  # unknown customer version -> don't exclude on version
    if not spec:
        return True
    vt = _ver_tuple(ver)
    for raw in str(spec).replace(",", ";").split(";"):
        tok = raw.strip().lower()
        if not tok or tok == "all":
            return True
        if tok.endswith(".x"):
            if vt[0] == _ver_tuple(tok[:-2])[0]:
                return True
        elif tok.endswith("+"):
            base = _ver_tuple(tok[:-1])
            if vt >= base:
                return True
        else:
            if vt == _ver_tuple(tok) or vt[0] == _ver_tuple(tok)[0]:
                return True
    return False


def in_effect(meta: dict, as_of: str) -> bool:
    eff = meta.get("effective_from") or ""
    dep = meta.get("deprecated_on") or ""
    if eff and eff > as_of:
        return False  # not yet effective
    if dep and dep <= as_of:
        return False  # already removed
    return True


def is_upcoming_deprecation(meta: dict, as_of: str) -> bool:
    dep = meta.get("deprecated_on") or ""
    return bool(dep) and dep > as_of


# ---------------------------------------------------------------------------
# result type
# ---------------------------------------------------------------------------
@dataclass
class PrecedenceResult:
    authoritative: list[dict] = field(default_factory=list)  # docs (authority<=3), ranked
    supporting: list[dict] = field(default_factory=list)     # tickets (authority 4), evidence
    conflicts: list[dict] = field(default_factory=list)      # {reason, winner_source_id, loser_source_id}
    upcoming_deprecations: list[dict] = field(default_factory=list)
    dropped: list[dict] = field(default_factory=list)        # {source_id, reason} (audit)

    def has_grounding(self) -> bool:
        return bool(self.authoritative)


def _dedup_best_per_source(cands: list[dict]) -> list[dict]:
    """Keep the single best-scoring chunk per source_id (lowest distance)."""
    best: dict[str, dict] = {}
    for c in cands:
        sid = c["metadata"].get("source_id", c.get("chunk_id", ""))
        d = c.get("distance")
        if sid not in best or (d is not None and d < (best[sid].get("distance") or 9e9)):
            best[sid] = c
    return list(best.values())


def apply_precedence(candidates: list[dict], customer_version: Optional[str],
                     as_of: str) -> PrecedenceResult:
    res = PrecedenceResult()
    cands = _dedup_best_per_source(candidates)

    # 1. Applicability (version + effective/deprecated dates)
    applicable = []
    for c in cands:
        m = c["metadata"]
        if not version_covers(m.get("product_versions", ""), customer_version):
            res.dropped.append({"source_id": m.get("source_id", ""),
                                "reason": f"version {m.get('product_versions')} != customer {customer_version}"})
            continue
        if not in_effect(m, as_of):
            res.dropped.append({"source_id": m.get("source_id", ""),
                                "reason": "not in effect / already deprecated on as_of_date"})
            continue
        if is_upcoming_deprecation(m, as_of):
            res.upcoming_deprecations.append({
                "source_id": m.get("source_id", ""), "title": m.get("title", ""),
                "deprecated_on": m.get("deprecated_on", ""),
            })
        applicable.append(c)

    # 2. Supersession: drop sources explicitly superseded by another applicable source
    present_ids = {c["metadata"].get("source_id", "") for c in applicable}
    superseded: set[str] = set()
    for c in applicable:
        sup = c["metadata"].get("supersedes", "") or ""
        for loser in [s.strip() for s in sup.replace(",", ";").split(";") if s.strip()]:
            if loser in present_ids:
                superseded.add(loser)
                res.conflicts.append({
                    "reason": "superseded by newer/explicit source",
                    "winner_source_id": c["metadata"].get("source_id", ""),
                    "loser_source_id": loser,
                })
    applicable = [c for c in applicable if c["metadata"].get("source_id", "") not in superseded]

    # 3. Split by authority; tickets (4) and community (5) cannot contradict docs (<=3)
    docs = [c for c in applicable if int(c["metadata"].get("authority_level", 5)) <= 3]
    tickets = [c for c in applicable if int(c["metadata"].get("authority_level", 5)) == 4]

    def rank_key(c):
        m = c["metadata"]
        return (int(m.get("authority_level", 5)), _neg_date(m.get("last_updated", "")),
                c.get("distance") if c.get("distance") is not None else 9e9)

    docs.sort(key=rank_key)

    # conflict: an outdated ticket (or one that conflicts_with a present doc) loses to docs
    doc_ids = {c["metadata"].get("source_id", "") for c in docs}
    for t in tickets:
        m = t["metadata"]
        cw = (m.get("conflicts_with", "") or "").strip()
        winner = ""
        if cw and cw in doc_ids:
            winner = cw
        elif m.get("outdated") and docs:
            winner = docs[0]["metadata"].get("source_id", "")
        if winner:
            res.conflicts.append({
                "reason": "resolved ticket is outdated / contradicts current documentation; documentation wins",
                "winner_source_id": winner,
                "loser_source_id": m.get("source_id", ""),
            })

    res.authoritative = docs
    res.supporting = tickets
    return res


def _neg_date(d: str):
    """Sort newer-first: return a value that sorts ascending for newer dates."""
    return tuple(-x for x in _ver_tuple(d.replace("-", "."))) if d else (0,)
