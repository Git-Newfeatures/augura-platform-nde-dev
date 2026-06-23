"""Lexical normalization + string similarity (ported from MVP lexical-normalizer.js)."""

from __future__ import annotations

import math
import re
from collections import Counter

# Clinical subset of the MVP ABBREV_MAP (synonyms carry the rest).
ABBREV_MAP: dict[str, str] = {
    "hba1c": "hemoglobin a1c",
    "a1c": "hemoglobin a1c",
    "hgba1c": "hemoglobin a1c",
    "sbp": "systolic blood pressure",
    "dbp": "diastolic blood pressure",
    "bp": "blood pressure",
    "hr": "heart rate",
    "bmi": "body mass index",
    "ldl": "ldl cholesterol",
    "hdl": "hdl cholesterol",
    "tg": "triglycerides",
    "egfr": "estimated glomerular filtration rate",
    "crp": "c reactive protein",
    "spo2": "oxygen saturation",
    "wt": "weight",
    "ht": "height",
    "dob": "date of birth",
    "dx": "diagnosis",
    "rx": "prescription",
    "t1d": "type 1 diabetes",
    "t2d": "type 2 diabetes",
    "dm": "diabetes mellitus",
    "cgm": "continuous glucose monitoring",
    "tir": "tir",
    "copd": "chronic obstructive pulmonary disease",
    "chf": "congestive heart failure",
}
_TIMEPOINT = re.compile(
    r"\.(bl|baseline|3m|6m|12m|24m|36m|w0|w2|w4|w8|w12|pre|post|fu)\b",
    re.IGNORECASE,
)
_SEP = re.compile(r"[_.:\-/\\|]")
_NOISE = {
    "value",
    "values",
    "score",
    "scores",
    "result",
    "results",
    "data",
    "var",
    "variable",
    "col",
    "column",
    "field",
    "entry",
    "item",
    "measure",
    "measurement",
    "level",
    "reading",
    "status",
    "flag",
    "indicator",
    "code",
    "cd",
    "id",
    "num",
    "no",
    "n",
    "the",
    "a",
    "an",
    "of",
    "in",
    "at",
    "on",
    "for",
    "and",
    "or",
    "with",
    "per",
}


def normalize(raw: str | None) -> str:
    s = (raw or "").lower().replace("..", " ")
    s = _TIMEPOINT.sub(" ", s)
    s = _SEP.sub(" ", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    expanded: list[str] = []
    for tok in s.split():
        expanded.extend(ABBREV_MAP[tok].split() if tok in ABBREV_MAP else [tok])
    tokens = [t for t in expanded if t not in _NOISE and not t.isdigit()]
    return " ".join(tokens)


def _ngrams(s: str, n: int = 3) -> Counter[str]:
    padded = f"  {s} "
    if len(padded) >= n:
        return Counter(padded[i : i + n] for i in range(len(padded) - n + 1))
    return Counter()


def _ngram_sim(a: str, b: str) -> float:
    ca, cb = _ngrams(a), _ngrams(b)
    if not ca or not cb:
        return 0.0
    dot = sum(v * cb.get(g, 0) for g, v in ca.items())
    na = math.sqrt(sum(v * v for v in ca.values()))
    nb = math.sqrt(sum(v * v for v in cb.values()))
    return dot / (na * nb) if na and nb else 0.0


def _levenshtein_sim(a: str, b: str) -> float:
    if not a and not b:
        return 1.0
    la, lb = len(a), len(b)
    if la == 0 or lb == 0:
        return 0.0
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
        prev = cur
    return 1 - prev[lb] / max(la, lb)


def _token_jaccard(a: str, b: str) -> float:
    sa, sb = set(a.split()), set(b.split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def string_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return 0.45 * _ngram_sim(a, b) + 0.35 * _token_jaccard(a, b) + 0.20 * _levenshtein_sim(a, b)
