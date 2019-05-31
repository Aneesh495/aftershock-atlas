"""Decode Eurostat sparse cell offsets and replay both quarter contrasts."""

from __future__ import annotations

import math
from decimal import Decimal
from pathlib import Path

import numpy as np

from .io import ROOT, digest, read_json
from .verification import require


def equal(actual: object, expected: object, reason: str) -> None:
    if isinstance(expected, dict):
        require(isinstance(actual, dict) and actual.keys() == expected.keys(), reason + " fields")
        for field, value in expected.items():
            equal(actual[field], value, f"{reason}.{field}")
    elif type(expected) is float:
        require(type(actual) in (int, float) and math.isclose(actual, expected, abs_tol=1e-10), reason)
    else:
        require(actual == expected and type(actual) is type(expected), reason)


def coordinates(data: dict, config: dict) -> dict:
    shape = tuple(data["size"])
    coordinates = dict(zip(data["id"], np.indices(shape).reshape(len(shape), -1), strict=True))
    axis_codes = {}
    for name in data["id"]:
        source_codes = data["dimension"][name]["category"]["index"]
        labels = source_codes if isinstance(source_codes, list) else sorted(source_codes, key=source_codes.get)
        require(len(labels) == shape[data["id"].index(name)] and len(set(labels)) == len(labels), "Eurostat axis inventory")
        if name in config["fixed"]:
            require(labels == [config["fixed"][name]], "Eurostat denominator changed")
        axis_codes[name] = np.asarray(labels)
    positions = {"geo": config["states"], "time": config["periods"], "nace_r2": config["sectors"].keys()}
    require(set(axis_codes) == set(config["fixed"]) | set(positions), "Eurostat cube dimension changed")
    require(all(set(axis_codes[key]) == set(labels) for key, labels in positions.items()), "Eurostat cohort changed")
    length = int(np.prod(shape))
    output = {}
    obs, status = data["value"], data.get("status", {})
    require(all(key.isdecimal() and str(int(key)) == key and int(key) < length for key in obs.keys() | status.keys()),
            "Eurostat cell position exceeds cube")
    for i in range(length):
        key = tuple(str(axis_codes[name][coordinates[name][i]]) for name in ("geo", "nace_r2", "time"))
        value, flags = obs.get(str(i)), status.get(str(i), "")
        require(value is None or (type(value) in (float, int) and 0 <= value <= 168), "Eurostat hour value out of domain")
        require(type(flags) is str and not set(flags) - set("bcdefmnpuz"), "Eurostat observation flag changed")
        output[key] = (value, flags, i)
    return output


def expected_change(raw: dict, state: str, sector: str, start: str, end: str, periods: list[str]) -> dict:
    first = raw[state, sector, start]
    last = raw[state, sector, end]
    inside = [raw[state, sector, period] for period in periods if start <= period <= end]
    withheld = set("bcdfmnuz")
    seen = set("".join(flag for _, flag, _ in inside))
    missing = sum(value is None for value, _, _ in inside)
    eligible = not missing and not withheld & seen
    return {
        "baseline_hours": first[0], "target_hours": last[0], "baseline_cell": first[2], "target_cell": last[2],
        "change_hours": float(Decimal(str(last[0])) - Decimal(str(first[0]))) if eligible else None,
        "unfit_flags": "".join(sorted(seen & withheld)), "window_flags": "".join(sorted(seen)),
        "missing_quarters": missing,
    }


def statistics(cohort: list[dict], sector: str, start: str, end: str) -> dict:
    rates = [r["change_hours"] for r in cohort if r["change_hours"] is not None]
    paired = [r["sector_minus_total_change_hours"] for r in cohort if r["sector_minus_total_change_hours"] is not None]
    clean = [r["change_hours"] for r in cohort if r["both_unflagged"]]
    return {"sector": sector, "baseline_quarter": start, "target_quarter": end,
            "matched_countries": len(rates), "paired_total_matches": len(paired),
            "unflagged_matches_to_total": len(clean), "below_by_one_hour": sum(x <= -1 for x in rates),
            "above_by_one_hour": sum(x >= 1 for x in rates),
            "median_change_hours": float(np.median(rates)) if rates else None,
            "median_unflagged_change_hours": float(np.median(clean)) if clean else None,
            "median_sector_minus_total_change_hours": float(np.median(paired)) if paired else None}


def verify_sectors(artifact: dict, file: Path, expected_source: str) -> dict:
    definitions = ROOT / "configs/sector-hours-v6.json"
    manifest = ROOT / "configs/sector-hours-inputs.json"
    spec = read_json(manifest)["eurostat_sector_hours"]
    config = read_json(definitions)
    require(file.stat().st_size == spec["bytes"] and digest(file) == spec["sha256"], "Sector hours raw input mismatch")
    require(artifact["source"] == expected_source and artifact["source_sha256"] == spec["sha256"]
            and artifact["input_sha256"] == digest(manifest) and artifact["definition_sha256"] == digest(definitions),
            "Sector hours source identity changed")
    require(artifact["unit"] == config["unit"] and artifact["population"] == config["population"],
            "Sector-hours worker denominator changed")
    data = read_json(file)
    raw = coordinates(data, config)
    require(artifact["released_update"] == data["updated"] and artifact["cube_size"] == len(raw), "Eurostat vintage changed")
    observations = {(r["geo"], r["sector"], r["quarter"]): r for r in artifact["observations"]}
    require(set(observations) == set(raw) and len(artifact["observations"]) == len(raw), "Sector observation inventory changed")
    for (geo, sector, quarter), (hour, flag, i) in raw.items():
        equal(observations[geo, sector, quarter], {"geo": geo, "sector": sector, "quarter": quarter,
              "hours": hour, "flags": flag, "cell": i}, "Eurostat observation, flag or cell changed")
    comparisons = {(r["target_quarter"], r["geo"], r["sector"]): r for r in artifact["comparisons"]}
    summaries = {(r["target_quarter"], r["sector"]): r for r in artifact["summary"]}
    expected_comparisons, expected_summaries = 0, 0
    for start, end in config["windows"]:
        for sector, label in config["sectors"].items():
            cohort = []
            for geo in config["states"]:
                s = expected_change(raw, geo, sector, start, end, config["periods"])
                t = expected_change(raw, geo, "TOTAL", start, end, config["periods"])
                delta = s["change_hours"]
                total = t["change_hours"]
                paired = delta is not None and total is not None
                expected = {"geo": geo, "sector": sector, "sector_label": label, "baseline_quarter": start,
                            "target_quarter": end, **s, "total_activity_change_hours": total,
                            "sector_minus_total_change_hours": delta - total if paired else None,
                            "both_unflagged": paired and s["window_flags"] == t["window_flags"] == ""}
                require((end, geo, sector) in comparisons, "Missing planned sector comparison")
                equal(comparisons[end, geo, sector], expected, "Sector comparison or break handling changed")
                cohort.append(expected)
                expected_comparisons += 1
            require((end, sector) in summaries, "Missing sector cohort summary")
            equal(summaries[end, sector], statistics(cohort, sector, start, end), "Sector cohort summary changed")
            expected_summaries += 1
    require(expected_comparisons == len(comparisons) == len(artifact["comparisons"])
            and expected_summaries == len(summaries) == len(artifact["summary"]), "Extra sector comparisons or summaries")
    return {"quarter_values": len(raw), "country_sector_comparisons": expected_comparisons,
            "cohort_summaries": expected_summaries}
