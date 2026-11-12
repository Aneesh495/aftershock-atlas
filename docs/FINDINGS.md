# Findings and limitations

These are executed preview results, not complete acceptance. Inputs are the November 11, 2026 acquisition and two released WHO excess mortality vintages. The frozen primary forecast protocol is version 1.

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

## Data and inference limits

WHO surveillance covers 240 reporting areas, including territories. The annual World Bank panel uses 217 economies, with missing values and source-defined estimates. Current-vintage annual inputs cannot establish historical available-at-the-time forecasts. The geography registry does not prove historical border stability.

The WHO excess releases contain 4656 monthly country cells across 194 countries. Input support is 2459 reported and 2197 predicted cells. Modeled excess mortality is kept distinct from reported COVID deaths. Age bins differ across the two releases, and the later age table omits the earlier Nx denominator field.

The selected HGI analysis aligns 9,443 A2/B2 records after 243 ambiguous-strand exclusions; 9,328 have concordant direction. Cohort overlap and LD prevent independent replication claims. CDC viral estimates and host associations remain separate. Provider unreliable lineage cells are suppressed.

Twelve study tables execute. Eight have bounded analysis support and four have incomplete outcome or design support. A missing hours or learning measure is an unavailable estimand, not a null pandemic effect. The aggregate extract alone cannot establish survey-weight or nonresponse diagnostics. The separate version 2 week 1 public-use replay checks actual person and replicate weights; its later-wave and selection limits remain. School closure contrasts do not identify causal effects under the unresolved policy bundle and interference assumptions.

The California and Florida count-model intervals cover only 43.3% and 35.7% of the held-out 2020-2022 observations against a nominal 90% target. Those failures argue against treating a pre-period seasonal count model as a reliable pandemic counterfactual.

## What is still required

See [build status](BUILD_STATUS.md). In particular, complete historical as-of and geography validation, independent survey design auditing, lawful richer subgroup denominators, hours and learning outcomes, the complete full-profile scientific campaign remain incomplete. A working atlas and a diagnostic verifier pass do not close those requirements.

## Source-frozen replay

The original v0.1.0-preview executable is `b6876777275d9696fcbd4c28bc669151552ba4ae`. The clean-checkout diagnostic is `source-clean-20261111`; full attempt `full-20261111` failed explicitly on incomplete gates. Exact source, inputs, command exits and independent replay quantities are in the preserved bundles.

## Exploratory extension

The [version 2 report](EXTENSION_RESULTS.md) adds actual 80-replicate survey replay and hierarchical dynamic forecasts. It retains two missed survey agreement tolerances, three model-family losses and substantial interval undercoverage. These outcomes do not close full scientific acceptance.

## Official historical editions

The [version 3 report](HISTORICAL_RESULTS.md) uses six official archives with origin-specific inputs and no current-value fallback. It contains 66 separate configurations and 42,097 predictions. Only routine DTP meets the practical CRPS criterion; the learned GDP score is 41.27 percent worse than its validation-selected baseline. Every learned family undercovers nominal intervals. Mortality and life expectancy have eligible archived features only for 2022. A changed horizon, GDP index and training window prevent attributing the differences from version 1 solely to vintage. The final clean diagnostic passed nineteen actual tamper controls; the full profile executed those checks and still returned nonzero on incomplete scope.
