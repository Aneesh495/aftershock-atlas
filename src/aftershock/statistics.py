"""Small explicit numerical methods with independent analytical tests."""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.special import gammaln
from scipy.stats import norm


def finite_vector(values) -> np.ndarray:
    array = np.asarray(values, dtype=np.float64)
    if array.ndim != 1 or not len(array) or not np.isfinite(array).all():
        raise ValueError("Expected nonempty finite vector")
    return array


def proper_scores(y, mean, sd, lower=None, upper=None) -> dict:
    y, mean, sd = (finite_vector(a) for a in (y, mean, sd))
    if y.shape != mean.shape or y.shape != sd.shape or (sd <= 0).any():
        raise ValueError("Score shapes or variance invalid")
    z = (y - mean) / sd
    nll = np.log(sd) + .5 * math.log(2 * math.pi) + .5 * z ** 2
    crps = sd * (z * (2 * norm.cdf(z) - 1) + 2 * norm.pdf(z) - 1 / math.sqrt(math.pi))
    lo = mean - norm.ppf(.95) * sd if lower is None else finite_vector(lower)
    hi = mean + norm.ppf(.95) * sd if upper is None else finite_vector(upper)
    interval = hi - lo + 20 * (lo - y) * (y < lo) + 20 * (y - hi) * (y > hi)
    return {"n": len(y), "mae": float(np.mean(abs(y - mean))), "rmse": float(np.mean((y - mean) ** 2) ** .5),
            "gaussian_nll": float(nll.mean()), "crps": float(crps.mean()), "interval_score_90": float(interval.mean()),
            "coverage_90": float(((y >= lo) & (y <= hi)).mean()), "width_90": float((hi - lo).mean())}


def conformal_multiplier(y, mean, sd, coverage: float = .9) -> float:
    if not 0 < coverage < 1:
        raise ValueError("Invalid coverage")
    y, mean, sd = (finite_vector(v) for v in (y, mean, sd))
    if len(y) < 10 or (sd <= 0).any():
        raise ValueError("Calibration needs at least ten valid observations")
    scores = np.sort(abs(y - mean) / sd)
    index = min(len(scores) - 1, math.ceil((len(scores) + 1) * coverage) - 1)
    return float(max(.01, scores[index]))


def ridge(x, y, penalty: float = 1e-5, weights=None) -> np.ndarray:
    x, y = np.asarray(x, float), finite_vector(y)
    if x.ndim != 2 or len(x) != len(y) or not np.isfinite(x).all() or penalty < 0:
        raise ValueError("Invalid regression input")
    w = np.ones(len(y)) if weights is None else finite_vector(weights)
    if (w <= 0).any() or len(w) != len(y):
        raise ValueError("Positive observation weights required")
    regularizer = np.eye(x.shape[1]) * penalty
    regularizer[0, 0] = 0
    return np.linalg.solve(x.T @ (w[:, None] * x) + regularizer, x.T @ (w * y))


def design_time(n: int, period: int | None = None, origin: int = 0) -> np.ndarray:
    t = np.arange(origin, origin + n, dtype=float)
    columns = [np.ones(n), t / 52]
    if period:
        for harmonic in (1, 2):
            columns.extend([np.sin(t * 2 * math.pi * harmonic / period), np.cos(t * 2 * math.pi * harmonic / period)])
    return np.stack(columns, axis=1)


@dataclass
class CountFit:
    beta: np.ndarray
    dispersion: float
    converged: bool
    iterations: int

    def predict(self, design, exposure=None) -> tuple[np.ndarray, np.ndarray]:
        x = np.asarray(design, float)
        offset = 0 if exposure is None else np.log(finite_vector(exposure))
        mean = np.exp(np.clip(x @ self.beta + offset, -25, 25))
        return mean, np.sqrt(mean + self.dispersion * mean ** 2)


