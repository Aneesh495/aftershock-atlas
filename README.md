# Aftershock Atlas

Aftershock Atlas compares population-level pandemic-era trajectories while preserving data definitions, revisions, uncertainty, and the boundary between description, prediction, and causal evidence.

This repository is under active construction. See [build status](docs/BUILD_STATUS.md) for executed work and incomplete gates. It is broader than mortality forecasting: employment, economic output, education, health service coverage, surveys, policy, and aggregate biological evidence have distinct contracts.

## Development

Python 3.13, uv, Node 24, npm, Git, and Graphviz are used. Dependencies and acquisition limits are pinned. No participant records or individual genomes are used.

```sh
make bootstrap
make doctor
make data
make panel
make fit
make forecasts
make causal
make studies
make atlas
make demo
```

Publication and results will be documented only after they are verified.
