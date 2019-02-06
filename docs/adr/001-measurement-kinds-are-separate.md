# ADR 001: Measurement kinds are separate

Status: accepted for the research preview.

## Context

A common numeric value column simplifies storage but can hide whether a value is observed, surveyed or modeled.

## Decision

Keep an explicit measurement kind in every observation and separate DuckDB views for observations, modeled estimates, surveys, policy and imputation. Biological and WHO excess artifacts have dedicated schemas.

## Consequences and rejected alternative

A universal daily table was rejected because annual estimates, report weeks and survey waves do not share a sampling or timing contract. Consumers must retain units and kinds through export.
