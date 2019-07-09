# UK quarterly growth forecasts

The UK forecast uses the preceding quarter's archived national accounts edition. Every target is the first estimate from a subsequent publication. Training on 72 quarters and validation on 11 use one workbook released in November 2021. The nine calibration residuals come from distinct archived first estimates. The eight test quarters are 2024Q1 through 2025Q4. No model was selected by a test score.

| Model | Test MAE, percentage points | Full 90% interval width, percentage points | First estimates covered |
| --- | ---: | ---: | ---: |
| Zero growth, validation-selected baseline | 0.329 | 1.926 | 8/8 |
| Persistence | 0.338 | 1.710 | 7/8 |
| Four-quarter mean | 0.278 | 4.434 | 8/8 |
| Same quarter a year earlier | 0.285 | 11.274 | 8/8 |
| Ridge, penalty 1 | 0.338 | 3.423 | 8/8 |
| Ridge, penalty 10 | 0.320 | 2.643 | 8/8 |
| Ridge, penalty 100, validation-selected | 0.295 | 1.185 | 8/8 |

The selected ridge has lower absolute error and narrower intervals than the validation-selected zero baseline on this sequence. The four-quarter mean has the smallest observed MAE. The eight-of-eight coverage count has a 95% exact binomial interval of approximately 63% to 100%, before accounting for dependence. Calibration uses the largest of nine absolute residuals. These results establish dated forecast support for one economy. They leave the demonstrated multinational mortality and life expectancy undercoverage unresolved.

[Registered calibration protocol](FORECAST_CALIBRATION_PLAN_V9.md) · [ONS real-time release archive](https://www.ons.gov.uk/economy/grossdomesticproductgdp/datasets/realtimedatabaseforukgdpabmi)
