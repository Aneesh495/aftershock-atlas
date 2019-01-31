import {format,safe} from './data';
import type { Series } from './types';

export function lineChart(series: Series[], unit: string, selected?: number, baseline?: number): string {
  const width=900, height=300, left=64, right=24, top=20, bottom=42;
  const all = series.flatMap(s => s.points.filter(p => p.y !== null && Number.isFinite(p.y)));
  if (!all.length) return '<div class="empty">No comparable observations for this selection. Choose another outcome or country.</div>';
  const xs = all.map(p=>p.x), ys = all.flatMap(p=>[p.y!,p.low ?? p.y!,p.high ?? p.y!]);
  const xmin=Math.min(...xs), xmax=Math.max(...xs), ymin0=Math.min(...ys), ymax0=Math.max(...ys);
  const padding=Math.max((ymax0-ymin0)*.12,Math.abs(ymax0)*.02,.01);
  const ymin=ymin0-padding,ymax=ymax0+padding;
  const x=(v:number)=>left+(v-xmin)/(xmax-xmin||1)*(width-left-right);
  const y=(v:number)=>height-bottom-(v-ymin)/(ymax-ymin)*(height-top-bottom);
  const grid = Array.from({length:5},(_,i)=>{
    const value=ymin+(ymax-ymin)*i/4;
    return `<line x1="${left}" x2="${width-right}" y1="${y(value)}" y2="${y(value)}" stroke="#e1e6df"/><text x="${left-12}" y="${y(value)+4}" text-anchor="end">${format(value,Math.abs(value)<10?2:0)}</text>`;
  }).join('');
  let ticks = [...new Set(xs)].filter((_,i,a)=>i%Math.max(1,Math.ceil(a.length/7))===0);
  if (xmax > 2100) ticks = [xmin,...ticks.filter(v=>v>xmin&&v<xmax),xmax].slice(0,8);
  const labels=ticks.map(v=>`<text x="${x(v)}" y="${height-13}" text-anchor="middle">${v>2100?new Date(v).getFullYear():v}</text>`).join('');
  const shapes=series.map(s=>{
    const segments: typeof s.points[]=[]; let current: typeof s.points=[];
    for (const p of s.points) { if(p.y===null) {if(current.length)segments.push(current);current=[];} else current.push(p); }
    if(current.length)segments.push(current);
    return segments.map(segment=>{
      const line=segment.map((p,i)=>`${i?'L':'M'}${x(p.x).toFixed(2)},${y(p.y!).toFixed(2)}`).join(' ');
      const band=segment.every(p=>p.low!==undefined&&p.high!==undefined) ? `<path d="${segment.map((p,i)=>`${i?'L':'M'}${x(p.x)},${y(p.high!)}`).join(' ')} ${[...segment].reverse().map(p=>`L${x(p.x)},${y(p.low!)}`).join(' ')}Z" fill="${s.color}" opacity=".1"/>` : '';
      return `${band}<path d="${line}" stroke="${s.color}" stroke-width="2.7" fill="none" ${s.dashed?'stroke-dasharray="7 5"':''}/>${segment.filter(p=>p.x===selected).map(p=>`<circle cx="${x(p.x)}" cy="${y(p.y!)}" r="5" fill="${s.color}" stroke="white" stroke-width="2"><title>${safe(s.name)}: ${format(p.y)} ${safe(unit)}</title></circle>`).join('')}`;
    }).join('');
  }).join('');
  const reference = baseline!==undefined&&baseline>=ymin&&baseline<=ymax ? `<line x1="${left}" x2="${width-right}" y1="${y(baseline)}" y2="${y(baseline)}" stroke="#9b9f96" stroke-dasharray="3 4"/>` : '';
  const onset = xmin<=2020&&xmax>=2020 ? `<rect x="${x(2020)}" y="${top}" width="${Math.max(0,x(Math.min(2022,xmax))-x(2020))}" height="${height-top-bottom}" fill="#d9ddd3" opacity=".2"/><text x="${x(2020)+7}" y="${top+12}" class="era-label">2020-2022 comparison window</text>` : '';
  return `<div class="chart-legend">${series.map(s=>`<span><i style="background:${s.color}"></i>${safe(s.name)}</span>`).join('')}<span class="unit">${safe(unit)}</span></div><svg class="line-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Trajectory comparison in ${safe(unit)}">${onset}${grid}${labels}${reference}${shapes}</svg>`;
}
