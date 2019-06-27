import { lineChart } from './charts';
import { socialContext } from './social-context-view';
import { format, read, safe, table } from './data';
import type { Rendered } from './atlas-view';
import type { HealthDomain, Index, State } from './types';

type PublicRow = Record<string, unknown>;
type SeriesDomain = Exclude<HealthDomain, 'survey' | 'context'>;
type Report = PublicRow & { week_start: string; reports: number };
interface StateReports {
  code: string;
  source: string;
  definition_sha256: string;
  weeks: Record<SeriesDomain, Report[]>;
}
interface Registry {
  host: string;
  dataset: string;
  first: string;
  last: string;
  date_basis: string;
  location_basis: string;
  source_description: string;
}
interface Surveillance {
  source: string;
  definition_sha256: string;
  jurisdictions: { code: string; label: string }[];
  registry: Record<SeriesDomain, Registry>;
  inputs: Record<string, { bytes: number; sha256: string }>;
  summary: Record<SeriesDomain, { weeks: number; with_reports: number; with_seven_report_dates: number }>;
}
interface Wave {
  wave: { start: string; end: string; recall_days: number; income_year: number; responses: number;
    weighted_unit_response_percent: number; release: string; phase: string };
  rows: (PublicRow & { group_kind: string; suppressed: boolean })[];
  selection_sensitivity: PublicRow[];
  source_sha256: string;
}
interface Bridge {
  source: string;
  definition_sha256: string;
  aggregate_comparator_sha256: string;
  comparability: string;
  population: string;
  context: string;
  sensitivity_basis: string;
  waves: Record<string, Wave>;
}

const titles: Record<HealthDomain, string> = {
  hospital: 'Hospital and ICU reports',
  testing: 'PCR testing',
  vaccination: 'Primary series vaccination',
  survey: 'Household Pulse symptoms',
  context: 'Age-adjusted survey context',
};
const hospitalOptions = {
  admissions: { label: 'Confirmed adult admissions', unit: 'Admissions per full week',
    key: 'confirmed_adult_admissions', field: 'weekly_total' },
  icu_patients: { label: 'Confirmed adult ICU patients', unit: 'Mean occupied beds in a full week',
    key: 'confirmed_adult_icu_patients', field: 'weekly_mean' },
  icu_occupied: { label: 'All-cause adult ICU utilization', unit: 'Percent of matched staffed adult ICU bed-days',
    key: 'all_cause_adult_icu_occupancy', field: 'weekly_percent' },
  icu_covid: { label: 'Confirmed or suspected COVID ICU utilization', unit: 'Percent of matched staffed adult ICU bed-days',
    key: 'confirmed_or_suspected_adult_icu_occupancy', field: 'weekly_percent' },
};

const option = (value: string, label: string, current: string) =>
  `<option value="${safe(value)}"${value === current ? ' selected' : ''}>${safe(label)}</option>`;
const control = (label: string, id: string, values: string) =>
  `<label for="${id}">${safe(label)}<select id="${id}">${values}</select></label>`;

function object(value: unknown): PublicRow {
  return value !== null && typeof value === 'object' ? value as PublicRow : {};
}
function numeric(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}
function measure(
  domain: SeriesDomain, report: Report, metric: keyof typeof hospitalOptions,
): { value: number | null; limits: PublicRow } {
  if (domain === 'hospital') {
    const definition = hospitalOptions[metric];
    const counts = object(report[definition.key]);
    return { value: numeric(counts[definition.field]), limits: counts };
  }
  if (domain === 'testing') {
    const { positive, negative, inconclusive } = report;
    return { value: numeric(report.weekly_positivity_percent), limits: {
      ...Object.fromEntries(Object.entries({ positive, negative, inconclusive }).flatMap(([label, item]) =>
        Object.entries(object(item)).map(([key, value]) => [`${label}_${key}`, value]))),
      determinate_results: report.determinate_results, negative_reported_counts: report.negative_result_corrections,
      cumulative_results: report.latest_cumulative_results,
    } };
  }
  const latest = object(report.latest_report);
  return { value: numeric(latest.provider_coverage_percent), limits: {
    ...latest, negative_updates_in_week: report.negative_completion_updates,
    completion_corrections: report.completion_corrections,
  } };
}

