import { country, read, safe, table } from './data';
import type { Rendered } from './atlas-view';
import type { Index, State } from './types';

type RecordRow = Record<string, unknown>;
type Estimate = { value: number | null; se: number | null; lower: number | null;
  upper: number | null; source_cell: string; se_cell: string; missing: string | null };
interface LearningRow {
  system: string; subject: string; caution: string | null; atlas_region: string | null;
  source_sha256: string; sheet: string; cycles: Record<string, Estimate>;
  '2015_to_2018': number | null; '2018_to_2022_released': Estimate;
  p_value: number | null; q_value: number | null;
}
interface Measurement {
  protocol: string;
  source: string;
  definition_sha256: string;
  learning: { rows: LearningRow[]; summary: RecordRow[]; change_se_basis: string };
  hours: { rows: RecordRow[]; summary: RecordRow[]; limitation: string; gdp_panel_sha256: string };
  remote_instruction: { rows: RecordRow[]; population: string; limitation: string };
}

type StudySection = 'learning' | 'instruction' | 'hours';
const sections = {
  learning: 'Learning assessments',
  instruction: 'US remote instruction',
  hours: 'Annual hours and GDP',
};
const subjects = ['mathematics', 'reading', 'science'];
const option = (value: string, label: string, selection: string) =>
  `<option value="${safe(value)}"${value === selection ? ' selected' : ''}>${safe(label)}</option>`;

function assessmentExport(row: LearningRow): RecordRow {
  const trend = row['2018_to_2022_released'];
  return {
    education_system: row.system, subject: row.subject, caution: row.caution,
    score_2015: row.cycles['2015'].value, score_2018: row.cycles['2018'].value,
    score_2022: row.cycles['2022'].value, change_2015_to_2018: row['2015_to_2018'],
    change_2018_to_2022: trend.value, lower: trend.lower, upper: trend.upper,
    trend_standard_error: trend.se, unit: 'PISA scale points', p_value: row.p_value,
    q_value: row.q_value, missing: trend.missing, atlas_region: row.atlas_region,
    source_sheet: row.sheet, change_cell: trend.source_cell, se_cell: trend.se_cell,
    source_sha256: row.source_sha256,
  };
}

export async function measurementView(
  index: Index, state: State, signal: AbortSignal, update: (patch: Partial<State>) => void,
): Promise<Rendered> {
  const data = await read<Measurement>('measurement-v4', signal);
  const section = state.measurementSection as StudySection;
  const choices = Object.entries(sections).map(([key, text]) => option(key, text, section)).join('');
  let rows: RecordRow[] = [];
  let content = '';
  if (section === 'learning') {
    const subject = state.learningSubject;
    rows = data.learning.rows.filter(r => r.subject === subject).map(assessmentExport);
    content = `<section class="panel prose measurement-panel"><h2>Learning assessments</h2>
      <label class="filter-label" for="learning-subject">Subject</label>
      <select id="learning-subject">${subjects.map(s => option(s, s, subject)).join('')}</select>
      <p>OECD PISA scores describe assessment-eligible students. Published 2018 to 2022 change errors include scale-linking uncertainty. The earlier difference spans three years.</p>
      ${table(data.learning.summary.filter(r => r.subject === subject), 2)}
      <h3>Education systems and published changes</h3>
      <p class="micro">Sampling and linkage cautions are retained. The cautious sensitivity includes all systems with a published change.</p>
      ${table(rows, 81)}</section>`;
  } else if (section === 'instruction') {
    const groups = [...new Set(data.remote_instruction.rows.map(r => String(r.group)))];
    const group = groups.includes(state.instructionGroup) ? state.instructionGroup : groups[0];
    rows = data.remote_instruction.rows.filter(r => r.group === group).map(r => ({
      measure: r.label, group: r.group, value: r.value, lower: r.lower, upper: r.upper,
      unit: r.unit, complete_respondents: r.complete_respondents, weighted_adult_denominator: r.denominator,
      item_missing_fraction: r.weighted_item_missing_fraction, suppression: r.suppression_reason,
      population: r.population, item_missing_lower: r.item_missing_lower, item_missing_upper: r.item_missing_upper,
      source_sha256: r.source_hash,
    }));
    content = `<section class="panel prose measurement-panel"><h2>US remote instruction</h2>
      <label class="filter-label" for="instruction-group">Adult demographic group</label>
      <select id="instruction-group">${groups.map(g => option(g, g, group)).join('')}</select>
      <p>${safe(data.remote_instruction.population)}. April 23 to May 5, 2020.</p>
      <p class="micro">${safe(data.remote_instruction.limitation)}</p>${table(rows, 11)}</section>`;
  } else {
    const year = state.hoursYear;
    rows = data.hours.rows.filter(r => r.target_year === year).map(r => ({
      country: country(index, String(r.region)), target_year: year, hours_index: r.hours_index,
      gdp_per_person_index: r.gdp_per_person_index, baseline_hours: r.baseline_hours,
      target_hours: r.target_hours, within_country_hours_change: r.change_hours,
      comparison_exclusions: Array.isArray(r.comparison_exclusions) ? r.comparison_exclusions.join('; ') : '',
      unit: r.unit, cohort: r.cohort, source_sha256: r.source_sha256, gdp_panel_sha256: data.hours.gdp_panel_sha256,
      region: r.region,
    }));
    content = `<section class="panel prose measurement-panel"><h2>Annual hours and GDP</h2>
      <label class="filter-label" for="hours-year">Comparison year</label>
      <select id="hours-year">${[2020, 2022].map(y => option(String(y), String(y), String(year))).join('')}</select>
      <p>Each country uses 2019 = 100. Hours describe employed people. GDP describes output per resident.</p>
      <p class="micro">${safe(data.hours.limitation)}</p>
      ${table(data.hours.summary.filter(r => r.year === year), 1)}
      <h3>Matched country series</h3>${table(rows, 45)}</section>`;
  }
  const provenance = { scientific_source: data.source, protocol: data.protocol, definition_sha256: data.definition_sha256 };
  return {
    html: `<section class="page-heading measurement-heading"><div><div class="eyebrow">WORK AND EDUCATION</div>
      <h1>Hours worked, instruction and learning</h1>
      <p>Compare actual annual work hours and real GDP within countries. Explore measured learning and reported instruction in their own populations.</p></div>
      <div class="measurement-selector"><label class="filter-label" for="measurement-section">Measure</label>
      <select id="measurement-section">${choices}</select></div>
    </section>${content}`,
    rows: rows.map(r => ({ ...r, ...provenance })),
    after(root) {
      const selectors: [string, (value: string) => Partial<State>][] = [
        ['measurement-section', measurementSection => ({ measurementSection })],
        ['learning-subject', learningSubject => ({ learningSubject })],
        ['instruction-group', instructionGroup => ({ instructionGroup })],
        ['hours-year', value => ({ hoursYear: Number(value) })],
      ];
      for (const [id, patch] of selectors) {
        const select = root.querySelector<HTMLSelectElement>(`#${id}`);
        select?.addEventListener('change', () => update(patch(select.value)));
      }
    },
  };
}
