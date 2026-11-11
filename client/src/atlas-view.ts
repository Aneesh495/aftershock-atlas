import {country,format,points,read,safe,table} from './data';
import {lineChart} from './charts';
import {drawMap} from './map';
import type {Index,Point,Scenario,Series,State} from './types';

export interface Rendered {html:string;rows:Record<string,unknown>[];after?:(root:HTMLElement)=>void|Promise<void>}
export async function atlasView(index:Index,state:State,signal:AbortSignal,update:(patch:Partial<State>)=>void):Promise<Rendered> {
  const [all,scenarios]=await Promise.all([points(state,signal),read<Scenario[]>('scenarios',signal)]);
  const metric=index.metrics[state.metric];
  const selected=all.filter(r=>r.region===state.primary||r.region===state.comparison);
  const unit=state.indexed?'2019 = 100':state.rate&&state.metric.startsWith('covid_')?'reports / 100,000 annual population':metric.unit;
  function display(row:Point):number|null {
    if(!state.indexed)return row.value;
    const base=all.find(r=>r.region===row.region&&r.yr===2019)?.value;
    return base&&row.value!==null?row.value/base*100:null;
  }
  const series:Series[]=[state.primary,state.comparison].map((id,i)=>({name:country(index,id),color:i?'#bd724c':'#226354',
    points:selected.filter(r=>r.region===id).map(r=>({x:r.yr,y:display(r)}))}));
  const hasScenario=scenarios.some(r=>r.metric===state.metric);
  if(state.scenario&&hasScenario)for(const [i,id] of [state.primary,state.comparison].entries()) {
    const base=all.find(r=>r.region===id&&r.yr===2019)?.value;
    const convert=(v:number)=>state.indexed?(base?v/base*100:null):v;
    series.push({name:`${country(index,id)} pre-2020 projection`,color:i?'#bd724c':'#226354',dashed:true,
      points:scenarios.filter(r=>r.region===id&&r.metric===state.metric&&r.year>=2020).map(r=>({x:r.year,y:convert(r.scenario),
        low:convert(r.lower)??undefined,high:convert(r.upper)??undefined}))});
  }
  const cards=[state.primary,state.comparison].map((id,i)=>{
    const row=selected.find(r=>r.region===id&&r.yr===state.year),value=row?display(row):null;
    const pre=selected.find(r=>r.region===id&&r.yr===2019)?.value;
    const delta=row?.value!==null&&row?.value!==undefined&&pre!==null&&pre!==undefined?row.value-pre:null;
    return `<div class="country-card"><div><span class="country-dot" style="background:${i?'#bd724c':'#226354'}"></span>${safe(country(index,id))}<small>${safe(id)}</small></div><strong>${format(value,state.metric==='gdp'?0:1)}<span>${state.indexed?'index':safe(metric.unit)}</span></strong><p>${delta===null?'No matched 2019 baseline':`${delta>=0?'+':''}${format(delta)} ${safe(metric.unit)} since 2019`}</p></div>`;
  }).join('');
  const countries=index.country_registry.slice().sort((a,b)=>a.name.localeCompare(b.name));
  const options=(selected:string)=>countries.map(r=>`<option value="${r.id}" ${selected===r.id?'selected':''}>${safe(r.name)}</option>`).join('');
  const metricOptions=['employment','mortality','gdp','school','immunization','life_expectancy','covid_deaths','covid_cases'].map(id=>`<option value="${id}" ${id===state.metric?'selected':''}>${safe(index.metrics[id].title)}</option>`).join('');
  const coverage=index.coverage.find(r=>r.metric===state.metric)!;
  const exports=selected.map(r=>({...r,display_value:display(r),unit,kind:metric.kind,source_panel:index.panel_sha256,vintage:index.vintage}));
  const html=`<div class="page-heading"><div><div class="eyebrow">A LONGITUDINAL VIEW OF THE PANDEMIC</div><h1>Different shocks.<br><em>Uneven recoveries.</em></h1><p>Follow the records across health, work and everyday life.<br>Compare trajectories, then inspect what supports them.</p></div><div class="edition"><span>RESEARCH EDITION</span><strong>2000 <span>→</span> 2025</strong><p>Measured coverage varies by outcome.</p></div></div>
    <section class="control-bar" aria-label="Comparison controls"><label>OUTCOME<select id="metric">${metricOptions}</select></label><label>COMPARE<select id="primary">${options(state.primary)}</select></label><span class="versus">with</span><label><span class="sr-only">Comparison country</span><select id="comparison">${options(state.comparison)}</select></label><label class="year-control">YEAR <output id="year-output">${state.year}</output><input type="range" id="year" min="2000" max="2025" value="${state.year}" aria-label="Comparison year"></label></section>
    <div class="research-grid"><section class="panel map-panel"><div class="panel-heading"><div><span class="eyebrow">01 / GEOGRAPHY</span><h2>${safe(metric.title)} <span class="year-badge">${state.year}</span></h2></div><span class="pill">${coverage.countries} countries with values</span></div><div id="map"><div class="loading">Loading source-bound geography…</div></div><div class="map-note"><span>Click a country to update the comparison.</span><span>Natural Earth reference borders</span></div></section><section class="selection-panel"><div class="eyebrow">YOUR COMPARISON</div>${cards}<div class="measurement"><span class="tiny-label">MEASUREMENT</span><strong>${safe(metric.kind.replaceAll('_',' '))}</strong><p>${safe(metric.definition)}</p></div></section></div>
    <section class="panel trajectory-panel"><div class="panel-heading"><div><span class="eyebrow">02 / TRAJECTORIES</span><h2>Where the paths diverge</h2></div><div class="segmented" role="group" aria-label="Trajectory display"><button id="levels" class="${!state.indexed?'active':''}" aria-pressed="${!state.indexed}">Native units</button><button id="indexed" class="${state.indexed?'active':''}" aria-pressed="${state.indexed}">2019 = 100</button></div></div><div class="chart-options"><label><input type="checkbox" id="scenario" ${state.scenario?'checked':''} ${!hasScenario?'disabled':''}> Predictive no-shock band</label>${state.metric.startsWith('covid_')?`<label><input type="checkbox" id="rate" ${state.rate?'checked':''}> Per 100,000 people</label>`:''}<span class="micro">${state.scenario&&hasScenario?'2010-2019 trend extrapolation · 90% predictive interval':'Current-vintage records · missing values stay missing'}</span></div>${lineChart(series,unit,state.year,state.indexed?100:undefined)}<div class="chart-caption">${state.scenario&&hasScenario?'<strong>A projection, not a causal effect.</strong> The band extrapolates a pre-2020 regime and may miss structural changes.':'The shaded comparison window is a shared visual reference. It is not a universal lockdown date or pandemic end.'}</div><details><summary>Inspect and export the underlying observations</summary>${table(exports)}</details></section>
    <section class="context-row"><div><span class="eyebrow">READ THE EVIDENCE</span><h2>Every trajectory has a definition.</h2><p>Surveillance reports, modeled estimates and survey responses answer different questions. Start with the source before drawing a conclusion.</p></div><button class="context-card" data-view="studies"><span>12 STUDY PROTOCOLS</span><strong>Questions, results<br>and limits <b>↗</b></strong></button><button class="context-card" data-view="coverage"><span>INDEPENDENT COVERAGE</span><strong>See what each<br>domain measures <b>↗</b></strong></button><button class="context-card" data-view="biology"><span>SEPARATE BIOLOGICAL EVIDENCE</span><strong>Host associations<br>and viral lineages <b>↗</b></strong></button></section>`;
  return {html,rows:exports,after:async root=>{
    root.querySelector<HTMLSelectElement>('#metric')!.onchange=e=>update({metric:(e.target as HTMLSelectElement).value});
    for(const key of ['primary','comparison'] as const)root.querySelector<HTMLSelectElement>(`#${key}`)!.onchange=e=>update({[key]:(e.target as HTMLSelectElement).value});
    root.querySelector<HTMLInputElement>('#year')!.oninput=e=>{root.querySelector('#year-output')!.textContent=(e.target as HTMLInputElement).value;};
    root.querySelector<HTMLInputElement>('#year')!.onchange=e=>update({year:Number((e.target as HTMLInputElement).value)});
    root.querySelector('#levels')!.addEventListener('click',()=>update({indexed:false}));
    root.querySelector('#indexed')!.addEventListener('click',()=>update({indexed:true}));
    root.querySelector<HTMLInputElement>('#scenario')!.onchange=e=>update({scenario:(e.target as HTMLInputElement).checked});
    const rate=root.querySelector<HTMLInputElement>('#rate');if(rate)rate.onchange=e=>update({rate:(e.target as HTMLInputElement).checked});
    await drawMap(root.querySelector('#map')!,index,state,all,id=>update({primary:id}),signal);
  }};
}
