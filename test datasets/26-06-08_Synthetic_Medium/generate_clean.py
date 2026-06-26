#!/usr/bin/env python3
"""
generate_clean.py
Produces 11 clean synthetic CSV tables for Augura DQ engine v2 pressure testing.
Based on the Lucis data dictionary (502 fields, 9 domains).

Unit conventions:
  SITE_A  creatinine → mg/dL   |  glucose → mmol/L
  SITE_B  creatinine → µmol/L  |  glucose → mg/dL
"""

import csv
import math
from pathlib import Path

OUT = Path(__file__).parent / "clean"
OUT.mkdir(exist_ok=True)


def write_csv(path, rows):
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        wr.writeheader()
        wr.writerows(rows)


def r2(v):
    return round(float(v), 2) if v != "" else ""


def r1(v):
    return round(float(v), 1) if v != "" else ""


def ri(v):
    return int(round(float(v))) if v != "" else ""


# ─────────────────────────────────────────────────────────────────────────────
# 1. PATIENTS  (15 rows)
# ─────────────────────────────────────────────────────────────────────────────

PATIENTS = [
    # SITE_A ─────────────────────────────────────────────────────────────────
    {"patient_id": "P001", "gender": "female", "birth_date": "1979-03-15",
     "enrollment_date": "2024-01-08", "site_id": "SITE_A",
     "height_cm": 162.0, "weight_kg": 81.5, "waist_cm": 91.2,
     "ethnicity": "WHITE", "country_code": "GB", "death_date": "", "study_arm": "INTERVENTION"},
    {"patient_id": "P002", "gender": "male", "birth_date": "1986-11-22",
     "enrollment_date": "2024-01-10", "site_id": "SITE_A",
     "height_cm": 178.0, "weight_kg": 73.2, "waist_cm": 82.5,
     "ethnicity": "WHITE", "country_code": "GB", "death_date": "", "study_arm": "CONTROL"},
    {"patient_id": "P003", "gender": "female", "birth_date": "1972-07-08",
     "enrollment_date": "2024-01-15", "site_id": "SITE_A",
     "height_cm": 165.0, "weight_kg": 72.9, "waist_cm": 85.0,
     "ethnicity": "WHITE", "country_code": "GB", "death_date": "", "study_arm": "INTERVENTION"},
    {"patient_id": "P004", "gender": "male", "birth_date": "1957-04-20",
     "enrollment_date": "2024-01-18", "site_id": "SITE_A",
     "height_cm": 175.0, "weight_kg": 87.2, "waist_cm": 97.5,
     "ethnicity": "WHITE", "country_code": "GB", "death_date": "", "study_arm": "CONTROL"},
    {"patient_id": "P005", "gender": "female", "birth_date": "1995-09-14",
     "enrollment_date": "2024-01-22", "site_id": "SITE_A",
     "height_cm": 163.0, "weight_kg": 53.5, "waist_cm": 68.2,
     "ethnicity": "SOUTH_ASIAN", "country_code": "GB", "death_date": "", "study_arm": "INTERVENTION"},
    {"patient_id": "P006", "gender": "male", "birth_date": "1969-12-03",
     "enrollment_date": "2024-01-25", "site_id": "SITE_A",
     "height_cm": 177.0, "weight_kg": 93.1, "waist_cm": 102.3,
     "ethnicity": "WHITE", "country_code": "GB", "death_date": "", "study_arm": "CONTROL"},
    {"patient_id": "P007", "gender": "female", "birth_date": "1963-05-25",
     "enrollment_date": "2024-02-01", "site_id": "SITE_A",
     "height_cm": 160.0, "weight_kg": 62.2, "waist_cm": 78.5,
     "ethnicity": "WHITE", "country_code": "GB", "death_date": "", "study_arm": "INTERVENTION"},
    {"patient_id": "P008", "gender": "male", "birth_date": "1980-08-11",
     "enrollment_date": "2024-02-05", "site_id": "SITE_A",
     "height_cm": 180.0, "weight_kg": 90.1, "waist_cm": 98.2,
     "ethnicity": "BLACK", "country_code": "GB", "death_date": "", "study_arm": "INTERVENTION"},
    # SITE_B ─────────────────────────────────────────────────────────────────
    {"patient_id": "P009", "gender": "female", "birth_date": "1991-07-14",
     "enrollment_date": "2024-02-10", "site_id": "SITE_B",
     "height_cm": 162.0, "weight_kg": 57.5, "waist_cm": 70.3,
     "ethnicity": "WHITE", "country_code": "FR", "death_date": "", "study_arm": "CONTROL"},
    {"patient_id": "P010", "gender": "male", "birth_date": "1976-02-28",
     "enrollment_date": "2024-02-14", "site_id": "SITE_B",
     "height_cm": 174.0, "weight_kg": 91.0, "waist_cm": 103.5,
     "ethnicity": "WHITE", "country_code": "FR", "death_date": "", "study_arm": "INTERVENTION"},
    {"patient_id": "P011", "gender": "female", "birth_date": "1967-01-30",
     "enrollment_date": "2024-02-18", "site_id": "SITE_B",
     "height_cm": 158.0, "weight_kg": 65.5, "waist_cm": 82.0,
     "ethnicity": "WHITE", "country_code": "FR", "death_date": "2024-06-02", "study_arm": "CONTROL"},
    {"patient_id": "P012", "gender": "male", "birth_date": "1983-11-07",
     "enrollment_date": "2024-02-22", "site_id": "SITE_B",
     "height_cm": 176.0, "weight_kg": 78.6, "waist_cm": 88.1,
     "ethnicity": "WHITE", "country_code": "FR", "death_date": "", "study_arm": "INTERVENTION"},
    {"patient_id": "P013", "gender": "female", "birth_date": "1988-06-22",
     "enrollment_date": "2024-03-01", "site_id": "SITE_B",
     "height_cm": 166.0, "weight_kg": 65.8, "waist_cm": 77.4,
     "ethnicity": "HISPANIC", "country_code": "FR", "death_date": "", "study_arm": "CONTROL"},
    {"patient_id": "P014", "gender": "male", "birth_date": "1952-10-18",
     "enrollment_date": "2024-03-05", "site_id": "SITE_B",
     "height_cm": 172.0, "weight_kg": 80.1, "waist_cm": 95.8,
     "ethnicity": "WHITE", "country_code": "FR", "death_date": "", "study_arm": "CONTROL"},
    {"patient_id": "P015", "gender": "female", "birth_date": "1999-04-03",
     "enrollment_date": "2024-03-10", "site_id": "SITE_B",
     "height_cm": 167.0, "weight_kg": 59.4, "waist_cm": 72.1,
     "ethnicity": "WHITE", "country_code": "FR", "death_date": "", "study_arm": "INTERVENTION"},
]

write_csv(OUT / "01_patients.csv", PATIENTS)
print("✓  01_patients.csv  (15 rows)")


# ─────────────────────────────────────────────────────────────────────────────
# 2. BIOMARKER RESULTS  (44 rows — P011 has T0/T1 only, dies 2024-06-02)
# ─────────────────────────────────────────────────────────────────────────────
# T0 values keyed by patient_id. Missing sex-specific cols use "" sentinel.

