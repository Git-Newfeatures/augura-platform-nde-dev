# Frontend Real-Only Cleanup — Frontend Wiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `apps/web` render only real, backend-sourced data: fetch every domain catalog from the `/reference/*` endpoints (built in the backend plan), derive exposure/population options from live cohort data, and delete every hardcoded catalog, fallback, and demo constant.

**Architecture:** Add a reference-catalog layer to `dataClient.js` (`fetchReference` + `useReference` hook, session-cached) with normalizers that reshape the snake_case API payloads into the exact shapes the views already render. Wire each view to the hook, delete the inline constants, and reuse the existing loading + EmptyState pattern. Pure presentation (icons, colors, the nav/workflow routing graph, regex *application* logic) stays client-side.

**Tech Stack:** React 18, Vite, plain JS/JSX + one TS file (`projectDefaults.ts`). No test runner — verification is `npm run build`, `npm run lint`, a grep sweep for deleted symbols, and a preview smoke test against a seeded backend.

**Prerequisite:** The backend plan (`2026-06-17-frontend-real-only-cleanup-backend.md`) must be merged/applied first — these endpoints must exist and be seeded. Runtime preview verification requires a reachable backend with the seed applied.

**Spec:** `docs/superpowers/specs/2026-06-17-frontend-real-only-cleanup-design.md`

All commands run from `apps/web/` unless noted. `vite build` fails on unresolved imports/refs, so it is the primary correctness gate for each task.

---

## Deletion ledger (used by the final grep sweep)

| File | Delete | Keep (presentation/logic) |
|---|---|---|
| `views/OutcomeSelection.jsx` | `OUTCOME_CATALOG`, `FALLBACK_OUTCOMES`, `ENDPOINT_METADATA`, `buildOutcomesFromEndpoints`, `EXPOSURE_OPTIONS`, `POPULATION_OPTIONS`, `D1_OUTCOME_MAP`, `ELEMENT_RATIONALE` | — |
| `views/StudyType.jsx` | `getStudyDesigns`, `ESTIMAND_OPTS` | `DESIGN_ICON`, new `DESIGN_COLOR` map |
| `workspace/NewStudyPage.jsx` | `FRAMEWORKS` | — |
| `config.js` | `ESTIMATORS`, `ESTIMATOR_FILTER` | `POWER_THRESHOLD`, `POWER_MARGINAL_FLOOR` |
| `CorpusPanelEmbed.jsx` | `ET_LABELS`, `ET_DESCRIPTIONS`, `SOURCE_DESCRIPTIONS`, `DOMAIN_LABELS`, `JUR_LABELS`, `SOURCE_LABEL_FALLBACK`, `SOURCE_ET_DEFAULTS` | `ET_COLORS`, `COVERAGE_COLS`, `COL_LABELS`, `MIN_COL_DOCS`, `sourceLabel` (rewired) |
| `views/ProfilingAssistant.jsx` | `STUDY_DESIGN_FALLBACK`, `DOC_TYPE_FALLBACK`, inline `RANGES` | `ID_COLS` (see note) |
| `views/DatasetVerification.jsx` | `PII_PATTERNS`, `GROUPS`, `GROUP_REMAP`, `ROLES`, `ROLE_LABEL` | `ROLE_TAG` |
| `data/projectDefaults.ts` | `FALLBACK_PROJECT_ID` | `BLANK_DEFAULTS` |
| `SimulationEngine.jsx` *(gap, found by completeness critic)* | `OUTCOME_LABELS` | — |
| `views/CausalModel.jsx` *(gap)* | `D1_OUTCOME_MAP`, `OUTCOME_LABEL_MAP`, inline outcome label maps, Lucis demo strings (`D1_COMPARATOR`, intervention/population fallbacks) | — |
| `views/DataAvailability.jsx` *(gap)* | `PRIMARY_OUTCOME_ROW`, `DYNAMIC_SECONDARIES` (hardcoded outcome labels + clinical caveats) | live cohort pct/N access |

> **Backend gap:** `CeslSourceOut` must also expose `default_evidence_type`
> (column/seed exist but the response schema omitted it, so F5's
> `SOURCE_ET_DEFAULTS` reads a field the API never returns).

> **Note on `ID_COLS`** (ProfilingAssistant.jsx:72): a short list of conventional
> id column names (`member_id`, `user_id`, …) used purely for local duplicate
> detection. It is detection *logic*, not surfaced data, and the backend
> `dq-rules` schema does not carry it. It stays client-side. If you later want it
> backend-sourced, add an `id_columns` array to `/reference/dq-rules`.

---

## Task 1: Reference-catalog layer in `dataClient.js`

