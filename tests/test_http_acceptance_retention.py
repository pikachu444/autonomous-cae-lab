"""Retention regression; these minimal ZIPs are TEST ONLY, not native evidence."""

import hashlib
import io
import json
import zipfile

import pytest

from scripts.verify_lab_ui import check_bundle, retain_library_bundle


def _test_bundle(marker):
    files = {"result.json": json.dumps({"test_only": marker}).encode(),
             "thread.json": b'{"test_only": true}', "report.html": b"TEST ONLY"}
    rows = [{"path": name, "size_bytes": len(value), "sha256": hashlib.sha256(value).hexdigest()}
            for name, value in files.items()]
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        for name, value in files.items():
            archive.writestr(name, value)
        archive.writestr("bundle_manifest.json", json.dumps({"files": rows}))
    return data.getvalue()


def test_valid_hyphenated_library_and_experiment_ids_cannot_replace_each_others_zip(tmp_path):
    first_bytes, second_bytes = _test_bundle("first"), _test_bundle("second")
    first = retain_library_bundle(tmp_path, "a-b", "c", first_bytes)
    second = retain_library_bundle(tmp_path, "a", "b-c", second_bytes)
    assert first["retained_zip"] != second["retained_zip"]
    for row, expected in ((first, first_bytes), (second, second_bytes)):
        stored = (tmp_path / row["retained_zip"]).read_bytes()
        assert stored == expected
        assert check_bundle(stored)["sha256"] == row["sha256"]
    with pytest.raises(FileExistsError):
        retain_library_bundle(tmp_path, "a-b", "c", second_bytes)
    assert (tmp_path / first["retained_zip"]).read_bytes() == first_bytes
