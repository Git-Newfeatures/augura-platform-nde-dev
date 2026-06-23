"""The governed vocabulary exposes the expected enums (notably the fixed polarity)."""

from augura_api.modules.semantic import vocab


def test_polarity_is_governed_three_values() -> None:
    assert vocab.POLARITY == ["increases", "decreases", "neutral"]
    assert "mixed" not in vocab.POLARITY
    assert "unknown" not in vocab.POLARITY


def test_domains_and_qualifier_enums_present() -> None:
    assert "therapeutics" in vocab.AUGURA_DOMAINS
    assert "reverses_polarity" in vocab.QUALIFIER_EFFECTS
    assert "LOINC" in vocab.STANDARD_CODE_VOCABULARIES
