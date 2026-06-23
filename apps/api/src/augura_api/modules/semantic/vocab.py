"""Governed vocabulary (Semantic Layer v3 §10.5) — single source for the enums.

Imported by both enrichment (B4) AND causal (B2) so they no longer diverge.
Historical bug fixed: polarity was `mixed`/`unknown` on the DAG side but `neutral`
on the enrichment side. The governed value is `neutral`.
"""

# §10.5 — relation polarity.
POLARITY: list[str] = ["increases", "decreases", "neutral"]

# augura_domain — concept domains.
AUGURA_DOMAINS: list[str] = [
    "therapeutics",
    "measurement",
    "condition",
    "device",
    "procedure",
    "outcome",
    "structural",
    "biomarker",
    "pharmacology",
]

# §10.5 — governed qualifier enums.
QUALIFIER_TYPES: list[str] = [
    "population",
    "comorbidity",
    "age_range",
    "sex",
    "therapeutic_context",
    "biomarker_threshold",
    "temporal_context",
]
QUALIFIER_EFFECTS: list[str] = [
    "reverses_polarity",
    "attenuates_strength",
    "amplifies_strength",
    "restricts_applicability",
]

# Accepted standard code vocabularies for Layer 1 concepts.
STANDARD_CODE_VOCABULARIES: list[str] = ["LOINC", "SNOMED", "RxNorm", "OMOP", "ICD10CM"]

# Relation strength buckets.
RELATION_STRENGTH: list[str] = ["strong", "moderate", "weak"]
