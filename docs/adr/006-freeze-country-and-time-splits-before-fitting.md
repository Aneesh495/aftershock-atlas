# ADR 006: Freeze country and time splits before fitting

Status: accepted for the research preview.

## Context

Random row splits leak country trajectories and future regimes into training.

## Decision

Hash country identifiers into held-out groups and freeze training, validation and test years. Fit preprocessing only on training identities.

## Consequences and rejected alternative

The test is harder under pandemic drift, and missing outcomes leave unequal task support. Those costs are retained; a single pooled accuracy score would conceal them.
