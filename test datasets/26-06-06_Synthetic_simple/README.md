# DQ Engine Pressure-Test Datasets

Synthetic multi-table health dataset for testing the Augura data quality engine  
(`src/dq/dq-engine.js` and related checks as specified in  
`lucis-dashboard/docs/superpowers/specs/2026-06-05-dq-engine-design.md`).

---

## Cohort overview

**20 patients** — 10 at SITE_A (Paris), 10 at SITE_B (Lyon)  
**3 lab/visit timepoints** — T0 (enrollment), T1 (+90 days), T2 (+180 days)  
**2 DEXA timepoints** — T0 and T2 (P001–P015 only)  
**4 monthly device record windows** — starting from enrollment month  
**2 questionnaire timepoints** — T0 and T1

Total rows: ~330 across 6 tables — fast to profile in-browser.

---

## Table schema

### `01_patients.csv` — **grain: patient_id** (static entity table)
| Column | Role | Notes |
|---|---|---|
| `patient_id` | entity_id | P001–P020 |
| `site_id` | coded_value | SITE_A, SITE_B |
| `birth_date` | timestamp | ISO date |
| `sex` | coded_value | M, F |
| `enrollment_date` | timestamp | Study entry date |
| `death_date` | timestamp | Nullable; P003 died 2024-07-20 |
| `weight_kg` | measurement_value | Baseline weight |
| `height_cm` | measurement_value | Baseline height |
| `country_code` | coded_value | FR |

### `02_lab_results.csv` — **grain: (patient_id, visit_date, timepoint)** (longitudinal)
| Column | Role | Notes |
|---|---|---|
| `result_id` | entity_id | LAB-001 to LAB-060 |
| `patient_id` | foreign_key | → patients.patient_id |
| `visit_date` | timestamp | ISO date |
| `timepoint` | coded_value | T0, T1, T2 |
| `site_id` | coded_value | |
| `glucose_mg_dl` | measurement_value | numeric, range 50–500 |
| `hba1c_pct` | measurement_value | numeric, range 3–18 |
| `creatinine_mg_dl` | measurement_value | numeric, range 0.2–15 |
| `creatinine_unit` | unit_column | companion unit for creatinine |
| `egfr_ml_min` | measurement_value | |
| `hdl_mg_dl` | measurement_value | |
| `ldl_mg_dl` | measurement_value | |
| `triglycerides_mg_dl` | measurement_value | |
| `alt_u_l` | measurement_value | |
| `ast_u_l` | measurement_value | |
| `tsh_miu_l` | measurement_value | |
| `vitamin_d_ng_ml` | measurement_value | |
| `ferritin_ng_ml` | measurement_value | |
| `crp_mg_l` | measurement_value | |
| `hemoglobin_g_dl` | measurement_value | |
| `testosterone_ng_dl` | measurement_value | sex-specific values |

### `03_visits.csv` — **grain: (patient_id, visit_date, timepoint)** (longitudinal)
| Column | Role | Notes |
|---|---|---|
| `visit_id` | entity_id | VIS-001 to VIS-060 |
| `patient_id` | foreign_key | → patients.patient_id |
| `visit_date` | timestamp | Same dates as lab_results |
| `timepoint` | coded_value | T0, T1, T2 |
| `site_id` | coded_value | |
| `visit_type` | coded_value | INITIAL, FOLLOW_UP_3M, FOLLOW_UP_6M |
| `admission_datetime` | timestamp | Outpatient start (same day) |
| `discharge_datetime` | timestamp | Outpatient end; triggers DQ_CONS_004 |
| `systolic_bp` | measurement_value | mmHg |
| `diastolic_bp` | measurement_value | mmHg |
| `heart_rate` | measurement_value | bpm |
| `weight_kg` | measurement_value | Visit-day weight (compare to patients) |
| `waist_cm` | measurement_value | cm |
| `vo2_max` | measurement_value | mL/kg/min |

### `04_dexa_scans.csv` — **grain: (patient_id, scan_date, timepoint)** (longitudinal, P001–P015)
| Column | Role | Notes |
|---|---|---|
| `scan_id` | entity_id | DEX-001 to DEX-030 |
| `patient_id` | foreign_key | → patients.patient_id (P001–P015) |
| `scan_date` | timestamp | T0 = enrollment, T2 = +180 days |
| `timepoint` | coded_value | T0, T2 |
| `site_id` | coded_value | |
| `body_fat_pct` | measurement_value | % |
| `lean_mass_kg` | measurement_value | kg |
| `fat_mass_kg` | measurement_value | kg |
| `visceral_fat_g` | measurement_value | g |
| `bmd_whole_body_g_cm2` | measurement_value | g/cm² |
| `lumbar_spine_t_score` | measurement_value | range −4 to +4 |
| `femoral_neck_t_score` | measurement_value | range −4 to +4 |
| `total_hip_t_score` | measurement_value | range −4 to +4 |
| `almi_kg_m2` | measurement_value | kg/m² |

