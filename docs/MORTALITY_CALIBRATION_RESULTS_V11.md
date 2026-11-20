# Weekly all-cause mortality forecasting

The feature archive was published in July 2021. Model estimates use weekly counts through 2018 and validate in 2019. The 2022 calibration outcomes come from the August 2023 archive, before the January 2024 forecast origin. The May 2025 and September 2026 archives expose two versions of the 2024 test outcomes. These are archive availability dates from the source repository. They do not establish when every national reporting agency first released a week.

Across 22 eligible countries, the study evaluates 1,144 distinct 2024 weeks and 6,864 model-week predictions. Slovakia lacked a complete evaluation year in the frozen first test archive. Czechia, Italy and the Netherlands supply 156 geographically held-out weeks. They contribute no ridge coefficients, validation decisions or interval calibration. Their frozen pre-2020 histories provide local scales and baseline inputs.

| 2024 group | Selected ridge observed coverage for nominal 90% | Seasonal mean coverage | Ridge normalized MAE | Seasonal mean normalized MAE |
| --- | ---: | ---: | ---: | ---: |
| All 22 countries | 84.9% | 98.95% | 0.093 | 0.078 |
| Three held-out countries | 89.1% | 99.36% | 0.095 | 0.083 |

The selected ridge meets the registered 80% to 99% practical coverage range in both groups. The seasonal mean makes more accurate point forecasts in both groups. The ridge gives narrower intervals. Its normalized interval score is lower for the held-out countries and higher across all countries. The 95% country-bootstrap interval is 75.3% to 92.0% overall and 76.9% to 100% in the held-out countries. Three held-out countries give limited precision. Against the second vintage, ridge coverage was 85.0% overall and 89.7% in held-out countries. Calendar revisions, shifts in reporting and differing national definitions remain limitations.

The weekly observations are all-cause count aggregates divided by fixed 2015 weekly count means for scoring. Earlier miscalibration for selected global annual mortality and life expectancy targets remains documented in the separate annual experiment.

[Mortality calibration protocol](MORTALITY_CALIBRATION_PLAN_V11.md) · [Data paper](https://doi.org/10.7554/eLife.69336) · [Earlier annual results](HISTORICAL_RESULTS.md)