function header(state: State, hasBridge: boolean, hasContext: boolean): string {
  const choices = Object.entries(titles).filter(([key]) => (hasBridge || key !== 'survey') && (hasContext || key !== 'context'));
  return `<section class="page-heading measurement-heading"><div><div class="eyebrow">US PUBLIC HEALTH</div>
    <h1>What the reports measure</h1>
    <p>Explore archived hospital utilization, reported PCR results, vaccination, and survey estimates with their own dates and populations.</p></div>
    <div class="measurement-selector">${control('Series', 'health-domain',
      choices.map(([key, text]) => option(key, text, state.healthDomain)).join(''))}</div>
    </section>`;
}

function displayBridge(bridge: Bridge, state: State): Rendered {
  const wave = bridge.waves[state.pulseWave];
  const groups = { national: 'US adults', race_origin: 'Race and Hispanic origin', income: 'Household income' };
  const filtered = wave.rows.filter(row => row.group_kind === state.pulseGroup);
  const rows = filtered.map(row => ({
    group: row.group, symptom_measure: row.metric, percent: row.value, lower: row.lower, upper: row.upper,
    adult_denominator: row.denominator, complete_respondents: row.complete_respondents,
    provider_percent: row.provider_value, provider_difference_pp: row.provider_difference_pp,
    suppression: row.suppression_reason, weighted_eligible_adults: row.weighted_eligible_adults,
    weighted_item_missing_fraction: row.weighted_item_missing_fraction,
    item_missing_lower: row.item_missing_lower, item_missing_upper: row.item_missing_upper,
    se: row.se, kish_effective_n: row.kish_effective_n, wave: Number(state.pulseWave), phase: wave.wave.phase,
    recall_days: wave.wave.recall_days, income_reference_year: wave.wave.income_year,
    collection_start: wave.wave.start, collection_end: wave.wave.end, release_date: wave.wave.release,
    provider_weighted_household_response_percent: wave.wave.weighted_unit_response_percent,
    population: bridge.population, scientific_source: bridge.source, input_sha256: wave.source_sha256,
    comparator_sha256: bridge.aggregate_comparator_sha256, definition_sha256: bridge.definition_sha256,
  }));
  const waves = Object.entries(bridge.waves).map(([id, part]) =>
    option(id, `Week ${id} · ${part.wave.recall_days}-day recall`, state.pulseWave)).join('');
  return {
    rows,
    html: `<section class="panel prose measurement-panel"><h2>${titles.survey}</h2>
      <div class="health-filters">
      ${control('Survey wave', 'pulse-wave', waves)}
      ${control('Population group', 'pulse-group',
        Object.entries(groups).map(([key, label]) => option(key, label, state.pulseGroup)).join(''))}</div>
      <p>Collected ${safe(wave.wave.start)} to ${safe(wave.wave.end)}. Census recorded ${format(wave.wave.responses, 0)} responses and a ${format(wave.wave.weighted_unit_response_percent)}% weighted household response rate.</p>
      <p>${safe(bridge.comparability)}</p>
      <p class="micro">${safe(bridge.context)} Sampling intervals omit nonresponse bias. Negative provider differences mean the replayed estimate is lower.</p>
      ${table(rows)}<details><summary>National unit nonresponse scenarios</summary><p>${safe(bridge.sensitivity_basis)}</p>
      ${table(wave.selection_sensitivity, 12)}</details>
      <p><a href="https://www.cdc.gov/nchs/covid19/pulse/mental-health.htm">NCHS symptom definitions ↗</a></p></section>`,
  };
}

