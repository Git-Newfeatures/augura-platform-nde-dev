# Augura Platform — Semantic Layer v3 — Architecture

**Date:** 2026-06-25
**Status:** Proposed
**Scope:** Data intake taxonomy, table-grain determination, causal modeling, and data quality.
**Purpose:** Define stable boundaries so the semantic system can grow without mixing meanings, rules, and executable behavior.

## 1. Core Mental Model

The platform should answer five different questions in sequence:

1. **What does each source element mean?** The taxonomy maps files, tables, columns, and values to stable concepts and structural roles.
2. **What kind of record does each row represent?** Structural concepts and table archetype profiles propose the table type, candidate keys, parent links, and grain.
3. **What relationships are known between the mapped concepts?** Ontology artifacts provide causal, structural, and other domain relationships.
4. **Which checks apply to this dataset?** Declarative DQ constraints select checks based on mappings, roles, inferred grain, and cross-table relationships.
5. **How are those checks executed?** Programmed code profiles the data, evaluates constraints, and produces evidence-backed findings.

### 1.1 Three Core Execution Boundaries

Every causal-modeling or DQ behavior must be assigned to one of three boundaries.

#### 1. Declarative Semantic Artifacts

These artifacts define reviewed knowledge and policy:

- Taxonomy concepts, synonyms, standard codes, data types, roles, units, ranges, and valid values
- Causal ontology predicates, relations, and evidence
- DQ ontology predicates, constraints, and applicability conditions
- Archetype vocabulary and recognition shapes
- Unit transformations and contextual range profiles

They state what an element means, which relationships are recognized, and which conditions should hold. They do not scan rows or calculate findings.

#### 2. Programmed Functions

These functions provide deterministic or explicitly configured execution:

- Load and validate semantic artifacts
- Profile columns and tables
- Match source elements to taxonomy candidates
- Retrieve ontology relations
- Evaluate archetype shapes and determine grain
- Parse values, normalize units, and execute governed transformations
- Dispatch and evaluate DQ checks
- Assemble causal graph candidates from selected concepts and relations
- Generate evidence-backed outputs and DQ findings

Given the same input data, semantic release, configuration, and accepted contextual selections, these functions should produce the same result.

#### 3. Contextual Reasoning

Contextual reasoning (including bounded LLM calls) refines decisions where language or context is genuinely ambiguous:

- Interpret a clinical question or unfamiliar source documentation
- Select and role-label relevant causal relations for a specific question
- Propose a taxonomy mapping or archetype when deterministic evidence is inconclusive
- Explain competing grain hypotheses
- Suggest a unit interpretation or contextual-range candidate for review
- Summarize findings and analytical consequences

Contextual output is advisory. It must remain inside the candidate space supplied by the declarative artifacts and the programmed functions whenever possible.

An LLM must not silently:

- Add official taxonomy or ontology knowledge
- Invent a conversion equation or clinical threshold
- Declare a key, grain, or DQ defect without reproducible evidence
- Override a high-confidence deterministic result
- Remove or alter source records

The central execution pattern is:

> Declarative artifacts constrain the problem. Programmed functions calculate and validate. Contextual reasoning refines ambiguous context. Programmed functions then verify, structure, and record the result.

#### Current mapping architecture

In the new repo, deterministic concept matching should be implemented as a service that reads the semantic taxonomy and produces candidate proposals. Ambiguous or low-confidence results should remain visible for review. Any contextual or LLM-based refinement must be explicitly bounded, validated, and traceable.

### 1.2 Capability Responsibility Matrices

These matrices define the authority split for the two capabilities.

#### Causal Modeling

| Component | Responsibility |
|---|---|
| **Taxonomy** | Identifies dataset attributes as stable clinical, structural, and study concepts. |
| **Causal ontology** | Provides reviewed causal relationships, predicates, and supporting evidence. It does not assign one permanent DAG role to a concept. |
| **Profiles and contextual inputs** | The clinical question and PICOT framing provide population, exposure, comparator, outcome, and time context. Dataset mappings identify measured and unmeasured concepts. |
| **Programmed functions** | Parse structured inputs, retrieve the relevant ontology neighborhood, connect mapped attributes, assemble and validate graph candidates, identify data availability, and produce a reviewable graph structure. |
| **Contextual reasoning** | Interprets the question, selects relevant reviewed relations, assigns question-specific roles such as exposure, outcome, confounder, or mediator, prunes irrelevant candidates, and explains missing variables or unresolved assumptions. |
| **Output** | A reviewable causal graph and analysis specification. The current scope does not execute the statistical analysis. |

#### Data Quality

| Component | Responsibility |
|---|---|
| **Taxonomy** | Provides column meaning, primitive type, structural role, permitted units, broad plausible ranges, standard codes, and valid values. |
| **Archetype profiles** | Describe recognizable table structures, expected roles, candidate keys, possible grain, and cardinality patterns. |
| **DQ ontology** | Provides declarative validation predicates, constraints, applicability conditions, and links to executable check identifiers. |
| **Programmed functions** | Profile data, map columns, determine and test grain, detect and normalize units, run conversions, calculate missingness and uniqueness, evaluate constraints, and generate traceable findings. |
| **Contextual reasoning** | Assist with ambiguous mappings, unfamiliar table structures, close archetype candidates, possible unit interpretations, contextual-range research, and plain-language explanation. Suggestions must remain subject to deterministic validation or human review. |
| **Output** | DQ findings that identify affected data, evidence, severity, handling, and consequences for analysis or publication. |

These boundaries are about authority, not deployment. All three may run inside the same application. Their responsibilities must remain distinguishable even when they share code, storage, or user interfaces.

The three execution boundaries are orthogonal to the semantic capabilities below. For example, DQ uses declarative taxonomy and ontology artifacts, programmed check functions, and bounded contextual reasoning.

The solution has five logically separate semantic capabilities:

1. **Shared taxonomy:** concepts, synonyms, standard codes, and structural roles.
2. **Causal ontology:** relations used only for causal modeling.
3. **DQ ontology:** validation predicates and constraints used only for data quality.
4. **Archetype repository:** expected table structures used for table and grain recognition.
5. **Dimension grammar:** affix recognition patterns that decompose column labels into a base concept plus governed dimensions (§2.7).

They may share loader infrastructure and one top-level manifest while the platform is small. The important requirement is logical separation: causal predicates must not be interpreted as DQ rules, DQ predicates must not be used to build causal graphs, and archetype shapes must not be confused with either ontology.

The only required combination is reference by stable identifier. Both ontologies and the archetype repository may reference concepts from the shared taxonomy without copying those concepts into their own tables.

The architecture should remain deliberately small. New tables, schemas, versions, or services are justified only when they improve mapping accuracy, deterministic behavior, maintainability, or traceability of data-quality findings.

The governing priorities are:

