import pytest

from aftershock.resources import usage


def test_nested_checkout_accounts_for_parent_project(tmp_path, monkeypatch):
    project = tmp_path / "project"
    checkout = project / "replay"
    checkout.mkdir(parents=True)
    (project / "owned-source.bin").write_bytes(b"x" * 8192)
    monkeypatch.setenv("AFTERSHOCK_ACCOUNTING_ROOT", str(project))
    measured = usage(root=checkout)
    assert measured["project_bytes"] >= 8192
    assert (project / ".agent-local/resources.jsonl").is_file()
    monkeypatch.setenv("AFTERSHOCK_ACCOUNTING_ROOT", str(tmp_path / "unrelated"))
    with pytest.raises(ValueError, match="must contain"):
        usage(root=checkout)
