"""Official WDI edition partitions, conservative availability and explicit revisions."""
from __future__ import annotations

import calendar
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from .acquire import Source, acquire_one
from .io import ROOT, atomic_path, digest, exclusive, read_json, write_json
from .resources import usage

SCHEMA = pa.schema([
    ("region", pa.string()), ("metric", pa.string()), ("year", pa.int32()),
    ("edition", pa.string()), ("edition_available_at", pa.string()), ("acquired_at", pa.string()),
    ("raw_value", pa.float64()), ("value", pa.float64()), ("anchor_2010", pa.float64()),
    ("unit", pa.string()), ("kind", pa.string()), ("series_label", pa.string()),
    ("source_hash", pa.string()), ("flags", pa.string()),
])
UNITS = {"population": "persons", "employment": "percent population age 15+", "gdp": "2010=100 within-edition real GDP per capita index",
         "school": "gross secondary enrollment percent", "immunization": "DTP coverage percent",
         "mortality": "deaths per 1000 population", "life_expectancy": "years"}


def edition_bound(edition: str) -> str:
    if len(edition) != 6 or not edition.isdigit():
        raise ValueError("Six-digit official archive edition required")
    year, month = int(edition[:4]), int(edition[4:])
    if not 1980 <= year <= 2100 or not 1 <= month <= 12:
        raise ValueError("Invalid archive edition calendar")
    return f"{year:04d}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}T23:59:59+00:00"


def archive_sources() -> list[Source]:
    plan = read_json(ROOT / "configs/history-plan.json")
    sources = [Source("history_catalogue", "https://api.worldbank.org/v2/sources/57/version/data?format=json&per_page=1000",
        "json", 2_000_000, "World Bank CC BY 4.0 with additional terms; upstream attribution",
        "https://datatopics.worldbank.org/world-development-indicators/wdi-archives.html",
        "provider-designated archive catalogue; current acquisition", "Edition labels do not provide original cell release days")]
    for edition in plan["editions"]:
        for metric, code in plan["series"].items():
            sources.append(Source(f"archive_{edition}_{metric}",
                f"https://api.worldbank.org/v2/sources/57/country/all/series/{code}/time/all/version/{edition}/data?format=json&per_page=30000",
                "json", plan["max_source_bytes"], "World Bank CC BY 4.0 with additional terms; source-specific attribution",
                "https://datahelpdesk.worldbank.org/knowledgebase/articles/1886686-advanced-data-api-queries",
                "official WDI edition " + edition + "; month bound, not original cell publication day",
                "Current metadata may describe earlier editions incorrectly; future-reference estimates are excluded; GDP is internally indexed"))
    return sources


def validate_archive(payload: dict, edition: str, series: str) -> list[dict]:
    if not isinstance(payload, dict) or payload.get("pages") != 1 or payload.get("page") != 1:
        raise ValueError("Incomplete archive pagination or API error")
    source = payload.get("source", {})
    if source.get("id") != "57" or not isinstance(source.get("data"), list):
        raise ValueError("Wrong archive source schema")
    rows = source["data"]
    if len(rows) != payload.get("total") or not 100 <= len(rows) <= 30_000:
        raise ValueError("Archive population count mismatch")
    parsed, seen = [], set()
    for row in rows:
        dimensions = row.get("variable", [])
        if len(dimensions) != 4 or {v["concept"] for v in dimensions} != {"Country", "Version", "Series", "Time"}:
            raise ValueError("Archive dimension set mismatch")
        values = {v["concept"]: v for v in dimensions}
        if values["Version"]["id"] != edition or values["Series"]["id"] != series:
            raise ValueError("Archive edition or series substituted")
        time = values["Time"]["id"]
        if not time.startswith("YR") or not time[2:].isdigit():
            raise ValueError("Archive time is not an annual reference")
        region, year = values["Country"]["id"], int(time[2:])
        if (region, year) in seen:
            raise ValueError("Duplicate archive measurement population")
        seen.add((region, year))
        value = row.get("value")
        if value is not None and (not isinstance(value, (int, float)) or not np.isfinite(value)):
            raise ValueError("Nonfinite archive value")
        parsed.append({"region": region, "year": year, "raw_value": value,
                       "series_label": values["Series"].get("value", "")})
    return parsed


def acquire_history(refresh: bool = False) -> dict:
    raw = ROOT / "data/history/raw"
    plan = read_json(ROOT / "configs/history-plan.json")
    pin_path = ROOT / "configs/history-inputs.json"
    pins = read_json(pin_path) if pin_path.exists() else {}
    with exclusive(raw / ".acquire.lock"):
        result = read_json(raw / "index.json") if (raw / "index.json").exists() else {}
        for source in archive_sources():
            usage(30_000_000)
            record = acquire_one(source, raw, refresh)
            if source.id in pins and pins[source.id]["sha256"] != record["sha256"]:
                raise ValueError("Historical edition drifted from frozen bytes: " + source.id)
            payload = read_json(raw / record["path"], 12_000_000)
            if source.id == "history_catalogue":
                if record["sha256"] != plan["catalogue_sha256"]:
                    raise ValueError("Archive catalogue changed after protocol registration")
                if payload.get("pages") != 1:
                    raise ValueError("Truncated archive catalogue")
                versions = {v["id"] for v in payload["source"][0]["concept"][0]["variable"]}
                if not set(plan["editions"]) <= versions:
                    raise ValueError("Registered archive edition absent from provider catalogue")
            else:
                _, edition, metric = source.id.split("_", 2)
                validate_archive(payload, edition, plan["series"][metric])
            result[source.id] = pins.get(source.id, record)
            write_json(raw / "index.json", result)
            print(f"archived {source.id}: {record['bytes']} bytes", flush=True)
        if not pins:
            # Explicit first registration, retained in Git before any model fitting.
            frozen = {key: {k: v for k, v in record.items() if k != "headers"} for key, record in result.items()}
            write_json(pin_path, frozen)
    return {"sources": len(result), "frozen": pin_path.exists()}


