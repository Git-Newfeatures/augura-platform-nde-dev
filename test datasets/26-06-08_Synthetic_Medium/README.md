# Augura DQ Pressure-Test Dataset v2

Synthetic multi-table health dataset for pressure-testing the Augura Data Quality engine.  
Two complete versions: **clean** (physiologically consistent) and **degraded** (31 injected naturalistic errors).  
15 patients · 2 sites · 3 timepoints · 11 tables.

---

## Directory structure

```
test-datasets-v2/
├── clean/                     ← 11 source-of-truth CSVs
├── degraded/                  ← 11 modified CSVs (errors injected)
├── ground_truth/
│   ├── ground_truth.json      ← 31 engine-agnostic observable findings
│   ├── errors_catalog.json    ← machine-readable error manifest (produced by inject_errors.py)
│   ├── ground_truth_report.xlsx
│   └── generate_xlsx.py
├── generate_clean.py
└── inject_errors.py
```

---

## Tables

| # | File | Grain | Key columns |
|---|------|-------|-------------|
| 01 | `01_patients.csv` | 1 row / patient | patient_id, gender, birth_date, enrollment_date, site_id, death_date |
| 02 | `02_biomarker_results.csv` | 1 row / patient / timepoint | result_id, patient_id, timepoint, 41 biomarker columns |
| 03 | `03_dexa_results.csv` | 1 row / patient / timepoint* | scan_id, body_fat_pct, lean_mass_kg, bone_mineral_density, t-scores |
| 04 | `04_health_profile.csv` | 1 row / patient | chronic_conditions (comma-separated), lifestyle flags |
| 05 | `05_questionnaire_followup.csv` | 1 row / patient / timepoint | phq9_total, phq9_category, sleep_quality, stress_level |
| 06 | `06_wearable_aggregates.csv` | 1 row / patient / month (4 months) | daily_steps_avg, sleep_hours_avg, resting_hr_bpm, hrv_ms |
| 07 | `07_clinical_visits.csv` | 1 row / patient / timepoint | visit_date, admission_datetime, discharge_datetime, BP, weight |
| 08 | `08_diagnoses.csv` | 1 row / diagnosis | diagnosis_id, patient_id, icd10_code, diagnosis_name |
| 09 | `09_medications.csv` | 1 row / medication record | medication_id, patient_id, drug_name, dose_mg, start_date |
| 10 | `10_recommendations.csv` | 1 row / patient / timepoint | recommendation text, category, priority |
| 11 | `11_protocols.csv` | 1 row / patient | study_arm, protocol_version, consent_date |

\* P011 has T0 only for DEXA (deceased before T1 scan in clean version).

---

## Patient archetypes

| ID | Sex | Site | Archetype | Notes |
|----|-----|------|-----------|-------|
| P001 | F | SITE_A | Metabolic syndrome, improving | |
| P002 | M | SITE_A | Athlete, stable | |
| P003 | F | SITE_A | Hypothyroid, improving on Levothyroxine | TSH 8.2→3.8→2.1 |
| P004 | M | SITE_A | CKD stage 3, slow decline | Creatinine 2.1→2.3→2.5 mg/dL |
| P005 | F | SITE_A | Iron-deficiency anaemia | |
| P006 | M | SITE_A | NAFLD / liver disease | |
| P007 | F | SITE_A | Osteoporosis | On Alendronic acid + Vit D |
| P008 | M | SITE_A | CVD risk | |
| P009 | F | SITE_B | Healthy control | Anchor for near-duplicate E01 |
| P010 | M | SITE_B | Improving metabolic health | |
| P011 | F | SITE_B | Advanced cancer | **Death date 2024-06-02** — T0/T1 only in clean |
| P012 | M | SITE_B | Testosterone deficiency / hypogonadism | |
| P013 | F | SITE_B | Perimenopause | Near-duplicate of P009 in degraded |
| P014 | F | SITE_B | Elderly multi-morbid (T2DM, HTN, CKD) | |
| P015 | F | SITE_B | Mental health (anxiety/depression) | |

---

## Site unit conventions

| Measurement | SITE_A | SITE_B |
|-------------|--------|--------|
| Creatinine | mg/dL | µmol/L |
| Glucose | mmol/L | mg/dL |

Both sites use companion `*_unit` columns per row.

---

## Ground truth methodology

Errors were designed **independently of the DQ check-ID taxonomy**. The ground truth describes what a human clinical data expert would observe — table, column(s), affected rows, the observable problem, and the expected state — without referencing any check identifier.

The test question is: **did the DQ engine independently surface the same problems?**

Each finding has severity `hard` (logically/factually impossible) or `soft` (clinically implausible, requires human review).

### Finding summary

