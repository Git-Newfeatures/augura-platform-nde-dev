#!/usr/bin/env python3
"""
inject_errors.py
Reads the 11 clean CSVs and produces degraded versions with 31 injected
data quality problems. Each error is naturalistic — not engineered around
any check-ID taxonomy — so the DQ engine must earn every finding independently.

Writes:
  ./degraded/   — 11 modified CSV files
  ./ground_truth/errors_catalog.json — machine-readable error manifest
"""

import csv
import copy
import json
from pathlib import Path

CLEAN    = Path(__file__).parent / "clean"
DEGRADED = Path(__file__).parent / "degraded"
GT_DIR   = Path(__file__).parent / "ground_truth"

DEGRADED.mkdir(exist_ok=True)
GT_DIR.mkdir(exist_ok=True)


# ─── helpers ─────────────────────────────────────────────────────────────────

def read_csv(name):
    with open(CLEAN / name, encoding="utf-8") as f:
        return list(csv.DictReader(f))

def write_csv(name, rows):
    if not rows:
        return
    with open(DEGRADED / name, "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        wr.writeheader()
        wr.writerows(rows)

def find_row(rows, **criteria):
    for r in rows:
        if all(r.get(k) == str(v) for k, v in criteria.items()):
            return r
    return None

def idx(rows, **criteria):
    for i, r in enumerate(rows):
        if all(r.get(k) == str(v) for k, v in criteria.items()):
            return i
    return -1


# ─── error catalog accumulator ───────────────────────────────────────────────

ERRORS = []   # list of error dicts for ground_truth.json

def log(eid, table, affected_ids, columns, observable, severity, category, expected_behavior, notes=""):
    ERRORS.append({
        "id": eid,
        "table": table,
        "affected_row_ids": affected_ids,
        "columns_involved": columns,
        "observable_problem": observable,
        "severity": severity,      # "hard" | "soft" | "info"
        "category": category,
        "expected_behavior": expected_behavior,
        "notes": notes,
    })


# ═════════════════════════════════════════════════════════════════════════════
# TABLE 1: 01_patients.csv
# ═════════════════════════════════════════════════════════════════════════════

patients = read_csv("01_patients.csv")

# E01 — Near-duplicate: change P013 to look nearly identical to P009
# P009: female, 1991-07-14, 162 cm, 57.5 kg, SITE_B
# P013 (clean): female, 1988-06-22, 166 cm, 65.8 kg, SITE_B
# Degraded P013: birth_date 1991-06-19, height 162.0, weight 57.8
r = find_row(patients, patient_id="P013")
r["birth_date"]  = "1991-06-19"
r["height_cm"]   = "162.0"
r["weight_kg"]   = "57.8"
log("E01", "01_patients.csv",
    ["P013"],
    ["birth_date", "height_cm", "weight_kg"],
    "P013 (female, 1991-06-19, 162 cm, 57.8 kg, SITE_B) shares nearly identical demographics with P009 "
    "(female, 1991-07-14, 162 cm, 57.5 kg, SITE_B): same sex, site and height; dates of birth 25 days apart; "
    "weight within 0.3 kg. Pattern consistent with a merged-record near-duplicate.",
    "soft",
    "near_duplicate_entity",
    "Each row in the patients table should represent a unique individual. "
    "Near-identical demographic combinations within the same site warrant human review "
    "to confirm these are genuinely two separate patients and not a duplicated record.",
    "P009 is the anchor (unchanged); P013 was modified to approach it.")

# E02 — Future enrollment date for P014
r = find_row(patients, patient_id="P014")
r["enrollment_date"] = "2026-03-05"
log("E02", "01_patients.csv",
    ["P014"],
    ["enrollment_date"],
    "enrollment_date of 2026-03-05 is in the future relative to the study period "
    "(all other enrollments are in Jan–Mar 2024) and relative to today's date. "
    "An enrollment event cannot be recorded before it occurs.",
    "hard",
    "impossible_date",
    "enrollment_date must be a past date within the expected study window (2024-01-01 to 2024-12-31).",
    "Clean value was 2024-03-05; degraded value is 2026-03-05.")

write_csv("01_patients.csv", patients)
print(f"✓  01_patients.csv  (E01, E02)")


# ═════════════════════════════════════════════════════════════════════════════
# TABLE 2: 02_biomarker_results.csv
# ═════════════════════════════════════════════════════════════════════════════

bio = read_csv("02_biomarker_results.csv")

# E03 — Non-numeric value in numeric field: BIO-001 (P001-T0) glucose_value → "fasting"
i = idx(bio, result_id="BIO-001")
bio[i]["glucose_value"] = "fasting"
log("E03", "02_biomarker_results.csv",
    ["BIO-001"],
    ["glucose_value"],
    "glucose_value contains the string 'fasting' instead of a numeric measurement. "
    "The field is declared as a numeric measurement column.",
    "hard",
    "unparseable_value",
    "glucose_value should contain a numeric fasting plasma glucose in the declared unit (mmol/L for SITE_A). "
    "Expected range approximately 3.5–15 mmol/L for this cohort.")

# E04 — Cross-table coherence: BIO-009 (P003-T2) tsh_miu_l → 0.02
# P003 is a hypothyroid patient on levothyroxine 100 mcg; TSH 0.02 indicates severe hyperthyroidism —
# contradicts both the health_profile (HYPOTHYROIDISM) and the medication record (levothyroxine).
i = idx(bio, result_id="BIO-009")
bio[i]["tsh_miu_l"] = "0.02"
log("E04", "02_biomarker_results.csv",
    ["BIO-009"],
    ["tsh_miu_l"],
    "P003's T2 TSH value is 0.02 mIU/L (severe hyperthyroidism suppression), yet the "
    "04_health_profile table records HYPOTHYROIDISM as a chronic condition and the "
    "09_medications table records levothyroxine 100 mcg (a hypothyroid treatment). "
    "A levothyroxine-treated patient with TSH 0.02 is clinically contradictory across three tables.",
    "soft",
    "cross_table_clinical_incoherence",
    "TSH should remain in the low-normal to sub-therapeutic range for a patient on stable "
    "levothyroxine therapy for hypothyroidism (expected T2 range ~1.0–3.5 mIU/L). "
    "If the dose was over-replaced, TSH < 0.1 would require clinical explanation consistent "
    "with the other tables.",
    "Affects rows in 02_biomarker_results, 04_health_profile, and 09_medications.")

# E05 — Creatinine spike-then-return: BIO-011 (P004-T1) creatinine_value → 8.9
# P004 trajectory: T0=2.1, T1=8.9, T2=2.5 mg/dL — spike then return
i = idx(bio, result_id="BIO-011")
bio[i]["creatinine_value"] = "8.9"
log("E05", "02_biomarker_results.csv",
    ["BIO-011"],
    ["creatinine_value"],
    "P004 creatinine_value trajectory is 2.1 → 8.9 → 2.5 mg/dL across T0/T1/T2 — a 4.2× spike "
    "at T1 followed by near-complete normalisation 90 days later. A serum creatinine increase "
    "of this magnitude followed by spontaneous return to near-baseline within one 90-day period "
    "is physiologically implausible without acute-on-chronic kidney injury with subsequent full recovery, "
    "which would typically appear in clinical notes and change the CKD staging.",
    "soft",
    "implausible_longitudinal_trajectory",
    "Expected creatinine trajectory for a CKD stage 3 patient is slow monotonic progression "
    "(T0=2.1, T1≈2.3, T2≈2.5 mg/dL as in the clean version). A single-timepoint spike of "
    "this magnitude without corresponding clinical context should be flagged for review.",
    "Pair with E06 (same row) — eGFR value is also inconsistent with this creatinine.")

# E06 — Formula contradiction: BIO-011 (P004-T1) egfr_ml_min → 91 (impossible with creatinine 8.9)
i = idx(bio, result_id="BIO-011")
bio[i]["egfr_ml_min"] = "91"
log("E06", "02_biomarker_results.csv",
    ["BIO-011"],
    ["egfr_ml_min", "creatinine_value"],
    "BIO-011 (P004-T1) has creatinine_value=8.9 mg/dL and egfr_ml_min=91 on the same row. "
    "By the CKD-EPI formula, a 67-year-old male with creatinine 8.9 mg/dL would have an eGFR "
    "of approximately 5 mL/min/1.73 m², not 91. These two values cannot both be correct simultaneously.",
    "hard",
    "cross_column_formula_contradiction",
    "egfr_ml_min must be consistent with creatinine_value, patient age, and sex. "
    "At creatinine 8.9 mg/dL for a 67-year-old male, eGFR ≈ 5 mL/min/1.73 m² (CKD-EPI).",
    "Pair with E05 (same row). Both values point to the same underlying data error.")

# E07 — Impossible hard range: BIO-014 (P005-T1) hba1c_pct → 97.4
i = idx(bio, result_id="BIO-014")
bio[i]["hba1c_pct"] = "97.4"
log("E07", "02_biomarker_results.csv",
    ["BIO-014"],
    ["hba1c_pct"],
    "hba1c_pct value of 97.4 is physiologically impossible. HbA1c is reported as a percentage "
    "of total haemoglobin; the biological maximum is 100% but clinical values range 4–20% in "
    "the most extreme cases of uncontrolled diabetes. A value of 97.4 is impossible.",
    "hard",
    "impossible_value_hard_range",
    "hba1c_pct must be in the range 4.0–20.0%. "
    "For a previously iron-deficient 29-year-old female with no diabetes, expected range is 4.5–5.5%.")

# E08 — Unit scale mismatch: BIO-028 (P010-T0, SITE_B) creatinine_value → 1.1,
# creatinine_unit stays µmol/L  (1.1 µmol/L is impossible; 1.1 mg/dL ≈ 97 µmol/L is normal)
i = idx(bio, result_id="BIO-028")
bio[i]["creatinine_value"] = "1.1"
log("E08", "02_biomarker_results.csv",
    ["BIO-028"],
    ["creatinine_value", "creatinine_unit"],
    "BIO-028 (P010-T0, SITE_B) has creatinine_value=1.1 with creatinine_unit='µmol/L'. "
    "A serum creatinine of 1.1 µmol/L is physiologically impossible (normal male range 62–115 µmol/L). "
    "The value 1.1 corresponds to 1.1 mg/dL, which is normal, suggesting the mg/dL-scale value "
    "was entered in a column whose unit convention for SITE_B is µmol/L.",
    "hard",
    "unit_scale_mismatch",
    "SITE_B creatinine values should be in µmol/L (normal male range 62–115 µmol/L). "
    "The correct value for P010 at T0 would be approximately 95 µmol/L.",
    "All other SITE_B creatinine values are in the 60–135 µmol/L range, confirming the convention.")

# E09 — Sentinel value: BIO-029 (P010-T1) cortisol_nmol_l → -99
i = idx(bio, result_id="BIO-029")
bio[i]["cortisol_nmol_l"] = "-99"
log("E09", "02_biomarker_results.csv",
    ["BIO-029"],
    ["cortisol_nmol_l"],
    "cortisol_nmol_l value of -99 is negative and physiologically impossible. "
    "The pattern -99 (or 999, -1) is a widely-used sentinel code for 'test failed', "
    "'not recorded', or 'outside measurable range'. It should not be treated as a "
    "numeric cortisol measurement.",
    "hard",
    "sentinel_in_numeric_field",
    "cortisol_nmol_l should contain a positive numeric value (morning range: 100–700 nmol/L). "
    "A value of -99 must be treated as missing/failed and not as a low cortisol result.")

# E10 — Statistical outlier: BIO-027 (P009-T2) ldl_mmol_l → 14.7
i = idx(bio, result_id="BIO-027")
bio[i]["ldl_mmol_l"] = "14.7"
log("E10", "02_biomarker_results.csv",
    ["BIO-027"],
    ["ldl_mmol_l"],
    "ldl_mmol_l value of 14.7 mmol/L for P009-T2 is a statistical extreme outlier. "
    "All other ldl_mmol_l values in the dataset range from 2.0 to 5.2 mmol/L. "
    "14.7 mmol/L is ~6 standard deviations above the column mean and would represent "
    "severe familial hypercholesterolaemia — inconsistent with P009's otherwise healthy profile "
    "(T0 LDL 2.2 mmol/L, no relevant diagnoses or medications).",
    "soft",
    "statistical_outlier",
    "Expected P009 LDL at T2 is approximately 2.1–2.3 mmol/L based on trajectory. "
    "A value above 8.0 mmol/L should trigger review; 14.7 mmol/L suggests transcription error.")

# E11 — Site-concentrated missingness: all SITE_B vit_b12_pmol_l → blank
site_b_pids = {"P009","P010","P011","P012","P013","P014","P015"}
affected_b12 = []
for row in bio:
    if row["patient_id"] in site_b_pids:
        row["vit_b12_pmol_l"] = ""
        affected_b12.append(row["result_id"])
log("E11", "02_biomarker_results.csv",
    affected_b12,
    ["vit_b12_pmol_l"],
    f"vit_b12_pmol_l is blank for all {len(affected_b12)} SITE_B rows (P009–P015) "
    "and fully populated for all 24 SITE_A rows. Missing rate: 45% overall, 100% at SITE_B, "
    "0% at SITE_A. This concentration pattern is inconsistent with random sample failure — "
    "it suggests a site-level instrumentation gap or a protocol difference not documented in the schema.",
    "soft",
    "site_concentrated_missingness",
    "vit_b12_pmol_l should be measured for all patients regardless of site. "
    "If SITE_B does not routinely measure B12, the schema should document this and the "
    "missing values should be coded as 'NOT_APPLICABLE' rather than blank.",
    "Affects 20 rows: 7 patients × 3 timepoints minus P011 T2 (2 timepoints only).")

# E12 — Co-missing iron panel: ferritin, serum_iron, transferrin blank at T2 for P006, P012, P014
co_missing_rows = ["BIO-018", "BIO-035", "BIO-041"]
for rid in co_missing_rows:
    i = idx(bio, result_id=rid)
    bio[i]["ferritin_ng_ml"] = ""
    bio[i]["serum_iron_umol_l"] = ""
    bio[i]["transferrin_g_l"] = ""
log("E12", "02_biomarker_results.csv",
    co_missing_rows,
    ["ferritin_ng_ml", "serum_iron_umol_l", "transferrin_g_l"],
    "ferritin_ng_ml, serum_iron_umol_l, and transferrin_g_l are simultaneously blank for "
    "P006, P012, and P014 at T2 (BIO-018, BIO-035, BIO-041). These three columns form a "
    "clinical iron-status panel; their joint absence in exactly three rows at the same "
    "timepoint (T2) points to a skipped panel order rather than random measurement failure. "
    "Co-missingness correlation for these three columns is 1.0.",
    "soft",
    "co_missing_ordered_panel",
    "All three iron-panel columns should be populated at every timepoint. "
    "If the panel was deliberately not ordered at T2 for these patients, "
    "the reason should be documented in the visit notes.",
    "Patients P006 (liver disease), P012 (hypogonadism), P014 (elderly multi-morbid) "
    "all have clinical indications for iron monitoring.")

# E13 — Orphan foreign key: add BIO-045 with non-existent patient_id = "P099"
orphan_row = copy.copy(bio[0])   # template
for k in orphan_row:
    orphan_row[k] = ""
orphan_row.update({
    "result_id": "BIO-045",
    "patient_id": "P099",
    "timepoint": "T0",
    "sample_date": "2024-03-20",
    "site_id": "SITE_B",
    "glucose_value": "5.5",
    "glucose_unit": "mg/dL",
    "hba1c_pct": "5.3",
    "creatinine_value": "72",
    "creatinine_unit": "µmol/L",
    "egfr_ml_min": "94",
})
bio.append(orphan_row)
log("E13", "02_biomarker_results.csv",
    ["BIO-045"],
    ["patient_id"],
    "BIO-045 references patient_id 'P099', which does not exist in the 01_patients.csv table. "
    "This is an orphan foreign key — a biomarker record that cannot be linked to any known patient.",
    "hard",
    "orphan_foreign_key",
    "Every result_id in biomarker_results must have a patient_id that exists in patients. "
    "'P099' does not exist in the patients table and the row cannot be attributed to any patient.")

# E14 — Grain duplicate: add BIO-046 as a second T1 record for P007
original = find_row(bio, result_id="BIO-020")  # P007-T1
dup_row = copy.copy(original)
dup_row["result_id"] = "BIO-046"
dup_row["ldl_mmol_l"] = "3.3"      # slightly different values
dup_row["crp_mg_l"] = "2.8"
dup_row["glucose_value"] = "5.7"
bio.append(dup_row)
log("E14", "02_biomarker_results.csv",
    ["BIO-020", "BIO-046"],
    ["result_id", "patient_id", "timepoint"],
    "Two rows share the same patient_id (P007) and timepoint (T1): BIO-020 and BIO-046. "
    "The declared grain of this table is one row per patient per timepoint. "
    "The two rows have slightly different values for ldl_mmol_l, crp_mg_l, and glucose_value, "
    "suggesting either duplicate data entry or two samples labelled as the same timepoint.",
    "hard",
    "grain_duplicate",
    "The (patient_id, timepoint) combination must be unique in this table. "
    "One of these rows must be removed or the timepoint label corrected.")

write_csv("02_biomarker_results.csv", bio)
print(f"✓  02_biomarker_results.csv  (E03–E14, {len(bio)} rows)")


# ═════════════════════════════════════════════════════════════════════════════
# TABLE 3: 03_dexa_results.csv
# ═════════════════════════════════════════════════════════════════════════════

dexa = read_csv("03_dexa_results.csv")

# E15 — Impossible body fat trajectory: DEX-002 (P001-T2) body_fat_pct → 11.8
i = idx(dexa, scan_id="DEX-002")
dexa[i]["body_fat_pct"] = "11.8"
log("E15", "03_dexa_results.csv",
    ["DEX-002"],
    ["body_fat_pct"],
    "P001's body_fat_pct drops from 38.5% at T0 to 11.8% at T2 — a reduction of 26.7 "
    "percentage points in 6 months. Through diet and exercise intervention, 3–5% body fat "
    "reduction per 6-month period is the physiological maximum. A 26.7-point drop would require "
    "extreme medical intervention and would not occur without corresponding dramatic weight loss.",
    "soft",
    "implausible_longitudinal_trajectory",
    "P001's weight at T2 visit is approximately 78.4 kg (from clinical_visits), implying "
    "total fat mass would be ~9.3 kg at 11.8% — inconsistent with a 162 cm woman weighing 78 kg. "
    "Expected body_fat_pct at T2 ≈ 36.5% based on clean trajectory.",
    "Clean DEX-002 value was approximately 36.6%; modified to 11.8%.")

# E16 — Impossible T-score: DEX-014 (P007-T2) lumbar_spine_t_score → +8.2
i = idx(dexa, scan_id="DEX-014")
dexa[i]["lumbar_spine_t_score"] = "8.2"
log("E16", "03_dexa_results.csv",
    ["DEX-014"],
    ["lumbar_spine_t_score"],
    "lumbar_spine_t_score of +8.2 is outside the clinically defined range for T-scores. "
    "DEXA T-scores represent standard deviations from the mean bone density of a young reference "
    "population; the practical clinical range is approximately -4.0 to +3.0. "
    "A T-score of +8.2 is physiologically impossible and indicates a data entry or instrument error.",
    "hard",
    "impossible_value_hard_range",
    "lumbar_spine_t_score must be in the range -4.0 to +3.0. "
    "P007's T0 lumbar T-score was -2.6 (osteoporosis range); T2 expected ≈ -2.4 "
    "after vitamin D supplementation and alendronic acid treatment.")

write_csv("03_dexa_results.csv", dexa)
print(f"✓  03_dexa_results.csv  (E15, E16)")


# ═════════════════════════════════════════════════════════════════════════════
# TABLE 4: 04_health_profile.csv  (no errors)
# ═════════════════════════════════════════════════════════════════════════════

hp = read_csv("04_health_profile.csv")
write_csv("04_health_profile.csv", hp)
print(f"  04_health_profile.csv  (clean copy)")


# ═════════════════════════════════════════════════════════════════════════════
# TABLE 5: 05_questionnaire_followup.csv
# ═════════════════════════════════════════════════════════════════════════════

qfu = read_csv("05_questionnaire_followup.csv")

# E17 — Invalid coded value: QFU-017 (P009-T0) phq9_category → "MODERATE-SEVERE"
i = idx(qfu, response_id="QFU-017")
qfu[i]["phq9_category"] = "MODERATE-SEVERE"
log("E17", "05_questionnaire_followup.csv",
    ["QFU-017"],
    ["phq9_category"],
    "phq9_category value 'MODERATE-SEVERE' is not a member of the allowed value set "
    "{NONE, MILD, MODERATE, SEVERE}. The PHQ-9 standard scoring produces four severity "
    "categories with no compound category 'MODERATE-SEVERE'. This value was likely entered "
    "by a clinician who used a non-standard label.",
    "soft",
    "invalid_coded_value",
    "phq9_category must be one of: NONE (0–4), MILD (5–9), MODERATE (10–14), SEVERE (15–27). "
    "P009's PHQ-9 total of 2 maps to 'NONE'.")

# E18 — Missing longitudinal row: remove QFU-030 (P015-T1)
qfu = [r for r in qfu if r["response_id"] != "QFU-030"]
log("E18", "05_questionnaire_followup.csv",
    ["QFU-030"],
    ["response_id"],
    "P015 has a T0 questionnaire response but no T1 response. P015 is alive and has "
    "biomarker results and clinical visits at T1, making the absence of a T1 questionnaire "
    "an unexplained longitudinal gap rather than a protocol-expected missing record.",
    "soft",
    "missing_longitudinal_record",
    "A T1 questionnaire response (expected ~2024-06-08) should exist for P015. "
    "Its absence creates a gap in the patient's reported wellbeing trajectory at the "
    "most clinically meaningful timepoint (6 months into mental health treatment).",
    "QFU-029 (P015-T0) exists; QFU-030 (P015-T1) was removed.")

write_csv("05_questionnaire_followup.csv", qfu)
print(f"✓  05_questionnaire_followup.csv  (E17, E18, {len(qfu)} rows)")


# ═════════════════════════════════════════════════════════════════════════════
# TABLE 6: 06_wearable_aggregates.csv
# ═════════════════════════════════════════════════════════════════════════════

war = read_csv("06_wearable_aggregates.csv")

# E19 — Negative impossible value: WAR-008 (P002-M4) daily_steps_avg → -5
i = idx(war, record_id="WAR-008")
war[i]["daily_steps_avg"] = "-5"
log("E19", "06_wearable_aggregates.csv",
    ["WAR-008"],
    ["daily_steps_avg"],
    "daily_steps_avg value of -5 is negative and physically impossible. "
    "Step counts are non-negative integers by definition. "
    "The value -5 likely represents a sentinel used to indicate a device sync failure "
    "or data unavailability.",
    "hard",
    "sentinel_in_numeric_field",
    "daily_steps_avg must be a non-negative integer. "
    "P002's other monthly step averages are 12,500–13,000, making -5 a clear anomaly.")

# E20 — String in numeric field: WAR-043 (P011-M3) sleep_hours_avg → "not synced"
i = idx(war, record_id="WAR-043")
war[i]["sleep_hours_avg"] = "not synced"
log("E20", "06_wearable_aggregates.csv",
    ["WAR-043"],
    ["sleep_hours_avg"],
    "sleep_hours_avg contains the string 'not synced' instead of a numeric value. "
    "The field is a numeric measurement column. 'not synced' appears to be a device "
    "status message that was written directly into the data field instead of being "
    "recorded as missing.",
    "hard",
    "unparseable_value",
    "sleep_hours_avg should contain a numeric value (expected range 4.0–10.0 hours). "
    "Device status messages must not appear in measurement columns; "
    "the cell should be blank or coded as a specific missing-data sentinel.")

# E21 — Sentinel value: WAR-055 (P014-M3) resting_hr_bpm → 9999
i = idx(war, record_id="WAR-055")
war[i]["resting_hr_bpm"] = "9999"
log("E21", "06_wearable_aggregates.csv",
    ["WAR-055"],
    ["resting_hr_bpm"],
    "resting_hr_bpm value of 9999 is a clear sentinel. Physiologically normal resting heart "
    "rate range is 40–110 bpm; 9999 is impossible and is a common placeholder used by "
    "device firmware or data pipelines to indicate 'no reading available'.",
    "hard",
    "sentinel_in_numeric_field",
    "resting_hr_bpm must be a positive integer in the range 40–150 bpm. "
    "P014's other monthly readings are 79–81 bpm; 9999 must be treated as missing.")

write_csv("06_wearable_aggregates.csv", war)
print(f"✓  06_wearable_aggregates.csv  (E19, E20, E21)")


# ═════════════════════════════════════════════════════════════════════════════
# TABLE 7: 07_clinical_visits.csv
# ═════════════════════════════════════════════════════════════════════════════

vis = read_csv("07_clinical_visits.csv")

# E22 — Wrong date format: VIS-023 (P008-T1) visit_date → "08/05/2024"
i = idx(vis, visit_id="VIS-023")
vis[i]["visit_date"] = "08/05/2024"
log("E22", "07_clinical_visits.csv",
    ["VIS-023"],
    ["visit_date"],
    "visit_date for VIS-023 is '08/05/2024' (DD/MM/YYYY or MM/DD/YYYY format) "
    "rather than the ISO 8601 format YYYY-MM-DD used by all other rows in this table. "
    "It is ambiguous whether this means May 8 or August 5, 2024.",
    "soft",
    "non_standard_date_format",
    "All visit_date values must use YYYY-MM-DD format (ISO 8601). "
    "Expected value: 2024-05-05 (P008-T1, 90 days after enrollment 2024-02-05).")

# E23 — Discharge before admission: VIS-029 (P010-T1)
i = idx(vis, visit_id="VIS-029")
vis[i]["admission_datetime"] = "2024-05-14 14:30"
vis[i]["discharge_datetime"] = "2024-05-14 11:00"
log("E23", "07_clinical_visits.csv",
    ["VIS-029"],
    ["admission_datetime", "discharge_datetime"],
    "VIS-029 (P010-T1) has admission_datetime 14:30 and discharge_datetime 11:00 on the same "
    "date (2024-05-14), making the encounter duration -3.5 hours. "
    "A patient cannot be discharged before they were admitted.",
    "hard",
    "temporal_ordering_violation",
    "discharge_datetime must be strictly greater than admission_datetime. "
    "Expected discharge time: approximately 11:44 (same-day outpatient visit of ~90 minutes).")

# E24 — Reversed timepoint dates: P007 T1 ↔ T2 visit_dates swapped
i1 = idx(vis, visit_id="VIS-020")   # P007-T1
i2 = idx(vis, visit_id="VIS-021")   # P007-T2
vis[i1]["visit_date"] = "2024-08-01"
vis[i1]["admission_datetime"] = "2024-08-01 09:00"
vis[i1]["discharge_datetime"] = "2024-08-01 11:30"
vis[i2]["visit_date"] = "2024-05-01"
vis[i2]["admission_datetime"] = "2024-05-01 09:00"
vis[i2]["discharge_datetime"] = "2024-05-01 11:30"
log("E24", "07_clinical_visits.csv",
    ["VIS-020", "VIS-021"],
    ["visit_date", "admission_datetime", "discharge_datetime"],
    "P007's T1 visit_date (2024-08-01) is later than T2 visit_date (2024-05-01). "
    "The T2 timepoint is labelled as occurring 90 days before the T1 timepoint, "
    "violating the expected temporal ordering T0 < T1 < T2.",
    "hard",
    "timepoint_ordering_violation",
    "visit_dates must be monotonically increasing across timepoints: "
    "T0 (2024-02-01) < T1 (expected 2024-05-01) < T2 (expected 2024-08-01). "
    "The dates appear to have been transposed between T1 and T2.")

# E25 — Event after death: add VIS-045 (P011-T2) dated after P011's death (2024-06-02)
extra_vis = copy.copy(vis[-1])
for k in extra_vis:
    extra_vis[k] = ""
extra_vis.update({
    "visit_id": "VIS-045",
    "patient_id": "P011",
    "timepoint": "T2",
    "visit_date": "2024-08-18",
    "admission_datetime": "2024-08-18 09:00",
    "discharge_datetime": "2024-08-18 11:30",
    "site_id": "SITE_B",
    "systolic_bp_mmhg": "152",
    "diastolic_bp_mmhg": "98",
    "weight_kg": "64.2",
    "vo2max_ml_kg_min": "19.8",
    "clinician_id": "CLIN-B01",
    "visit_notes_free_text": "",
})
vis.append(extra_vis)
log("E25", "07_clinical_visits.csv",
    ["VIS-045"],
    ["visit_date", "patient_id"],
    "VIS-045 records a clinical visit for P011 on 2024-08-18, which is 77 days after "
    "P011's recorded death date (2024-06-02 in 01_patients.csv). "
    "A deceased patient cannot have a clinical visit.",
    "hard",
    "event_after_death",
    "No clinical visit or other active event should be recorded for a patient after their "
    "death_date. The 01_patients.csv record for P011 shows death_date=2024-06-02.")

# E26 — Diastolic > systolic: VIS-040 (P014-T1)
i = idx(vis, visit_id="VIS-040")
vis[i]["systolic_bp_mmhg"] = "88"
vis[i]["diastolic_bp_mmhg"] = "96"
log("E26", "07_clinical_visits.csv",
    ["VIS-040"],
    ["systolic_bp_mmhg", "diastolic_bp_mmhg"],
    "VIS-040 (P014-T1) has systolic_bp_mmhg=88 and diastolic_bp_mmhg=96. "
    "Diastolic blood pressure must always be lower than systolic; "
    "a reading of 88/96 mmHg is physiologically impossible.",
    "hard",
    "cross_column_physiological_impossibility",
    "systolic_bp_mmhg must be strictly greater than diastolic_bp_mmhg. "
    "P014 is hypertensive; expected values at T1 ≈ systolic 152, diastolic 93.")

# E27 — Implausible weight drop: VIS-044 (P015-T2) weight_kg → 46.8
i = idx(vis, visit_id="VIS-044")
vis[i]["weight_kg"] = "46.8"
log("E27", "07_clinical_visits.csv",
    ["VIS-044"],
    ["weight_kg"],
    "P015's weight_kg drops from 59.4 kg at T0 to ~58.2 kg at T1 (consistent) "
    "to 46.8 kg at T2 — a loss of 11.4 kg in 3 months. "
    "For a healthy 25-year-old woman with no documented illness, this rate of weight loss "
    "(38 g/day) would require severe malnutrition or undiagnosed serious illness, "
    "neither of which is documented in any other table.",
    "soft",
    "implausible_longitudinal_value",
    "Expected P015 weight at T2 ≈ 58.0 kg based on stable trajectory. "
    "A change of >5% of body weight in one timepoint interval warrants clinical review.")

write_csv("07_clinical_visits.csv", vis)
print(f"✓  07_clinical_visits.csv  (E22–E27, {len(vis)} rows)")


# ═════════════════════════════════════════════════════════════════════════════
# TABLE 8: 08_diagnoses.csv
# ═════════════════════════════════════════════════════════════════════════════

dgn = read_csv("08_diagnoses.csv")

# E28 — ICD-9 format in ICD-10 field: DGN-008 (P006) K76.0 → 571.40
i = idx(dgn, diagnosis_id="DGN-008")
dgn[i]["icd10_code"] = "571.40"
log("E28", "08_diagnoses.csv",
    ["DGN-008"],
    ["icd10_code"],
    "icd10_code '571.40' appears to be in ICD-9-CM format (numeric code 571.40 = "
    "Fatty change of liver, not elsewhere classified) rather than ICD-10-CM format "
    "(K76.0 = Fatty (change of) liver, not elsewhere classified). "
    "The column name explicitly states ICD-10. All other codes in this table use the "
    "ICD-10 letter-prefix format (e.g., K76.0, E11.9, I10).",
    "soft",
    "wrong_coding_vocabulary",
    "icd10_code values must use ICD-10-CM format: one alphabetic character prefix followed "
    "by numeric digits (e.g., K76.0). ICD-9 codes must not appear in this field.")

# E29 — Sex-condition incoherence: DGN-007 (P005-F) → BPH (male-specific condition)
i = idx(dgn, diagnosis_id="DGN-007")
dgn[i]["icd10_code"] = "N40.1"
dgn[i]["diagnosis_name"] = "Benign prostatic hyperplasia with lower urinary tract symptoms"
log("E29", "08_diagnoses.csv",
    ["DGN-007"],
    ["icd10_code", "diagnosis_name"],
    "DGN-007 assigns the diagnosis N40.1 (Benign prostatic hyperplasia with lower urinary "
    "tract symptoms) to patient P005, who is recorded as female in 01_patients.csv. "
    "Benign prostatic hyperplasia is an exclusively male condition (requires a prostate). "
    "This is a cross-table sex-condition incoherence.",
    "hard",
    "sex_condition_incoherence",
    "N40.x (BPH) diagnoses must only be assigned to male patients. "
    "P005 is female (01_patients.csv). The clean diagnosis was D50.9 (Iron deficiency anaemia), "
    "which is consistent with P005's clinical profile and biomarker values.",
    "Affects rows in 08_diagnoses and 01_patients.")

# E30 — Missing diagnoses for documented multi-morbid patient: remove P014's 3 diagnosis rows
before_count = len(dgn)
dgn = [r for r in dgn if r["patient_id"] != "P014"]
after_count = len(dgn)
log("E30", "08_diagnoses.csv",
    ["DGN-020", "DGN-021", "DGN-022"],
    ["patient_id"],
    f"P014 has no rows in the diagnoses table ({before_count - after_count} rows removed). "
    "Yet P014's health_profile records 'TYPE_2_DIABETES,HYPERTENSION,CHRONIC_KIDNEY_DISEASE' "
    "as chronic conditions, and the medications table shows Lisinopril (HTN), Metformin (T2DM), "
    "Amlodipine (HTN), and Furosemide (CKD oedema). "
    "The absence of any diagnostic record for a patient with documented conditions and medications "
    "is an implausible longitudinal gap.",
    "soft",
    "missing_expected_records",
    "Patients with documented chronic conditions in health_profile and corresponding medications "
    "in the medications table should have at least one matching diagnosis record. "
    "P014 should have ICD-10 records for I10 (HTN), E11.9 (T2DM), and N18.2 (CKD stage 2).",
    "Cross-references: 04_health_profile (P014 chronic_conditions) and 09_medications "
    "(MED-019, MED-020, MED-021, MED-031).")

write_csv("08_diagnoses.csv", dgn)
print(f"✓  08_diagnoses.csv  (E28, E29, E30, {len(dgn)} rows)")


# ═════════════════════════════════════════════════════════════════════════════
# TABLE 9: 09_medications.csv
# ═════════════════════════════════════════════════════════════════════════════

meds = read_csv("09_medications.csv")

# E31 — Value embeds unit: MED-018 (P012) dose_mg → "25mg"
i = idx(meds, medication_id="MED-018")
meds[i]["dose_mg"] = "25mg"
log("E31", "09_medications.csv",
    ["MED-018"],
    ["dose_mg"],
    "dose_mg value is '25mg' — the numeric value and unit string are concatenated in a "
    "column defined as a numeric field. The 'mg' suffix should not be present in the dose_mg "
    "column (the column name already implies the unit is milligrams).",
    "soft",
    "unit_embedded_in_numeric_field",
    "dose_mg must contain a plain numeric value (e.g., 25.0). "
    "Unit labels must not be appended to numeric measurement fields.")

write_csv("09_medications.csv", meds)
print(f"✓  09_medications.csv  (E31)")


# ═════════════════════════════════════════════════════════════════════════════
# TABLE 10 & 11: no errors
# ═════════════════════════════════════════════════════════════════════════════

for name in ["10_recommendations.csv", "11_protocols.csv"]:
    rows = read_csv(name)
    write_csv(name, rows)
print(f"  10_recommendations.csv, 11_protocols.csv  (clean copies)")


# ═════════════════════════════════════════════════════════════════════════════
# WRITE ERROR CATALOG
# ═════════════════════════════════════════════════════════════════════════════

catalog = {
    "dataset_version": "v2",
    "total_errors": len(ERRORS),
    "tables_affected": sorted({e["table"] for e in ERRORS}),
    "severity_counts": {
        "hard": sum(1 for e in ERRORS if e["severity"] == "hard"),
        "soft": sum(1 for e in ERRORS if e["severity"] == "soft"),
    },
    "category_counts": {},
    "errors": ERRORS,
}
for e in ERRORS:
    catalog["category_counts"][e["category"]] = catalog["category_counts"].get(e["category"], 0) + 1

with open(GT_DIR / "errors_catalog.json", "w", encoding="utf-8") as f:
    json.dump(catalog, f, indent=2, ensure_ascii=False)

print(f"\n✅  {len(ERRORS)} errors injected across {len(catalog['tables_affected'])} tables")
print(f"    Hard: {catalog['severity_counts']['hard']}  |  Soft: {catalog['severity_counts']['soft']}")
print(f"    Catalog written to ground_truth/errors_catalog.json")
