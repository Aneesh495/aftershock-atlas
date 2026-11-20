import { lineChart } from './charts';
import { format, read, safe, table } from './data';
import type { Rendered } from './atlas-view';
import type { Index, State } from './types';

interface Revision {
  quarter: string; first_release: string | null; qna_release: string | null;
  first_growth_pct: number | null; qna_growth_pct: number | null; revision_pp: number | null;
  substantive_revision: boolean | null; strict_sign_change: boolean | null;
}
interface Release {
  release_id: string; kind: string; quarter: string; release_day: string; capture_at: string;
  terminal_label: string; terminal_column: number; has_notice: boolean;
  workbook_url: string; workbook_sha256: string; bulletin_url: string; bulletin_sha256: string;
}
interface Origin {
  anchor: string; origin: string; available_day: string | null; available_quarter: string | null;
  available_release: string | null; available_growth_pct: number | null;
}
interface GDP {
  source: string; series: string; availability_scope: string; definition_sha256: string;
  editions: Release[]; revisions: Revision[]; as_of: Origin[];
}
interface Geography {
  source: string; inputs_sha256: string; population_day: string; notice_date: string;
  tiger_boundary_date: string; tiger_release_date: string; resident_population: number;
  old_counties: {geoid: string; name: string; residents: number; county_only_counts_ambiguous: boolean}[];
  planning_regions: {geoid: string; name: string}[];
  overlaps: {old_county: string; planning_region: string; residents: number;
    municipalities: number; share_of_old_county: number; share_of_planning_region: number}[];
  limitations: string; acs_vintage: string;
}

function select(label: string, id: string, choices: [string, string][], selected: string): string {
  return `<label for="${id}">${safe(label)}<select id="${id}">${choices.map(([value,text]) =>
    `<option value="${safe(value)}"${value === selected ? ' selected' : ''}>${safe(text)}</option>`).join('')}</select></label>`;
}

const quarterDate = (q: string) => Date.UTC(Number(q.slice(0,4)), (Number(q.slice(-1)) - 1) * 3, 1);

function displayGDP(data: GDP, state: State): Rendered {
  const quarter = data.revisions.some(r => r.quarter === state.gdpQuarter) ? state.gdpQuarter : '2022Q2';
  const selected = data.editions.filter(r => r.quarter === quarter);
  const chart = lineChart([
    { name: 'First estimate', color: '#346359', points: data.revisions.map(r => ({x: quarterDate(r.quarter), y: r.first_growth_pct})) },
    { name: 'Quarterly national accounts', color: '#ab632c', dashed: true, points: data.revisions.map(r => ({x: quarterDate(r.quarter), y: r.qna_growth_pct})) },
  ], 'Quarter-on-quarter growth (%)', quarterDate(quarter), 0);
  const rows = data.revisions.map(r => {
    const first = data.editions.find(e => e.quarter === r.quarter && e.kind === 'first');
    const qna = data.editions.find(e => e.quarter === r.quarter && e.kind === 'qna');
    return {...r, first_sha256: first?.workbook_sha256, revised_sha256: qna?.workbook_sha256,
      first_bulletin: first?.bulletin_url, revised_bulletin: qna?.bulletin_url,
      scientific_source: data.source, definition_sha256: data.definition_sha256};
  });
  const origins = data.as_of.filter(r => selected.some(edition => edition.release_id === r.anchor)).map(r => ({
    origin: r.origin, last_available_release: r.available_day, available_reference_quarter: r.available_quarter,
    available_growth_pct: r.available_growth_pct, available_edition: r.available_release,
  }));
  return {rows, html: `<section class="panel prose measurement-panel"><h2>UK GDP as released</h2>
    <p>${safe(data.series)}. Each growth estimate uses two quarters from the same edition.</p>
    ${select('Inspect a reference quarter', 'gdp-quarter', data.revisions.map(r => [r.quarter,r.quarter]),quarter)}
    ${chart}${table(rows)}
    </section><section class="panel prose"><h2>What was available on each release day</h2>
    <p>${safe(data.availability_scope)}</p>${table(origins,4)}
    ${selected.map(e => `<details><summary>${safe(e.release_day)} · ${e.kind === 'first' ? 'First estimate' : 'Quarterly national accounts'}</summary>
      <p>Workbook column ${format(e.terminal_column,0)} · ${safe(e.terminal_label)}.</p>
      <p>Archived copy captured ${safe(e.capture_at.split('T')[0])}. ${e.has_notice ? 'The provider attached an update notice to this bulletin.' : ''}</p>
      <p><a href="${safe(e.bulletin_url)}" target="_blank" rel="noreferrer">Original ONS bulletin ↗</a>
      · <a href="${safe(e.workbook_url)}" target="_blank" rel="noreferrer">Archived workbook ↗</a></p></details>`).join('')}
    </section>`};
}

