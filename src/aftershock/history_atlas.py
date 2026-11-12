"""Versioned historical comparisons with source identities and partitioned exports."""
from __future__ import annotations

import numpy as np
import duckdb

from .contracts import METRICS
from .history import UNITS, edition_bound
from .io import ROOT, digest, read_json, write_json
from .resources import usage


def feature_vintage_sensitivity():
    from .history import history_cube
    from .history_features import final_history_truth, transformed
    from .features import OUTCOMES
    plan = read_json(ROOT / "configs/history-plan.json")
    histories = {edition: history_cube(edition)[1] for edition in plan["editions"]}
    final = final_history_truth()
    countries = [r["id"] for r in read_json(ROOT / "data/panel/regions.json")]
    editions = {int(e[:4]): e for e in plan["editions"]}
    initial = histories[plan["editions"][0]]
    rows = []
    for region in countries:
        for year in range(2019, 2025):
            edition = editions[year - 1]
            for metric in OUTCOMES:
                a = transformed(histories[edition], region, year - 2, metric)
                b = transformed(initial, region, year - 2, metric)
                c = transformed(final, region, year - 2, metric)
                values = [float(x) if np.isfinite(x) else None for x in (a, b, c)]
                rows.append({"region": region, "metric": metric, "target_year": year, "endpoint_year": year - 2,
                    "edition": edition, "archived_endpoint_t": values[0], "initial_edition_endpoint_t": values[1],
                    "current_endpoint_t": values[2], "current_minus_archived_t": c - a if np.isfinite(c) and np.isfinite(a) else None,
                    "unit": "log1p 2010=100 within-edition index" if metric == "gdp" else UNITS[metric],
                    "interpretation": "feature revision sensitivity; current values never fill archived model inputs"})
    write_json(ROOT / "data/results/history-sensitivity.json", rows)
    return rows


def archive_rows(edition, metric):
    db = duckdb.connect(":memory:")
    db.execute("SET memory_limit='512MB'")
    db.execute("SET threads=2")
    try:
        result = db.execute("SELECT region,year,value,raw_value,anchor_2010,flags FROM read_parquet(?) WHERE edition=? AND metric=? ORDER BY region,year",
            [str(ROOT / "data/history/observations.parquet"), edition, metric])
        keys = [column[0] for column in result.description]
        return [dict(zip(keys, row)) for row in result.fetchall()]
    finally:
        db.close()


def revision_study():
    plan = read_json(ROOT / "configs/history-plan.json")
    pins = read_json(ROOT / "configs/history-inputs.json")
    early, late = plan["editions"][0], plan["editions"][-1]
    comparisons, summaries, reversals = [], [], []
    for metric in plan["series"]:
        old = {(r["region"], r["year"]): r for r in archive_rows(early, metric) if r["year"] <= 2017}
        new = {(r["region"], r["year"]): r for r in archive_rows(late, metric) if r["year"] <= 2017}
        cells = []
        for region, year in sorted(set(old) | set(new)):
            a, b = old.get((region, year), {}).get("value"), new.get((region, year), {}).get("value")
            delta = b - a if a is not None and b is not None else None
            row = {"region": region, "year": year, "metric": metric, "old_edition": early, "new_edition": late,
                "old_value": a, "new_value": b, "change": delta, "unit": UNITS[metric],
                "old_source_sha256": pins[f"archive_{early}_{metric}"]["sha256"],
                "new_source_sha256": pins[f"archive_{late}_{metric}"]["sha256"],
                "old_available_bound": edition_bound(early), "new_available_bound": edition_bound(late),
                "comparison_kind": "within-edition indexed revisions" if metric == "gdp" else "provider-estimate revisions"}
            comparisons.append(row)
            cells.append(row)
        matched = [r for r in cells if r["change"] is not None]
        changes = np.array([r["change"] for r in matched])
        summaries.append({"metric": metric, "unit": UNITS[metric], "matched_cells": len(matched),
            "unmatched_cells": len(cells) - len(matched), "exactly_changed_cells": int(np.sum(changes != 0)),
            "median_signed_revision": float(np.median(changes)), "median_absolute_revision": float(np.median(abs(changes))),
            "p95_absolute_revision": float(np.quantile(abs(changes), .95)),
            "interpretation": "complete frozen panel comparison; not independent sampled observations"})
        for region in sorted({r["region"] for r in cells}):
            endpoints = [lookup.get((region, year), {}).get("value") for lookup in (old, new) for year in (2010, 2017)]
            if any(v is None for v in endpoints):
                continue
            before, after = endpoints[1] - endpoints[0], endpoints[3] - endpoints[2]
            reversals.append({"region": region, "metric": metric, "old_edition": early, "new_edition": late,
                "change_2010_2017_old": before, "change_2010_2017_new": after,
                "opposite_nonzero_directions": bool(before * after < 0), "unit": UNITS[metric]})
    result = {"protocol": "historical-v3-exploratory", "hypothesis": "Past reference-year values do not change across official archive editions",
        "early_edition": early, "late_edition": late, "reference_years": [2000, 2017],
        "rows": comparisons, "summaries": summaries, "trajectory_signs": reversals,
        "metadata_proves_historical_definition": False,
        "conclusion": "Differences include revisions, precision and definition changes; they are not pandemic causal effects",
        "source_panel_sha256": digest(ROOT / "data/history/observations.parquet")}
    write_json(ROOT / "data/results/history-revisions.json", result)
    return result