**Files:**
- Modify: `apps/web/src/workspace/dataClient.js`

- [ ] **Step 1: Add the reference fetchers, cache, hook, and normalizers**

Append to `dataClient.js` (the file already imports `useState`, `useEffect`, `apiJson`):

```js
// ── Reference catalogs ──────────────────────────────────────────────────────
//   Static config served by the backend /reference/* endpoints. Cached for the
//   session (these don't change between fetches). Raw payloads are cached; views
//   apply the exported normalizers (some need per-study context, e.g. {partner}).
const REFERENCE_ENDPOINTS = {
  outcomes:           '/reference/outcomes',
  study_designs:      '/reference/study-designs',
  estimands:          '/reference/estimands',
  estimators:         '/reference/estimators',
  frameworks:         '/reference/frameworks',
  evidence_types:     '/reference/evidence-types',
  domains:            '/reference/domains',
  jurisdictions:      '/reference/jurisdictions',
  literature_designs: '/reference/literature-study-designs',
  dq_rules:           '/reference/dq-rules',
  variable_roles:     '/reference/variable-roles',
  cesl_sources:       '/reference/cesl-sources',
}

const _refCache = new Map()

/** One-shot, session-cached fetch of a raw reference payload. Yields null on error. */
export async function fetchReference(name) {
  if (_refCache.has(name)) return _refCache.get(name)
  const path = REFERENCE_ENDPOINTS[name]
  const promise = (path ? apiJson(path) : Promise.resolve(null)).catch(() => null)
  _refCache.set(name, promise)
  return promise
}

/** Returns { data, loading } for a reference catalog. `data` is the raw payload (array or object) or null. */
export function useReference(name) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    let alive = true
    ;(async () => {
      setLoading(true)
      const d = await fetchReference(name)
      if (alive) { setData(d); setLoading(false) }
    })()
    return () => { alive = false }
  }, [name])
  return { data, loading }
}

// snake_case API → the exact shapes each view renders. Pure functions, no fetch.

/** /reference/outcomes → { [columnCode]: { key, label, unit, primary, desc, tags, verdict, verdictLabel } }.
 *  The "In dataset ✓" availability tag is added by the view from the live cohort, not here. */
export const normOutcomeCatalog = (rows) =>
  Object.fromEntries((rows ?? []).map((o) => [o.code, {
    key: o.short_key, label: o.label, unit: o.unit, primary: o.is_primary,
    desc: o.description, tags: o.regulatory_tags ?? [],
    verdict: o.verdict, verdictLabel: o.verdict_label,
  }]))

/** /reference/estimators → array with camelCase fields matching the old ESTIMATORS const. */
export const normEstimators = (rows) =>
  (rows ?? []).map((e) => ({
    key: e.key, label: e.label, short: e.short, recommended: e.recommended,
    bootstrapPending: e.bootstrap_pending, interpretability: e.interpretability,
    stability: e.stability, tooltip: e.tooltip,
    eligibleStudyTypes: e.eligible_study_types ?? [],
  }))

/** Build the old ESTIMATOR_FILTER shape ({ retro:[keys], prosp:[keys] }) from normalized estimators. */
export const estimatorFilter = (estimators) => ({
  retro: (estimators ?? []).filter((e) => e.eligibleStudyTypes.includes('retro')).map((e) => e.key),
  prosp: (estimators ?? []).filter((e) => e.eligibleStudyTypes.includes('prosp')).map((e) => e.key),
})

/** /reference/study-designs → the StudyType selector shape. Only enriched designs
 *  (those with a description) are selector options. {partner} is interpolated here. */
export const normStudyDesigns = (rows, partner = 'Partner') =>
  (rows ?? [])
    .filter((d) => d.description != null && d.description !== '')
    .map((d) => ({
      id: d.code,
      name: d.label,
      desc: String(d.description ?? '').replaceAll('{partner}', partner),
      tags: (d.tags ?? []).map(([c, t]) => [c, String(t).replaceAll('{partner}', partner)]),
      estimands: d.estimands ?? [],
    }))

/** /reference/estimands → the old ESTIMAND_OPTS shape (desc ← description). */
export const normEstimands = (rows) =>
  (rows ?? []).map((e) => ({
    key: e.key, name: e.name, desc: e.description,
    regulatory: e.regulatory, recommended: e.recommended, tag: e.tag,
  }))

/** Array of { code, label } → { [code]: label } map (evidence-types/domains/jurisdictions/literature designs/sources). */
export const codeLabelMap = (rows) =>
  Object.fromEntries((rows ?? []).map((r) => [r.code, r.label]))
```

- [ ] **Step 2: Build to confirm no syntax/import errors**