function displayConnecticut(data: Geography, state: State): Rendered {
  const county = data.old_counties.find(r => r.geoid === state.ctCounty) ?? data.old_counties[0];
  const rows = data.overlaps.filter(r => r.old_county === county.geoid).map(r => ({
    old_county: county.name, planning_region: data.planning_regions.find(n => n.geoid === r.planning_region)?.name,
    residents: r.residents, municipalities: r.municipalities,
    percent_of_old_county: r.share_of_old_county * 100, percent_of_planning_region: r.share_of_planning_region * 100,
    population_day: data.population_day, county_only_event_assignment_ambiguous: county.county_only_counts_ambiguous,
    old_geoid: r.old_county, new_geoid: r.planning_region,
    scientific_source: data.source, input_manifest_sha256: data.inputs_sha256,
  }));
  return {rows, html: `<section class="panel prose measurement-panel"><h2>Connecticut resident crosswalk</h2>
    <p>${format(data.resident_population,0)} people on ${safe(data.population_day)} conserved across the eight historical counties and nine planning regions.</p>
    ${select('Historical county', 'ct-county', data.old_counties.map(r => [r.geoid, r.name]), county.geoid)}
    <p>${safe(county.name)} had ${format(county.residents,0)} residents. ${county.county_only_counts_ambiguous ?
      'It splits across planning regions, so its county-only totals cannot be transferred exactly.' :
      'All of its resident population maps to a single planning region.'}</p>
    ${table(rows)}<p>${safe(data.limitations)}</p>
    <details><summary>Geography dates and source</summary><p>Notice ${safe(data.notice_date)}. TIGER boundary date ${safe(data.tiger_boundary_date)}. Release ${safe(data.tiger_release_date)}.</p>
    <p>ACS adoption ${safe(data.acs_vintage)}.</p>
    <p><a href="https://www2.census.gov/geo/docs/reference/ct_change/ct_cou_to_cousub_crosswalk.txt" target="_blank" rel="noreferrer">Census relationship file ↗</a>
    · <a href="https://www2.census.gov/adrm/PDB/2024/2024_PDB_Documentation.pdf" target="_blank" rel="noreferrer">Planning-region benchmarks ↗</a></p></details>
    </section>`};
}

export async function chronologyView(
  index: Index, state: State, signal: AbortSignal, update: (patch: Partial<State>) => void,
): Promise<Rendered> {
  const sections: [string, string][] = [];
  if (index.files['uk-vintages.json']) sections.push(['gdp', 'UK GDP revisions']);
  if (index.files['ct-crosswalk.json']) sections.push(['ct', 'Connecticut planning regions']);
  const section = sections.some(([id]) => id === state.chronologySection) ? state.chronologySection : sections[0][0];
  const content = section === 'gdp'
    ? displayGDP(await read<GDP>('uk-vintages', signal), state)
    : displayConnecticut(await read<Geography>('ct-crosswalk', signal), state);
  return {rows: content.rows, html: `<section class="page-heading measurement-heading"><div>
    <h1>Release dates and boundaries</h1>
    <p>Inspect what changed between releases and how resident populations map to new boundaries.</p></div>
    <div class="measurement-selector">${select('Series', 'chronology-section', sections, section)}</div>
    </section>${content.html}`, after(root) {
    const inputs: [string, 'chronologySection' | 'gdpQuarter' | 'ctCounty'][] = [
      ['chronology-section','chronologySection'], ['gdp-quarter','gdpQuarter'], ['ct-county','ctCounty'],
    ];
    for (const [id, key] of inputs) {
      const input = root.querySelector<HTMLSelectElement>(`#${id}`);
      input?.addEventListener('change', () => update({[key]: input.value}));
    }
  }};
}