1. Leverage medical data, terminology, unit, and validation standards whenever they apply.
2. Prefer accurate and useful semantic coverage over broad but uncertain coverage.
3. Build the minimum infrastructure that reliably supports taxonomy mapping, causal modeling preparation, and DQ.
4. Keep behavior stable, deterministic, explainable, and testable.
5. Preserve every material DQ issue well enough to explain its handling and consequence in later analysis or publication.

## 2. Semantic Layers

### 2.1 Source Instance Layer

This is the submitted dataset: files, tables, rows, column names, source data types, observed values, observed units, and source metadata.

Nothing observed in one dataset should silently become a permanent taxonomy fact. Runtime observations are evidence, not definitions.

### 2.2 Taxonomy

The taxonomy is the controlled vocabulary used to identify source elements.

#### Layer 0: Structural and Data-Model Concepts

Layer 0 describes how data is organized, independently of a clinical concept.

Examples:

- Person, encounter, record, and measurement identifiers
- Event start, event end, and observation time
- Unit, value, vocabulary code, and source-system columns

These concepts are required for reliable grain, key, and relationship inference. A column such as `patient_id` must map to the structural role `person_identifier`.

Layer 0 should be standards-aligned, but it should not be copied from only one medical data standard. No single standard covers observational analytics, clinical-trial submissions, healthcare exchange, and arbitrary customer files equally well.

Recommended alignment:

- **OMOP CDM as the primary analytical backbone.** Reuse its person-centric event model and distinctions among record identifiers, person identifiers, visit identifiers, concept identifiers, source values, units, and event dates.
- **HL7 FHIR as the primary exchange and source-context crosswalk.** Reuse its distinctions among resource identifier, business identifier, subject, encounter, effective time, issued time, specimen, method, value, and unit.
- **CDISC SDTM as the clinical-trial crosswalk.** Reuse its general observation classes and study variables when submitted data follows trial-domain conventions.
- **Platform structural roles as the stable internal abstraction.** A role such as `person_identifier` can map to OMOP `person_id`, a FHIR `Patient` reference, an SDTM subject identifier, or a nonstandard `patient_id` source column.

Layer 0 is therefore a canonical metadata vocabulary with explicit crosswalks, not a new clinical terminology and not a clone of OMOP tables.

#### Layer 1: Standard Domain Concepts

Layer 1 contains externally standardized clinical and biomedical concepts, such as Hemoglobin A1c, serum creatinine, diabetes mellitus, and metformin.

Standard identifiers should be reused where licensing and distribution permit, including LOINC, SNOMED CT, RxNorm, ICD source codes, and OMOP standard concept identifiers.

#### Layer 2: Platform Extensions

Layer 2 contains concepts necessary for the platform that are not adequately represented by selected external standards.

Every extension requires a stable identifier, precise definition, declared scope, provenance, relationship to the closest standard concept, review status, and version history. Layer 2 must not duplicate a standard concept merely because its standard name is inconvenient.

### 2.3 Archetype Shape Repository

The archetype repository describes recognizable table structures. It is separate from both the causal ontology and the DQ ontology.

Examples include person master, encounter, diagnosis occurrence, medication exposure, long-form measurement, wide measurement panel, and specimen.

Each profile can declare:

- Required and optional structural roles
- Diagnostic concept categories
- Candidate row keys and parent entity roles
- Expected cardinalities and temporal patterns
- Wide versus long representation
- Evidence weights and confidence thresholds

Shapes generate and score hypotheses. The data must then confirm or reject them.

The full target repository may eventually have two parts:

1. **A small archetype vocabulary:** names and semantic links such as `is_subtype_of`, `specializes`, `has_subject_role`, `has_event_role`, and `compatible_with_domain`.
2. **Recognition shapes:** required, optional, alternative, and disqualifying roles; candidate keys; expected cardinalities; and scoring weights.

The first part has ontological aspects. For example, `long_measurement_table` can be a subtype of `clinical_event_table`. The second part is a closed-world recognition profile and is better aligned with SHACL shapes than with open-world ontology axioms.

The authoritative recognition path should be:

1. Map columns to taxonomy concepts and Layer 0 roles.
2. Evaluate all eligible archetype shapes.
3. Rank candidates using role coverage, conflicting evidence, cardinality, and key evidence.
4. Confirm the leading candidate with procedural profiling.
5. Return the selected archetype, alternatives, confidence, and evidence.

An LLM should not be the primary archetype classifier. It may interpret unfamiliar source documentation or explain a close tie, but it must choose among governed repository shapes. Adding new archetype shapes is outside the runtime workflow.

SHACL is the design model, not a requirement to adopt RDF immediately. The current implementation can represent the same elements in Supabase tables and evaluate them in application code.

### 2.4 Causal Ontology

The causal ontology captures clinically meaningful relationships used by causal modeling, such as `causes`, `increases_risk_of`, `confounds`, `mediates`, and `is_effect_modifier_for`.

This capability references shared taxonomy identifiers but has its own predicate vocabulary and evidence model.

No causal relation is executable as a DQ rule merely because it exists in this ontology.

The causal workflow combines the three execution boundaries:

1. **Programmed functions** parse available structured question elements and connect dataset mappings to taxonomy concepts.
2. **Contextual reasoning** interprets ambiguous clinical language and proposes question-specific exposure, outcome, population, time, and study roles.
3. **Programmed functions** retrieve the ontology neighborhood around the mapped and question-derived concepts.
4. **Contextual reasoning** selects relevant reviewed relations, assigns contextual roles, prunes irrelevant relations, and identifies likely missing variables.
5. **Programmed functions** assemble graph candidates using the accepted concepts and relations.
6. **Programmed functions** check graph structure, variable availability, temporal information, and measured versus unmeasured status.
7. **Programmed functions** produce a reviewable causal model and analysis specification containing assumptions and unresolved questions.

The current scope ends at a reviewable model or specification. It does not require the platform to execute the statistical analysis, and it does not require a new persistent audit store for causal-model generation.

### 2.5 DQ Ontology

The DQ ontology is a logically separate capability owned by the data-quality domain. It contains validation concepts, predicates, applicability semantics, and declarative constraints, but not profiling algorithms.

Examples:

- `greater_than`
- `temporally_precedes`
- `not_after`
- `uses_vocabulary`
- `incompatible_with`
- `requires_presence_of`
- `unit_compatible_with`
- `foreign_key_to`
- `unique_within`
- `derived_consistent_with`

A constraint identifies its target scope, subject, operator, object or parameters, applicability conditions, severity, evidence source, and executable implementation identifier.

This follows the W3C SHACL division between declarative shapes and a validation engine. The implementation may remain Supabase tables and application code; adopting the separation does not require converting the platform to RDF.

The DQ ontology may reference:

- Taxonomy concepts such as Hemoglobin A1c
- Layer 0 roles such as `person_identifier` or `event_start`
- Archetype identifiers such as `long_measurement_table`
- Unit, vocabulary, and range profile identifiers

It must not import causal predicates into its validation namespace. If a clinically causal relationship motivates a DQ constraint, the DQ ontology should contain a separately reviewed validation rule with its own evidence and applicability conditions.

