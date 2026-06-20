"""Vocabulaire gouverné (Semantic Layer v3 §10.5) — source unique des enums.

Importé par l'enrichissement (B4) ET le causal (B2) pour qu'ils ne divergent plus.
Bug historique corrigé : polarity valait `mixed`/`unknown` côté DAG mais `neutral`
côté enrichissement. La valeur gouvernée est `neutral`.
"""

# §10.5 — polarité des relations.
POLARITY: list[str] = ["increases", "decreases", "neutral"]

# augura_domain — domaines des concepts.
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

# §10.5 — enums gouvernés des qualifiers.
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

# Vocabulaires de codes standards acceptés pour les concepts Layer 1.
STANDARD_CODE_VOCABULARIES: list[str] = ["LOINC", "SNOMED", "RxNorm", "OMOP", "ICD10CM"]

# Buckets de force de relation.
RELATION_STRENGTH: list[str] = ["strong", "moderate", "weak"]
