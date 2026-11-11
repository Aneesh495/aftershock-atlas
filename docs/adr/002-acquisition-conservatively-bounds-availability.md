# ADR 002: Acquisition conservatively bounds availability

Status: accepted for the research preview.

## Context

Reference years are easy to mistake for release dates, especially in revised annual sources.

## Decision

Use acquired_at and available_at with exact source bytes. As-of queries return no historical value when archived availability is absent.

## Consequences and rejected alternative

This prevents an unsupported historical deployment claim. It also means current-vintage model tests cannot satisfy full as-of forecasting acceptance.