### 2.6 Contextual Clinical Knowledge

Context-dependent clinical interpretation belongs in a later, separately governed module.

Examples:

- Age- and sex-specific reference intervals
- Pregnancy-specific thresholds
- Specimen- or assay-specific ranges
- Disease- or treatment-dependent targets
- Derived clinical consistency rules

This module must not be required to deliver reliable structural mapping, grain inference, unit validation, vocabulary validation, or relational integrity.

### 2.7 Dimension Grammar and Affix Archetypes

A column label often encodes more than a concept. `hba1c_baseline`, `hba1c_6mo`, and `hba1c_12mo` are the same measurand differentiated by *when* it was measured; `knee_rom_left` and `knee_rom_right` by *which side*. The platform must not mint a new taxonomy concept for each concept-plus-modifier combination — that explodes the taxonomy and breaks reuse of unit, range, and vocabulary metadata. Instead, a column resolves to a **base concept plus a set of governed dimensions**:

```text
mapping   = base_concept + [ dimension, ... ]
dimension = { type, value }                                    # closed-value kinds: laterality, specimen, method, ...
dimension = { type: relative_time, operator, anchor_concept, offset }   # event-anchored kinds
```

This is the same representation whether the dimension is carried in the column name (wide tables) or in a value column with one row per measurement (long tables). Both encodings must reconcile to the same canonical statement (see §5).

#### Dimension kinds

Recognized dimensions fall into a few structural families, each with a different extraction strategy:

- **Scheduled time** — a point on a study calendar, named (`baseline`, `screening`, `eot`) or parametric (`week12`, `6mo`); resolved through a study visit map.
- **Event-anchored (relative) time** — a triple of operator (`pre`/`post`/`peri`/`around`), an **anchor that is itself a taxonomy concept** (`postop` = after(surgery), `postprandial` = after(meal)), and an optional offset.
- **Laterality / side** — closed set (`left`/`right`/`bilateral`; ophthalmic `OD`/`OS`/`OU`).
- **Body site / position** — closed set (`lumbar`; `sitting`/`standing`/`supine`; `rest`/`stress`).
- **Specimen / matrix** — closed set (`serum`/`plasma`/`urine`/`csf`; `capillary`/`venous`).
- **Method / assay / device** — closed set (`hplc`/`elisa`/`poc`; `central`/`local`).
- **Derived statistic** — a function over a base and window (`mean`, `min`/`max`, `sd`, `auc`, `nadir`, `change`/`delta`, `pct_change`); the derived quantity may carry a **different plausible range and even different units** than the base concept.
- **Aggregation window** — a period spec (`24h`, `daily`, `overnight`, `am`/`pm`), usually paired with a statistic.
- **Rater / source** — closed set (`self`/`proxy`/`clinician`; `reader1`/`reader2`).
- **Replicate** — an ordinal index (`rep1`/`rep2`).
- **Vocabulary / representation** — which coding system, or code-vs-label (`icd10`/`snomed`; `code`/`desc`).
- **Condition status** — a modal qualifier (`hx`/history, `suspected`, `prior`/`current`).

A **unit carried in the column name** (`weight_kg`, `hba1c_pct`) is not a dimension: it resolves to the concept's unit profile (§3).

#### Dimension versus distinct concept

A modifier is a **dimension** only when values remain **comparable along that axis** — baseline → 6mo → 12mo HbA1c belong on one trajectory; left vs. right are the same measurand on two sides. A modifier is **concept-distinguishing** when it changes *what is measured* such that values are not interchangeable — serum vs. urine sodium, troponin by two assays with different reference limits. Each governed dimension must therefore declare whether it **preserves comparability** (a true dimension) or **forks the concept** (route the residual to a distinct concept). Time and laterality are almost always true dimensions; specimen and method are case-by-case and must be governed explicitly. This is the same boundary as the unit rule in §3 — two units, methods, specimens, or meanings that imply different properties may require different concepts rather than one concept with interchangeable variants.

#### Affix archetypes — governed recognition shapes

Affix decomposition is governed the same way table grain is: by evidence-ranked recognition shapes, not blind string stripping. An **affix archetype** declares:

- a **matcher** — a token set and its position (prefix, suffix, or separator style), with an **alias layer** analogous to concept synonyms (`6mo` ≡ `m6` ≡ `month6` ≡ visit `v3`);
- the **dimension kind** it yields and how to extract its operator, value, or anchor;
- the **comparability flag** above;
- **evidence weights and confidence thresholds**.

The recognition workflow:

1. **Residual must map.** After carving the affix, the remaining token must resolve to a known concept; if it does not, do not carve.
2. **Family evidence.** Sibling columns that share a base with varying affixes (`bp_sitting` + `bp_standing`) are the strongest signal; a lone affixed column is weak.
3. **Compositionality.** Multiple dimensions may stack in any order (`bp_sitting_left_6mo`) and are peeled successively.
4. **Reconcile with grain.** An affix archetype (wide encoding) and a table archetype (long encoding) must emit the same canonical dimension representation, so downstream checks are layout-independent. Affix archetypes and grain archetypes are two faces of one dimension model.
5. **Contextual fallback.** An LLM may interpret an unfamiliar affix token — advisory only, confirmed against the taxonomy and the data.

The chief failure mode is **over-carving** — stripping a token that is part of a real concept name, or misreading an ambiguous token (`min` as statistic, minutes, or part of a name). Rules 1–2 are the guard: carve only when the residual maps and the data supports it.

Like the archetype shape repository (§2.3), affix archetypes are SHACL-like closed-world recognition profiles that reference shared taxonomy concepts (notably as relative-time anchors); they are not a separate ontology. Adding new affix archetypes is a governance activity, not part of the runtime workflow.

## 3. What Belongs on a Taxonomy Concept?

A concept may carry stable, broadly applicable properties:

- Preferred label, synonyms, definition, and standard codes
- Domain and concept type
- Expected primitive data type and quantity kind
- Preferred canonical unit
- Broad physical or physiological plausibility bounds
- Common temporality affordances
- Structural roles the concept can fulfill

Conditional or one-to-many knowledge should not be compressed into scalar concept columns. Use dedicated profiles for allowed units and conversions, method and specimen variants, categorical value sets, conditional ranges, clinical thresholds, cross-concept constraints, and archetype requirements.

Per-column modifiers such as timepoint, laterality, specimen, or derivation are likewise not new concepts and not scalar columns; they are governed dimensions decomposed at mapping time (§2.7).

The platform's `taxonomy_concepts` table should separate the concept's stable meaning from dataset-specific source evidence. In particular, unit evidence belongs in the unit profile tables and runtime observations, not on the concept row itself.

The new repo's semantic schema should distinguish:

- `preferred_unit`: the normalization target
- `allowed_unit`: a unit valid for the quantity
- `observed_unit`: the unit found in the submitted dataset

