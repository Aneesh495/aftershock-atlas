import { format, read, safe, table } from './data';
import type { Rendered } from './atlas-view';
import type { State } from './types';

interface Estimate {
  suppressed: boolean; adjusted_pct: number | null; crude_pct: number | null;
  lower: number | null; upper: number | null; se_pp: number | null;
  complete_adults: number | null; weighted_complete: number | null;
  item_missing_pct: number | null; item_missing_lower: number | null; item_missing_upper: number | null;
}
interface Group {
  group_kind: string; group: string; metric: string;
  primary: Estimate; birthday_sensitivity: Estimate;
}
interface Contrast {
  group_kind: string; group: string; metric: string; reference: string;
  estimates: {mode: string; difference_pp: number | null; lower: number | null; upper: number | null; q: number | null}[];
}
interface Survey {
  source: string; config_sha256: string; metric_labels: Record<string,string>;
  age_standard: Record<string,number>; age_sensitivity: string; comparison_scope: string;
  nonresponse_scope: string;
  waves: Record<string, {
    wave: { start: string; end: string; recall_days: number; income_year: number; weighted_unit_response_percent: number };
    source_sha256: string; rows: Group[]; contrasts: Contrast[];
    food_adults_18_plus_benchmark: { survey_pct: number; provider_pct: number; within_tolerance: boolean };
  }>;
}

function select(id: string, label: string, items: [string,string][], current: string): string {
  return `<label for="${id}">${safe(label)}<select id="${id}">${items.map(([key,label]) =>
    `<option value="${safe(key)}"${key === current ? ' selected' : ''}>${safe(label)}</option>`).join('')}</select></label>`;
}

export async function socialContext(state: State, signal: AbortSignal): Promise<Rendered> {
  const data = await read<Survey>('social-context', signal);
  const wave = data.waves[state.pulseWave];
  const metric = state.contextOutcome;
  const mode = state.contextSensitivity ? 'birthday_sensitivity' : 'primary';
  const groups = wave.rows.filter(row => row.group_kind === state.contextGroup && row.metric === metric);
  const contrasts = wave.contrasts.filter(row => row.group_kind === state.contextGroup && row.metric === metric);
  const rows = groups.map(row => {
    const selected = row[mode];
    const contrast = contrasts.find(x => x.group === row.group);
    const delta = contrast?.estimates.find(x => x.mode === mode);
    return {
      group: row.group, adjusted_percent: selected.adjusted_pct, lower: selected.lower, upper: selected.upper,
      crude_percent: selected.crude_pct, suppressed: selected.suppressed,
      complete_adults: selected.complete_adults, weighted_complete_adults: selected.weighted_complete,
      difference_pp: delta?.difference_pp ?? null, reference: contrast?.reference ?? null,
      difference_lower: delta?.lower ?? null, difference_upper: delta?.upper ?? null, fdr_q: delta?.q ?? null,
      adjusted_se_pp: selected.se_pp, item_missing_pct: selected.item_missing_pct,
      item_missing_lower: selected.item_missing_lower, item_missing_upper: selected.item_missing_upper,
      age_standard: data.age_standard, age_mode: mode, outcome: data.metric_labels[metric],
      week: state.pulseWave, start: wave.wave.start, end: wave.wave.end,
      symptom_recall_days: wave.wave.recall_days, income_reference_year: wave.wave.income_year,
      weighted_household_response_percent: wave.wave.weighted_unit_response_percent,
      scientific_source: data.source, input_sha256: wave.source_sha256, definition_sha256: data.config_sha256,
    };
  });
  const plot = rows.some(r => r.adjusted_percent !== null) ? `<ul class="context-bars">${rows.map(row =>
    `<li><span>${safe(row.group)}</span><div aria-hidden="true"><i style="width:${row.adjusted_percent ?? 0}%"></i></div>
      <strong>${row.adjusted_percent === null ? 'Suppressed' : `${format(row.adjusted_percent)}%`}</strong></li>`).join('')}</ul>` : '';
  return {rows, html: `<section class="panel prose measurement-panel"><h2>Survey context by age, tenure and income</h2>
    <div class="health-filters">
    ${select('pulse-wave','Survey week', [['33','Week 33'],['34','Week 34']],state.pulseWave)}
    ${select('context-group','Population group',[['national','US adults'],['race_origin','Race and Hispanic origin'],['tenure','Housing tenure'],['income','Household income']],state.contextGroup)}
    ${select('context-outcome','Outcome',[['food_insufficiency','Food insufficiency'],['mental_health_screen','Anxiety or depression screen']],metric)}
    <label for="context-sensitivity">Age calculation<select id="context-sensitivity">
      <option value="0"${!state.contextSensitivity ? ' selected' : ''}>Age at year end</option><option value="1"${state.contextSensitivity ? ' selected' : ''}>Exclude boundary birth years</option></select></label>
    </div>
    <p>${safe(data.metric_labels[metric])}. Age 25 and older. Collected ${safe(wave.wave.start)} to ${safe(wave.wave.end)}.</p>
    ${plot}${table(rows)}
    <details><summary>Survey definitions and benchmark</summary>
      <p>${safe(data.comparison_scope)}</p><p>${safe(data.age_sensitivity)}</p><p>${safe(data.nonresponse_scope)}</p>
      <p>The unrestricted age 18+ food comparison is ${format(wave.food_adults_18_plus_benchmark.survey_pct,3)}% in the reanalysis and ${format(wave.food_adults_18_plus_benchmark.provider_pct,3)}% in the official table.</p>
      <p><a href="https://www.census.gov/data/tables/2021/demo/hhp/hhp${safe(state.pulseWave)}.html" target="_blank" rel="noreferrer">Census wave tables ↗</a>
      · <a href="https://www.cdc.gov/nchs/hus/sources-definitions/age-adjustment.htm" target="_blank" rel="noreferrer">NCHS age standard ↗</a></p>
    </details>
    </section>`};
}
