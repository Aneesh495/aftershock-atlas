import { lineChart } from './charts';
import { format, read, safe, table } from './data';
import type { Rendered } from './atlas-view';
import type { State } from './types';

interface Territory {
  source: string; definitions_sha256: string; evidence_limit: string;
  m49_reference: {url: string; sha256: string};
  transition_registry: {name:string; effective:string; predecessor:string; successors:Record<string,string>}[];
  rows: {
    region:string; metric:string; edition:string; era:string; present:number; reported_missing:number;
    absent_rows:number; future_values:number; territory_basis_unverified:number; transition_date:string;
  }[];
}
interface Mortality {
  source: string; definition_sha256: string; source_citation: string;
  origins: {calibration: string; evaluation: string};
  upstream: Record<string,{provider_snapshot_at:string;url:string;sha256:string}>;
  cohorts: {held_out:string[]; test:string[]; missing_outcomes:Record<string,string[]>};
  validation: {selected_ridge:string; selected_baseline:string};
  scores: {model:string;group:string;coverage:number;coverage_cluster_lower:number;coverage_cluster_upper:number;
    weeks:number;countries:number;revision_coverage:number|null;practical_coverage_met:boolean;
    mean_absolute_error_normalized:number;mean_interval_score_normalized:number;mean_width_normalized:number}[];
  scales: Record<string,number>;
  predictions: {region:string;week:number;model:string;standardized_forecast:number;standardized_lower:number;
    standardized_upper:number;standardized_observed:number;standardized_revision:number|null;covered:boolean}[];
}

function choice(id: string, label: string, items: [string,string][], current: string): string {
  return `<label for="${id}">${safe(label)}<select id="${id}">${items.map(([key,title]) =>
    `<option value="${safe(key)}"${key === current ? ' selected' : ''}>${safe(title)}</option>`).join('')}</select></label>`;
}

const names: Record<string,string> = {
  MNE:'Montenegro',SRB:'Serbia',CUW:'Curaçao',SXM:'Sint Maarten',
  BES:'Bonaire, Sint Eustatius and Saba',SSD:'South Sudan',SDN:'Sudan',
};
const metrics: Record<string,string> = {
  population:'Population',employment:'Employment',gdp:'Real GDP per capita',
  school:'Secondary enrollment',immunization:'DTP coverage',mortality:'Crude mortality',life_expectancy:'Life expectancy',
};
const modelLabel = (model:string) => ({
  seasonal_mean:'Same-week mean',seasonal_persistence:'Same week in 2018',damped_trend:'Damped trend',
}[model] ?? `Ridge, penalty ${model.replace('ridge_', '')}`);

export async function territoryAudit(state: State, signal: AbortSignal): Promise<Rendered> {
  const data = await read<Territory>('territory-audit',signal);
  const codes = data.transition_registry.flatMap(e => Object.keys(e.successors));
  const region = codes.includes(state.transitionRegion) ? state.transitionRegion : 'SDN';
  const transition = data.transition_registry.find(e => region in e.successors)!;
  const editions = [...new Set(data.rows.map(r => r.edition))];
  const edition = editions.includes(state.territoryEdition) ? state.territoryEdition : 'current';
  const rows = data.rows.filter(r => r.region === region && r.edition === edition).map(r => ({
    area: names[region], metric: metrics[r.metric], era:r.era.replaceAll('_',' '), available_cells: r.present,
    cells_needing_territory_proof: r.territory_basis_unverified, provider_blank_cells: r.reported_missing,
    absent_rows: r.absent_rows, future_reference_values: r.future_values,
    transition_date: r.transition_date, edition, predecessor_m49:transition.predecessor,
    successor_m49:transition.successors[region], m49_source_sha256:data.m49_reference.sha256,
    scientific_source:data.source, definition_sha256:data.definitions_sha256,
  }));
  return {rows,html:`<section class="panel prose measurement-panel"><h2>International territory changes</h2>
    <div class="health-filters">${choice('transition-region','Successor economy',codes.map(c=>[c,names[c]]),region)}
    ${choice('territory-edition','WDI vintage',editions.map(e=>[e,e==='current'?'Current frozen panel':e]),edition)}</div>
    <p>${safe(transition.name)} · ${safe(transition.effective)} · M49 ${safe(transition.predecessor)} to ${safe(transition.successors[region])}.</p>
    ${table(rows)}<p>${safe(data.evidence_limit)}</p>
    <p><a href="${safe(data.m49_reference.url)}" target="_blank" rel="noreferrer">UN statistical code changes ↗</a></p>
    </section>`};
}

