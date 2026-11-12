import {country,format,read,safe,table} from './data';
import {lineChart} from './charts';
import type {Rendered} from './atlas-view';
import type {Index,State} from './types';

interface HistoryIndex {
  editions:string[];
  metrics:Record<string,{title:string;unit:string}>;
  availability_basis:string;
  limitations:string[];
  inventory:{edition:string;metric:string;nonmissing:number;countries:number;excluded_future_values:number;edition_available_at:string;unit:string}[];
}
interface Partition {
  edition:string;metric:string;unit:string;kind:string;source_sha256:string;edition_available_at:string;
  future_values_withheld:number;license:string;rows:{region:string;year:number;value:number|null}[];
}

export async function historyView(index:Index,state:State,signal:AbortSignal,update:(s:Partial<State>)=>void):Promise<Rendered> {
  const history=await read<HistoryIndex>('history-index',signal);
  const metric=Object.hasOwn(history.metrics,state.historyMetric)?state.historyMetric:'employment';
  const early=history.editions.includes(state.edition)?state.edition:history.editions[0];
  const late=history.editions.includes(state.revisionEdition)?state.revisionEdition:history.editions[history.editions.length-1];
  const [a,b,revisions,scores,sensitivity]=await Promise.all([
    read<Partition>(`hist_${early}_${metric}`,signal),read<Partition>(`hist_${late}_${metric}`,signal),
    read<{summaries:Record<string,unknown>[];trajectory_signs:Record<string,unknown>[]}>('history-revisions',signal),
    read<{completed_configurations:number;prediction_rows:number;learned_comparisons:Record<string,unknown>[];test_support:Record<string,unknown>[]}>('history-scores',signal),
    metric==='population'?Promise.resolve({rows:[] as Record<string,unknown>[]}):read<{rows:Record<string,unknown>[]}>(`history-sensitivity_${metric}`,signal)]);
  const regions=[state.primary,state.comparison].filter((r,i,all)=>all.indexOf(r)===i);
  const points=[a,b].flatMap((partition,editionIndex)=>regions.map((region,countryIndex)=>({
    name:`${country(index,region)} · ${partition.edition}`,color:countryIndex?'#bd724c':'#226354',dashed:editionIndex===0,
    points:partition.rows.filter(r=>r.region===region).map(r=>({x:Date.UTC(r.year,0,1),y:r.value}))
  })));
  const firstValues=new Map(a.rows.map(r=>[`${r.region}:${r.year}`,r.value]));
  const secondValues=new Map(b.rows.map(r=>[`${r.region}:${r.year}`,r.value]));
  const identities=[...new Set([...a.rows,...b.rows].filter(r=>regions.includes(r.region)).map(r=>`${r.region}:${r.year}`))].sort();
  const selected=identities.map(identity=>{
    const [region,year]=identity.split(':');
    const first=firstValues.get(identity)??null,second=secondValues.get(identity)??null;
    return {region,year:Number(year),metric,edition_a:early,edition_b:late,value_a:first,value_b:second,
      change_b_minus_a:first!==null&&second!==null?second-first:null,unit:a.unit,
      kind:a.kind,source_a_sha256:a.source_sha256,source_b_sha256:b.source_sha256,
      available_bound_a:a.edition_available_at,available_bound_b:b.edition_available_at,
      executable_source:index.source_commit,license:a.license,availability_basis:history.availability_basis};
  });
  const names=index.country_registry;
  const options=(current:string)=>names.map(r=>`<option value="${safe(r.id)}" ${r.id===current?'selected':''}>${safe(r.name)}</option>`).join('');
  const editionOptions=(current:string)=>history.editions.map(e=>`<option value="${e}" ${e===current?'selected':''}>${e.slice(0,4)}-${e.slice(4)}</option>`).join('');
  const matching=selected.filter(r=>r.change_b_minus_a!==null);
  const signs=revisions.trajectory_signs.filter(r=>r.metric===metric&&regions.includes(String(r.region)));
  const metricComparison=scores.learned_comparisons.filter(r=>r.metric===metric).map(r=>({baseline:r.validation_selected_baseline,crps_improvement_percent:Number(r.relative_crps_improvement)*100,cluster_lower_percent:Number(r.cluster_lower)*100,cluster_upper_percent:Number(r.cluster_upper)*100,countries:r.countries,practical_criterion_met:r.practical_5pct_and_positive_interval}));
  const support=scores.test_support.filter(r=>r.metric===metric);
  return {html:`<div class="page-heading compact"><div><div class="eyebrow">HISTORICAL EDITIONS / EXPLORATORY V3</div><h1>The past gets<br><em>revised too.</em></h1><p>Compare official archive editions. A reference year is not a publication date, and today’s value can differ from the earlier estimate.</p></div></div>
    <section class="panel"><div class="history-controls">
      <label>Historical outcome<select id="history-metric">${Object.entries(history.metrics).map(([id,m])=>`<option value="${id}" ${id===metric?'selected':''}>${safe(m.title)}</option>`).join('')}</select></label>
      <label>First edition<select id="history-early">${editionOptions(early)}</select></label>
      <label>Comparison edition<select id="history-late">${editionOptions(late)}</select></label>
      <label>First country<select id="history-primary">${options(state.primary)}</select></label>
      <label>Second country<select id="history-comparison">${options(state.comparison)}</select></label>
    </div><div class="panel-heading"><div><span class="eyebrow">${early} / ${late}</span><h2>${safe(history.metrics[metric].title)}</h2></div><span class="pill">${safe(a.unit)}</span></div>
    ${lineChart(points,a.unit)}<aside class="research-note"><strong>Edition month, not a witnessed original release day</strong><p>${safe(history.availability_basis)}. Dashed curves use the first selected edition. Gaps remain missing. Provider future-reference estimates are withheld: ${a.future_values_withheld} / ${b.future_values_withheld} cells in these global partitions.</p></aside>
    ${metric==='gdp'?'<p class="micro">Each edition is indexed to its own positive 2010 value. This removes constant scaling from a price-base change; it does not remove methodology or population revisions. Values are indices, not constant 2015 dollars.</p>':''}
    <p class="micro">Current country codes do not prove stable historical borders. The selected comparison contains ${matching.length} jointly available cells. Changes are the comparison edition minus the first edition.</p>
    <details><summary>Inspect selected editions and export provenance</summary>${table(selected,25)}</details></section>
    <section class="panel prose"><span class="eyebrow">REGISTERED REVISION STUDY / 201811 VERSUS 202312</span><h2>Revisions are part of the measurement.</h2>${table(revisions.summaries.filter(r=>r.metric===metric),10)}${signs.length?table(signs,10):'<p>No jointly eligible 2010-2017 direction comparison for these countries.</p>'}<p>These are exact contrasts in a frozen panel, not independent sampled observations. Revisions can reflect precision, definition changes and backcasts.</p></section>
    <section class="panel prose"><span class="eyebrow">ORIGIN-SPECIFIC FORECASTS</span><h2>${scores.completed_configurations} separate historical configurations</h2><p>Models fit the 201811 edition. Each later forecast uses its designated archive, with four lags ending two years before its target. The three network seeds begin from new random parameters. No current-vintage value fills an unavailable historical feature.</p><p>Calendar test outcomes were inspected in earlier protocols, so these comparisons are exploratory. Positive improvement percentages mean lower CRPS than the validation-selected baseline. GDP scores use log1p of a within-edition index and cannot be pooled with the earlier dollar-target scores.</p>
    ${metric==='population'?'<p>Population is a denominator series and is not a forecast target in this experiment.</p>':`${table(metricComparison,6)}<h3>Eligible outcomes by test year</h3>${table(support,10)}<p class="micro">Zero support is unavailable evidence, not a successful forecast. Historical publication lags can remove entire outcome-year cells.</p>`}</section>
    <section class="panel prose"><h2>Inspect feature-vintage sensitivity</h2><p>These rows compare the actual feature endpoint with the initial and current editions. Values use ${metric==='gdp'?'log1p of the within-edition GDP index':safe(a.unit)}. They are diagnostics. Current values do not replace missing historical inputs.</p>${table(sensitivity.rows.filter(r=>regions.includes(String(r.region))),20)}</section><section class="panel prose"><h2>Follow both upstream identities</h2><p>${early}: <code>${safe(a.source_sha256)}</code></p><p>${late}: <code>${safe(b.source_sha256)}</code></p><p><a href="https://datatopics.worldbank.org/world-development-indicators/wdi-archives.html" target="_blank" rel="noreferrer">Official WDI archive catalogue and metadata caveat ↗</a></p></section>`,rows:selected,after:root=>{
      const bindings:{id:string;key:keyof State}[]=[{id:'history-metric',key:'historyMetric'},{id:'history-early',key:'edition'},
        {id:'history-late',key:'revisionEdition'},{id:'history-primary',key:'primary'},{id:'history-comparison',key:'comparison'}];
      for(const {id,key} of bindings)root.querySelector<HTMLSelectElement>(`#${id}`)!.onchange=e=>update({[key]:(e.target as HTMLSelectElement).value});
    }};
}
