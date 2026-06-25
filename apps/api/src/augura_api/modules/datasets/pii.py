"""Pure PII header scanner.

Matches dataset column headers against the active regex patterns from
pii_pattern_catalog (HIPAA minimum-necessary / GDPR data-minimization). Pure and
DB-free so it is trivially unit-testable; the service loads the patterns and calls it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class PiiPattern:
    key: str
    pattern: str


@dataclass(frozen=True)
class PiiHit:
    column: str
    pattern_key: str


def scan_headers_for_pii(headers: list[str], patterns: list[PiiPattern]) -> list[PiiHit]:
    """Return one hit per (header, pattern) match. A malformed pattern is skipped, never
    raised — a bad catalog row must not break ingestion (fail open on the SCANNER, while
    the caller still fails closed on any real hit)."""
    compiled: list[tuple[str, re.Pattern[str]]] = []
    for p in patterns:
        try:
            compiled.append((p.key, re.compile(p.pattern, re.IGNORECASE)))
        except re.error:
            continue
    hits: list[PiiHit] = []
    for header in headers:
        for key, rx in compiled:
            if rx.search(header):
                hits.append(PiiHit(column=header, pattern_key=key))
    return hits
