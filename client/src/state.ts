import type { Index, State, View } from './types';

const defaults: State = {view:'atlas',metric:'employment',primary:'USA',comparison:'GBR',year:2023,
  indexed:false,scenario:false,rate:false,study:'S01',subgroup:'total',vintage:'2023'};
const views: View[] = ['atlas','studies','coverage','biology','subnational','methods','sources'];
export function restore(index: Index): State {
  let stored: Partial<State> = {};
  try { stored = JSON.parse(localStorage.getItem('aftershock:v1') ?? '{}'); } catch { /* Ignore corrupt view preferences. */ }
  const state = {...defaults,...stored};
  const query = new URLSearchParams(location.search);
  for (const key of ['view','metric','primary','comparison','study','subgroup','vintage'] as const) {
    const value = query.get(key); if (value) (state as unknown as Record<string,unknown>)[key] = value;
  }
  if (query.has('year')) state.year = Number(query.get('year'));
  for (const key of ['indexed','scenario','rate'] as const) if (query.has(key)) state[key] = query.get(key) === '1';
  if (!views.includes(state.view)) state.view = defaults.view;
  const annual = Object.values(index.metrics).filter(m => m.frequency === 'annual').map(m => m.id);
  if (![...annual,'covid_cases','covid_deaths'].includes(state.metric)) state.metric = defaults.metric;
  for (const key of ['primary','comparison'] as const) if (!index.country_registry.some(r => r.id === state[key])) state[key] = defaults[key];
  state.year = Math.min(2025,Math.max(2000,Math.round(Number(state.year) || defaults.year)));
  if (!/^S(0[1-9]|1[0-2])$/.test(state.study)) state.study = 'S01';
  for (const key of ['indexed','scenario','rate'] as const) state[key] = state[key] === true;
  state.vintage = state.vintage === '2022' ? '2022' : '2023';
  return state;
}
export function persist(state: State): void {
  try { localStorage.setItem('aftershock:v1',JSON.stringify(state)); } catch { /* Storage is optional. */ }
  const query = new URLSearchParams();
  for (const [key,value] of Object.entries(state)) query.set(key,typeof value === 'boolean' ? value ? '1' : '0' : String(value));
  history.replaceState(null,'',`?${query}`);
}
