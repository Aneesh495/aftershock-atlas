from aftershock import quality


def test_stress_fault_receipts_are_json_booleans(tmp_path, monkeypatch):
    (tmp_path / ".agent-local").mkdir()
    monkeypatch.setattr(quality, "ROOT", tmp_path)
    result = quality.engineering_campaign("stress")
    assert len(result["checks"]) == 4
    assert result["checks"][-1]["rng_replayed"] is True
    assert (tmp_path / "data/results/stress.json").is_file()
