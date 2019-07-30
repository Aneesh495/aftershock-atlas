import type { Index, State, View } from './types';

const defaults: State = {view:'atlas',metric:'employment',primary:'USA',comparison:'GBR',year:2023,
  healthDomain:'hospital',reportingState:'CA',reportingYear:2022,hospitalMetric:'admissions',pulseWave:'33',pulseGroup:'national',
  contextGroup:'tenure',contextOutcome:'food_insufficiency',contextSensitivity:false,
  chronologySection:'gdp',gdpQuarter:'2022Q2',ctCounty:'09001',transitionRegion:'SDN',territoryEdition:'current',mortalityForecastCountry:'Italy',
  laborSector:'I',laborCountry:'FR',laborWindow:'2020-Q2',occupationGroup:'occupation',occupationOutcome:'telework',
  measurementSection:'learning',learningSubject:'mathematics',instructionGroup:'All eligible adults',hoursYear:2020,
  indexed:false,scenario:false,rate:false,study:'S01',subgroup:'total',vintage:'2023',historyMetric:'employment',edition:'201811',revisionEdition:'202312'};
const views: View[] = ['atlas','studies','coverage','biology','subnational','methods','sources','vintages','measurement','health','chronology'];
export function restore(index: Index): State {
  let stored: Partial<State> = {};
  try { stored = JSON.parse(localStorage.getItem('aftershock:v1') ?? '{}'); } catch { /* Ignore corrupt view preferences. */ }
  const state = {...defaults,...stored};
  const query = new URLSearchParams(location.search);
  for (const key of ['view','metric','primary','comparison','study','subgroup','vintage','historyMetric','edition','revisionEdition','measurementSection','learningSubject','instructionGroup','healthDomain','reportingState','hospitalMetric','pulseWave','pulseGroup','laborSector','laborCountry','laborWindow','occupationGroup','occupationOutcome','chronologySection','gdpQuarter','ctCounty','contextGroup','contextOutcome','transitionRegion','territoryEdition','mortalityForecastCountry'] as const) {
    const value = query.get(key); if (value) (state as unknown as Record<string,unknown>)[key] = value;
  }
  if (query.has('reportingYear')) state.reportingYear = Number(query.get('reportingYear'));
  if (query.has('hoursYear')) state.hoursYear = Number(query.get('hoursYear'));
  if (query.has('year')) state.year = Number(query.get('year'));
  for (const key of ['indexed','scenario','rate','contextSensitivity'] as const) if (query.has(key)) state[key] = query.get(key) === '1';
  if (!views.includes(state.view)) state.view = defaults.view;
  if (state.view === 'chronology' && !index.files['uk-vintages.json'] && !index.files['ct-crosswalk.json']) state.view = 'atlas';
  const annual = Object.values(index.metrics).filter(m => m.frequency === 'annual').map(m => m.id);
  if (![...annual,'covid_cases','covid_deaths'].includes(state.metric)) state.metric = defaults.metric;
  for (const key of ['primary','comparison'] as const) if (!index.country_registry.some(r => r.id === state[key])) state[key] = defaults[key];
  state.year = Math.min(2026,Math.max(2000,Math.round(Number(state.year) || defaults.year)));
  if (!/^S(0[1-9]|1[0-2])$/.test(state.study)) state.study = 'S01';
  for (const key of ['indexed','scenario','rate','contextSensitivity'] as const) state[key] = state[key] === true;
  state.vintage = state.vintage === '2022' ? '2022' : '2023';
  if(!['population','employment','gdp','school','immunization','mortality','life_expectancy'].includes(state.historyMetric))state.historyMetric='employment';
  for(const key of ['edition','revisionEdition'] as const)if(!['201811','201912','202012','202112','202212','202312'].includes(state[key]))state[key]=defaults[key];
  if (!index.files['measurement-v4.json'] && state.view === 'measurement') state.view = 'atlas';
  const workSections = ['learning', 'instruction', 'hours'];
  if (index.files['sector-hours.json']) workSections.push('sector');
  if (index.files['occupational-work.json']) workSections.push('occupation');
  if (!workSections.includes(state.measurementSection)) state.measurementSection = 'learning';
  state.laborWindow = state.laborWindow === '2023-Q2' ? '2023-Q2' : '2020-Q2';
  if (!['occupation', 'industry', 'national'].includes(state.occupationGroup)) state.occupationGroup = 'occupation';
  state.occupationOutcome = state.occupationOutcome === 'unable_to_work' ? 'unable_to_work' : 'telework';
  if (!['mathematics','reading','science'].includes(state.learningSubject)) state.learningSubject = 'mathematics';
  state.hoursYear = state.hoursYear === 2022 ? 2022 : 2020;
  if (!index.files['state-surveillance.json'] && state.view === 'health') state.view = 'atlas';
  if (!['hospital','testing','vaccination','survey','context'].includes(state.healthDomain)) state.healthDomain = 'hospital';
  if (!index.files['social-context.json'] && state.healthDomain === 'context') state.healthDomain = 'hospital';
  if (!['national','race_origin','tenure','income'].includes(state.contextGroup)) state.contextGroup = 'tenure';
  state.contextOutcome = state.contextOutcome === 'mental_health_screen' ? 'mental_health_screen' : 'food_insufficiency';
  if (!index.files['survey-bridge.json'] && state.healthDomain === 'survey') state.healthDomain = 'hospital';
  if (!/^[A-Z]{2}$/.test(state.reportingState) || !index.files[`state-report-${state.reportingState.toLowerCase()}.json`]) state.reportingState = defaults.reportingState;
  if (![2020, 2021, 2022, 2023, 2024].includes(state.reportingYear)) state.reportingYear = defaults.reportingYear;
  if (!['admissions','icu_patients','icu_occupied','icu_covid'].includes(state.hospitalMetric)) state.hospitalMetric = 'admissions';
  state.pulseWave = state.pulseWave === '34' ? '34' : '33';
  if (!['national','race_origin','income'].includes(state.pulseGroup)) state.pulseGroup = 'national';
  return state;
}
export function persist(state: State): void {
  try { localStorage.setItem('aftershock:v1',JSON.stringify(state)); } catch { /* Storage is optional. */ }
  const query = new URLSearchParams();
  for (const [key,value] of Object.entries(state)) query.set(key,typeof value === 'boolean' ? value ? '1' : '0' : String(value));
  history.replaceState(null,'',`?${query}`);
}
