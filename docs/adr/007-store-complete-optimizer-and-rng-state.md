# ADR 007: Store complete optimizer and RNG state

Status: accepted for the research preview.

## Context

Saving weights alone cannot reproduce interruption and restart.

## Decision

Atomically store parameters, Adam moments, epoch, RNG, configuration and exact data/protocol identities. Save initialization and the validation-selected checkpoint separately.

## Consequences and rejected alternative

Checkpoint restore is deterministic and rejects changed identities. A completed early-stop run remains completed when invoked again, preventing accidental extra training after stopping.