async function displaySurveillance(state: State, domain: SeriesDomain, signal: AbortSignal): Promise<Rendered> {
  const registry = await read<Surveillance>('state-surveillance', signal);
  const current = registry.jurisdictions.find(r => r.code === state.reportingState) ?? registry.jurisdictions[0];
  const reports = await read<StateReports>(`state-report-${current.code.toLowerCase()}`, signal);
  if (reports.code !== current.code || reports.source !== registry.source || reports.definition_sha256 !== registry.definition_sha256) {
    throw new Error('State reports and their registry refer to different snapshots');
  }
  const rule = registry.registry[domain];
  const firstYear = Number(rule.first.slice(0, 4));
  const lastYear = Number(rule.last.slice(0, 4));
  const year = Math.min(lastYear, Math.max(firstYear, state.reportingYear));
  const metric = (state.hospitalMetric in hospitalOptions ? state.hospitalMetric : 'admissions') as keyof typeof hospitalOptions;
  const label = domain === 'hospital' ? hospitalOptions[metric].label :
    domain === 'testing' ? 'PCR positivity' : 'Percent with a completed primary series';
  const unit = domain === 'hospital' ? hospitalOptions[metric].unit : 'Percent';
  const rawHash = registry.inputs[`v5_${domain}_rows`].sha256;
  const rows = reports.weeks[domain].filter(r => r.week_start.startsWith(String(year))).map(report => {
    const { value, limits } = measure(domain, report, metric);
    return { week_start: report.week_start, state: current.code, value, unit, reporting_days: report.reports, ...limits,
      metric: label, date_basis: rule.date_basis, geography_basis: rule.location_basis,
      source_sha256: rawHash, scientific_source: registry.source, definition_sha256: registry.definition_sha256 };
  });
  const coverage = rows.filter(r => r.value !== null).length;
  const curve = lineChart([{ name: current.label, color: '#31695a',
    points: rows.map(r => ({ x: Date.parse(r.week_start), y: r.value })) }], unit,
    undefined, undefined, [0, unit === 'Percent' || unit.startsWith('Percent of') ? 100 : Infinity], 'month');
  const years = Array.from({ length: lastYear - firstYear + 1 }, (_, i) => String(firstYear + i));
  const hospital = domain === 'hospital' ? control('Hospital measure', 'hospital-metric',
    Object.entries(hospitalOptions).map(([key, item]) => option(key, item.label, metric)).join('')) : '';
  const explanation = {
    hospital: 'Admissions are weekly counts. Confirmed adult ICU patient counts are weekly means. Utilization uses the provider’s paired numerator and denominator. Complete values require seven supported report dates.',
    testing: 'Positivity uses positive and negative results over a complete week. Inconclusive results are shown separately. A missing count or negative correction leaves positivity unavailable.',
    vaccination: 'Each week shows the latest available CDC snapshot. Signed changes compare consecutive source reports. Corrections and gaps remain visible in the data export.',
  };
  return { rows, html: `<section class="panel prose measurement-panel"><h2>${safe(titles[domain])}</h2>
    <div class="health-filters">
    ${control('Reporting jurisdiction', 'reporting-state',
      registry.jurisdictions.map(r => option(r.code, r.label, current.code)).join(''))}
    ${control('Year', 'reporting-year', years.map(y => option(y, y, String(year))).join(''))}
    ${hospital}</div>
    <p>${safe(rule.date_basis)} ${safe(rule.source_description)}</p>
    <h3>${safe(label)} in ${safe(current.label)}</h3>
    <p class="micro">${coverage} of ${rows.length} weeks have a value. ${safe(explanation[domain])}</p>
    ${curve}${table(rows, 54)}
    <p><a href="https://${safe(rule.host)}/d/${safe(rule.dataset)}">Primary source ↗</a></p>
    </section>` };
}

export async function healthView(
  index: Index, state: State, signal: AbortSignal, update: (patch: Partial<State>) => void,
): Promise<Rendered> {
  const hasBridge = Boolean(index.files['survey-bridge.json']);
  const hasContext = Boolean(index.files['social-context.json']);
  const unavailable = (state.healthDomain === 'survey' && !hasBridge) || (state.healthDomain === 'context' && !hasContext);
  const domain = unavailable ? 'hospital' : state.healthDomain;
  const result = domain === 'survey'
    ? displayBridge(await read<Bridge>('survey-bridge', signal), state)
    : domain === 'context' ? await socialContext(state, signal) : await displaySurveillance(state, domain, signal);
  return {
    html: header({ ...state, healthDomain: domain }, hasBridge, hasContext) + result.html,
    rows: result.rows,
    after(root) {
      const events: [string, (value: string) => Partial<State>][] = [
        ['health-domain', healthDomain => ({ healthDomain: healthDomain as HealthDomain })],
        ['reporting-state', reportingState => ({ reportingState })],
        ['reporting-year', value => ({ reportingYear: Number(value) })],
        ['hospital-metric', hospitalMetric => ({ hospitalMetric })],
        ['pulse-wave', pulseWave => ({ pulseWave })],
        ['pulse-group', pulseGroup => ({ pulseGroup })],
        ['context-group', contextGroup => ({ contextGroup })],
        ['context-outcome', contextOutcome => ({ contextOutcome })],
        ['context-sensitivity', value => ({ contextSensitivity: value === '1' })],
      ];
      for (const [id, patch] of events) {
        const input = root.querySelector<HTMLSelectElement>(`#${id}`);
        input?.addEventListener('change', () => update(patch(input.value)));
      }
    },
  };
}
