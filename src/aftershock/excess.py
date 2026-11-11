"""WHO modeled excess mortality preserves release revisions and input-support labels."""
from __future__ import annotations

import io
from collections import Counter
from pathlib import Path
from zipfile import ZipFile

import openpyxl

from .io import ROOT, read_json, write_json
from .panel import connect, records


def read_workbook(path: Path) -> dict[str, list[dict]]:
    with ZipFile(path) as archive:
        members = [m for m in archive.infolist() if m.filename.endswith("EstimatesByCountry.xlsx")]
        if len(members) != 1 or members[0].file_size > 15_000_000:
            raise ValueError("Missing or oversized country workbook")
        workbook = openpyxl.load_workbook(io.BytesIO(archive.read(members[0])), read_only=True, data_only=True)
        output = {}
        for sheet in workbook:
            if sheet.title == "Notes":
                continue
            header, rows = None, []
            for row in sheet.iter_rows(values_only=True):
                if len(row) > 2 and row[1] == "iso3" and row[2] == "year":
                    header = [str(x).lower().replace("*", "") if x is not None else "" for x in row]
                    continue
                if header and isinstance(row[1], str) and len(row[1]) == 3:
                    record = {key: value for key, value in zip(header, row) if key}
                    rows.append(record)
            if rows:
                output[sheet.title] = rows
        workbook.close()
    return output


def analyze_excess() -> dict:
    index = read_json(ROOT / "data/raw/index.json")
    releases = {key: read_workbook(ROOT / "data/raw" / index[key]["path"]) for key in ("excess_2022", "excess_2023")}
    old_months = releases["excess_2022"]["Country by year and month"]
    new_months = releases["excess_2023"]["Deaths by year and month"]
    old = {(r["iso3"], int(r["year"]), int(r["month"])): r for r in old_months}
    revisions = []
    for row in new_months:
        key = row["iso3"], int(row["year"]), int(row["month"])
        if key in old:
            a, b = float(old[key]["excess.mean"]), float(row["excess.mean"])
            revisions.append({"region": key[0], "year": key[1], "month": key[2], "old": a, "new": b,
                              "delta": b - a, "input_type_old": old[key]["type"], "input_type_new": row["type"],
                              "old_release": "2022-05-05", "new_release": "2023-05-19", "kind": "modeled_estimate"})
    with connect() as db:
        official = records(db, """SELECT region,substr(event_end,1,4) yr,sum(value) deaths,count(value) reported_weeks
            FROM observations WHERE metric='covid_deaths' AND substr(event_end,1,4) IN ('2020','2021')
            GROUP BY region,yr""")
    reports = {(r["region"], r["yr"]): r for r in official}
    annual = []
    for row in releases["excess_2023"]["Deaths by year"]:
        if row["year"] not in (2020, 2021):
            continue
        report = reports.get((row["iso3"], str(row["year"])), {})
        mean, low, high = (float(row[k]) for k in ("excess.mean", "excess.low", "excess.high"))
        if not low <= mean <= high:
            raise ValueError("Invalid WHO annual interval")
        deaths = report.get("deaths")
        annual.append({"region": row["iso3"], "year": row["year"], "excess": mean, "lower": low, "upper": high,
                       "reported_covid_deaths": deaths, "reported_weeks": report.get("reported_weeks", 0),
                       "ratio": mean / deaths if deaths and deaths > 0 else None,
                       "kind": "modeled_excess_estimate", "report_timing": "COVID deaths summed by WHO report week",
                       "excess_timing": "modeled event year; not calendar-aligned with report dates"})
    age_old = releases["excess_2022"]["Country by year, sex and age"]
    age_new = releases["excess_2023"]["Deaths by year, sex and age"]
    result = {"annual": annual, "monthly_revision_rows": revisions, "months": len(new_months),
              "countries": len({r["iso3"] for r in new_months}),
              "input_types": dict(Counter(str(r["type"]).lower() for r in new_months)),
              "old_age_bands": sorted({r["age"] for r in age_old}),
              "new_age_bands": sorted({r["age_group"] for r in age_new}),
              "new_release_age_denominators": False,
              "source_hashes": {k: index[k]["sha256"] for k in releases},
              "license": "CC BY-NC-SA 3.0 IGO", "attribution": "World Health Organization, 2022 and 2023; no endorsement",
              "limitations": ["WHO excess deaths are modeled estimates, including locations without complete reported deaths",
                              "A ratio to reported COVID deaths combines different date definitions and estimands",
                              "Monthly and annual uncertainty cannot be reconstructed by summing marginal interval endpoints",
                              "Age bands changed between releases; 2023 age tables omit Nx denominators, blocking matched rate recomputation"]}
    write_json(ROOT / "data/results/excess.json", result)
    return {k: v for k, v in result.items() if k not in {"annual", "monthly_revision_rows"}}
