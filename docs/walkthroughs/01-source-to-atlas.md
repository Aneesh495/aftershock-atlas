# Source to atlas

`make covid-data` acquires exact WHO report-week CSV bytes and annual population metadata. `acquire.py` bounds HTTP size, timestamps acquisition and stores a content-addressed file. `make data` adds the annual and secondary sources.

`make panel` runs source-specific parsers. `who_rows` preserves signed corrections and absent cells; `world_bank_rows` rejects truncated pages and excludes regional aggregates. The Arrow writer validates each typed record. DuckDB rejects duplicate measurement identities before writing a coverage manifest.

`make atlas` exports annual values, source cards, independent coverage and previously fitted studies. `atlas-view.ts` obtains the selected outcome's actual JSON and maps it by ISO identity. Map clicks update the same country state used by curves and export. Per-population reported rates use annual population for the same region and year, returning missing when no denominator exists. Country-level survey or genetics data is never invented to fill map coverage.

Verify through the browser: select USA and GBR, choose employment, inspect 2019-2023 values, then switch to crude mortality and its measurement label. The source button exposes the acquisition identity, rights and timing limits.
