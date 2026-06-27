# Taxonomy Expansion — Stage 1 (concepts + affix recognition), Synthetic Medium dataset

**Date:** 2026-06-26
**Status:** Proposal for review (nothing applied to the governed layer)
**Dataset:** `test datasets/26-06-08_Synthetic_Medium/clean/` (11 CSVs, ~150 columns)
**North star:** `docs/specs/2026-06-26-semantic-layer-expansion-north-star.md` (Stage 1)
**Method:** Option A — Claude Code (Opus 4.8) as one-shot, web-grounded analyst. Dataset columns +
sample values compared against the live governed taxonomy in `public` (172 active concepts, ~1,500
synonyms, 5 affix archetypes, 12 dimension kinds; pulled 2026-06-26).

---

## 0. Summary

| Outcome | Count | Where |
|---|---|---|
| Columns triaged | ~150 | Appendix A |
| Map to an **existing** concept (already a synonym) | ~35 | — |
| Existing concept, **add a synonym** | ~22 | §4 |
| **New concepts** proposed | ~63 | §3 |
| **True affix / dimension** findings | 4 | §2.1 |
| **Normalization / unit-handling** findings (not dimensions) | 2 | §2.2 |
| Ambiguities to resolve before applying | 5 | §5 |

**Headline:** the taxonomy is **disease-management-shaped** (CKD, COPD, HF, diabetes, oncology, device
telemetry) and **thin on the general longitudinal-wellness panel** this dataset is: standard lab
chemistry / hematology / endocrine biomarkers, DEXA body composition, validated PRO scales (PHQ-9,
GAD-7, PSQI), and lifestyle / social-determinant fields.

---

## 2. Column-name token findings

**Not every name suffix is an affix.** Two kinds of tokens appear in these columns, and they must be
handled differently:

- **§2.1 True dimensions** — a token that carves the *same base concept* into distinct, comparable,
  governable variants (left vs right; T0 vs T1; serum vs CSF; mean vs max). These belong in the affix
  grammar (`dimension_kinds` + `affix_archetypes`).
- **§2.2 Normalization tokens** — a token that conveys **units** or is **filler** (`_value`, `_result`,
  `_level`). It does **not** create a variant; it must be *stripped during matching* so the base
  concept is found, with units routed to `canonical_unit` / the unit column / `unit_conversions`.
  Modeling these as affixes adds nothing.

Today's grammar has 5 archetypes (`AFX_LATERALITY`, `AFX_DERIVED_STAT`, `AFX_SCHEDULED_TIME`,
`AFX_RELATIVE_TIME_POSTOP`, `AFX_SPECIMEN`) and 12 dimension kinds, 7 with **no archetype yet**
(`aggregation_window`, `body_site`, `condition_status`, `method`, `rater`, `replicate`, `vocabulary`).

### 2.1 True dimension findings (real affix work)

- **F3 — `AFX_DERIVED_STAT` is missing the `avg` alias.** The archetype has `mean, max, min, sd, delta,
  change, auc, nadir` but the data uses **`avg`**: `daily_steps_avg`, `sleep_hours_avg`,
  `active_minutes_avg`, `screen_time_hours_avg`, `avg_sleep_hours`. → add `avg`, `average`.
- **F4 — `body_site` dimension has no archetype, and the data needs it.** DEXA T-scores
  `lumbar_spine_t_score`, `femoral_neck_t_score`, `total_hip_t_score` are the *same measurement at three
  sites*; android/gynoid are body-region variants of body-fat %. One concept + an `AFX_BODY_SITE`
  archetype (`lumbar_spine`, `femoral_neck`, `total_hip`, `android`, `gynoid`) is cleaner than 3–5
  concepts. (Decide site-vs-region modeling in review.)
- **F5 — timepoint tokens `T0/T1/T2` aren't recognized.** `timepoint ∈ {T0,T1,T2}`. The *Timepoint
  Label* concept (`L2_TV002`) and `AFX_SCHEDULED_TIME` exist but list neither → add `t0,t1,t2`.
