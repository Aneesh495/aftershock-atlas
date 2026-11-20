"""Replay CPS estimates with a bounded vectorized join and explicit populations."""

from __future__ import annotations

from itertools import islice
from pathlib import Path
from zipfile import ZipFile

import numpy as np

from .io import ROOT, digest, read_json
from .verification import require
from .verify_sector_hours import equal


def read_columns(raw: Path, record: dict, layout: dict, widths: dict) -> np.ndarray:
    archive_path = raw / record["path"]
    require(archive_path.stat().st_size == record["bytes"] and digest(archive_path) == record["sha256"],
            "CPS private input identity changed")
    total = widths["record_count"]
    block = np.empty((total, len(layout)), dtype=np.int64)
    labels = list(layout)
    if len(widths["record_widths"]) == 1:
        record_width = widths["record_widths"][0]
    else:
        record_width = max(widths["record_widths"])
    dtype = np.dtype({"names": labels, "formats": [f"S{hi - lo + 1}" for lo, hi in layout.values()],
                      "offsets": [lo - 1 for lo, _ in layout.values()], "itemsize": record_width})
    cap = 150_000_000 if record["id"].startswith("cps_basic") else 8_000_000
    with ZipFile(archive_path) as archive:
        members = archive.infolist()
        require(len(members) == 1 and members[0].filename == widths["archive_member"] and
                members[0].file_size <= cap, "CPS archive scope changed")
        count = 0
        with archive.open(members[0]) as stream:
            while batch := list(islice(stream, 4096)):
                rows = [row.rstrip(b"\r\n") for row in batch]
                require(count + len(rows) <= total and all(len(row) in widths["record_widths"] for row in rows),
                        "CPS record count or width changed")
                records = np.asarray(rows, dtype=dtype.str).view(dtype)
                for i, label in enumerate(labels):
                    clean = np.char.strip(records[label])
                    block[count:count + len(rows), i] = np.where(clean == b"", b"-1", clean).astype(np.int64)
                count += len(rows)
        require(count == total, "CPS record count changed")
    return block


def keys(cps: dict[str, np.ndarray]) -> np.ndarray:
    return cps["household_key"] * 100 + cps["person_key"]


def cohort_replay(raw: Path, pins: dict, config: dict, month: str) -> tuple[dict, np.ndarray, dict]:
    suffix = month.replace("-", "")
    source_ids = {kind: f"cps_{kind}_{suffix}" for kind in ("basic", "covid")}
    data = {}
    year, month_num = map(int, month.split("-"))
    for kind, identity in source_ids.items():
        layout = config["fields"][kind]
        matrix = read_columns(raw, pins[identity], layout, config["sources"][identity])
        cols = dict(zip(layout, matrix.T, strict=True))
        require((cols["month"] == month_num).all() and (cols["year"] == (year if kind == "basic" else year % 100)).all(),
                "CPS source month changed")
        data[kind] = cols
    base, survey = data["basic"], data["covid"]
    extract_keys = keys(survey)
    native_keys = keys(base)
    surveyed = (base["household_key"] > 0) & (base["person_key"] > 0)
    require(len(np.unique(extract_keys)) == len(extract_keys) and len(np.unique(native_keys[surveyed])) == surveyed.sum()
            and np.isin(extract_keys, native_keys[surveyed]).all(), "CPS partner identity mismatch")
    eligible = (base["person_type"] == 2) & (base["age"] >= 16) & np.isin(base["employment"], [1, 2])
    selected = native_keys[eligible]
    order = np.argsort(extract_keys)
    hits = np.searchsorted(extract_keys[order], selected)
    require((hits < len(order)).all() and np.array_equal(extract_keys[order[hits]], selected),
            "CPS eligible worker missing an extract partner")
    responses = np.stack((survey["telework"], survey["unable_to_work"]))[:, order[hits]]
    require(np.isin(responses, [-1, 1, 2]).all(), "CPS response code changed")
    adults = {field: base[field][eligible] for field in ("industry", "occupation", "supplement_weight", "composite_weight")}
    require((adults["supplement_weight"] > 0).all() and (adults["composite_weight"] >= 0).all(),
            "CPS survey person weight invalid")
    observed_classes = sum(np.isin(adults[field], [int(code) for code in config[group]]).sum()
                           for field, group in (("occupation", "occupations"), ("industry", "industries")))
    checks = {
        "source_sha256": {"basic": pins[source_ids["basic"]]["sha256"], "extract": pins[source_ids["covid"]]["sha256"]},
        "linked_responses": len(extract_keys), "eligible_workers": int(eligible.sum()),
        "unassigned_classifications": int(2 * eligible.sum() - observed_classes),
    }
    return adults, responses, checks