BIO_T0 = {
    # apob,apoa1,ldl,hdl,tg | hgb,ferritin,serum_iron,transferrin,transferrin_sat
    # crp,wbc,nlr | crea_val,crea_unit,egfr,urea,na,k
    # ast,alt,ggt,bili | gluc_val,gluc_unit,hba1c,insulin,homa_ir
    # vitd,vitb12,mg,omega3 | testo,estradiol,shbg,psa | tsh,ft3,ft4 | cortisol,dheas
    "P001": {"apob_g_l": 1.38, "apoa1_g_l": 1.20, "ldl_mmol_l": 4.8, "hdl_mmol_l": 0.98, "tg_mmol_l": 2.8,
             "hemoglobin_g_dl": 13.0, "ferritin_ng_ml": 42, "serum_iron_umol_l": 13.8, "transferrin_g_l": 2.9, "transferrin_saturation_pct": 21,
             "crp_mg_l": 6.2, "wbc_1e9_l": 7.4, "nlr_ratio": 2.9,
             "creatinine_value": 0.87, "creatinine_unit": "mg/dL", "egfr_ml_min": 74, "urea_mmol_l": 6.1, "sodium_mmol_l": 140, "potassium_mmol_l": 4.2,
             "ast_u_l": 28, "alt_u_l": 35, "ggt_u_l": 42, "bilirubin_total_umol_l": 14,
             "glucose_value": 7.1, "glucose_unit": "mmol/L", "hba1c_pct": 6.9, "insulin_miu_l": 18.5, "homa_ir": 5.8,
             "vit_d_nmol_l": 38, "vit_b12_pmol_l": 285, "magnesium_mmol_l": 0.82, "omega3_index_pct": 4.8,
             "testosterone_nmol_l": "", "estradiol_pmol_l": 195, "shbg_nmol_l": 52, "psa_total_ug_l": "",
             "tsh_miu_l": 2.1, "ft3_pmol_l": 4.8, "ft4_pmol_l": 16.2, "cortisol_nmol_l": 395, "dheas_umol_l": 4.5},
    "P002": {"apob_g_l": 0.72, "apoa1_g_l": 1.45, "ldl_mmol_l": 2.0, "hdl_mmol_l": 1.82, "tg_mmol_l": 0.85,
             "hemoglobin_g_dl": 15.2, "ferritin_ng_ml": 88, "serum_iron_umol_l": 17.5, "transferrin_g_l": 2.4, "transferrin_saturation_pct": 30,
             "crp_mg_l": 0.9, "wbc_1e9_l": 5.8, "nlr_ratio": 1.8,
             "creatinine_value": 1.05, "creatinine_unit": "mg/dL", "egfr_ml_min": 92, "urea_mmol_l": 5.2, "sodium_mmol_l": 141, "potassium_mmol_l": 4.0,
             "ast_u_l": 18, "alt_u_l": 20, "ggt_u_l": 22, "bilirubin_total_umol_l": 10,
             "glucose_value": 5.0, "glucose_unit": "mmol/L", "hba1c_pct": 5.1, "insulin_miu_l": 5.8, "homa_ir": 1.3,
             "vit_d_nmol_l": 72, "vit_b12_pmol_l": 342, "magnesium_mmol_l": 0.88, "omega3_index_pct": 7.2,
             "testosterone_nmol_l": 18.5, "estradiol_pmol_l": 85, "shbg_nmol_l": 35, "psa_total_ug_l": 0.8,
             "tsh_miu_l": 1.8, "ft3_pmol_l": 5.2, "ft4_pmol_l": 16.8, "cortisol_nmol_l": 285, "dheas_umol_l": 8.2},
    "P003": {"apob_g_l": 0.92, "apoa1_g_l": 1.28, "ldl_mmol_l": 4.2, "hdl_mmol_l": 1.18, "tg_mmol_l": 2.1,
             "hemoglobin_g_dl": 12.8, "ferritin_ng_ml": 38, "serum_iron_umol_l": 12.5, "transferrin_g_l": 2.7, "transferrin_saturation_pct": 20,
             "crp_mg_l": 3.2, "wbc_1e9_l": 6.5, "nlr_ratio": 2.4,
             "creatinine_value": 0.82, "creatinine_unit": "mg/dL", "egfr_ml_min": 72, "urea_mmol_l": 5.5, "sodium_mmol_l": 139, "potassium_mmol_l": 4.0,
             "ast_u_l": 22, "alt_u_l": 24, "ggt_u_l": 20, "bilirubin_total_umol_l": 11,
             "glucose_value": 5.6, "glucose_unit": "mmol/L", "hba1c_pct": 5.6, "insulin_miu_l": 9.2, "homa_ir": 2.3,
             "vit_d_nmol_l": 55, "vit_b12_pmol_l": 298, "magnesium_mmol_l": 0.84, "omega3_index_pct": 5.1,
             "testosterone_nmol_l": "", "estradiol_pmol_l": 42, "shbg_nmol_l": 68, "psa_total_ug_l": "",
             "tsh_miu_l": 8.2, "ft3_pmol_l": 3.8, "ft4_pmol_l": 10.2, "cortisol_nmol_l": 325, "dheas_umol_l": 3.8},
    "P004": {"apob_g_l": 0.95, "apoa1_g_l": 1.15, "ldl_mmol_l": 3.2, "hdl_mmol_l": 1.05, "tg_mmol_l": 2.2,
             "hemoglobin_g_dl": 10.8, "ferritin_ng_ml": 225, "serum_iron_umol_l": 11.2, "transferrin_g_l": 2.1, "transferrin_saturation_pct": 23,
             "crp_mg_l": 8.5, "wbc_1e9_l": 7.2, "nlr_ratio": 3.1,
             "creatinine_value": 2.1, "creatinine_unit": "mg/dL", "egfr_ml_min": 35, "urea_mmol_l": 12.5, "sodium_mmol_l": 138, "potassium_mmol_l": 5.2,
             "ast_u_l": 24, "alt_u_l": 22, "ggt_u_l": 28, "bilirubin_total_umol_l": 13,
             "glucose_value": 6.2, "glucose_unit": "mmol/L", "hba1c_pct": 6.5, "insulin_miu_l": 12.5, "homa_ir": 3.5,
             "vit_d_nmol_l": 32, "vit_b12_pmol_l": 248, "magnesium_mmol_l": 0.78, "omega3_index_pct": 4.5,
             "testosterone_nmol_l": 9.5, "estradiol_pmol_l": 72, "shbg_nmol_l": 38, "psa_total_ug_l": 1.8,
             "tsh_miu_l": 2.5, "ft3_pmol_l": 4.5, "ft4_pmol_l": 15.5, "cortisol_nmol_l": 410, "dheas_umol_l": 3.2},
    "P005": {"apob_g_l": 0.65, "apoa1_g_l": 1.42, "ldl_mmol_l": 2.5, "hdl_mmol_l": 1.55, "tg_mmol_l": 0.92,
             "hemoglobin_g_dl": 10.2, "ferritin_ng_ml": 6, "serum_iron_umol_l": 7.1, "transferrin_g_l": 3.8, "transferrin_saturation_pct": 12,
             "crp_mg_l": 1.2, "wbc_1e9_l": 6.2, "nlr_ratio": 2.1,
             "creatinine_value": 0.72, "creatinine_unit": "mg/dL", "egfr_ml_min": 102, "urea_mmol_l": 4.8, "sodium_mmol_l": 141, "potassium_mmol_l": 3.9,
             "ast_u_l": 18, "alt_u_l": 16, "ggt_u_l": 14, "bilirubin_total_umol_l": 9,
             "glucose_value": 5.2, "glucose_unit": "mmol/L", "hba1c_pct": 5.1, "insulin_miu_l": 6.2, "homa_ir": 1.4,
             "vit_d_nmol_l": 48, "vit_b12_pmol_l": 318, "magnesium_mmol_l": 0.86, "omega3_index_pct": 5.2,
             "testosterone_nmol_l": "", "estradiol_pmol_l": 285, "shbg_nmol_l": 62, "psa_total_ug_l": "",
             "tsh_miu_l": 2.2, "ft3_pmol_l": 5.0, "ft4_pmol_l": 16.1, "cortisol_nmol_l": 458, "dheas_umol_l": 5.8},
    "P006": {"apob_g_l": 1.12, "apoa1_g_l": 1.05, "ldl_mmol_l": 4.2, "hdl_mmol_l": 0.92, "tg_mmol_l": 3.5,
             "hemoglobin_g_dl": 14.2, "ferritin_ng_ml": 380, "serum_iron_umol_l": 18.2, "transferrin_g_l": 2.2, "transferrin_saturation_pct": 36,
             "crp_mg_l": 7.8, "wbc_1e9_l": 7.8, "nlr_ratio": 3.2,
             "creatinine_value": 0.95, "creatinine_unit": "mg/dL", "egfr_ml_min": 85, "urea_mmol_l": 5.9, "sodium_mmol_l": 140, "potassium_mmol_l": 4.2,
             "ast_u_l": 65, "alt_u_l": 78, "ggt_u_l": 95, "bilirubin_total_umol_l": 28,
             "glucose_value": 6.8, "glucose_unit": "mmol/L", "hba1c_pct": 6.2, "insulin_miu_l": 15.2, "homa_ir": 4.6,
             "vit_d_nmol_l": 42, "vit_b12_pmol_l": 275, "magnesium_mmol_l": 0.80, "omega3_index_pct": 4.2,
             "testosterone_nmol_l": 10.5, "estradiol_pmol_l": 92, "shbg_nmol_l": 28, "psa_total_ug_l": 1.2,
             "tsh_miu_l": 1.9, "ft3_pmol_l": 4.7, "ft4_pmol_l": 15.8, "cortisol_nmol_l": 445, "dheas_umol_l": 5.2},
    "P007": {"apob_g_l": 0.82, "apoa1_g_l": 1.32, "ldl_mmol_l": 3.5, "hdl_mmol_l": 1.42, "tg_mmol_l": 1.5,
             "hemoglobin_g_dl": 13.2, "ferritin_ng_ml": 62, "serum_iron_umol_l": 14.5, "transferrin_g_l": 2.6, "transferrin_saturation_pct": 24,
             "crp_mg_l": 2.5, "wbc_1e9_l": 6.8, "nlr_ratio": 2.2,
             "creatinine_value": 0.78, "creatinine_unit": "mg/dL", "egfr_ml_min": 78, "urea_mmol_l": 5.8, "sodium_mmol_l": 140, "potassium_mmol_l": 4.1,
             "ast_u_l": 20, "alt_u_l": 18, "ggt_u_l": 22, "bilirubin_total_umol_l": 11,
             "glucose_value": 5.8, "glucose_unit": "mmol/L", "hba1c_pct": 5.5, "insulin_miu_l": 8.5, "homa_ir": 2.2,
             "vit_d_nmol_l": 28, "vit_b12_pmol_l": 295, "magnesium_mmol_l": 0.81, "omega3_index_pct": 5.0,
             "testosterone_nmol_l": "", "estradiol_pmol_l": 32, "shbg_nmol_l": 78, "psa_total_ug_l": "",
             "tsh_miu_l": 2.8, "ft3_pmol_l": 4.6, "ft4_pmol_l": 15.2, "cortisol_nmol_l": 368, "dheas_umol_l": 2.8},
    "P008": {"apob_g_l": 1.42, "apoa1_g_l": 1.08, "ldl_mmol_l": 5.2, "hdl_mmol_l": 1.05, "tg_mmol_l": 2.2,
             "hemoglobin_g_dl": 15.5, "ferritin_ng_ml": 95, "serum_iron_umol_l": 18.8, "transferrin_g_l": 2.5, "transferrin_saturation_pct": 32,
             "crp_mg_l": 5.8, "wbc_1e9_l": 7.5, "nlr_ratio": 2.9,
             "creatinine_value": 0.92, "creatinine_unit": "mg/dL", "egfr_ml_min": 88, "urea_mmol_l": 5.5, "sodium_mmol_l": 141, "potassium_mmol_l": 4.1,
             "ast_u_l": 22, "alt_u_l": 25, "ggt_u_l": 32, "bilirubin_total_umol_l": 12,
             "glucose_value": 5.9, "glucose_unit": "mmol/L", "hba1c_pct": 5.8, "insulin_miu_l": 10.2, "homa_ir": 2.7,
             "vit_d_nmol_l": 52, "vit_b12_pmol_l": 310, "magnesium_mmol_l": 0.85, "omega3_index_pct": 4.5,
             "testosterone_nmol_l": 14.5, "estradiol_pmol_l": 88, "shbg_nmol_l": 30, "psa_total_ug_l": 1.1,
             "tsh_miu_l": 1.8, "ft3_pmol_l": 5.1, "ft4_pmol_l": 16.5, "cortisol_nmol_l": 362, "dheas_umol_l": 7.5},
    # SITE_B ──────────────────────────────────────────────────────────────────
    "P009": {"apob_g_l": 0.62, "apoa1_g_l": 1.52, "ldl_mmol_l": 2.2, "hdl_mmol_l": 1.68, "tg_mmol_l": 0.88,
             "hemoglobin_g_dl": 13.5, "ferritin_ng_ml": 52, "serum_iron_umol_l": 15.2, "transferrin_g_l": 2.5, "transferrin_saturation_pct": 26,
             "crp_mg_l": 1.5, "wbc_1e9_l": 6.0, "nlr_ratio": 1.9,
             "creatinine_value": 65, "creatinine_unit": "µmol/L", "egfr_ml_min": 98, "urea_mmol_l": 4.8, "sodium_mmol_l": 141, "potassium_mmol_l": 3.9,
             "ast_u_l": 18, "alt_u_l": 16, "ggt_u_l": 14, "bilirubin_total_umol_l": 9,
             "glucose_value": 88, "glucose_unit": "mg/dL", "hba1c_pct": 4.9, "insulin_miu_l": 6.0, "homa_ir": 1.3,
             "vit_d_nmol_l": 68, "vit_b12_pmol_l": 325, "magnesium_mmol_l": 0.87, "omega3_index_pct": 6.1,
             "testosterone_nmol_l": "", "estradiol_pmol_l": 265, "shbg_nmol_l": 58, "psa_total_ug_l": "",
             "tsh_miu_l": 1.9, "ft3_pmol_l": 5.1, "ft4_pmol_l": 16.5, "cortisol_nmol_l": 388, "dheas_umol_l": 6.2},
    "P010": {"apob_g_l": 1.25, "apoa1_g_l": 1.12, "ldl_mmol_l": 4.0, "hdl_mmol_l": 0.95, "tg_mmol_l": 2.4,
             "hemoglobin_g_dl": 14.8, "ferritin_ng_ml": 88, "serum_iron_umol_l": 16.5, "transferrin_g_l": 2.4, "transferrin_saturation_pct": 30,
             "crp_mg_l": 6.5, "wbc_1e9_l": 7.8, "nlr_ratio": 3.0,
             "creatinine_value": 95, "creatinine_unit": "µmol/L", "egfr_ml_min": 80, "urea_mmol_l": 7.2, "sodium_mmol_l": 140, "potassium_mmol_l": 4.3,
             "ast_u_l": 28, "alt_u_l": 35, "ggt_u_l": 45, "bilirubin_total_umol_l": 14,
             "glucose_value": 148, "glucose_unit": "mg/dL", "hba1c_pct": 6.8, "insulin_miu_l": 20.1, "homa_ir": 6.2,
             "vit_d_nmol_l": 40, "vit_b12_pmol_l": 312, "magnesium_mmol_l": 0.80, "omega3_index_pct": 4.8,
             "testosterone_nmol_l": 16.2, "estradiol_pmol_l": 92, "shbg_nmol_l": 32, "psa_total_ug_l": 1.5,
             "tsh_miu_l": 2.2, "ft3_pmol_l": 4.9, "ft4_pmol_l": 15.8, "cortisol_nmol_l": 415, "dheas_umol_l": 6.8},
    "P011": {"apob_g_l": 1.18, "apoa1_g_l": 1.05, "ldl_mmol_l": 4.5, "hdl_mmol_l": 0.88, "tg_mmol_l": 3.2,
             "hemoglobin_g_dl": 11.2, "ferritin_ng_ml": 18, "serum_iron_umol_l": 9.5, "transferrin_g_l": 3.2, "transferrin_saturation_pct": 13,
             "crp_mg_l": 12.5, "wbc_1e9_l": 9.5, "nlr_ratio": 4.2,
             "creatinine_value": 82, "creatinine_unit": "µmol/L", "egfr_ml_min": 72, "urea_mmol_l": 8.5, "sodium_mmol_l": 136, "potassium_mmol_l": 4.8,
             "ast_u_l": 38, "alt_u_l": 42, "ggt_u_l": 65, "bilirubin_total_umol_l": 22,
             "glucose_value": 152, "glucose_unit": "mg/dL", "hba1c_pct": 7.2, "insulin_miu_l": 22.5, "homa_ir": 7.5,
             "vit_d_nmol_l": 22, "vit_b12_pmol_l": 185, "magnesium_mmol_l": 0.72, "omega3_index_pct": 3.5,
             "testosterone_nmol_l": "", "estradiol_pmol_l": 28, "shbg_nmol_l": 82, "psa_total_ug_l": "",
             "tsh_miu_l": 2.8, "ft3_pmol_l": 4.2, "ft4_pmol_l": 14.8, "cortisol_nmol_l": 555, "dheas_umol_l": 2.1},
    "P012": {"apob_g_l": 0.88, "apoa1_g_l": 1.22, "ldl_mmol_l": 3.1, "hdl_mmol_l": 1.18, "tg_mmol_l": 1.8,
             "hemoglobin_g_dl": 14.5, "ferritin_ng_ml": 72, "serum_iron_umol_l": 16.2, "transferrin_g_l": 2.5, "transferrin_saturation_pct": 28,
             "crp_mg_l": 2.8, "wbc_1e9_l": 6.5, "nlr_ratio": 2.3,
             "creatinine_value": 82, "creatinine_unit": "µmol/L", "egfr_ml_min": 92, "urea_mmol_l": 5.5, "sodium_mmol_l": 141, "potassium_mmol_l": 4.0,
             "ast_u_l": 20, "alt_u_l": 22, "ggt_u_l": 25, "bilirubin_total_umol_l": 11,
             "glucose_value": 98, "glucose_unit": "mg/dL", "hba1c_pct": 5.4, "insulin_miu_l": 8.5, "homa_ir": 2.1,
             "vit_d_nmol_l": 55, "vit_b12_pmol_l": 298, "magnesium_mmol_l": 0.84, "omega3_index_pct": 5.5,
             "testosterone_nmol_l": 8.2, "estradiol_pmol_l": 85, "shbg_nmol_l": 58, "psa_total_ug_l": 0.9,
             "tsh_miu_l": 2.0, "ft3_pmol_l": 4.8, "ft4_pmol_l": 16.0, "cortisol_nmol_l": 358, "dheas_umol_l": 6.5},
    "P013": {"apob_g_l": 0.72, "apoa1_g_l": 1.42, "ldl_mmol_l": 2.8, "hdl_mmol_l": 1.52, "tg_mmol_l": 1.2,
             "hemoglobin_g_dl": 13.8, "ferritin_ng_ml": 45, "serum_iron_umol_l": 14.8, "transferrin_g_l": 2.6, "transferrin_saturation_pct": 25,
             "crp_mg_l": 1.8, "wbc_1e9_l": 6.2, "nlr_ratio": 2.0,
             "creatinine_value": 68, "creatinine_unit": "µmol/L", "egfr_ml_min": 96, "urea_mmol_l": 5.0, "sodium_mmol_l": 140, "potassium_mmol_l": 4.0,
             "ast_u_l": 18, "alt_u_l": 20, "ggt_u_l": 16, "bilirubin_total_umol_l": 10,
             "glucose_value": 91, "glucose_unit": "mg/dL", "hba1c_pct": 5.2, "insulin_miu_l": 7.2, "homa_ir": 1.6,
             "vit_d_nmol_l": 58, "vit_b12_pmol_l": 315, "magnesium_mmol_l": 0.86, "omega3_index_pct": 5.8,
             "testosterone_nmol_l": "", "estradiol_pmol_l": 280, "shbg_nmol_l": 52, "psa_total_ug_l": "",
             "tsh_miu_l": 2.1, "ft3_pmol_l": 5.0, "ft4_pmol_l": 16.2, "cortisol_nmol_l": 395, "dheas_umol_l": 5.5},
    "P014": {"apob_g_l": 1.15, "apoa1_g_l": 1.08, "ldl_mmol_l": 3.8, "hdl_mmol_l": 0.92, "tg_mmol_l": 2.6,
             "hemoglobin_g_dl": 13.5, "ferritin_ng_ml": 125, "serum_iron_umol_l": 15.5, "transferrin_g_l": 2.3, "transferrin_saturation_pct": 29,
             "crp_mg_l": 9.2, "wbc_1e9_l": 8.2, "nlr_ratio": 3.5,
             "creatinine_value": 125, "creatinine_unit": "µmol/L", "egfr_ml_min": 55, "urea_mmol_l": 9.8, "sodium_mmol_l": 138, "potassium_mmol_l": 5.0,
             "ast_u_l": 28, "alt_u_l": 32, "ggt_u_l": 38, "bilirubin_total_umol_l": 14,
             "glucose_value": 162, "glucose_unit": "mg/dL", "hba1c_pct": 7.5, "insulin_miu_l": 22.8, "homa_ir": 8.1,
             "vit_d_nmol_l": 35, "vit_b12_pmol_l": 228, "magnesium_mmol_l": 0.78, "omega3_index_pct": 4.2,
             "testosterone_nmol_l": 8.8, "estradiol_pmol_l": 72, "shbg_nmol_l": 42, "psa_total_ug_l": 2.8,
             "tsh_miu_l": 3.2, "ft3_pmol_l": 4.3, "ft4_pmol_l": 14.8, "cortisol_nmol_l": 385, "dheas_umol_l": 2.5},
    "P015": {"apob_g_l": 0.65, "apoa1_g_l": 1.48, "ldl_mmol_l": 2.4, "hdl_mmol_l": 1.58, "tg_mmol_l": 0.95,
             "hemoglobin_g_dl": 13.2, "ferritin_ng_ml": 38, "serum_iron_umol_l": 13.2, "transferrin_g_l": 2.7, "transferrin_saturation_pct": 21,
             "crp_mg_l": 2.8, "wbc_1e9_l": 6.5, "nlr_ratio": 2.1,
             "creatinine_value": 62, "creatinine_unit": "µmol/L", "egfr_ml_min": 104, "urea_mmol_l": 4.5, "sodium_mmol_l": 141, "potassium_mmol_l": 3.9,
             "ast_u_l": 18, "alt_u_l": 17, "ggt_u_l": 15, "bilirubin_total_umol_l": 10,
             "glucose_value": 85, "glucose_unit": "mg/dL", "hba1c_pct": 5.0, "insulin_miu_l": 6.5, "homa_ir": 1.4,
             "vit_d_nmol_l": 32, "vit_b12_pmol_l": 265, "magnesium_mmol_l": 0.78, "omega3_index_pct": 4.5,
             "testosterone_nmol_l": "", "estradiol_pmol_l": 242, "shbg_nmol_l": 55, "psa_total_ug_l": "",
             "tsh_miu_l": 2.5, "ft3_pmol_l": 4.9, "ft4_pmol_l": 16.0, "cortisol_nmol_l": 650, "dheas_umol_l": 5.8},
}

