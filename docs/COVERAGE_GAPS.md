# Requirement and artifact map

This inventory describes implemented measurement and missing scope. A domain name on a page does not establish complete measurement.

| Requirement | Implemented artifact | Current limit |
| --- | --- | --- |
| Global COVID reports and state surveillance | `panel.py`, WHO signed weekly cases/deaths. `state_surveillance.py`, archived hospital, ICU and PCR from 50 states and DC | State populations and date bases differ across measures. Reporting changes and gaps limit comparisons |
| COVID vaccine rollout | CDC completed primary series and doses from 50 states and DC, with signed corrections | Resident and administered jurisdictions differ. Archives end in 2023 |
| Excess mortality and revisions | `excess.py`, WHO May 2022 and May 2023 | Modeled 2020-2021 estimates, not observed daily deaths |
| Geography and denominators | `geography.py`, current registry and additive crosswalk contract | Historical split/merge source validation incomplete; no invented residence denominator for occurrence counts |
| Historical information sets | `history.py`, six official WDI archive editions; independent raw/feature replay | Archive-month bounds do not prove original cell publication days or territorial equivalence; sparse historical outcome support |
| Employment and output | `features.py`, WDI employment ratio and constant-price GDP per person | OECD actual annual hours matched within countries. Sector and actual weekly-hours evidence still needed |
| Education | WDI enrollment, Oxford policies, OECD PISA and US adult-reported remote instruction | Three distinct education populations. No individual comparison or causal closure estimate |
| Mobility exposure | `mobility.py`, UK daily aggregates | Opt-in device sample, no worker denominator or occupational exposure claim |
| Mental-health instruments | `survey.py`, NCHS published US waves | Reference period changes in July 2021; no matched pre-pandemic comparison |
| Actual survey weighting | Census weeks 1, 33 and 34 and 80 person replicates, with independent replay | Week-specific estimates and separate recall periods. Published comparison discrepancies retained. Selection bias remains |
| Source-defined group denominators | National, sex, race/origin and income denominators audited in three US waves under their own schema | Age-standardized subgroup and broader social context remain incomplete |
| Subnational studies | `subnational.py`, California and Florida occurrence deaths | Two real count studies; severe interval undercoverage; not adjusted risk disparities |
| Human host association evidence | `genetics.py`, released HGI A2/B2 selected statistics | Shared samples and LD; no independent genetic replication or genome-wide scan |
| Viral lineage evidence | `lineages.py`, archived national weighted CDC series | Unreliable cells suppressed; sequencing-selection bias; overlapping lineage labels |
| Original learned forecasts | `network.py`, six outcome heads, three trained seeds | Mixed CRPS and poor pandemic calibration; retrospective source vintage |
| Hierarchical dynamic forecasts | `dynamic.py`, fitted level/slope model and Gaussian slope prior | Exploratory reused test set; three outcome losses and boundary fits |
| Candidate policy analysis | `causal.py`, real group-time/pretrend/placebo tables | Identification not established; unsupported late-cohort cells withheld |
| Twelve studies | `studies.py`, twelve executed JSON and CSV tables | S04 remains partial in occupational outcome support |
| Atlas and exports | TypeScript maps, linked comparisons, source library, study and vintage CSVs | Browser evidence covers bounded paths, not every combination or exhaustive accessibility conformance |
| Independent verification | `verification.py`, `verification_extension.py`, `verify_history.py` | Exact source and inputs required; engineering diagnostics cannot certify missing scientific work |

The full profile returns nonzero while mandatory evidence is incomplete. [Build status](BUILD_STATUS.md), [findings](FINDINGS.md) and the [extension report](EXTENSION_RESULTS.md) retain failures and narrower supported conclusions.

The [historical extension](HISTORICAL_RESULTS.md) reports archived support by outcome and test year. Historical availability gaps and model calibration remain open. The [work and education](MEASUREMENT_RESULTS_V4.md) and [public health](SURVEILLANCE_RESULTS_V5.md) extensions report additional independently replayed measurements.
