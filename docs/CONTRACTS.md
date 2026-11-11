# Measurement and numerical contracts

## Ownership and identities

`Observation` owns immutable scalar values and source identities. The Arrow file owns serialized records; DuckDB creates bounded in-memory views over that file. The public exporter owns a separate disclosure-filtered artifact tree. The HTTP server serves only the built tree and approved annual metric files. Raw sources, checkpoints and local accounting are outside its document root.

A measurement key is region, metric, event start, event end, group and vintage. Duplicate populations within a vintage are rejected. Source hashes identify exact upstream bytes. Publication and acquisition timestamps are distinct concepts. Current acquisition times conservatively bound availability. They do not retrospectively date annual values to their reference years.

## Units and kinds

Cases and reported deaths are signed weekly reports, allowing negative corrections. Blank cells stay absent. WHO excess deaths are modeled estimates. WDI crude mortality and life expectancy are demographic estimates; routine DTP coverage is modeled WHO/UNICEF coverage; employment is an ILO modeled ratio. Real GDP is constant 2015 USD per person. Gross secondary enrollment can exceed 100 percent. No annual value is silently interpolated to a weekly observation.

Survey estimates retain instrument, US source-defined group, phase, interval and provider suppression. Provider-released aggregates are relayed as such; derived small-group estimates need independently known sample support. Unknown sample sizes are not reverse-engineered from confidence intervals.

## Time and geography

Event dates use ISO calendar strings. Availability timestamps require a timezone. Country timezones are not inferred from a single capital coordinate. Current World Bank identifiers do not establish historical sovereignty or stable borders. Registry validity intervals are unknown where no crosswalk evidence is supplied. `crosswalk` accepts only additive nonnegative quantities and allocation weights that conserve each source exactly once. Rates need numerator and denominator reconstruction.

New York City and New York excluding the city remain distinct CDC jurisdictions. State-of-occurrence death counts are not joined to residence denominators. The California and Florida comparisons therefore remain counts, not age-adjusted state risk contrasts.

## Precision and failure

Scientific computation uses CPU float64. Count IRLS rejects negative observations rather than clipping surveillance corrections. Gaussian spreads must be positive. Regression and covariance computations retain their declared ridge and numerical floors. `NaN` and infinity are rejected at JSON and observation boundaries. Missing arrays use explicit masks internally and nulls publicly.

Atomic files are flushed and renamed on the same filesystem. Acquisition and panel locks reject competing writers. A failed acquisition keeps earlier successful source partitions and records the error. Training checkpoints include parameters, Adam moments, RNG, epoch, data identity and protocol identity. Restore refuses identity changes. Checkpoint ZIP expansion and model dimensions are bounded.

## Forecast and causal separation

The network predicts transformed annual changes using four preceding annual lags. Training normalization and calibration exclude held-out countries and future target years. GDP uses log1p scoring; displayed levels and intervals use the inverse transform. Calibrated 90 percent bands are predictive intervals, not credible causal effects.

The school-closure group-time estimator reports computable contrasts under explicit assumptions. Insufficient groups receive null estimates. Non-rejection of pretrends does not establish parallel trends. Policy bundles, reverse causation, anticipation and spillovers prevent the current candidate from being presented as identified causal evidence.
