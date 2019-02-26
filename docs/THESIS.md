# Aftershock Atlas: trajectories, measurement and the limits of comparison

## Abstract

Aftershock Atlas is a reproducible population-level research application that compares pandemic-era trajectories without turning incompatible measurements into a single universal score. A global report-week surveillance panel and annual multi-domain estimates feed an original temporal model, classical baselines, predictive scenarios, candidate group-time designs and an interactive atlas. Separate survey, subnational, host-genetic and viral pipelines preserve their own sampling and timing limits. The main result is mixed predictive performance with substantial interval undercoverage, alongside concrete evidence that data availability and measurement definitions restrict what the application can infer.

The project is a research preview. Several scientific requirements remain incomplete, including historical available-at-time evaluation, full geography reconciliation, complete multiwave survey design auditing and complete hours or learning measurement. Missing data and failed identification are outputs of the workflow, not grounds for silently changing the question.

## Research design

The pandemic did not produce a single intervention at one worldwide time. Outcomes differ in frequency, denominator, selection and reporting delay. A common 2020-2022 visual window is useful for orientation, but it is not used as a universal lockdown date or end of exposure. The annual employment and GDP studies use matched reference years and explicit eligibility. Survey comparisons use source-defined phases. Oxford policies provide country-specific adoption dates for candidate designs. Viral estimates use a frozen publication window.

The protocol is recorded in `configs/studies.json` and `docs/EXPERIMENT_PLAN.md`. It was frozen before study-table execution, after source inspection and engineering pilots; it is not a blinded external registration. The falsifiable questions and material differences are retained even where data cannot support a complete answer. No omnibus significance test combines unrelated outcome units.

## Measurement and source identity

Every panel value retains an event interval, availability timestamp, source byte hash, measurement kind, unit, frequency, group and flags. WHO case and death observations use report weeks. CDC deaths use event weeks and state of occurrence. WDI annual mortality, population, employment and immunization include estimates. Gross secondary enrollment is not learning attainment and can exceed 100 percent. Real GDP per person is not nominal GDP or hours of work.

Raw acquisitions are bounded and stored under content hashes. A revision creates another identity rather than mutating the original bytes. Two WHO excess mortality releases demonstrate actual changed estimates and age definitions. Current annual source acquisition is not a historical archive: reference-year chronology alone cannot establish the contemporaneously available information set.

Geographic harmonization uses current reference identifiers with explicit unknown historical validity. Additive crosswalk code conserves each source population exactly once and propagates supplied allocation bounds. It is not used to invent a global historical boundary reconstruction. Source-defined race and ethnicity categories remain in their US context and are never treated as a universal biological partition.

## Predictive methods

The original learner receives four annual lagged levels for six outcomes plus missingness indicators. GDP uses log1p transformation. The target is the next transformed value minus the latest known value. Missing outcome targets are masked. Country-balanced loss limits the influence of locations with denser training series. The shared tanh layer produces six Gaussian means and log variances; analytic gradients and Adam are implemented directly with NumPy primitives.

Country identities are assigned by a frozen hash rule. Held-out countries enter neither preprocessing nor calibration. Training years end in 2015; validation is 2016-2018; testing is 2019-2024. Seeds 11, 29 and 47 begin at independent random initializations. Checkpoints preserve initialization, best validation parameters, Adam moments, epoch and sampler RNG. Finite differences test all parameters of a small network, and restored checkpoints reproduce the next optimizer update.

Persistence, local trend, pooled ridge and a local-level filter use the same permitted lag information. Validation selects the baseline and early stopping. Absolute standardized validation residuals calibrate 90 percent predictive bands. This calibration has no exchangeability guarantee through a pandemic regime shift. Proper scores, interval coverage and untrained controls test different aspects of the model rather than making a single accuracy claim.

A separate pre-2020 scenario extrapolates 2010-2019 linear trends and reports a local-level alternative. It is labeled predictive no-shock throughout. It is not presented as what would certainly have happened without the pandemic. The CDC state studies fit an original negative-binomial IRLS model with trend and seasonal harmonics; negative report corrections are not silently transformed into valid count-model observations.

## Identification and causal limits

The policy candidate is first national full school closure under Oxford majority-population coding. The outcome is annual modeled employment. The group-time comparison uses the preceding year and not-yet-treated or never-treated controls with outcome support. The intended estimand requires parallel trends, no anticipation and a defensible interference assumption. The implementation retains pretrend diagnostics, pseudo-onsets, country bootstrap intervals and differential-trend sensitivity.

