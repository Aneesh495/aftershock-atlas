"""Executable study tables with explicit support, alternatives and unavailable estimands."""
from __future__ import annotations

import csv
from collections import defaultdict

import numpy as np

from .excess import read_workbook
from .geography import age_standardized
from .io import ROOT, digest, read_json, write_json
from .panel import connect, records


def bootstrap_mean(values: list[float], seed: int = 11, replicates: int = 999) -> dict:
    if not values:
        return {"mean": None, "lower": None, "upper": None, "n": 0}
    y = np.asarray(values, float)
    rng = np.random.default_rng(seed)
    draws = [float(rng.choice(y, len(y)).mean()) for _ in range(replicates)]
    lower, upper = np.quantile(draws, [.025, .975])
    return {"mean": float(y.mean()), "lower": float(lower), "upper": float(upper), "n": len(y),
            "interpretation": "country bootstrap describes this eligible set, not randomized pandemic assignment"}


def endpoint_table(metric: str, end: int = 2023) -> list[dict]:
    with connect() as db:
        rows = records(db, """SELECT region,substr(event_start,1,4) yr,value FROM observations
            WHERE metric=? AND value IS NOT NULL AND \"group\"='total'""", [metric])
    panel: dict[str, dict[int, float]] = defaultdict(dict)
    for row in rows:
        panel[row["region"]][int(row["yr"])] = row["value"]
    table = []
    for region, series in sorted(panel.items()):
        if all(year in series for year in (2019, 2020, end)):
            base, onset, latest = series[2019], series[2020], series[end]
            table.append({"region": region, "baseline_year": 2019, "baseline": base,
                          "onset_year": 2020, "onset": onset, "end_year": end, "end": latest,
                          "onset_change": onset - base, "change": latest - base,
                          "percent_change": (latest / base - 1) * 100 if base else None})
    return table


def age_comparison() -> tuple[list[dict], dict]:
    source = read_json(ROOT / "data/raw/index.json")["excess_2022"]
    rows = read_workbook(ROOT / "data/raw" / source["path"])["Country by year, sex and age"]
    chosen = [r for r in rows if r["iso3"] in {"USA", "GBR"}]
    bands = sorted({r["age"] for r in chosen})
    standard = np.array([sum(r["nx"] for r in chosen if r["year"] == 2020 and r["age"] == band) for band in bands], float)
    weights = standard / standard.sum()
    table, raw = [], []
    for region in ("USA", "GBR"):
        for year in (2020, 2021):
            counts = [sum(r["acm.mean"] for r in chosen if r["iso3"] == region and r["year"] == year and r["age"] == band) for band in bands]
            population = [sum(r["nx"] for r in chosen if r["iso3"] == region and r["year"] == year and r["age"] == band) for band in bands]
            if any(p <= 0 for p in population):
                raise ValueError("Age denominator missing")
            rate = age_standardized(counts, population, weights.tolist())
            crude = sum(counts) / sum(population) * 100000
            table.append({"region": region, "year": year, "crude_per_100k": crude,
                          "standardized_per_100k": rate["rate"], "numerical_poisson_se": rate["se"],
                          "change_from_crude_percent": (rate["rate"] / crude - 1) * 100,
                          "kind": "modeled_age_specific_allcause_mortality", "standard": "pooled USA+GBR 2020 WHO 2022 population"})
            raw.extend({"region": region, "year": year, "age": band, "count": c, "population": p, "standard_weight": float(w)}
                       for band, c, p, w in zip(bands, counts, population, weights))
    return table, {"bands": bands, "raw": raw, "source_hash": source["sha256"],
                   "limitation": "Numerical Poisson approximation does not include WHO model uncertainty or covariance"}


