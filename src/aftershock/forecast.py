"""Matched-information baselines, learned seed controls, and predictive scenarios."""
from __future__ import annotations


import numpy as np

from .features import OUTCOMES, SEEDS, annual_cube, inverse, make_features
from .io import ROOT, digest, now, source_commit, write_json
from .network import TemporalNetwork, train
from .resources import usage
from .statistics import conformal_multiplier, local_level, proper_scores, ridge


def baseline_predictions(features) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    f = features
    shape = f.target.shape
    output = {name: (np.zeros(shape), np.ones(shape)) for name in ("persistence", "trend", "pooled_ridge", "local_level")}
    for j, outcome in enumerate(OUTCOMES):
        fit = f.train & f.mask[:, j]
        if fit.sum() < 100:
            raise ValueError(f"No training support for {outcome}")
        noise = max(float(np.nanstd(f.target[fit, j])), 1e-3)
        output["persistence"][1][:, j] = noise
        xfit = np.column_stack([np.ones(fit.sum()), f.x[fit]])
        beta = ridge(xfit, f.target[fit, j], 1, f.weights[fit])
        allx = np.column_stack([np.ones(len(f.x)), f.x])
        output["pooled_ridge"][0][:, j] = allx @ beta
        residual = f.target[fit, j] - xfit @ beta
        output["pooled_ridge"][1][:, j] = max(float(np.std(residual)), 1e-3)
        for i, row in enumerate(f.raw):
            window = row.reshape(4, len(OUTCOMES))[:, j]
            valid = np.isfinite(window)
            if not valid[-1]:
                continue
            if valid.sum() >= 3:
                t = np.arange(4)[valid]
                a = np.column_stack([np.ones(len(t)), t])
                b = ridge(a, window[valid])
                output["trend"][0][i, j] = np.array([1, 4]) @ b - window[-1]
            output["trend"][1][i, j] = noise
            level, variance, _ = local_level(window, q=noise ** 2 * .1, r=noise ** 2)
            output["local_level"][0][i, j] = level - window[-1]
            output["local_level"][1][i, j] = variance ** .5
    return output


def prediction_records(f, name: str, mean: np.ndarray, sd: np.ndarray, training: dict | None = None) -> list[dict]:
    results = []
    multipliers = []
    for j in range(len(OUTCOMES)):
        v = f.validation & f.mask[:, j]
        multipliers.append(conformal_multiplier(f.target[v, j], mean[v, j], sd[v, j]))
    for i in np.where(f.test)[0]:
        for j, metric in enumerate(OUTCOMES):
            if not f.mask[i, j]:
                continue
            truth_t = float(f.target[i, j] + f.base[i, j])
            mean_t = float(mean[i, j] + f.base[i, j])
            spread = float(sd[i, j])
            radius = multipliers[j] * spread
            results.append({**f.keys[i], "model": name, "metric": metric,
                            "truth_t": truth_t, "mean_t": mean_t, "sd_t": spread,
                            "lower_t": mean_t - radius, "upper_t": mean_t + radius,
                            "truth": float(inverse(truth_t, metric)), "mean": float(inverse(mean_t, metric)),
                            "lower": float(inverse(mean_t - radius, metric)), "upper": float(inverse(mean_t + radius, metric)),
                            "calibration_multiplier": multipliers[j], "score_unit": "log1p USD" if metric == "gdp" else "native unit",
                            "availability_mode": "retrospective_final_vintage", "trained": training is not None})
    return results


def summarize_predictions(rows: list[dict]) -> list[dict]:
    groups: dict[tuple, list[dict]] = {}
    for r in rows:
        for group in ("all", "held_out_country" if r["held_out_region"] else "retained_country",
                      "country:" + r["region"], "year:" + str(r["target_year"])):
            groups.setdefault((r["model"], r["metric"], group), []).append(r)
    results = []
    for (model, metric, group), records in sorted(groups.items()):
        def values(key):
            return [r[key] for r in records]
        score = proper_scores(values("truth_t"), values("mean_t"), values("sd_t"), values("lower_t"), values("upper_t"))
        results.append({"model": model, "metric": metric, "group": group, **score,
                        "countries": len({r["region"] for r in records}), "first_test_year": min(r["target_year"] for r in records),
                        "last_test_year": max(r["target_year"] for r in records), "score_unit": records[0]["score_unit"]})
    return results


def compare_learned(scores: list[dict], chosen: dict[str, str]) -> list[dict]:
    output = []
    rng = np.random.default_rng(11)
    for metric in OUTCOMES:
        rows = [r for r in scores if r["metric"] == metric and r["group"].startswith("country:")]
        lookup = {(r["group"], r["model"]): r for r in rows}
        countries = sorted({r["group"] for r in rows})
        base, learned, count = [], [], []
        for country in countries:
            b = lookup[country, chosen[metric]]
            networks = [lookup[country, f"network_{seed}"] for seed in SEEDS]
            base.append(b["crps"])
            learned.append(float(np.mean([r["crps"] for r in networks])))
            count.append(b["n"])
        base, learned, count = np.array(base), np.array(learned), np.array(count)
        difference = float(np.sum((base - learned) * count) / np.sum(base * count))
        resamples = rng.integers(0, len(countries), (999, len(countries)))
        sampled = np.sum((base[resamples] - learned[resamples]) * count[resamples], axis=1) / np.sum(base[resamples] * count[resamples], axis=1)
        lower, upper = np.quantile(sampled, [.025, .975])
        output.append({"metric": metric, "validation_selected_baseline": chosen[metric], "countries": len(countries),
                       "relative_crps_improvement": difference, "cluster_lower": float(lower), "cluster_upper": float(upper),
                       "bootstrap_replicates": 999, "practical_5pct_and_positive_interval": bool(difference >= .05 and lower > 0),
                       "comparison": "mean of three seed scores; country-cluster resampling; fixed validation baseline"})
    return output


