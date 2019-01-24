"""Within-UK workplace mobility is not a cross-country employment measure."""
from __future__ import annotations

from collections import defaultdict

import numpy as np

from .io import ROOT, read_json, write_json
from .panel import csv_rows, number


def analyze_mobility() -> dict:
    index = read_json(ROOT / "data/raw/index.json")
    points, definitions = [], []
    for year in (2020, 2021, 2022):
        source = index[f"mobility_gb_{year}"]
        if source["status"] != "acquired":
            continue
        definitions.append({"year": year, "hash": source["sha256"]})
        for row in csv_rows(ROOT / "data/raw" / source["path"], cap=200000):
            if row["sub_region_1"] or row["sub_region_2"]:
                continue
            points.append({"region": "GBR", "date": row["date"],
                           "workplace": number(row["workplaces_percent_change_from_baseline"]),
                           "residential": number(row["residential_percent_change_from_baseline"]),
                           "kind": "opt_in_device_aggregate", "unit": "percent change relative to baseline weekday"})
    periods = defaultdict(list)
    for point in points:
        if point["workplace"] is not None:
            periods[point["date"][:4]].append(point["workplace"])
    summary = [{"year": int(year), "observed_days": len(values), "median_workplace_change": float(np.median(values)),
                "p10": float(np.quantile(values, .1)), "p90": float(np.quantile(values, .9)),
                "distribution": "day distribution; not a sampling confidence interval"} for year, values in sorted(periods.items())]
    result = {"geography": "GBR national only", "points": sorted(points, key=lambda r: r["date"]), "annual": summary,
              "sources": definitions, "attribution": "Google LLC, Google COVID-19 Community Mobility Reports, accessed 2026-11-11",
              "country_count": 1 if points else 0, "independent_people_denominator": None,
              "methodology_breaks": ["2020-04-11 through 2020-04-18 categorization changes", "2020-08-17 improved reporting applied retrospectively"],
              "limitations": ["Opt-in device users are not a representative worker sample", "Do not compare national mobility changes across countries",
                              "Visits to workplaces are not employment, hours or remote-work eligibility", "Baseline weekday composition differs from annual employment denominators"]}
    write_json(ROOT / "data/results/mobility.json", result)
    return {k: v for k, v in result.items() if k != "points"}