# Per-patient delta multipliers for T1 and T2
# Format: {col: (factor_T1, factor_T2)}  — omitted cols stay at T0
BIO_DELTA = {
    "P001": {  # metabolic syndrome, IMPROVING
        "ldl_mmol_l": (0.87, 0.75), "hdl_mmol_l": (1.07, 1.14), "tg_mmol_l": (0.86, 0.72),
        "apob_g_l": (0.92, 0.85), "apoa1_g_l": (1.04, 1.09),
        "crp_mg_l": (0.77, 0.57), "wbc_1e9_l": (0.95, 0.90),
        "alt_u_l": (0.86, 0.74), "ast_u_l": (0.89, 0.79), "ggt_u_l": (0.85, 0.71),
        "glucose_value": (0.91, 0.84), "hba1c_pct": (0.94, 0.90),
        "insulin_miu_l": (0.82, 0.69), "homa_ir": (0.76, 0.58),
        "vit_d_nmol_l": (1.37, 1.79), "cortisol_nmol_l": (0.89, 0.81),
    },
    "P002": {  # athletic, STABLE — tiny drift only (no explicit overrides needed)
    },
    "P003": {  # hypothyroid, IMPROVING on levothyroxine
        "tsh_miu_l": (0.46, 0.26),  # 8.2 → 3.8 → 2.1
        "ft4_pmol_l": (1.32, 1.48), "ft3_pmol_l": (1.18, 1.29),
        "ldl_mmol_l": (0.93, 0.86), "tg_mmol_l": (0.90, 0.81),
        "crp_mg_l": (0.84, 0.70), "cortisol_nmol_l": (0.93, 0.88),
    },
    "P004": {  # CKD stage 3, DECLINING
        "creatinine_value": (1.10, 1.19),  # 2.1→2.31→2.5
        "egfr_ml_min": (0.91, 0.83),       # 35→32→29
        "urea_mmol_l": (1.10, 1.20), "potassium_mmol_l": (1.02, 1.04),
        "hemoglobin_g_dl": (0.97, 0.94), "crp_mg_l": (1.03, 1.06),
        "sodium_mmol_l": (0.99, 0.98),
    },
    "P005": {  # iron deficiency, IMPROVING on ferrous sulfate
        "ferritin_ng_ml": (2.0, 3.67),     # 6→12→22
        "serum_iron_umol_l": (1.44, 1.89), # 7.1→10.2→13.4
        "hemoglobin_g_dl": (1.13, 1.19),   # 10.2→11.5→12.1
        "transferrin_saturation_pct": (1.33, 1.67), # 12→16→20
        "transferrin_g_l": (0.87, 0.76),   # high transferrin falls with treatment
    },
    "P006": {  # NAFLD, IMPROVING
        "alt_u_l": (0.83, 0.69), "ast_u_l": (0.80, 0.67),
        "ggt_u_l": (0.82, 0.65), "bilirubin_total_umol_l": (0.89, 0.79),
        "crp_mg_l": (0.85, 0.72), "tg_mmol_l": (0.88, 0.77),
        "hdl_mmol_l": (1.06, 1.12), "homa_ir": (0.87, 0.76),
        "insulin_miu_l": (0.87, 0.76), "glucose_value": (0.94, 0.89),
    },
    "P007": {  # osteoporosis risk, STABLE with VitD supplementation
        "vit_d_nmol_l": (1.61, 2.21),  # 28→45→62
        "crp_mg_l": (0.92, 0.84),
    },
    "P008": {  # cardiovascular risk, IMPROVING on statin
        "ldl_mmol_l": (0.79, 0.65),    # 5.2→4.1→3.4
        "apob_g_l": (0.83, 0.69),
        "apoa1_g_l": (1.07, 1.13),
        "crp_mg_l": (0.72, 0.50),
        "tg_mmol_l": (0.88, 0.77), "hdl_mmol_l": (1.06, 1.11),
    },
    "P009": {  # healthy, STABLE — minimal change
    },
    "P010": {  # metabolic, IMPROVING on metformin + orlistat
        "glucose_value": (0.86, 0.74),  # 148→127→110
        "hba1c_pct": (0.93, 0.87),
        "insulin_miu_l": (0.83, 0.69), "homa_ir": (0.77, 0.59),
        "tg_mmol_l": (0.89, 0.79), "hdl_mmol_l": (1.05, 1.11),
        "crp_mg_l": (0.85, 0.72),
        "alt_u_l": (0.88, 0.77), "ggt_u_l": (0.88, 0.77),
        "vit_d_nmol_l": (1.25, 1.55),
    },
    "P011": {  # T0→T1 only (dies 2024-06-02), DECLINING
        "crp_mg_l": (1.46, None),      # 12.5→18.2
        "wbc_1e9_l": (1.21, None),     # 9.5→11.5
        "nlr_ratio": (1.38, None),     # 4.2→5.8
        "hemoglobin_g_dl": (0.88, None),  # 11.2→9.8
        "ferritin_ng_ml": (0.83, None),   # 18→15
        "ast_u_l": (1.37, None), "alt_u_l": (1.38, None), "ggt_u_l": (1.26, None),
        "creatinine_value": (1.10, None), "egfr_ml_min": (0.91, None),
        "sodium_mmol_l": (0.98, None), "potassium_mmol_l": (1.04, None),
        "cortisol_nmol_l": (1.12, None),
    },
    "P012": {  # testosterone deficiency, IMPROVING with treatment
        "testosterone_nmol_l": (1.07, 1.12),  # 8.2→8.8→9.2
        "shbg_nmol_l": (0.95, 0.91),
        "crp_mg_l": (0.93, 0.86),
    },
    "P013": {  # perimenopause, natural progression
        "estradiol_pmol_l": (0.86, 0.70),   # 280→240→196
        "shbg_nmol_l": (0.96, 0.92),
    },
    "P014": {  # elderly multi-morbid, DECLINING
        "glucose_value": (0.90, 0.85),  # 162→146→138 (treatment effect partially)
        "hba1c_pct": (0.97, 0.95),
        "creatinine_value": (1.02, 1.05), "egfr_ml_min": (0.98, 0.95),
        "urea_mmol_l": (1.04, 1.08), "potassium_mmol_l": (1.02, 1.04),
        "crp_mg_l": (1.02, 1.05),
    },
    "P015": {  # mental health, IMPROVING on SSRI
        "cortisol_nmol_l": (0.80, 0.63),   # 650→520→410
        "crp_mg_l": (0.89, 0.79),
        "vit_d_nmol_l": (1.28, 1.63),  # supplementing
        "magnesium_mmol_l": (1.04, 1.09),
    },
}

