"""Bounded HTTPS acquisition with content-addressed immutable vintages."""
from __future__ import annotations

import dataclasses
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from urllib.parse import urlencode

from .io import ROOT, append_json, atomic_path, digest, exclusive, now, read_json, write_json
from .resources import usage


@dataclass(frozen=True)
class Source:
    id: str
    url: str
    format: str
    max_bytes: int
    rights: str
    citation: str
    timing: str
    limitations: str
    redistribute: bool = True


def sources() -> list[Source]:
    result = [Source(
        "who", "https://srhdpeuwpubsa.blob.core.windows.net/whdh/COVID/WHO-COVID-19-global-data.csv",
        "csv", 30_000_000, "WHO dashboard terms; attribution; no endorsement",
        "https://data.who.int/dashboards/covid19/data", "report week; acquired vintage only",
        "Testing, reporting frequency, backlogs and negative revisions vary. Blank is not zero."),
        Source("regions", "https://api.worldbank.org/v2/country?format=json&per_page=400", "json", 2_000_000,
               "World Bank CC BY 4.0 with additional terms", "https://datacatalog.worldbank.org/public-licenses",
               "current registry; not a historical border reconstruction", "Aggregates are excluded from country panels."),
        Source("policy", "https://raw.githubusercontent.com/OxCGRT/covid-policy-dataset/main/data/OxCGRT_compact_national_v1.csv",
               "csv", 70_000_000, "CC BY 4.0", "https://github.com/OxCGRT/covid-policy-dataset",
               "final 2020-2022 policy coding; acquired vintage", "Majority-population policy, not adherence; bundles confound attribution."),
        Source("cdc_pre", "https://data.cdc.gov/resource/3yf8-kanr.csv?$limit=50000&$order=jurisdiction_of_occurrence,weekendingdate",
               "csv", 15_000_000, "Public Domain U.S. Government", "https://data.cdc.gov/d/3yf8-kanr",
               "event week, final 2014-2019", "State of occurrence differs from residence; suppression preserved."),
        Source("cdc_post", "https://data.cdc.gov/resource/muzy-jte6.csv?$limit=50000&$order=jurisdiction_of_occurrence,week_ending_date",
               "csv", 15_000_000, "Public Domain U.S. Government", "https://data.cdc.gov/d/muzy-jte6",
               "event week, provisional through 2023; dataset stopped updating", "Reporting lag and incomplete recent weeks; not current surveillance."),
        Source("hgi_a2", "https://storage.googleapis.com/covid19-hg-public/freeze_7/results/20220403/main/sumstats/COVID19_HGI_A2_ALL_20220403.10k.tsv.gz",
               "tsv.gz", 5_000_000, "HGI public aggregate terms; no identification; acknowledge HGI",
               "https://www.covid19hg.org/results/r7/", "2022-04-08 release; GRCh38; top 10000 selected variants",
               "Very severe respiratory confirmed COVID versus population. Selected hits, LD and shared samples preclude independent replication.", False),
        Source("hgi_b2", "https://storage.googleapis.com/covid19-hg-public/freeze_7/results/20220403/main/sumstats/COVID19_HGI_B2_ALL_20220403.10k.tsv.gz",
               "tsv.gz", 5_000_000, "HGI public aggregate terms; no identification; acknowledge HGI",
               "https://www.covid19hg.org/results/r7/", "2022-04-08 release; GRCh38; top 10000 selected variants",
               "Hospitalized COVID versus population. Overlap with A2 means concordance is not replication.", False),
        Source("world_map", "https://cdn.jsdelivr.net/npm/world-atlas@2.0.2/countries-110m.json", "json", 500_000,
               "Natural Earth public domain; world-atlas ISC", "https://github.com/topojson/world-atlas",
               "cartographic reference only", "Coarse borders do not establish political status or longitudinal comparability."),
    ]
    result.extend([
        Source("survey", "https://data.cdc.gov/resource/8pt5-q6wp.csv?" + urlencode({"$limit": 100000}),
               "csv", 35_000_000, "Public Domain U.S. Government", "https://data.cdc.gov/d/8pt5-q6wp",
               "Household Pulse waves 2020-2024; published aggregate estimates", "Not a matched longitudinal sample; no pre-2020 equivalent; nonresponse and phase changes."),
        Source("lineage", "https://data.cdc.gov/resource/jr58-6ysp.csv?" + urlencode({"$limit": 200000, "$where": "usa_or_hhsregion='USA' AND modeltype='weighted'"}),
               "csv", 50_000_000, "Public Domain U.S. Government", "https://data.cdc.gov/d/jr58-6ysp",
               "CDC national weighted estimates with publication dates", "Sequencing selection bias; different publications and intervals must not be summed."),
    ])
    indicators = {"population": "SP.POP.TOTL", "employment": "SL.EMP.TOTL.SP.ZS",
                  "gdp": "NY.GDP.PCAP.KD", "school": "SE.SEC.ENRR", "immunization": "SH.IMM.IDPT",
                  "mortality": "SP.DYN.CDRT.IN", "life_expectancy": "SP.DYN.LE00.IN"}
    for metric, code in indicators.items():
        result.append(Source(f"wb_{metric}",
                             f"https://api.worldbank.org/v2/country/all/indicator/{code}?date=2000:2025&format=json&per_page=10000",
                             "json", 6_000_000, "World Bank CC BY 4.0 with additional terms; upstream attribution",
                             f"https://data.worldbank.org/indicator/{code}", "annual reference period; current acquired vintage only",
                             "Annual release and revision dates unavailable per cell. Final-vintage retrospective evaluation only."))
    return result


