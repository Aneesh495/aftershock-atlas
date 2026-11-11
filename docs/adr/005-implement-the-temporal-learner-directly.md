# ADR 005: Implement the temporal learner directly

Status: accepted for the research preview.

## Context

A downloaded forecasting model would not demonstrate learning or permit exact gradient and sampler replay.

## Decision

Implement tanh features, six Gaussian heads, masked country-balanced loss, analytic gradients and Adam with NumPy primitives.

## Consequences and rejected alternative

This keeps the defining temporal engine visible and testable. It adds numerical responsibility, including finite-difference tests, nonfinite checks, optimizer restore and interval calibration failure reporting.