def build_history() -> dict:
    usage(250_000_000)
    pins = read_json(ROOT / "configs/history-inputs.json")
    plan = read_json(ROOT / "configs/history-plan.json")
    countries = {r["id"] for r in read_json(ROOT / "data/panel/regions.json")}
    output = ROOT / "data/history/observations.parquet"
    inventory, excluded, total = [], {}, 0
    with atomic_path(output) as temporary:
        with pq.ParquetWriter(temporary, SCHEMA, compression="zstd") as writer:
            for edition in plan["editions"]:
                for metric, series in plan["series"].items():
                    record = pins[f"archive_{edition}_{metric}"]
                    path = ROOT / "data/history/raw" / record["path"]
                    if digest(path) != record["sha256"]:
                        raise ValueError("Archived source integrity mismatch")
                    raw = validate_archive(read_json(path, 12_000_000), edition, series)
                    anchors = {r["region"]: r["raw_value"] for r in raw if r["year"] == 2010}
                    batch, nonmissing, future, missing_anchor, raw_nonmissing = [], 0, 0, 0, 0
                    visible_countries = set()
                    for row in raw:
                        if row["region"] not in countries:
                            excluded[row["region"]] = excluded.get(row["region"], 0) + 1
                            continue
                        if not 2000 <= row["year"] <= 2024:
                            continue
                        value, flags = row["raw_value"], "provider_archive_month;current_code_match;historical_metadata_limited"
                        raw_nonmissing += value is not None
                        if row["year"] > int(edition[:4]):
                            future += value is not None
                            value = None
                            flags += ";future_reference_excluded"
                        anchor = anchors.get(row["region"]) if metric == "gdp" else None
                        if metric == "gdp":
                            if anchor is None or anchor <= 0:
                                missing_anchor += value is not None
                                value = None
                                flags += ";missing_positive_2010_anchor"
                            elif value is not None:
                                if value <= 0:
                                    raise ValueError("Nonpositive real GDP cannot be indexed")
                                value = value / anchor * 100
                                flags += ";within_edition_2010_index;price_base_revision_caveat"
                        nonmissing += value is not None
                        if value is not None:
                            visible_countries.add(row["region"])
                        batch.append({**row, "metric": metric, "edition": edition,
                            "edition_available_at": edition_bound(edition), "acquired_at": record["acquired_at"],
                            "value": value, "anchor_2010": anchor, "unit": UNITS[metric],
                            "kind": "derived_index" if metric == "gdp" else "provider_estimate",
                            "source_hash": record["sha256"], "flags": flags})
                        if len(batch) >= 8192:
                            writer.write_table(pa.Table.from_pylist(batch, schema=SCHEMA))
                            total += len(batch)
                            batch.clear()
                    if batch:
                        writer.write_table(pa.Table.from_pylist(batch, schema=SCHEMA))
                        total += len(batch)
                    inventory.append({"edition": edition, "metric": metric, "nonmissing": nonmissing,
                        "raw_nonmissing": raw_nonmissing, "excluded_future_values": future, "missing_anchor_values": missing_anchor,
                        "countries": len(visible_countries),
                        "source_sha256": record["sha256"], "edition_available_at": edition_bound(edition), "unit": UNITS[metric]})
    manifest = {"schema": "official-archive-v3", "rows": total, "sha256": digest(output), "inventory": inventory,
        "excluded_country_codes": excluded, "editions": plan["editions"], "source_count": len(pins),
        "availability_basis": "provider-designated edition month; original cell publication days unavailable",
        "limitations": ["Current code matching does not prove stable territorial boundaries", "Current metadata may replace historical definitions",
                        "Future-reference estimates are withheld from observed displays", "GDP indices remove constant scaling, not methodological revisions"]}
    write_json(ROOT / "data/history/manifest.json", manifest)
    return manifest


def history_cube(edition: str) -> tuple[list[str], dict[str, dict[int, dict[str, float]]]]:
    import duckdb
    plan = read_json(ROOT / "configs/history-plan.json")
    if edition not in plan["editions"]:
        raise ValueError("Unknown frozen archive edition")
    db = duckdb.connect(":memory:")
    db.execute("SET memory_limit='512MB'")
    db.execute("SET threads=2")
    try:
        rows = db.execute("SELECT region,metric,year,value FROM read_parquet(?) WHERE edition=? AND value IS NOT NULL ORDER BY region,year,metric",
                          [str(ROOT / "data/history/observations.parquet"), edition]).fetchall()
    finally:
        db.close()
    result = {}
    for region, metric, year, value in rows:
        result.setdefault(region, {}).setdefault(year, {})[metric] = value
    return sorted(result), result