The late-adoption cohort has only two countries and fails the minimum support rule. The earlier cohort allows arithmetic contrasts but does not solve policy bundling, reverse causation or spillovers. The application therefore labels the entire design as descriptive candidate diagnostics. A non-significant pretrend test cannot establish the required assumptions. Potential mediators such as work and care arrangements are not inserted as confounders.

## Aggregate surveys and biological evidence

Household Pulse provides published weighted symptom estimates and marginal intervals. The extract does not contain participant weights, PSUs or response denominators. It supports within-phase published-estimate comparisons and suppression checks; it cannot independently reproduce the provider's survey design. Unknown cross-wave covariance is handled with a conservative marginal-width envelope, and no matched-respondent claim is made.

HGI A2 and B2 selected-variant releases support a technical association harmonization exercise. The pipeline validates GRCh38 coordinates, reference and effect alleles, effect signs, standard errors, ambiguous common palindromic alleles and selected-set multiplicity. Odds ratios are derived from released log effects. Shared cases and controls and absent LD references prevent independent replication or conditional causal interpretation. No individual genomes are acquired, and no host-genetic association is used to explain national or ethnic group trajectories.

CDC weighted viral estimates are a different artifact. One archived national publication is selected instead of mixing historical and nowcast revisions. Unreliable cells retain suppression. Hierarchically overlapping lineage labels are not arbitrarily summed into a prevalence partition. Sequencing selection bias limits interpretation independently of host association limitations.

## Results

The acquired panel contains 851,150 typed records. A global surveillance slice covers 240 reporting areas, and annual series include up to 217 economies. Real source-specific limits are explicit: surveys are US-only, mobility is UK-only, subnational count studies are California and Florida, and HGI case-control samples do not define a country panel.

## Forecast results

Training target years are 2004-2015, validation years 2016-2018 and test years 2019-2024. The fitted cohort has 2004 training rows, 501 validation rows and 1302 test rows. The three seeds stop after 69, 68 and 64 epochs respectively in the first campaign. Parameter changes are nonzero. There are 68570 test prediction records across 60 outcome/model configurations, including untrained controls.

Baselines below are selected by validation CRPS, not by the final test minimum. Lower CRPS is better. Each family's scale is separate. GDP uses log1p USD units. Network values are means of the three seed scores.

| Outcome | Validation-selected baseline | Baseline test CRPS | Mean network test CRPS | Network interval coverage, nominal 90% |
| --- | --- | --- | --- | --- |
| employment | pooled_ridge | 0.90933 | 0.87227 | 75.0-76.3% |
| gdp | pooled_ridge | 0.03547 | 0.03467 | 74.6-75.4% |
| immunization | pooled_ridge | 2.53435 | 2.36654 | 85.8-86.5% |
| life_expectancy | pooled_ridge | 0.70283 | 0.70641 | 60.8-61.7% |
| mortality | pooled_ridge | 0.62642 | 0.54898 | 60.4-62.0% |
| school | persistence | 2.03894 | 2.09836 | 88.5-89.7% |

Learned scores improve on several comparisons and regress on others. Interval coverage is poor for mortality and life expectancy. A model with a better point distribution score does not thereby meet a calibrated uncertainty requirement. These outcomes remain visible in the atlas and frozen records. No thresholds were lowered after this result.


## S01: Excess mortality and official reports

**Hypothesis:** WHO modeled excess deaths exceed reported COVID deaths in most jointly covered country-years.

2020 and 2021 joint populations; alternate WHO releases. Missingness rule: Do not fill absent WHO reports; report nonmissing report weeks.

Modeled excess and reported COVID death totals differ across jointly measured country-years. Ratios mix event-year estimates and report-week counts and cannot isolate reporting bias.

The executed table has 388 rows. Support status is `bounded_analysis`. Selected result fields: `{"above_1_2": 269, "above_one": 280, "eligible_country_years": 349, "median_absolute_monthly_revision": 105.52408970000002, "revision_cells": 4656}`.

Uncertainty: Published WHO annual 95 percent intervals; no sums of marginal bounds. Material difference: Ratio above 1.2 is descriptively material. Alternate explanations include Indirect deaths, Model assumptions, Reporting-date mismatch, Under-ascertainment.

Replay table: `data/results/studies/S01.csv`, produced by `make studies`; protocol: `configs/studies.json`.

## S02: Reporting corrections and observation gaps

**Hypothesis:** Negative report corrections and missing weeks are nonuniform across reporting areas.

WHO case and death series; per-area missingness, signed corrections and reporting-era changes. Missingness rule: Blank remains absent, including runs of absent reports.

Signed corrections and long missing runs occur in the reported surveillance panel. Missingness is not evidence of no infections or deaths.