- **F6 — `condition_status` dimension has no archetype.** `diagnoses.status ∈
  {ACTIVE,CHRONIC,RESOLVED}` (and the other `status` fields). → define it (or a Diagnosis Status
  concept with valid values — §3.6, §5.4).

### 2.2 Normalization / unit-handling findings (NOT dimensions)

- **F1 — unit suffixes are unit *handling*, not a dimension.** The dominant convention is
  `<concept>_<unit>` (`apob_g_l`, `ldl_mmol_l`, `systolic_bp_mmhg`, `vit_b12_pmol_l`, `wbc_1e9_l`, …,
  >40 columns). The matcher should **strip the unit token to find the base concept** and route the unit
  to `canonical_unit` + `unit_conversions`. This is *not* a new affix archetype/dimension — a
  hypothetical `apob_mg_dl` is the same quantity in different units, not a distinct variant. A simple
  unit-token→UCUM lookup for the matcher is enough (`g_l→g/L`, `mmol_l→mmol/L`, `pct→%`, `mmhg→mm[Hg]`,
  `bpm→/min`, `u_l→U/L`, `1e9_l→10^9/L`, …).
- **Filler tokens** (`_value`, `_result`, `_level`) carry no meaning — `glucose_value` is just glucose,
  `creatinine_value` is just creatinine. The Measurement Value structural concept already lists `value`
  as a synonym; the matcher should treat these as stop-words. (The remaining `glucose_value` issue is a
  concept *collision*, not an affix — §5.1.)
- **F2 — unit *mismatches* between data and canonical.** Data reports several analytes in mmol/L while
  the taxonomy canon is mg/dL: `ldl_mmol_l`, `hdl_mmol_l`, `tg_mmol_l`, `glucose_value`
  (+`glucose_unit`), `creatinine_value` (+`creatinine_unit` ∈ {mg/dL, µmol/L}). Concept mapping is
  fine; a `unit_conversions` entry makes the values comparable. Stage 3.

---

## 3. New concepts proposed

Fields follow `taxonomy_concepts`: `concept_name | augura_domain | value_type | value_min–value_max |
canonical_unit | dq_column_role`. Ranges are **plausible physiological bounds** (sanity limits, the
existing style), not reference ranges. LOINC codes are *suggested, verify* (Stage-1 scope is the
concept; standard codes are Stage-3 `taxonomy_standard_codes`, included where confirmed via web).

### 3.1 Laboratory biomarkers — `biomarker` (numeric, measurement_value) — `02_biomarker_results.csv`
The largest gap.

