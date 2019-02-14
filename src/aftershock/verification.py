"""Independent evidence replay. No training or result generation is allowed here."""
from __future__ import annotations

import csv
import hashlib
import gzip
import json
import math
import subprocess
from collections import defaultdict
from datetime import datetime, timedelta, date
from pathlib import Path
from zipfile import ZipFile

import numpy as np
from scipy.special import erf

from .io import ROOT, contained, digest, read_json


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def trusted_inputs(expected: str) -> dict:
    require(len(expected) == 40 and all(c in "0123456789abcdef" for c in expected), "Expected full source commit is required")
    subprocess.run(["git", "cat-file", "-e", expected + "^{commit}"], cwd=ROOT, check=True, capture_output=True)
    names = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", expected], cwd=ROOT, text=True).splitlines()
    selected = [p for p in names if p.startswith(("src/", "configs/", "client/src/", "tests/", "scripts/", ".github/")) or p in
                {"pyproject.toml", "uv.lock", "client/package-lock.json", "client/package.json", "client/index.html", "Makefile", "docs/EXPERIMENT_PLAN.md"}]
    result = {}
    for name in selected:
        content = subprocess.check_output(["git", "show", f"{expected}:{name}"], cwd=ROOT)
        result[name] = hashlib.sha256(content).hexdigest()
    return result


def verify_manifest(bundle: Path) -> dict:
    manifest = read_json(bundle / "MANIFEST.json")
    require(isinstance(manifest.get("files"), dict) and len(manifest["files"]) >= 15, "Incomplete artifact manifest")
    actual = {str(p.relative_to(bundle)) for p in bundle.rglob("*") if p.is_file() and p.name not in {"MANIFEST.json", "VERIFICATION.json"}}
    require(actual == set(manifest["files"]), "Unlisted or missing evidence artifact")
    for name, expected in manifest["files"].items():
        path = contained(bundle, name)
        require(not path.is_symlink() and path.is_file(), "Evidence path is not an owned regular file")
        require(path.stat().st_size <= 80_000_000, "Oversized evidence artifact")
        require(digest(path) == expected["sha256"] and path.stat().st_size == expected["bytes"], "Artifact checksum or size mismatch: " + name)
    return manifest


def verify_observations(bundle: Path, datasets: dict) -> dict:
    import pycountry
    expected_values = {}
    registry = read_json(bundle / datasets["sources"]["regions"]["bundle_path"])[1]
    country_ids = {r["id"] for r in registry if r["region"]["id"] != "NA"}
    for source_id, source in datasets["sources"].items():
        relative = source.get("bundle_path")
        if not relative:
            continue
        path = contained(bundle, relative)
        require(digest(path) == source["sha256"], "Frozen upstream bytes do not match trusted dataset")
        if source_id.startswith("wb_"):
            metric = source_id[3:]
            data = read_json(path)
            require(int(data[0]["pages"]) == 1 and len(data[1]) == int(data[0]["total"]), "Truncated raw annual source")
            for r in data[1]:
                if r["countryiso3code"] in country_ids:
                    year = str(r["date"])
                    expected_values[r["countryiso3code"], metric, year + "-01-01", year + "-12-31"] = r["value"]
        elif source_id == "who":
            with path.open(encoding="utf-8-sig", newline="") as raw_stream:
                for r in csv.DictReader(raw_stream):
                    region = pycountry.countries.get(alpha_2=r["Country_code"])
                    code = region.alpha_3 if region else ("XKX" if r["Country_code"] == "XK" else "WHO:" + r["Country_code"])
                    end = r["Date_reported"]
                    start = (date.fromisoformat(end) - timedelta(days=6)).isoformat()
                    for column, metric in (("New_cases", "covid_cases"), ("New_deaths", "covid_deaths")):
                        expected_values[code, metric, start, end] = float(r[column]) if r[column] else None
    identities = set()
    annual: dict[tuple, float] = {}
    counts: dict[str, int] = defaultdict(int)
    regions: dict[str, set] = defaultdict(set)
    negatives = 0
    with (bundle / "observations.csv").open(newline="") as stream:
        for row in csv.DictReader(stream):
            key = tuple(row[k] for k in ("region", "metric", "event_start", "event_end", "group", "vintage"))
            require(key not in identities, "Duplicate measurement population in evidence")
            identities.add(key)
            source = datasets["sources"][row["source"]]
            require(row["source_hash"] == source["sha256"], "Observation upstream identity mismatch")
            require(row["available_at"] == source["available_at"] and row["vintage"] == source["acquired_at"], "Forged vintage or availability timestamp")
            require(datetime.fromisoformat(row["available_at"]).tzinfo is not None, "Naive availability timestamp")
            require(row["event_start"] <= row["event_end"], "Reversed event interval")
            raw_key = row["region"], row["metric"], row["event_start"], row["event_end"]
            require(raw_key in expected_values, "Observation is absent from frozen upstream bytes")
            expected_value = expected_values.pop(raw_key)
            actual_value = float(row["value"]) if row["value"] else None
            require(expected_value == actual_value, "Observation value differs from independent raw-source parser")
            counts[row["metric"]] += 1
            if row["value"]:
                value = float(row["value"])
                require(math.isfinite(value), "Nonfinite observed value")
                regions[row["metric"]].add(row["region"])
                negatives += value < 0
                if row["frequency"] == "annual":
                    require(row["group"] == "total", "Unexpected annual subgroup")
                    annual[row["region"], row["metric"], int(row["event_start"][:4])] = value
                expected_kind = "modeled_estimate" if row["metric"] in {"population", "employment", "mortality", "life_expectancy", "immunization"} else "observed"
                require(row["kind"] == expected_kind, "Reclassified observation or modeled estimate")
    require(len(identities) >= 1000 and len(regions["covid_deaths"]) >= 120, "Empty or reduced surveillance workload")
    require(not expected_values, "Raw measurements omitted from evidence population")
    return {"annual": annual, "records": len(identities), "metric_counts": dict(counts), "negative_values": negatives,
            "surveillance_regions": len(regions["covid_deaths"])}


