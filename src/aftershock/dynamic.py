"""Original empirical-Bayes damped level/slope filter, fitted on training targets."""
from __future__ import annotations

import numpy as np
from scipy.optimize import minimize

from .features import OUTCOMES, make_features
from .forecast import prediction_records, summarize_predictions
from .io import ROOT, digest, read_json, source_commit, write_json
from .resources import usage


def filter_windows(windows: np.ndarray, parameters: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Forecast one step after each four-lag window, without reading any targets."""
    values = np.asarray(windows, dtype=float)
    if values.ndim != 2 or values.shape[1] != 4:
        raise ValueError("Four chronological lag columns required")
    prior_mean, log_tau, log_q_level, log_q_slope, log_r, phi = np.asarray(parameters, float)
    if not np.isfinite(parameters).all() or not 0 <= phi <= 1:
        raise ValueError("Invalid dynamic parameters")
    tau, q_level, q_slope, r = np.exp([log_tau, log_q_level, log_q_slope, log_r])
    transition = np.array([[1., phi], [0., phi]])
    q = np.diag([q_level, q_slope])
    n = len(values)
    valid = np.isfinite(values)
    first = np.argmax(valid, axis=1)
    origin = values[np.arange(n), first]
    supported = valid.any(axis=1)
    origin = np.where(supported, origin, 0.)
    # The first observed level centers its latent prior; its uncertainty is R.
    state = np.column_stack([np.zeros(n), np.full(n, prior_mean)])
    covariance = np.broadcast_to(np.diag([r, tau]), (n, 2, 2)).copy()
    identity = np.eye(2)
    for t in range(1, 5):
        active = first < t
        predicted = state @ transition.T
        propagated = transition @ covariance @ transition.T + q
        state[active], covariance[active] = predicted[active], propagated[active]
        if t == 4:
            break
        observed = active & valid[:, t]
        residual = values[observed, t] - origin[observed] - state[observed, 0]
        gain = covariance[observed, :, 0] / (covariance[observed, 0, 0] + r)[:, None]
        state[observed] += gain * residual[:, None]
        # Joseph form preserves positive covariance near tiny-noise boundaries.
        kh = np.zeros((observed.sum(), 2, 2))
        kh[:, :, 0] = gain
        a = identity - kh
        covariance[observed] = a @ covariance[observed] @ a.transpose(0, 2, 1) + r * gain[:, :, None] * gain[:, None, :]
    means = state[:, 0] + origin
    variances = covariance[:, 0, 0] + r
    if not np.isfinite(means).all() or not np.isfinite(variances).all() or (variances <= 0).any():
        raise ValueError("Nonfinite or nonpositive dynamic prediction")
    means[~supported] = np.nan
    variances[~supported] = np.nan
    return means, variances


def fit_dynamic() -> dict:
    usage(100_000_000)
    features = make_features()
    prediction_mean = np.zeros_like(features.target)
    prediction_sd = np.ones_like(features.target)
    fits = []
    for j, metric in enumerate(OUTCOMES):
        scale = float(features.yscale[j])
        windows = features.raw.reshape(-1, 4, len(OUTCOMES))[:, :, j] / scale
        targets = (features.target[:, j] + features.base[:, j]) / scale
        selected = features.train & features.mask[:, j]
        weights = features.weights[selected]
        def objective(parameters):
            mu, variance = filter_windows(windows[selected], parameters)
            nll = .5 * (np.log(2 * np.pi * variance) + (targets[selected] - mu) ** 2 / variance)
            return float(np.average(nll, weights=weights))
        starts = []
        candidates = []
        prior = float(np.average(features.target[selected, j] / scale, weights=weights))
        for damping in (.2, .7, 1.):
            initial = np.array([prior, 0., -2., -3., 0., damping])
            result = minimize(objective, initial, method="L-BFGS-B",
                              bounds=[(-10, 10)] + [(-8, 6)] * 4 + [(0, 1)],
                              options={"maxiter": 150, "ftol": 1e-10})
            record = {"initial_phi": damping, "converged": bool(result.success), "message": str(result.message),
                      "iterations": int(result.nit), "training_nll": float(result.fun),
                      "parameters": result.x.tolist()}
            starts.append(record)
            if np.isfinite(result.fun) and np.isfinite(result.x).all():
                candidates.append(record)
        if not candidates:
            raise ValueError("All hierarchical starts failed: " + metric)
        chosen = min(candidates, key=lambda r: r["training_nll"])
        mu, variance = filter_windows(windows, np.array(chosen["parameters"]))
        prediction_mean[:, j] = np.nan_to_num(mu * scale - features.base[:, j])
        prediction_sd[:, j] = np.nan_to_num(np.sqrt(variance) * scale, nan=scale)
        fits.append({"metric": metric, "training_rows": int(selected.sum()), "training_countries": len({
            k["region"] for k, use in zip(features.keys, selected) if use}), "scale": scale,
            "chosen": chosen, "starts": starts,
            "boundary_parameters": [i for i, p in enumerate(chosen["parameters"]) if
                (i == 5 and min(abs(p), abs(p - 1)) < 1e-5) or (1 <= i <= 4 and min(abs(p + 8), abs(p - 6)) < 1e-4)]})
        print(f"dynamic {metric}: NLL {chosen['training_nll']:.5f}, converged {chosen['converged']}", flush=True)
    predictions = prediction_records(features, "hierarchical_damped", prediction_mean, prediction_sd, {"fitted": True})
    scores = summarize_predictions(predictions)
    prior = read_json(ROOT / "data/results/fit.json")
    comparisons = []
    for metric in OUTCOMES:
        for group in ("all", "held_out_country", "retained_country"):
            baseline = next(r for r in prior["scores"] if r["model"] == prior["selected_baselines"][metric]
                            and r["metric"] == metric and r["group"] == group)
            current = next(r for r in scores if r["metric"] == metric and r["group"] == group)
            comparisons.append({"metric": metric, "group": group, "baseline": baseline["model"],
                                "relative_crps_improvement": 1 - current["crps"] / baseline["crps"],
                                "coverage_90": current["coverage_90"], "n": current["n"],
                                "interpretation": "exploratory reused test outcomes, not a fresh confirmatory comparison"})
    result = {"source": source_commit(), "protocol": "extension-v2-exploratory",
              "protocol_sha256": digest(ROOT / "docs/EXTENSION_PLAN_V2.md"),
              "panel_sha256": digest(ROOT / "data/panel/observations.parquet"), "fits": fits,
              "completed_configurations": len(OUTCOMES), "attempted_starts": sum(len(r["starts"]) for r in fits),
              "converged_starts": sum(s["converged"] for r in fits for s in r["starts"]),
              "prediction_rows": len(predictions), "scores": scores, "comparisons": comparisons,
              "parameter_order": ["slope_prior_mean", "log_slope_prior_variance", "log_level_process_variance",
                                   "log_slope_process_variance", "log_observation_variance", "damping"],
              "limitations": ["Empirical-Bayes Gaussian shared slope prior; no demographic or spatial causal interpretation",
                "Repeated windows use a weighted conditional working likelihood", "Noise parameters are shared within outcome",
                "Test outcomes were already inspected in version 1", "Final-vintage retrospective information only"]}
    write_json(ROOT / "data/results/dynamic-predictions.json", predictions)
    write_json(ROOT / "data/results/dynamic.json", result)
    return {k: v for k, v in result.items() if k not in {"fits", "scores"}}
