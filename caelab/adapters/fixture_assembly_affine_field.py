"""Internal S4a AnalysisAdapter over the original qualified coarse assembly.

The operator supplies a trusted bundle object; settings cannot select arbitrary
paths, change the frozen case, remesh or enable contacts. Root owns admission
through Lab injection and the later actual native qualification.
"""
from __future__ import annotations

from pathlib import Path

from . import fixture_assembly_native_import as transport
from . import fixture_assembly_mesh_reuse as reuse
from .fixture_assembly_affine_field_worker import parse_native_fields, qualified_volumes
from plugins.fixture_design.assembly_field_reference import canonical_settings, validate_settings
from plugins.fixture_design.assembly_field_comparison import compare_fields


_WORKER = "fixture_assembly_affine_field_worker.py"
_CAPSULE = (_WORKER, "codeaster_worker.py", "fixture_assembly_native_import_worker.py",
            "fixture_assembly_field_geometry.py", "assembly_mesh.py", "assembly_field_reference.py")
_PENDING = ["physical_material_qualification", "fixture_contact_and_load_path",
            "fixture_fastening_and_mounting", "machine_requirements", "physical_strength",
            "durability", "compiled_image_source_equivalence"]


def source_files():
    base = Path(__file__).resolve().parent
    domain = base.parent.parent / "plugins" / "fixture_design"
    return transport.source_files() | {
        "fixture_assembly_affine_field.py": Path(__file__).resolve(),
        _WORKER: base / _WORKER,
        "fixture_assembly_field_geometry.py": base / "fixture_assembly_field_geometry.py",
        "assembly_mesh.py": domain / "assembly_mesh.py",
        "assembly_field_reference.py": domain / "assembly_field_reference.py",
        "assembly_field_comparison.py": domain / "assembly_field_comparison.py",
    }


def _source_pins():
    return {name: transport._entry(path) for name, path in source_files().items()}


