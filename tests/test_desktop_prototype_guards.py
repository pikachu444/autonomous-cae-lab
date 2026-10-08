"""Portable refusal checks for the bounded native application prototypes."""
import copy
import json
from pathlib import Path
import runpy
import sys
import types

import pytest

from apps.desktop_post.prepare import validate_fixture_pair


def test_fixture_labels_reject_swapped_or_different_metadata():
    a = {"force_N": 150, "backend": "fixture.calculix",
         "versions": {"ccx": "This is Version 2.21"},
         "static": {"step": 1, "increment": 1, "load_parameter": 1.0},
         "decision": "NOT_RELEASED"}
    b = {**a, "force_N": 200}
    validate_fixture_pair(a, b)
    with pytest.raises(ValueError, match="Source A"):
        validate_fixture_pair(b, b)
    for key, value in (("versions", {"ccx": "This is Version 2.22"}),
                       ("static", {"step": 2, "increment": 1, "load_parameter": 1.0}),
                       ("decision", "RELEASED")):
        changed = copy.deepcopy(b)
        changed[key] = value
        with pytest.raises(ValueError, match="Source B"):
            validate_fixture_pair(a, changed)


@pytest.mark.parametrize("existing", [False, True])
def test_native_failure_receipt_only_in_new_owned_output(tmp_path, monkeypatch, existing):
    for name in ("FreeCAD", "ObjectsFem", "femmesh", "femmesh.gmshtools"):
        module = types.ModuleType(name)
        if name == "femmesh.gmshtools":
            module.GmshTools = object
        monkeypatch.setitem(sys.modules, name, module)
    output = tmp_path / "verification"
    if existing:
        output.mkdir()
        (output / "failure.txt").write_bytes(b"historical failure\n")
        (output / "evidence.bin").write_bytes(b"historical evidence")
    before = {p.name: p.read_bytes() for p in output.iterdir()} if existing else {}
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"output": str(output), "source": str(tmp_path / "missing.FCStd")}), encoding="utf-8")
    monkeypatch.setenv("CAE_PRE_VERIFY_CONFIG", str(config))
    script = Path(__file__).resolve().parents[1] / "apps/desktop_pre/verify_native.py"
    with pytest.raises(FileExistsError if existing else FileNotFoundError):
        runpy.run_path(str(script))
    if existing:
        assert {p.name: p.read_bytes() for p in output.iterdir()} == before
    else:
        assert "FileNotFoundError" in (output / "failure.txt").read_text(encoding="utf-8")
