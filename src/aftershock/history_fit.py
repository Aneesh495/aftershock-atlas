"""Matched archive information sets with fresh temporal networks and frozen baselines."""
from __future__ import annotations

import numpy as np
from scipy.optimize import minimize

from .dynamic import filter_windows
from .features import OUTCOMES, SEEDS, inverse
from .forecast import compare_learned, summarize_predictions
from .history import UNITS
from .history_features import history_features
from .io import ROOT, atomic_path, digest, read_json, source_commit, write_json
from .network import TemporalNetwork, train
from .resources import usage
from .statistics import conformal_multiplier, local_level, proper_scores, ridge


def historical_baselines(f):
    shape = f.target.shape
    names = ("persistence", "trend", "pooled_ridge", "local_level", "hierarchical_damped_2y")
    output = {name: (np.zeros(shape), np.ones(shape)) for name in names}
    parameters = []
    for j, metric in enumerate(OUTCOMES):
        selected = f.train & f.mask[:, j]
        if selected.sum() < 100:
            raise ValueError("Insufficient historical training support: " + metric)
        noise = max(float(np.std(f.target[selected, j])), 1e-3)
        allx = np.column_stack([np.ones(len(f.x)), f.x])
        beta = ridge(allx[selected], f.target[selected, j], 1, f.weights[selected])
        residual_sd = max(float(np.std(f.target[selected, j] - allx[selected] @ beta)), 1e-3)
        output["pooled_ridge"][0][:, j] = allx @ beta
        output["pooled_ridge"][1][:, j] = residual_sd
        output["persistence"][1][:, j] = noise
        windows = f.raw.reshape(-1, 4, len(OUTCOMES))[:, :, j]
        for i, window in enumerate(windows):
            valid = np.isfinite(window)
            if not valid[-1]:
                continue
            if valid.sum() >= 3:
                t = np.arange(4)[valid]
                coefficients = ridge(np.column_stack([np.ones(valid.sum()), t]), window[valid])
                output["trend"][0][i, j] = np.array([1, 5]) @ coefficients - window[-1]
            output["trend"][1][i, j] = noise
            level, variance, _ = local_level(window, q=noise ** 2 * .1, r=noise ** 2)
            output["local_level"][0][i, j] = level - window[-1]
            output["local_level"][1][i, j] = (variance + noise ** 2 * .1) ** .5
        scale = float(f.yscale[j])
        training_windows = windows[selected] / scale
        levels = (f.target[selected, j] + f.base[selected, j]) / scale
        def objective(p):
            mu, variance = filter_windows(training_windows, p, horizon=2)
            return float(np.average(.5 * (np.log(2 * np.pi * variance) + (levels - mu) ** 2 / variance), weights=f.weights[selected]))
        starts = []
        slope = float(np.average(f.target[selected, j], weights=f.weights[selected]) / scale / 2)
        for phi in (.2, .7, 1.):
            result = minimize(objective, [slope, 0., -2., -3., 0., phi], method="L-BFGS-B",
                bounds=[(-10, 10)] + [(-8, 6)] * 4 + [(0, 1)], options={"maxiter": 150, "ftol": 1e-10})
            if not np.isfinite(result.fun) or not np.isfinite(result.x).all():
                raise ValueError("Nonfinite historical dynamic fit")
            starts.append({"initial_phi": phi, "converged": bool(result.success), "iterations": int(result.nit),
                           "message": str(result.message), "training_nll": float(result.fun), "parameters": result.x.tolist()})
        chosen = min(starts, key=lambda r: r["training_nll"])
        mu, variance = filter_windows(windows / scale, np.array(chosen["parameters"]), horizon=2)
        output["hierarchical_damped_2y"][0][:, j] = np.nan_to_num(mu * scale - f.base[:, j])
        output["hierarchical_damped_2y"][1][:, j] = np.nan_to_num(np.sqrt(variance) * scale, nan=scale)
        parameters.append({"metric": metric, "training_rows": int(selected.sum()), "noise": noise,
                           "ridge_beta": beta.tolist(), "ridge_residual_sd": residual_sd, "scale": scale,
                           "dynamic": {"horizon": 2, "chosen": chosen, "starts": starts}})
        print(f"historical baselines {metric}: {int(selected.sum())} training outcomes", flush=True)
    return output, parameters


def archive_predictions(f, model, mean, sd, training_kind):
    calibration = []
    for j in range(len(OUTCOMES)):
        selected = f.validation & f.mask[:, j]
        calibration.append(conformal_multiplier(f.target[selected, j], mean[selected, j], sd[selected, j]))
    records = []
    for i in np.where(f.test)[0]:
        for j, metric in enumerate(OUTCOMES):
            if not f.mask[i, j]:
                continue
            truth = float(f.target[i, j] + f.base[i, j])
            mu, spread = float(mean[i, j] + f.base[i, j]), float(sd[i, j])
            radius = calibration[j] * spread
            records.append({**f.keys[i], "model": model, "metric": metric,
                "truth_t": truth, "mean_t": mu, "sd_t": spread, "lower_t": mu - radius, "upper_t": mu + radius,
                "truth": float(inverse(truth, metric)), "mean": float(inverse(mu, metric)), "lower": float(inverse(mu - radius, metric)), "upper": float(inverse(mu + radius, metric)),
                "feature_endpoint_t": float(f.base[i, j]), "calibration_multiplier": calibration[j],
                "score_unit": "log1p 2010=100 within-edition index" if metric == "gdp" else UNITS[metric],
                "availability_mode": "provider_designated_archive", "training_kind": training_kind,
                "truth_kind": "final_vintage_provider_estimate", "interpretation": "exploratory reused calendar outcomes"})
    return records