Run: `npm run build`
Expected: build succeeds (the new exports are unused so far; this verifies syntax).

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/workspace/dataClient.js
git commit -m "feat(web): reference-catalog fetch layer + normalizers"
```

---

## Task 2: `config.js` — remove ESTIMATORS, rewire SimulationEngine & StudyDesign

**Files:**
- Modify: `apps/web/src/config.js`
- Modify: `apps/web/src/SimulationEngine.jsx`
- Modify: `apps/web/src/views/StudyDesign.jsx`

- [ ] **Step 1: Delete `ESTIMATORS` and `ESTIMATOR_FILTER` from `config.js`**

Remove lines 20-49 (the `ESTIMATORS` array and `ESTIMATOR_FILTER` object). Keep `POWER_THRESHOLD` and `POWER_MARGINAL_FLOOR`. Update the file's header comment to drop the estimator-config description.

- [ ] **Step 2: Rewire `SimulationEngine.jsx`**

Remove `ESTIMATORS, ESTIMATOR_FILTER,` from the `./config` import (line 28). Add:
```js
import { useReference, normEstimators, estimatorFilter } from '@/workspace/dataClient'
```
Inside the component, near the other hooks:
```js
const { data: estimatorRows, loading: estimatorsLoading } = useReference('estimators')
const ESTIMATORS = useMemo(() => normEstimators(estimatorRows), [estimatorRows])
const ESTIMATOR_FILTER = useMemo(() => estimatorFilter(ESTIMATORS), [ESTIMATORS])
```
(Ensure `useMemo` is imported from `react`.) All existing references to `ESTIMATORS` / `ESTIMATOR_FILTER` (lines ~349-1035) now resolve to these locals. Where the component renders before estimators load, guard the empty case: if `estimatorsLoading`, render the existing loading affordance (or `ESTIMATORS.length === 0` → the existing empty/loading branch). Add a guard at the top of the estimator-dependent render: `if (estimatorsLoading) return <the existing loading UI>` — reuse whatever spinner/skeleton the file already uses; if none, render `null` until loaded.

- [ ] **Step 3: Rewire `views/StudyDesign.jsx`**

Remove `import { ESTIMATORS, ESTIMATOR_FILTER } from "../config";` (line 6). Add:
```js
import { useReference, normEstimators, estimatorFilter } from '@/workspace/dataClient'
```
Inside the component:
```js
const { data: estimatorRows, loading: estimatorsLoading } = useReference('estimators')
const ESTIMATORS = useMemo(() => normEstimators(estimatorRows), [estimatorRows])
const ESTIMATOR_FILTER = useMemo(() => estimatorFilter(ESTIMATORS), [ESTIMATORS])
```
(Import `useMemo`.) The local `ESTIMATOR_META` (descriptions/tags keyed by estimator key, lines 9-…) is presentation — **keep it**. References at lines 56-57, 122 resolve to the locals. Add an `estimatorsLoading` guard before the estimator list renders (reuse existing loading UI or `null`).

- [ ] **Step 4: Build**

Run: `npm run build`
Expected: success. If it fails with "ESTIMATORS is not defined", a reference was missed — fix and rebuild.

- [ ] **Step 5: Confirm the constants are gone**

Run: `grep -rn "ESTIMATOR_FILTER\|export const ESTIMATORS" src`
Expected: no matches (the only `ESTIMATORS` now are the in-component `const ESTIMATORS = useMemo(...)`).

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/config.js apps/web/src/SimulationEngine.jsx apps/web/src/views/StudyDesign.jsx
git commit -m "feat(web): source estimators from /reference/estimators"
```

---

## Task 3: `StudyType.jsx` — study designs + estimands from API

**Files:**
- Modify: `apps/web/src/views/StudyType.jsx`

- [ ] **Step 1: Add a client-side color map and wire the hooks**

Keep `DESIGN_ICON` (lines 9-14). Add a color map (the colors were inline in `getStudyDesigns`):
```js
const DESIGN_COLOR = {
  retro_cohort: '#0F6E56', pre_post: '#0C447C',
  external_matched: '#633806', mediation: '#2E9EAD',
}
```
Add imports:
```js
import { useMemo } from 'react'
import { useReference, normStudyDesigns, normEstimands } from '@/workspace/dataClient'
```
In the component (it receives `partnerLabel`):
```js
const { data: designRows, loading: designsLoading } = useReference('study_designs')
const { data: estimandRows } = useReference('estimands')
const STUDY_DESIGNS = useMemo(
  () => normStudyDesigns(designRows, partnerLabel).map((d) => ({
    ...d, icon: '📂', color: DESIGN_COLOR[d.id],
  })),
  [designRows, partnerLabel],
)
const ESTIMAND_OPTS = useMemo(() => normEstimands(estimandRows), [estimandRows])
```
> The old `getStudyDesigns()` set per-design emoji icons (`📂📈🔗🔬`). Preserve them
> with a code→emoji map alongside `DESIGN_COLOR` (retro_cohort `📂`, pre_post `📈`,
> external_matched `🔗`, mediation `🔬`) instead of the single `'📂'` above.

