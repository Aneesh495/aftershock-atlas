"""Stream source-specific definitions into a typed Arrow panel and DuckDB views."""
from __future__ import annotations

import csv
from dataclasses import asdict, fields
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable, Iterator

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from .contracts import METRICS, Observation
from .geography import iso3, us_region
from .io import ROOT, atomic_path, digest, exclusive, now, read_json, write_json
from .resources import usage

NUMERIC = {"value", "lower", "upper", "denominator"}
SCHEMA = pa.schema([(f.name, pa.float64() if f.name in NUMERIC else pa.string()) for f in fields(Observation)])


def number(text: str | None) -> float | None:
    if text is None or text.strip() in {"", "NA", "N/A", "NaN", "null", "Suppressed"}:
        return None
    value = float(text.replace(",", ""))
    if not __import__("math").isfinite(value):
        raise ValueError("Nonfinite input")
    return value


def csv_rows(path: Path, cap: int = 500_000) -> Iterator[dict]:
    csv.field_size_limit(1_000_000)
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or len(reader.fieldnames) > 400:
            raise ValueError("Invalid CSV header")
        for i, row in enumerate(reader):
            if i >= cap:
                raise ValueError("Source row bound reached; pagination must be explicit")
            if None in row:
                raise ValueError("Ragged CSV record")
            yield row


def observe(source: dict, region: str, metric: str, start: str, end: str, value: float | None,
            group: str = "total", flags: str = "", lower: float | None = None, upper: float | None = None) -> Observation:
    m = METRICS[metric]
    return Observation(region, metric, start, end, value, source["available_at"], source["acquired_at"],
                       source["id"], source["sha256"], m.kind, m.unit, m.frequency, group, lower, upper, flags=flags)


def who_rows(source: dict, path: Path) -> Iterator[Observation]:
    for row in csv_rows(path):
        region = iso3(row["Country_code"])
        if not region:
            region = "WHO:" + row["Country_code"]
        end = row["Date_reported"]
        start = (date.fromisoformat(end) - timedelta(days=6)).isoformat()
        for field, metric in (("New_cases", "covid_cases"), ("New_deaths", "covid_deaths")):
            value = number(row[field])
            flags = "report_date;blank_not_zero"
            if value is not None and value < 0:
                flags += ";negative_correction"
            yield observe(source, region, metric, start, end, value, flags=flags)


def world_bank_rows(source: dict, path: Path, countries: set[str]) -> Iterator[Observation]:
    payload = read_json(path)
    if not isinstance(payload, list) or len(payload) != 2:
        raise ValueError("World Bank error or invalid envelope")
    if int(payload[0]["pages"]) != 1 or int(payload[0]["total"]) != len(payload[1]):
        raise ValueError("Truncated World Bank page")
    metric = source["id"].removeprefix("wb_")
    for row in payload[1]:
        region = row["countryiso3code"]
        if region not in countries:
            continue
        year = int(row["date"])
        yield observe(source, region, metric, f"{year}-01-01", f"{year}-12-31", row["value"],
                      flags="final_vintage_only;annual_not_interpolated")


def policy_rows(source: dict, path: Path) -> Iterator[Observation]:
    columns = {"StringencyIndex_Average": "stringency", "C1M_School closing": "school_policy",
               "C2M_Workplace closing": "work_policy"}
    for row in csv_rows(path):
        if row["Jurisdiction"] != "NAT_TOTAL" or row["RegionCode"]:
            continue
        day = datetime.strptime(row["Date"], "%Y%m%d").date().isoformat()
        for column, metric in columns.items():
            yield observe(source, row["CountryCode"], metric, day, day, number(row[column]),
                          flags="final_coding;majority_population;not_adherence")


def cdc_rows(source: dict, path: Path) -> Iterator[Observation]:
    prior = source["id"] == "cdc_pre"
    for row in csv_rows(path, cap=49999):
        region = us_region(row["jurisdiction_of_occurrence"])
        if not region:
            continue
        end = row["weekendingdate" if prior else "week_ending_date"][:10]
        start = (date.fromisoformat(end) - timedelta(days=6)).isoformat()
        value = number(row["allcause" if prior else "all_cause"])
        flag = row.get("flag_allcause", "")
        flags = "event_week;state_of_occurrence;" + ("final" if prior else "provisional")
        if flag or value is None:
            flags += ";suppressed"
        yield observe(source, region, "allcause_weekly", start, end, value, flags=flags)


def survey_rows(source: dict, path: Path) -> Iterator[Observation]:
    for row in csv_rows(path, cap=99999):
        if row["indicator"] != "Symptoms of Anxiety Disorder or Depressive Disorder":
            continue
        region = us_region(row["state"])
        if not region:
            continue
        group = "total" if row["group"] in {"National Estimate", "By State"} else row["group"] + ": " + row["subgroup"]
        flags = "upstream_public_aggregate;weighted_by_provider;phase=" + row["phase"]
        value = number(row["value"])
        if value is None:
            flags += ";suppressed"
        yield observe(source, region, "anxiety", row["time_period_start_date"][:10], row["time_period_end_date"][:10],
                      value, group, flags, number(row["lowci"]), number(row["highci"]))