def verify_forecasts(bundle: Path, annual: dict) -> dict:
    predictions = read_json(bundle / "predictions.json", 64_000_000)
    scores = read_json(bundle / "fit.json")
    require(len(predictions) > 1000, "Empty forecast workload")
    groups = defaultdict(list)
    identities = set()
    for row in predictions:
        key = row["model"], row["region"], row["target_year"], row["metric"]
        require(key not in identities, "Duplicate forecast population")
        identities.add(key)
        expected_holdout = int(hashlib.sha256(row["region"].encode()).hexdigest(), 16) % 5 == 0
        require(row["held_out_region"] == expected_holdout, "Country holdout assignment was reclassified")
        require(2019 <= row["target_year"] <= 2024, "Future label or shifted test era")
        require(row["feature_last_year"] == row["target_year"] - 1, "Future feature label or feature chronology violation")
        truth = annual.get((row["region"], row["metric"], row["target_year"]))
        require(truth is not None and math.isclose(truth, row["truth"], rel_tol=1e-10, abs_tol=1e-9), "Forecast truth detached from raw panel")
        transformed_truth = math.log1p(truth) if row["metric"] == "gdp" else truth
        require(math.isclose(transformed_truth, row["truth_t"], rel_tol=1e-10, abs_tol=1e-9), "Scored truth uses incorrect target transformation")
        require(row["availability_mode"] == "retrospective_final_vintage", "Forged historical information set")
        for name in ("truth_t", "mean_t", "sd_t", "lower_t", "upper_t"):
            require(math.isfinite(row[name]), "Nonfinite forecast quantity")
        require(row["sd_t"] > 0 and row["lower_t"] <= row["mean_t"] <= row["upper_t"], "Invalid predictive interval")
        for label in ("all", "held_out_country" if row["held_out_region"] else "retained_country",
                      "country:" + row["region"], "year:" + str(row["target_year"])):
            groups[row["model"], row["metric"], label].append(row)
    require(len({(r["model"], r["metric"]) for r in predictions}) >= 30, "Fewer than required nonempty model configurations")
    for record in scores["scores"]:
        rows = groups[record["model"], record["metric"], record["group"]]
        require(len(rows) == record["n"], "Forecast scoring denominator mismatch: " + str((record["model"], record["metric"], record["group"])))
        actual, mu, sd, lower, upper = (np.array([r[k] for r in rows]) for k in ("truth_t", "mean_t", "sd_t", "lower_t", "upper_t"))
        z = (actual - mu) / sd
        phi = np.exp(-.5 * z * z) / math.sqrt(2 * math.pi)
        cdf = .5 * (1 + erf(z / math.sqrt(2)))
        recomputed = {"mae": float(np.abs(actual - mu).mean()), "rmse": float(np.mean((actual - mu) ** 2) ** .5),
                      "gaussian_nll": float(np.mean(np.log(sd) + .5 * math.log(2 * math.pi) + z * z / 2)),
                      "crps": float(np.mean(sd * (z * (2 * cdf - 1) + 2 * phi - 1 / math.sqrt(math.pi)))),
                      "coverage_90": float(np.mean((actual >= lower) & (actual <= upper))),
                      "width_90": float(np.mean(upper - lower)),
                      "interval_score_90": float(np.mean(upper - lower + 20 * np.maximum(lower - actual, 0) + 20 * np.maximum(actual - upper, 0)))}
        for key, value in recomputed.items():
            require(math.isclose(value, record[key], rel_tol=1e-9, abs_tol=1e-9), "Independent proper score mismatch: " + key)
    joint_countries = []
    for region in {k[0] for k in annual}:
        supported = True
        for metric in ("employment", "gdp", "mortality"):
            supported &= sum((region, metric, year) in annual for year in range(2010, 2020)) >= 8
            supported &= all((region, metric, year) in annual for year in (2020, 2021))
            supported &= any((region, metric, year) in annual for year in (2023, 2024))
        if supported:
            joint_countries.append(region)
    require(len(joint_countries) >= 15, "Insufficient real joint pre/during/post panel")
    return {"prediction_records": len(predictions), "configurations": len({(r["model"], r["metric"]) for r in predictions}),
            "score_groups": len(groups), "joint_multiyear_economies": len(joint_countries)}