def estimate(source: np.ndarray, workers: dict, group: np.ndarray) -> dict:
    known = np.isin(source, [1, 2]) & group
    yes = (source == 1) & group
    count = int(known.sum())
    if count < 100 or yes.sum() < 10 or (known & ~yes).sum() < 10:
        return {"suppressed": True, "suppression_reason": "insufficient complete or binary outcome support",
                "percent": None, "complete_respondents": None, "adult_worker_denominator": None}
    w, c = workers["supplement_weight"], workers["composite_weight"]
    denominator, numerator = int(w[known].sum()), int(w[yes].sum())
    c_denom, c_num = int(c[known].sum()), int(c[yes].sum())
    eligible = int(w[group].sum())
    return {
        "suppressed": False, "suppression_reason": None, "percent": numerator / denominator * 100,
        "complete_respondents": count, "adult_worker_denominator": denominator / 10000,
        "weighted_affirmative_workers": numerator / 10000, "eligible_worker_population": eligible / 10000,
        "weighted_item_missing_fraction": 1 - denominator / eligible,
        "missing_lower_percent": numerator / eligible * 100,
        "missing_upper_percent": (numerator + eligible - denominator) / eligible * 100,
        "alternate_composite_weight_share_percent": c_num / c_denom * 100 if c_denom else None,
    }


def verify_occupation(artifact: dict, expected_source: str) -> dict:
    config_path, pin_path = ROOT / "configs/occupational-work-v6.json", ROOT / "configs/occupation-inputs.json"
    config, pins = read_json(config_path), read_json(pin_path)
    require(artifact["source"] == expected_source and artifact["definition_sha256"] == digest(config_path)
            and artifact["private_inputs_sha256"] == digest(pin_path), "CPS artifact source identity changed")
    require(artifact["population"] == config["population"] and artifact["limitations"] == config["limitations"]
            and artifact["recall_days"] == 28, "CPS employed population or recall changed")
    raw = ROOT / "data/private-survey/labor"
    for name, pin in pins.items():
        if name not in config["sources"]:
            file = raw / pin["path"]
            require(file.stat().st_size == pin["bytes"] and digest(file) == pin["sha256"], "CPS documented weights changed")
    require(set(artifact["periods"]) == set(config["months"]), "CPS study calendar changed")
    source_rows = {}
    suppressed = concordant = 0
    for month in config["months"]:
        series = artifact["periods"][month]
        workers, responses, scope = cohort_replay(raw, pins, config, month)
        for field, expected in scope.items():
            equal(series[field], expected, f"CPS linkage changed: {month}.{field}")
        require(series["month"] == month, "CPS wave label changed")
        group_codes = {
            ("national", "total"): ("US civilian workers", np.full(responses.shape[1], True)),
            **{(kind, code): (label, workers[kind] == int(code))
               for kind, group in (("occupation", "occupations"), ("industry", "industries"))
               for code, label in config[group].items()},
        }
        rows = {(row["group_kind"], row["group_code"], row["outcome"]): row for row in series["rows"]}
        require(len(rows) == len(series["rows"]) == 2 * len(group_codes), "CPS published cell count changed")
        for (kind, code), (label, group) in group_codes.items():
            for outcome, source in zip(("telework", "unable_to_work"), responses, strict=True):
                identity = kind, code, outcome
                expected = estimate(source, workers, group)
                suppressed += expected["suppressed"]
                source_rows[month, *identity] = expected["percent"]
                require(identity in rows, "CPS population cell missing")
                equal(rows[identity], {"group": label, "group_kind": kind, "group_code": code,
                      "outcome": outcome, "month": month, **expected}, "CPS worker weighting or disclosure changed")
        official = config["telework_comparators"][month]
        gap = source_rows[month, "national", "total", "telework"] - official["value"]
        agrees = abs(gap) <= .2
        equal(series["telework_comparator"], {**official, "difference_pp": gap, "agrees": agrees},
              "CPS benchmark comparison changed")
        concordant += agrees
    expected_size = len(source_rows) // 3
    comparisons = {(r["group_kind"], r["group_code"], r["outcome"]): r for r in artifact["comparisons"]}
    require(len(comparisons) == len(artifact["comparisons"]) == expected_size, "CPS contrast population changed")
    for identity, row in comparisons.items():
        populations = {"national": {"total": "US civilian workers"}, "occupation": config["occupations"],
                       "industry": config["industries"]}
        kind, code, outcome = identity
        a, b, c = (source_rows[month, *identity] for month in config["months"])
        gap = c - a if c is not None and a is not None else None
        equal(row, {"group_kind": kind, "group_code": code, "group": populations[kind][code], "outcome": outcome,
                    "september_2020_percent": a, "september_2021_percent": b, "september_2022_percent": c,
                    "change_pp": gap, "meets_descriptive_change_threshold": abs(gap) >= 5 if gap is not None else None},
              "CPS same-calendar month contrast changed")
    return {"cells": len(source_rows), "suppressed": suppressed, "comparisons": expected_size,
            "provider_agreements": concordant}