def export_history():
    usage(250_000_000)
    manifest = read_json(ROOT / "data/history/manifest.json")
    plan = read_json(ROOT / "configs/history-plan.json")
    pins = read_json(ROOT / "configs/history-inputs.json")
    public = ROOT / "client/public/data"
    files, anchors = {}, []
    for edition in plan["editions"]:
        for metric in plan["series"]:
            source = pins[f"archive_{edition}_{metric}"]
            inventory = next(r for r in manifest["inventory"] if r["edition"] == edition and r["metric"] == metric)
            source_rows = archive_rows(edition, metric)
            rows = [{k: r[k] for k in ("region", "year", "value")} for r in source_rows]
            if metric == "gdp":
                anchors.extend({"region": r["region"], "edition": edition, "raw_2010": r["raw_value"],
                    "source_sha256": source["sha256"], "unit": "provider constant-price per-capita units; price base not reasserted"}
                    for r in source_rows if r["year"] == 2010)
            payload = {"edition": edition, "metric": metric, "unit": UNITS[metric],
                "kind": "derived_index" if metric == "gdp" else "provider_estimate", "source_sha256": source["sha256"],
                "edition_available_at": edition_bound(edition), "acquired_at": source["acquired_at"], "rows": rows,
                "future_values_withheld": inventory["excluded_future_values"], "license": source["rights"],
                "availability_basis": manifest["availability_basis"], "limitations": manifest["limitations"]}
            name = f"hist_{edition}_{metric}.json"
            write_json(public / name, payload)
            files[name] = {"sha256": digest(public / name), "bytes": (public / name).stat().st_size}
    revisions = revision_study()
    sensitivity = feature_vintage_sensitivity()
    for metric in plan["series"]:
        if metric == "population":
            continue
        name = f"history-sensitivity_{metric}.json"
        write_json(public / name, {"rows": [r for r in sensitivity if r["metric"] == metric]})
        files[name] = {"sha256": digest(public / name), "bytes": (public / name).stat().st_size}
    write_json(ROOT / "data/results/history-anchors.json", anchors)
    write_json(public / "history-revisions.json", {k: v for k, v in revisions.items() if k != "rows"})
    files["history-revisions.json"] = {"sha256": digest(public / "history-revisions.json"), "bytes": (public / "history-revisions.json").stat().st_size}
    fit = read_json(ROOT / "data/results/history-fit.json")
    support = [{"metric": metric, "year": year, "eligible_outcomes": next((r["n"] for r in fit["scores"]
        if r["model"] == "persistence" and r["metric"] == metric and r["group"] == f"year:{year}"), 0)}
        for metric in plan["series"] if metric != "population" for year in range(2019, 2025)]
    write_json(public / "history-scores.json", {**{k: v for k, v in fit.items() if k not in
        {"training", "baseline_parameters", "prediction_files", "feature_sources"}}, "test_support": support})
    files["history-scores.json"] = {"sha256": digest(public / "history-scores.json"), "bytes": (public / "history-scores.json").stat().st_size}
    index = {"protocol": "historical-v3-exploratory", "editions": plan["editions"], "inventory": manifest["inventory"],
        "metrics": {metric: {"title": "Real GDP per capita, indexed within edition" if metric == "gdp" else METRICS[metric].title,
                            "unit": UNITS[metric]} for metric in plan["series"]},
        "availability_basis": manifest["availability_basis"], "limitations": manifest["limitations"],
        "panel_sha256": manifest["sha256"], "files": files}
    write_json(public / "history-index.json", index)
    write_json(ROOT / "data/results/history-export.json", index)
    return {"editions": len(plan["editions"]), "partitions": len(plan["editions"]) * len(plan["series"]),
            "revision_cells": len(revisions["rows"]), "public_bytes": sum(v["bytes"] for v in files.values())}
