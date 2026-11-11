from aftershock.features import OUTCOMES, SEEDS
from aftershock.forecast import compare_learned


def test_country_cluster_comparison_has_native_booleans_and_known_ratio():
    scores = []
    for metric in OUTCOMES:
        for country in ("country:A", "country:B"):
            scores.append({"metric": metric, "group": country, "model": "persistence", "crps": 2, "n": 2})
            for seed in SEEDS:
                scores.append({"metric": metric, "group": country, "model": f"network_{seed}", "crps": 1, "n": 2})
    result = compare_learned(scores, dict.fromkeys(OUTCOMES, "persistence"))
    assert all(r["relative_crps_improvement"] == .5 for r in result)
    assert all(r["practical_5pct_and_positive_interval"] is True for r in result)
