"""Headless acceptance of retained-data fidelity and native analysis save/reopen.

Use ParaView's pvpython --force-offscreen-rendering. This is not GUI acceptance.
Writes only a fresh verification directory and appended analysis revisions.
"""
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paraview import simple as p, servermanager
import commands


def main():
    project_path = Path(sys.argv[1]).resolve(strict=True)
    os.environ["CAE_POST_PROJECT"] = str(project_path)
    os.environ["CAE_POST_HOME"] = str(Path(__file__).resolve().parent)
    output = project_path.parent / ("verification-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6])
    output.mkdir(exist_ok=False)
    commands.restore_workspace()
    _, doc = commands.verify_sources()
    source_hashes = {pin["path"]: commands.sha(pin["path"]) for item in doc["sources"].values() for pin in item["source_pins"]}
    original_project_hash = commands.sha(project_path)
    # Native Properties can change FileName without changing the reader label.
    # All retained metadata must be rejected before a probe or saved revision.
    swapped_readers_rejected = []
    swaps = [("A | 150 N | native U [mm]", "B"), ("B | 200 N | native U [mm]", "A")]
    if "view_file" in doc["comparison"]:
        swaps.append(("Derived | B - A | exact matched IDs", "A"))
    saved_root = Path(doc.get("project_root", project_path.parent)) / "saved"
    before_saved = set(saved_root.iterdir()) if saved_root.exists() else set()
    for reader_name, other_key in swaps:
        reader = p.FindSource(reader_name)
        original_files = list(reader.FileName)
        replacement = doc["sources"][other_key]
        try:
            reader.FileName = [str(replacement.get("view_path", project_path.parent / replacement["view_file"]))]
            reader.UpdatePipeline()
            commands.verify_sources()  # Unchanged disk artifacts alone still pass.
            for operation in (commands.exact_peak_probe, commands.save_project):
                try:
                    operation()
                except RuntimeError as error:
                    assert "Retained reader path mismatch" in str(error)
                else:
                    raise AssertionError(operation.__name__ + " accepted a swapped retained reader")
            swapped_readers_rejected.append(reader_name)
        finally:
            reader.FileName = original_files
            reader.UpdatePipeline()
    assert (set(saved_root.iterdir()) if saved_root.exists() else set()) == before_saved
    commands.verify_retained_readers(project_path, doc)
    commands.show_component("UZ")
    commands.show_component("Magnitude")
    p.SetActiveSource(commands.candidate())
    commands.new_slice()
    created_slice = p.GetActiveSource()
    assert created_slice.GetDataInformation().GetNumberOfCells() > 0
    forbidden = {"NativeNodeId", "NativeElementId", "FixedXYZ_input", "LoadedNode_input"}
    for sampled in (created_slice, p.FindSource("Section | B | plane X = 0 mm"), p.FindSource("Line probe | B | spatial interpolation")):
        sampled.UpdatePipeline()
        assert not forbidden.intersection(sampled.PointData.keys())
        assert not forbidden.intersection(sampled.CellData.keys())
        assert "U_mm" in sampled.PointData.keys()
    commands.exact_peak_probe()
    extraction = p.GetActiveSource()
    probe_data = servermanager.Fetch(extraction)
    assert probe_data.GetNumberOfPoints() == 1
    assert probe_data.GetPointData().GetArray("NativeNodeId").GetValue(0) == doc["exact_probe"]["node_id"]
    assert list(probe_data.GetPointData().GetArray("U_mm").GetTuple3(0)) == doc["exact_probe"]["displacement_mm"]
    comparison_checked = False
    if doc["comparison"]["status"] != "BLOCKED":
        delta = servermanager.Fetch(p.FindSource("Derived | B - A | exact matched IDs"))
        a = json.loads(Path(doc["sources"]["A"]["field_path"]).read_text(encoding="utf-8"))
        b = json.loads(Path(doc["sources"]["B"]["field_path"]).read_text(encoding="utf-8"))
        for component, label in enumerate(("UX", "UY", "UZ")):
            absolute = delta.GetPointData().GetArray("Delta_" + label + "_mm")
            relative = delta.GetPointData().GetArray("Relative_" + label + "_percent")
            mask = delta.GetPointData().GetArray("Relative_" + label + "_valid")
            for index, (na, nb) in enumerate(zip(a["nodes"], b["nodes"])):
                baseline = na["displacement_mm"][component]
                difference = nb["displacement_mm"][component] - baseline
                assert absolute.GetValue(index) == difference
                assert mask.GetValue(index) == int(baseline != 0)
                if baseline == 0:
                    assert math.isnan(relative.GetValue(index))
                else:
                    assert relative.GetValue(index) == 100 * difference / abs(baseline)
        comparison_checked = True
    # A native legacy reader uses FileNames, not FileName. Its input must be
    # discovered by ParaView metadata and pinned without a reader-specific map.
    legacy_file = output / "external-reader-test.vtk"
    legacy_text = "# vtk DataFile Version 3.0\nSynthetic reader integrity test\nASCII\nDATASET POLYDATA\nPOINTS 1 float\n0 0 0\nVERTICES 1 2\n1 0\n"
    legacy_file.write_text(legacy_text, encoding="utf-8")
    legacy = p.LegacyVTKReader(registrationName="Verification | external legacy reader", FileNames=[str(legacy_file)])
    legacy.UpdatePipeline()
    assert legacy.GetDataInformation().GetNumberOfPoints() == 1
    saved = commands.save_project()
    saved_doc = json.loads(saved.read_text(encoding="utf-8"))
    assert saved_doc["native_reader_files"][str(legacy_file)] == commands.sha(legacy_file)
    p.ResetSession()
    os.environ["CAE_POST_PROJECT"] = str(saved)
    commands.restore_workspace()
    p.FindSource("Saved probe | B | native node " + str(doc["exact_probe"]["node_id"])).UpdatePipeline()
    reopened_probe = servermanager.Fetch(p.FindSource("Saved probe | B | native node " + str(doc["exact_probe"]["node_id"])))
    assert reopened_probe.GetNumberOfPoints() == 1
    assert list(reopened_probe.GetPointData().GetArray("U_mm").GetTuple3(0)) == doc["exact_probe"]["displacement_mm"]
    legacy_changed_rejected = False
    try:
        legacy_file.write_text(legacy_text + "\n", encoding="utf-8")
        try:
            commands.restore_workspace()
        except RuntimeError as error:
            assert "Saved analysis reader input changed" in str(error)
            legacy_changed_rejected = True
        assert legacy_changed_rejected
    finally:
        legacy_file.write_text(legacy_text, encoding="utf-8")
    # A self-consistent state hash cannot bless a B reader pointed at A. Restore
    # must check the loaded native reader after checking the manifest/files.
    reader = commands.candidate()
    original_files = list(reader.FileName)
    try:
        reader.FileName = [saved_doc["sources"]["A"]["view_path"]]
        bad_state = output / "swapped-reader.pvsm"
        p.SaveState(str(bad_state))
    finally:
        reader.FileName = original_files
    swapped_doc = dict(saved_doc, workspace_file=bad_state.name, workspace_sha256=commands.sha(bad_state))
    bad_project = output / "swapped-reader-project.json"
    bad_project.write_text(json.dumps(swapped_doc), encoding="utf-8")
    os.environ["CAE_POST_PROJECT"] = str(bad_project)
    p.ResetSession()
    swapped_restore_rejected = False
    try:
        commands.restore_workspace()
    except RuntimeError as error:
        assert "Retained reader path mismatch" in str(error)
        swapped_restore_rejected = True
    assert swapped_restore_rejected
    p.ResetSession()
    os.environ["CAE_POST_PROJECT"] = str(saved)
    commands.restore_workspace()
    # Invalid source metadata must be rejected before loading any visualization.
    damaged = json.loads(saved.read_text(encoding="utf-8"))
    damaged["sources"]["B"]["source_pins"][0]["sha256"] = "0" * 64
    negative = output / "invalid-project.json"
    negative.write_text(json.dumps(damaged), encoding="utf-8")
    os.environ["CAE_POST_PROJECT"] = str(negative)
    rejected = False
    try:
        commands.verify_sources()
    except RuntimeError:
        rejected = True
    assert rejected
    os.environ["CAE_POST_PROJECT"] = str(saved)
    assert commands.sha(project_path) == original_project_hash
    assert all(commands.sha(path) == digest for path, digest in source_hashes.items())
    report = {"status": "PASS", "gui_verified": False, "saved_project": str(saved),
              "component_commands": ["UZ", "Magnitude"], "slice_nonempty": True,
              "exact_probe_node_id": doc["exact_probe"]["node_id"], "exact_probe_displacement_mm": doc["exact_probe"]["displacement_mm"],
              "all_difference_and_relative_values_checked": comparison_checked,
              "zero_denominator_masks_checked": comparison_checked, "source_hash_mismatch_rejected": rejected,
              "changed_retained_reader_probe_and_save_rejected": swapped_readers_rejected,
              "changed_retained_reader_restore_rejected": swapped_restore_rejected,
              "native_legacy_FileNames_input_pinned_and_change_rejected": legacy_changed_rejected,
              "interpolated_outputs_have_no_native_identity_or_input_classification": True,
              "saved_probe_reopened": True, "original_project_and_source_files_unchanged": True}
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(output / "report.json"), **report}))


if __name__ == "__main__":
    main()