def fit_history() -> dict:
    usage(250_000_000)
    f = history_features()
    directory = ROOT / "data/models/historical-v3"
    pins = read_json(ROOT / "configs/history-inputs.json")
    identity = {"schema": "archive-two-year-index-v3", "protocol": digest(ROOT / "docs/HISTORICAL_PLAN_V3.md"),
                "archive_panel": digest(ROOT / "data/history/observations.parquet"),
                "target_panel": digest(ROOT / "data/panel/observations.parquet"),
                "model_code": {name: digest(ROOT / "src/aftershock" / name) for name in
                    ("history.py", "history_features.py", "history_fit.py", "network.py", "dynamic.py", "statistics.py", "features.py", "panel.py", "io.py")}}
    baselines, baseline_parameters = historical_baselines(f)
    output, validation_scores, training = [], [], []
    for name, (mean, sd) in baselines.items():
        output.extend(archive_predictions(f, name, mean, sd, "classical_estimation"))
        for j, metric in enumerate(OUTCOMES):
            selected = f.validation & f.mask[:, j]
            validation_scores.append({"model": name, "metric": metric,
                **proper_scores(f.target[selected, j], mean[selected, j], sd[selected, j])})
    selected_baselines = {metric: min((r for r in validation_scores if r["metric"] == metric), key=lambda r: r["crps"])["model"]
                          for metric in OUTCOMES}
    for seed in SEEDS:
        model = TemporalNetwork(f.x.shape[1], len(OUTCOMES), seed)
        mu, sd = model.forward(f.x)
        output.extend(archive_predictions(f, f"untrained_{seed}", mu * f.yscale + f.ymean, sd * f.yscale, "untrained_control"))
        run = directory / f"seed-{seed}"
        fitted = train(model, f.x[f.train], f.y[f.train], f.mask[f.train], f.weights[f.train],
                       (f.x[f.validation], f.y[f.validation], f.mask[f.validation]), run, identity)
        restored, _ = TemporalNetwork.load(run / "best.npz")
        mu, sd = restored.forward(f.x)
        output.extend(archive_predictions(f, f"network_{seed}", mu * f.yscale + f.ymean, sd * f.yscale, "gradient_network"))
        training.append(fitted)
        print(f"historical seed {seed}: {fitted['completed_epochs']} epochs, movement {fitted['parameter_l2_change']:.4f}", flush=True)
    scores = summarize_predictions(output)
    files = {}
    for metric in OUTCOMES:
        path = ROOT / f"data/results/history-predictions/{metric}.json"
        write_json(path, [r for r in output if r["metric"] == metric])
        files[metric] = {"path": str(path.relative_to(ROOT / "data/results")), "sha256": digest(path), "bytes": path.stat().st_size}
    result = {"protocol": "historical-v3-exploratory", "source": source_commit(), "identity": identity,
        "initial_edition": "201811", "training_target_years": [2005, 2014], "validation_target_years": [2015, 2017],
        "test_target_years": [2019, 2024], "train_rows": int(f.train.sum()), "validation_rows": int(f.validation.sum()),
        "test_rows": int(f.test.sum()), "prediction_rows": len(output), "prediction_files": files,
        "completed_configurations": len([r for r in scores if r["group"] == "all"]), "training_seeds": list(SEEDS),
        "training": training, "baseline_parameters": baseline_parameters, "baseline_validation_scores": validation_scores,
        "selected_baselines": selected_baselines, "scores": scores, "learned_comparisons": compare_learned(scores, selected_baselines),
        "feature_sources": {key: value["sha256"] for key, value in pins.items()},
        "availability": "Official edition-month bounds; no original cell release-day proof",
        "limitations": ["Calendar test outcomes were inspected in earlier protocols", "Current-code matching does not prove historical borders",
            "GDP indices remove constant scaling but not definition changes", "Final target revisions enter test truth, never archived features",
            "Pre-pandemic calibration may fail under pandemic drift"]}
    write_json(ROOT / "data/results/history-fit.json", result)
    write_json(directory / "baseline-parameters.json", baseline_parameters)
    write_json(directory / "replay-keys.json", f.keys)
    with atomic_path(directory / "replay-inputs.npz") as temporary:
        with temporary.open("wb") as stream:
            np.savez_compressed(stream, x=f.x, raw=f.raw, target=f.target, base=f.base, mask=f.mask,
                                train=f.train, validation=f.validation, test=f.test, yscale=f.yscale, ymean=f.ymean)
    return {k: v for k, v in result.items() if k not in {"scores", "training", "baseline_parameters", "baseline_validation_scores", "feature_sources", "prediction_files"}}

