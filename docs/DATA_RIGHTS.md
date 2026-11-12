# Source, rights and model cards

`configs/data-inputs.json` freezes URLs, acquired byte hashes, acquisition timestamps, rights, source-specific timing and exclusions. `make data` retains successful source files under content-addressed names. Raw inputs are excluded from Git. Core release snapshots include only inputs marked for redistribution.

| Source | Scope and measurement | Rights and public handling |
| --- | --- | --- |
| [WHO surveillance](https://data.who.int/dashboards/covid19/data) | Cases and deaths by report week; revisions and blank reports retained | Attribution and WHO dashboard terms; no endorsement |
| [WHO excess mortality](https://www.who.int/data/sets/global-excess-deaths-associated-with-COVID-19-modelled-estimates) | May 2022 and May 2023 modeled 2020-2021 estimates; reported/predicted input labels | CC BY-NC-SA 3.0 IGO; derived tables retain these terms |
| [World Bank indicators](https://datahelpdesk.worldbank.org/knowledgebase/articles/898581) | Current-vintage annual estimates, national accounts and school enrollment | [CC BY 4.0 with additional terms](https://datacatalog.worldbank.org/public-licenses); upstream attribution retained |
| [Oxford final policy dataset](https://github.com/OxCGRT/covid-policy-dataset) | National total majority-population policy coding, 2020-2022 | CC BY 4.0; cite Hale and colleagues |
| [CDC mortality](https://data.cdc.gov/d/muzy-jte6) | Weekly state-of-occurrence counts; final pre-period and provisional pandemic period | US Government public domain; source flags retained |
| [CDC Household Pulse estimates](https://data.cdc.gov/d/8pt5-q6wp) | Published weighted symptom estimates; US national and state groups | US Government public domain; no raw respondents or new cross-tabs |
| [CDC viral estimates](https://data.cdc.gov/d/jr58-6ysp) | Frozen June 20, 2025 weighted national publication; unreliable cells suppressed | US Government public domain; overlapping lineage labels not summed |
| [HGI release 7](https://www.covid19hg.org/results/r7/) | Public selected A2/B2 aggregate variants, GRCh38 | [HGI terms](https://www.covid19hg.org/about/); acknowledge HGI; no reidentification or full genome-scan presentation; raw downloads acquired separately |
| [Google mobility](https://www.google.com/covid19/mobility/data_documentation.html) | UK national daily workplace and residential aggregates, 2020-2022 | Google Community Mobility terms and attribution; raw downloads acquired separately |
| [Natural Earth / world-atlas](https://github.com/topojson/world-atlas) | Coarse cartographic reference | Natural Earth public domain; world-atlas ISC |

Google LLC, Google COVID-19 Community Mobility Reports, accessed November 11, 2026. Source methodology changes and opt-in sampling are retained. The series is not a representative employment or hours survey. Cross-country mobility comparisons are not made.

The selected HGI variants are not independent observations. A2 and B2 share samples, phenotype nesting and controls. One representative per 1 Mb display bin is not LD clumping. Selected-set BH adjustments cannot establish genome-wide FDR. No reference build conversion, ancestry inference, individual prediction or explanation of national genetic differences is attempted.

## Historical editions and public-use survey handling

`configs/history-inputs.json` separately freezes 43 WDI archive partitions, including the edition catalogue and seven indicators in six official editions. These public country aggregates retain World Bank CC BY 4.0 with additional source terms. The [archive documentation](https://datatopics.worldbank.org/world-development-indicators/wdi-archives.html) warns that current metadata may replace historical definitions. GDP is indexed within each edition to avoid asserting an unverified historical dollar price base. Edition-month bounds are provider designations, not witnessed original cell release days.

`configs/survey-inputs.json` identifies the lawful Census week 1 public-use ZIP and method statement. The U.S. Government release is public use; no reidentification is attempted. The respondent ZIP remains in ignored local storage and is excluded from release snapshots, examples and evidence. Only disclosure-checked aggregates enter those artifacts. The core input snapshot remains the original immutable v0.1.0-preview archive; the historical archive snapshot contains WDI aggregates only.

## Model card

The primary original model is a shared tanh temporal network with six Gaussian outcome heads. Four lagged annual levels per outcome and missingness masks form 48 inputs; the shared layer has 48 hidden units. Adam starts from random initialization at seeds 11, 29 and 47. Loss uses observed outcome masks and country-balanced training weights. Validation chooses stopping and interval calibration. Training checkpoints preserve optimizer and RNG state.

The intended use is research on retrospective aggregate trajectories. It is unsuitable for clinical decisions, personal risk predictions, group ranking or policy optimization. Chronological tests use today's vintage and do not prove historical deployability. Pandemic drift causes severe interval undercoverage for some targets. Classical baselines and untrained controls remain visible.

## Dependencies

NumPy supplies array primitives, SciPy supplies numerical distributions and special functions, Arrow supplies columnar serialization, DuckDB supplies queries, openpyxl supplies workbook reading, and pycountry supplies reference identifiers. The forecasting network, gradients, optimizer, count IRLS, state filter, harmonization, study logic and verifier are authored in this repository. The client uses TypeScript, Vite, d3-geo projection primitives and topojson-client geometry decoding. Locked dependency versions are in `uv.lock` and `client/package-lock.json`.
