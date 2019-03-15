"""Safe preview packaging, immutable source snapshots and explicit release limitations."""
from __future__ import annotations

import tarfile
from pathlib import Path
from zipfile import ZipFile
import shutil

from .io import ROOT, digest, read_json, write_json
from .resources import usage
from .verification import verify_bundle


def package_release(evidence: str | None) -> dict:
    if not evidence:
        raise ValueError("Release packaging requires --evidence for an independently verified diagnostic bundle")
    bundle = Path(evidence).resolve()
    source = read_json(bundle / "SOURCE_INPUTS.json")["commit"]
    verification = verify_bundle(bundle, source)
    if len(read_json(bundle / "negative-controls.json")["controls"]) < 19:
        raise ValueError("Nineteen recorded negative controls required before packaging")
    usage(250_000_000)
    output = ROOT / "releases"
    output.mkdir(exist_ok=True)
    archive = output / "aftershock-atlas-preview.tar.gz"
    if not (ROOT / "dist/index.html").is_file():
        raise ValueError("Build the atlas before packaging")
    with tarfile.open(archive, "w:gz") as tar:
        for path in (ROOT / "dist", ROOT / "docs", ROOT / "README.md", ROOT / "LICENSE", ROOT / "configs"):
            tar.add(path, arcname="aftershock-atlas/" + str(path.relative_to(ROOT)))
    snapshot = output / "aftershock-core-inputs.zip"
    frozen = read_json(ROOT / "configs/SNAPSHOT.json")
    if not snapshot.exists() or digest(snapshot) != frozen["sha256"]:
        from .acquire import Source, acquire_one
        source_spec = Source("core_snapshot", frozen["url"], "zip", 100_000_000,
            "Mixed frozen source terms", frozen["url"], "immutable source snapshot", "No raw respondent, HGI or mobility files")
        received = acquire_one(source_spec, ROOT / "data/raw")
        cached = ROOT / "data/raw" / received["path"]
        if digest(cached) != frozen["sha256"]:
            raise ValueError("Core restoration snapshot identity mismatch")
        shutil.copyfile(cached, snapshot)
    with ZipFile(snapshot) as zipped:
        import hashlib
        if hashlib.sha256(zipped.read("SNAPSHOT.json")).hexdigest() != digest(ROOT / "configs/data-inputs.json"):
            raise ValueError("Frozen core archive metadata differs from trusted source inputs")
    history = output / "aftershock-history-inputs.zip"
    history_pin = read_json(ROOT / "configs/HISTORY_SNAPSHOT.json")
    if not history.exists() or digest(history) != history_pin["sha256"]:
        from .acquire import Source, acquire_one
        spec = Source("history_snapshot", history_pin["url"], "zip", 80_000_000,
            "World Bank CC BY 4.0 with additional terms", history_pin["url"], "immutable official-edition snapshot", "No respondent records")
        received = acquire_one(spec, ROOT / "data/history/raw")
        cached = ROOT / "data/history/raw" / received["path"]
        if digest(cached) != history_pin["sha256"]:
            raise ValueError("Historical restoration snapshot identity mismatch")
        shutil.copyfile(cached, history)
    receipt = {"release_kind": "preview", "full_acceptance": False, "executable_source": source,
               "verification": verification, "evidence_identity": bundle.name,
               "files": {p.name: {"sha256": digest(p), "bytes": p.stat().st_size} for p in (archive, snapshot, history)},
               "limitations": "Full scientific and implementation acceptance remains incomplete. Raw Census public-use, mobility and HGI downloads are acquired separately and excluded from release input snapshots."}
    write_json(output / "RELEASE.json", receipt)
    return receipt
