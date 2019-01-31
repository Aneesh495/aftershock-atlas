export interface Metric {
  id: string; title: string; family: string; unit: string; frequency: string;
  kind: string; definition: string;
}
export interface Region { id: string; name: string; region: string; income: string; iso2: string }
export interface Coverage {
  metric: string; kind: string; unit: string; frequency: string; row_count: number;
  nonmissing: number; regions: number; countries: number; first_date: string; last_date: string;
}
export interface Index {
  version: number; built_at: string; source_commit: string; panel_sha256: string;
  record_count: number; country_registry: Region[]; metrics: Record<string, Metric>;
  coverage: Coverage[]; numeric_to_iso3: Record<string,string>; vintage: string;
  limitations: string[]; files: Record<string,string>;
}
export interface Point { region: string; yr: number; value: number | null; metric?: string; reported_weeks?: number; total_weeks?: number }
export interface Scenario { region: string; metric: string; year: number; observed: number | null; scenario: number; lower: number; upper: number; alternative_level: number }
export interface Study {
  id: string; title: string; hypothesis: string; comparison: string; missingness: string;
  intervals: string; alternatives: string[]; practical: string; support: string; status: string;
  conclusion: string; table: Record<string,unknown>[]; summary: Record<string,unknown>;
}
export type View = 'atlas' | 'studies' | 'coverage' | 'biology' | 'subnational' | 'methods' | 'sources';
export interface State {
  view: View; metric: string; primary: string; comparison: string; year: number;
  indexed: boolean; scenario: boolean; rate: boolean; study: string; subgroup: string; vintage: string;
}
export interface Series { name: string; color: string; points: { x: number; y: number | null; low?: number; high?: number }[]; dashed?: boolean }
export interface SurveyRow {
  region: string; event_start: string; event_end: string; value: number | null; lower: number | null;
  upper: number | null; group: string; phase: string; suppressed?: boolean; suppression_reason?: string;
}
export interface GeneticRow { chromosome: string; position: number; effect_allele: string; reference: string;
  a2_odds_ratio: number; a2_lower: number; a2_upper: number; a2_beta: number; b2_beta_aligned: number; a2_p: number }
export interface SourceCard { id: string; citation: string; url: string; rights: string; timing: string;
  limitations: string; acquired_at: string; sha256: string; bytes: number; status: string }