Medical standards do not always nominate one universal unit for a measurement. LOINC identifies the observation, UCUM encodes units, OMOP can store a standardized unit concept, and FHIR can declare permitted or customary units. The platform's `preferred_unit` is therefore an explicit normalization policy, not an assumption that every source standard mandates the same unit.

Every quantitative taxonomy concept supported by the platform should have an explicit unit-coverage declaration:

- `not_applicable`: the observation is unitless, categorical, textual, or otherwise has no unit.
- `supported_set_curated`: the clinically meaningful units currently accepted by the platform are listed.
- `partial`: some supported units are known, but curation is incomplete.
- `unknown`: the concept requires unit review before unit-dependent validation can be trusted.

The goal is not exhaustivity. UCUM can generate an effectively unbounded set of expressions. The goal is a small, accurate set of clinically meaningful units that the platform supports for each sufficiently specific observation concept.

For each supported unit, store:

- Canonical UCUM code
- Display label and recognized source aliases
- Quantity kind
- Whether it is preferred, allowed, deprecated, or display-only
- Applicable method, specimen, or concept variant when necessary
- Transformation identifier to the preferred unit, when conversion is valid
- Provenance, review status, and version

A unit set belongs to a sufficiently precise observation definition. If two units imply different properties, specimens, methods, or meanings, the source may need to map to different taxonomy concepts rather than treating them as interchangeable units of one concept.

### 3.1 Unit Recognition and Transformation

Identifying the measurement concept is not enough to convert its values. The engine must also know:

- The observed unit
- The canonical unit
- Whether the units represent the same quantity kind
- The conversion rule and its provenance
- Any concept-specific parameters required by the conversion

The conversion registry should distinguish four cases:

1. **Linear dimensional conversion:** multiply by a scale factor, such as `mg` to `g`.
2. **Affine or special conversion:** apply an offset or defined function, such as Celsius to Fahrenheit.
3. **Concept-dependent conversion:** use clinical concept knowledge, such as mass concentration to molar concentration, which can require the analyte's molecular mass.
4. **Derived quantity transformation:** transform between related but inverse or otherwise different quantity kinds using a governed equation.

The implementation may derive pure decimal-prefix scaling from a whitelisted unit without enumerating every equivalent spelling in the taxonomy. For example, if `mg/L` is whitelisted, `ug/mL` or `µg/mL` may resolve to it because they have the same dimensions and a deterministic decimal scale. This fallback must not cross dimensions: `mg/L` to `mmol/L` still requires a concept-specific governed conversion.

The execution engine should:

1. Read or infer the observed unit from a dedicated unit column, source metadata, column annotation, or an unambiguous header.
2. Normalize the unit string to a UCUM code when possible.
3. Verify that the conversion applies to the mapped concept and quantity kind.
4. Preserve the source value and source unit.
5. Produce a normalized value and unit with the conversion rule identifier.
6. Refuse conversion when the unit, quantity kind, method, or equation is ambiguous.

Contextual reasoning may suggest a unit interpretation for review. It must not invent or execute a conversion formula.

### 3.2 Missing or Implicit Unit Handling

A correct taxonomy mapping does not prove that the source values have a known unit. The engine must resolve concept identity and unit identity independently.

Unit evidence should be evaluated in this order:

1. Dedicated unit column paired with the value column
2. Source data dictionary, schema, API metadata, or file manifest
3. Unambiguous unit annotation in the column header
4. Governed table, site, instrument, or ingestion configuration
5. Statistical or contextual inference as an advisory candidate only

The resulting unit status should be one of:

- `observed`: explicitly present in the source rows
- `declared`: provided by trusted source metadata or ingestion configuration
- `inferred_candidate`: plausible but not authoritative
- `ambiguous`: several units remain plausible
- `missing`: no unit evidence exists
- `not_applicable`: the concept is genuinely unitless or categorical

The engine then follows these rules:

- If an observed or declared unit is allowed, normalize and convert when a governed transformation exists.
- If the unit is recognized but not in the allowed-unit profile, report a unit-compatibility defect and do not convert automatically.
- If only an inferred candidate exists, show it for review but do not convert or run unit-dependent ranges.
- If the unit is missing or ambiguous, preserve the source value, report the missing-unit condition, and suppress conversion and unit-dependent range checks.
- If the concept has no allowed-unit or quantity-kind metadata, report a semantic-coverage gap separately from a dataset defect.
- Continue unit-independent checks such as missingness, primitive type, duplicate, key, and vocabulary checks.

A single allowed unit in the taxonomy is not enough to assume the source uses that unit. It can be assigned implicitly only when a trusted source contract declares that convention.

Unit detection should normalize a source token through the permitted-unit aliases for the mapped concept, then validate the resulting UCUM code and transformation. For body temperature:

- `temp_c`, `degC`, `Celsius`, and UCUM `Cel` may resolve to the supported Celsius unit.
- `temp_f`, `degF`, `Fahrenheit`, and UCUM `[degF]` may resolve to the supported Fahrenheit unit.
- A value of `37` may support Celsius as a plausibility signal, but it does not prove the unit.
- A value of `98.6` may support Fahrenheit as a plausibility signal, but it does not prove the unit.
- Once the unit is observed or declared, the engine can normalize the value and evaluate ranges in the corresponding or preferred unit.

Example: a column named `hba1c` maps confidently to Hemoglobin A1c, but no unit column, header annotation, data dictionary, or ingestion contract exists.

- The taxonomy unit profile may show `%` and `mmol/mol` as allowed units.
- Values such as `5.8` and `7.2` may make `%` look likely, but that remains an `inferred_candidate`.
- The engine preserves the source values, reports `unit_missing_or_ambiguous`, and does not convert or apply percent-based ranges.
- Once a trusted source declaration confirms `%`, the status becomes `declared`, and conversion or range checks may run.

If the taxonomy has no unit profile at all, the finding should be a semantic coverage defect such as `semantic_unit_metadata_missing`. That is a governance gap, not proof that the submitted dataset is defective.

### 3.3 Range Profiles and Precedence

Every observation concept actively supported by the platform should declare a range-support status:

- `not_applicable`: a numeric range has no useful meaning for this concept.
- `generic_curated`: a defensible generic range or broad plausibility range is available.
- `contextual_curated`: a generic range and one or more important contextual variants are available.
- `context_required`: no generic clinical range is safe; method, population, specimen, laboratory, or another qualifier is required.
- `pending_review`: a range may apply, but semantic curation is incomplete.

The status should be explicit for concepts used by the platform. An accurate generic range, or an honest `context_required` or `pending_review` status, is preferable to many weak or conflicting rules.

For common observations such as body temperature, the initial platform package may contain:

- One preferred unit and supported alternative units
- One broad plausibility range
- One generic reference range with clear provenance
- No specialized fever, hypothermia, age, measurement-site, or disease ranges yet

That is acceptable if the metadata declares `generic_curated` and does not imply that specialized contexts are covered.