export async function mortalityCalibration(state: State, signal: AbortSignal): Promise<Rendered> {
  const data = await read<Mortality>('mortality-calibration',signal);
  const region = data.cohorts.test.includes(state.mortalityForecastCountry) ? state.mortalityForecastCountry : data.cohorts.test[0];
  const selected = [data.validation.selected_baseline,data.validation.selected_ridge];
  const scale = data.scales[region];
  const predictions = data.predictions.filter(r => selected.includes(r.model) && r.region === region);
  const rows = predictions.map(r => ({
    country:region,week:r.week,model:modelLabel(r.model),deaths:r.standardized_observed*scale,
    forecast_deaths:r.standardized_forecast*scale,lower:r.standardized_lower*scale,upper:r.standardized_upper*scale,
    revised_deaths:r.standardized_revision===null?null:r.standardized_revision*scale,covered:r.covered,
    origin:data.origins.evaluation,held_out_country:data.cohorts.held_out.includes(region),
    target_archive_sha256:data.upstream.evaluation.sha256, feature_archive_sha256:data.upstream.features.sha256,
    calibration_archive_sha256:data.upstream.calibration.sha256, revision_archive_sha256:data.upstream.revision.sha256,
    scientific_source:data.source, definition_sha256:data.definition_sha256,
  }));
  const scoreRows = data.scores.filter(r => selected.includes(r.model) && ['all','held_out',region].includes(r.group)).map(r => ({
    model:modelLabel(r.model),group:r.group.replaceAll('_',' '),countries:r.countries,weeks:r.weeks,
    coverage_pct:100*r.coverage,cluster_lower_pct:100*r.coverage_cluster_lower,cluster_upper_pct:100*r.coverage_cluster_upper,
    normalized_mae:r.mean_absolute_error_normalized, normalized_interval_score:r.mean_interval_score_normalized,
    revised_coverage_pct:r.revision_coverage===null?null:100*r.revision_coverage,
  }));
  const plot = lineChart([
    {name:'Registered all-cause deaths',color:'#346359',points:rows.filter(r=>r.model===modelLabel(selected[0])).map(r=>({x:r.week,y:r.deaths}))},
    ...selected.map((m,i)=>({name:modelLabel(m),color:i===0?'#6b7797':'#ab632c',dashed:true,
      points:rows.filter(r=>r.model===modelLabel(m)).map(r=>({x:r.week,y:r.forecast_deaths,low:r.lower,high:r.upper}))})),
  ],'Deaths per source week');
  return {rows,html:`<section class="panel prose measurement-panel"><h2>Weekly mortality forecast calibration</h2>
    ${choice('mortality-forecast-country','Test country',data.cohorts.test.map(r=>[r,r]),region)}
    <p>Origin ${safe(data.origins.evaluation)}. ${data.cohorts.held_out.includes(region) ? 'This country was held out from model fitting, validation and calibration.' : 'This country contributed its earlier data to fitting and calibration.'}
    Across all countries, the test uses ${format(data.cohorts.test.length*52,0)} weekly observations.</p>
    ${plot}${table(scoreRows,12)}
    <p>Nominal intervals are 90%. The weekly plot shows counts. Scores normalize by the fixed 2015 weekly mean for each country. Cohort intervals resample countries.</p>
    <details><summary>Timing and source</summary>
    <p>Feature archive ${safe(data.upstream.features.provider_snapshot_at.slice(0,10))}. Calibration archive ${safe(data.upstream.calibration.provider_snapshot_at.slice(0,10))}. Test archive ${safe(data.upstream.evaluation.provider_snapshot_at.slice(0,10))}. Revised outcome archive ${safe(data.upstream.revision.provider_snapshot_at.slice(0,10))}.</p>
    <p><a href="${safe(data.source_citation)}" target="_blank" rel="noreferrer">World Mortality Dataset paper ↗</a></p></details>
    </section>`};
}
