import hashlib
import json
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from aftershock.io import write_json
from aftershock.features import held_out
from aftershock.network import TemporalNetwork
from aftershock.verification import verify_forecasts, verify_manifest


def test_manifest_rejects_corruption_and_missing_artifacts(tmp_path):
    files = {}
    for i in range(15):
        name = f"record-{i}.json"
        data = json.dumps({"synthetic_structural_probe": i}).encode()
        (tmp_path / name).write_bytes(data)
        files[name] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    write_json(tmp_path / "MANIFEST.json", {"files": files})
    verify_manifest(tmp_path)
    original = (tmp_path / "record-0.json").read_bytes()
    (tmp_path / "record-0.json").write_text("corrupted")
    with pytest.raises(ValueError, match="checksum"):
        verify_manifest(tmp_path)
    (tmp_path / "record-0.json").write_bytes(original)
    (tmp_path / "record-0.json").unlink()
    with pytest.raises(ValueError, match="Unlisted or missing"):
        verify_manifest(tmp_path)


def test_structurally_valid_future_feature_is_semantically_rejected(tmp_path):
    row = {"model": "synthetic_probe", "metric": "employment", "region": "USA", "target_year": 2020,
           "feature_last_year": 2020, "held_out_region": held_out("USA")}
    write_json(tmp_path / "predictions.json", [row] * 1001)
    write_json(tmp_path / "fit.json", {"scores": []})
    with pytest.raises(ValueError, match="Future feature label"):
        verify_forecasts(tmp_path, {})


def test_checkpoint_rejects_zip_expansion_before_loading_arrays(tmp_path):
    path = tmp_path / "bomb.npz"
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("oversized.npy", b"0" * 20_000_001)
    assert path.stat().st_size < 100000
    with pytest.raises(ValueError, match="expansion"):
        TemporalNetwork.load(path)
