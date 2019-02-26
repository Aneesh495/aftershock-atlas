"""Survey estimands retain instrument, phase, mode and denominator limitations."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .io import ROOT, write_json
from .panel import connect, records
from .privacy import Disclosure


@dataclass(frozen=True)
class SurveyDesign:
    instrument: str
    mode: str
    country: str
    reference_days: int
    weight_basis: str

    def comparable(self, other: SurveyDesign) -> bool:
        return self == other


def weighted_mean(y, weights, psu: list[str], strata: list[str]) -> dict:
    values, w = np.asarray(y, float), np.asarray(weights, float)
    n = len(values)
    if not n or w.shape != values.shape or len(psu) != n or len(strata) != n:
        raise ValueError("Survey arrays must align")
    if not np.isfinite(values).all() or not np.isfinite(w).all() or (w <= 0).any():
        raise ValueError("Finite outcomes and positive design weights required")
    total, mean = float(w.sum()), float(np.sum(w * values) / w.sum())
    linearized = w * (values - mean) / total
    stratum_psu: dict[str, dict[str, float]] = {}
    for s, p, residual in zip(strata, psu, linearized):
        group = stratum_psu.setdefault(s, {})
        group[p] = group.get(p, 0) + residual
    variance, df = 0.0, 0
    for group in stratum_psu.values():
        if len(group) < 2:
            raise ValueError("Singleton PSU needs an explicit design treatment")
        sums = np.array(list(group.values()))
        variance += len(sums) / (len(sums) - 1) * float(np.sum((sums - sums.mean()) ** 2))
        df += len(sums) - 1
    return {"mean": mean, "se": variance ** .5, "df": df, "weight_sum": total,
            "kish_effective_n": float(w.sum() ** 2 / np.sum(w ** 2)), "sample_n": n,
            "variance": "Taylor linearization of weighted mean, stratified cluster design"}


def nonresponse_envelope(proportion: float, response: float) -> tuple[float, float]:
    if not 0 <= proportion <= 1 or not 0 < response <= 1:
        raise ValueError("Proportion and response must lie in the unit interval")
    return response * proportion, response * proportion + 1 - response


def analyze_surveys() -> dict:
    with connect() as db:
        rows = records(db, """SELECT region,event_start,event_end,value,lower,upper,\"group\",flags
            FROM observations WHERE metric='anxiety' ORDER BY region,\"group\",event_start""")
    safe = []
    for row in rows:
        safe.append(Disclosure().apply({**row, "release_basis": "upstream_public_aggregate",
                                      "phase": row["flags"].split("phase=")[-1].split(";")[0]}))
    for row in safe:
        row["reference_days"] = 7 if row["event_start"] < "2021-07-21" else 14
    groups: dict[tuple, list[dict]] = {}
    for row in safe:
        if row["value"] is not None:
            groups.setdefault((row["region"], row["group"], row["phase"]), []).append(row)
    changes = []
    for (region, group, phase), series in groups.items():
        if len(series) < 2:
            continue
        first, last = series[0], series[-1]
        if first["lower"] is None or last["lower"] is None:
            continue
        # Published intervals provide a conservative SE sum when cross-wave covariance is unknown.
        radius = (first["upper"] - first["lower"] + last["upper"] - last["lower"]) / 2
        delta = last["value"] - first["value"]
        changes.append({"region": region, "group": group, "phase": phase, "first": first["event_start"],
                        "last": last["event_end"], "waves": len(series), "first_value": first["value"], "last_value": last["value"],
                        "change_pp": delta, "lower": delta - radius, "upper": delta + radius,
                        "interval_method": "sum of published marginal half-widths; unknown covariance; approximate conservative bound",
                        "matched_respondents": False})
    from .survey_design import analyze_design
    design = analyze_design()
    result = {"design_replay": {k: v for k, v in design.items() if k != "sources"}, "rows": safe, "phase_changes": changes, "country_count": 1,
              "state_count": len({r["region"] for r in safe if r["region"] != "USA"}),
              "phases": sorted({r["phase"] for r in safe}), "suppressed": sum(r["value"] is None for r in safe),
              "instrument": "PHQ-2 / GAD-2 symptoms, 7-day reference before July 21 2021 and 14 days thereafter; not a clinical diagnosis",
              "mode": "Census Household Pulse online household survey; weighted estimates published by NCHS",
              "independent_weight_recomputation": "week_1_only", "response_rate_available_in_extract": False,
              "limitations": ["Published aggregates lack individual design information; week 1 is separately replayed from lawful public-use files",
                              "Cross-wave samples are not a matched panel", "No comparable pre-2020 series is present",
                              "Between-phase changes are not treated as instrument-stable effects",
                              "US source-defined race and ethnicity groups are not exported as universal categories"],
              "source": "https://data.cdc.gov/d/8pt5-q6wp"}
    write_json(ROOT / "data/results/surveys.json", result)
    return {k: v for k, v in result.items() if k not in {"rows", "phase_changes", "design_replay"}}
