# Historical-edition protocol, version 3

This extension is exploratory. Version 1 and version 2 outcomes have already been reviewed. The new purpose is to measure historical information-set differences using official archived editions, not to claim a fresh blinded pandemic test. The published v0.1.1-preview and its source 8bd15fb2e9110197f32cf84ada81fd0b533c4371 remain preserved.

## Sources and availability

Use World Bank WDI Database Archives, API source 57, with official edition identifiers. Freeze the provider's version catalogue and the six latest editions at the end of 2018 through 2023: 201811, 201912, 202012, 202112, 202212 and 202312, subject to verifying these exact identifiers are in the catalogue. Query all countries and reference years separately for population and the six existing outcome series. Require complete API pagination, matching source/edition/indicator dimensions, unique country/reference-year keys and finite values. Freeze every upstream byte identity. Do not replace an unavailable edition with today's values.

The provider identifies archive months, not exact original cell release dates. Use the final UTC instant of that month as a conservative edition-month bound and label it as a provider-designated archive, not a cryptographically witnessed original release. The API's current lastupdated date is a retrieval/maintenance property and does not redetermine the historical edition. Current indicator metadata may describe older editions incorrectly. Preserve series labels and warn about definition changes.

Retain current-code country matching as an explicit geographic limit. Exclude source aggregates and unknown identifiers with a ledger; do not invent split/merge mappings. The historical exercise does not independently establish territorial equivalence. Keep all raw future-reference values available for audit, but exclude them from observed lag features and historical observation displays because their projection/nowcast status is not sufficiently specified.

For GDP, use an internally indexed constant-price per-person series with 2010 equal to 100 within each edition. Require a positive 2010 anchor. This removes constant price-base scaling, not methodological or population revisions. Do not label these values as constant 2015 dollars or compare their numerical CRPS directly with version 1's dollar target. GDP model features and targets use log1p of this index. The remaining five outcome units retain their source-defined estimate status, with cross-edition definition caveats.

## Revisions and falsifiable comparisons

Compare jointly observed 2000-2017 cells in the earliest and latest editions, by outcome and country. Publish missingness, signed and absolute revisions, source hashes, edition-month bounds and excluded future-reference values. The null is zero revision for each matched cell; report exact descriptive contrasts without treating archived values as independent samples. Check whether edition changes alter descriptive 2017-versus-2010 trajectory signs. No single revision score pools unrelated units. Keep every disagreement and unmatched cell.

## Forecast information set

Train an initial model using only the 201811 edition. Training target years are 2005-2014, validation 2015-2017, and test target years 2019-2024. Retain SHA256(country) modulo five for held-out countries. Each target year Y uses the edition selected at the end of Y-1 and four reference-year lags Y-5 through Y-2. This deliberately allows a one-reference-year publication lag. The target is the value at Y minus the latest feature value at Y-2, so the forecast horizon from the feature endpoint is two years. Missing endpoints or targets remain masked.

Training and validation labels come only from the initial edition and exclude reference years after its archive month. Test truth uses the frozen current main panel, transformed to the same within-edition GDP index definition using its own 2010 anchor. Also retain test-feature endpoints in the initial/final vintages for revision sensitivity. Test years reuse previously inspected calendar outcomes and remain exploratory. Preprocessing, stopping, calibration, pooled parameters and slope priors exclude held-out countries and test targets.

Fit persistence, four-lag linear trend with a two-year extrapolation, pooled ridge, a local-level filter with two-step variance propagation, and the empirical-Bayes damped level/slope model with two-step state propagation. Reuse the registered network architecture and optimization settings, with fresh initialized models and seeds 11, 29 and 47. Keep untrained controls. Each model family uses the same historical feature population and target mask. Select the strongest classical baseline on validation CRPS separately per outcome, before examining test comparisons.

Score family-specific CRPS, Gaussian log score, MAE/RMSE, calibrated nominal 90 percent coverage and interval score. Publish country, year and held-out-country groups. Compare mean-of-three-seed CRPS with the frozen validation-selected baseline using 999 country-cluster bootstrap replicates and the five-percent practical criterion. Do not tune further when coverage or improvement fails. Stop each learned run at 300 epochs or 40 validation-patience epochs, whichever occurs first. Save initialized, best and restart states and explicit source/feature identities.

## Independent checks and interface

Independently parse raw archive dimensions, all exported historical values and both GDP anchors. Reconstruct every model feature from its target year's designated edition and verify no later edition or final-vintage fallback is present. Recompute normalizers from the initial-edition training population, replay saved model parameters and two-step state recurrences, and recompute scores by unit and population. Add actual rehashed tamper subprocesses for a substituted later edition, a forged archive bound, a future-reference feature and a changed GDP anchor. Preserve their intended rejection reasons.

Add an atlas view with selectable editions, metric and countries; chronology, missing values, indexed GDP units and source drill-down must remain visible. Export the complete selected comparison with exact source identities and definition caveats. Historical files remain partitioned by edition and metric to bound each browser request. Keep the existing published preview and experiment results intact.

## Resource and failure rules

Forty-two data requests are capped at 12 MB each, and the catalogue at 2 MB. Acquisitions are serial and content-addressed. Reserve 30 MB before each request and stop at the existing 5 GB project or 400 GB writable-volume cap. Reserve 250 MB before feature construction, fit and evidence assembly, with no more than 512 MB query memory or 256 MB spill. Each execution stage has a ten-minute timeout, with atomic per-source and per-seed recovery. No paid compute or unattended schedule is authorized. A partial source, unknown archive identity, missing anchor, budget failure or unverifiable timestamp leaves the corresponding claim incomplete.

## Primary documentation

- [Official WDI archive editions and metadata caveat](https://datatopics.worldbank.org/world-development-indicators/wdi-archives.html)
- [World Bank multidimensional archive API](https://datahelpdesk.worldbank.org/knowledgebase/articles/1886686-advanced-data-api-queries)
- [World Bank data licensing](https://datacatalog.worldbank.org/public-licenses)