The executed table has 480 rows. Support status is `bounded_analysis`. Selected result fields: `{"area_metrics_above_20pct_missing": 387, "areas": 240, "negative_correction_weeks": 31}`.

Uncertainty: Exact finite-panel counts; no population sampling confidence claim. Material difference: Any correction changes cumulative aggregation; gaps above 20 percent flag limited support. Alternate explanations include Surveillance redesign, Batch reports, Testing intensity.

Replay table: `data/results/studies/S02.csv`, produced by `make studies`; protocol: `configs/studies.json`.

## S03: Age-standardized mortality contrasts

**Hypothesis:** Direct age standardization changes at least one crude country mortality contrast.

WHO 2022 modeled age and sex counts and Nx for USA and GBR; common pooled 2020 standard. Missingness rule: Require identical age bins and positive Nx; do not bridge changed 2023 bins.

Common-population age standardization changes the crude mortality contrasts. This is a check on modeled aggregate age composition, not an estimate of racial or individual risk.

The executed table has 4 rows. Support status is `bounded_analysis`. Selected result fields: `{"2023_comparable_bands": false, "independently_recomputable": true, "source_release": "WHO May 2022"}`.

Uncertainty: Poisson approximation is a numerical sensitivity, excludes WHO model covariance. Material difference: Contrast changes at least 5 percent. Alternate explanations include Modeled demographic assumptions, Age aggregation, Changing age composition.

Replay table: `data/results/studies/S03.csv`, produced by `make studies`; protocol: `configs/studies.json`.

## S04: Unequal work and mobility exposure

**Hypothesis:** Employment trajectories and workplace mobility expose different populations and cannot be equated.

Annual employment estimates and available aggregate workplace mobility within source geography. Missingness rule: No country or year extrapolation across unavailable mobility coverage.

Within-UK workplace visits declined relative to a short weekday baseline. The opt-in device population cannot identify employment, hours or unequal occupational exposure.

The executed table has 3 rows. Support status is `partial_outcome_support`. Selected result fields: `{"employment_countries": 187, "mobility_countries": 1}`.

Uncertainty: Source estimates; no invented mobility sampling intervals. Material difference: Definitions and coverage determine eligible contrasts. Alternate explanations include Opt-in device selection, Remote work eligibility, Informal labor.

Replay table: `data/results/studies/S04.csv`, produced by `make studies`; protocol: `configs/studies.json`.

## S05: Routine health service disruption

**Hypothesis:** DTP coverage in 2021 is below its 2010-2019 trend in more than half of eligible countries.

DTP observed estimates versus prespecified predictive no-shock trend; local-level sensitivity. Missingness rule: At least eight pre-period years and 2021 outcome.

Routine immunization differences depend on the chosen pre-period baseline. The trend and local-level comparisons remain predictive sensitivities; neither identifies a pandemic effect.

The executed table has 193 rows. Support status is `bounded_analysis`. Selected result fields: `{"below_trend": 136, "below_trend_2pp": 91, "eligible": 193}`.

Uncertainty: Predictive trend bands; do not call them causal intervals. Material difference: Two percentage points. Alternate explanations include Conflict, Supply constraints, Model revisions, Catch-up vaccination.

Replay table: `data/results/studies/S05.csv`, produced by `make studies`; protocol: `configs/studies.json`.

## S06: Comparative school closure timing

**Hypothesis:** Full closure timing supports eligible group-time comparisons with annual employment.

Oxford adoption cohorts versus not-yet-treated places with support checks. Missingness rule: At least five treated and five controls; four pre-period years for trend check.

Some group-time cells can be calculated, but school closures coincide with other policies and epidemic changes. The two-country late-adoption cohort fails minimum support. Causal identification is not established.

The executed table has 9 rows. Support status is `bounded_analysis`. Selected result fields: `{"identification": "not_established"}`.

Uncertainty: Country bootstrap where eligible; null estimates where unsupported. Material difference: One employment percentage point. Alternate explanations include Policy bundles, Reverse causation, Anticipation, Spillovers.

Replay table: `data/results/studies/S06.csv`, produced by `make studies`; protocol: `configs/studies.json`.

## S07: Employment recovery

**Hypothesis:** 2023 employment remains below 2019 in at least one quarter of jointly measured countries.

Matched country estimates in 2019, 2020 and 2023; 2024 sensitivity. Missingness rule: Complete matched pairs only; publish excluded countries.

Employment recovery differs across the matched country estimates. The eligible sample and endpoint year change the summary; these ratios also depend on demographic composition.

The executed table has 184 rows. Support status is `bounded_analysis`. Selected result fields: `{"below_2019": 89}`.