# Timepoint → enrollment date offsets in days
TP_OFFSET = {"T0": 0, "T1": 90, "T2": 180}
# Enrollment dates per patient
ENROLL = {p["patient_id"]: p["enrollment_date"] for p in PATIENTS}


def add_days(date_str, days):
    from datetime import date, timedelta
    y, m, d = date_str.split("-")
    return str(date(int(y), int(m), int(d)) + timedelta(days=days))


def apply_delta(base, delta, tp_index):
    """Return a float for the given timepoint (tp_index: 0=T0, 1=T1, 2=T2)."""
    if base == "":
        return ""
    if delta is None:
        return ""  # marker has no T2 value (P011)
    f = delta[tp_index - 1] if tp_index > 0 else 1.0
    if f is None:
        return ""
    val = float(base) * f
    # Preserve integer-like display for certain columns
    return val


BIO_COLS_INT = {"egfr_ml_min", "sodium_mmol_l", "potassium_mmol_l",
                "ferritin_ng_ml", "wbc_1e9_l"}

NUMERIC_COLS = {
    "apob_g_l": 2, "apoa1_g_l": 2, "ldl_mmol_l": 2, "hdl_mmol_l": 2, "tg_mmol_l": 2,
    "hemoglobin_g_dl": 1, "ferritin_ng_ml": 0, "serum_iron_umol_l": 1,
    "transferrin_g_l": 2, "transferrin_saturation_pct": 0,
    "crp_mg_l": 1, "wbc_1e9_l": 1, "nlr_ratio": 1,
    "creatinine_value": 1, "egfr_ml_min": 0, "urea_mmol_l": 1,
    "sodium_mmol_l": 0, "potassium_mmol_l": 1,
    "ast_u_l": 0, "alt_u_l": 0, "ggt_u_l": 0, "bilirubin_total_umol_l": 0,
    "glucose_value": 1, "hba1c_pct": 1, "insulin_miu_l": 1, "homa_ir": 1,
    "vit_d_nmol_l": 0, "vit_b12_pmol_l": 0, "magnesium_mmol_l": 2, "omega3_index_pct": 1,
    "testosterone_nmol_l": 1, "estradiol_pmol_l": 0, "shbg_nmol_l": 0, "psa_total_ug_l": 1,
    "tsh_miu_l": 1, "ft3_pmol_l": 1, "ft4_pmol_l": 1,
    "cortisol_nmol_l": 0, "dheas_umol_l": 1,
}

bio_rows = []
rid = 1
for p in PATIENTS:
    pid = p["patient_id"]
    t0 = BIO_T0[pid]
    delta = BIO_DELTA.get(pid, {})
    tps = ["T0", "T1"] if pid == "P011" else ["T0", "T1", "T2"]
    for tp in tps:
        tp_idx = ["T0", "T1", "T2"].index(tp)
        row = {
            "result_id": f"BIO-{rid:03d}",
            "patient_id": pid,
            "timepoint": tp,
            "sample_date": add_days(ENROLL[pid], TP_OFFSET[tp]),
            "site_id": p["site_id"],
        }
        for col, dp in NUMERIC_COLS.items():
            base_val = t0[col]
            if base_val == "":
                row[col] = ""
                continue
            col_delta = delta.get(col)
            if tp_idx == 0 or col_delta is None:
                raw = float(base_val)
            else:
                f = col_delta[tp_idx - 1]
                raw = float(base_val) * f if f is not None else None
            if raw is None:
                row[col] = ""
            elif dp == 0:
                row[col] = int(round(raw))
            else:
                row[col] = round(raw, dp)
        # pass-through string cols
        row["creatinine_unit"] = t0["creatinine_unit"]
        row["glucose_unit"] = t0["glucose_unit"]
        bio_rows.append(row)
        rid += 1

write_csv(OUT / "02_biomarker_results.csv", bio_rows)
print(f"✓  02_biomarker_results.csv  ({len(bio_rows)} rows)")


# ─────────────────────────────────────────────────────────────────────────────
# 3. DEXA RESULTS  (29 rows — all patients T0 + T2, except P011 T0 only)
# ─────────────────────────────────────────────────────────────────────────────

# T0 values: body_fat_pct, total_fat_kg, total_lean_kg, almi_kg_m2,
#            visceral_fat_area_cm2, lumbar_t, femoral_t, hip_t,
#            whole_body_bmd, frax_major_pct, frax_hip_pct, android_fat_pct, gynoid_fat_pct
DEXA_T0 = {
    "P001": [38.5, 31.4, 48.2, 6.1, 185, -0.8, -0.5, -0.4, 1.12, 4.5, 0.8, 42.1, 36.2],
    "P002": [14.2, 10.4, 62.1, 9.8, 65, 1.2, 1.0, 1.1, 1.35, 1.2, 0.1, 18.5, 12.8],
    "P003": [33.5, 24.4, 46.8, 6.5, 142, -0.9, -0.7, -0.6, 1.10, 5.8, 1.0, 38.2, 35.5],
    "P004": [31.8, 27.7, 57.2, 7.5, 175, -0.5, -0.4, -0.3, 1.15, 8.5, 1.5, 35.5, 28.8],
    "P005": [24.5, 13.1, 39.5, 6.2, 88, 0.2, 0.4, 0.3, 1.18, 2.5, 0.2, 28.5, 26.2],
    "P006": [33.1, 30.8, 60.5, 8.2, 195, -0.3, -0.2, -0.1, 1.18, 6.5, 1.2, 38.8, 30.5],
    "P007": [29.2, 18.2, 42.8, 5.8, 98, -2.6, -2.1, -2.0, 0.92, 18.5, 5.2, 32.5, 31.2],
    "P008": [28.5, 25.6, 63.2, 8.8, 168, 0.1, 0.2, 0.2, 1.22, 5.5, 0.8, 32.2, 26.5],
    "P009": [22.8, 13.1, 43.5, 6.8, 72, 0.5, 0.6, 0.7, 1.25, 2.5, 0.2, 25.5, 24.8],
    "P010": [35.2, 32.0, 57.5, 7.8, 212, -0.2, -0.1, 0.0, 1.15, 7.5, 1.5, 40.5, 33.2],
    "P011": [32.5, 21.3, 43.2, 5.9, 165, -1.2, -0.9, -0.8, 1.08, 14.5, 3.8, 36.5, 34.2],
    "P012": [22.5, 17.7, 59.8, 8.5, 95, 0.3, 0.5, 0.4, 1.25, 4.5, 0.6, 25.8, 20.5],
    "P013": [25.8, 17.0, 47.8, 7.1, 88, 0.4, 0.6, 0.5, 1.22, 2.8, 0.3, 29.2, 27.8],
    "P014": [31.2, 25.0, 53.8, 7.2, 185, -1.5, -1.2, -1.1, 1.05, 15.5, 4.2, 35.2, 29.5],
    "P015": [23.5, 14.0, 44.5, 6.5, 75, 0.3, 0.4, 0.5, 1.22, 2.2, 0.1, 26.5, 25.5],
}
# T2 deltas (factor for each field — for body fat: improving means decrease; lean mass: may increase)
DEXA_DELTA_T2 = {
    "P001": [0.95, 0.94, 1.01, 1.02, 0.93, 1.05, 1.05, 1.05, 1.01, 0.94, 0.92, 0.94, 0.96],
    "P002": [0.98, 0.97, 1.01, 1.02, 0.96, 1.01, 1.01, 1.01, 1.00, 0.98, 0.98, 0.98, 0.99],
    "P003": [0.96, 0.95, 1.02, 1.03, 0.95, 1.05, 1.05, 1.05, 1.02, 0.92, 0.90, 0.96, 0.97],
    "P004": [0.99, 0.99, 0.99, 0.99, 1.03, 1.03, 1.03, 1.03, 0.99, 1.02, 1.04, 1.00, 1.00],
    "P005": [0.93, 0.91, 1.04, 1.05, 0.90, 1.02, 1.02, 1.02, 1.02, 0.92, 0.88, 0.92, 0.94],
    "P006": [0.93, 0.91, 1.01, 1.02, 0.91, 1.03, 1.03, 1.03, 1.01, 0.93, 0.90, 0.93, 0.95],
    "P007": [0.99, 0.99, 1.01, 1.02, 0.98, 1.08, 1.07, 1.07, 1.02, 0.94, 0.88, 0.99, 0.99],
    "P008": [0.95, 0.93, 1.02, 1.03, 0.92, 1.03, 1.03, 1.03, 1.02, 0.93, 0.88, 0.94, 0.96],
    "P009": [0.99, 0.99, 1.01, 1.01, 0.99, 1.01, 1.01, 1.01, 1.00, 0.99, 0.99, 0.99, 0.99],
    "P010": [0.95, 0.93, 1.02, 1.03, 0.91, 1.03, 1.03, 1.03, 1.01, 0.93, 0.90, 0.93, 0.95],
    # P011 only T0 — no T2
    "P012": [0.98, 0.97, 1.01, 1.02, 0.97, 1.02, 1.02, 1.02, 1.01, 0.98, 0.97, 0.98, 0.99],
    "P013": [0.99, 0.99, 1.01, 1.01, 0.99, 1.01, 1.01, 1.01, 1.00, 0.99, 0.99, 0.99, 0.99],
    "P014": [1.01, 1.01, 0.99, 0.99, 1.04, 0.97, 0.97, 0.97, 0.99, 1.04, 1.08, 1.01, 1.01],
    "P015": [0.97, 0.96, 1.02, 1.03, 0.95, 1.02, 1.02, 1.02, 1.01, 0.95, 0.92, 0.96, 0.98],
}
DEXA_FIELDS = [
    "body_fat_pct", "total_fat_mass_kg", "total_lean_mass_kg", "almi_kg_m2",
    "visceral_fat_area_cm2", "lumbar_spine_t_score", "femoral_neck_t_score", "total_hip_t_score",
    "whole_body_bmd_g_cm2", "frax_major_osteoporotic_pct", "frax_hip_pct",
    "android_fat_pct", "gynoid_fat_pct",
]
DEXA_DP = [1, 1, 1, 2, 0, 1, 1, 1, 2, 1, 1, 1, 1]

dexa_rows = []
did = 1
for p in PATIENTS:
    pid = p["patient_id"]
    tps = ["T0"] if pid == "P011" else ["T0", "T2"]
    t0v = DEXA_T0[pid]
    for tp in tps:
        row = {
            "scan_id": f"DEX-{did:03d}",
            "patient_id": pid,
            "timepoint": tp,
            "scan_date": add_days(ENROLL[pid], TP_OFFSET[tp]),
            "site_id": p["site_id"],
        }
        if tp == "T0":
            vals = t0v
        else:
            d2 = DEXA_DELTA_T2[pid]
            vals = [t0v[i] * d2[i] for i in range(len(t0v))]
        for i, field in enumerate(DEXA_FIELDS):
            row[field] = round(vals[i], DEXA_DP[i])
        dexa_rows.append(row)
        did += 1

write_csv(OUT / "03_dexa_results.csv", dexa_rows)
print(f"✓  03_dexa_results.csv  ({len(dexa_rows)} rows)")


# ─────────────────────────────────────────────────────────────────────────────
# 4. HEALTH PROFILE  (15 rows — static at enrollment)
# ─────────────────────────────────────────────────────────────────────────────