- [ ] **Step 2: Replace `getStudyDesigns(partnerLabel)` and `ESTIMAND_OPTS` references**

Wherever the render called `getStudyDesigns(partnerLabel)`, use `STUDY_DESIGNS`. The `ESTIMAND_OPTS` references now point to the memoized local. Add a loading guard: while `designsLoading && STUDY_DESIGNS.length === 0`, render the existing loading affordance (or an EmptyState "Loading study designs…").

- [ ] **Step 3: Delete the constants**

Delete `getStudyDesigns` (lines 16-55) and `ESTIMAND_OPTS` (lines 57-87).

- [ ] **Step 4: Build + grep**

Run: `npm run build`
Run: `grep -rn "getStudyDesigns\|ESTIMAND_OPTS" src`
Expected: build succeeds; grep returns no matches.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/views/StudyType.jsx
git commit -m "feat(web): source study designs + estimands from /reference"
```

---

## Task 4: `NewStudyPage.jsx` — frameworks from API

**Files:**
- Modify: `apps/web/src/workspace/NewStudyPage.jsx`

- [ ] **Step 1: Wire the hook and delete `FRAMEWORKS`**

Delete `const FRAMEWORKS = [...]` (line 9). Add:
```js
import { useReference } from '@/workspace/dataClient'
```
In the component:
```js
const { data: frameworkRows } = useReference('frameworks')
const FRAMEWORKS = (frameworkRows ?? []).map((f) => f.label)
```
This preserves the existing behavior (the dropdown rendered framework label strings and submitted the selected label in the POST `/studies` body). All existing `FRAMEWORKS` references resolve to this local. If the form renders before frameworks load, the dropdown is simply empty until loaded — acceptable (an empty `<select>`); no fallback list.

- [ ] **Step 2: Build + grep**

Run: `npm run build`
Run: `grep -rn "const FRAMEWORKS = \[" src`
Expected: build succeeds; grep returns no matches.

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/workspace/NewStudyPage.jsx
git commit -m "feat(web): source frameworks from /reference/frameworks"
```

---

## Task 5: `CorpusPanelEmbed.jsx` — corpus classification labels from API

**Files:**
- Modify: `apps/web/src/CorpusPanelEmbed.jsx`

- [ ] **Step 1: Wire the reference hooks**

Add the import:
```js
import { useReference, codeLabelMap } from '@/workspace/dataClient'
```
Inside the component, build the label/description maps from the API (replacing the deleted consts). Use `useMemo`:
```js
const { data: etRows } = useReference('evidence_types')
const { data: domainRows } = useReference('domains')
const { data: jurRows } = useReference('jurisdictions')
const { data: sourceRows } = useReference('cesl_sources')

const ET_LABELS = useMemo(() => codeLabelMap(etRows), [etRows])
const ET_DESCRIPTIONS = useMemo(
  () => Object.fromEntries((etRows ?? []).map((e) => [e.code, e.description])), [etRows])
const DOMAIN_LABELS = useMemo(() => codeLabelMap(domainRows), [domainRows])
const JUR_LABELS = useMemo(() => codeLabelMap(jurRows), [jurRows])
const SOURCE_ET_DEFAULTS = useMemo(
  () => Object.fromEntries((sourceRows ?? [])
    .filter((s) => s.default_evidence_type)
    .map((s) => [s.code, s.default_evidence_type])), [sourceRows])
```
(Import `useMemo` — the file already imports `useState, useEffect, useMemo`.)

- [ ] **Step 2: Rewire the `sourceLabel` helper**

The module-level `sourceLabel(code, agentSources)` (lines 122-127) referenced `COL_LABELS` and `SOURCE_LABEL_FALLBACK`. Keep `COL_LABELS` (heatmap column abbreviations — presentation). Remove the `SOURCE_LABEL_FALLBACK` fallback tier; resolve from the fetched `cesl_sources` instead. Since `sourceLabel` is module-level, pass the fetched sources in (the call sites already pass `agentSources`). Rewrite:
```js
function sourceLabel(code, agentSources = []) {
  return (agentSources ?? []).find((s) => s.code === code)?.label
    ?? COL_LABELS[code]
    ?? code
}
```
At call sites inside the component, pass the fetched `sourceRows` as `agentSources` if no agent-provided sources exist: `sourceLabel(code, agentSources.length ? agentSources : (sourceRows ?? []))`.