| Concept | unit | min–max | source col | LOINC (verify) |
|---|---|---|---|---|
| Apolipoprotein B | g/L | 0.2–3.0 | `apob_g_l` | 1884-6 |
| Apolipoprotein A1 | g/L | 0.3–3.5 | `apoa1_g_l` | 1869-7 |
| Ferritin | ng/mL | 1–2000 | `ferritin_ng_ml` | 2276-4 |
| Serum Iron | µmol/L | 1–80 | `serum_iron_umol_l` | 14798-3 |
| Transferrin | g/L | 0.5–6 | `transferrin_g_l` | 3034-6 |
| Transferrin Saturation | % | 0–100 | `transferrin_saturation_pct` | 2502-3 |
| White Blood Cell Count | 10^9/L | 0–100 | `wbc_1e9_l` | 6690-2 |
| Neutrophil-to-Lymphocyte Ratio | ratio | 0–50 | `nlr_ratio` | — |
| Blood Urea (BUN) | mmol/L | 0–60 | `urea_mmol_l` | 22664-7 |
| Serum Sodium | mmol/L | 100–180 | `sodium_mmol_l` | 2951-2 |
| Serum Potassium | mmol/L | 1–10 | `potassium_mmol_l` | 2823-3 |
| Aspartate Aminotransferase (AST) | U/L | 0–2000 | `ast_u_l` | 1920-8 |
| Alanine Aminotransferase (ALT) | U/L | 0–2000 | `alt_u_l` | 1742-6 |
| Gamma-Glutamyl Transferase (GGT) | U/L | 0–2000 | `ggt_u_l` | 2324-2 |
| Total Bilirubin | µmol/L | 0–600 | `bilirubin_total_umol_l` | 1975-2 |
| Fasting Serum Insulin | mIU/L | 0–300 | `insulin_miu_l` | 27353-2 |
| Vitamin D (25-OH) | nmol/L | 0–400 | `vit_d_nmol_l` | 14635-7 |
| Vitamin B12 (Cobalamin) | pmol/L | 0–1500 | `vit_b12_pmol_l` | 16695-9 |
| Serum Magnesium | mmol/L | 0.1–5 | `magnesium_mmol_l` | 19123-9 |
| Omega-3 Index | % | 0–20 | `omega3_index_pct` | — |
| Testosterone (Total) | nmol/L | 0–60 | `testosterone_nmol_l` | 14913-8 |
| Estradiol (E2) | pmol/L | 0–4000 | `estradiol_pmol_l` | 14715-7 |
| Sex Hormone-Binding Globulin (SHBG) | nmol/L | 0–250 | `shbg_nmol_l` | 13967-5 |
| Prostate-Specific Antigen (PSA, total) | µg/L | 0–100 | `psa_total_ug_l` | 2857-1 |
| Thyroid-Stimulating Hormone (TSH) | mIU/L | 0–100 | `tsh_miu_l` | 3016-3 |
| Free Triiodothyronine (FT3) | pmol/L | 0–50 | `ft3_pmol_l` | 3051-0 |
| Free Thyroxine (FT4) | pmol/L | 0–100 | `ft4_pmol_l` | 3024-7 |
| Cortisol (serum) | nmol/L | 0–2000 | `cortisol_nmol_l` | 2143-6 |
| DHEA-Sulfate (DHEAS) | µmol/L | 0–30 | `dheas_umol_l` | 14688-6 |

### 3.2 Body composition / DEXA — `measurement` (numeric) — `03_dexa_results.csv`

| Concept | unit | min–max | source col |
|---|---|---|---|
| Body Fat Percentage | % | 0–100 | `body_fat_pct` (+ android/gynoid via body-region affix — F4) |
| Total Fat Mass | kg | 0–200 | `total_fat_mass_kg` |
| Lean Body Mass (Total) | kg | 0–150 | `total_lean_mass_kg` |
| Appendicular Lean Mass Index (ALMI) | kg/m2 | 0–15 | `almi_kg_m2` (sarcopenia ♂≤7.23, ♀≤5.67 — Stage 3) |
| Visceral Fat Area | cm2 | 0–500 | `visceral_fat_area_cm2` |
| Bone Mineral Density (absolute) | g/cm2 | 0.3–2.0 | `whole_body_bmd_g_cm2` |
| Bone Mineral Density T-score | SD (unitless) | -6–6 | `*_t_score` ×3 via `AFX_BODY_SITE` (F4) |
| FRAX 10-yr Major Osteoporotic Probability | % | 0–100 | `frax_major_osteoporotic_pct` |
| FRAX 10-yr Hip Fracture Probability | % | 0–100 | `frax_hip_pct` |
| Waist Circumference | cm | 30–200 | `01_patients.waist_cm` |

### 3.3 Vitals / wearable metrics — `measurement` (numeric) — `06_wearable_aggregates.csv`