Some observations should not receive a generic clinical reference range. For example, an assay-specific troponin result may be marked `context_required`. It can still have broad technical plausibility checks while clinical interpretation waits for the assay or laboratory range.

A minimal range record should contain:

```text
range_id
concept_id
range_kind
low_value
high_value
unit
context_profile_id
evidence_source
review_status
version
```

Optional context belongs in a separate qualifier table rather than dozens of mostly empty columns:

```text
context_profile_id
qualifier_type
operator
qualifier_value_or_code
```

Initial qualifier types should be deliberately small:

- `age`
- `sex`
- `pregnancy`
- `condition`
- `specimen`
- `method_or_assay`
- `laboratory_or_site`

New qualifier types should be added only when a real executable use case requires them. Study-specific rules should normally remain in a dataset or study policy package that references the shared range structure, rather than becoming permanent global ontology properties.

`range_kind` must distinguish at least:

- `absolute_or_physical`
- `plausibility`
- `reference`
- `critical`
- `clinical_decision`
- `study_target`

When several ranges apply, use explicit precedence:

1. Valid source-observation or laboratory-specific range
2. Study protocol or data-definition range
3. Curated method, specimen, device, and population-specific range
4. Curated generic reference range
5. Broad plausibility bound

The selected range and all matched qualifiers must be recorded in DQ evidence. If two equally specific ranges conflict, the engine should report ambiguity instead of choosing silently.

FHIR `ObservationDefinition.qualifiedValue` is an inspiration for separating a range from its applicability context. The platform does not need to implement every FHIR field.

Contextual reasoning can retrieve candidate ranges, summarize guidance, interpret free-text study context, or help map that context to known qualifier types. It must not supply an unreviewed range directly as an executable DQ rule.

When no curated contextual range applies, the engine should either use a broad plausibility bound with an explicit label or state that no contextual range check was run. It should not invent a threshold during validation.

Range applicability should be reported at runtime:

- `generic_range_applied`
- `contextual_range_applied`
- `generic_fallback_applied`
- `context_required_but_missing`
- `range_not_applicable`
- `range_metadata_pending`

This makes the system clear about what it knows and does not know without pretending that its clinical knowledge is exhaustive.

## 4. Concrete Clinical Examples

### 4.1 Hemoglobin A1c

Stable knowledge says that HbA1c is a numeric measurement commonly represented as percent or mmol/mol. A unit profile can define both units and a governed conversion.

Basic DQ should recognize the unit, convert only known compatible units, and apply broad plausibility bounds after normalization. It should not treat a diabetes treatment target as a universal reference interval.

Pregnancy, comorbidity, or treatment goals may alter an appropriate target. Those contextual targets are not intrinsic properties of the HbA1c concept.

### 4.2 Serum Creatinine

Stable knowledge includes its numeric measurement type and common `mg/dL` and `umol/L` units. Basic DQ can validate type, unit conversion, and broad plausibility.

Reference intervals may vary by laboratory, age, sex, and method. eGFR consistency also requires an equation version and additional attributes. The first implementation should not claim that one universal creatinine range diagnoses pathology.

### 4.3 Troponin

Troponin demonstrates why one `value_min` and `value_max` on a concept can be misleading. The upper reference limit may be assay-specific, so the method and laboratory provenance matter.

Basic DQ can still validate numeric representation, unit compatibility, missingness, duplicates, and the presence of assay or source-range metadata when policy requires it.

### 4.4 Blood Pressure

Systolic and diastolic blood pressure are separate mapped concepts with a common unit. Declarative constraints can state that:

- Systolic should not be below diastolic for the same observation.
- Both values should use compatible units.
- Both should share the intended person and observation time.

The implementation performs the comparison. The constraint states when and why it applies.

### 4.5 Dates and Events

Structural constraints can state that admission precedes discharge, specimen collection is not after result publication, and child-table person identifiers resolve to the person table.

These are good DQ constraint profiles because they are declarative, reusable, and independent of the mechanics used to scan rows.

## 5. Grain and Archetype Inference

### 5.1 One Continuous Grain-Determination Workflow

Grain determination combines semantic interpretation and data validation in one iterative workflow:

1. Map identifiers, dates, concepts, and structural roles.
2. Generate candidate table archetypes from those mappings.
3. Generate candidate physical keys and analytical grains.
4. Test each candidate using nullness, uniqueness, repetition, cardinality, temporal patterns, and cross-table relationships.
5. Reject weak candidates and test the next-best archetype or grain.
6. Distinguish a wrong grain from an intended grain containing duplicate or missing-key defects.
7. Select the best-supported grain with confidence and alternatives, or mark the grain unresolved.
8. Produce DQ findings against the selected intended grain.

The same evidence both determines and validates the grain. Grain is not inferred in one disconnected phase and validated later. If no candidate is sufficiently supported, the engine must report `grain_unresolved` and avoid misleading duplicate-key conclusions.

An archetype may rerank ambiguous mappings. It must not override a high-confidence mapping merely to make a preferred table pattern fit.

### 5.2 Preserve Three Different Notions

- **Physical row key:** What uniquely identifies the stored row, such as `result_id`.
- **Analytical grain:** What one row represents, such as one person at one timepoint.
- **Parent link:** How the row relates to another entity, such as `patient_id` linking to the person table.

For a wide biomarker table, `result_id` may be the physical key, `patient_id + timepoint` may describe the analytical grain, and biomarker columns are multiple observations stored on that row.

For a long measurement table, the analytical grain may be person + time + analyte + specimen, while a measurement identifier remains the physical key.

Treating every identifier as the grain produces incorrect duplicate checks.

### 5.3 Candidate-Key Detection and Failure Handling

Uniqueness detection is necessary, but uniqueness alone does not define grain. A row number, UUID, import sequence, or hash may be perfectly unique while saying nothing about what the row represents.

The grain engine should generate a bounded set of candidate keys from:

- Layer 0 identifier roles
- Archetype key expectations
- Time, concept, specimen, encounter, and site roles
- Cross-table foreign-key evidence
- Source constraints and metadata

Each candidate should be scored on:

- Semantic fitness for the archetype
- Completeness
- Observed uniqueness ratio
- Number and concentration of duplicate violations
- Minimality
- Stability across files, sites, and extracts
- Foreign-key behavior
- Whether it is a physical surrogate key or an analytical business key

The result should not be only `unique` or `not unique`. It should classify candidates such as:

- `confirmed_key`: semantically appropriate and exactly unique
- `intended_key_with_violations`: semantically appropriate and nearly unique, with likely duplicate defects
- `surrogate_physical_key`: unique record identifier that does not define analytical grain
- `insufficient_evidence`: no reliable key found

If the leading hypothesis is wrong:

1. Keep it and its failed evidence in the candidate list.
2. Evaluate the next-ranked candidate or archetype.
3. Compare candidates using both semantic and statistical evidence.
4. If an expected key is nearly unique, preserve it as the intended grain and report duplicate violations.
5. If only an unrelated surrogate column is unique, use it as the physical row key but do not promote it to analytical grain.
6. Route low-confidence or materially conflicting cases to review.