- [ ] **Step 3: Delete the moved constants**

Delete `ET_LABELS` (12-21), `ET_DESCRIPTIONS` (25-34), `SOURCE_DESCRIPTIONS` (36-44), `DOMAIN_LABELS` (56-74), `JUR_LABELS` (76-80), `SOURCE_LABEL_FALLBACK` (112-118), and the module-level `SOURCE_ET_DEFAULTS` (130-135). **Keep** `ET_COLORS` (47-54), `COVERAGE_COLS` (84-95), `COL_LABELS` (96-107), `MIN_COL_DOCS` (110).

> `SOURCE_DESCRIPTIONS` had extra display-only keys (`510k`, `semantic_scholar`)
> not in `cesl_sources`. If a tooltip references those, resolve the description
> from the fetched `cesl_sources` by code and render no tooltip when absent — do
> not reintroduce a hardcoded description.

- [ ] **Step 4: Build + grep**

Run: `npm run build`
Run: `grep -rn "const ET_LABELS\|const ET_DESCRIPTIONS\|const DOMAIN_LABELS\|const JUR_LABELS\|SOURCE_LABEL_FALLBACK\|const SOURCE_ET_DEFAULTS\|const SOURCE_DESCRIPTIONS" src`
Expected: build succeeds; grep returns no matches.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/CorpusPanelEmbed.jsx
git commit -m "feat(web): source corpus classification labels from /reference"
```

---

## Task 6: `ProfilingAssistant.jsx` — literature designs + biomarker ranges from API

**Files:**
- Modify: `apps/web/src/views/ProfilingAssistant.jsx`

- [ ] **Step 1: Wire the hooks**

Add import:
```js
import { useReference, codeLabelMap } from '@/workspace/dataClient'
```
In the component:
```js
const { data: litDesignRows } = useReference('literature_designs')
const { data: sourceRows } = useReference('cesl_sources')
const { data: dqRules } = useReference('dq_rules')
const STUDY_DESIGN_FALLBACK = useMemo(() => codeLabelMap(litDesignRows), [litDesignRows])
const DOC_TYPE_FALLBACK = useMemo(
  () => Object.fromEntries((sourceRows ?? []).map((s) => [s.code, s.code])), [sourceRows])
```
(`DOC_TYPE_FALLBACK` was an identity map over source codes; derive it from the real source list. Import `useMemo`.)

- [ ] **Step 2: Replace inline `RANGES` in `runLocalChecks`**

The `runLocalChecks` function builds an inline `RANGES` array (lines 87-93). Replace it with the backend rules, rebuilding the regex from the `pattern` string:
```js
const RANGES = (dqRules?.biomarker_ranges ?? []).map((r) => ({
  patterns: new RegExp(r.pattern, 'i'),
  min: r.value_min, max: r.value_max, unit: r.unit,
}))
```
Because `runLocalChecks` may run from a `useEffect` on mount, ensure `dqRules` is available: gate the range portion on `dqRules` being loaded, or re-run `runLocalChecks` when `dqRules` arrives (add `dqRules` to the relevant effect's deps, or compute ranges at call time from the latest `dqRules`). Keep `ID_COLS` (line 72) as-is.

- [ ] **Step 3: Delete the moved constants**

Delete `STUDY_DESIGN_FALLBACK` (11-25) and `DOC_TYPE_FALLBACK` (27-32) module-level consts (now in-component memos). Remove the inline `RANGES` literal (replaced in Step 2).

- [ ] **Step 4: Build + grep**

Run: `npm run build`
Run: `grep -rn "^const STUDY_DESIGN_FALLBACK\|^const DOC_TYPE_FALLBACK" src && grep -rn "patterns:/hba1c/i" src`
Expected: build succeeds; both greps return no matches.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/views/ProfilingAssistant.jsx
git commit -m "feat(web): source literature designs + biomarker ranges from /reference"
```

---

## Task 7: `DatasetVerification.jsx` — PII patterns + variable roles from API

**Files:**
- Modify: `apps/web/src/views/DatasetVerification.jsx`

- [ ] **Step 1: Wire the hooks**

