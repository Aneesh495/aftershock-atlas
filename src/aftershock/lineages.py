"""CDC weighted viral estimates retain publication identity and reliability flags."""
from __future__ import annotations

from collections import Counter

from .io import ROOT, read_json, write_json
from .panel import csv_rows, number


def analyze_lineages() -> dict:
    index = read_json(ROOT / "data/raw/index.json")
    source = index["lineage"]
    rows = list(csv_rows(ROOT / "data/raw" / source["path"], cap=199999))
    versions: dict[tuple, dict] = {}
    duplicates = 0
    all_ids = set()
    for row in rows:
        key = tuple(row[k] for k in ("usa_or_hhsregion", "week_ending", "variant", "time_interval", "modeltype"))
        publication = row["creation_date"]
        identity = (*key, publication)
        if identity in all_ids:
            duplicates += 1
        all_ids.add(identity)
        if key not in versions or publication > versions[key]["creation_date"]:
            versions[key] = row
    selected, suppressed = [], 0
    for row in versions.values():
        value = number(row["share"])
        lower, upper = number(row["share_lo"]), number(row["share_hi"])
        if value is not None and not 0 <= value <= 1:
            raise ValueError("Lineage share outside [0,1]")
        unreliable = number(row["count_lt10"]) != 0
        if unreliable:
            suppressed += 1
            value, lower, upper = None, None, None
        selected.append({"region": row["usa_or_hhsregion"], "week": row["week_ending"][:10],
                         "variant": row["variant"], "value": value, "lower": lower, "upper": upper,
                         "publication": row["creation_date"][:10], "interval": row["time_interval"],
                         "kind": "weighted_lineage_estimate", "suppressed": unreliable})
    result = {"input_rows": len(rows), "unique_selected_rows": len(selected), "duplicate_source_rows": duplicates,
              "suppressed_rows": suppressed, "publication_count": len({r["creation_date"] for r in rows}),
              "interval_counts": dict(Counter(r["interval"] for r in selected)), "source_hash": source["sha256"],
              "geography": "USA national", "model": "CDC weighted estimates; no nowcast mixed into this extract",
              "limitations": ["Variant aggregates may overlap hierarchically; shares are not summed across arbitrary labels",
                              "Publication changes and sequencing selection can alter estimates",
                              "Weighted surveillance estimates are not raw submission prevalence",
                              "No link to human host genetic association records"], "rows": sorted(selected, key=lambda r: (r["week"], r["variant"]))}
    write_json(ROOT / "data/results/lineages.json", result)
    return {k: v for k, v in result.items() if k != "rows"}