### `05_device_records.csv` — **grain: (patient_id, recorded_month)** (longitudinal)
| Column | Role | Notes |
|---|---|---|
| `record_id` | entity_id | DEV-001 to DEV-080 |
| `patient_id` | foreign_key | → patients.patient_id |
| `recorded_month` | timestamp | First of month (YYYY-MM-01) |
| `site_id` | coded_value | |
| `device_type` | coded_value | WEARABLE, SMARTWATCH, PHONE_APP |
| `daily_steps_avg` | measurement_value | steps/day monthly average |
| `avg_heart_rate_bpm` | measurement_value | bpm |
| `sleep_hours_avg` | measurement_value | hours/night average |
| `active_minutes_avg` | measurement_value | active min/day |
| `screen_time_hours_avg` | measurement_value | hours/day |

### `06_questionnaire_responses.csv` — **grain: (patient_id, response_date, timepoint)** (longitudinal)
| Column | Role | Notes |
|---|---|---|
| `response_id` | entity_id | QST-001 to QST-040 |
| `patient_id` | foreign_key | → patients.patient_id |
| `response_date` | timestamp | T0 = enrollment, T1 = +90 days |
| `timepoint` | coded_value | T0, T1 |
| `site_id` | coded_value | |
| `questionnaire_id` | coded_value | ONBOARDING_L1, FOLLOW_UP_L1 |
| `stress_level_0_10` | measurement_value | 0–10 integer |
| `energy_level` | coded_value | valid: LOW, MODERATE, HIGH |
| `sleep_quality` | coded_value | valid: POOR, FAIR, GOOD, EXCELLENT |
| `motivation_scale_1_10` | measurement_value | 1–10 integer |
| `activity_level` | coded_value | valid: SEDENTARY, LIGHT, MODERATE, VIGOROUS, VERY_ACTIVE |
| `diet_type` | coded_value | valid: OMNIVORE, PESCATARIAN, VEGETARIAN, VEGAN, KETO, MEDITERRANEAN, PALEO |
| `general_wellbeing_1_10` | measurement_value | 1–10 integer |

---

## Cross-table relationships (FK map)

```
patients.patient_id
  ← lab_results.patient_id
  ← visits.patient_id
  ← dexa_scans.patient_id
  ← device_records.patient_id
  ← questionnaire_responses.patient_id
```

Shared concept across tables (triggers DQ_CONS_009):
- `weight_kg` appears in both `patients` (baseline) and `visits` (visit-day)

Temporal anchor for cross-table coherence (triggers DQ_CONS_008):
- `patients.enrollment_date` is the earliest valid date for any event in all other tables
- `patients.death_date` is the latest valid date for events (triggers DQ_CONS_005)

---

## Injected DQ errors — degraded version

Each error is tagged with its target check ID from `dq_checks.csv`.

### `01_patients.csv`
| Row | Change from clean | Check ID | Description |
|---|---|---|---|
| P018 | sex: F→M, birth_date: 1995-09-08→1980-06-28 | DQ_CONS_006 | Near-duplicate of P017 (M, 1980-06-25, SITE_B, similar anthropometrics) |