HP = [
    {"patient_id": "P001", "activity_level": "LIGHT", "diet_type": "MEDITERRANEAN",
     "sleep_schedule_consistency": "SOMEWHAT_CONSISTENT", "avg_sleep_hours": 6.5,
     "stress_level_0_10": 6, "smoking_status": "NEVER", "alcohol_frequency": "2_4_PER_MONTH",
     "chronic_conditions": "TYPE_2_DIABETES,HYPERLIPIDAEMIA", "current_medications_yn": True,
     "preferred_communication_style": "BALANCED", "motivation_scale_1_10": 7,
     "living_situation": "WITH_PARTNER", "environment_type": "SUBURBAN"},
    {"patient_id": "P002", "activity_level": "VERY_ACTIVE", "diet_type": "OMNIVORE",
     "sleep_schedule_consistency": "VERY_CONSISTENT", "avg_sleep_hours": 7.8,
     "stress_level_0_10": 3, "smoking_status": "NEVER", "alcohol_frequency": "2_3_PER_WEEK",
     "chronic_conditions": "", "current_medications_yn": False,
     "preferred_communication_style": "SCIENTIFIC", "motivation_scale_1_10": 9,
     "living_situation": "WITH_PARTNER", "environment_type": "URBAN"},
    {"patient_id": "P003", "activity_level": "LIGHT", "diet_type": "OMNIVORE",
     "sleep_schedule_consistency": "INCONSISTENT_WEEKENDS", "avg_sleep_hours": 7.0,
     "stress_level_0_10": 5, "smoking_status": "FORMER", "alcohol_frequency": "MONTHLY_OR_LESS",
     "chronic_conditions": "HYPOTHYROIDISM", "current_medications_yn": True,
     "preferred_communication_style": "PRACTICAL", "motivation_scale_1_10": 6,
     "living_situation": "LIVE_ALONE", "environment_type": "SUBURBAN"},
    {"patient_id": "P004", "activity_level": "SEDENTARY", "diet_type": "OMNIVORE",
     "sleep_schedule_consistency": "SOMEWHAT_CONSISTENT", "avg_sleep_hours": 6.8,
     "stress_level_0_10": 5, "smoking_status": "FORMER", "alcohol_frequency": "MONTHLY_OR_LESS",
     "chronic_conditions": "CHRONIC_KIDNEY_DISEASE,TYPE_2_DIABETES,HYPERTENSION", "current_medications_yn": True,
     "preferred_communication_style": "SIMPLE", "motivation_scale_1_10": 5,
     "living_situation": "WITH_PARTNER", "environment_type": "RURAL"},
    {"patient_id": "P005", "activity_level": "MODERATE", "diet_type": "VEGETARIAN",
     "sleep_schedule_consistency": "VERY_CONSISTENT", "avg_sleep_hours": 7.5,
     "stress_level_0_10": 4, "smoking_status": "NEVER", "alcohol_frequency": "NEVER",
     "chronic_conditions": "IRON_DEFICIENCY_ANAEMIA", "current_medications_yn": True,
     "preferred_communication_style": "SCIENTIFIC", "motivation_scale_1_10": 8,
     "living_situation": "WITH_ROOMMATES", "environment_type": "URBAN"},
    {"patient_id": "P006", "activity_level": "SEDENTARY", "diet_type": "OMNIVORE",
     "sleep_schedule_consistency": "INCONSISTENT_WEEKENDS", "avg_sleep_hours": 7.2,
     "stress_level_0_10": 6, "smoking_status": "FORMER", "alcohol_frequency": "2_3_PER_WEEK",
     "chronic_conditions": "LIVER_DISEASE,HYPERLIPIDAEMIA", "current_medications_yn": True,
     "preferred_communication_style": "PRACTICAL", "motivation_scale_1_10": 5,
     "living_situation": "WITH_PARTNER", "environment_type": "SUBURBAN"},
    {"patient_id": "P007", "activity_level": "LIGHT", "diet_type": "MEDITERRANEAN",
     "sleep_schedule_consistency": "VERY_CONSISTENT", "avg_sleep_hours": 7.2,
     "stress_level_0_10": 4, "smoking_status": "NEVER", "alcohol_frequency": "MONTHLY_OR_LESS",
     "chronic_conditions": "OSTEOPOROSIS", "current_medications_yn": True,
     "preferred_communication_style": "BALANCED", "motivation_scale_1_10": 7,
     "living_situation": "LIVE_ALONE", "environment_type": "RURAL"},
    {"patient_id": "P008", "activity_level": "MODERATE", "diet_type": "OMNIVORE",
     "sleep_schedule_consistency": "SOMEWHAT_CONSISTENT", "avg_sleep_hours": 6.8,
     "stress_level_0_10": 6, "smoking_status": "FORMER", "alcohol_frequency": "4_PLUS_PER_WEEK",
     "chronic_conditions": "HYPERTENSION,HYPERCHOLESTEROLAEMIA", "current_medications_yn": True,
     "preferred_communication_style": "PRACTICAL", "motivation_scale_1_10": 6,
     "living_situation": "WITH_PARTNER", "environment_type": "URBAN"},
    {"patient_id": "P009", "activity_level": "MODERATE", "diet_type": "PESCATARIAN",
     "sleep_schedule_consistency": "VERY_CONSISTENT", "avg_sleep_hours": 7.5,
     "stress_level_0_10": 3, "smoking_status": "NEVER", "alcohol_frequency": "2_4_PER_MONTH",
     "chronic_conditions": "", "current_medications_yn": False,
     "preferred_communication_style": "SCIENTIFIC", "motivation_scale_1_10": 8,
     "living_situation": "WITH_PARTNER", "environment_type": "URBAN"},
    {"patient_id": "P010", "activity_level": "SEDENTARY", "diet_type": "OMNIVORE",
     "sleep_schedule_consistency": "VERY_INCONSISTENT", "avg_sleep_hours": 6.0,
     "stress_level_0_10": 7, "smoking_status": "CURRENT", "alcohol_frequency": "2_4_PER_MONTH",
     "chronic_conditions": "TYPE_2_DIABETES,OBESITY", "current_medications_yn": True,
     "preferred_communication_style": "SIMPLE", "motivation_scale_1_10": 6,
     "living_situation": "WITH_PARTNER", "environment_type": "SUBURBAN"},
    {"patient_id": "P011", "activity_level": "SEDENTARY", "diet_type": "OMNIVORE",
     "sleep_schedule_consistency": "INCONSISTENT_WEEKENDS", "avg_sleep_hours": 6.0,
     "stress_level_0_10": 8, "smoking_status": "FORMER", "alcohol_frequency": "MONTHLY_OR_LESS",
     "chronic_conditions": "COLON_CANCER,TYPE_2_DIABETES,HYPERTENSION", "current_medications_yn": True,
     "preferred_communication_style": "PRACTICAL", "motivation_scale_1_10": 4,
     "living_situation": "WITH_PARTNER", "environment_type": "SUBURBAN"},
    {"patient_id": "P012", "activity_level": "MODERATE", "diet_type": "OMNIVORE",
     "sleep_schedule_consistency": "SOMEWHAT_CONSISTENT", "avg_sleep_hours": 7.0,
     "stress_level_0_10": 5, "smoking_status": "NEVER", "alcohol_frequency": "2_3_PER_WEEK",
     "chronic_conditions": "TESTICULAR_HYPOFUNCTION", "current_medications_yn": True,
     "preferred_communication_style": "SCIENTIFIC", "motivation_scale_1_10": 7,
     "living_situation": "LIVE_ALONE", "environment_type": "URBAN"},
    {"patient_id": "P013", "activity_level": "MODERATE", "diet_type": "MEDITERRANEAN",
     "sleep_schedule_consistency": "SOMEWHAT_CONSISTENT", "avg_sleep_hours": 7.2,
     "stress_level_0_10": 5, "smoking_status": "NEVER", "alcohol_frequency": "2_4_PER_MONTH",
     "chronic_conditions": "PERIMENOPAUSE", "current_medications_yn": False,
     "preferred_communication_style": "BALANCED", "motivation_scale_1_10": 7,
     "living_situation": "WITH_PARTNER", "environment_type": "URBAN"},
    {"patient_id": "P014", "activity_level": "SEDENTARY", "diet_type": "OMNIVORE",
     "sleep_schedule_consistency": "VERY_INCONSISTENT", "avg_sleep_hours": 6.2,
     "stress_level_0_10": 6, "smoking_status": "FORMER", "alcohol_frequency": "MONTHLY_OR_LESS",
     "chronic_conditions": "TYPE_2_DIABETES,HYPERTENSION,CHRONIC_KIDNEY_DISEASE", "current_medications_yn": True,
     "preferred_communication_style": "SIMPLE", "motivation_scale_1_10": 5,
     "living_situation": "WITH_PARTNER", "environment_type": "RURAL"},
    {"patient_id": "P015", "activity_level": "LIGHT", "diet_type": "VEGAN",
     "sleep_schedule_consistency": "VERY_INCONSISTENT", "avg_sleep_hours": 5.5,
     "stress_level_0_10": 8, "smoking_status": "NEVER", "alcohol_frequency": "NEVER",
     "chronic_conditions": "DEPRESSION,GENERALISED_ANXIETY", "current_medications_yn": True,
     "preferred_communication_style": "BALANCED", "motivation_scale_1_10": 5,
     "living_situation": "LIVE_ALONE", "environment_type": "URBAN"},
]

for row in HP:
    row["profile_date"] = ENROLL[row["patient_id"]]
    row["site_id"] = next(p["site_id"] for p in PATIENTS if p["patient_id"] == row["patient_id"])

write_csv(OUT / "04_health_profile.csv", HP)
print(f"✓  04_health_profile.csv  (15 rows)")


# ─────────────────────────────────────────────────────────────────────────────
# 5. QUESTIONNAIRE FOLLOW-UP  (30 rows — T0 + T1 for all 15 patients)
# P011 is still alive at T1 (May 18), dies June 2
# ─────────────────────────────────────────────────────────────────────────────

# T0: phq9_total, phq9_cat, gad7_total, gad7_cat, psqi_total,
#     energy_level, stress_0_10, motivation_1_10, sleep_quality, wellbeing_1_10
QFU_T0 = {
    "P001": [5, "MILD", 4, "MINIMAL", 8, "MODERATE", 6, 7, "FAIR", 6],
    "P002": [1, "NONE", 1, "MINIMAL", 4, "HIGH", 3, 9, "GOOD", 9],
    "P003": [8, "MILD", 6, "MILD", 10, "LOW", 5, 6, "FAIR", 5],
    "P004": [6, "MILD", 5, "MILD", 9, "LOW", 5, 5, "FAIR", 5],
    "P005": [4, "NONE", 3, "MINIMAL", 7, "MODERATE", 4, 8, "GOOD", 7],
    "P006": [5, "MILD", 4, "MINIMAL", 9, "MODERATE", 6, 5, "FAIR", 5],
    "P007": [3, "NONE", 2, "MINIMAL", 7, "MODERATE", 4, 7, "GOOD", 7],
    "P008": [6, "MILD", 5, "MILD", 9, "MODERATE", 6, 6, "FAIR", 6],
    "P009": [2, "NONE", 2, "MINIMAL", 5, "HIGH", 3, 8, "GOOD", 8],
    "P010": [7, "MILD", 6, "MILD", 11, "LOW", 7, 6, "FAIR", 5],
    "P011": [9, "MILD", 7, "MILD", 12, "LOW", 8, 4, "POOR", 4],
    "P012": [4, "NONE", 3, "MINIMAL", 8, "MODERATE", 5, 7, "GOOD", 6],
    "P013": [3, "NONE", 3, "MINIMAL", 7, "MODERATE", 5, 7, "GOOD", 7],
    "P014": [7, "MILD", 6, "MILD", 11, "LOW", 6, 5, "FAIR", 5],
    "P015": [14, "MODERATE", 12, "MODERATE", 15, "LOW", 8, 5, "POOR", 4],
}
# T1 changes (absolute delta for int scores; same cat unless specified)
QFU_T1_DELTA = {  # (phq9d, gad7d, psqid, energyd, stressd, motivd, wellbeing_d) — strings stay same unless overridden
    "P001": [-2, -1, -2, 0, -1, 1, 1],
    "P002": [0, 0, -1, 0, 0, 0, 0],
    "P003": [-2, -1, -2, 1, -1, 1, 1],   # hypothyroid improving
    "P004": [1, 1, 1, 0, 0, 0, 0],        # declining
    "P005": [-1, -1, -1, 1, -1, 1, 1],   # iron improving
    "P006": [-1, -1, -1, 0, -1, 1, 1],
    "P007": [-1, 0, -1, 0, 0, 1, 0],
    "P008": [-2, -2, -2, 1, -1, 1, 1],
    "P009": [0, 0, -1, 0, 0, 0, 0],
    "P010": [-2, -2, -2, 1, -2, 1, 1],
    "P011": [3, 2, 2, -1, 1, -1, -1],    # declining
    "P012": [-1, -1, -1, 1, 0, 1, 1],
    "P013": [0, 0, 0, 0, 0, 0, 0],
    "P014": [1, 1, 1, 0, 0, -1, -1],
    "P015": [-4, -4, -3, 1, -2, 1, 2],   # mental health improving
}
QFU_PHQ9_CAT = lambda s: "NONE" if s <= 4 else "MILD" if s <= 9 else "MODERATE" if s <= 14 else "SEVERE"
QFU_GAD7_CAT = lambda s: "MINIMAL" if s <= 4 else "MILD" if s <= 9 else "MODERATE" if s <= 14 else "SEVERE"
QFU_PSQI_CAT = lambda s: "GOOD" if s <= 5 else "FAIR" if s <= 10 else "POOR"

