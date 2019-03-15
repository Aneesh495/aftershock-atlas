import copy

import pytest

from aftershock.history import edition_bound, validate_archive


def archive_fixture():
    rows = [{"variable": [{"concept": "Country", "id": f"C{i}", "value": f"country {i}"},
                         {"concept": "Version", "id": "201811", "value": "2018 Nov"},
                         {"concept": "Series", "id": "SP.POP.TOTL", "value": "Population"},
                         {"concept": "Time", "id": "YR2010", "value": "2010"}], "value": 100 + i}
            for i in range(100)]
    return {"page": 1, "pages": 1, "total": 100, "source": {"id": "57", "data": rows}}


def test_archive_month_bound_is_explicit_and_handles_leap_years():
    assert edition_bound("202002") == "2020-02-29T23:59:59+00:00"
    assert edition_bound("201802") == "2018-02-28T23:59:59+00:00"
    for bad in ("201813", "20181", "future", "180001"):
        with pytest.raises(ValueError):
            edition_bound(bad)


def test_archive_rejects_partial_pages_and_edition_substitution():
    data = archive_fixture()
    assert len(validate_archive(data, "201811", "SP.POP.TOTL")) == 100
    data["pages"] = 2
    with pytest.raises(ValueError, match="pagination"):
        validate_archive(data, "201811", "SP.POP.TOTL")

    data["pages"] = 1
    with pytest.raises(ValueError, match="substituted"):
        validate_archive(data, "201912", "SP.POP.TOTL")
    data["source"]["data"][1] = copy.deepcopy(data["source"]["data"][0])
    with pytest.raises(ValueError, match="Duplicate"):
        validate_archive(data, "201811", "SP.POP.TOTL")


def test_array_header_cannot_request_more_memory_than_stored_bytes(tmp_path):
    import io
    from zipfile import ZipFile
    import numpy as np
    from aftershock.verification import verify_array_archive
    buffer = io.BytesIO()
    np.lib.format.write_array_header_1_0(buffer, {"descr": "<f8", "fortran_order": False, "shape": (100_000,)})
    path = tmp_path / "malformed.npz"
    with ZipFile(path, "w") as archive:
        archive.writestr("x.npy", buffer.getvalue() + b"\x00" * 8)
    with pytest.raises(ValueError, match="allocation"):
        verify_array_archive(path)


def test_saved_pass_flags_cannot_promote_unsupported_full_scope():
    from aftershock.verification import verify_declared_scope
    acceptance = {"profile": "full", "full_acceptance": True,
                  "gates": [{"gate": f"G{i:02d}", "status": "passed"} for i in range(1, 17)]}
    with pytest.raises(ValueError, match="exceed source-supported"):
        verify_declared_scope(acceptance)
    acceptance["gates"][-1] = acceptance["gates"][0]
    with pytest.raises(ValueError, match="population"):
        verify_declared_scope(acceptance)
