import {geoNaturalEarth1,geoPath} from 'd3-geo';
import {feature} from 'topojson-client';
import type {GeometryCollection,Topology} from 'topojson-specification';
import {country,format,read,safe} from './data';
import type {Index,Point,State} from './types';

export async function drawMap(container: HTMLElement, index: Index, state: State, rows: Point[], pick: (id:string)=>void, signal:AbortSignal): Promise<void> {
  const topology=await read<Topology<{countries:GeometryCollection}>>('world',signal);
  if(signal.aborted)return;
  const countries=feature(topology,topology.objects.countries);
  const projection=geoNaturalEarth1().fitExtent([[8,3],[932,390]],countries);
  const path=geoPath(projection);
  const values=new Map(rows.filter(r=>r.yr===state.year).map(r=>[r.region,r.value]));
  const bases=new Map(rows.filter(r=>r.yr===2019).map(r=>[r.region,r.value]));
  if(state.indexed) for(const [id,value] of values) {
    const base=bases.get(id);values.set(id,value!==null&&base?value/base*100:null);
  }
  const finite=[...values.values()].filter((v):v is number=>v!==null).sort((a,b)=>a-b);
  const colors=['#dce7d6','#b4d0b7','#7daa94','#4c8271','#22594f'];
  const thresholds=[.2,.4,.6,.8].map(q=>finite[Math.floor((finite.length-1)*q)]);
  const color=(v:number|null|undefined)=>v===null||v===undefined?'url(#missing)':colors[thresholds.filter(t=>v>t).length];
  const paths=countries.features.map(f=>{
    const numeric=String(f.id).padStart(3,'0'),iso=index.numeric_to_iso3[numeric],value=values.get(iso);
    const selected=iso===state.primary||iso===state.comparison;
    const selectable=index.country_registry.some(r=>r.id===iso);
    return `<path d="${path(f)??''}" fill="${color(value)}" stroke="${selected?'#e2a66c':'#f8faf3'}" stroke-width="${selected?'1.8':'.55'}" ${selectable?`data-country="${iso}" role="button" tabindex="${iso===state.primary?'0':'-1'}" aria-label="${safe(country(index,iso))}: ${format(value)}. Select country."`:''}><title>${safe(country(index,iso??'Unmatched geography'))}: ${format(value)}</title></path>`;
  }).join('');
  container.innerHTML=`<svg viewBox="0 0 940 405" class="world-map" aria-label="World map. Use arrow keys to move between countries, Enter to select."><defs><pattern id="missing" patternUnits="userSpaceOnUse" width="4" height="4"><rect width="4" height="4" fill="#e9ece4"/><path d="M0,4L4,0" stroke="#d6dbd1" stroke-width=".6"/></pattern></defs>${paths}</svg><div class="map-legend"><span>Lower ${state.indexed?'2019 index':'value'}</span>${colors.map(c=>`<i style="background:${c}"></i>`).join('')}<span>Higher</span><span class="missing-key">▨ Unavailable</span></div>`;
  const nodes=[...container.querySelectorAll<SVGPathElement>('[data-country]')];
  for(const [i,node] of nodes.entries()) {
    node.addEventListener('click',()=>pick(node.dataset.country!));
    node.addEventListener('keydown',event=>{
      if(event.key==='Enter'||event.key===' ') {event.preventDefault();pick(node.dataset.country!);}
      else if(['ArrowRight','ArrowDown','ArrowLeft','ArrowUp'].includes(event.key)) {
        event.preventDefault();const next=nodes[(i+(event.key==='ArrowRight'||event.key==='ArrowDown'?1:-1)+nodes.length)%nodes.length];
        node.setAttribute('tabindex','-1');next.setAttribute('tabindex','0');next.focus();
      }
    });
  }
}