| ID | Severity | Table | Category | Short description |
|----|----------|-------|----------|-------------------|
| F01 | soft | patients | near_duplicate_entity | P013 demographics near-identical to P009 |
| F02 | hard | patients | impossible_date | P014 enrollment_date 2026-03-05 (future) |
| F03 | hard | biomarker_results | unparseable_value | BIO-001 glucose_value = "fasting" |
| F04 | soft | biomarker_results | cross_table_clinical_incoherence | P003 TSH 0.02 contradicts HYPOTHYROIDISM + Levothyroxine |
| F05 | soft | biomarker_results | implausible_longitudinal_trajectory | P004 creatinine spike 2.1→8.9→2.5 mg/dL |
| F06 | hard | biomarker_results | cross_column_formula_contradiction | BIO-011 creatinine 8.9 mg/dL with eGFR 91 (impossible) |
| F07 | hard | biomarker_results | impossible_value_hard_range | BIO-014 HbA1c = 97.4% |
| F08 | hard | biomarker_results | unit_scale_mismatch | BIO-028 creatinine 1.1 µmol/L (mg/dL value in µmol/L field) |
| F09 | hard | biomarker_results | sentinel_in_numeric_field | BIO-029 cortisol = -99 |
| F10 | soft | biomarker_results | statistical_outlier | BIO-027 LDL 14.7 mmol/L (P009 baseline 2.2) |
| F11 | soft | biomarker_results | site_concentrated_missingness | vit_b12 missing 100% at SITE_B, 0% at SITE_A |
| F12 | soft | biomarker_results | co_missing_ordered_panel | Iron panel (ferritin+serum_iron+transferrin) co-missing at T2 for P006/P012/P014 |
| F13 | hard | biomarker_results | orphan_foreign_key | BIO-045 patient_id = "P099" (non-existent) |
| F14 | hard | biomarker_results | grain_duplicate | BIO-020 and BIO-046 both P007-T1 |
| F15 | soft | dexa_results | implausible_longitudinal_trajectory | P001 body_fat_pct 38.5→11.8% in 6 months |
| F16 | hard | dexa_results | impossible_value_hard_range | DEX-014 lumbar T-score = +8.2 |
| F17 | soft | questionnaire_followup | invalid_coded_value | QFU-017 phq9_category = "MODERATE-SEVERE" |
| F18 | soft | questionnaire_followup | missing_longitudinal_record | P015 T1 questionnaire missing despite active T1 visit |
| F19 | hard | wearable_aggregates | sentinel_in_numeric_field | WAR-008 daily_steps_avg = -5 |
| F20 | hard | wearable_aggregates | unparseable_value | WAR-043 sleep_hours_avg = "not synced" |
| F21 | hard | wearable_aggregates | sentinel_in_numeric_field | WAR-055 resting_hr_bpm = 9999 |
| F22 | soft | clinical_visits | non_standard_date_format | VIS-023 visit_date = "08/05/2024" (DD/MM/YYYY) |
| F23 | hard | clinical_visits | temporal_ordering_violation | VIS-029 discharge (11:00) before admission (14:30) |
| F24 | hard | clinical_visits | timepoint_ordering_violation | P007 T1 visit (2024-08-01) after T2 visit (2024-05-01) |
| F25 | hard | clinical_visits | event_after_death | VIS-045 P011 visit 2024-08-18 (77 days after death) |
| F26 | hard | clinical_visits | cross_column_physiological_impossibility | VIS-040 diastolic (96) > systolic (88) mmHg |
| F27 | soft | clinical_visits | implausible_longitudinal_value | P015 weight 59.4→46.8 kg in 3 months |
| F28 | soft | diagnoses | wrong_coding_vocabulary | DGN-008 ICD-9 code "571.40" in ICD-10 field |
| F29 | hard | diagnoses | sex_condition_incoherence | DGN-007 N40.1 (BPH) assigned to female patient P005 |
| F30 | soft | diagnoses | missing_expected_records | P014 has zero diagnosis rows despite T2DM + HTN + CKD in health_profile |
| F31 | soft | medications | unit_embedded_in_numeric_field | MED-018 dose_mg = "25mg" |

---

## Reproducing the dataset

```bash
# Create clean tables
python3 generate_clean.py

# Inject errors into degraded/ directory
python3 inject_errors.py

# Generate XLSX report
cd ground_truth && python3 generate_xlsx.py
```

Requires Python 3.9+ and `openpyxl` (`pip install openpyxl`).

---

## Special handling

**P011 (deceased):** Clean version contains T0/T1 records only across all tables.  
Degraded version adds a T2 clinical visit (VIS-045) dated after death — this is injected error F25.

**Sex-specific biomarkers:** `testosterone_nmol_l` and `psa_total_ug_l` are intentionally blank for all female patients in both versions. This is clinically appropriate and is **not** a DQ error.

**Iron panel co-missingness (F12):** The three columns `ferritin_ng_ml`, `serum_iron_umol_l`, and `transferrin_g_l` are simultaneously missing at T2 for P006, P012, and P014. The Pearson correlation of missingness across these three columns is 1.0 — an unambiguous signal of a skipped ordered panel.