Add import:
```js
import { useReference } from '@/workspace/dataClient'
```
In the component:
```js
const { data: dqRules } = useReference('dq_rules')
const { data: varRoles } = useReference('variable_roles')

const PII_PATTERNS = useMemo(
  () => (dqRules?.pii_patterns ?? []).map((p) => ({ rx: new RegExp(p.pattern, 'i'), reason: p.label })),
  [dqRules])
const GROUPS = useMemo(
  () => (varRoles?.groups ?? []).map((g) => ({
    id: g.code, label: g.label, description: g.description, tagColor: ROLE_TAG[g.code] ?? 'b',
  })), [varRoles])
const GROUP_REMAP = useMemo(() => varRoles?.group_aliases ?? {}, [varRoles])
const ROLES = useMemo(
  () => (varRoles?.roles ?? []).filter((r) => r.selectable).map((r) => r.code), [varRoles])
const ROLE_LABEL = useMemo(
  () => Object.fromEntries((varRoles?.roles ?? []).map((r) => [r.code, r.label])), [varRoles])
```
> The old `GROUPS` carried a per-group `tagColor`. There is no per-group color in
> the API (colors are presentation). Reuse the kept `ROLE_TAG` map for group
> colors if a group code matches; otherwise default `'b'`, as above. If the UI
> relied on distinct group colors not present in `ROLE_TAG`, add a small
> client-side `GROUP_TAG` color map next to `ROLE_TAG` (presentation) with the
> original five group colors: outcomes `b`, exposure `g`, engagement `p`,
> administrative `b`, other `r` — and use that instead.

Keep `ROLE_TAG` (lines 65-70) as-is. `scanForPII` (line 20) already iterates `PII_PATTERNS` using `.rx`/`.reason` — the memo above preserves that shape, so `scanForPII` is unchanged. Ensure `scanForPII` is called after `PII_PATTERNS` is populated (gate on `dqRules` loaded, or re-scan when it arrives).

- [ ] **Step 2: Delete the moved constants**

Delete `PII_PATTERNS` (9-19), `GROUPS` (35-41), `GROUP_REMAP` (46-56), `ROLES` (58), and `ROLE_LABEL` (59-64) module-level consts. Keep `ROLE_TAG`.

- [ ] **Step 3: Build + grep**

Run: `npm run build`
Run: `grep -rn "^const PII_PATTERNS\|^const GROUPS\|^const GROUP_REMAP\|^const ROLES\|^const ROLE_LABEL" src`
Expected: build succeeds; grep returns no matches.

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/views/DatasetVerification.jsx
git commit -m "feat(web): source PII patterns + variable roles from /reference"
```

---

## Task 8: `OutcomeSelection.jsx` — outcomes from API + cohort-derived exposure/population

**Files:**
- Modify: `apps/web/src/views/OutcomeSelection.jsx`

This is the largest view change: remove the outcomes catalog + all fallbacks, fetch the catalog, intersect it with the live cohort biomarkers for the "In dataset ✓" availability tag, and derive exposure/population options from the real cohort members.

- [ ] **Step 1: Wire the outcomes catalog**

Add imports:
```js
import { useMemo } from 'react'
import { useReference, normOutcomeCatalog } from '@/workspace/dataClient'
```
In the component:
```js
const { data: outcomeRows, loading: outcomesLoading } = useReference('outcomes')
const OUTCOME_CATALOG = useMemo(() => normOutcomeCatalog(outcomeRows), [outcomeRows])
```
Wherever the view previously read `OUTCOME_CATALOG[col]` it now reads from this memo. The catalog no longer carries the "In dataset ✓" tag (that was demo data); add it from the live cohort in Step 3.

- [ ] **Step 2: Replace the outcome list construction (delete fallbacks)**

The view built its outcome list from `OUTCOME_CATALOG` ∩ cohort biomarkers, with `FALLBACK_OUTCOMES` / `buildOutcomesFromEndpoints` / `ENDPOINT_METADATA` as fallbacks. Replace that with a single real-only derivation from the live cohort (`fetchCohort` already provides `biomarkers`):
```js
// outcomes = catalog entries whose column is present in the cohort's biomarkers.
const availableOutcomes = useMemo(() => {
  const present = new Set((cohort?.biomarkers ?? []).map((b) => b.name ?? b.column ?? b.code))
  return Object.entries(OUTCOME_CATALOG)
    .filter(([col]) => present.has(col))
    .map(([col, meta]) => ({
      ...meta,
      tags: [['g', 'In dataset ✓'], ...meta.tags],
      available: true,
    }))
}, [OUTCOME_CATALOG, cohort])
```
> Confirm the cohort biomarker row field name (`b.name` vs `b.column` vs `b.code`)
> by logging one row of `cohort.biomarkers` once; the `present` set must key on the
> same code the catalog uses (the Supabase column name, e.g. `hba1c_pct`). Adjust
> the accessor accordingly. If the cohort has no biomarkers, `availableOutcomes`
> is `[]` → render the existing EmptyState ("No outcomes available for this
> cohort"), not a fallback list.

Render the existing loading affordance while `outcomesLoading`.

- [ ] **Step 3: Derive exposure & population options from the cohort**

Replace `EXPOSURE_OPTIONS` / `POPULATION_OPTIONS` (hardcoded) with derivations from `cohort.members`. The known field is `engagement_group` (lowercase `high`/`medium`/`low`, via the existing `engagementGroup` helper imported from `cohortData`). Derive other facets from whatever member fields exist, empty when absent:
```js
import { fetchCohort, engagementGroup } from '../workspace/cohortData'
// …
const EXPOSURE_OPTIONS = useMemo(() => {
  const groups = new Set((cohort?.members ?? []).map(engagementGroup).filter(Boolean))
  const labelFor = { high: 'High engagement', medium: 'Medium engagement', low: 'Low engagement' }
  return [...groups].sort().map((g) => labelFor[g] ?? g)
}, [cohort])

