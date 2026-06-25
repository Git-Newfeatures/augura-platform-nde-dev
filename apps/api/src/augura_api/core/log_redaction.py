"""structlog processor that redacts PHI/PII-ish values from log events.

Defense-in-depth for HIPAA minimum-necessary / GDPR Art 5(1)(c): logs ship to a
sub-processor (Modal/observability), so values under sensitive keys are masked before
rendering. Keys are matched case-insensitively by substring; ids/codes are preserved.
"""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any, cast

_REDACTED = "[redacted]"

# Substrings that mark a key as carrying PHI/PII. Tune as new fields appear.
_SENSITIVE = (
    "email",
    "first_name",
    "last_name",
    "full_name",
    "name",
    "dob",
    "birth",
    "ssn",
    "phone",
    "address",
    "passport",
    "member",
    "biomarker",
    "hba1c",
    "ldl",
    "crp",
    "bmi",
    "patient",
)

# Keys that contain "name" etc. but are safe operational fields — never redact these.
# Includes ids/codes so their preservation is EXPLICIT, not merely accidental (robust
# against a future _SENSITIVE term like "id").
_ALLOW = (
    "event",
    "logger",
    "level",
    "model",
    "model_name",
    "event_name",
    "tool_name",
    "request_id",
    "study_id",
    "code",
)


def _is_sensitive(key: str) -> bool:
    k = key.lower()
    if k in _ALLOW:
        return False
    return any(s in k for s in _SENSITIVE)


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        d = cast(dict[str, Any], value)
        return {k: (_REDACTED if _is_sensitive(k) else _redact(v)) for k, v in d.items()}
    return value


def redact_processor(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    result: dict[str, Any] = {}
    for k, v in event_dict.items():
        result[k] = _REDACTED if _is_sensitive(k) else _redact(v)
    return result