Uncertainty: Country bootstrap of descriptive average changes. Material difference: One percentage point. Alternate explanations include Population age structure, Long-run labor shifts, ILO model revisions.

Replay table: `data/results/studies/S07.csv`, produced by `make studies`; protocol: `configs/studies.json`.

## S08: Real output recovery and missing hours

**Hypothesis:** Real per-person GDP recovery varies across countries and cannot identify hours lost.

Constant 2015 USD GDP per person 2019, 2020, 2023; alternative 2024 endpoints. Missingness rule: Matched positive GDP values; never substitute nominal GDP.

Constant-price per-person GDP trajectories differ across matched countries. The panel contains no hours series and cannot estimate working hours lost.

The executed table has 203 rows. Support status is `partial_outcome_support`. Selected result fields: `{"hours_available": false}`.

Uncertainty: Country bootstrap of log changes. Material difference: Five percent real output per person. Alternate explanations include Exchange conversion base, Sector composition, Non-pandemic shocks.

Replay table: `data/results/studies/S08.csv`, produced by `make studies`; protocol: `configs/studies.json`.

## S09: School policy and enrollment

**Hypothesis:** School policy and gross secondary enrollment do not establish matched learning loss.

Oxford closure exposure and matched WDI enrollment endpoints. Missingness rule: No interpolation of missing school observations.

Gross secondary enrollment changes are observed for a selected subset of countries. Enrollment, remote instruction and learning attainment are distinct outcomes. Missing assessment data prevents a learning-loss estimate.

The executed table has 115 rows. Support status is `partial_outcome_support`. Selected result fields: `{"learning_assessment_available": false, "remote_instruction_available": false}`.

Uncertainty: Country bootstrap of enrollment change; source definition limitations. Material difference: Two gross enrollment percentage points. Alternate explanations include Repeat enrollment, Population age structure, Migration, Definition shifts.

Replay table: `data/results/studies/S09.csv`, produced by `make studies`; protocol: `configs/studies.json`.

## S10: Mental health survey changes

**Hypothesis:** Within-phase symptom changes differ across US source-defined groups.

Household Pulse first and last wave within each phase and geography. Missingness rule: Provider suppression retained; no pre-2020 matched baseline.

Within-phase published symptom estimates vary across US groups and states. The separate version 2 public-use replay joins 74,413 respondents to 80 replicate weights and reconstructs 24 national and source-defined subgroup estimates. Twenty-two agree within the registered tolerance. The two combined-symptom discrepancies remain unresolved. Later-wave weights, nonresponse bias and cross-wave covariance remain incomplete. The reference period changes from seven to fourteen days in July 2021.

The executed table has 1216 rows. Support status is `partial_design_support`. Selected result fields: `{"independent_weight_recomputation": "week_1_only", "states": 51, "suppressed": 235}`.

Uncertainty: Published marginal intervals; conservative unknown-covariance change envelope. Material difference: Five percentage points. Alternate explanations include Nonresponse, Mode and instrument shifts, Repeated participants, Composition.

Replay table: `data/results/studies/S10.csv`, produced by `make studies`; protocol: `configs/studies.json`.

## S11: Viral phase heterogeneity

**Hypothesis:** Weighted lineage composition changes over the archived CDC observation window.

One frozen national weighted publication; reliable lineage estimates over time. Missingness rule: Unreliable cells suppressed; no submission counts as prevalence.

The highest reliable reported lineage estimate changes across the archived US national window. Overlapping lineage labels and sequencing selection prevent interpreting these rows as an exhaustive prevalence partition.

The executed table has 105 rows. Support status is `bounded_analysis`. Selected result fields: `{"duplicate_source_rows": 0, "geography": "USA national", "input_rows": 11024, "model": "CDC weighted estimates; no nowcast mixed into this extract", "publication_count": 1, "source_hash": "f97334b5f1228b1dc989512082cf893adde7c4296621a2448b326efe2c6d28c7", "suppressed_rows": 9701, "unique_selected_rows": 11024}`.

Uncertainty: CDC published uncertainty; no sums across overlapping lineage labels. Material difference: Dominant lineage change within comparable interval definitions. Alternate explanations include Sequencing selection, Classification changes, Publication revision.

Replay table: `data/results/studies/S11.csv`, produced by `make studies`; protocol: `configs/studies.json`.

## S12: Aggregate host genetics methods

**Hypothesis:** Allele harmonization and ambiguous-strand exclusions materially affect aggregate concordance.

HGI A2 and B2 released selected variants; GRCh38 and effect-allele checks. Missingness rule: Exclude mismatches, ambiguous common palindromic variants and absent overlap.

