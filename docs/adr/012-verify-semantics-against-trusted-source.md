# ADR 012: Verify semantics against trusted source

Status: accepted for the research preview.

## Context

Checksums alone allow internally consistent forged results.

## Decision

Implement a separate raw parser, score recomputation, chronological feature reconstruction and direct saved-parameter replay. Require an independently supplied expected Git revision and run rehashed negative controls as subprocesses.

## Consequences and rejected alternative

The verifier cannot fix a missing result, retrain or replace a model. A diagnostic pass establishes tested invariants, while full scientific coverage and identification remain separate gates.
