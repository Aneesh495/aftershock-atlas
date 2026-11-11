# Failure and recovery

A WHO acquisition that exceeds its byte cap returns a failed source receipt and does not replace the last valid immutable input. A parser that reaches its row cap refuses to assume the extract is complete. This occurred during the lineage pilot: a broad revision query hit the 200,000-row cap. The retained failure led to a source-defined, frozen national weighted publication query, rather than accepting a truncated dataset.

An interrupted atomic write preserves prior bytes. `make stress` injects this failure and checks the old state directly. A saved RNG checkpoint restarts with identical next RNG output. Tests also verify the next optimizer update matches after restore.

The browser shows an unavailable view and a retry action when an actual source file is missing. Previously successful data is not replaced by example values. Rapid outcome changes cancel stale requests. Restoring the source and retrying recovers the ordinary path. API requests cannot read raw or private paths outside the public export boundary.
