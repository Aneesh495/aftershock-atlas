# Requirement and artifact map

This inventory describes implemented measurement and missing scope. A domain name on a page does not establish complete measurement.

| Requirement | Implemented artifact | Current limit |
| --- | --- | --- |
| Global COVID reports | `panel.py`, WHO signed weekly cases/deaths | No tests, hospital or ICU series; changing reporting remains a limitation |
| COVID vaccine rollout | None | Routine DTP coverage is a different health-service outcome |
| Excess mortality and revisions | `excess.py`, WHO May 2022 and May 2023 | Modeled 2020-2021 estimates, not observed daily deaths |
| Geography and denominators | `geography.py`, current registry and additive crosswalk contract | Historical split/merge source validation incomplete; no invented residence denominator for occurrence counts |
| Historical information sets | `temporal.py`, conservative acquisition availability | Annual final-vintage records cannot establish available-at-time forecasts |
| Employment and output | `features.py`, WDI employment ratio and constant-price GDP per person | No working-hours or sector series; annual frequency only |
| Education | WDI gross secondary enrollment and Oxford school policies | No learning assessment or remote-instruction outcome; enrollment does not measure either |
| Mobility exposure | `mobility.py`, UK daily aggregates | Opt-in device sample, no worker denominator or occupational exposure claim |
| Mental-health instruments | `survey.py`, NCHS published US waves | Reference period changes in July 2021; no matched pre-pandemic comparison |
| Actual survey weighting | `survey_design.py`, Census week 1 PUF and 80 replicates | One wave; two combined-symptom agreement failures; selection bias unresolved |
| Source-defined group denominators | Twenty-four week 1 national/sex/race-origin cells | No universal racial schema; full multiwave socioeconomic/age contextual audit incomplete |
| Subnational studies | `subnational.py`, California and Florida occurrence deaths | Two real count studies; severe interval undercoverage; not adjusted risk disparities |
| Human host association evidence | `genetics.py`, released HGI A2/B2 selected statistics | Shared samples and LD; no independent genetic replication or genome-wide scan |
| Viral lineage evidence | `lineages.py`, archived national weighted CDC series | Unreliable cells suppressed; sequencing-selection bias; overlapping lineage labels |
| Original learned forecasts | `network.py`, six outcome heads, three trained seeds | Mixed CRPS and poor pandemic calibration; retrospective source vintage |
| Hierarchical dynamic forecasts | `dynamic.py`, fitted level/slope model and Gaussian slope prior | Exploratory reused test set; three outcome losses and boundary fits |
| Candidate policy analysis | `causal.py`, real group-time/pretrend/placebo tables | Identification not established; unsupported late-cohort cells withheld |
| Twelve studies | `studies.py`, twelve executed JSON and CSV tables | Four remain partial in outcome or design support |
| Atlas and exports | TypeScript maps, linked comparisons, source library, study and vintage CSVs | Browser evidence covers bounded paths, not every combination or exhaustive accessibility conformance |
| Independent verification | `verification.py`, `verification_extension.py` | Exact source and inputs required; engineering diagnostics cannot certify missing scientific work |

The full profile returns nonzero while mandatory evidence is incomplete. [Build status](BUILD_STATUS.md), [findings](FINDINGS.md) and the [extension report](EXTENSION_RESULTS.md) retain failures and narrower supported conclusions.