def run_studies() -> dict:
    directory = ROOT / "data/results"
    protocols = read_json(ROOT / "configs/studies.json")
    excess, survey, causal, genetics, lineage, mobility = [read_json(directory / f"{name}.json")
        for name in ("excess", "surveys", "causal", "genetics", "lineages", "mobility")]
    scenarios = read_json(directory / "scenarios.json")
    fit = read_json(directory / "fit.json")
    output = []

    def result(number: int, table: list[dict], summary: dict, conclusion: str, support: str = "bounded_analysis"):
        protocol = protocols["studies"][number - 1]
        payload = {**protocol, "status": support, "table": table, "summary": summary, "conclusion": conclusion,
                   "protocol_sha256": digest(ROOT / "configs/studies.json"),
                   "source_panel_sha256": read_json(ROOT / "data/panel/manifest.json")["sha256"]}
        write_json(directory / "studies" / f"{protocol['id']}.json", payload)
        if table:
            path = directory / "studies" / f"{protocol['id']}.csv"
            with path.open("w", newline="") as stream:
                keys = list(dict.fromkeys(key for row in table for key in row))
                writer = csv.DictWriter(stream, fieldnames=keys)
                writer.writeheader()
                writer.writerows(table)
        output.append(payload)

    ratios = [r["ratio"] for r in excess["annual"] if r["ratio"] is not None]
    result(1, excess["annual"], {"eligible_country_years": len(ratios), "above_one": sum(r > 1 for r in ratios),
           "above_1_2": sum(r > 1.2 for r in ratios), "revision_cells": len(excess["monthly_revision_rows"]),
           "median_absolute_monthly_revision": float(np.median([abs(r["delta"]) for r in excess["monthly_revision_rows"]]))},
           "Modeled excess and reported COVID death totals differ across jointly measured country-years. Ratios mix event-year estimates and report-week counts and cannot isolate reporting bias.")
    with connect() as db:
        reporting = records(db, """SELECT region,metric,count(*) total_weeks,count(value) reported_weeks,
            sum(CASE WHEN value<0 THEN 1 ELSE 0 END) negative_weeks,
            min(CASE WHEN value<0 THEN value END) minimum_correction
            FROM observations WHERE metric IN ('covid_cases','covid_deaths') GROUP BY region,metric ORDER BY region,metric""")
    for row in reporting:
        row["missing_fraction"] = 1 - row["reported_weeks"] / row["total_weeks"]
    result(2, reporting, {"areas": len({r["region"] for r in reporting}),
           "negative_correction_weeks": sum(r["negative_weeks"] for r in reporting),
           "area_metrics_above_20pct_missing": sum(r["missing_fraction"] > .2 for r in reporting)},
           "Signed corrections and long missing runs occur in the reported surveillance panel. Missingness is not evidence of no infections or deaths.")
    ages, age_raw = age_comparison()
    write_json(directory / "age-replay.json", age_raw)
    result(3, ages, {"standard_bands": age_raw["bands"], "independently_recomputable": True,
           "source_release": "WHO May 2022", "2023_comparable_bands": False},
           "Common-population age standardization changes the crude mortality contrasts. This is a check on modeled aggregate age composition, not an estimate of racial or individual risk.")
    result(4, mobility["annual"], {"mobility_countries": mobility["country_count"], "device_denominator": None,
           "employment_countries": next(r["countries"] for r in read_json(ROOT / "data/panel/manifest.json")["coverage"] if r["metric"] == "employment")},
           "Within-UK workplace visits declined relative to a short weekday baseline. The opt-in device population cannot identify employment, hours or unequal occupational exposure.", "partial_outcome_support")
    health = [r for r in scenarios if r["metric"] == "immunization" and r["year"] == 2021 and r["observed"] is not None]
    table = [{"region": r["region"], "year": 2021, "observed_estimate": r["observed"], "trend": r["scenario"],
              "lower": r["lower"], "upper": r["upper"], "gap_pp": r["observed"] - r["scenario"],
              "local_level_gap_pp": r["observed"] - r["alternative_level"]} for r in health]
    result(5, table, {"eligible": len(table), "below_trend": sum(r["gap_pp"] < 0 for r in table),
           "below_trend_2pp": sum(r["gap_pp"] < -2 for r in table)},
           "Routine immunization differences depend on the chosen pre-period baseline. The trend and local-level comparisons remain predictive sensitivities; neither identifies a pandemic effect.")
    result(6, causal["cells"], {"adoption_counts": causal["adoption_counts"], "pretrends": causal["pretrends"],
           "pseudo_onsets": causal["pseudo_onsets"], "identification": causal["identification"]},
           "Some group-time cells can be calculated, but school closures coincide with other policies and epidemic changes. The two-country late-adoption cohort fails minimum support. Causal identification is not established.")
    employment, later = endpoint_table("employment"), endpoint_table("employment", 2024)
    result(7, employment, {"change_pp": bootstrap_mean([r["change"] for r in employment]),
           "below_2019": sum(r["change"] < 0 for r in employment), "2024_sensitivity": bootstrap_mean([r["change"] for r in later])},
           "Employment recovery differs across the matched country estimates. The eligible sample and endpoint year change the summary; these ratios also depend on demographic composition.")
    gdp = endpoint_table("gdp")
    result(8, gdp, {"percent_change": bootstrap_mean([r["percent_change"] for r in gdp if r["percent_change"] is not None]),
           "2024_sensitivity": bootstrap_mean([r["percent_change"] for r in endpoint_table("gdp", 2024) if r["percent_change"] is not None]),
           "hours_available": False},
           "Constant-price per-person GDP trajectories differ across matched countries. The panel contains no hours series and cannot estimate working hours lost.", "partial_outcome_support")
    schooling = endpoint_table("school")
    result(9, schooling, {"enrollment_change_pp": bootstrap_mean([r["change"] for r in schooling]),
           "remote_instruction_available": False, "learning_assessment_available": False},
           "Gross secondary enrollment changes are observed for a selected subset of countries. Enrollment, remote instruction and learning attainment are distinct outcomes. Missing assessment data prevents a learning-loss estimate.", "partial_outcome_support")
    result(10, survey["phase_changes"], {"states": survey["state_count"], "phases": survey["phases"],
           "suppressed": survey["suppressed"], "independent_weight_recomputation": "week_1_only",
           "weight_point_matches": survey["design_replay"]["point_matches"], "weight_point_comparisons": survey["design_replay"]["point_comparisons"]},
           "Within-phase published symptom estimates vary across US groups and states. A separate week 1 public-use replay audits person and replicate weights and source-defined subgroup denominators. Later weights, nonresponse bias and cross-wave covariance remain unresolved. The question reference period changes in July 2021.", "partial_design_support")
    dominant = {}
    for row in lineage["rows"]:
        if row["value"] is not None and (row["week"] not in dominant or row["value"] > dominant[row["week"]]["value"]):
            dominant[row["week"]] = row
    result(11, sorted(dominant.values(), key=lambda r: r["week"]),
           {k: v for k, v in lineage.items() if k != "rows"},
           "The highest reliable reported lineage estimate changes across the archived US national window. Overlapping lineage labels and sequencing selection prevent interpreting these rows as an exhaustive prevalence partition.")
    result(12, genetics["representatives"], {k: v for k, v in genetics.items() if k != "representatives"},
           "Effect-allele harmonization aligns aggregate selected-variant associations after ambiguous-strand exclusions. Shared samples and LD prevent treating concordance as independent replication.")
    summary = {"protocol_version": protocols["version"], "studies": output, "count": len(output),
               "bounded_analyses": sum(s["status"] == "bounded_analysis" for s in output),
               "partial_support": sum(s["status"].startswith("partial") for s in output),
               "forecast_configurations": fit["completed_configurations"], "full_domain_acceptance": False}
    write_json(directory / "studies.json", summary)
    return {k: v for k, v in summary.items() if k != "studies"}