def verify_model_replay(bundle: Path, annual: dict) -> dict:
    preprocessing = read_json(bundle / "models/preprocessing.json")
    keys = read_json(bundle / "models/replay-keys.json")
    probes = read_json(bundle / "PROBES.json")["model_indices"]
    predictions = read_json(bundle / "predictions.json", 64_000_000)
    lookup = {(r["model"], r["region"], r["target_year"], r["metric"]): r for r in predictions}
    outcomes = preprocessing["outcomes"]
    require(outcomes == ["employment", "gdp", "school", "immunization", "mortality", "life_expectancy"], "Outcome order differs from frozen contract")
    eligible = [(region, year) for region in sorted({k[0] for k in annual}) for year in range(2004, 2025)
                if any((region, metric, year) in annual and (region, metric, year - 1) in annual for metric in outcomes)]
    require([(k["region"], k["target_year"]) for k in keys] == eligible, "Feature population omitted eligible country-years")
    for key in keys:
        expected_holdout = int(hashlib.sha256(key["region"].encode()).hexdigest(), 16) % 5 == 0
        require(key["held_out_region"] == expected_holdout and key["feature_last_year"] == key["target_year"] - 1, "Feature split or chronology reclassified")
    raw = np.array([[annual.get((key["region"], metric, year), np.nan)
                     for year in range(key["target_year"] - 4, key["target_year"]) for metric in outcomes] for key in keys])
    for j in range(1, raw.shape[1], len(outcomes)):
        raw[:, j] = np.log1p(raw[:, j])
    fit_rows = np.array([k["target_year"] <= 2015 and not k["held_out_region"] for k in keys])
    center_x, scale_x = np.nanmean(raw[fit_rows], axis=0), np.maximum(np.nanstd(raw[fit_rows], axis=0), 1e-4)
    require(np.allclose(center_x, preprocessing["xmean"]) and np.allclose(scale_x, preprocessing["xscale"]), "Preprocessing fitted on wrong population")
    expected_x = np.concatenate([np.nan_to_num((raw - center_x) / scale_x), np.isfinite(raw).astype(float)], axis=1)
    next_levels = np.array([[annual.get((key["region"], metric, key["target_year"]), np.nan) for metric in outcomes] for key in keys])
    next_levels[:, 1] = np.log1p(next_levels[:, 1])
    expected_base = raw.reshape(len(raw), 4, len(outcomes))[:, -1, :]
    expected_target = next_levels - expected_base
    expected_center_y = np.nanmean(expected_target[fit_rows], axis=0)
    expected_scale_y = np.maximum(np.nanstd(expected_target[fit_rows], axis=0), 1e-4)
    for row in preprocessing["train"] + preprocessing["validation"]:
        require(not row["held_out_region"], "Held-out country leaked into fitting or calibration")
    require(all(r["target_year"] <= 2015 for r in preprocessing["train"]), "Future training label")
    require(all(2016 <= r["target_year"] <= 2018 for r in preprocessing["validation"]), "Validation time shift")
    with np.load(bundle / "models/replay-inputs.npz", allow_pickle=False) as arrays:
        x, base, mask, scale, center = [arrays[name] for name in ("x", "base", "mask", "yscale", "ymean")]
        require(np.allclose(x, expected_x, rtol=1e-12, atol=1e-12), "Feature values use future or incorrect raw observations")
        require(np.allclose(base, expected_base, equal_nan=True), "Forecast base detached from preceding source value")
        require(np.array_equal(mask, np.isfinite(expected_target)), "Outcome missingness mask was changed")
        require(np.allclose(center, expected_center_y) and np.allclose(scale, expected_scale_y), "Target preprocessing fitted on wrong population")
        require(len(keys) == len(x) and len(probes) >= 8, "Frozen replay probes missing")
        replayed = 0
        for seed in (11, 29, 47):
            path = bundle / f"models/seed-{seed}/best.npz"
            with ZipFile(path) as z:
                require(sum(f.file_size for f in z.infolist()) < 20_000_000, "Checkpoint expansion exceeds budget")
            with np.load(path, allow_pickle=False) as checkpoint, np.load(bundle / f"models/seed-{seed}/initial.npz", allow_pickle=False) as initial:
                movement = sum(float(np.sum((checkpoint["p_" + k] - initial["p_" + k]) ** 2)) for k in ("w1", "b1", "w2", "b2"))
                require(movement > 1e-12, "Parameters never changed from initialization")
                state = json.loads(checkpoint["state"].tobytes())
                require(state["steps"] > 0 and state["epoch"] > 0, "Optimizer never executed")
                h = np.tanh(x[probes] @ checkpoint["p_w1"] + checkpoint["p_b1"])
                out = h @ checkpoint["p_w2"] + checkpoint["p_b2"]
                means = out[:, :len(outcomes)] * scale + center + base[probes]
                spreads = np.exp(.5 * np.clip(out[:, len(outcomes):], -6, 3)) * scale
                for p, i in enumerate(probes):
                    key = keys[i]
                    require(2019 <= key["target_year"] <= 2024, "Replay probe outside test set")
                    for j, metric in enumerate(outcomes):
                        if not mask[i, j]:
                            continue
                        row = lookup[f"network_{seed}", key["region"], key["target_year"], metric]
                        require(np.isclose(row["mean_t"], means[p, j], rtol=1e-10, atol=1e-10), "Saved model mean replay failed")
                        require(np.isclose(row["sd_t"], spreads[p, j], rtol=1e-10, atol=1e-10), "Saved model variance replay failed")
                        replayed += 1
    return {"replayed_predictions": replayed, "seeds": [11, 29, 47]}