| Concept | unit | min–max | source col |
|---|---|---|---|
| Heart Rate Variability (HRV) | ms | 0–300 | `hrv_ms` |
| Active Minutes (MVPA) | minutes/day | 0–1440 | `active_minutes_avg` (`avg` affix) |
| Screen Time | hours/day | 0–24 | `screen_time_hours_avg` (`avg` affix) |
| Sleep Duration | hours | 0–24 | `sleep_hours_avg`, `avg_sleep_hours` (`avg` affix) |

> `daily_steps_avg`, `resting_hr_bpm` map to **existing** *Physical Activity Level* / *Heart Rate* (§4).

### 3.4 Patient-reported outcomes — `observation` — `05_questionnaire_followup.csv`

| Concept | value_type | min–max | source col |
|---|---|---|---|
| PHQ-9 Depression Score | numeric | 0–27 | `phq9_total` |
| GAD-7 Anxiety Score | numeric | 0–21 | `gad7_total` |
| PSQI (Pittsburgh Sleep Quality Index) | numeric | 0–21 | `psqi_total` |
| General Wellbeing (self-report) | numeric | 1–10 | `general_wellbeing_1_10` |
| PHQ-9 Severity Category | categorical | — | `phq9_category` |
| GAD-7 Severity Category | categorical | — | `gad7_category` |
| Energy Level (self-report) | categorical | — | `energy_level` |
| Sleep Quality (self-report) | categorical | — | `sleep_quality` |

> The `*_category` fields are derived bins of their score — review whether to model as separate concepts
> or as DQ valid-value sets on the parent score (Stage 3).

### 3.5 Lifestyle / behavioral / social determinants — domain `behavioral` (or new `social_determinant`)
From `04_health_profile.csv` (+ `05`):

| Concept | value_type | source col |
|---|---|---|
| Diet Type / Dietary Pattern | categorical | `diet_type` (≠ existing *Dietary Compliance* = adherence) |
| Alcohol Consumption Frequency | categorical | `alcohol_frequency` |
| Perceived Stress Level | numeric 0–10 | `stress_level_0_10` |
| Motivation Level | numeric 1–10 | `motivation_scale_1_10` |
| Sleep Schedule Consistency | categorical | `sleep_schedule_consistency` |
| Preferred Communication Style | categorical | `preferred_communication_style` |
| Living Situation | categorical | `living_situation` |
| Environment Type (urban/suburban/rural) | categorical | `environment_type` |

### 3.6 Medication, diagnosis, demographic, structural

| Concept | domain | value_type | source col |
|---|---|---|---|
| Medication Dose Amount | drug | numeric (mg) | `dose_mg` (generalizes existing *Insulin Dose Amount*) |
| Dosing Frequency | drug | categorical | `frequency` |
| Medication Indication | drug | text | `indication` |
| Drug Name (label) | drug | text | `drug_name` |
| Diagnosis Name (label) | condition | text | `diagnosis_name` |
| Diagnosis / Condition Status | condition | categorical | `status` (ACTIVE/CHRONIC/RESOLVED — F6) |
| Date of Birth | demographic | date | `birth_date` |
| Country | demographic | categorical | `country_code` |
| Clinician / Provider Identifier | structural | entity_id | `clinician_id` (`rater` dimension) |
| Wearable Device Type | device_telemetry | categorical | `device_type` (`method` dimension) |
| Clinical Note (free text) | observation | text | `visit_notes_free_text` |

### 3.7 Augura program constructs — suggest new domain `program` — `10/11_*.csv`

| Concept | value_type | source col |
|---|---|---|
| Health Pillar | categorical | `recommendations.pillar` |
| Recommendation Priority | categorical | `priority` |
| Recommendation Title | text | `recommendations.title` |
| Recommendation Status | categorical | `recommendations.status` |
| Protocol Name | text | `protocols.title` |
| Protocol Status | categorical | `protocols.status` |
| Lucis Score | numeric 0–100 | `lucis_score_at_creation` (Augura composite) |
| Goal Count | numeric | `goal_count` |

