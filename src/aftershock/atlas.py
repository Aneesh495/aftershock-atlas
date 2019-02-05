"""Build a privacy-filtered, source-bound static research atlas."""
from __future__ import annotations

import shutil
import subprocess

import pycountry

from .contracts import METRICS
from .io import ROOT, digest, now, read_json, source_commit, write_json
from .panel import connect, records
from .privacy import Disclosure
from .resources import usage


def export_atlas(build: bool = True) -> dict:
    usage(150_000_000)
    public = ROOT / "client/public/data"
    public.mkdir(parents=True, exist_ok=True)
    manifest = read_json(ROOT / "data/panel/manifest.json")
    sources = read_json(ROOT / "data/raw/index.json")
    registry = read_json(ROOT / "data/panel/regions.json")
    with connect() as db:
        for metric, definition in METRICS.items():
            if definition.frequency != "annual":
                continue
            points = records(db, """SELECT region,CAST(substr(event_start,1,4) AS INTEGER) AS yr,value
                FROM observations WHERE metric=? AND \"group\"='total' ORDER BY region,event_start""", [metric])
            write_json(public / f"{metric}.json", points)
        annual_surveillance = records(db, """SELECT region,metric,CAST(substr(event_end,1,4) AS INTEGER) AS yr,
            sum(value) AS value,count(value) reported_weeks,count(*) total_weeks FROM observations
            WHERE metric IN ('covid_cases','covid_deaths') GROUP BY region,metric,yr ORDER BY region,yr""")
        weekly = records(db, """SELECT region,metric,event_start,event_end,value,flags FROM observations
            WHERE metric IN ('covid_cases','covid_deaths') AND region IN ('USA','GBR','IND','BRA','DEU','ZAF')
            ORDER BY region,metric,event_start""")
    write_json(public / "surveillance.json", annual_surveillance)
    write_json(public / "weekly.json", weekly)
    written = ["studies", "scenarios", "genetics", "excess", "subnational", "surveys", "mobility", "causal"]
    for name in written:
        value = read_json(ROOT / f"data/results/{name}.json")
        if name == "surveys":
            value["rows"] = [Disclosure().apply(row) for row in value["rows"]]
        write_json(public / f"{name}.json", value)
    lineages = read_json(ROOT / "data/results/lineages.json")
    write_json(public / "lineages.json", lineages)
    fit = read_json(ROOT / "data/results/fit.json")
    write_json(public / "scores.json", {k: v for k, v in fit.items() if k != "training"})
    source_cards = [{k: v for k, v in source.items() if k not in {"headers", "path"}} for source in sources.values()]
    write_json(public / "sources.json", source_cards)
    numeric = {c.numeric: c.alpha_3 for c in pycountry.countries}
    shutil.copyfile(ROOT / "data/raw" / sources["world_map"]["path"], public / "world.json")
    header = {"version": 1, "built_at": now(), "source_commit": source_commit(), "panel_sha256": manifest["sha256"],
              "record_count": manifest["rows"], "country_registry": registry,
              "metrics": {k: m.public() for k, m in METRICS.items()}, "coverage": manifest["coverage"],
              "numeric_to_iso3": numeric, "vintage": "2026-11-11 acquisition; final-vintage retrospective panel",
              "limitations": ["Full acceptance remains incomplete", "Published surveys have no matched pre-2020 baseline",
                              "Predictive no-shock bands are extrapolations, not causal estimates"],
              "files": {p.name: digest(p) for p in sorted(public.glob("*.json")) if p.name != "index.json"}}
    write_json(public / "index.json", header)
    if build:
        command = subprocess.run(["npm", "run", "build"], cwd=ROOT / "client")
        if command.returncode:
            raise RuntimeError("Client build failed")
        destination = ROOT / "dist"
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(ROOT / "client/dist", destination)
    return {"public_files": len(header["files"]), "panel_sha256": manifest["sha256"], "built": build}
