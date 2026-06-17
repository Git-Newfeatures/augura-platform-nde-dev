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

// Neutral defaults applied to every study. Real per-study metadata should come
// from the backend study record once that is wired; until then studies render
// with this blank shape (no hardcoded partner content).
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
