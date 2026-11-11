"""Two source-defined state case studies with seasonal count baselines."""
from __future__ import annotations

import numpy as np
from scipy.stats import nbinom

from .io import ROOT, write_json
from .panel import connect, records
from .statistics import design_time, fit_negative_binomial, negative_binomial_nll


def subnational_studies() -> dict:
    studies = []
    with connect() as db:
        for region in ("US-CA", "US-FL"):
            rows = records(db, """SELECT event_start,event_end,value,flags FROM observations
                WHERE metric='allcause_weekly' AND region=? AND value IS NOT NULL ORDER BY event_start""", [region])
            if len(rows) < 400:
                raise ValueError("Subnational pre/during coverage insufficient")
            train = np.array([r["event_end"] < "2019-01-01" for r in rows])
            validation = np.array(["2019-01-01" <= r["event_end"] < "2020-01-01" for r in rows])
            test = np.array(["2020-01-01" <= r["event_end"] < "2023-01-01" for r in rows])
            y = np.array([r["value"] for r in rows])
            x = design_time(len(y), 52)
            model = fit_negative_binomial(x[train], y[train])
            if not model.converged:
                raise ValueError("Count fit failed to converge")
            mean, sd = model.predict(x)
            size = 1 / model.dispersion
            probability = size / (size + mean)
            lower, upper = nbinom.ppf(.05, size, probability), nbinom.ppf(.95, size, probability)
            points = [{**r, "expected": float(mean[i]), "lower": float(lower[i]), "upper": float(upper[i]),
                       "difference": float(y[i] - mean[i]), "phase": "pre" if train[i] or validation[i] else "pandemic",
                       "kind": "observed_count_with_predictive_no_shock", "denominator": None} for i, r in enumerate(rows)]
            studies.append({"region": region, "rows": points, "model": "original negative-binomial IRLS with trend and two seasonal harmonics",
                            "training_weeks": int(train.sum()), "validation_weeks": int(validation.sum()), "test_weeks": int(test.sum()),
                            "dispersion": model.dispersion, "iterations": model.iterations,
                            "test_nll": negative_binomial_nll(y[test], mean[test], model.dispersion),
                            "validation_coverage_90": float(((y[validation] >= lower[validation]) & (y[validation] <= upper[validation])).mean()),
                            "test_coverage_90": float(((y[test] >= lower[test]) & (y[test] <= upper[test])).mean()),
                            "observed_minus_predicted_2020_2022": float((y[test] - mean[test]).sum()),
                            "causal": False, "denominator_status": "Not joined: counts by occurrence, no matching residence-based rate denominator",
                            "limitations": ["Predictive intervals omit coefficient uncertainty", "Final 2014-2019 and provisional 2020-2023 definitions differ",
                                            "No age adjustment; state count differences are not disparity rate estimates"]})
    result = {"case_studies": studies, "source": "CDC NVSS state of occurrence", "count": len(studies)}
    write_json(ROOT / "data/results/subnational.json", result)
    return {"count": len(studies), "regions": [s["region"] for s in studies]}
