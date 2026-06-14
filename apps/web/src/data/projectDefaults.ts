export interface BenchmarkMeta {
  indication: string;
  included: string;
  excluded: string;
}

export interface ProjectDefaults {
  displayName: string;
  tagline: string;
  headerMeta: string;
  productCharacteristics: string;
  userCharacteristics: string;
  outcomesOfInterest: string;
  defaultCohort: string;
  partnerLabel: string;
  endpoints: string[];
  cqExposure: string;
  cqPopulation: string[];
  benchmarkMeta: BenchmarkMeta;
}

export const PROJECT_DEFAULTS: Record<string, ProjectDefaults> = {
  lucis: {
    displayName: 'Lucis',
    tagline: 'preventive biomarker platform',
    headerMeta: 'Consumer wellness · France · UK · Ireland · Portugal',
    productCharacteristics: `Preventive digital health platform combining longitudinal biomarker testing, wearable data, lifestyle questionnaires, and personalised digital coaching to improve cardiometabolic health.

Key data collected:
• Repeated biological lab tests (HbA1c, lipids, CRP, glucose)
• Clinical metrics: BMI, blood pressure, waist circumference
• Wearable data: activity, sleep, HRV
• Lifestyle questionnaires: nutrition, sleep, mental health
• User engagement and adherence to recommendations`,
    userCharacteristics: `• ~4,000 active members in a longitudinal cohort
• Adults interested in preventive health
• Many with early cardiometabolic risk factors
• Repeated biomarker testing every 3–6 months`,
    outcomesOfInterest: `Demonstrate that following Lucis recommendations improves cardiometabolic health:
• Improvements in biomarkers (HbA1c, LDL, CRP)
• Improvements in behavioural metrics
• Reduction in diabetes progression risk`,
    defaultCohort: 'validation_v1',
    partnerLabel: 'Lucis',
    endpoints: ['hba1c', 'ldl', 'crp'],
    cqExposure: 'Top quartile engagement score (Q4)',
    cqPopulation: ['Prediabetic (HbA1c 5.7–6.4)', 'France', 'UK', 'Ireland', 'Portugal'],
    benchmarkMeta: {
      indication: 'cardiometabolic / preventive health',
      included: 'Digital health platforms targeting prediabetes, T2D prevention, lipid management, or general cardiometabolic risk reduction. Evidence from PubMed prospective studies, ClinicalTrials.gov registrations, and FDA-cleared general wellness SaMD.',
      excluded: 'Pharmacological interventions, in-clinic devices requiring HCP operation, acute-care SaMD (e.g. AF detection, sepsis prediction), and disease-management tools requiring an established diagnosis (Class IIa+).',
    },
  },

  bloomlife: {
    displayName: 'Bloomlife',
    tagline: 'maternal fetal monitoring',
    headerMeta: 'High-risk pregnancy RPM · Maternal fetal monitoring',
    productCharacteristics: `Remote patient monitoring platform for high-risk pregnancies combining continuous fetal heart rate monitoring, uterine contraction tracking, and maternal vital signs to support clinical decision-making.

Key data collected:
• Continuous fetal heart rate and movement
• Uterine contraction frequency and intensity
• Maternal blood pressure and weight
• Symptom self-reporting (headache, swelling, fetal movement)
• Clinical visit notes and ultrasound findings`,
    userCharacteristics: `• High-risk pregnant patients (preeclampsia, preterm labor, fetal growth restriction)
• Monitored from 24 weeks gestation through delivery
• Managed by maternal-fetal medicine specialists
• Daily or continuous monitoring cadence`,
    outcomesOfInterest: `Demonstrate that Bloomlife RPM reduces adverse perinatal outcomes:
• Earlier detection of preterm labor and preeclampsia
• Reduction in unplanned hospital admissions
• Improved neonatal outcomes (gestational age at delivery, NICU admission rate)`,
    defaultCohort: 'bloomlife_pilot_v1',
    partnerLabel: 'Bloomlife',
    endpoints: ['contraction_frequency', 'maternal_hr', 'fetal_movement'],
    cqExposure: 'Active monitoring (≥1 session/day)',
    cqPopulation: ['High-risk pregnant patients', '24–36 weeks gestation'],
    benchmarkMeta: {
      indication: 'maternal-fetal monitoring / high-risk pregnancy RPM',
      included: 'Remote patient monitoring platforms for high-risk pregnancies, continuous fetal surveillance devices, maternal vital-sign tracking tools, and digital decision-support systems for maternal-fetal medicine. Evidence from PubMed RCTs and observational studies, ClinicalTrials.gov registrations, and FDA 510(k)-cleared RPM devices.',
      excluded: 'General consumer wellness wearables without clinical-grade monitoring, in-hospital bedside monitors requiring HCP operation, neonatal ICU devices, and reproductive-health apps without perinatal outcome data.',
    },
  },
};

// Neutral defaults for studies that aren't a known demo fixture (created via the
// New-study flow, or real studies). Prevents Lucis content leaking into them.
export const BLANK_DEFAULTS: ProjectDefaults = {
  displayName: 'New study',
  tagline: '',
  headerMeta: '',
  productCharacteristics: '',
  userCharacteristics: '',
  outcomesOfInterest: '',
  defaultCohort: '',
  partnerLabel: 'Study',
  endpoints: [],
  cqExposure: '',
  cqPopulation: [],
  benchmarkMeta: { indication: '', included: '', excluded: '' },
};

export const FALLBACK_PROJECT_ID = 'lucis';