ENERGY_SEQ = ["LOW", "MODERATE", "HIGH"]
SLEEP_SEQ = ["POOR", "FAIR", "GOOD", "EXCELLENT"]

qfu_rows = []
qid = 1
for p in PATIENTS:
    pid = p["patient_id"]
    base = QFU_T0[pid]
    d = QFU_T1_DELTA[pid]
    for tp in ["T0", "T1"]:
        if tp == "T0":
            phq, phq_cat, gad, gad_cat, psqi, energy, stress, motiv, sleep_q, wb = base
        else:
            phq  = max(0, base[0] + d[0])
            gad  = max(0, base[2] + d[1])
            psqi = max(0, base[4] + d[2])
            ei   = max(0, min(2, ENERGY_SEQ.index(base[5]) + d[3]))
            energy = ENERGY_SEQ[ei]
            stress = max(0, min(10, base[6] + d[4]))
            motiv  = max(1, min(10, base[7] + d[5]))
            si     = max(0, min(3, SLEEP_SEQ.index(base[8]) + (1 if d[2] < 0 else (-1 if d[2] > 0 else 0))))
            sleep_q = SLEEP_SEQ[si]
            wb     = max(1, min(10, base[9] + d[6]))
            phq_cat = QFU_PHQ9_CAT(phq)
            gad_cat = QFU_GAD7_CAT(gad)
        qfu_rows.append({
            "response_id": f"QFU-{qid:03d}",
            "patient_id": pid,
            "timepoint": tp,
            "response_date": add_days(ENROLL[pid], TP_OFFSET[tp]),
            "site_id": p["site_id"],
            "phq9_total": phq,
            "phq9_category": phq_cat,
            "gad7_total": gad,
            "gad7_category": gad_cat,
            "psqi_total": psqi,
            "energy_level": energy,
            "stress_level_0_10": stress,
            "motivation_scale_1_10": motiv,
            "sleep_quality": sleep_q,
            "general_wellbeing_1_10": wb,
        })
        qid += 1

write_csv(OUT / "05_questionnaire_followup.csv", qfu_rows)
print(f"✓  05_questionnaire_followup.csv  ({len(qfu_rows)} rows)")


# ─────────────────────────────────────────────────────────────────────────────
# 6. WEARABLE AGGREGATES  (60 rows — 15 patients × 4 months)
# ─────────────────────────────────────────────────────────────────────────────

# T0 monthly values: steps, resting_hr, hrv_ms, sleep_hrs, active_min, screen_hrs
WAR_BASE = {
    "P001": [6200, 74, 38, 6.5, 28, 5.8],
    "P002": [12500, 54, 72, 7.8, 85, 3.2],
    "P003": [5500, 76, 32, 6.8, 25, 5.5],
    "P004": [3800, 78, 28, 6.5, 15, 6.5],
    "P005": [6800, 78, 42, 7.2, 32, 5.2],
    "P006": [4200, 76, 30, 6.8, 18, 6.2],
    "P007": [5800, 72, 35, 7.2, 28, 5.5],
    "P008": [7200, 72, 40, 6.8, 38, 5.0],
    "P009": [8500, 68, 55, 7.5, 48, 4.2],
    "P010": [3900, 80, 25, 6.2, 18, 6.8],
    "P011": [3500, 82, 22, 5.8, 14, 7.2],
    "P012": [7500, 70, 48, 7.0, 42, 4.8],
    "P013": [8200, 70, 52, 7.2, 45, 4.5],
    "P014": [3200, 80, 22, 6.0, 12, 7.0],
    "P015": [5200, 76, 35, 5.5, 22, 7.5],
}
# Monthly delta (cumulative change factor per month for improving patients)
WAR_MONTHLY_DELTA = {
    "P001": [1.03, 0.98, 1.05, 1.04, 1.05, 0.97],
    "P002": [1.01, 0.99, 1.01, 1.00, 1.01, 0.99],
    "P003": [1.02, 0.99, 1.03, 1.02, 1.02, 0.99],
    "P004": [0.99, 1.01, 0.98, 0.99, 0.99, 1.01],
    "P005": [1.03, 0.98, 1.04, 1.02, 1.03, 0.98],
    "P006": [1.02, 0.99, 1.02, 1.01, 1.02, 0.99],
    "P007": [1.02, 0.99, 1.03, 1.01, 1.02, 0.99],
    "P008": [1.04, 0.98, 1.04, 1.03, 1.04, 0.98],
    "P009": [1.01, 0.99, 1.01, 1.00, 1.01, 0.99],
    "P010": [1.04, 0.98, 1.04, 1.03, 1.04, 0.98],
    "P011": [0.98, 1.02, 0.96, 0.97, 0.97, 1.02],
    "P012": [1.03, 0.99, 1.03, 1.02, 1.03, 0.99],
    "P013": [1.02, 0.99, 1.02, 1.01, 1.02, 0.99],
    "P014": [0.99, 1.01, 0.98, 0.99, 0.99, 1.01],
    "P015": [1.03, 0.98, 1.05, 1.04, 1.04, 0.97],
}

war_rows = []
wid = 1
for p in PATIENTS:
    pid = p["patient_id"]
    base = WAR_BASE[pid]
    df = WAR_MONTHLY_DELTA[pid]
    enroll_month = ENROLL[pid][:7]
    ey, em = int(enroll_month[:4]), int(enroll_month[5:])
    for m in range(4):
        mo = em + m
        yr = ey
        if mo > 12:
            mo -= 12
            yr += 1
        date_str = f"{yr}-{mo:02d}-01"
        vals = [base[i] * (df[i] ** m) for i in range(6)]
        war_rows.append({
            "record_id": f"WAR-{wid:03d}",
            "patient_id": pid,
            "recorded_month": date_str,
            "site_id": p["site_id"],
            "device_type": "WEARABLE" if pid in ["P001","P002","P004","P005","P007","P008","P009","P010","P012","P013"] else "SMARTWATCH" if pid in ["P003","P006","P011","P014"] else "PHONE_APP",
            "daily_steps_avg": int(round(vals[0])),
            "resting_hr_bpm": int(round(vals[1])),
            "hrv_ms": round(vals[2], 1),
            "sleep_hours_avg": round(vals[3], 1),
            "active_minutes_avg": int(round(vals[4])),
            "screen_time_hours_avg": round(vals[5], 1),
        })
        wid += 1

write_csv(OUT / "06_wearable_aggregates.csv", war_rows)
print(f"✓  06_wearable_aggregates.csv  ({len(war_rows)} rows)")


# ─────────────────────────────────────────────────────────────────────────────
# 7. CLINICAL VISITS  (44 rows — T0/T1/T2 all except P011 T0/T1 only)
# ─────────────────────────────────────────────────────────────────────────────

# T0: weight_kg, systolic, diastolic, vo2max
VIS_T0 = {
    "P001": [81.5, 138, 88, 24.5], "P002": [73.2, 118, 75, 52.8],
    "P003": [72.9, 128, 82, 26.2], "P004": [87.2, 148, 92, 21.5],
    "P005": [53.5, 112, 72, 31.5], "P006": [93.1, 142, 90, 22.8],
    "P007": [62.2, 132, 82, 24.0], "P008": [90.1, 145, 92, 28.5],
    "P009": [57.5, 115, 72, 35.2], "P010": [91.0, 145, 92, 22.5],
    "P011": [65.5, 150, 95, 20.5], "P012": [78.6, 125, 80, 30.5],
    "P013": [65.8, 118, 75, 32.8], "P014": [80.1, 155, 95, 19.5],
    "P015": [59.4, 118, 75, 30.2],
}
# Delta per timepoint (T1 factor, T2 factor) for each of the 4 values
VIS_DELTA = {
    "P001": [(0.98, 0.96), (0.97, 0.93), (0.97, 0.93), (1.04, 1.08)],
    "P002": [(1.00, 1.00), (1.00, 0.99), (1.00, 0.99), (1.02, 1.03)],
    "P003": [(0.99, 0.98), (0.98, 0.96), (0.98, 0.96), (1.03, 1.06)],
    "P004": [(1.00, 1.01), (1.01, 1.02), (1.01, 1.02), (0.97, 0.94)],
    "P005": [(0.99, 0.99), (0.99, 0.98), (0.99, 0.98), (1.04, 1.08)],
    "P006": [(0.98, 0.96), (0.99, 0.97), (0.99, 0.97), (1.03, 1.06)],
    "P007": [(1.00, 1.00), (0.99, 0.98), (0.99, 0.98), (1.02, 1.04)],
    "P008": [(0.98, 0.95), (0.97, 0.94), (0.97, 0.94), (1.03, 1.06)],
    "P009": [(1.00, 0.99), (0.99, 0.98), (0.99, 0.98), (1.02, 1.03)],
    "P010": [(0.98, 0.95), (0.98, 0.96), (0.98, 0.96), (1.04, 1.08)],
    "P011": [(1.01, None), (1.01, None), (1.01, None), (0.96, None)],
    "P012": [(1.00, 1.00), (0.99, 0.98), (0.99, 0.98), (1.02, 1.04)],
    "P013": [(1.00, 1.00), (0.99, 0.98), (0.99, 0.98), (1.02, 1.03)],
    "P014": [(1.00, 1.01), (1.01, 1.02), (1.01, 1.02), (0.97, 0.94)],
    "P015": [(0.99, 0.98), (0.99, 0.97), (0.99, 0.97), (1.03, 1.06)],
}

vis_rows = []
vid = 1
for p in PATIENTS:
    pid = p["patient_id"]
    base = VIS_T0[pid]
    dd = VIS_DELTA[pid]
    tps = ["T0", "T1"] if pid == "P011" else ["T0", "T1", "T2"]
    for tp in tps:
        ti = ["T0", "T1", "T2"].index(tp)
        visit_date = add_days(ENROLL[pid], TP_OFFSET[tp])
        admit_dt = f"{visit_date} 09:00"
        disch_dt = f"{visit_date} 11:30"
        if ti == 0:
            wt, sys, dia, vo2 = base
        else:
            fi = ti - 1
            wt  = round(base[0] * dd[0][fi], 1) if dd[0][fi] else base[0]
            sys = int(round(base[1] * dd[1][fi])) if dd[1][fi] else base[1]
            dia = int(round(base[2] * dd[2][fi])) if dd[2][fi] else base[2]
            vo2 = round(base[3] * dd[3][fi], 1) if dd[3][fi] else base[3]
        vis_rows.append({
            "visit_id": f"VIS-{vid:03d}",
            "patient_id": pid,
            "timepoint": tp,
            "visit_date": visit_date,
            "admission_datetime": admit_dt,
            "discharge_datetime": disch_dt,
            "site_id": p["site_id"],
            "systolic_bp_mmhg": sys,
            "diastolic_bp_mmhg": dia,
            "weight_kg": wt,
            "vo2max_ml_kg_min": vo2,
            "clinician_id": "CLIN-A01" if p["site_id"] == "SITE_A" else "CLIN-B01",
            "visit_notes_free_text": "",
        })
        vid += 1

write_csv(OUT / "07_clinical_visits.csv", vis_rows)
print(f"✓  07_clinical_visits.csv  ({len(vis_rows)} rows)")


# ─────────────────────────────────────────────────────────────────────────────
# 8. DIAGNOSES  (~26 rows)
# ICD-10 codes only; not all patients have diagnoses
# ─────────────────────────────────────────────────────────────────────────────