def fit_negative_binomial(design, counts, exposure=None, iterations: int = 100) -> CountFit:
    x, y = np.asarray(design, float), finite_vector(counts)
    if (y < 0).any() or x.ndim != 2 or len(x) != len(y) or not np.isfinite(x).all():
        raise ValueError("Count model cannot silently discard negative corrections")
    offset = np.zeros(len(y)) if exposure is None else np.log(finite_vector(exposure))
    if not np.isfinite(offset).all():
        raise ValueError("Positive exposure required")
    beta = ridge(x, np.log(y + .5) - offset)
    alpha = .1
    converged = False
    for iteration in range(iterations):
        eta = np.clip(x @ beta + offset, -25, 25)
        mu = np.exp(eta)
        alpha = max(1e-8, float(np.sum((y - mu) ** 2 - mu) / max(np.sum(mu ** 2), 1)))
        w = mu / (1 + alpha * mu)
        z = eta - offset + (y - mu) / np.maximum(mu, 1e-8)
        next_beta = ridge(x, z, .001, w)
        if np.max(abs(next_beta - beta)) < 1e-8:
            beta = next_beta
            converged = True
            break
        beta = .5 * beta + .5 * next_beta
    return CountFit(beta, alpha, converged, iteration + 1)


def negative_binomial_nll(counts, mean, dispersion: float) -> float:
    y, mu = finite_vector(counts), finite_vector(mean)
    if (y < 0).any() or (mu <= 0).any() or dispersion <= 0:
        raise ValueError("Invalid count likelihood")
    size = 1 / dispersion
    ll = gammaln(y + size) - gammaln(size) - gammaln(y + 1)
    ll += size * np.log(size / (size + mu)) + y * np.log(mu / (size + mu))
    return float(-ll.mean())


def local_level(y, q: float = .1, r: float = 1.0) -> tuple[float, float, list[dict]]:
    values = np.asarray(y, float)
    valid = values[np.isfinite(values)]
    if not len(valid) or q < 0 or r <= 0:
        raise ValueError("Invalid state-space input")
    state, variance = float(valid[0]), r * 10
    trace = []
    for t, value in enumerate(values):
        variance += q
        predicted = state
        if np.isfinite(value):
            gain = variance / (variance + r)
            state += gain * (value - state)
            variance *= 1 - gain
        trace.append({"t": t, "prior": predicted, "state": state, "variance": variance,
                      "observed": bool(np.isfinite(value))})
    return state, variance + q + r, trace


def interrupted_time_series(y, onset: int, period: int | None = None) -> dict:
    y = finite_vector(y)
    if onset < 8 or len(y) - onset < 8:
        raise ValueError("Interrupted series needs pre and post support")
    x = design_time(len(y), period)
    step = (np.arange(len(y)) >= onset).astype(float)
    ramp = np.maximum(0, np.arange(len(y)) - onset) / 52
    x = np.column_stack((x, step, ramp))
    beta = ridge(x, y)
    residual = y - x @ beta
    bread = np.linalg.pinv(x.T @ x)
    scores = x * residual[:, None]
    meat = scores.T @ scores
    lag = min(4, len(y) // 5)
    for k in range(1, lag + 1):
        part = scores[k:].T @ scores[:-k]
        meat += (1 - k / (lag + 1)) * (part + part.T)
    cov = bread @ meat @ bread
    se = float(max(cov[-2, -2], 0) ** .5)
    effect = float(beta[-2])
    return {"level_change": effect, "se_hac": se, "lower": effect - 1.96 * se, "upper": effect + 1.96 * se,
            "slope_change_per_52_steps": float(beta[-1]), "n": len(y), "onset_index": onset,
            "interpretation": "descriptive interrupted time series; simultaneous shocks remain uncontrolled"}


def bh_adjust(pvalues: list[float]) -> list[float]:
    p = finite_vector(pvalues)
    if ((p < 0) | (p > 1)).any():
        raise ValueError("P-values outside unit interval")
    order = np.argsort(p)
    adjusted = np.minimum.accumulate((p[order] * len(p) / np.arange(1, len(p) + 1))[::-1])[::-1]
    out = np.empty_like(p)
    out[order] = np.minimum(1, adjusted)
    return out.tolist()
