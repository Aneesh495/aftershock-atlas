"""Engineering diagnostics keep measured work separate from scientific acceptance."""
from __future__ import annotations

import re
import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np

from .io import ROOT, atomic_path, now, read_json, write_json
from .network import TemporalNetwork
from .resources import usage


def engineering_campaign(profile: str) -> dict:
    usage(30_000_000)
    started = time.monotonic()
    if profile == "bench":
        rng = np.random.default_rng(11)
        network = TemporalNetwork(48, 6, 11)
        x = rng.normal(size=(4096, 48))
        durations = []
        for _ in range(15):
            tick = time.perf_counter()
            mean, sd = network.forward(x)
            durations.append(time.perf_counter() - tick)
            if not np.isfinite(mean).all() or not (sd > 0).all():
                raise ValueError("Invalid inference output")
        result = {"kind": "CPU engineering diagnostic", "workload": "15 batches of 4096 synthetic feature vectors; no scientific acceptance",
                  "completed_rows": 15 * len(x), "median_batch_seconds": float(np.median(durations)),
                  "raw_batch_seconds": durations, "dtype": "float64", "threads": "OPENBLAS_NUM_THREADS=1"}
    else:
        checks = []
        with tempfile.TemporaryDirectory(dir=ROOT / ".agent-local", prefix="stress-") as directory:
            path = Path(directory) / "state.json"
            write_json(path, {"state": "preserved"})
            try:
                with atomic_path(path) as temporary:
                    temporary.write_text("interrupted")
                    raise InterruptedError("known fault")
            except InterruptedError:
                checks.append({"fault": "atomic writer interrupted", "prior_preserved": read_json(path)["state"] == "preserved"})
            path.write_text('{"value":NaN}')
            try:
                read_json(path)
                raise RuntimeError("Accepted nonfinite JSON")
            except ValueError:
                checks.append({"fault": "nonfinite JSON", "rejected": True})
            path.write_text("x" * 1001)
            try:
                read_json(path, 1000)
                raise RuntimeError("Accepted oversized JSON")
            except ValueError:
                checks.append({"fault": "oversized JSON", "rejected": True})
            model = TemporalNetwork(2, 1, 47, 4)
            model.save(Path(directory) / "resume.npz")
            restored, _ = TemporalNetwork.load(Path(directory) / "resume.npz")
            checks.append({"fault": "checkpoint restart", "rng_replayed": bool(model.rng.integers(2**31) == restored.rng.integers(2**31))})
        if not all(all(v is True for k, v in c.items() if k != "fault") for c in checks):
            raise ValueError("Stress invariant failed")
        result = {"kind": "deterministic fault diagnostic", "checks": checks, "scientific_acceptance": False}
    result.update(at=now(), elapsed_seconds=time.monotonic() - started)
    write_json(ROOT / "data/results" / f"{profile}.json", result)
    return result


def check_documentation() -> dict:
    markdown = [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]
    errors = []
    for path in markdown:
        text = path.read_text()
        if "\u2014" in text:
            errors.append(str(path.relative_to(ROOT)) + ": forbidden punctuation")
        for label, target in re.findall(r"\[([^\]]+)\]\(([^)]+)\)", text):
            if target.startswith(("https://", "http://", "#", "mailto:")):
                continue
            local = target.split("#")[0]
            if local and not (path.parent / local).resolve().exists():
                errors.append(f"{path.relative_to(ROOT)}: missing {target}")
    diagrams = sorted((ROOT / "docs/diagrams").glob("*.dot"))
    for source in diagrams:
        process = subprocess.run(["dot", "-Tsvg", str(source), "-o", str(source.with_suffix(".svg"))], capture_output=True, text=True)
        if process.returncode:
            errors.append(source.name + ": " + process.stderr)
        else:
            import xml.etree.ElementTree as ET
            tree = ET.parse(source.with_suffix(".svg"))
            if not tree.getroot().attrib.get("viewBox"):
                errors.append(source.name + ": invalid SVG viewport")
    if len(diagrams) < 12:
        errors.append("At least twelve distinct editable diagrams required")
    if errors:
        raise ValueError("Documentation checks failed: " + "; ".join(errors))
    return {"markdown_files": len(markdown), "rendered_diagrams": len(diagrams), "broken_local_links": 0}
