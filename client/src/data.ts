import type { Index, Point, State } from './types';

const cache = new Map<string, unknown>();
export async function read<T>(name: string, signal?: AbortSignal): Promise<T> {
  if (!/^[a-z0-9_-]+$/.test(name)) throw new Error('Invalid data identity');
  if (cache.has(name)) return cache.get(name) as T;
  const response = await fetch(new URL(`data/${name}.json`, document.baseURI), { signal });
  if (!response.ok) throw new Error(`Cannot load ${name}: HTTP ${response.status}`);
  const body: unknown = await response.json();
  if (signal?.aborted) throw new DOMException('Cancelled', 'AbortError');
  cache.set(name, body);
  return body as T;
}

export async function points(state: State, signal?: AbortSignal): Promise<Point[]> {
  const isCovid = state.metric.startsWith('covid_');
  const rows = await read<Point[]>(isCovid ? 'surveillance' : state.metric, signal);
  const selected = isCovid ? rows.filter(r => r.metric === state.metric) : rows;
  if (isCovid && state.rate) {
    const population = await read<Point[]>('population', signal);
    const lookup = new Map(population.map(r => [`${r.region}:${r.yr}`, r.value]));
    return selected.map(r => {
      const p = lookup.get(`${r.region}:${r.yr}`);
      return { ...r, value: p && r.value !== null ? r.value / p * 100000 : null };
    });
  }
  return selected;
}

export function country(index: Index, id: string): string {
  return index.country_registry.find(r => r.id === id)?.name ?? id;
}

export function format(value: unknown, digits = 1): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return 'Unavailable';
  return new Intl.NumberFormat('en-US', {maximumFractionDigits: digits}).format(value);
}

export function safe(text: unknown): string {
  return String(text ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]!));
}

export function table(rows: Record<string, unknown>[], limit = 80): string {
  if (!rows.length) return '<p class="empty">No eligible observations for this selection.</p>';
  const available = Object.keys(rows[0]).filter(k => typeof rows[0][k] !== 'object' || rows[0][k] === null);
  const columns = available.slice(0, 10);
  if (columns.includes('lower') && available.includes('upper') && !columns.includes('upper')) {
    columns.pop(); columns.splice(columns.indexOf('lower')+1,0,'upper');
  }
  return `<div class="table-scroll"><table><thead><tr>${columns.map(c => `<th scope="col">${safe(c.replaceAll('_',' '))}</th>`).join('')}</tr></thead><tbody>${rows.slice(0,limit).map(r => `<tr>${columns.map(c => `<td>${safe(typeof r[c] === 'number' ? format(r[c],3) : r[c] ?? 'Unavailable')}</td>`).join('')}</tr>`).join('')}</tbody></table></div>${rows.length > limit ? `<p class="micro">Showing ${limit} of ${rows.length} rows. Export includes all eligible rows.</p>` : ''}`;
}

export function download(rows: Record<string,unknown>[], name: string): void {
  if (!rows.length) return;
  const columns = [...new Set(rows.flatMap(r => Object.keys(r)))];
  const quote = (v: unknown): string => {
    let text = v === null || v === undefined ? '' : typeof v === 'object' ? JSON.stringify(v) : String(v);
    if (typeof v === 'string' && /^[=+@\-]/.test(text)) text = `'${text}`;
    return `"${text.replaceAll('"','""')}"`;
  };
  const csv = [columns.map(quote).join(','), ...rows.map(r => columns.map(c => quote(r[c])).join(','))].join('\r\n');
  const url = URL.createObjectURL(new Blob([csv], {type: 'text/csv;charset=utf-8'}));
  const anchor = document.createElement('a');
  anchor.href = url; anchor.download = `${name}.csv`; anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