const distinct = (members, field) =>
  [...new Set((members ?? []).map((m) => m?.[field]).filter((v) => v != null && v !== ''))]

const POPULATION_OPTIONS = useMemo(() => {
  const members = cohort?.members ?? []
  const out = []
  const countries = distinct(members, 'country')
  if (countries.length) out.push({ group: 'Country', items: countries.sort() })
  const ages = distinct(members, 'age')
  if (ages.length) out.push({ group: 'Age', items: ['Adults (18–65)', 'Older adults (≥65)']
    .filter((bucket) => ages.some((a) => (bucket.startsWith('Older') ? a >= 65 : a < 65))) })
  return out
}, [cohort])
```
> The exact member field names (`country`, `age`, condition) depend on the
> ingested cohort schema. Log one `cohort.members` row to confirm, then map the
> real fields. Any facet whose field is absent simply does not render — no
> hardcoded France/UK/quartile list. If no facets resolve, the population picker
> renders empty.

- [ ] **Step 4: Replace `D1_OUTCOME_MAP` and `ELEMENT_RATIONALE`**

`D1_OUTCOME_MAP` mapped short-key → "X change at 12 months". Derive it from the catalog label + the study's follow-up window:
```js
const followupLabel = (m) => `${m.label} at 12 months` // window from study state if available, else "12 months"
const d1Label = (shortKey) => {
  const meta = Object.values(OUTCOME_CATALOG).find((o) => o.key === shortKey)
  return meta ? followupLabel(meta) : shortKey
}
```
Use `d1Label(key)` wherever `D1_OUTCOME_MAP[key]` was read. If the study state exposes a real follow-up window, use it instead of the literal "12 months".

`ELEMENT_RATIONALE` was hardcoded "agent rationale" prose. Delete it. Where the view rendered a rationale line, render the rationale from real agent output if the component already receives it (e.g. via `chatProps`/props); otherwise omit the rationale line entirely. Do not render hardcoded reasoning.

- [ ] **Step 5: Delete all the constants**

Delete `OUTCOME_CATALOG` (15-56), `FALLBACK_OUTCOMES` (59-69), `ENDPOINT_METADATA` (74-81), `buildOutcomesFromEndpoints` (83-96), `EXPOSURE_OPTIONS` (99-103), `POPULATION_OPTIONS` (105-109), `D1_OUTCOME_MAP` (110-119), `ELEMENT_RATIONALE` (122-126).

- [ ] **Step 6: Build + grep**

Run: `npm run build`
Run: `grep -rn "FALLBACK_OUTCOMES\|ENDPOINT_METADATA\|buildOutcomesFromEndpoints\|D1_OUTCOME_MAP\|ELEMENT_RATIONALE\|const OUTCOME_CATALOG" src`
Expected: build succeeds; grep returns no matches.

- [ ] **Step 7: Commit**

```bash
git add apps/web/src/views/OutcomeSelection.jsx
git commit -m "feat(web): outcomes from /reference + cohort-derived exposure/population"
```

---

## Task 9: `projectDefaults.ts` / `LucisApp.jsx` — remove the 'lucis' fallback

**Files:**
- Modify: `apps/web/src/data/projectDefaults.ts`
- Modify: `apps/web/src/LucisApp.jsx`

- [ ] **Step 1: Delete `FALLBACK_PROJECT_ID`**

In `projectDefaults.ts`, delete line 40 (`export const FALLBACK_PROJECT_ID = 'lucis';`). Keep `BLANK_DEFAULTS`.

- [ ] **Step 2: Require a real study id in `LucisApp.jsx`**

Remove `FALLBACK_PROJECT_ID` from the import (line 20) → `import { BLANK_DEFAULTS } from "./data/projectDefaults";`. Replace the three usages:
- Line 64: `const projectId = params.id ?? FALLBACK_PROJECT_ID;` → `const projectId = params.id ?? null;`
- Add an early guard: when `projectId` is null, render an explicit empty/"select a study" state instead of loading a `'lucis'` workspace. Use the existing EmptyState component the app uses elsewhere:
```js
if (!projectId) {
  return <EmptyState title="No study selected" hint="Open a study from the workspace to continue." />
}
```
(Use the actual EmptyState import/props already used in the codebase — check `workspace/` or `ui/components`. If a different empty-state primitive exists, use it.)
- Lines 564, 579: `tenantSlug={projectId ?? FALLBACK_PROJECT_ID}` → `tenantSlug={projectId}` (the guard above guarantees it is non-null here).

- [ ] **Step 3: Build + grep**

Run: `npm run build`
Run: `grep -rn "FALLBACK_PROJECT_ID\|'lucis'\|\"lucis\"" src`
Expected: build succeeds; grep returns no matches (no `lucis` literal anywhere in `src`).

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/data/projectDefaults.ts apps/web/src/LucisApp.jsx
git commit -m "feat(web): require a real study id, drop 'lucis' fallback"
```

