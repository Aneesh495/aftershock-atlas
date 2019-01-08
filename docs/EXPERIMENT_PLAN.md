# Frozen experiment protocol, version 1

This protocol is frozen before model fitting. Current acquired vintages do not establish historical availability. All evaluations in this version are retrospective final-vintage exercises. As-of deployment parity and alternate real source vintages remain separate requirements.

## Forecast hypotheses

The prespecified learned comparison asks whether a shared temporal network improves within-family CRPS over the strongest validation-selected classical baseline. A practical improvement is at least 5 percent in mean CRPS, with country-cluster bootstrap intervals excluding zero. Failure to improve is retained. No score pools unrelated target scales.

Six annual outcomes are employment ratio, real GDP per capita, secondary enrollment, routine DTP coverage, crude mortality and life expectancy. Each has at least four preceding annual observations or explicit missingness. GDP is transformed with log1p. The target is the transformed next value minus the latest known value. Features contain four lagged levels for every outcome and explicit missing indicators. Means and scales are fitted on training countries and years only.

Training target years: 2004-2015. Validation target years: 2016-2018. Frozen test years: 2019-2024. Country assignment is SHA256(country) modulo five; bucket zero is held out from all fitting and calibration. Countries with missing targets are retained through outcome masks, not filled. Country weights equalize total contribution within the training population. Test records report temporal and held-out-country groups separately.

Models: persistence, four-lag linear trend, pooled ridge, local-level filter, and an original shared tanh network with Gaussian outcome heads. The network uses 48 hidden units, Adam, learning rate 0.003, batch size 256, maximum 300 epochs, 40 epochs validation patience, gradient clipping at 5, and seeds 11, 29, 47. Untrained seed controls are evaluated. Validation calibrates absolute standardized residual quantiles for 90 percent intervals. Calibration does not promise exchangeability under pandemic drift. Save initialized parameters, optimizer, RNG, best epoch, loss history, transformed predictions and row identities.

Primary scoring: per-family CRPS. Secondary: MAE, RMSE, Gaussian log score, 90 percent interval coverage and interval score. GDP scores use log1p units; raw GDP intervals are inverse-transformed. Inspect per-country and per-year errors. At least 30 nonempty outcome/model configurations must execute, with all three trained seeds retained.

## Predictive no-shock scenarios

Fit local linear pre-2020 trends from 2010-2019, compare with a local-level alternative, and propagate fitted residual uncertainty with horizon. These are predictive extrapolations of an earlier regime. They do not identify pandemic effects. Observed COVID reports have no pre-pandemic comparable series and do not receive invented pre-2020 observations.

## Candidate causal analysis

Candidate exposure is the first national Oxford school closure at level 3. Adoption is a policy coding date, not an adherence or effective exposure date. Outcome is annual employment, measured as a modeled estimate. The intended estimand is the group-time average effect on adopting countries compared with not-yet-treated countries. Require at least five treated and five eligible controls per cell, three pre-period outcomes, no pretrend rejection at 0.05, and a nonempty comparison group for the outcome year. If all countries are exposed before the annual outcome period ends, the design is unsupported. Produce diagnostics and descriptive event contrasts without relabeling them causal. Spillovers, anticipation and policy bundles are unresolved. Pseudo-onsets shifted two years, leave-region-out checks and sensitivity to unmeasured differential trends are retained.

## Resource and stopping rules

CPU diagnostic profile: two numerical threads, 512 MB DuckDB memory, 256 MB maximum spill, bounded source downloads, under 5 GB attributed project storage and under 400 GB writable-volume use. Reserve 350 MB before panel construction and 200 MB before fitting. Model checkpoints remain under 20 MB total. Per-stage timeout is ten minutes; a timeout is failed work. Acquisitions are serial with three bounded HTTP attempts. No paid compute is authorized.

The full profile additionally requires all domain gates, actual historical-vintage evaluation, survey design diagnostics, real age-denominator validation, complete biological checks, independent source-bound replay and a verified interactive walkthrough. A successful diagnostic profile cannot pass the full profile. Missing required work returns nonzero. A changed protocol gets a new version and retains prior results.
