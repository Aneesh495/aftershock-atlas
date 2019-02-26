# Exploratory extension results

Protocol: [version 2](EXTENSION_PLAN_V2.md). The extension was registered after version 1 test results were reviewed. These comparisons reuse the earlier outcomes and are exploratory. Version 1's [published preview](https://github.com/Aneesh495/aftershock-atlas/releases/tag/v0.1.0-preview) remains unchanged.

## Survey design

The public-use archive contains 74,413 respondents. Each record joined to its matching 80 replicate weights without unmatched or duplicate partners. No decompressed respondent file was written. Only aggregate estimates enter evidence and browser exports. The public-use ZIP remains under ignored `data/private-survey/` and is acquired independently when replaying the verifier.

Twenty-two of 24 national, sex and source-defined race/Hispanic-origin comparisons matched the published point estimate within the registered 0.15 percentage-point tolerance. All anxiety-only and depression-only comparisons matched. The strict four-item combined-symptom denominator missed the tolerance for non-Hispanic White single-race adults (-0.1517 points) and non-Hispanic Asian single-race adults (-0.1564 points). These small discrepancies are retained. Their cause is unresolved; incomplete-item eligibility and publication rounding are possible explanations, not established corrections.

| National measure | Weighted percent | Complete respondents | Weighted adult denominator | Published percent |
| --- | ---: | ---: | ---: | ---: |
| Anxiety symptoms | 30.8348 | 68,813 | 225,223,736 | 30.8 |
| Depressive symptoms | 23.5128 | 68,804 | 225,063,097 | 23.5 |
| Either, four complete items | 35.8428 | 68,643 | 224,610,841 | 35.9 |

The weighted denominator is the adult population represented by complete-item person weights. It is not the count of respondents. The provider's weighted unit response rate is 3.8 percent; the raw respondent/sample fraction is 74,413/1,867,126, about 3.985 percent. They use different definitions. The reported sampling intervals do not account for nonresponse bias. Explicit selection-sensitivity scenarios remain assumptions rather than identified bounds.

The [NCHS technical notes](https://www.cdc.gov/nchs/covid19/pulse/mental-health.htm) document a change from a seven-day symptom reference period to fourteen days on July 21, 2021. Exported survey rows now retain this distinction. A phase boundary breaks the chart rather than treating the instrument change as a continuous comparable series. This one-wave replay does not independently validate all later weights or longitudinal changes.

See the actual browser download [design CSV](media/survey-design-export.csv) and [survey view](media/survey-design.png).

## Hierarchical dynamic model

All 18 deterministic optimization starts converged. Six selected outcome models produced 6,857 test predictions. Several fits reached variance or damping boundaries; boundary indices and every start are retained in `dynamic.json`. A separately coded scalar recurrence replayed all 6,857 means and variances, training likelihoods and validation calibration multipliers.

| Outcome | CRPS improvement versus frozen baseline | Nominal 90% interval coverage |
| --- | ---: | ---: |
| Employment | 1.75% | 75.83% |
| Real GDP per capita | 2.30% | 75.45% |
| Secondary enrollment | -4.74% | 89.45% |
| Routine DTP coverage | 0.28% | 86.08% |
| Crude mortality | -3.58% | 68.66% |
| Life expectancy | -2.14% | 61.21% |

Positive values mean lower CRPS. No family reaches the five-percent practical threshold. The model loses on three outcomes. Its Gaussian uncertainty does not cover pandemic mortality and longevity reliably. These results provide no reason to promote the extension over the frozen baseline.

## Reproduction

```sh
make survey-data
make surveys
make dynamic
make studies atlas
```

The complete diagnostic additionally runs independent source-bound replay and subprocess tamper controls for the survey variance factor, survey denominator and saved dynamic parameters. The extension adds evidence, but full historical availability, wider survey-design validation, richer education and work data, subgroup contextual auditing and full scientific acceptance remain incomplete.
