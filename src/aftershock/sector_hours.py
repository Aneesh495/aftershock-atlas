"""Track the Eurostat cohort of employed people present in their main job."""

from __future__ import annotations

import itertools
import math
from pathlib import Path
from statistics import median

from .acquire import Source, acquire_one
from .io import ROOT, digest, read_json, source_commit, write_json
from .resources import usage

CONFIG = ROOT / "configs/sector-hours-v6.json"
PINS = ROOT / "configs/sector-hours-inputs.json"
RAW = ROOT / "data/labor/raw"
RESULT = ROOT / "data/results/sector-hours.json"


def acquire_sectors() -> dict:
    source, = read_json(PINS).values()
    spec = Source(**{field: source[field] for field in Source.__dataclass_fields__})
    receipt = acquire_one(spec, RAW)
    if (receipt["sha256"], receipt["bytes"]) != (source["sha256"], source["bytes"]):
        raise ValueError("Eurostat source moved beyond the pinned release")
    return {"sources": 1}


def ordered_axis(categories: dict, size: int) -> list[str]:
    positions = categories["index"]
    if isinstance(positions, dict):
        if set(positions.values()) != set(range(size)):
            raise ValueError("Invalid JSON-stat category coordinates")
        return sorted(positions, key=positions.__getitem__)
    if len(positions) != size or len(set(positions)) != size:
        raise ValueError("Invalid JSON-stat category order")
    return positions


def cube(path: Path, config: dict) -> tuple[dict, dict]:
    data = read_json(path)
    domains = {dim: {code} for dim, code in config["fixed"].items()}
    domains.update(nace_r2=set(config["sectors"]), geo=set(config["states"]), time=set(config["periods"]))
    dims, shape = data["id"], data["size"]
    if data.get("class") != "dataset" or len(dims) != len(shape) or set(dims) != set(domains):
        raise ValueError("Eurostat cube schema changed")
    axes = [ordered_axis(data["dimension"][dim]["category"], n) for dim, n in zip(dims, shape, strict=True)]
    if any(set(axis) != domains[dim] for dim, axis in zip(dims, axes, strict=True)):
        raise ValueError("Eurostat fixed denominator, jurisdiction, sector or quarter changed")
    measurements, flags = data["value"], data.get("status", {})
    size = math.prod(shape)
    for key in set(measurements) | set(flags):
        if not key.isdecimal() or str(int(key)) != key or int(key) >= size:
            raise ValueError("Eurostat cell address outside registered cube")
    out = {}
    for i, coordinates in enumerate(itertools.product(*axes)):
        identity = dict(zip(dims, coordinates, strict=True))
        value = measurements.get(str(i))
        mark = flags.get(str(i), "")
        if value is not None and (type(value) not in {int, float} or not math.isfinite(value) or not 0 <= value <= 168):
            raise ValueError("Eurostat hours outside weekly scale")
        if type(mark) is not str or not set(mark) <= set("bcdefmnpuz"):
            raise ValueError("Unregistered Eurostat observation status")
        out[identity["geo"], identity["nace_r2"], identity["time"]] = {"hours": value, "flags": mark, "cell": i}
    return out, {"released_update": data["updated"], "cube_size": size}


def change(cells: dict, periods: list[str], withheld_flags: set[str]) -> dict:
    window = [cells[period] for period in periods]
    issues = sorted({flag for point in window for flag in point["flags"]})
    missing = sum(point["hours"] is None for point in window)
    unfit = sorted(set(issues) & withheld_flags)
    baseline, target = window[0], window[-1]
    raw_difference = None
    if not unfit and not missing:
        raw_difference = round(target["hours"] - baseline["hours"], 9)
    return {
        "baseline_hours": baseline["hours"], "target_hours": target["hours"],
        "baseline_cell": baseline["cell"], "target_cell": target["cell"],
        "change_hours": raw_difference, "window_flags": "".join(issues),
        "unfit_flags": "".join(unfit), "missing_quarters": missing,
    }


def changes(points: dict, config: dict) -> tuple[list[dict], list[dict]]:
    periods = config["periods"]
    excluded = set(config["withhold_flags"])
    out = []
    for before, after in config["windows"]:
        window = periods[periods.index(before):periods.index(after) + 1]
        for state in config["states"]:
            comparisons = {
                sector: change({t: points[state, sector, t] for t in window}, window, excluded)
                for sector in config["sectors"]
            }
            total = comparisons["TOTAL"]
            for sector, comparison in comparisons.items():
                effect = comparison["change_hours"]
                baseline = total["change_hours"]
                out.append({
                    "geo": state, "sector": sector, "sector_label": config["sectors"][sector],
                    "baseline_quarter": before, "target_quarter": after, **comparison,
                    "total_activity_change_hours": baseline,
                    "sector_minus_total_change_hours": (
                        round(effect - baseline, 9) if effect is not None and baseline is not None else None
                    ),
                    "both_unflagged": not (comparison["window_flags"] or total["window_flags"]) and
                        effect is not None and baseline is not None,
                })
    summary = []
    for before, after in config["windows"]:
        for sector in config["sectors"]:
            choices = [r for r in out if r["sector"] == sector and r["target_quarter"] == after]
            all_changes = [r["change_hours"] for r in choices if r["change_hours"] is not None]
            differences = [r["sector_minus_total_change_hours"] for r in choices
                           if r["sector_minus_total_change_hours"] is not None]
            clean = [r["change_hours"] for r in choices if r["both_unflagged"]]
            summary.append({
                "sector": sector, "baseline_quarter": before, "target_quarter": after,
                "matched_countries": len(all_changes), "unflagged_matches_to_total": len(clean),
                "below_by_one_hour": sum(x <= -config["practical_hours"] for x in all_changes),
                "above_by_one_hour": sum(x >= config["practical_hours"] for x in all_changes),
                "median_change_hours": median(all_changes) if all_changes else None,
                "paired_total_matches": len(differences),
                "median_sector_minus_total_change_hours": median(differences) if differences else None,
                "median_unflagged_change_hours": median(clean) if clean else None,
            })
    return out, summary


def run_sectors() -> dict:
    usage(15_000_000)
    config = read_json(CONFIG)
    pin = read_json(PINS)["eurostat_sector_hours"]
    path = RAW / pin["path"]
    if path.stat().st_size != pin["bytes"] or digest(path) != pin["sha256"]:
        raise ValueError("Eurostat pinned raw bytes fail identity")
    points, metadata = cube(path, config)
    rows, summary = changes(points, config)
    data = {"schema_version": 1, "source": source_commit(), "source_sha256": pin["sha256"],
            "definition_sha256": digest(CONFIG), "input_sha256": digest(PINS),
            "population": config["population"], "unit": config["unit"], **metadata,
            "source_citation": pin["citation"],
            "comparisons": rows, "summary": summary,
            "observations": [{"geo": region, "sector": sector, "quarter": time, **point}
                             for (region, sector, time), point in sorted(points.items())]}
    write_json(RESULT, data)
    return data