def acquire_one(source: Source, raw: Path, refresh: bool = False) -> dict:
    if urlparse(source.url).scheme != "https":
        raise ValueError("HTTPS source required")
    receipt = raw / source.id / "latest.json"
    if receipt.exists() and not refresh:
        old = read_json(receipt)
        path = raw / old["path"]
        if path.exists() and digest(path) == old["sha256"]:
            return old
        raise ValueError(f"Cached source failed integrity: {source.id}")
    usage(source.max_bytes * 2)
    started = time.monotonic()
    target = raw / source.id / f"download.{source.format}"
    with atomic_path(target) as temporary:
        header = temporary.with_suffix(".headers")
        try:
            command = ["curl", "--fail", "--silent", "--show-error", "--location", "--proto", "=https",
                       "--proto-redir", "=https", "--max-filesize", str(source.max_bytes), "--connect-timeout", "20",
                       "--max-time", "180", "--retry", "2", "--dump-header", str(header), "--output", str(temporary), source.url]
            done = subprocess.run(command, capture_output=True, text=True, timeout=580)
            if done.returncode:
                raise RuntimeError(f"{source.id}: curl exit {done.returncode}: {done.stderr[:500]}")
            size = temporary.stat().st_size
            if not 20 <= size <= source.max_bytes:
                raise ValueError(f"{source.id}: empty or oversized input")
            checksum = digest(temporary)
            response_headers = header.read_text(errors="replace")[-12000:]
        finally:
            header.unlink(missing_ok=True)
    immutable = target.with_name(f"{checksum}.{source.format}")
    if immutable.exists():
        target.unlink()
    else:
        target.rename(immutable)
    result = {**dataclasses.asdict(source), "path": str(immutable.relative_to(raw)), "sha256": checksum,
              "bytes": size, "acquired_at": now(), "available_at": now(), "headers": response_headers,
              "elapsed_seconds": time.monotonic() - started}
    write_json(receipt, result)
    write_json(immutable.with_suffix(immutable.suffix + ".receipt.json"), result)
    return result


def acquire(refresh: bool = False, only: list[str] | None = None) -> dict:
    raw = ROOT / "data/raw"
    with exclusive(raw / ".acquire.lock"):
        index = read_json(raw / "index.json") if (raw / "index.json").exists() else {}
        for source in sources():
            if only and source.id not in only:
                continue
            try:
                index[source.id] = {"status": "acquired", **acquire_one(source, raw, refresh)}
                print(f"acquired {source.id}: {index[source.id]['bytes']} bytes", flush=True)
            except (RuntimeError, ValueError, subprocess.TimeoutExpired) as e:
                append_json(raw / "failures.jsonl", {"source": source.id, "at": now(), "error": str(e)})
                index[source.id] = {"status": "blocked", **dataclasses.asdict(source), "error": str(e)}
                print(f"blocked {source.id}: {e}", flush=True)
            write_json(raw / "index.json", index)
    return index