DIAGNOSES = [
    {"diagnosis_id": "DGN-001", "patient_id": "P001", "icd10_code": "E11.9",  "diagnosis_name": "Type 2 diabetes mellitus without complications", "onset_date": "2020-03-10", "status": "ACTIVE",   "site_id": "SITE_A"},
    {"diagnosis_id": "DGN-002", "patient_id": "P001", "icd10_code": "E78.5",  "diagnosis_name": "Hyperlipidaemia, unspecified",                   "onset_date": "2020-03-10", "status": "ACTIVE",   "site_id": "SITE_A"},
    {"diagnosis_id": "DGN-003", "patient_id": "P003", "icd10_code": "E03.9",  "diagnosis_name": "Hypothyroidism, unspecified",                    "onset_date": "2018-06-20", "status": "CHRONIC",  "site_id": "SITE_A"},
    {"diagnosis_id": "DGN-004", "patient_id": "P004", "icd10_code": "N18.3",  "diagnosis_name": "Chronic kidney disease, stage 3",               "onset_date": "2019-11-05", "status": "CHRONIC",  "site_id": "SITE_A"},
    {"diagnosis_id": "DGN-005", "patient_id": "P004", "icd10_code": "E11.9",  "diagnosis_name": "Type 2 diabetes mellitus without complications", "onset_date": "2016-04-18", "status": "CHRONIC",  "site_id": "SITE_A"},
    {"diagnosis_id": "DGN-006", "patient_id": "P004", "icd10_code": "I10",    "diagnosis_name": "Essential hypertension",                        "onset_date": "2015-09-12", "status": "CHRONIC",  "site_id": "SITE_A"},
    {"diagnosis_id": "DGN-007", "patient_id": "P005", "icd10_code": "D50.9",  "diagnosis_name": "Iron deficiency anaemia, unspecified",           "onset_date": "2023-08-30", "status": "ACTIVE",   "site_id": "SITE_A"},
    {"diagnosis_id": "DGN-008", "patient_id": "P006", "icd10_code": "K76.0",  "diagnosis_name": "Fatty liver disease, not elsewhere classified",  "onset_date": "2021-05-14", "status": "CHRONIC",  "site_id": "SITE_A"},
    {"diagnosis_id": "DGN-009", "patient_id": "P006", "icd10_code": "E78.1",  "diagnosis_name": "Pure hyperglyceridaemia",                       "onset_date": "2021-05-14", "status": "ACTIVE",   "site_id": "SITE_A"},
    {"diagnosis_id": "DGN-010", "patient_id": "P007", "icd10_code": "M81.0",  "diagnosis_name": "Age-related osteoporosis without fracture",     "onset_date": "2022-02-28", "status": "CHRONIC",  "site_id": "SITE_A"},
    {"diagnosis_id": "DGN-011", "patient_id": "P008", "icd10_code": "I10",    "diagnosis_name": "Essential hypertension",                        "onset_date": "2019-07-22", "status": "CHRONIC",  "site_id": "SITE_A"},
    {"diagnosis_id": "DGN-012", "patient_id": "P008", "icd10_code": "E78.00", "diagnosis_name": "Pure hypercholesterolaemia, unspecified",       "onset_date": "2019-07-22", "status": "ACTIVE",   "site_id": "SITE_A"},
    {"diagnosis_id": "DGN-013", "patient_id": "P010", "icd10_code": "E11.65", "diagnosis_name": "Type 2 diabetes with hyperglycaemia",           "onset_date": "2022-01-10", "status": "ACTIVE",   "site_id": "SITE_B"},
    {"diagnosis_id": "DGN-014", "patient_id": "P010", "icd10_code": "E66.01", "diagnosis_name": "Morbid obesity due to excess calories",         "onset_date": "2022-01-10", "status": "ACTIVE",   "site_id": "SITE_B"},
    {"diagnosis_id": "DGN-015", "patient_id": "P011", "icd10_code": "C18.9",  "diagnosis_name": "Malignant neoplasm of colon, unspecified",      "onset_date": "2023-03-15", "status": "ACTIVE",   "site_id": "SITE_B"},
    {"diagnosis_id": "DGN-016", "patient_id": "P011", "icd10_code": "E11.9",  "diagnosis_name": "Type 2 diabetes mellitus",                      "onset_date": "2019-08-20", "status": "CHRONIC",  "site_id": "SITE_B"},
    {"diagnosis_id": "DGN-017", "patient_id": "P011", "icd10_code": "I10",    "diagnosis_name": "Essential hypertension",                        "onset_date": "2017-11-05", "status": "CHRONIC",  "site_id": "SITE_B"},
    {"diagnosis_id": "DGN-018", "patient_id": "P012", "icd10_code": "E29.1",  "diagnosis_name": "Testicular hypofunction",                       "onset_date": "2023-05-10", "status": "ACTIVE",   "site_id": "SITE_B"},
    {"diagnosis_id": "DGN-019", "patient_id": "P013", "icd10_code": "N95.1",  "diagnosis_name": "Menopausal and female climacteric states",      "onset_date": "2023-09-01", "status": "ACTIVE",   "site_id": "SITE_B"},
    {"diagnosis_id": "DGN-020", "patient_id": "P014", "icd10_code": "I10",    "diagnosis_name": "Essential hypertension",                        "onset_date": "2008-03-15", "status": "CHRONIC",  "site_id": "SITE_B"},
    {"diagnosis_id": "DGN-021", "patient_id": "P014", "icd10_code": "E11.9",  "diagnosis_name": "Type 2 diabetes mellitus",                      "onset_date": "2012-07-28", "status": "CHRONIC",  "site_id": "SITE_B"},
    {"diagnosis_id": "DGN-022", "patient_id": "P014", "icd10_code": "N18.2",  "diagnosis_name": "Chronic kidney disease, stage 2",               "onset_date": "2020-10-14", "status": "CHRONIC",  "site_id": "SITE_B"},
    {"diagnosis_id": "DGN-023", "patient_id": "P015", "icd10_code": "F32.1",  "diagnosis_name": "Moderate depressive episode",                   "onset_date": "2023-01-08", "status": "ACTIVE",   "site_id": "SITE_B"},
    {"diagnosis_id": "DGN-024", "patient_id": "P015", "icd10_code": "F41.1",  "diagnosis_name": "Generalised anxiety disorder",                  "onset_date": "2022-11-15", "status": "ACTIVE",   "site_id": "SITE_B"},
    {"diagnosis_id": "DGN-025", "patient_id": "P002", "icd10_code": "S93.40", "diagnosis_name": "Sprain of ankle, unspecified",                  "onset_date": "2023-10-05", "status": "RESOLVED", "site_id": "SITE_A"},
    {"diagnosis_id": "DGN-026", "patient_id": "P009", "icd10_code": "J06.9",  "diagnosis_name": "Acute upper respiratory infection, unspecified","onset_date": "2024-01-12", "status": "RESOLVED", "site_id": "SITE_B"},
]

write_csv(OUT / "08_diagnoses.csv", DIAGNOSES)
print(f"✓  08_diagnoses.csv  ({len(DIAGNOSES)} rows)")


# ─────────────────────────────────────────────────────────────────────────────
# 9. MEDICATIONS  (32 rows)
# ─────────────────────────────────────────────────────────────────────────────

MEDICATIONS = [
    {"medication_id": "MED-001", "patient_id": "P001", "drug_name": "Metformin",         "rxnorm_code": "860975",  "dose_mg": 500.0,  "frequency": "TWICE_DAILY", "start_date": "2020-04-01", "end_date": "",           "indication": "Type 2 diabetes", "site_id": "SITE_A"},
    {"medication_id": "MED-002", "patient_id": "P001", "drug_name": "Atorvastatin",      "rxnorm_code": "617310",  "dose_mg": 20.0,   "frequency": "DAILY",       "start_date": "2020-04-01", "end_date": "",           "indication": "Hyperlipidaemia", "site_id": "SITE_A"},
    {"medication_id": "MED-003", "patient_id": "P003", "drug_name": "Levothyroxine",     "rxnorm_code": "966571",  "dose_mg": 0.1,    "frequency": "DAILY",       "start_date": "2018-07-10", "end_date": "",           "indication": "Hypothyroidism", "site_id": "SITE_A"},
    {"medication_id": "MED-004", "patient_id": "P004", "drug_name": "Ramipril",          "rxnorm_code": "35208",   "dose_mg": 5.0,    "frequency": "DAILY",       "start_date": "2019-12-01", "end_date": "",           "indication": "CKD / hypertension", "site_id": "SITE_A"},
    {"medication_id": "MED-005", "patient_id": "P004", "drug_name": "Furosemide",        "rxnorm_code": "4603",    "dose_mg": 40.0,   "frequency": "DAILY",       "start_date": "2020-02-15", "end_date": "",           "indication": "Fluid overload (CKD)", "site_id": "SITE_A"},
    {"medication_id": "MED-006", "patient_id": "P004", "drug_name": "Darbepoetin alfa", "rxnorm_code": "1299251", "dose_mg": 0.04,   "frequency": "WEEKLY",      "start_date": "2021-03-10", "end_date": "",           "indication": "CKD-related anaemia", "site_id": "SITE_A"},
    {"medication_id": "MED-007", "patient_id": "P005", "drug_name": "Ferrous sulfate",  "rxnorm_code": "4418",    "dose_mg": 200.0,  "frequency": "TWICE_DAILY", "start_date": "2023-09-15", "end_date": "",           "indication": "Iron deficiency", "site_id": "SITE_A"},
    {"medication_id": "MED-008", "patient_id": "P006", "drug_name": "Atorvastatin",      "rxnorm_code": "617310",  "dose_mg": 20.0,   "frequency": "DAILY",       "start_date": "2021-06-01", "end_date": "",           "indication": "Hyperlipidaemia / NAFLD", "site_id": "SITE_A"},
    {"medication_id": "MED-009", "patient_id": "P007", "drug_name": "Alendronic acid",  "rxnorm_code": "17780",   "dose_mg": 70.0,   "frequency": "WEEKLY",      "start_date": "2022-04-01", "end_date": "",           "indication": "Osteoporosis", "site_id": "SITE_A"},
    {"medication_id": "MED-010", "patient_id": "P007", "drug_name": "Colecalciferol",   "rxnorm_code": "41889",   "dose_mg": 0.025,  "frequency": "DAILY",       "start_date": "2022-04-01", "end_date": "",           "indication": "Vitamin D deficiency", "site_id": "SITE_A"},
    {"medication_id": "MED-011", "patient_id": "P008", "drug_name": "Rosuvastatin",     "rxnorm_code": "301542",  "dose_mg": 20.0,   "frequency": "DAILY",       "start_date": "2019-08-10", "end_date": "",           "indication": "Hypercholesterolaemia", "site_id": "SITE_A"},
    {"medication_id": "MED-012", "patient_id": "P008", "drug_name": "Amlodipine",       "rxnorm_code": "17767",   "dose_mg": 5.0,    "frequency": "DAILY",       "start_date": "2019-08-10", "end_date": "",           "indication": "Hypertension", "site_id": "SITE_A"},
    {"medication_id": "MED-013", "patient_id": "P010", "drug_name": "Metformin",        "rxnorm_code": "860975",  "dose_mg": 1000.0, "frequency": "TWICE_DAILY", "start_date": "2022-02-01", "end_date": "",           "indication": "Type 2 diabetes", "site_id": "SITE_B"},
    {"medication_id": "MED-014", "patient_id": "P010", "drug_name": "Orlistat",         "rxnorm_code": "37925",   "dose_mg": 120.0,  "frequency": "THREE_DAILY", "start_date": "2023-05-15", "end_date": "",           "indication": "Obesity management", "site_id": "SITE_B"},
    {"medication_id": "MED-015", "patient_id": "P011", "drug_name": "FOLFOX regimen",   "rxnorm_code": "1731083", "dose_mg": 85.0,   "frequency": "AS_NEEDED",   "start_date": "2023-05-01", "end_date": "2024-05-30", "indication": "Colorectal cancer chemotherapy", "site_id": "SITE_B"},
    {"medication_id": "MED-016", "patient_id": "P011", "drug_name": "Ramipril",         "rxnorm_code": "35208",   "dose_mg": 5.0,    "frequency": "DAILY",       "start_date": "2017-12-01", "end_date": "",           "indication": "Hypertension", "site_id": "SITE_B"},
    {"medication_id": "MED-017", "patient_id": "P011", "drug_name": "Metformin",        "rxnorm_code": "860975",  "dose_mg": 1000.0, "frequency": "DAILY",       "start_date": "2019-09-01", "end_date": "",           "indication": "Type 2 diabetes", "site_id": "SITE_B"},
    {"medication_id": "MED-018", "patient_id": "P012", "drug_name": "Clomiphene",       "rxnorm_code": "2105",    "dose_mg": 25.0,   "frequency": "DAILY",       "start_date": "2023-06-10", "end_date": "",           "indication": "Hypogonadism / low testosterone", "site_id": "SITE_B"},
    {"medication_id": "MED-019", "patient_id": "P014", "drug_name": "Lisinopril",       "rxnorm_code": "29046",   "dose_mg": 10.0,   "frequency": "DAILY",       "start_date": "2008-05-01", "end_date": "",           "indication": "Hypertension", "site_id": "SITE_B"},
    {"medication_id": "MED-020", "patient_id": "P014", "drug_name": "Metformin",        "rxnorm_code": "860975",  "dose_mg": 1000.0, "frequency": "DAILY",       "start_date": "2012-09-01", "end_date": "",           "indication": "Type 2 diabetes", "site_id": "SITE_B"},
    {"medication_id": "MED-021", "patient_id": "P014", "drug_name": "Amlodipine",       "rxnorm_code": "17767",   "dose_mg": 5.0,    "frequency": "DAILY",       "start_date": "2015-02-20", "end_date": "",           "indication": "Hypertension (adjunct)", "site_id": "SITE_B"},
    {"medication_id": "MED-022", "patient_id": "P015", "drug_name": "Sertraline",       "rxnorm_code": "36437",   "dose_mg": 50.0,   "frequency": "DAILY",       "start_date": "2023-02-10", "end_date": "",           "indication": "Major depressive disorder", "site_id": "SITE_B"},
    {"medication_id": "MED-023", "patient_id": "P015", "drug_name": "Escitalopram",     "rxnorm_code": "321988",  "dose_mg": 10.0,   "frequency": "DAILY",       "start_date": "2022-12-01", "end_date": "2023-02-10", "indication": "Generalised anxiety disorder", "site_id": "SITE_B"},
    {"medication_id": "MED-024", "patient_id": "P002", "drug_name": "Ibuprofen",        "rxnorm_code": "5640",    "dose_mg": 400.0,  "frequency": "AS_NEEDED",   "start_date": "2023-10-06", "end_date": "2023-11-30", "indication": "Ankle sprain", "site_id": "SITE_A"},
    {"medication_id": "MED-025", "patient_id": "P004", "drug_name": "Metformin",        "rxnorm_code": "860975",  "dose_mg": 500.0,  "frequency": "TWICE_DAILY", "start_date": "2016-05-01", "end_date": "",           "indication": "Type 2 diabetes (CKD adjusted dose)", "site_id": "SITE_A"},
    {"medication_id": "MED-026", "patient_id": "P013", "drug_name": "Calcium carbonate","rxnorm_code": "1198648", "dose_mg": 500.0,  "frequency": "TWICE_DAILY", "start_date": "2024-03-05", "end_date": "",           "indication": "Perimenopause bone support", "site_id": "SITE_B"},
    {"medication_id": "MED-027", "patient_id": "P006", "drug_name": "Silymarin",        "rxnorm_code": "37242",   "dose_mg": 150.0,  "frequency": "THREE_DAILY", "start_date": "2021-06-01", "end_date": "",           "indication": "Liver support (NAFLD)", "site_id": "SITE_A"},
    {"medication_id": "MED-028", "patient_id": "P009", "drug_name": "Folic acid",       "rxnorm_code": "4511",    "dose_mg": 0.4,    "frequency": "DAILY",       "start_date": "2024-01-15", "end_date": "",           "indication": "Preconception supplementation", "site_id": "SITE_B"},
    {"medication_id": "MED-029", "patient_id": "P003", "drug_name": "Calcium carbonate","rxnorm_code": "1198648", "dose_mg": 500.0,  "frequency": "DAILY",       "start_date": "2020-01-01", "end_date": "",           "indication": "Bone support (hypothyroid risk)", "site_id": "SITE_A"},
    {"medication_id": "MED-030", "patient_id": "P008", "drug_name": "Aspirin",          "rxnorm_code": "1191",    "dose_mg": 75.0,   "frequency": "DAILY",       "start_date": "2021-01-10", "end_date": "",           "indication": "Cardiovascular risk reduction", "site_id": "SITE_A"},
    {"medication_id": "MED-031", "patient_id": "P014", "drug_name": "Furosemide",       "rxnorm_code": "4603",    "dose_mg": 20.0,   "frequency": "DAILY",       "start_date": "2021-08-01", "end_date": "",           "indication": "Oedema management", "site_id": "SITE_B"},
    {"medication_id": "MED-032", "patient_id": "P001", "drug_name": "Omeprazole",       "rxnorm_code": "7646",    "dose_mg": 20.0,   "frequency": "DAILY",       "start_date": "2021-05-15", "end_date": "",           "indication": "Gastroprotection with metformin", "site_id": "SITE_A"},
]