def write_parquet(path: Path, rows: Iterable[Observation], batch_size: int = 8192) -> int:
    count = 0
    with atomic_path(path) as temporary:
        with pq.ParquetWriter(temporary, SCHEMA, compression="zstd") as writer:
            batch = []
            for row in rows:
                batch.append(row.record())
                count += 1
                if len(batch) == batch_size:
                    writer.write_table(pa.Table.from_pylist(batch, schema=SCHEMA))
                    batch.clear()
            if batch:
                writer.write_table(pa.Table.from_pylist(batch, schema=SCHEMA))
    if count == 0:
        raise ValueError("Empty panel is not a successful build")
    return count


def connect(path: Path | None = None) -> duckdb.DuckDBPyConnection:
    database = duckdb.connect(":memory:")
    database.execute("SET memory_limit='512MB'")
    database.execute("SET threads=2")
    database.execute("SET max_temp_directory_size='256MB'")
    database.read_parquet(str(path or ROOT / "data/panel/observations.parquet")).create_view("observations")
    for name, kind in (("survey_estimates", "survey_estimate"), ("modeled_estimates", "modeled_estimate"),
                       ("observed_values", "observed"), ("policy_design", "policy_design"), ("imputed_values", "imputed")):
        database.execute(f"CREATE VIEW {name} AS SELECT * FROM observations WHERE kind='{kind}'")
    return database


def records(db: duckdb.DuckDBPyConnection, query: str, params: list | None = None) -> list[dict]:
    result = db.execute(query, params or [])
    columns = [x[0] for x in result.description]
    return [dict(zip(columns, row)) for row in result.fetchall()]


def build_panel() -> dict:
    usage(350_000_000)
    raw, out = ROOT / "data/raw", ROOT / "data/panel"
    index = read_json(raw / "index.json")
    registry = read_json(raw / index["regions"]["path"])[1]
    country_list = [{"id": r["id"], "iso2": r["iso2Code"], "name": r["name"],
                     "region": r["region"]["value"], "income": r["incomeLevel"]["value"],
                     "longitude": number(r["longitude"]), "latitude": number(r["latitude"]),
                     "valid_start": None, "valid_end": None, "source_reference_start": "2000-01-01",
                     "timezone": "not harmonized; source-local dates only", "crosswalk_status": "current identifiers only; historical boundaries and backcasts unresolved"}
                    for r in registry if r["region"]["id"] != "NA"]
    countries = {r["id"] for r in country_list}
    def all_rows():
        for key, source in sorted(index.items()):
            if source["status"] != "acquired":
                continue
            path = raw / source["path"]
            if digest(path) != source["sha256"]:
                raise ValueError("Upstream bytes changed: " + key)
            if key == "who":
                yield from who_rows(source, path)
            elif key.startswith("wb_"):
                yield from world_bank_rows(source, path, countries)
            elif key == "policy":
                yield from policy_rows(source, path)
            elif key in {"cdc_pre", "cdc_post"}:
                yield from cdc_rows(source, path)
            elif key == "survey":
                yield from survey_rows(source, path)
    with exclusive(out / ".panel.lock"):
        count = write_parquet(out / "observations.parquet", all_rows())
        with connect() as db:
            duplicate = db.execute("SELECT region,metric,event_start,\"group\",vintage,count(*) n FROM observations GROUP BY ALL HAVING n>1 LIMIT 1").fetchone()
            if duplicate:
                raise ValueError(f"Duplicate measurement population: {duplicate}")
            coverage = records(db, """SELECT metric, kind, unit, frequency, count(*) row_count, count(value) nonmissing,
                count(DISTINCT region) regions, min(event_start) first_date, max(event_end) last_date,
                sum(CASE WHEN value<0 THEN 1 ELSE 0 END) negative_corrections,
                count(DISTINCT CASE WHEN length(region)=3 AND value IS NOT NULL THEN region END) countries
                FROM observations GROUP BY ALL ORDER BY metric""")
            per_region = records(db, """SELECT region,metric,count(value) nonmissing, min(event_start) first_date,
                max(event_end) last_date, count(*) total FROM observations WHERE \"group\"='total' GROUP BY region,metric""")
        output = {"schema_version": 1, "created_at": now(), "rows": count,
                  "sha256": digest(out / "observations.parquet"), "coverage": coverage,
                  "sources": {k: v["sha256"] for k, v in index.items() if v["status"] == "acquired"},
                  "historical_availability": "unavailable; current-vintage retrospective analyses only"}
        write_json(out / "manifest.json", output)
        write_json(out / "regions.json", country_list)
        write_json(out / "coverage.json", {"metrics": coverage, "regions": per_region})
        write_json(out / "metrics.json", {k: asdict(m) for k, m in METRICS.items()})
    return output
