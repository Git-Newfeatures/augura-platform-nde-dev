"""Pure PII header scanner: matches column headers against pii_pattern_catalog regexes."""

from augura_api.modules.datasets.pii import PiiPattern, scan_headers_for_pii

# Mirrors the REAL seed patterns in supabase/seed.sql (substring-matching, not \b-anchored)
# so the test proves prefixed identifier columns are caught — the case the gate exists for.
PATTERNS = [
    PiiPattern(key="name", pattern=r"(first|last|full|given|family|sur)_?name"),
    PiiPattern(key="email", pattern=r"e[_-]?mail"),
    PiiPattern(key="dob", pattern=r"dob|date_?of_?birth|birth_?date|birthday"),
]


def test_flags_prefixed_direct_identifier_headers() -> None:
    hits = scan_headers_for_pii(
        ["patient_email", "subject_dob", "patient_first_name", "hba1c_12m"], PATTERNS
    )
    flagged = {(h.column, h.pattern_key) for h in hits}
    assert ("patient_email", "email") in flagged
    assert ("subject_dob", "dob") in flagged
    assert ("patient_first_name", "name") in flagged
    # A clinical biomarker column is NOT flagged.
    assert all(h.column != "hba1c_12m" for h in hits)


def test_case_insensitive() -> None:
    hits = scan_headers_for_pii(["EMAIL", "DOB"], PATTERNS)
    assert {h.pattern_key for h in hits} == {"email", "dob"}


def test_clean_headers_return_no_hits() -> None:
    assert scan_headers_for_pii(["age", "ldl", "visit_month"], PATTERNS) == []


def test_invalid_regex_is_skipped_not_raised() -> None:
    # A malformed catalog pattern must not crash ingestion.
    hits = scan_headers_for_pii(["email"], [PiiPattern(key="bad", pattern="(")])
    assert hits == []