Thresholds may help classify data defects, but they must be explicit policy. For example, a `patient_id + visit_date` candidate with 99.8% uniqueness might be an intended key with duplicate defects, while a 100% unique `row_uuid` is only a storage key.

The platform implementation should resolve archetype and grain candidates using the semantic repository and table archetype metadata. Richer required/optional/disqualifying role shapes and subtype relations remain future extensions.

### 5.4 Role of Contextual Reasoning in Grain Decisions

Contextual reasoning can help:

- Interpret unfamiliar column names and descriptions
- Propose candidate archetypes
- Explain why competing grain hypotheses differ
- Summarize duplicate clusters for a reviewer
- Suggest additional deterministic tests

It should not:

- Declare rows erroneous without a reproducible rule
- Delete or exclude apparent outliers automatically
- Replace exact uniqueness, cardinality, or foreign-key calculations
- Turn a statistical threshold into clinical truth
- Select a key without exposing the underlying evidence

Rows that violate an intended key remain DQ findings. They can be classified as likely defects only through deterministic evidence, governed policy, or human approval. Contextual output is advisory evidence, not an executable constraint.

### 5.5 Relationship to the DQ Ontology

The DQ ontology does not define the grain. Structural taxonomy roles, archetype shapes, and procedural evidence determine it together.

The DQ ontology contributes declarative conditions such as key completeness, uniqueness, required-role presence, cardinality, and foreign-key integrity. These conditions help evaluate grain candidates and create findings, but they do not force the engine to select a particular archetype.

## 6. Automatic DQ Check Planning

The engine should build a visible check plan before running checks. Taxonomy metadata, DQ ontology constraints, archetypes, unit profiles, range profiles, and procedural profiling together determine which checks apply.

The four quality-check levels are a useful reporting classification, not the organizing architecture:

1. **Column:** type, unit, range, coded values, and other checks selected by the mapped taxonomy concept.
2. **Cross-column:** clinical impossibilities, value-unit disagreement, and within-table relational constraints.
3. **Table:** the complete grain workflow, temporal ordering, duplicates, cardinality, and missing-data patterns.
4. **Dataset/cross-table:** foreign keys, cross-table agreement, and cross-table temporal coherence.

File parsing and encoding remain intake preflight checks. Contextual clinical knowledge selects checks at one of the four scopes rather than creating another level.

### 6.1 Check-Plan Contract

Every planned check should report:

- Its executable scope: `column`, `cross_column`, `table`, or `dataset`
- Why it was selected
- Its taxonomy, DQ ontology, archetype, range, or unit source
- Required columns and tables
- Whether prerequisites were satisfied
- The rule or implementation identifier needed to interpret the finding

### 6.2 DQ Finding Traceability

The primary traceability requirement is the ability to explain the quality of the submitted data when the resulting analysis is interpreted or published.

Every material finding should preserve:

```text
finding_id
dataset_id
table
column_or_columns
affected_record_locator
check_id
severity
message
affected_count
affected_proportion
evidence
analysis_consequence
handling_status
handling_action
resolution_reason
resolved_by
publication_statement
created_at
```

The finding should support a clear statement such as:

> Three percent of biomarker records did not resolve to a patient record and were excluded from the analysis population.

or:

> HbA1c unit information was missing for 12% of records, so unit-dependent range validation could not be performed for those records.

Technical provenance such as taxonomy, DQ rule, and code versions should also be retained when inexpensive. It helps reproduce a result, but it is secondary to recording what was wrong, how much data was affected, how it was handled, and what consequence it had for the analysis.

## 7. Declarative Constraint Contract

The platform's DQ constraint schema should support the following fields:

```text
constraint_id
target_scope
subject_concept_or_role
operator
object_concept_or_role
parameters
applies_when
severity
implementation_id
evidence_source
status
version
```

`target_scope` must be one of `column`, `cross_column`, `table`, or `dataset`.

Example records:

```text
DQ_RANGE_001,column,hba1c,within_plausible_range,,,error,validate_range,...
DQ_TIME_001,cross_column,event_start,temporally_precedes,event_end,,both_present,error,compare_dates,...
DQ_BP_001,cross_column,systolic_blood_pressure,greater_than_or_equal,diastolic_blood_pressure,,same_observation,warning,compare_numeric,...
DQ_UNIT_001,cross_column,measurement_value,unit_compatible_with,unit_column,,mapped_quantity_kind,error,validate_unit_pair,...
DQ_FK_001,dataset,person_identifier,foreign_key_to,person_master.person_identifier,,child_table,critical,validate_fk,...
```

The executable check registry is the authoritative catalogue. It defines check metadata, trigger and execution functions, scanning, aggregation, tolerances, and reporting. The UI derives its check catalogue and run status from this registry, so a duplicate constraint file is unnecessary.

## 8. Recommended Standards Alignment

Use standards by responsibility:

- **OMOP Common Data Model:** domain alignment, standardized concept representation, and common clinical table patterns.
- **LOINC:** laboratory and observation identity, including method/specimen distinctions.
- **SNOMED CT:** clinical entities, findings, conditions, and relationships where licensed.
- **RxNorm:** normalized medication identity.
- **UCUM:** machine-readable units and dimensional compatibility.
- **HL7 FHIR Observation:** contextual ranges qualified by population, age, method, and related attributes.
- **W3C SHACL:** patterns for declarative constraints, applicability, severity, and validation reports.
- **OBO Foundry principles:** stable identifiers, scope, definitions, relation reuse, versioning, documentation, and maintenance.

The platform can use these principles while storing curated artifacts in Supabase tables and executing checks in application code.

## 9. Governance Invariants

1. A semantic identifier has one stable meaning and is never reused.
2. Every concept and relation has a definition, scope, provenance, status, and version.
3. Standard concepts are reused before platform-specific concepts are created.
4. Source observations never silently modify curated semantic knowledge.
5. Taxonomy, archetype, causal, and DQ content remain logically identifiable even when they share one repository and release.
6. Every DQ finding records enough evidence, affected data, handling, and analytical consequence to support later interpretation or publication.
7. Declarative constraints select behavior; executable code implements behavior.
8. Context-dependent clinical rules declare every required qualifier.
9. Grain determination returns evidence, confidence, and alternatives.
10. Semantic changes require regression tests against clean and defective datasets.
11. A synonym addition may change mapping behavior and requires mapping regression tests.
12. Breaking meaning or schema changes require an explicit migration and major version change.
13. Accuracy, clarity, and stable behavior take priority over broad but weak semantic coverage.
14. Every behavior is attributable to a declarative artifact, a programmed function, or an identified contextual reasoning call.
15. Contextual candidates and explanations are distinguishable from reviewed semantic knowledge and deterministic findings.
16. No causal relation may reference the same concept as both subject and object.
17. No two causal relations may share the same subject, predicate, object, and polarity. Opposite polarities on the same triple are permitted when at least one is disambiguated by a qualifier with `is_hard_constraint = true`.
18. A per-column modifier is represented as a governed dimension on the mapping, not as a new concept — unless it changes what is measured such that values are no longer comparable, in which case it forks into a distinct concept (§2.7).

