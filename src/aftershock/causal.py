"""Group-time comparisons expose unsupported identification instead of inventing controls."""
from __future__ import annotations

from collections import Counter

import numpy as np
from scipy.stats import ttest_ind

from .io import ROOT, read_json, write_json
from .panel import connect, records


def group_time(panel: dict[str, dict[int, float]], adoption: dict[str, int | None], cohort: int,
               target: int, min_group: int = 5, bootstrap: int = 499, seed: int = 11) -> dict:
    baseline = cohort - 1
    treated, controls = [], []
    for region, series in panel.items():
        if baseline not in series or target not in series:
            continue
        delta = series[target] - series[baseline]
        if adoption.get(region) == cohort:
            treated.append((region, delta))
        elif adoption.get(region) is None or adoption[region] > max(target, cohort):
            controls.append((region, delta))
    out = {"cohort": cohort, "target_year": target, "baseline_year": baseline,
           "treated_n": len(treated), "control_n": len(controls),
           "treated_regions": [r for r, _ in treated], "control_regions": [r for r, _ in controls],
           "estimand": "unconditional group-time ATT under unverified parallel trends and no interference"}
    if len(treated) < min_group or len(controls) < min_group:
        return {**out, "status": "unsupported", "effect": None, "lower": None, "upper": None,
                "reason": f"Requires at least {min_group} treated and {min_group} not-yet-treated or never-treated controls"}
    a, b = np.array([v for _, v in treated]), np.array([v for _, v in controls])
    estimate = float(a.mean() - b.mean())
    rng = np.random.default_rng(seed)
    draws = [float(rng.choice(a, len(a)).mean() - rng.choice(b, len(b)).mean()) for _ in range(bootstrap)]
    low, high = np.quantile(draws, [.025, .975])
    return {**out, "status": "computed_under_assumptions", "effect": estimate, "lower": float(low),
            "upper": float(high), "bootstrap_replicates": bootstrap,
            "sensitivity_differential_trend_1pp": [estimate - abs(target - baseline), estimate + abs(target - baseline)]}


def pretrend(panel: dict[str, dict[int, float]], adoption: dict[str, int | None], cohort: int) -> dict:
    treated, controls = [], []
    for region, series in panel.items():
        years = list(range(cohort - 4, cohort))
        if not all(y in series for y in years):
            continue
        slope = float(np.polyfit(np.arange(4), [series[y] for y in years], 1)[0])
        if adoption.get(region) == cohort:
            treated.append(slope)
        elif adoption.get(region) is None or adoption[region] > cohort:
            controls.append(slope)
    if len(treated) < 5 or len(controls) < 5:
        return {"status": "unsupported", "treated_n": len(treated), "control_n": len(controls), "p": None,
                "reason": "Insufficient independent countries with four pre-period values"}
    test = ttest_ind(treated, controls, equal_var=False)
    return {"status": "computed", "treated_n": len(treated), "control_n": len(controls),
            "slope_difference_pp_year": float(np.mean(treated) - np.mean(controls)), "p": float(test.pvalue),
            "parallel_trends_established": False, "note": "Non-rejection cannot establish parallel trends"}


def candidate_causal() -> dict:
    with connect() as db:
        policies = records(db, """SELECT region,min(event_start) adoption FROM observations
            WHERE metric='school_policy' AND value=3 GROUP BY region""")
        outcomes = records(db, """SELECT region,substr(event_start,1,4) AS yr,value FROM observations
            WHERE metric='employment' AND value IS NOT NULL AND \"group\"='total'""")
        eligible = {r[0] for r in db.execute("SELECT DISTINCT region FROM observations WHERE metric='school_policy'").fetchall()}
    dates = {r["region"]: r["adoption"] for r in policies}
    adoption = {r: int(dates[r][:4]) if r in dates else None for r in eligible}
    panel: dict[str, dict[int, float]] = {}
    for row in outcomes:
        if row["region"] in eligible:
            panel.setdefault(row["region"], {})[int(row["yr"])] = row["value"]
    cohorts = sorted({v for v in adoption.values() if v is not None})
    cells, checks, placebos = [], [], []
    for cohort in cohorts:
        checks.append({"cohort": cohort, **pretrend(panel, adoption, cohort)})
        for target in range(cohort, 2025):
            cells.append(group_time(panel, adoption, cohort, target))
        shifted = {r: None if year is None else year - 2 for r, year in adoption.items()}
        placebos.append(group_time(panel, shifted, cohort - 2, cohort - 2))
    result = {"candidate": "Full national school closure and annual employment",
              "treatment": "First OxCGRT C1M=3 date for NAT_TOTAL majority population",
              "adoption_counts": {str(k): v for k, v in Counter(adoption.values()).items()},
              "adoption_dates": dates, "outcome": "ILO modeled employment to population age 15+",
              "cells": cells, "pretrends": checks, "pseudo_onsets": placebos,
              "identification": "not_established", "display_class": "descriptive_candidate_diagnostics",
              "failed_assumptions": ["Policy bundles and epidemic severity jointly determine adoption",
                                     "School closure is not a randomized intervention or measured adherence",
                                     "Anticipation and international spillovers remain unresolved",
                                     "Annual outcomes hide within-year adoption differences"],
              "no_mediator_adjustment": True, "source_panel": read_json(ROOT / "data/panel/manifest.json")["sha256"]}
    write_json(ROOT / "data/results/causal.json", result)
    return result