write_csv(OUT / "09_medications.csv", MEDICATIONS)
print(f"✓  09_medications.csv  ({len(MEDICATIONS)} rows)")


# ─────────────────────────────────────────────────────────────────────────────
# 10. RECOMMENDATIONS  (30 rows — 2 per patient)
# ─────────────────────────────────────────────────────────────────────────────

PILLARS = ["NUTRITION_GUT_HEALTH", "PHYSICAL_ACTIVITY_LONGEVITY_FITNESS",
           "SLEEP_RECOVERY", "STRESS_MENTAL_SOCIAL_HEALTH",
           "SMART_SUPPLEMENTATION", "ENVIRONMENT_TOXINS"]

REC_DATA = [
    ("P001", "Reduce refined carbohydrates and increase fibre intake", "NUTRITION_GUT_HEALTH", "HIGH"),
    ("P001", "Add 30-min structured walks 5×/week to improve insulin sensitivity", "PHYSICAL_ACTIVITY_LONGEVITY_FITNESS", "HIGH"),
    ("P002", "Increase omega-3 rich foods (fatty fish 3×/week)", "NUTRITION_GUT_HEALTH", "MEDIUM"),
    ("P002", "Optimise post-workout recovery with protein timing", "PHYSICAL_ACTIVITY_LONGEVITY_FITNESS", "MEDIUM"),
    ("P003", "Prioritise 7-8h consistent sleep to support thyroid recovery", "SLEEP_RECOVERY", "HIGH"),
    ("P003", "Iodine-rich diet review in context of levothyroxine therapy", "NUTRITION_GUT_HEALTH", "MEDIUM"),
    ("P004", "Restrict dietary potassium and phosphorus (CKD stage 3)", "NUTRITION_GUT_HEALTH", "HIGH"),
    ("P004", "Low-impact aquatic exercise 3×/week to preserve muscle mass", "PHYSICAL_ACTIVITY_LONGEVITY_FITNESS", "MEDIUM"),
    ("P005", "Iron-rich food pairing with vitamin C to enhance absorption", "NUTRITION_GUT_HEALTH", "HIGH"),
    ("P005", "Moderate aerobic activity to support haematopoiesis", "PHYSICAL_ACTIVITY_LONGEVITY_FITNESS", "MEDIUM"),
    ("P006", "Eliminate alcohol and reduce fructose; Mediterranean pattern", "NUTRITION_GUT_HEALTH", "HIGH"),
    ("P006", "Structured stress-reduction programme (cortisol reduction)", "STRESS_MENTAL_SOCIAL_HEALTH", "HIGH"),
    ("P007", "Weight-bearing exercise programme for bone density", "PHYSICAL_ACTIVITY_LONGEVITY_FITNESS", "HIGH"),
    ("P007", "Vitamin D3 + K2 supplementation (VitD < 30 nmol/L)", "SMART_SUPPLEMENTATION", "HIGH"),
    ("P008", "Saturated fat reduction and plant-sterol-enriched foods", "NUTRITION_GUT_HEALTH", "HIGH"),
    ("P008", "Zone 2 cardio 4×/week to reduce LDL and CRP", "PHYSICAL_ACTIVITY_LONGEVITY_FITNESS", "HIGH"),
    ("P009", "Maintain current dietary pattern; add 1 portion fatty fish/week", "NUTRITION_GUT_HEALTH", "LOW"),
    ("P009", "Sleep hygiene optimisation (already good, reinforce routine)", "SLEEP_RECOVERY", "LOW"),
    ("P010", "Low glycaemic index diet with caloric deficit of 500 kcal/day", "NUTRITION_GUT_HEALTH", "HIGH"),
    ("P010", "Step-count target of 8000/day; progress to 10000 by T2", "PHYSICAL_ACTIVITY_LONGEVITY_FITNESS", "HIGH"),
    ("P011", "Nutritional support during chemotherapy (anti-nausea foods)", "NUTRITION_GUT_HEALTH", "HIGH"),
    ("P011", "Palliative fatigue management and gentle mobility programme", "PHYSICAL_ACTIVITY_LONGEVITY_FITNESS", "MEDIUM"),
    ("P012", "Zinc and vitamin D optimisation for testosterone support", "SMART_SUPPLEMENTATION", "HIGH"),
    ("P012", "Resistance training protocol to support endogenous testosterone", "PHYSICAL_ACTIVITY_LONGEVITY_FITNESS", "HIGH"),
    ("P013", "Phytoestrogen-rich diet (legumes, flaxseed) for menopause support", "NUTRITION_GUT_HEALTH", "MEDIUM"),
    ("P013", "Stress reduction and improved sleep for hormonal balance", "STRESS_MENTAL_SOCIAL_HEALTH", "MEDIUM"),
    ("P014", "Low-sodium DASH diet for combined HTN and CKD management", "NUTRITION_GUT_HEALTH", "HIGH"),
    ("P014", "Chair-based and aquatic exercise for frail elderly", "PHYSICAL_ACTIVITY_LONGEVITY_FITNESS", "MEDIUM"),
    ("P015", "Magnesium glycinate supplementation for anxiety and sleep", "SMART_SUPPLEMENTATION", "HIGH"),
    ("P015", "Digital detox evenings + consistent sleep schedule", "SLEEP_RECOVERY", "HIGH"),
]

rec_rows = []
for i, (pid, title, pillar, priority) in enumerate(REC_DATA, 1):
    enroll = ENROLL[pid]
    site = next(p["site_id"] for p in PATIENTS if p["patient_id"] == pid)
    rec_rows.append({
        "rec_id": f"REC-{i:03d}",
        "patient_id": pid,
        "rec_date": add_days(enroll, 7),
        "pillar": pillar,
        "priority": priority,
        "title": title,
        "status": "ACTIVE",
        "created_by": "SYSTEM",
        "site_id": site,
    })

write_csv(OUT / "10_recommendations.csv", rec_rows)
print(f"✓  10_recommendations.csv  ({len(rec_rows)} rows)")


# ─────────────────────────────────────────────────────────────────────────────
# 11. PROTOCOLS  (15 rows — one per patient)
# ─────────────────────────────────────────────────────────────────────────────

PROTOCOL_TITLES = {
    "P001": "Metabolic Syndrome Reversal Protocol",
    "P002": "Elite Athletic Performance Maintenance",
    "P003": "Thyroid Optimisation & Metabolic Recovery",
    "P004": "CKD Progression Slowdown & Anaemia Management",
    "P005": "Iron Repletion & Haematological Recovery",
    "P006": "Hepatic Regeneration & Cardiometabolic Control",
    "P007": "Bone Density Preservation & Fall Prevention",
    "P008": "Cardiovascular Risk Reduction Programme",
    "P009": "Preventive Longevity Optimisation",
    "P010": "Type 2 Diabetes Remission Programme",
    "P011": "Oncology Supportive Care Protocol",
    "P012": "Hormonal Rebalancing & Vitality Protocol",
    "P013": "Perimenopausal Transition Support",
    "P014": "Multi-Morbidity Stabilisation Programme",
    "P015": "Mental Health & Resilience Building Protocol",
}
LUCIS_SCORES = {
    "P001": 58.5, "P002": 91.2, "P003": 67.8, "P004": 44.2, "P005": 72.5,
    "P006": 55.1, "P007": 69.8, "P008": 61.5, "P009": 88.4, "P010": 52.5,
    "P011": 38.2, "P012": 74.5, "P013": 81.5, "P014": 41.2, "P015": 62.5,
}

prot_rows = []
for p in PATIENTS:
    pid = p["patient_id"]
    enroll = ENROLL[pid]
    prot_rows.append({
        "protocol_id": f"PROT-{pid}",
        "patient_id": pid,
        "title": PROTOCOL_TITLES[pid],
        "status": "COMPLETED" if pid == "P011" else "ACTIVE",
        "start_date": add_days(enroll, 7),
        "end_date": "2024-06-02" if pid == "P011" else "",
        "lucis_score_at_creation": LUCIS_SCORES[pid],
        "goal_count": 3 if pid in ["P004", "P011", "P014"] else 4 if pid in ["P001","P006","P008","P010"] else 2,
        "review_date": add_days(enroll, 97),
        "site_id": p["site_id"],
    })

write_csv(OUT / "11_protocols.csv", prot_rows)
print(f"✓  11_protocols.csv  ({len(prot_rows)} rows)")

print("\n✅  All 11 clean tables written to ./clean/")