The complete authoring and maintenance rules for each artifact type are defined in §10.

## 10. Business Rules — Taxonomy and Ontology Maintenance

### 10.1 Scope and roadmap

This section defines the operational rules for authoring, editing, and maintaining semantic artifacts in the platform's semantic schema. Rules are organized by artifact type and apply to any editor or tool performing changes.

**Current coverage:** taxonomy, causal ontology, DQ constraints, units, conversions, valid values, and archetypes.

**Pending:** richer range profiles and contextual qualifiers, advanced DQ predicate governance, and LLM-assisted semantic enrichment.

### 10.2 General principles

- Supabase is the primary source of truth. No runtime semantic changes are made by editing application code alone.
- Semantic changes are applied through an explicit release workflow that records versions and rollbacks.
- Every row carries a `review_status`. Valid transitions are:

  | Status | Meaning | Allowed transitions |
  |---|---|---|
  | `pending_review` | Proposed, not yet validated. | → `approved`, → `rejected` |
  | `approved` | Reviewed and active for runtime use. | → `deprecated` |
  | `rejected` | Explicitly declined. | (terminal) |
  | `deprecated` | Previously approved, no longer recommended. | (terminal) |

  A row may not transition directly from `pending_review` to `deprecated`.
- Any change that affects graph structure or DQ rule applicability requires validation tooling before declaring the release stable.
- The `active` boolean and `review_status` are independent. A concept or relation can be `approved` but `active = false` (staged for retirement). Runtime functions filter on both.

### 10.3 Taxonomy concepts

#### When to create a new concept

Create a new concept when:

- A clinical entity, measurement, drug, or structural role is referenced in a proposed ontology relation, DQ constraint, or mapping requirement AND no existing concept is semantically equivalent.
- An existing concept is too broad to serve as the unambiguous subject or object of a specific causal relation.
- A Layer 2 extension is required because no standard vocabulary provides an adequate representation.

Do not create a new concept when:

- A synonym of an existing concept resolves the ambiguity.
- The distinction is dataset-specific or study-specific; that belongs in dataset mapping, not the taxonomy.
- The candidate concept would be a near-duplicate of an existing one at the same layer.

#### Layer assignment

| Layer | Assign when |
|---|---|
| L0 | Structural and data-model roles: person identifier, record identifier, event start, unit column. |
| L1 | Externally standardized clinical concepts. Requires standard code evidence in the same release batch where practical. |
| L2 | Platform extensions not adequately represented by a selected external standard. Must include design rationale. |

#### Required fields for an active approved concept

A concept with `review_status = 'approved'` and `active = true` should carry:

- `local_concept_id` — stable identifier, never reused
- `concept_name` — unambiguous preferred label
- `layer` — 0, 1, or 2
- `augura_domain`
- `version`
- At least one synonym row of type `preferred`
- Layer 1 concepts should have at least one standard code row if licensing and provenance permit it.

Strongly recommended for clinical concepts:

- `value_type`
- `canonical_unit`
- `unit_coverage_status`
- `range_support_status`

#### Cascade rule

A concept introduced by an enrichment change must be included in the same release batch as any relation or constraint that references it.

#### Retiring a concept

A concept may not be deleted while referenced by any active relation. The correct sequence is:

1. Set `active = false`
2. Deprecate or remove all active references
3. Set `review_status = 'deprecated'`

### 10.4 Causal ontology — relations

#### Hard constraints

The platform should enforce:

1. No self-loop: `subject_concept_id != object_concept_id`.
2. No duplicate quadruple: unique `(subject_concept_id, predicate, object_concept_id, polarity)`.

Opposite polarities on the same triple are permitted when qualifiers provide disambiguation.

#### Soft validation rules

- Both subject and object must be active, approved concepts.
- When opposite-polarity rows exist for the same triple, at least one should carry a qualifier with `is_hard_constraint = true`.
- Approved relations should have evidence rows, or be documented as `established_physiology`.
- Approved concepts without active relation membership should be flagged for review.

#### Required fields for an active approved relation

- `relation_id`
- `subject_concept_id`
- `predicate`
- `object_concept_id`
- `polarity`
- `default_strength`
- `default_temporal_lag`
- `mechanism_summary`
- `version`

#### Adding a new causal predicate

New predicates should be rare. Before creating one:

- Check whether an existing predicate and polarity suffice.
- If the distinction matters only for one relation, use a qualifier instead of a new predicate.
- A new predicate requires metadata, direction type, and approval before any relation may reference it.

### 10.5 Causal ontology — qualifiers

Qualifiers assign a structural condition or scope to a relation. They affect DAG construction, not only documentation.

#### Rule 1

If `(A, predicate, B, increases)` and `(A, predicate, B, decreases)` both exist, at least one must carry a qualifier with `is_hard_constraint = true` specifying the condition under which that polarity applies.

#### Rule 2

Use `is_hard_constraint = true` when applying the relation universally would produce a clinically incorrect model. Use `is_hard_constraint = false` to document modulation without restriction.

#### Rule 3

Do not use qualifiers to capture context that belongs in evidence or protocol text.

#### Rule 4

Do not add a qualifier to a relation that holds universally.

#### Required fields for a qualifier row

- `qualifier_id`
- `relation_id`
- `qualifier_type`
- `qualifier_value`
- `qualifier_effect`
- `is_hard_constraint`
- `notes`

Optional fields such as `qualifier_concept_id` should be populated when the qualifier condition maps to an existing taxonomy concept.

### 10.6 Causal ontology — evidence

Evidence rows document the basis for a relation. They are documentary and do not gate approval.

- Every approved relation should have at least one evidence row.
- `source_type` values should distinguish established physiology, RCT, cohort, case series, and expert consensus.
- `evidence_strength` should be `strong`, `moderate`, `weak`, or `established`.
- Subgroup-specific evidence should include `population_notes`.
- Evidence rows are not structural. Adding or removing them should not alter DAG traversal semantics.

### 10.7 Data quality ontology — rules

DQ predicate and constraint authoring rules should follow the same structure as the causal rules, but they are owned by the DQ domain and require separate validation.

## 11. Validation Required for Semantic Updates

Before publishing a semantic release:

- Validate identifier uniqueness and referential integrity.
- Validate predicate subject and object types.
- Validate standard code formats and provenance.
- Validate unit dimensions and conversion round trips.
- Validate that conditional rules declare required context.
- Validate mapping golden sets.
- Validate archetype and grain fixture results.
- Validate DQ check-plan snapshots.
- Validate clean and intentionally defective dataset behavior.
- Review changed runtime findings caused by semantic updates.

## 12. Target Artifact Structure