def fit_models() -> dict:
    usage(200_000_000)
    directory = ROOT / "data/models"
    directory.mkdir(parents=True, exist_ok=True)
    f = make_features()
    identity = {"panel": digest(ROOT / "data/panel/observations.parquet"),
                "protocol": digest(ROOT / "docs/EXPERIMENT_PLAN.md"), "schema": "temporal-delta-v1"}
    output, training, validation_scores = [], [], []
    for name, (mean, sd) in baseline_predictions(f).items():
        output.extend(prediction_records(f, name, mean, sd))
        for j, metric in enumerate(OUTCOMES):
            selected = f.validation & f.mask[:, j]
            validation_scores.append({"model": name, "metric": metric,
                                      **proper_scores(f.target[selected, j], mean[selected, j], sd[selected, j])})
    for seed in SEEDS:
        model = TemporalNetwork(f.x.shape[1], len(OUTCOMES), seed)
        initial_mean, initial_sd = model.forward(f.x)
        output.extend(prediction_records(f, f"untrained_{seed}", initial_mean * f.yscale + f.ymean, initial_sd * f.yscale))
        run = directory / f"seed-{seed}"
        trained = train(model, f.x[f.train], f.y[f.train], f.mask[f.train], f.weights[f.train],
                        (f.x[f.validation], f.y[f.validation], f.mask[f.validation]), run, identity)
        training.append(trained)
        restored, _ = TemporalNetwork.load(run / "best.npz")
        mean, sd = restored.forward(f.x)
        output.extend(prediction_records(f, f"network_{seed}", mean * f.yscale + f.ymean, sd * f.yscale, trained))
        print(f"seed {seed}: {trained['completed_epochs']} epochs, parameter movement {trained['parameter_l2_change']:.4f}", flush=True)
    scores = summarize_predictions(output)
    selected_baselines = {metric: min((r for r in validation_scores if r["metric"] == metric), key=lambda r: r["crps"])["model"] for metric in OUTCOMES}
    source = source_commit()
    result = {"created_at": now(), "source": source, "identity": identity,
              "prediction_rows": len(output), "completed_configurations": len([r for r in scores if r["group"] == "all"]),
              "training_seeds": list(SEEDS), "train_rows": int(f.train.sum()), "validation_rows": int(f.validation.sum()),
              "test_rows": int(f.test.sum()), "training": training, "scores": scores,
              "baseline_validation_scores": validation_scores,
              "selected_baselines": selected_baselines, "learned_comparisons": compare_learned(scores, selected_baselines),
              "availability": "final-vintage retrospective; historical available-at-time forecasting unverified"}
    write_json(ROOT / "data/results/predictions.json", output)
    write_json(ROOT / "data/results/fit.json", result)
    write_json(directory / "identity.json", identity)
    with (directory / "replay-inputs.npz").open("wb") as stream:
        np.savez_compressed(stream, x=f.x, target=f.target, base=f.base, mask=f.mask, test=f.test,
                            yscale=f.yscale, ymean=f.ymean)
    write_json(directory / "replay-keys.json", f.keys)
    return {k: v for k, v in result.items() if k not in {"training", "scores", "baseline_validation_scores"}}


def no_shock_forecasts() -> dict:
    regions, cube = annual_cube()
    output = []
    for i, region in enumerate(regions):
        for j, metric in enumerate(OUTCOMES):
            window = cube[i, 10:20, j]
            valid = np.isfinite(window)
            if valid.sum() < 8 or not valid[-1]:
                continue
            t = np.arange(10)[valid]
            x = np.column_stack([np.ones(len(t)), t])
            beta = ridge(x, window[valid])
            residual = window[valid] - x @ beta
            sigma = max(float(np.std(residual, ddof=2)), .001)
            inverse_xtx = np.linalg.pinv(x.T @ x)
            level, variance, _ = local_level(window, q=sigma ** 2 * .1, r=sigma ** 2)
            for year in range(2010, 2026):
                tx = np.array([1, year - 2010])
                mean = float(tx @ beta)
                sd = sigma * float(1 + tx @ inverse_xtx @ tx) ** .5
                observed = cube[i, year - 2000, j]
                output.append({"region": region, "metric": metric, "year": year,
                               "observed": None if not np.isfinite(observed) else float(inverse(observed, metric)),
                               "scenario": float(inverse(mean, metric)), "lower": float(inverse(mean - 1.645 * sd, metric)),
                               "upper": float(inverse(mean + 1.645 * sd, metric)),
                               "alternative_level": float(inverse(level, metric)),
                               "alternative_sd_t": float((variance + max(0, year - 2020) * sigma ** 2 * .1) ** .5),
                               "training_end": 2019, "kind": "predictive_no_shock", "causal": False,
                               "window": "2010-2019; current source vintage"})
    write_json(ROOT / "data/results/scenarios.json", output)
    return {"rows": len(output), "countries": len({r["region"] for r in output}), "causal": False}
