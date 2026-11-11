# ADR 009: Reuse provider survey estimates without inventing design information

Status: accepted for the research preview.

## Context

Published weighted estimates do not expose response denominators, weights or PSUs.

## Decision

Retain provider labels, phases and intervals. Limit contrasts to within phases; use conservative interval envelopes for unknown covariance. Ship and test design-weight arithmetic separately without claiming real recomputation.

## Consequences and rejected alternative

Public participant records were not acquired. Independent design and nonresponse gates remain blocked rather than being replaced by unweighted approximations.
