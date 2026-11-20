"""Compare actual annual hours within source-matched country series."""

from __future__ import annotations

import csv
import math
from collections import defaultdict
from pathlib import Path
from statistics import median

from .io import ROOT, digest
from .measurement import RAW, pinned_file
from .panel import connect, records

DIMENSIONS = (
    "MEASURE", "UNIT_MEASURE", "SEX", "AGE", "LABOUR_FORCE_STATUS", "WORK_PERIOD",
    "HOURS_TYPE", "WORKER_STATUS", "WORK_TIME_ARNGMNT", "AGGREGATION_OPERATION",
    "HOUR_BANDS", "JOB_COVERAGE",
)


def annual_hours(path: Path, config: dict) -> tuple[dict, dict]:
    keys = tuple(config["key"].split(".")[1:])
    areas: dict[str, dict[int, dict]] = defaultdict(dict)
    exclusions: dict[str, int] = defaultdict(int)
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        for number, row in enumerate(reader, start=1):
            if number > 2_000_000 or None in row:
                raise ValueError("Oversized or malformed OECD hours data")
            if row["DATAFLOW"].replace(":", ",").replace("(", ",").rstrip(")") != config["flow"]:
                raise ValueError("Unexpected OECD hours dataflow")
            if tuple(row[k] for k in DIMENSIONS) != keys:
                raise ValueError("OECD hours measurement definitions differ")
            if row["UNIT_MULT"] not in {"", "0"}:
                raise ValueError("OECD hours unit multiplier differs")
            year = int(row["TIME_PERIOD"])
            if not config["start_year"] <= year <= config["end_year"]:
                raise ValueError("Unexpected hours observation year")
            region = row["REF_AREA"]
            if region == "OECD":
                exclusions["OECD aggregate"] += 1
                continue
            if len(region) != 3 or not region.isascii() or not region.isupper():
                raise ValueError("Unexpected hours area identifier")
            if year in areas[region]:
                raise ValueError("Duplicate hours observation for country and year")
            value = float(row["OBS_VALUE"]) if row["OBS_VALUE"] else None
            if value is not None and (not math.isfinite(value) or not 0 < value <= 8784):
                raise ValueError("Hours outside elapsed-time bounds")
            areas[region][year] = {"value": value, "status": row["OBS_STATUS"]}
    return dict(areas), dict(exclusions)


def contrast_rows(areas: dict, config: dict, gdp: dict, source_hash: str) -> list[dict]:
    contrasts = []
    baseline = config["baseline_year"]
    for iso, values in sorted(areas.items()):
        for year in config["comparison_years"]:
            window = [values.get(y) for y in range(baseline, year + 1)]
            base, target = window[0], window[-1]
            reasons = []
            if any(item is None or item["value"] is None for item in window):
                reasons.append("incomplete annual window")
            inadmissible = sorted({
                item["status"] for item in window
                if item and item["status"] not in config["admissible_statuses"]
            })
            if inadmissible:
                reasons.append("status excludes comparison: " + ", ".join(inadmissible))
            a, b = gdp.get((iso, baseline)), gdp.get((iso, year))
            gdp_index = 100 * b / a if a and b is not None else None
            contrasts.append({
                "region": iso, "baseline_year": baseline, "target_year": year,
                "baseline_hours": base["value"] if base else None,
                "target_hours": target["value"] if target else None,
                "change_hours": target["value"] - base["value"] if not reasons else None,
                "hours_index": 100 * target["value"] / base["value"] if not reasons else None,
                "gdp_per_person_index": gdp_index, "gdp_match": gdp_index is not None and not reasons,
                "source_sha256": source_hash, "unit": config["unit"], "cohort": "total employment",
                "flag_history": [item["status"] if item is not None else None for item in window],
                "comparison_exclusions": reasons, "standard_error": None,
            })
    return contrasts


def summarize_hours(rows: list[dict], years: list[int]) -> list[dict]:
    result = []
    for year in years:
        population = [r for r in rows if r["target_year"] == year]
        eligible = [r for r in population if r["hours_index"] is not None]
        values = [r["hours_index"] - 100 for r in eligible]
        joint = [r for r in eligible if r["gdp_match"]]
        result.append({
            "year": year, "countries": len(eligible), "excluded": len(population) - len(eligible),
            "gdp_matches": len(joint), "below_2019_hours": sum(x < 0 for x in values),
            "above_2019_hours": sum(x > 0 for x in values),
            "median_hours_change_percent": median(values) if len(values) >= 5 else None,
            "range_hours_change_percent": [min(values), max(values)] if len(values) >= 5 else None,
            "diverging_hours_and_gdp": sum(
                (r["hours_index"] - 100) * (r["gdp_per_person_index"] - 100) < 0 for r in joint
            ),
        })
    return result


def hours_study(sources: dict, config: dict) -> dict:
    if "oecd_annual_hours" not in sources:
        return {"status": "unavailable", "rows": [], "summary": [], "limitation": "OECD extract pending."}
    meta = sources["oecd_annual_hours"]
    areas, excluded = annual_hours(pinned_file(RAW, meta), config)
    with connect() as db:
        gdp = {
            (r["region"], r["yr"]): r["value"] for r in records(db, """
                SELECT region, CAST(substr(event_start,1,4) AS INTEGER) AS yr, value
                FROM observations WHERE metric='gdp' AND "group"='total' AND value > 0
            """)
        }
    contrasts = contrast_rows(areas, config, gdp, meta["sha256"])
    return {
        "status": "acquired", "source_sha256": meta["sha256"], "unit": config["unit"],
        "gdp_panel_sha256": digest(ROOT / "data/panel/observations.parquet"),
        "rows": contrasts, "summary": summarize_hours(contrasts, config["comparison_years"]),
        "observations": sum(map(len, areas.values())), "excluded_observations": excluded,
        "limitation": "Within-country retrospective changes. OECD methods vary by country. Sampling errors, ILO weekly hours and occupational sector detail remain unavailable.",
    }