> §3.6 / §3.7 free-text fields (`drug_name`, `indication`, `*_title`, `visit_notes`) are
> **low-confidence** as governed concepts — they're free-text payloads, not measurements. Keep the
> categoricals/numerics; decide per-field on the text ones.

---

## 4. New synonyms for existing concepts (no new concept needed)

| Dataset column | Existing concept (`local_concept_id`) | Note |
|---|---|---|
| `ldl_mmol_l` | LDL Cholesterol (`L1_M029`) | unit mismatch — F2 |
| `hdl_mmol_l` | HDL Cholesterol (`L1_M030`) | unit mismatch — F2 |
| `tg_mmol_l` | Triglycerides (`L1_M032`) | unit mismatch — F2 |
| `crp_mg_l` | C-Reactive Protein (`L2_BM002`) | |
| `hemoglobin_g_dl` | Hemoglobin (`L1_M025`) | |
| `creatinine_value` | Serum Creatinine (`L1_M022`) | `_value` filler; + `creatinine_unit` → Unit column |
| `egfr_ml_min` | eGFR (`L1_M021`) | canonical mL/min/1.73m2 |
| `hba1c_pct` | Hemoglobin A1c (`L1_M001`) | |
| `systolic_bp_mmhg` | Systolic BP (`L1_M008`) | |
| `diastolic_bp_mmhg` | Diastolic BP (`L1_M009`) | |
| `vo2max_ml_kg_min` | VO2 Max (`L1_M033`) | |
| `resting_hr_bpm` | Heart Rate (`L1_M010`) | `resting` qualifier |
| `daily_steps_avg` | Physical Activity Level (`L2_BH001`) | `avg` affix (F3) |
| `creatinine_unit`, `glucose_unit` | Unit of Measure Column (`L0_unit_column`) | add as synonyms |
| `timepoint` | Timepoint Label (`L2_TV002`) | + values t0/t1/t2 — F5 |
| already-synonym ✓ | activity_level, gender, ethnicity, smoking_status, study_arm, height_cm, weight_kg, homa_ir, admission/discharge_datetime, icd10_code | no action |

---

## 5. Ambiguities to resolve before applying