def verify_domain_semantics(bundle: Path) -> dict:
    import io
    import openpyxl
    age = read_json(bundle / "age-replay.json")
    studies = read_json(bundle / "studies.json")
    datasets = read_json(bundle / "DATASETS.json")["sources"]
    with ZipFile(bundle / datasets["excess_2022"]["bundle_path"]) as archive:
        name = next(n for n in archive.namelist() if n.endswith("EstimatesByCountry.xlsx"))
        workbook = openpyxl.load_workbook(io.BytesIO(archive.read(name)), read_only=True, data_only=True)
        actual_age = defaultdict(lambda: {"population": 0, "count": 0})
        for row in workbook["Country by year, sex and age"].iter_rows(values_only=True):
            if row[1] in {"USA", "GBR"} and row[2] in {2020, 2021}:
                group = actual_age[row[1], row[2], row[4]]
                group["population"] += row[5]
                group["count"] += row[8]
        workbook.close()
    for row in age["raw"]:
        source_row = actual_age[row["region"], row["year"], row["age"]]
        require(row["population"] == source_row["population"] and row["count"] == source_row["count"], "Age count or denominator detached from WHO release")
        pooled_band = sum(r["population"] for k, r in actual_age.items() if k[1] == 2020 and k[2] == row["age"])
        pooled_total = sum(r["population"] for k, r in actual_age.items() if k[1] == 2020)
        require(math.isclose(row["standard_weight"], pooled_band / pooled_total, rel_tol=1e-12), "Forged age standard population weight")
    s3 = next(s for s in studies["studies"] if s["id"] == "S03")
    for summary in s3["table"]:
        rows = [r for r in age["raw"] if r["region"] == summary["region"] and r["year"] == summary["year"]]
        require(len(rows) == 7 and abs(sum(r["standard_weight"] for r in rows) - 1) < 1e-12, "Invalid age standard population")
        rate = sum(r["count"] / r["population"] * r["standard_weight"] for r in rows) * 100000
        require(math.isclose(rate, summary["standardized_per_100k"], rel_tol=1e-12), "Independent age standardized rate mismatch")
    genes = read_json(bundle / "genetics.json")
    host_raw = {}
    for source_id in ("hgi_a2", "hgi_b2"):
        with gzip.open(bundle / datasets[source_id]["bundle_path"], "rt") as stream:
            host_raw[source_id] = {(r["#CHR"], int(r["POS"]), r["REF"], r["ALT"]): r for r in csv.DictReader(stream, delimiter="\t")}
    for row in genes["representatives"]:
        require(row["build"] == "GRCh38" and row["reference"] != row["effect_allele"], "Invalid genetic reference or effect allele")
        require(math.isclose(math.exp(row["a2_beta"]), row["a2_odds_ratio"], rel_tol=1e-12), "Invalid genetic effect sign or odds ratio")
        require(row["same_direction"] == (row["a2_beta"] * row["b2_beta_aligned"] > 0), "Genetic direction classification mismatch")
        raw_key = row["chromosome"], row["position"], row["reference"], row["effect_allele"]
        require(raw_key in host_raw["hgi_a2"] and raw_key in host_raw["hgi_b2"], "Genetic variant detached from released summary statistics")
        require(float(host_raw["hgi_a2"][raw_key]["all_inv_var_meta_beta"]) == row["a2_beta"], "Genetic effect sign detached from released effect allele")
        require(float(host_raw["hgi_b2"][raw_key]["all_inv_var_meta_beta"]) == row["b2_beta_aligned"], "Aligned effect detached from released summary statistic")
    require(genes["independent_replication"] is False, "Shared-sample genetics reclassified as independent replication")
    causal = read_json(bundle / "causal.json")
    require(causal["identification"] == "not_established", "Unsupported causal identification claim")
    for placebo in causal["pseudo_onsets"]:
        require(placebo["baseline_year"] == placebo["cohort"] - 1, "Shifted placebo baseline")
        require(placebo["cohort"] + 2 in {int(y[:4]) for y in causal["adoption_dates"].values()}, "Placebo onset detached from actual adoption")
    for cell in causal["cells"]:
        if cell["treated_n"] < 5 or cell["control_n"] < 5:
            require(cell["effect"] is None and cell["status"] == "unsupported", "Unsupported causal cell given an effect")
    surveys = read_json(bundle / "surveys.json")
    hidden = 0
    for row in surveys["rows"]:
        require(not any(k in row for k in {"person_id", "respondent", "raw_weight", "sample_n"}), "Protected survey field in public output")
        if row.get("suppressed"):
            require(all(row.get(k) is None for k in ("value", "lower", "upper", "denominator", "se")), "Suppression leaked through a public statistic")
            hidden += 1
    require(len(studies["studies"]) == 12 and all(s["table"] for s in studies["studies"]), "Missing substantive study tables")
    return {"age_contrasts": len(s3["table"]), "genetic_probes": len(genes["representatives"]), "suppressed_survey_cells": hidden}