---

## Task 10: Final verification sweep

- [ ] **Step 1: Full deletion-ledger grep**

Run from `apps/web`:
```bash
grep -rn -E "OUTCOME_CATALOG|FALLBACK_OUTCOMES|ENDPOINT_METADATA|buildOutcomesFromEndpoints|D1_OUTCOME_MAP|ELEMENT_RATIONALE|getStudyDesigns|ESTIMAND_OPTS|export const FRAMEWORKS|export const ESTIMATORS|ESTIMATOR_FILTER|ET_LABELS|ET_DESCRIPTIONS|SOURCE_DESCRIPTIONS|DOMAIN_LABELS|JUR_LABELS|SOURCE_LABEL_FALLBACK|SOURCE_ET_DEFAULTS|STUDY_DESIGN_FALLBACK|DOC_TYPE_FALLBACK|PII_PATTERNS|GROUP_REMAP|ROLE_LABEL|FALLBACK_PROJECT_ID" src
```
Expected: matches only inside `dataClient.js` normalizers / in-component `useMemo` locals — **no** top-level `const NAME = [literal data]` definitions. Eyeball each hit; every remaining occurrence must be a variable fed by `useReference`, not a hardcoded literal.

- [ ] **Step 2: Build + lint**

Run: `npm run build && npm run lint`
Expected: build succeeds; lint passes (fix any unused-import warnings left by deletions).

- [ ] **Step 3: Preview smoke test (requires a seeded backend reachable at `VITE_API_URL`)**

Use the preview tooling: start the dev server, then for each affected view confirm (a) the `/reference/*` call appears in the network log, (b) the catalog renders, (c) no console errors, (d) an empty cohort yields an EmptyState, not a crash or fabricated data. Affected views: New Study (frameworks), Study Type (designs + estimands), Outcome Selection (outcomes + exposure/population), Study Design / Simulation (estimators), Corpus panel (evidence types/domains/jurisdictions), Profiling Assistant (ranges), Dataset Verification (PII + roles).

If no backend is reachable, record that runtime verification is pending and rely on the build + grep gates; do **not** claim runtime-verified.

- [ ] **Step 4: Final commit (only if lint fixes were needed)**

```bash
git add -A
git commit -m "chore(web): lint cleanup after real-only cleanup"
```

---

## Self-review checklist (run before handing off)

- [ ] Every row of the deletion ledger has a task that both deletes the constant and supplies a `useReference`-backed replacement (or cohort-derived value).
- [ ] No view renders a hardcoded list when its catalog/cohort is empty — it renders loading then EmptyState.
- [ ] Normalizer field names match what each view reads (e.g. estimators expose `bootstrapPending`, `eligibleStudyTypes`; outcomes expose `primary`, `verdictLabel`, `desc`).
- [ ] `{partner}` interpolation happens in `normStudyDesigns` using the view's `partnerLabel`.
- [ ] `ID_COLS` (ProfilingAssistant) and `ROLE_TAG`/`ET_COLORS`/`COVERAGE_COLS`/`COL_LABELS` (presentation) are intentionally **kept**.
- [ ] No `lucis` literal remains anywhere in `apps/web/src`.
- [ ] Regex patterns from the backend are rebuilt with `new RegExp(pattern, 'i')` (PII + biomarker ranges) and match the original case-insensitive behavior.