1. **`glucose_value` collision — resolved by table context (general rule).** The bare string is
   ambiguous (it's a global synonym of **Sensor Glucose (CGM)** `L1_M006`), but the **table** resolves
   it: `glucose_value` sits in `02_biomarker_results.csv`, a lab panel (one row per `timepoint`, a
   `sample_date`, a `glucose_unit` column, siblings all fasting serum analytes) — and the dataset has
   **no CGM signature anywhere** (no `sensor_glucose`, time-in-range, variability, CGM device, or
   high-frequency timestamps). → map to **Serum/Plasma Glucose**, not CGM (use *Fasting Plasma Glucose*
   `L1_M005` only if the protocol confirms fasting draws; otherwise a generic *Serum Glucose*).
   **Principle:** column→concept mapping is **table-scoped**. Global synonyms only *generate candidates*;
   the table archetype + sibling columns are the *resolver*. The matcher (and any future endpoint)
   should disambiguate per table, not by the bare name — this is what `table_archetypes` is for.
2. **`rxnorm_code`** already appears under *Vocabulary Code Column* (`L0_vocabulary_code_column`), but
   there is no concept-specific *RxNorm Code* like the existing *Drug Code (NDC)* / *Procedure Code
   (CPT)*. Reuse the generic vocab column, or add *RxNorm Code*?
3. **`chronic_conditions`** is a comma-separated multi-value list (`TYPE_2_DIABETES,HYPERLIPIDAEMIA`).
   Maps to condition concepts but is denormalized — explode vs. treat as free list?
4. **`status` reused** across diagnoses/medications/recommendations/protocols with different value sets
   — one *Status* concept with context, or per-entity status concepts? (relates to F6).
5. **Domain placement** for §3.5 lifestyle/social fields and §3.7 Augura constructs — reuse `behavioral`
   or introduce `social_determinant` / `program`?

---

## 6. Deferred (out of Stage-1 scope)

- **Stage 2 (causal):** candidate `ontology_relations` (e.g. metformin → HbA1c; visceral fat →
  HOMA-IR; physical activity → VO2 max). Not proposed here.
- **Stage 3 (DQ):** valid-value sets for the new categoricals, `taxonomy_dq_valid_values`, unit
  conversions (F1/F2), and `taxonomy_standard_codes` (the LOINC seeds above).

---

## Appendix A — full column triage

Legend: **E** existing (synonym) · **E+S** existing, add synonym · **NEW** new concept · **AFX** true
dimension finding · **NORM** unit/filler normalization · **AMB** ambiguity · **STRUCT** id/date.

- **01_patients:** patient_id=E(Person Id) · gender=E(Sex) · birth_date=NEW(Date of Birth) ·
  enrollment_date=E · site_id=E · height_cm=E · weight_kg=E · waist_cm=NEW · ethnicity=E ·
  country_code=NEW(Country) · death_date=E · study_arm=E(Treatment Arm).
- **02_biomarker_results:** result_id=STRUCT · patient_id=E · timepoint=E+S+AFX(F5) · sample_date=E ·
  site_id=E · apob/apoa1/ferritin/serum_iron/transferrin/transferrin_sat/wbc/nlr/urea/sodium/potassium/
  ast/alt/ggt/bilirubin/insulin/vit_d/vit_b12/magnesium/omega3/testosterone/estradiol/shbg/psa/tsh/ft3/
  ft4/cortisol/dheas = **NEW**(§3.1), unit suffix=NORM(F1) · ldl/hdl/tg/crp/hemoglobin/egfr/hba1c=E+S
  (F2) · creatinine_value=E+S(NORM `_value`) · glucose_value=AMB(§5.1) · homa_ir=E ·
  creatinine_unit/glucose_unit=E+S(Unit).
- **03_dexa_results:** all measures=NEW(§3.2); t-scores via AFX(F4); android/gynoid via region affix.
- **04_health_profile:** activity_level=E · smoking_status=E · diet_type/sleep_schedule_consistency/
  alcohol_frequency/preferred_communication_style/living_situation/environment_type=NEW cat(§3.5) ·
  avg_sleep_hours=NEW(Sleep Duration)+AFX(F3) · stress_level_0_10/motivation_scale_1_10=NEW ·
  chronic_conditions=AMB(§5.3) · current_medications_yn=NEW(med-use flag) · profile_date=E.
- **05_questionnaire_followup:** phq9/gad7/psqi/general_wellbeing=NEW · *_category/energy/sleep_quality=
  NEW cat · stress/motivation=NEW(shared) · response_date=E.
- **06_wearable_aggregates:** device_type=NEW(method) · daily_steps_avg=E+S+AFX · resting_hr_bpm=E+S ·
  hrv_ms/active_minutes_avg/screen_time_hours_avg=NEW · sleep_hours_avg=NEW(Sleep Duration)+AFX ·
  recorded_month=E.
- **07_clinical_visits:** systolic/diastolic/weight/vo2max=E+S · admission/discharge_datetime=E ·
  clinician_id=NEW · visit_notes_free_text=NEW(text).
- **08_diagnoses:** icd10_code=E · diagnosis_name=NEW(text) · onset_date=E · status=NEW/AFX(F6).
- **09_medications:** drug_name=NEW(text) · rxnorm_code=AMB(§5.2) · dose_mg=NEW · frequency=NEW cat ·
  indication=NEW(text) · start/end_date=E.
- **10_recommendations:** pillar/priority/status=NEW cat · title=NEW(text) · created_by=NEW · rec_date=E.
- **11_protocols:** title=NEW(text) · status=NEW cat · lucis_score_at_creation=NEW · goal_count=NEW ·
  start/end/review_date=E.