def verify_bundle(path: str | Path, expected_source: str) -> dict:
    bundle = Path(path).resolve()
    verify_manifest(bundle)
    source = read_json(bundle / "SOURCE_INPUTS.json")
    require(source["commit"] == expected_source, "Source commit mismatch")
    trusted = trusted_inputs(expected_source)
    require(source["files"] == trusted, "Source file identities differ from trusted Git commit")
    # Running code must match the trusted version too, even when this checkout has later reports.
    for name, checksum in trusted.items():
        require((ROOT / name).is_file() and digest(ROOT / name) == checksum, "Verifier runtime source mismatch: " + name)
    datasets = read_json(bundle / "DATASETS.json")
    for source_id, data in datasets["sources"].items():
        trusted_data = read_json(ROOT / "configs/data-inputs.json")[source_id]
        require({k: v for k, v in data.items() if k != "bundle_path"} == trusted_data, "Dataset metadata differs from trusted acquisition manifest")
    observations = verify_observations(bundle, datasets)
    annual = observations.pop("annual")
    forecasts = verify_forecasts(bundle, annual)
    replay = verify_model_replay(bundle, annual)
    domain = verify_domain_semantics(bundle)
    commands = [json.loads(line) for line in (bundle / "COMMANDS.jsonl").read_text().splitlines()]
    require(len(commands) >= 5 and all(r["exit"] == 0 for r in commands), "Required command missing or failed")
    acceptance = read_json(bundle / "ACCEPTANCE.json")
    require(acceptance["profile"] in {"diagnostic", "full"}, "Unknown campaign profile")
    if acceptance["profile"] == "full":
        require(all(g["status"] == "passed" for g in acceptance["gates"]), "Full profile has incomplete domain gates")
    return {"status": "passed", "profile": acceptance["profile"], "source": expected_source,
            "observations": observations, "forecasts": forecasts, "replay": replay, "domain": domain,
            "full_acceptance": acceptance["profile"] == "full"}
