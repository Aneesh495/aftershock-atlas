"""Publish source-bound state partitions and protected survey aggregates."""

from __future__ import annotations

from pathlib import Path

import pycountry

from .io import ROOT, read_json, write_json


def export_health(public: Path) -> dict:
    results = ROOT / "data/results"
    surveillance = results / "state-surveillance.json"
    bridge = results / "survey-bridge.json"
    cards = {}
    if surveillance.exists():
        data = read_json(surveillance)
        states = data.pop("states")
        data["jurisdictions"] = []
        for code, weeks in states.items():
            name = pycountry.subdivisions.get(code=f"US-{code}").name
            data["jurisdictions"].append({"code": code, "label": name})
            write_json(public / f"state-report-{code.lower()}.json", {
                "code": code,
                "source": data["source"],
                "definition_sha256": data["definition_sha256"],
                "weeks": weeks,
            })
        data["jurisdictions"].sort(key=lambda item: item["label"])
        write_json(public / "state-surveillance.json", data)
        cards.update(read_json(ROOT / "configs/surveillance-inputs.json"))
    if bridge.exists():
        data = read_json(bridge)
        write_json(public / "survey-bridge.json", data)
        cards.update(read_json(ROOT / "configs/survey-bridge-inputs.json"))
    return {key: {**value, "status": "acquired"} for key, value in cards.items()}
