import threading
import urllib.error
import urllib.request
from functools import partial

import pytest

from aftershock.io import ROOT, read_json
from aftershock.server import AtlasHandler, BoundedHTTPServer


@pytest.fixture
def public_server():
    if not (ROOT / "client/public/data/index.json").exists():
        pytest.skip("Exported real-data snapshot required for public integration")
    handler = partial(AtlasHandler, directory=str(ROOT / "client/public"))
    server = BoundedHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_real_snapshot_api_and_export(public_server):
    import json
    with urllib.request.urlopen(public_server + "/api/observations?metric=employment&regions=USA,GBR&start=2019&end=2023") as response:
        data = json.load(response)
    assert data["count"] == 10
    assert {r["region"] for r in data["rows"]} == {"USA", "GBR"}
    with urllib.request.urlopen(public_server + "/api/export?metric=employment&regions=USA&start=2019&end=2020") as response:
        assert response.headers["Content-Type"].startswith("text/csv")
        import csv
        import io
        rows = list(csv.DictReader(io.StringIO(response.read().decode())))
        assert [r["yr"] for r in rows] == ["2019", "2020"]
        assert all(r["region"] == "USA" for r in rows)
    for path in ("/api/observations?metric=../../raw", "/api/observations?end=9999", "/api/private", "/data/raw/", "/data/private-survey/"):
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(public_server + path)
        assert error.value.code in (400, 403, 404)


def test_provider_suppression_in_public_cache():
    path = ROOT / "client/public/data/surveys.json"
    if not path.exists():
        pytest.skip("Exported survey source required")
    rows = read_json(path)["rows"]
    hidden = [r for r in rows if r.get("suppressed")]
    assert len(hidden) > 0
    assert all(r["value"] is None and r["lower"] is None and r["upper"] is None for r in hidden)
    assert all(not {"person_id", "sample_n", "raw_weight", "respondent"}.intersection(r) for r in rows)


def test_design_export_contains_only_aggregate_cells():
    path = ROOT / "client/public/data/surveys.json"
    if not path.exists() or "design_replay" not in read_json(path):
        pytest.skip("Extension snapshot required")
    design = read_json(path)["design_replay"]
    assert len(design["rows"]) == 24
    assert design["raw_in_evidence"] is False
    assert all(r["complete_respondents"] >= 100 for r in design["rows"] if not r.get("suppressed"))
    def inspect(value):
        if isinstance(value, dict):
            assert not {"SCRAM", "PWEIGHT", "PWEIGHT1", "person_id", "raw_weight", "sample_n"}.intersection(value)
            for child in value.values():
                inspect(child)
        elif isinstance(value, list):
            for child in value:
                inspect(child)
    inspect(design)
