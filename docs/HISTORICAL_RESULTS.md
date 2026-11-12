# Official-edition historical replay

Status: executed exploratory engineering pilot. A new source-frozen campaign is pending. The earlier releases and their retrospective results remain preserved.

## Information actually available

The [registered version 3 protocol](HISTORICAL_PLAN_V3.md) selects six official World Bank WDI archive editions, from November 2018 through December 2023. Forty-two metric/edition partitions and the catalogue are frozen by byte hash. The panel contains 227,850 country/year/metric/edition cells, including missing cells. It withholds 399 nonmissing future-reference values from lag features and historical observation displays. Their raw values remain auditable.

Each test target Y uses four reference years Y-5 through Y-2 from the edition selected at the end of Y-1. An unreported endpoint excludes that outcome. Today's data never fill an archived feature. Current frozen data provide test truth, using their own GDP index anchor. The initial 201811 edition supplies both training and validation labels. These earlier labels are retrospective information known at that edition, rather than simulated forecasts issued in each training year.

The provider archive month is a conservative edition bound. It does not establish an original cell publication day, independent witnessed release or stable historical borders. Current country identifiers remain an explicit geographic limitation. The provider also warns that current indicator metadata may describe old editions incorrectly. GDP is therefore internally indexed to 2010=100 separately within every edition. The index removes constant price-base scaling, but methodological, denominator and territorial revisions remain possible. Its model score uses log1p index units and cannot be compared numerically with version 1 dollar scores.

## Executed pilot

The pilot used 4,001 eligible country-year rows: 1,638 training, 479 validation and 1,235 test rows. Five classical baselines, three freshly initialized network seeds and three untrained controls produced 66 family/model configurations and 42,097 test predictions. The saved table contains 12,067 country, year and held-out-country score groups. The three learned seeds stopped after 68, 52 and 57 epochs. No additional fitting or protocol change followed test review.

| Outcome | Validation-selected baseline | Mean learned CRPS improvement | Country-cluster 95% interval |
| --- | --- | --- | --- |
| Employment | Damped level/slope, two-step | -0.04% | -0.94% to 0.91% |
| Indexed GDP per person | Damped level/slope, two-step | -41.27% | -55.62% to -28.03% |
| Secondary enrollment | Damped level/slope, two-step | 1.58% | -2.75% to 5.00% |
| DTP coverage | Damped level/slope, two-step | 9.61% | 5.78% to 13.33% |
| Crude mortality | Damped level/slope, two-step | -2.50% | -5.59% to -0.01% |
| Life expectancy | Pooled ridge | -2.93% | -4.80% to -1.54% |

Positive improvement means lower CRPS than the baseline chosen using validation data. Intervals use 999 country-cluster replicates, and each family has its own units. Only DTP meets the registered five-percent improvement and positive-interval criterion. This is an exploratory comparison using calendar outcomes already inspected in earlier protocols. It is not a blinded confirmation.

| Eligible test outcomes | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
| --- | --- | --- | --- | --- | --- | --- |
| Employment | 187 | 187 | 187 | 186 | 184 | 179 |
| Indexed GDP | 186 | 192 | 184 | 177 | 191 | 190 |
| Secondary enrollment | 5 | 47 | 50 | 51 | 46 | 49 |
| DTP coverage | 192 | 192 | 192 | 0 | 193 | 192 |
| Crude mortality | 0 | 0 | 0 | 194 | 0 | 0 |
| Life expectancy | 0 | 0 | 0 | 194 | 0 | 0 |

These zeros are actual source support, not software errors or zero effects. A family score for mortality or life expectancy describes the 2022 cohort only. Sparse enrollment support further limits cross-country conclusions. The model cannot acquire information by filling these gaps from later editions.

The change from version 1 also changes forecast horizon, training period, GDP transformation and information set. A performance difference between versions cannot be attributed solely to data revisions. The separate endpoint-sensitivity table compares designated archived, initial-edition and current endpoints without feeding current values into model inputs.

## Independent replay and failure boundaries

The pilot receipt `evidence/history-pilot/CHECKS-v2.json` independently parsed all 43 source partitions, reconstructed all 227,850 typed cells and 27,342 early/late revision comparisons, rebuilt feature populations and training normalizers, replayed all saved historical predictions and recomputed score groups, baseline selection and cluster intervals. Later source changes require a new clean campaign. This pilot receipt does not certify those later changes.

The new verifier also checks every endpoint-sensitivity cell, direction-change summary, fresh network initialization and two-step baseline covariance. Rehashed tamper controls substitute a later archive, forge an edition bound, inject a future target into a lag, and change a GDP anchor. The complete campaign retains the original controls and adds a forged full-pass claim. Actual rejection receipts will be recorded by the new campaign, rather than inferred from these recipes.

`configs/full-scope.json` freezes the implementation's unsupported gates. A saved acceptance record cannot promote them by changing booleans. The full campaign executes independent checks and tamper subprocesses, then preserves a nonzero result with `full_acceptance=false` while required scope remains incomplete. Its verifier command has no option to bypass the domain gates.

## Reproduction

```sh
make history-data
make history-panel
make history-fit
make history-atlas
make atlas
make build
make demo
```

Use the Historical editions view to select an outcome, two editions and two countries. Exports retain both missing and observed country/year keys, exact upstream hashes, month bounds, units and executable source. Reverse the edition order to inspect a signed comparison in the other direction. The fixed revision study remains 201811 versus 202312 regardless of the current selector.

The deterministic history input ZIP contains public aggregate archive bytes, source identities and rights. It contains no respondent records. Restoration checks the entire member set, expansion bound, manifest identity and every source hash before accepting data. The local prepared-archive round trip restored all 43 partitions; remote release restoration remains pending publication.
