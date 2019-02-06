# ADR 003: Stream into Arrow and query with bounded DuckDB

Status: accepted for the research preview.

## Context

The global panel is larger than a useful hand-edited CSV and source files revise.

## Decision

Validate immutable typed records in 8192-row batches, atomically replace the panel and expose bounded DuckDB views.

## Consequences and rejected alternative

An unbounded in-memory dataframe merge was rejected. Complete rebuilds cost more CPU but make duplicate identities, source revisions and failed writes auditable.