Effect-allele harmonization aligns aggregate selected-variant associations after ambiguous-strand exclusions. Shared samples and LD prevent treating concordance as independent replication.

The executed table has 20 rows. Support status is `bounded_analysis`. Selected result fields: `{"a2_below_threshold": 1366, "aligned_variants": 9443, "analysis": "host_genetics_aggregate_methods", "direction_concordant": 9328, "display_bin_bp": 1000000, "genome_wide_threshold": 5e-08, "independent_replication": false, "ld_independence_established": false, "multiplicity": "BH applies only to the selected 10000 variants; ascertainment prevents genome-wide FDR interpretation", "rounded_p_discrepancies_log_tolerance_0_1": 0, "sample_overlap": "A2 severe cases can be contained in B2 hospitalized cases; controls and contributing cohorts overlap", "source": "HGI release 7; April 2022", "terms": "https://www.covid19hg.org/about/"}`.

Uncertainty: Published beta/SE Wald intervals; selected-set BH scope explicit. Material difference: Any incorrect effect sign invalidates an association comparison. Alternate explanations include Sample overlap, LD, Selection of top variants, Phenotype differences.

Replay table: `data/results/studies/S12.csv`, produced by `make studies`; protocol: `configs/studies.json`.

## Independent verification

Evidence bundles bind executable files to an independently supplied Git commit. They include frozen upstream identities, raw records, command exits, environment, completed workloads, model states and per-unit predictions. The verifier is implemented separately from the summarizer. It independently parses all included WHO and annual values, rejects duplicate populations or forged availability, reconstructs features from earlier source records, recomputes proper scores and replays fixed saved-model probes without retraining.

Age-standardized rates are independently summed from source age counts, denominators and common weights. Genetic odds ratios must agree with signed log effects and aligned direction. Suppressed survey values cannot reappear through confidence intervals or export. Rehashed semantic mutations test these relationships rather than only file corruption.

The public client is connected to the actual exported snapshot. Browser verification covers country and outcome selection, predictive bands, unsupported causal cells, subnational evidence, aggregate genetics, CSV export, missing data, recovery, keyboard navigation, constrained layout and persistence. Screenshots and DOM observations identify the exercised view and source-bound snapshot. Lightweight CI is engineering evidence and cannot certify an unexecuted full scientific profile.

## Limitations and unanswered questions

Current source vintages do not prove historical deployability. Full border crosswalks and source-specific denominator auditing remain incomplete. Survey aggregates cannot reveal unmeasured nonresponse or participant-level instrument comparability. Employment ratios cannot recover hours lost; enrollment cannot establish learning attainment. HGI selected variants do not support genome-wide discovery, independent replication or personal risk predictions. Country associations cannot identify individual risks.

The version 2 extension adds an original hierarchical damped level/slope filter with an empirical Gaussian slope prior and fitted process and observation noise. All 18 starts converged, but no outcome met the five-percent practical CRPS improvement criterion. Schooling, mortality and life expectancy lost to their frozen baselines. Mortality and life-expectancy coverage remained 68.66 and 61.21 percent for nominal 90 percent bands. These reused test outcomes provide exploratory evidence only. Causal identification remains unresolved even where a numerical contrast is available. Most critically, learned and count-model interval undercoverage makes uncertainty a live failure, not a solved feature.

## Reproducibility and references

Run the root Makefile commands and use a new campaign identity. Exact protocols, source manifests, contracts, decisions and recovery instructions are in this repository. Original source and failed results are retained. No paid compute, identifiable participant records, individual genomes or clinical use are required. Public-use deidentified Census records are acquired only into ignored local storage and never enter public examples or evidence.

Primary references: [WHO surveillance](https://data.who.int/dashboards/covid19/data), [WHO modeled excess mortality](https://www.who.int/data/sets/global-excess-deaths-associated-with-COVID-19-modelled-estimates), [Oxford final policy dataset](https://github.com/OxCGRT/covid-policy-dataset), [World Bank indicator API](https://datahelpdesk.worldbank.org/knowledgebase/articles/898581), [NCHS Household Pulse](https://data.cdc.gov/d/8pt5-q6wp), [HGI release 7](https://www.covid19hg.org/results/r7/), and [Callaway and Sant'Anna](https://arxiv.org/abs/1803.09015). These sources define data and methods; they do not endorse this implementation or certify its acceptance.

The [exploratory extension report](EXTENSION_RESULTS.md) records the exact survey discrepancies, adult denominators, nonresponse definitions, hierarchical-model losses and replay commands.
