# Architecture

The historical extension separates edition-month information sets from final target truth. [Editable origin diagram](diagrams/20-historical-origin.dot), [rendered diagram](diagrams/20-historical-origin.svg), [protocol](HISTORICAL_PLAN_V3.md) and [results](HISTORICAL_RESULTS.md) describe the two-year endpoint horizon, missingness and independent reconstruction. Browser partition verification checks consistency with the loaded snapshot index before parsing or caching data.

The defining core is source-bound measurement reconciliation, temporal forecasting, explicit causal support checks and independent replay. Libraries provide serialization, projections and numerical primitives. Source bytes, measurement estimates, predictions and causal claims remain distinct.

Acquisition is serial, byte-bounded and resumable. Typed observations are streamed into Arrow batches and queried through bounded DuckDB views. Source-specific biological, survey and excess-mortality pipelines write separate artifacts. A disclosure-filtered exporter creates the actual client snapshot. Static hosting and the loopback API share the public boundary.

The network is trained from random initialization with an authored forward pass, masked likelihood, analytic gradients and Adam. Chronological country splits and training-only scaling prevent reference-year leakage. Current-vintage data still limits claims about historical information availability.

The independently implemented verifier reconstructs included measurements from frozen upstream bytes, checks feature chronology, recomputes scores and directly replays parameter arrays. Rehashing a mutated file is insufficient to pass it.

## Editable diagrams

Each source below is checked by Graphviz rendering and SVG XML inspection. These diagrams describe implemented paths and explicit unavailable states, not proposed evidence of success.

- [System context](diagrams/01-system-context.dot) · [rendered SVG](diagrams/01-system-context.svg)
- [Runtime components](diagrams/02-components.dot) · [rendered SVG](diagrams/02-components.svg)
- [Ownership boundaries](diagrams/03-ownership.dot) · [rendered SVG](diagrams/03-ownership.svg)
- [Event time and acquisition time](diagrams/04-source-timing.dot) · [rendered SVG](diagrams/04-source-timing.svg)
- [Additive crosswalk contract](diagrams/05-crosswalk.dot) · [rendered SVG](diagrams/05-crosswalk.svg)
- [Survey estimation and disclosure](diagrams/06-survey.dot) · [rendered SVG](diagrams/06-survey.svg)
- [Host association interpretation](diagrams/07-host-genetics.dot) · [rendered SVG](diagrams/07-host-genetics.svg)
- [Forecast information sets](diagrams/08-split.dot) · [rendered SVG](diagrams/08-split.svg)
- [Three different questions](diagrams/09-inference-separation.dot) · [rendered SVG](diagrams/09-inference-separation.svg)
- [Interruption and recovery](diagrams/10-recovery.dot) · [rendered SVG](diagrams/10-recovery.svg)
- [Bounded runtime concurrency](diagrams/11-concurrency.dot) · [rendered SVG](diagrams/11-concurrency.svg)
- [Persistent artifact lifecycle](diagrams/12-persistence.dot) · [rendered SVG](diagrams/12-persistence.svg)
- [Independent semantic verification](diagrams/13-evidence.dot) · [rendered SVG](diagrams/13-evidence.svg)
- [Static and local deployment](diagrams/14-deployment.dot) · [rendered SVG](diagrams/14-deployment.svg)
- [Independent correctness oracles](diagrams/15-test-oracles.dot) · [rendered SVG](diagrams/15-test-oracles.svg)
- [Numerical prediction paths](diagrams/16-model-math.dot) · [rendered SVG](diagrams/16-model-math.svg)
- [Identity and coverage inventory](diagrams/17-coverage.dot) · [rendered SVG](diagrams/17-coverage.svg)
- [Candidate treatment structure and threats](diagrams/18-treatment-structure.dot) · [rendered SVG](diagrams/18-treatment-structure.svg)
- [Exploratory hierarchical dynamics](diagrams/19-dynamic.dot) · [rendered SVG](diagrams/19-dynamic.svg)