### `02_lab_results.csv`
| Row | Column | Change | Check ID | Description |
|---|---|---|---|---|
| LAB-020 (P007-T1) | `glucose_mg_dl` | 84 → "pending" | DQ_TYPE_001 | Non-numeric text in numeric column |
| LAB-025 (P009-T0) | `visit_date` | 2024-02-08 → "02/08/2024" | DQ_TYPE_002 | US date format mixed into ISO column |
| LAB-025 (P009-T0) | `creatinine_mg_dl` | 1.38 → 121.9 | DQ_UNIT_003 | Value is in µmol/L (121.9 ≈ 1.38×88.4) but `creatinine_unit` still says "mg/dL" |
| LAB-015 (P005-T2) | `hba1c_pct` | 6.2 → 85.3 | DQ_RANGE_001 (hard) | HbA1c >18% is physiologically impossible |
| LAB-035 (P012-T1) | `creatinine_mg_dl` | 0.73 → -0.5 | DQ_RANGE_001 (hard) | Negative creatinine is physiologically impossible |
| LAB-057 (P019-T2) | `alt_u_l` | 65 → 2847 | DQ_RANGE_002 | Extreme statistical outlier (~40× above normal ceiling) |
| LAB-031 (P011-T0) | `vitamin_d_ng_ml` | 20 → -99 | DQ_MISS_002 | Sentinel value for missing |
| LAB-033 (P011-T2) | `vitamin_d_ng_ml` | 30 → 999 | DQ_MISS_002 | Sentinel value for missing |
| LAB-031–033, 040–042, 046–051, 055–057 | `vitamin_d_ng_ml` | various → blank | DQ_MISS_001 / DQ_MISS_005 / DQ_MISS_006 | 25% missing rate; 100% of blanks in SITE_B; rate increases T0→T1→T2 |
| LAB-{all females}+LAB-007-009+LAB-013-015 | `testosterone_ng_dl` | values → blank | DQ_MISS_003 | 60% missing (>50% threshold) — requires HITL handling policy |
| LAB-033 (P011-T2) | `ferritin_ng_ml`, `crp_mg_l` | values → blank | DQ_MISS_004 | Co-missing pair (same rows across P011/P014/P016 at T2) |
| LAB-042 (P014-T2) | `ferritin_ng_ml`, `crp_mg_l` | values → blank | DQ_MISS_004 | Co-missing pair |
| LAB-048 (P016-T2) | `ferritin_ng_ml`, `crp_mg_l` | values → blank | DQ_MISS_004 | Co-missing pair |
| LAB-061 | entire row | duplicate of LAB-014 (P005-T1), different result_id | DQ_CONS_002 | Grain key violation: same (patient_id, visit_date, timepoint) |
| LAB-034 (P012-T0) | `visit_date` | 2024-02-16 → 2024-08-14 | DQ_CONS_003 | P012 rows now out of chronological order (T0 date > T2 date) |
| LAB-036 (P012-T2) | `visit_date` | 2024-08-14 → 2024-02-16 | DQ_CONS_003 | Paired with above — T0 and T2 dates swapped |
| LAB-062 | entire row | patient_id = "P025" (does not exist) | DQ_CONS_007 | Orphan foreign key — P025 not in patients table |
| LAB-026 (P009-T1) | `creatinine_mg_dl` | 1.35 → 8.92 | DQ_COH_002 | Impossible trajectory spike (T0=1.38, T1=8.92, T2=1.30) |

### `03_visits.csv`
| Row | Column | Change | Check ID | Description |
|---|---|---|---|---|
| VIS-030 (P010-T2) | `visit_date` | 2024-08-08 → "08/08/2024" | DQ_TYPE_002 | US date format in ISO column |
| VIS-023 (P008-T1) | `admission_datetime`, `discharge_datetime` | swapped (discharge 08:00, admission 10:30) | DQ_CONS_004 | Discharge before admission |
| VIS-009 (P003-T2) | `visit_date` | 2024-07-13 → 2024-07-25 | DQ_CONS_005 | Visit 5 days after P003's death (2024-07-20) |
| VIS-012 (P004-T2) | `weight_kg` | 57.8 → 47.2 | DQ_CONS_009 | 11.5 kg discrepancy from baseline (58.7 kg) in patients table |
| VIS-043–045 (P015) | entire rows | removed | DQ_MISS_007 | P015 present in lab_results, dexa_scans, device_records but absent in visits |
| VIS-039 (P013-T2) | `systolic_bp`, `diastolic_bp` | 108/68 → 85/92 | DQ_COH_001 | Diastolic pressure exceeds systolic — clinical impossibility |

### `04_dexa_scans.csv`
| Row | Column | Change | Check ID | Description |
|---|---|---|---|---|
| DEX-015 (P008-T0) | `lumbar_spine_t_score` | -0.6 → +8.5 | DQ_RANGE_001 (hard) | T-score physiologically impossible (max ≈ +4) |
| DEX-002 (P001-T2) | `body_fat_pct` | 22.8 → 7.2 | DQ_COH_002 | Trajectory: 24.5% → 7.2% in 6 months — implausible 17-point drop |
| DEX-019 (P010-T0) | `scan_date` | 2024-02-10 → 2024-01-20 | DQ_CONS_008 | Scan 21 days before P010's enrollment date (2024-02-10) |

