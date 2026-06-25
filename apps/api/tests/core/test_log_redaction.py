"""The structlog redaction processor masks values for sensitive keys (no PHI in logs)."""

from augura_api.core.log_redaction import redact_processor


def test_redacts_sensitive_keys() -> None:
    event = {
        "event": "app_error",
        "email": "alice@example.com",
        "first_name": "Alice",
        "hba1c": 7.1,
        "request_id": "abc",  # operational — preserved (explicit _ALLOW)
        "study_id": "s1",  # id — preserved
        "code": "not_found",  # operational — preserved
        "model": "claude-opus-4-8",  # operational — preserved
        "tool_name": "search_pubmed",  # operational — preserved
        "count": 5,
        "tags": ["a", "b"],  # non-dict/non-str value passes through unchanged
        "note": None,
    }
    out = redact_processor(None, "info", dict(event))
    assert out["email"] == "[redacted]"
    assert out["first_name"] == "[redacted]"
    assert out["hba1c"] == "[redacted]"
    assert out["event"] == "app_error"
    assert out["request_id"] == "abc"
    assert out["study_id"] == "s1"
    assert out["code"] == "not_found"
    assert out["model"] == "claude-opus-4-8"
    assert out["tool_name"] == "search_pubmed"
    assert out["count"] == 5
    assert out["tags"] == ["a", "b"]
    assert out["note"] is None


def test_redacts_nested_dicts() -> None:
    event = {"event": "x", "context": {"email": "a@b.com", "study_id": "s1"}}
    out = redact_processor(None, "info", dict(event))
    assert out["context"]["email"] == "[redacted]"
    assert out["context"]["study_id"] == "s1"  # ids are not PHI
