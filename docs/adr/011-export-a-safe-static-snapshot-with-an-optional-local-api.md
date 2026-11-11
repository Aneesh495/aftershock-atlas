# ADR 011: Export a safe static snapshot with an optional local API

Status: accepted for the research preview.

## Context

A useful research demonstration should not require a running database or participant data in a browser.

## Decision

Export actual derived public JSON and run selection, maps, curves and CSV in TypeScript. The loopback server provides bounded optional annual queries over the same public data.

## Consequences and rejected alternative

Static deployments do not pretend to provide the Python API. Snapshot version and source identities are visible. Provider suppression applies before data reaches browser cache or exports.