### `05_device_records.csv`
| Row | Column | Change | Check ID | Description |
|---|---|---|---|---|
| DEV-041 (P011-M1) | `daily_steps_avg` | 5100 → -1 | DQ_MISS_002 | Sentinel value for missing/error |
| DEV-073 (P019-M1) | `avg_heart_rate_bpm` | 77 → 9999 | DQ_MISS_002 | Sentinel value for missing/error |
| DEV-072 (P018-M4) | `sleep_hours_avg` | 8.0 → "not recorded" | DQ_TYPE_001 | Non-numeric text in numeric column |

### `06_questionnaire_responses.csv`
| Row | Column | Change | Check ID | Description |
|---|---|---|---|---|
| QST-011 (P006-T0) | `activity_level` | LIGHT → "EXTREME" | DQ_CONS_001 | Not in declared valid set {SEDENTARY, LIGHT, MODERATE, VIGOROUS, VERY_ACTIVE} |
| QST-025 (P013-T0) | `diet_type` | OMNIVORE → "ATKINS" | DQ_CONS_001 | Not in declared valid set |
| QST-034 (P017-T1) | `energy_level` | MODERATE → "VERY_HIGH" | DQ_CONS_001 | Not in declared valid set {LOW, MODERATE, HIGH} |

---

## DQ check coverage matrix

| Check ID | Category | Triggered in degraded? | Table(s) |
|---|---|---|---|
| DQ_TYPE_001 | type | ✓ | lab_results (LAB-020), device_records (DEV-072) |
| DQ_TYPE_002 | type | ✓ | lab_results (LAB-025), visits (VIS-030) |
| DQ_UNIT_003 | unit | ✓ | lab_results (LAB-025 creatinine µmol/L in mg/dL column) |
| DQ_RANGE_001 | range | ✓ (hard ×3) | lab_results (HbA1c=85.3, creatinine=-0.5), dexa_scans (T-score=+8.5) |
| DQ_RANGE_002 | range | ✓ (soft) | lab_results (ALT=2847) |
| DQ_MISS_001 | missing | ✓ | lab_results (vitamin_d_ng_ml 25% missing) |
| DQ_MISS_002 | missing | ✓ | lab_results (-99, 999), device_records (-1, 9999) |
| DQ_MISS_003 | missing | ✓ | lab_results (testosterone_ng_dl 60% missing) |
| DQ_MISS_004 | missing | ✓ | lab_results (ferritin + crp always co-missing at T2 for P011/P014/P016) |
| DQ_MISS_005 | missing | ✓ | lab_results (vitamin_d 100% of blanks in SITE_B) |
| DQ_MISS_006 | missing | ✓ | lab_results (vitamin_d missing rate: T0<T1<T2) |
| DQ_MISS_007 | missing | ✓ | P015 absent in visits, present in lab_results / dexa / device |
| DQ_COH_001 | coherence | ✓ | visits (P013-T2: diastolic > systolic) |
| DQ_COH_002 | coherence | ✓ | lab_results (P009 creatinine spike), dexa_scans (P001 body_fat drop) |
| DQ_CONS_001 | consistency | ✓ | questionnaire (3 invalid coded values) |
| DQ_CONS_002 | consistency | ✓ | lab_results (P005-T1 duplicate row) |
| DQ_CONS_003 | consistency | ✓ | lab_results (P012 dates out of order) |
| DQ_CONS_004 | consistency | ✓ (hard) | visits (P008-T1 discharge before admission) |
| DQ_CONS_005 | consistency | ✓ (hard) | visits (P003-T2 visit after death) |
| DQ_CONS_006 | consistency | ✓ (soft) | patients (P017≈P018: same sex, 3-day birth_date gap, same site) |
| DQ_CONS_007 | consistency | ✓ (hard) | lab_results (P025 orphan FK) |
| DQ_CONS_008 | consistency | ✓ (hard) | dexa_scans (P010 scan before enrollment) |
| DQ_CONS_009 | consistency | ✓ (soft) | visits vs patients (P004 weight: 47.2 vs 58.7 kg) |

Checks not triggered (require ontology relation setup or file-level events):  
DQ_FILE_*, DQ_TYPE_003, DQ_UNIT_001, DQ_UNIT_002, DQ_MEAN_*, DQ_MISS_* (grain-based)

---

## Notes on the clean version

The clean version has no injected errors. It does contain naturally occurring clinical variation that the DQ engine should **not** flag:
- P003 deteriorating trajectory (declining health before death) — valid longitudinal signal
- P006 low ferritin and vitamin D (genuine deficiencies)
- P005 elevated HbA1c (diabetic range, but within plausible bounds)
- P008 elevated TSH (thyroid disorder, plausible)
- P003 `death_date` present — T2 visit is intentionally 7 days before death
- Some columns (testosterone) have low values for elderly patients — within range
