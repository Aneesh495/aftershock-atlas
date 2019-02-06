# Reproduction and recovery

## Public snapshot

The tracked public snapshot can run without upstream network access:

```sh
make bootstrap
make build
cp -R client/dist dist
make demo
```

The production server listens on loopback port 8765. It provides bounded annual JSON queries at `/api/observations?metric=employment&regions=USA,GBR&start=2019&end=2023` and CSV exports at `/api/export` with the same query. Static hosting uses the same public JSON files in the browser. Static hosting does not claim to provide the optional local API.

## Research replay

Run the commands in the root README. Initial source acquisition is serial and bounded. World Bank and WHO current endpoints can change. Compare newly acquired hashes with `configs/data-inputs.json`; a drifted source requires a new registered vintage and a new experiment identity. The release core-input snapshot preserves redistributable bytes. HGI and Google historical files use their recorded immutable release URLs and terms.

A scientific campaign must use the frozen exact inputs. Do not overwrite the source manifest to make drift pass. Each campaign gets a new noncolliding run ID. `make verify EVIDENCE=evidence/<id>` supplies the current Git HEAD as trusted expected source. When verifying a historical bundle after report-only changes, invoke `aftershock verify --evidence <path> --expected-source <full-source-commit>` explicitly. The running implementation must match that source's executable files.

## Interruption

Successful raw files are content-addressed and hash-checked before reuse. Re-run `make data` after interruption. Temporary partial files are removed. If a process is forcibly killed, inspect a lock's PID before removing the stale project-owned lock. Never remove a lock owned by a live writer.

`make fit` resumes atomic checkpoints only when the panel and protocol identities match. Seed directories contain initialized parameters, best parameters, restart state and loss history. A completed validation-patience run does not execute extra epochs when resumed. Preserve the old directory and its hashes before adopting a new protocol.

Panel construction writes to an atomic temporary file with 8192-row batches. A failed write preserves the prior complete file. The aggregate panel is rebuilt from exact raw inputs rather than incrementally mutating rows in place. Geography or measurement changes therefore invalidate downstream identities.

## Storage and costs

The project checks attributed local storage before known growth and records private samples under `.agent-local/`. Acquisition caps apply to compressed bytes and parsers cap expanded rows or workbook sizes. The local HTTP server limits active requests to eight and uses 15-second socket timeouts. DuckDB uses two threads, a 512 MB memory limit and at most 256 MB spill.

No paid compute or unattended scheduler is used. CPU diagnostics are separate from scientific acceptance. A full campaign with missing sources, unsupported assumptions or incomplete verification returns nonzero and keeps failure artifacts.
