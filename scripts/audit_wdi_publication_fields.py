#!/usr/bin/env python3
"""Measure publication-date metadata coverage in the pinned WDI archive responses."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/history-inputs.json"
RAW = ROOT / "data/history/raw"
PUBLICATION_FIELDS = {"first_release_day", "first_published", "publication_date", "available_at", "release_date"}


def audit() -> dict:
    contracts = json.loads(CONFIG.read_bytes())
    observed = Counter()
    top_level = Counter()
    record_fields = Counter()
    dimension_sets = Counter()
    partitions = []
    count = 0
    for identity, pin in sorted(contracts.items()):
        if not identity.startswith("archive_"):
            continue
        _, edition, metric = identity.split("_", 2)
        path = (RAW / pin["path"]).resolve()
        if not path.is_relative_to(RAW.resolve()) or path.stat().st_size != pin["bytes"]:
            raise ValueError("WDI archive object is outside its declared location or size")
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != pin["sha256"]:
            raise ValueError(f"WDI archive source checksum differs: {identity}")
        decoded = json.loads(payload)
        source = decoded["source"]
        rows = source["data"]
        if decoded["pages"] != 1 or decoded["total"] != len(rows):
            raise ValueError(f"WDI source page is incomplete: {identity}")
        observed[edition] += len(rows)
        top_level.update(decoded.keys())
        seen = 0
        for row in rows:
            record_fields.update(row.keys())
            dimension = {d["concept"]: d["id"] for d in row["variable"]}
            if dimension.pop("Version") != edition:
                raise ValueError("Different WDI edition embedded in the evidence")
            dimension_sets[", ".join(sorted(dimension))] += 1
            fields = {str(key).lower() for key in row}
            if PUBLICATION_FIELDS & fields:
                seen += 1
        count += seen
        partitions.append({"metric": metric, "edition": edition, "rows": len(rows), "original_cell_timestamps": seen})
    return {
        "manifest_sha256": hashlib.sha256(CONFIG.read_bytes()).hexdigest(),
        "partition_count": len(partitions),
        "row_count": sum(observed.values()),
        "row_counts_by_edition": dict(observed),
        "top_level_fields_partition_count": dict(sorted(top_level.items())),
        "record_fields_row_count": dict(sorted(record_fields.items())),
        "dimensions_excluding_registered_version_row_count": dict(dimension_sets),
        "original_cell_timestamps": count,
        "conclusion": "Reference year and edition month are observed. The audited WDI response schema does not provide a first publication timestamp for any returned observation.",
        "archive_docs": "https://datatopics.worldbank.org/world-development-indicators/wdi-archives.html",
        "partitions": partitions,
    }


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2, sort_keys=True))