The active semantic store is the Supabase `public` schema and the frontend bundle loaded at startup. Semantic release versioning, FK enforcement, and logical separation between taxonomy, causal ontology, and DQ constraints are maintained at the database level.

The frontend loader fetches the full bundle in a single call and holds it in memory for the session.

### 12.1 Current implementation gaps

The current platform is moving toward this target architecture. Present gaps include:

- Incomplete representation of Layer 0 structural concepts.
- Unit profile metadata that is not yet fully separable from source evidence.
- Limited unit normalization and governed conversion support.
- Scalar concept ranges that do not distinguish plausibility, reference, critical, clinical decision, and study ranges.
- Missing explicit range-support and unit-coverage statuses.
- Grain inference that is not yet a continuous, evidence-ranked workflow.
- Archetype metadata that is not yet fully loadable or ranked.
- DQ finding persistence that does not fully capture handling action and analytical consequence.

These gaps should be addressed before adding more extensive contextual clinical interpretation.

## 13. Implementation Priorities

### Phase 1: Structural Foundation

- Keep taxonomy, causal ontology, and DQ constraints in clearly named tables.
- Add Layer 0 structural concepts and synonyms.
- Add OMOP, FHIR, and CDISC crosswalk metadata for structural roles.
- Reliably map person, record, encounter, event, time, value, unit, and code roles.
- Separate physical key, analytical grain, and parent link.
- Introduce archetype profiles and a continuous evidence-based grain-determination workflow.
- Introduce dimension grammar and affix archetypes that decompose column labels into a base concept plus governed dimensions, reconciled with grain (§2.7).

### Phase 2: Deterministic DQ Planning

- Normalize concept metadata exposed to DQ.
- Add allowed units, governed transformations, valid values, and broad plausibility metadata.
- Require range-support and unit-coverage status for every supported observation concept where those properties apply.
- Add explicit observed, declared, inferred, ambiguous, missing, and not-applicable unit states.
- Add declarative structural and cross-column constraints.
- Produce an inspectable DQ check plan before execution.
- Correct duplicate and cross-table checks to use inferred grain and keys.
- Persist material findings with affected counts, evidence, handling, and analytical consequences.

### Phase 3: Causal Execution

- Implement the causal procedural workflow through generation of a reviewable causal model and analysis specification.

### Phase 4: Contextual Clinical Knowledge

- Add qualified reference ranges and decision thresholds.
- Represent method, specimen, age, sex, pregnancy, laboratory, and disease context.
- Add clinical consistency rules only when prerequisite mappings are reliable.

## 14. Architectural Decision Summary

- Organize execution around three core boundaries: declarative semantic artifacts, programmed functions, and bounded contextual reasoning.
- Use semantic artifacts to define meaning and policy, programmed functions to calculate and validate, and contextual reasoning only to refine ambiguity.
- Use one shared taxonomy as the semantic foundation.
- Do not create duplicate taxonomies for causal modeling and DQ.
- Keep causal ontology and DQ ontology logically separate through predicates, tables, evidence models, and loader behavior.
- Keep the archetype shape repository separate from both ontologies.
- Permit a small archetype vocabulary for subtype and role relationships, but keep recognition conditions in SHACL-like shapes.
- Decompose column-name affixes into a base concept plus governed dimensions rather than minting a concept per modifier; recognize them with evidence-ranked affix archetypes that reconcile with table grain, and treat a modifier as a dimension only while it keeps values comparable.
- Do not put profiling algorithms or grain inference inside the DQ ontology.
- Add Layer 0 structural concepts before expanding advanced clinical rules.
- Treat grain determination as one iterative workflow that proposes, tests, rejects, selects, and reports findings; use contextual reasoning only as a bounded fallback or explanation.
- Store stable defaults on concepts and conditional knowledge in dedicated profiles.
- Keep DQ execution in code and make check selection declarative and traceable.
- Make DQ traceability primarily about affected data, evidence, handling, and consequences for analysis or publication.
- Treat unit identity as independent evidence from concept identity and suppress conversions and unit-dependent ranges when unit evidence is missing.
- Curate a small, accurate set of clinically meaningful units supported by the platform for each quantitative concept, using UCUM codes and source aliases.
- Use a minimal contextual range record plus optional qualifiers rather than a wide universal schema.
- Require supported observation concepts to declare whether ranges are not applicable, generically curated, contextually curated, context-required, or pending review.
- Leverage standards whenever they apply without forcing an unsuitable standard onto a use case.
- Prefer efficacy, accuracy, clarity, and stable operation over semantic exhaustivity.
- Defer pathology-dependent ranges until units, identifiers, grain, and cross-table relationships are reliable.

## 15. Semantic Release Version Management

### 15.1 Unified versioning

All semantic components share a single release number. A release applies to the platform as a whole, not to individual components in isolation.

| Component | Version field | Notes |
|---|---|---|
| `semantic_release_version` | Top-level release tag | The primary identifier used in tooling and UI |
| `taxonomy_version` | Set equal to `semantic_release_version` | |
| `causal_ontology_version` | Set equal to `semantic_release_version` | |
| `dq_ontology_version` | Set equal to `semantic_release_version` | Bumps even if DQ artifacts were not touched |
| `omop_cdm_version` | Fixed at `5.4` unless an OMOP upgrade occurs | |

### 15.2 Explicit changelog

Every release should record per-entity pre-apply state for the semantic tables. This enables exact rollback of the head release.

### 15.3 Rollback mechanics

Rollback should be performed only on the head release and should revert each changed entity to its pre-apply state. The platform should maintain an explicit changelog to support this.

### 15.4 Semantic layer workspace

The `/semantic` route in the platform provides a read-only admin view of the current semantic release:

| Tab | Contents |
|---|---|
| **Taxonomy** | Browse active concepts with domain/layer/standard-code filters. | 
| **Causal ontology** | Browse active relations with predicate/polarity filters. | 
| **Versions** | Current release manifest and per-table counts. |

### 15.5 Release workflow summary

1. Propose a new semantic release with explicit review-ready artifact rows.
2. Review the proposed artifact set and mark approved rows.
3. Apply the release through the semantic enrichment workflow.
4. Validate coherence, mapping, archetype, and DQ regression tests.
5. Roll back the head release if the release is invalid.

---

## References

- W3C, SHACL Recommendation: https://www.w3.org/TR/shacl/
- OBO Foundry Principles: https://obofoundry.org/principles/fp-000-summary.html
- UCUM Specification: https://ucum.org/ucum
- OHDSI OMOP Common Data Model: https://ohdsi.github.io/CommonDataModel/
- HL7 FHIR R4 Observation definitions: https://hl7.org/fhir/R4/Observation-definitions.html
- HL7 FHIR R5 ObservationDefinition: https://fhir.hl7.org/fhir/observationdefinition.html
- CDISC Study Data Tabulation Model: https://www.cdisc.org/standards/foundational/sdtm
- HL7 FHIR R5 reference range applicability: https://hl7.org/fhir/R5/valueset-referencerange-appliesto.html
