import { lineChart } from './charts';
import { format, read, safe, table } from './data';
import type { Rendered } from './atlas-view';
import type { State } from './types';

type Row = Record<string, unknown>;
type HoursEntry = { geo: string; sector: string; quarter: string; hours: number | null; flags: string; cell: number };
type SectorComparison = Row & {
  geo: string; sector: string; sector_label: string; baseline_quarter: string; target_quarter: string;
};
interface SectorData {
  source: string; source_sha256: string; definition_sha256: string; unit: string; population: string;
  observations: HoursEntry[]; comparisons: SectorComparison[];
  summary: (Row & { sector: string; target_quarter: string })[];
}
interface OccupationData {
  source: string; definition_sha256: string; private_inputs_sha256: string; population: string;
  recall_days: number; limitations: string[];
  periods: Record<string, { rows: Row[]; telework_comparator: { value: number; url: string; difference_pp: number };
    source_sha256: { basic: string; extract: string } }>;
  comparisons: (Row & { group_kind: string; group_code: string; outcome: string })[];
}
type SelectionUpdate = (patch: Partial<State>) => void;

const choice = (code: string, title: string, current: string) =>
  `<option value="${safe(code)}"${code === current ? ' selected' : ''}>${safe(title)}</option>`;

function bind(root: HTMLElement, id: string, update: (value: string) => void): void {
  const input = root.querySelector<HTMLSelectElement>(`#${id}`);
  input?.addEventListener('change', () => update(input.value));
}

export async function sectorView(state: State, signal: AbortSignal, update: SelectionUpdate): Promise<Rendered> {
  const data = await read<SectorData>('sector-hours', signal);
  const labels = new Intl.DisplayNames(['en'], { type: 'region' });
  const country = (code: string) => labels.of(code === 'EL' ? 'GR' : code) ?? code;
  const sectors = [...new Map(data.comparisons.map(r => [r.sector, r.sector_label])).entries()];
  const selected = sectors.some(([code]) => code === state.laborSector) ? state.laborSector : 'TOTAL';
  const countries = [...new Set(data.comparisons.map(r => r.geo))].sort((a, b) => country(a).localeCompare(country(b)));
  const geo = countries.includes(state.laborCountry) ? state.laborCountry : 'DE';
  const bounds = data.comparisons.filter(r => r.sector === selected && r.geo === geo);
  const rows = data.comparisons.filter(r => r.sector === selected && r.target_quarter === state.laborWindow).map(r => ({
    country: country(r.geo), baseline_quarter: r.baseline_quarter, target_quarter: r.target_quarter,
    baseline_hours: r.baseline_hours, target_hours: r.target_hours, change_hours: r.change_hours,
    total_change_hours: r.total_activity_change_hours, sector_minus_total_hours: r.sector_minus_total_change_hours,
    flags: r.window_flags, missing_quarters: r.missing_quarters, country_code: r.geo, sector: r.sector,
    sector_label: r.sector_label, baseline_cell: r.baseline_cell, target_cell: r.target_cell,
    unfit_flags: r.unfit_flags, both_unflagged: r.both_unflagged, unit: data.unit, population: data.population,
    scientific_source: data.source, source_sha256: data.source_sha256, definition_sha256: data.definition_sha256,
  }));
  const selectedLabel = sectors.find(([key]) => key === selected)![1];
  const series = [{ code: selected, label: selectedLabel, color: '#31695a' }];
  if (selected !== 'TOTAL') series.push({ code: 'TOTAL', label: 'All activities', color: '#bd724c' });
  const chart = lineChart(series.map(s => ({ name: s.label, color: s.color,
    points: data.observations.filter(r => r.geo === geo && r.sector === s.code).map(r => {
      const year = Number(r.quarter.slice(0, 4)), quarter = Number(r.quarter.slice(-1));
      return { x: Date.UTC(year, (quarter - 1) * 3, 1), y: r.flags.match(/[ucdnzf]/) ? null : r.hours,
        breakBefore: r.flags.includes('b') || r.quarter === '2021-Q1' };
    }) })), 'Actual hours in the main job per reference week');
  const notes = bounds.map(r => ({
    baseline_quarter: r.baseline_quarter, target_quarter: r.target_quarter,
    change_hours: r.change_hours, total_change_hours: r.total_activity_change_hours,
    flags: r.window_flags, missing_quarters: r.missing_quarters,
  }));
  return {
    rows,
    html: `<section class="panel prose measurement-panel"><h2>Quarterly sector hours</h2>
      <div class="health-filters"><label for="labor-sector">Economic activity<select id="labor-sector">
      ${sectors.map(([code, label]) => choice(code, label, selected)).join('')}</select></label>
      <label for="labor-country">Country in chart<select id="labor-country">
      ${countries.map(code => choice(code, country(code), geo)).join('')}</select></label>
      <label for="labor-window">Quarter comparison<select id="labor-window">
      ${choice('2020-Q2', '2019 Q2 to 2020 Q2', state.laborWindow)}
      ${choice('2023-Q2', '2022 Q2 to 2023 Q2', state.laborWindow)}</select></label></div>
      <p>${safe(data.population)}. People absent for the reference week are outside the denominator.</p>
      <h3>${safe(country(geo))} · ${safe(selectedLabel)}</h3>
      <p class="micro">The line breaks at the 2021 EU-LFS redesign and reported series breaks. Unreliable cells are withheld from the chart.</p>
      ${chart}${table(notes)}
      <h3>Matched quarter comparisons across the EU</h3>
      <p class="micro">Flagged discontinuities can leave a quarter pair unavailable even when both endpoint values are published.</p>
      ${table(data.summary.filter(r => r.sector === selected && r.target_quarter === state.laborWindow), 1)}
      ${table(rows, 27)}<p><a href="https://ec.europa.eu/eurostat/databrowser/view/lfsq_ewhan2/default/table">Eurostat sector hours ↗</a></p>
      </section>`,
    after(root) {
      bind(root, 'labor-sector', laborSector => update({ laborSector }));
      bind(root, 'labor-country', laborCountry => update({ laborCountry }));
      bind(root, 'labor-window', laborWindow => update({ laborWindow }));
    },
  };
}

