"""Safe preview packaging, immutable source snapshots and explicit release limitations."""
from __future__ import annotations

import tarfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from .io import ROOT, digest, read_json, write_json
from .resources import usage
from .verification import verify_bundle


def package_release(evidence: str | None) -> dict:
    if not evidence:
        raise ValueError("Release packaging requires --evidence for an independently verified diagnostic bundle")
    bundle = Path(evidence).resolve()
    source = read_json(bundle / "SOURCE_INPUTS.json")["commit"]
    verification = verify_bundle(bundle, source)
    if len(read_json(bundle / "negative-controls.json")["controls"]) < 10:
        raise ValueError("Ten recorded negative controls required before packaging")
    usage(250_000_000)
    output = ROOT / "releases"
    output.mkdir(exist_ok=True)
    archive = output / "aftershock-atlas-preview.tar.gz"
    if not (ROOT / "dist/index.html").is_file():
        raise ValueError("Build the atlas before packaging")
    with tarfile.open(archive, "w:gz") as tar:
        for path in (ROOT / "dist", ROOT / "docs", ROOT / "README.md", ROOT / "LICENSE", ROOT / "configs"):
            tar.add(path, arcname="aftershock-atlas/" + str(path.relative_to(ROOT)))
    sources = read_json(ROOT / "configs/data-inputs.json")
    snapshot = output / "aftershock-core-inputs.zip"
    with ZipFile(snapshot, "w", compression=ZIP_DEFLATED) as zipped:
        for key, source in sources.items():
            if source["redistribute"]:
                path = ROOT / "data/raw" / source["path"]
                if digest(path) != source["sha256"]:
                    raise ValueError("Upstream bytes changed before packaging")
                zipped.write(path, arcname=source["path"])
        zipped.write(ROOT / "configs/data-inputs.json", arcname="SNAPSHOT.json")
        zipped.write(ROOT / "docs/DATA_RIGHTS.md", arcname="DATA_RIGHTS.md")
    receipt = {"release_kind": "preview", "full_acceptance": False, "executable_source": source,
               "verification": verification, "evidence_identity": bundle.name,
               "files": {p.name: {"sha256": digest(p), "bytes": p.stat().st_size} for p in (archive, snapshot)},
               "limitations": "Full scientific and implementation acceptance remains incomplete. Raw mobility and HGI downloads are acquired separately under their own terms."}
    write_json(output / "RELEASE.json", receipt)
    return receipt
