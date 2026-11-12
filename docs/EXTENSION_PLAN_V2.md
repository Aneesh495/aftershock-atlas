# Extension protocol, version 2

Registered after reviewing version 1 test results. Version 1 source b6876777275d9696fcbd4c28bc669151552ba4ae and its release remain available. This extension is exploratory. Reusing 2019-2024 outcomes does not create a fresh confirmatory test.

## Survey design reproduction

Use the Census public-use week 1 archive, April 23 through May 5, 2020, and its original 80 person replicate weights. Stream ZIP members without writing decompressed records. Join on the provider's SCRAM and WEEK keys, reject duplicates and missing partners, and remove the keys before producing any artifact. No respondent records, individual weights or identifiers enter evidence, client assets or release archives.

Recompute GAD-2 and PHQ-2 positivity with both required items coded 1-4, subtracting one before summation, threshold 3. The combined estimate requires all four items. Separately retain denominator exclusions and weighted item missingness. Compare national and source-defined sex and race/Hispanic-origin cells with the independently published NCHS week 1 values. Point agreement tolerance is 0.15 percentage points, registered before execution. Differences remain visible; no denominator is changed to force agreement.

The successive-difference variance is 4/80 times the sum of squared differences between replicate estimates and the full-weight estimate. Publish 95 percent normal sampling intervals, point differences and their limitations. These intervals do not reproduce all NCHS presentation-standard transformations. No clinical interpretation or global racial schema is permitted. Groups with fewer than 100 complete respondents are suppressed, including estimates, intervals and denominators. Report unweighted response fraction 74,413/1,867,126 separately from the provider's 3.8 percent weighted unit response rate. Neither quantity is the fraction of the adult population represented by the calibrated person weights. Nonresponse scenarios shift nonrespondent symptom prevalence by -10, -5, +5 and +10 percentage points using the reported weighted response rate. These are sensitivity scenarios, not identified population bounds.

Recognize the reference-period change on July 21, 2021 from 7 to 14 days and preserve wave boundaries. A one-week design replay cannot validate weights for all later waves. It cannot estimate pre-pandemic change or nonresponse bias from participant records alone.

## Hierarchical dynamic forecast extension

Keep version 1 splits, six outcomes, transforms, country weights, four-lag information set and validation calibration. Add an original two-state damped trend filter. Each window has a latent level and slope. Slopes share an empirical Gaussian prior learned on training countries/years; all countries share estimated process and observation variances. Missing lags skip measurement updates. The transition is level plus damped slope, with slope damping phi in [0,1]. Gaussian updates propagate covariance and observation uncertainty.

Fit the slope-prior mean and variance, two process variances, observation variance and damping using weighted conditional one-step Gaussian likelihood on training targets only. Three deterministic starts use phi 0.2, 0.7 and 1.0; maximum 150 L-BFGS-B iterations each. Select the finite fit with lowest training objective. Record convergence failures and boundary solutions. Do not tune on validation or test scores. Calibrate 90 percent bands using retained-country validation residuals only. Score all eligible version 1 test rows, countries and years; compare with each family's frozen version 1 validation-selected baseline. Report CRPS, log score, coverage and interval score separately by family. The 5 percent practical criterion remains descriptive in this exploratory extension.

## Resources and verification

Reserve 300 MB before the 60 MB capped ZIP acquisition. Enforce at most 120 MB total ZIP expansion while streaming, 100,000 records, 80 replicates, one active acquisition and no decompressed disk copy. Model fits reserve 100 MB and have a ten-minute stage timeout. The 5 GB project and 400 GB writable-volume caps remain binding. Cost is zero. Stop on integrity, join, finite-value or budget failures. Resume with `make survey-data`, `make surveys`, and `make dynamic`.

Independent replay must re-read the frozen public-use ZIP outside the evidence directory, reconstruct weighted numerators, denominators and replicate variances using a separate implementation, and reject altered denominators or variance factors. Replay dynamic predictions from saved parameters with a separately coded scalar covariance recurrence. Preserve both original results and extension outcomes, including losses and interval failures.

## Primary methods

- [Census public-use releases](https://www.census.gov/data/datasets/time-series/demo/hhp/2020.html)
- [Census phase 1 source and accuracy statement, pages 4-5, 8 and 11](https://www2.census.gov/programs-surveys/demo/technical-documentation/hhp/Source-and-Accuracy-Statement-June11-June16.pdf)
- [NCHS instrument, scoring and reference-period change](https://www.cdc.gov/nchs/covid19/pulse/mental-health.htm)