export async function occupationView(state: State, signal: AbortSignal, update: SelectionUpdate): Promise<Rendered> {
  const data = await read<OccupationData>('occupational-work', signal);
  const measures = { telework: 'Teleworked because of the pandemic',
    unable_to_work: 'Unable to work due to closures or lost business' };
  const groups = { occupation: 'Main-job occupation', industry: 'Main-job industry', national: 'All employed civilians' };
  const selected = data.comparisons.filter(r => r.group_kind === state.occupationGroup && r.outcome === state.occupationOutcome);
  const rows = selected.map(r => {
    const supplemental: Row = {};
    for (const [name, month] of Object.entries(data.periods)) {
      const record = month.rows.find(m => m.group_kind === r.group_kind && m.group_code === r.group_code && m.outcome === r.outcome);
      const year = name.slice(0, 4);
      Object.assign(supplemental, {
        [`denominator_${year}`]: record?.adult_worker_denominator,
        [`complete_respondents_${year}`]: record?.complete_respondents,
        [`missing_lower_${year}`]: record?.missing_lower_percent,
        [`missing_upper_${year}`]: record?.missing_upper_percent,
        [`suppression_${year}`]: record?.suppression_reason,
        [`basic_sha256_${year}`]: month.source_sha256.basic,
        [`extract_sha256_${year}`]: month.source_sha256.extract,
      });
    }
    return { group: r.group, september_2020_percent: r.september_2020_percent,
      september_2021_percent: r.september_2021_percent, september_2022_percent: r.september_2022_percent,
      change_pp: r.change_pp, at_least_five_points: r.meets_descriptive_change_threshold,
      outcome: r.outcome, group_code: r.group_code, group_kind: r.group_kind, ...supplemental,
      recall_days: data.recall_days, scientific_source: data.source, definition_sha256: data.definition_sha256,
      private_inputs_sha256: data.private_inputs_sha256 };
  });
  const anchors = Object.entries(data.periods).map(([month, row]) => ({
    month, published_telework_percent: row.telework_comparator.value, difference_pp: row.telework_comparator.difference_pp,
  }));
  return {
    rows,
    html: `<section class="panel prose measurement-panel"><h2>US occupational disruptions</h2>
      <div class="health-filters"><label for="occupation-group">Classification<select id="occupation-group">
      ${Object.entries(groups).map(([code, label]) => choice(code, label, state.occupationGroup)).join('')}</select></label>
      <label for="occupation-outcome">Survey measure<select id="occupation-outcome">
      ${Object.entries(measures).map(([code, label]) => choice(code, label, state.occupationOutcome)).join('')}</select></label></div>
      <p>${safe(data.population)}. Both questions cover the last four weeks.</p>
      <p class="micro">Five percentage points is the prespecified descriptive threshold. Complete-response group denominators are in CSV. The estimates omit design sampling intervals.</p>
      ${table(rows, 13)}<details><summary>Check the national published telework comparison</summary>
      ${table(anchors, 3)}<p>Maximum absolute difference ${format(Math.max(...anchors.map(r => Math.abs(r.difference_pp))), 3)} points.</p>
      </details><p><a href="https://www2.census.gov/programs-surveys/cps/techdocs/Covid19_TechDoc.pdf">Census supplement method ↗</a></p>
      </section>`,
    after(root) {
      bind(root, 'occupation-group', occupationGroup => update({ occupationGroup }));
      bind(root, 'occupation-outcome', occupationOutcome => update({ occupationOutcome }));
    },
  };
}