class FixtureAssemblyAffineFieldAdapter:
    backend = "fixture.assembly_affine_field.code_aster"
    version = "1"
    analysis_type = "linear_static"
    default_metrics = list(canonical_settings()["limits"])

    def __init__(self, bundle):
        if type(bundle) is not transport.QualifiedAssemblyMeshBundle:
            raise TypeError("Independently trusted QualifiedAssemblyMeshBundle object required")
        self.bundle = bundle

    def solve(self, parent_result, parent_root, output, settings):
        """Append to a fresh child, preserving complete native/partial artifacts."""
        settings = validate_settings(settings)
        root = reuse._absolute(output)
        if root.exists() and (not root.is_dir() or any(root.iterdir())):
            raise ValueError("Fresh empty affine child output required")
        sources, budgets = _source_pins(), transport._budgets()
        root.mkdir(parents=True, exist_ok=True)
        captured, checked, attempted, returned = False, False, False, False
        provenance = {"adapter": self.backend, "adapter_version": self.version,
                      "scope": "S4a_SYNTHETIC_AFFINE_NUMERICAL_PATCH", "source_files": sources,
                      "material": settings["material"], "execution_settings": settings,
                      "decision": "NOT_RELEASED", "budgets": budgets}
        known = {}
        try:
            descriptor = self.bundle.capture(parent_result, parent_root, root / "mesh-reuse")
            captured = True
            capture = root / "mesh-reuse"
            receipt = reuse._json(transport._bytes(capture, descriptor["receipt"]["path"],
                {key: descriptor["receipt"][key] for key in ("sha256", "size_bytes")}))
            if receipt["profile"].get("mesh_size_mm") != 3.0 or receipt["profile"].get("name") != "coarse3":
                raise ValueError("S4a requires the retained original qualified coarse3 mesh")
            original_pin, mapping_pin, quality_pin = (receipt["output_files"][name]
                for name in ("mesh.msh", "mapping.json", "quality.json"))
            mapping = reuse._json(transport._bytes(capture, "mapping.json", mapping_pin))
            quality = reuse._json(transport._bytes(capture, "quality.json", quality_pin))
            qualified_volumes(quality, settings["components"])
            original = transport._bytes(capture, "mesh.msh", original_pin)
            mesh_bytes, transform = transport.transport_msh(original, mapping)
            if transform["source_entry"] != original_pin:
                raise ValueError("Original mesh pin differs from transport source")
            image, image_pin, executable, executable_pin = transport._image_identity()
            for folder in ("native", "capsule", "preferences", "scratch"):
                (root / folder).mkdir(exist_ok=False)
            native = root / "native"
            with (native / "mesh-transport.msh").open("xb") as stream:
                stream.write(mesh_bytes)
            native_sources = {}
            files = source_files()
            for name in _CAPSULE:
                data = transport._bytes(files[name].parent, files[name].name, sources[name])
                with (root / "capsule" / name).open("xb") as stream:
                    stream.write(data)
                native_sources[name] = transport._entry(root / "capsule" / name)
            config = {"schema_version": 1, "settings": settings, "mesh_revision": receipt["mesh_revision"],
                      "parent": receipt["parent"], "profile": receipt["profile"],
                      "original_mesh_entry": original_pin, "mapping_entry": mapping_pin,
                      "quality_entry": quality_pin, "transport_entry": transform["transport_entry"],
                      "native_sources": native_sources}
            input_pin = transport._save(native, "input.json", config)
            transport._save(root, "transport.json", transform)
            provenance.update({"reuse": descriptor, "mesh_revision": receipt["mesh_revision"],
                "cad_parent": receipt["parent"], "original_mesh_entry": original_pin,
                "mapping_entry": mapping_pin, "quality_entry": quality_pin,
                "native_sources": native_sources, "input_entry": input_pin,
                "image": {"path": str(image), **image_pin},
                "container_runtime": {"path": str(executable), **executable_pin},
                "compiled_image_source_equivalence": "UNKNOWN"})
            transport._save(root, "intent.json", provenance | {
                "solver_status": "NOT_RUN", "converged": None, "OMP_NUM_THREADS": 1,
                "contacts": "NONE", "ties": "NONE", "external_forces": "NONE",
                "boundary": "ALL_VERIFIED_EXTERIOR_NODES_ONLY_INTERIOR_FREE"})
            comm = ("from pathlib import Path\nimport hashlib\n"
                    f"p=Path('/work/capsule/{_WORKER}')\nb=p.read_bytes()\n"
                    f"assert hashlib.sha256(b).hexdigest()=={native_sources[_WORKER]['sha256']!r} and len(b)=={native_sources[_WORKER]['size_bytes']}\n"
                    "ns={'__file__':str(p),'__name__':'_affine_bootstrap','__package__':''}\n"
                    "exec(compile(b,str(p),'exec',dont_inherit=True),ns)\n"
                    "ns['bootstrap']('/work/native/input.json')\n")
            with (native / "affine.comm").open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(comm)
            export = (f"P actions make_etude\nP memory_limit {budgets['solver_memory_mb']}\n"
                      f"P time_limit {budgets['solver_time_seconds']}\nP mpi_nbcpu 1\nP ncpus 1\n"
                      "F comm /work/native/affine.comm D 1\nF mmed /work/native/mesh-transport.msh D 20\n"
                      "F mess /work/native/aster.mess R 6\nF resu /work/native/aster.resu R 8\n"
                      "F rmed /work/native/fields.med R 80\n")
            with (native / "affine.export").open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(export)
            for name in ("native/input.json", "native/mesh-transport.msh", "native/affine.comm",
                         "native/affine.export", "transport.json", "intent.json",
                         *("capsule/" + name for name in _CAPSULE)):
                known[name] = transport._entry(root / name)

            def recheck():
                if (_source_pins() != sources or transport._entry(image) != image_pin or
                        transport._entry(executable) != executable_pin):
                    raise ValueError("Controller source/image/runtime drift")
                for name, pin in known.items():
                    transport._bytes(root, name, pin)

            recheck()
            container_version = transport._owned_process([str(executable), "--version"], native,
                "container-version", timeout=budgets["subprocess_timeout_seconds"])
            transport._save(root, "container-version.json", {"observed": container_version})
            self.bundle.recheck(capture)
            recheck()
            command = [str(executable), "exec", "--cleanenv", "--containall", "--no-home", "--env", "OMP_NUM_THREADS=1",
                "--bind", str(root) + ":/work:rw", "--bind", str(root / "preferences") + ":" + str(Path.home()) + ":rw",
                "--bind", str(root / "scratch") + ":/tmp:rw", "--pwd", "/work", str(image),
                "/bin/bash", "--noprofile", "--norc", "-c", 'source /opt/activate.sh; exec run_aster "$1"',
                "caelab-assembly-affine", "/work/native/affine.export"]
            attempted = True
            transport._owned_process(command, native, "native-affine", timeout=budgets["subprocess_timeout_seconds"])
            returned = True
            recheck()
            raw_pin = transport._entry(native / "worker-result.json")
            raw = reuse._json(transport._bytes(native, "worker-result.json", raw_pin))
            if (type(raw.get("schema_version")) is not int or raw["schema_version"] != 1 or
                    raw.get("status") != "AFFINE_NATIVE_OBSERVED_NOT_COMPARED" or
                    raw.get("input_entry") != input_pin or raw.get("native_sources") != native_sources or
                    raw.get("mesh_revision") != config["mesh_revision"] or raw.get("parent") != config["parent"] or
                    raw.get("profile") != config["profile"] or raw.get("transport_entry") != config["transport_entry"] or
                    raw.get("decision") != "NOT_RELEASED"):
                raise ValueError("Native result/source/input/parent/mesh identity differs")
            runtime_pins = {name: transport._entry(native / name) for name in ("runtime-before.json", "runtime-after.json")}
            before, after = (reuse._json(transport._bytes(native, name, runtime_pins[name]))
                             for name in ("runtime-before.json", "runtime-after.json"))
            if (before != raw["runtime_before"] or after != raw["runtime_after"] or before != after or
                    before.get("versions", {}).get("code_aster") != "17.4.0"):
                raise ValueError("Observed native runtime records differ")
            catalog_pin = reuse._pin(raw["catalog_entry"]).value()
            catalog = reuse._json(transport._bytes(native, "native-catalog.json", catalog_pin))
            observed_outputs = {"worker-result.json": raw_pin, "native-catalog.json": catalog_pin} | runtime_pins
            for name in ("DEPL", "REAC_NODA", "SIEF_ELGA", "COOR_ELGA"):
                pin = reuse._pin(raw["table_entries"][name]).value()
                table = reuse._json(transport._bytes(native, name.lower() + ".table.json", pin))
                if table != raw["tables"][name]:
                    raise ValueError("Embedded native field differs from retained original table")
                observed_outputs[name.lower() + ".table.json"] = pin
            for component in settings["components"]:
                path = "energy-" + component + ".table.json"
                pin = transport._entry(native / path)
                if reuse._json(transport._bytes(native, path, pin)) != raw["native_energy"][component]:
                    raise ValueError("Native energy differs from retained original table")
                observed_outputs[path] = pin
            fields = parse_native_fields(raw, mapping, catalog, quality, settings)
            comparison = compare_fields(settings, fields)
            fields_pin = transport._save(root, "admitted-fields.json", fields)
            comparison_pin = transport._save(root, "comparison.json", comparison)
            known["admitted-fields.json"], known["comparison.json"] = fields_pin, comparison_pin
            provenance.update({"native_runtime": before, "container_version": container_version,
                "worker_result_entry": raw_pin, "native_catalog_entry": catalog_pin,
                "comparison_entry": comparison_pin, "geometry_checks": fields["geometry_checks"],
                "geometry_order_binding": fields["geometry_order_binding"]})
            self.bundle.recheck(capture)
            checked = True
            recheck()
            for name, pin in observed_outputs.items():
                transport._bytes(native, name, pin)
            provenance["admitted_native_observation_entries"] = observed_outputs
            provenance["retained_native_files"] = {p.relative_to(root).as_posix(): transport._entry(p)
                                                   for p in sorted(native.iterdir()) if p.is_file()}
            outcome = {"status": "COMPLETED" if comparison["status"] == "PASS" else "REJECTED",
                "solver_status": "COMPLETED", "converged": True,
                "checks": [{"code": "assembly_import_identity_before_meca", "status": "PASS"},
                           {"code": "full_native_fields_and_curved_point_identity", "status": "PASS"}] + comparison["checks"],
                "metrics": comparison["metrics"], "pending_validations": list(_PENDING),
                "provenance": provenance, "raw_result": "simulation/comparison.json"}
            if comparison["status"] != "PASS" and not any(c["status"] == "FAIL" for c in outcome["checks"]):
                outcome["checks"].append({"code": "native_fields_not_fully_qualified", "status": "FAIL",
                                          "detail": "Required native energy is UNKNOWN; numerical admission blocked"})
            transport._save(root, "adapter-outcome.json", outcome)
            return outcome
        except Exception as error:
            failure = {"status": "REJECTED", "error": type(error).__name__ + ": " + str(error),
                       "native_execution_attempted": attempted, "native_process_returned": returned,
                       "numerical_verdict": "UNKNOWN", "decision": "NOT_RELEASED", "provenance": provenance}
            transport._save(root, "failure.json", failure)
            return {"status": "REJECTED", "solver_status": "UNKNOWN" if returned else
                    "FAILED_EXECUTION" if attempted else "NOT_RUN", "converged": None,
                "checks": [{"code": "assembly_affine_admission", "status": "FAIL", "observed": failure["error"]}],
                "metrics": {"native_field_admission": {"value": None, "unit": "1", "valid": False,
                                                       "reason": failure["error"]}},
                "pending_validations": list(_PENDING), "provenance": provenance,
                "raw_result": "simulation/failure.json"}
        finally:
            if captured and not checked:
                # A same-object recheck is also required after partial failure.
                self.bundle.recheck(root / "mesh-reuse")
