"""Pinned assembly S4a worker and strict, standard-library field admission.

Code_Aster is imported only inside run_affine. The imported mesh is compared
body by body before modelling, and that same object receives exterior-only U.
All oracle coordinates/weights are labelled derived and never replace native
observations. Source/API controls are not native acceptance.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import sys
from types import ModuleType

if __package__:
    from . import codeaster_worker as foundation
    from . import fixture_assembly_native_import_worker as importer
    from .fixture_assembly_field_geometry import exterior_nodes, tetra10_gauss


def body_layout(mapping, catalog, components):
    """Use actual imported group indices; never merge coincident body nodes."""
    source = importer.source_catalog(mapping)
    if set(source["bodies"]) != set(components):
        raise ValueError("Frozen seven-body component scope differs")
    bodies = []
    for component in components:
        volume = source["bodies"][component]
        faces = sorted(name for name, group in source["groups"].items()
                       if group["dim"] == 2 and group["component_id"] == component)
        bodies.append({"component_id": component,
                       "volume_cell_indices": sorted(catalog["group_cell_indices"][volume]),
                       "face_cell_indices": sorted(i for name in faces
                                                    for i in catalog["group_cell_indices"][name])})
    boundary = exterior_nodes(catalog["cells"], bodies)
    return source, bodies, boundary


def qualified_volumes(quality, components):
    if quality.get("status") != "PASS" or len(quality["bodies"]) != len(components):
        raise ValueError("Qualified original per-body mesh volumes required")
    values = {}
    for body in quality["bodies"]:
        component = body["component_id"]
        value = foundation._finite(body["integrated_mesh_volume_mm3"], "qualified mesh volume")
        if component in values or component not in components or value <= 0 or body["status"] != "PASS":
            raise ValueError("Incomplete/invalid qualified per-body mesh volume")
        values[component] = value
    return values


def _context(raw, order, volumes):
    if (type(order) is not int or order <= 0 or raw.get("available_orders") != [order] or
            raw.get("solver_status") != "COMPLETED" or raw.get("converged") is not True or
            raw.get("geometry_context") != {
                "basis": "CHAM_GD from CALC_CHAM_ELEM on the same imported model",
                "result_order_binding": "DERIVED_COMMAND_CONTEXT_NOT_NATIVE_GEOMETRY_ORDER",
                "selected_result_order": order, "volume_groups": volumes}):
        raise ValueError("Actual single result/geometry context differs")
    access = raw["access_parameters"]
    if (access.get("NUME_ORDRE") != [order] or not isinstance(access.get("INST"), list) or
            len(access["INST"]) != 1 or foundation._finite(access["INST"][0], "actual INST") != 0.0):
        raise ValueError("Actual result access parameters do not bind the frozen static instant")


def _native_energy(observation, volume_group, order):
    """Unsupported native columns stay UNKNOWN, without a substituted energy."""
    if not isinstance(observation, dict) or observation.get("status") != "OBSERVED":
        return {"status": "UNKNOWN", "value_n_mm": None,
                "reason": (observation or {}).get("reason", "Native energy table unavailable")}
    try:
        if observation["selection"] != {"GROUP_MA": volume_group, "NUME_ORDRE": order,
                                        "option": "ENER_POT"}:
            raise ValueError("Native energy command selection differs")
        table, count = foundation._table(observation["table"], ("TOTALE", "NUME_ORDRE", "LIEU"), "ENER_POT")
        if count != 1:
            raise ValueError("Native body energy table is not exactly one selected row")
        foundation._field_order(table, 0, order, "ENER_POT")
        if foundation._name(table["LIEU"][0], "energy LIEU") != volume_group:
            raise ValueError("Native energy LIEU does not identify its volume group")
        value = foundation._finite(table["TOTALE"][0], "native TOTALE energy")
        if value <= 0:
            raise ValueError("Native body energy must be positive")
        return {"status": "OBSERVED", "value_n_mm": value,
                "basis": "NATIVE_POST_ELEM_ENER_POT_TOTALE", "volume_group": volume_group,
                "order": order, "raw_table_retained": True}
    except (ValueError, KeyError, TypeError) as error:
        return {"status": "UNKNOWN", "value_n_mm": None, "reason": str(error)}


def parse_native_fields(raw, mapping, catalog, quality, settings):
    """Join every actual decimal internal ID, order and FPG5 location exactly."""
    from plugins.fixture_design.assembly_field_reference import validate_settings
    settings = validate_settings(settings)
    # The host repeats the worker's pre-MECA body/order/group guard independently.
    comparison = importer.validate_native_catalog(mapping, catalog)
    source, body_cells, boundary = body_layout(mapping, catalog, settings["components"])
    volumes = [source["bodies"][component] for component in settings["components"]]
    order = raw["order"]
    _context(raw, order, volumes)
    if raw.get("boundary") != boundary or raw.get("identity_verified_before_model") is not True:
        raise ValueError("Observed exterior-only boundary/pre-MECA identity differs")
    mesh_volumes = qualified_volumes(quality, settings["components"])
    xyz = catalog["coordinates_mm"]
    cells = {cell["index"]: cell for cell in catalog["cells"]}
    node_owner, cell_owner = {}, {}
    for component in settings["components"]:
        group = source["bodies"][component]
        for node in catalog["group_node_indices"][group]:
            if node in node_owner:
                raise ValueError("Native node shared between admitted bodies")
            node_owner[node] = component
        for cell in catalog["group_cell_indices"][group]:
            cell_owner[cell] = component
    tables = raw["tables"]

    def nodal(name):
        table, count = foundation._table(tables[name],
            ("NOEUD", "NUME_ORDRE", *foundation.COORDINATE_COMPONENTS, *foundation.VECTOR_COMPONENTS), name)
        if count != len(xyz):
            raise ValueError("Every native body node required in " + name)
        values = {}
        for row in range(count):
            index = foundation._table_identifier(table["NOEUD"][row], name) - 1
            if index not in node_owner or index in values:
                raise ValueError("Duplicate/foreign actual native node in " + name)
            foundation._field_order(table, row, order, name)
            coords = [foundation._finite(table[k][row], name + " XYZ") for k in foundation.COORDINATE_COMPONENTS]
            if max(abs(a-b) for a, b in zip(coords, xyz[index])) > importer.COORDINATE_ABSOLUTE_MM:
                raise ValueError("Actual nodal table coordinates differ from imported mesh")
            values[index] = [foundation._finite(table[k][row], name + " vector") for k in foundation.VECTOR_COMPONENTS]
        if set(values) != set(node_owner):
            raise ValueError("Incomplete native nodal scope")
        return values

    displacement, reaction = nodal("DEPL"), nodal("REAC_NODA")
    stresses, count = foundation._table(tables["SIEF_ELGA"],
        ("MAILLE", "POINT", "SOUS_POINT", "NUME_ORDRE", *foundation.COORDINATE_COMPONENTS,
         *foundation.STRESS_COMPONENTS), "SIEF_ELGA")
    geometry, geometry_count = foundation._table(tables["COOR_ELGA"],
        ("MAILLE", "POINT", "SOUS_POINT", "X", "Y", "Z", "W"), "COOR_ELGA")
    expected_count = 5 * len(cell_owner)
    if count != expected_count or geometry_count != expected_count:
        raise ValueError("Exactly every TETRA10 times five native locations required")

    def locations(table, rows, label, columns, *, result_order):
        values = {}
        for row in range(rows):
            cell = foundation._table_identifier(table["MAILLE"][row], label) - 1
            point = foundation._identifier(table["POINT"][row], label + " point")
            subpoint = foundation._identifier(table["SOUS_POINT"][row], label + " subpoint")
            key = cell, point, subpoint
            if cell not in cell_owner or point not in (1, 2, 3, 4, 5) or subpoint != 1 or key in values:
                raise ValueError("Duplicate/foreign/wrong native cell-point-subpoint in " + label)
            if result_order:
                foundation._field_order(table, row, order, label)
            values[key] = [foundation._finite(table[col][row], label + " " + col) for col in columns]
        if set(values) != {(cell, point, 1) for cell in cell_owner for point in range(1, 6)}:
            raise ValueError("Missing full native cell-point-subpoint scope")
        return values

    stress_rows = locations(stresses, count, "SIEF_ELGA",
                             (*foundation.COORDINATE_COMPONENTS, *foundation.STRESS_COMPONENTS), result_order=True)
    geometry_rows = locations(geometry, geometry_count, "COOR_ELGA", ("X", "Y", "Z", "W"), result_order=False)
    body_results = {component: {"nodes": [], "gauss": [],
        "qualified_mesh_volume_mm3": mesh_volumes[component],
        "native_energy": _native_energy(raw.get("native_energy", {}).get(component),
                                        source["bodies"][component], order)} for component in settings["components"]}
    exterior = {row["component_id"]: set(row["exterior_node_indices"]) for row in boundary}
    for index in range(len(xyz)):
        component = node_owner[index]
        body_results[component]["nodes"].append({"native_index": index,
            "source_node_id": comparison["source_node_ids_by_native_index"][index],
            "xyz_mm": xyz[index], "displacement_mm": displacement[index], "reaction_n": reaction[index],
            "exterior": index in exterior[component]})
    maximum_xyz_error, maximum_weight_error = 0.0, 0.0
    for cell in sorted(cell_owner):
        component = cell_owner[cell]
        expectations = tetra10_gauss([xyz[index] for index in cells[cell]["node_indices"]])
        for expected in expectations:
            point, subpoint = expected["point"], 1
            native_geom, native_stress = geometry_rows[cell, point, subpoint], stress_rows[cell, point, subpoint]
            if expected["signed_jacobian_mm3"] <= 0:
                raise ValueError("Invalid nonpositive derived curved-element Jacobian retained")
            coordinate_error = max(abs(a-b) for a, b in zip(native_geom[:3], expected["xyz_mm"]))
            metadata_error = max(abs(a-b) for a, b in zip(native_stress[:3], native_geom[:3]))
            expected_weight = expected["native_expected_weight_mm3"]
            weight_error = abs(native_geom[3]-expected_weight) / abs(expected_weight)
            if (max(coordinate_error, metadata_error) > importer.COORDINATE_ABSOLUTE_MM or
                    weight_error > settings["limits"]["mesh_volume_relative"]):
                raise ValueError("Native spatial point order/curved geometry/signed weight differs from frozen source rule")
            maximum_xyz_error = max(maximum_xyz_error, coordinate_error, metadata_error)
            maximum_weight_error = max(maximum_weight_error, weight_error)
            body_results[component]["gauss"].append({"native_cell_index": cell,
                "source_element_id": comparison["source_element_ids_by_native_index"][cell],
                "point": point, "subpoint": subpoint, "order": order,
                "xyz_mm": native_geom[:3], "weight_mm3": native_geom[3], "stress6_mpa": native_stress[3:],
                "derived_geometry_reference": expected})
    return {"scope": "COMPLETE_NATIVE_AFFINE_FIELDS", "bodies": body_results,
            "order": order, "native_import_comparison": comparison,
            "geometry_checks": {"maximum_coordinate_error_mm": maximum_xyz_error,
                                "coordinate_absolute_limit_mm": importer.COORDINATE_ABSOLUTE_MM,
                                "maximum_point_weight_relative_error": maximum_weight_error,
                                "point_weight_relative_limit": settings["limits"]["mesh_volume_relative"]},
            "geometry_order_binding": raw["geometry_context"]["result_order_binding"]}


def _pin(data):
    return {"sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}


def _capsule_modules(capsule, pins):
    """Load only independently pinned pure sources; no repository sys.path."""
    packages = ("_affine_capsule", "plugins", "plugins.fixture_design")
    for name in packages:
        if name in sys.modules:
            raise RuntimeError("Unowned preloaded capsule package: " + name)
        module = ModuleType(name)
        module.__path__ = [str(capsule)]
        sys.modules[name] = module
    names = {
        "codeaster_worker.py": "_affine_capsule.codeaster_worker",
        "fixture_assembly_native_import_worker.py": "_affine_capsule.fixture_assembly_native_import_worker",
        "fixture_assembly_field_geometry.py": "_affine_capsule.fixture_assembly_field_geometry",
        "assembly_mesh.py": "plugins.fixture_design.assembly_mesh",
        "assembly_field_reference.py": "plugins.fixture_design.assembly_field_reference",
        "fixture_assembly_affine_field_worker.py": "_affine_capsule.fixture_assembly_affine_field_worker",
    }
    loaded = {}
    for filename, fullname in names.items():
        path, module = capsule / filename, ModuleType(fullname)
        data = path.read_bytes()
        if _pin(data) != pins[filename]:
            raise RuntimeError("Pinned native capsule source drift: " + filename)
        module.__file__, module.__package__ = str(path), fullname.rpartition(".")[0]
        sys.modules[fullname] = module
        exec(compile(data, str(path), "exec", dont_inherit=True), module.__dict__)
        loaded[filename] = module
    return loaded


def bootstrap(input_path):
    """The .comm loads this file without importing host packages."""
    input_file = Path(input_path)
    config = json.loads(input_file.read_bytes())
    modules = _capsule_modules(input_file.parent.parent / "capsule", config["native_sources"])
    return modules["fixture_assembly_affine_field_worker.py"].run_affine(input_path, modules)


def run_affine(input_path, modules):
    """One native import, one same-mesh pre-MECA guard, one affine solve."""
    from code_aster.Commands import (
        AFFE_CHAR_CINE_F, AFFE_MATERIAU, AFFE_MODELE, CALC_CHAM_ELEM, CALC_CHAMP,
        CREA_TABLE, DEBUT, DEFI_GROUP, DEFI_MATERIAU, FIN, FORMULE,
        IMPR_RESU, LIRE_MAILLAGE, MECA_STATIQUE, POST_ELEM,
    )
    from code_aster.Cata.Syntax import _F

    input_file = Path(input_path)
    input_bytes = input_file.read_bytes()
    config = json.loads(input_bytes)
    output, capsule = input_file.parent, input_file.parent.parent / "capsule"
    settings = modules["assembly_field_reference.py"].validate_settings(config["settings"])

    def save(name, value):
        data = json.dumps(foundation._json_safe(value), sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode("utf-8") + b"\n"
        with (output / name).open("xb") as stream:
            stream.write(data)
        return _pin(data)

    def guard_sources():
        if input_file.read_bytes() != input_bytes:
            raise RuntimeError("Native input byte drift")
        for name, pin in config["native_sources"].items():
            if _pin((capsule / name).read_bytes()) != pin:
                raise RuntimeError("Native capsule byte drift: " + name)
        if _pin(Path("fort.20").read_bytes()) != config["transport_entry"]:
            raise RuntimeError("Actual unit20 byte drift")
        for name, key in (("mapping.json", "mapping_entry"), ("quality.json", "quality_entry")):
            if _pin((output.parent / "mesh-reuse" / name).read_bytes()) != config[key]:
                raise RuntimeError("Captured qualified source byte drift: " + name)

    phase = "BEFORE_DEBUT"
    try:
        DEBUT()
        guard_sources()
        versions, runtime = foundation._runtime_versions()
        before = {"versions": versions, "code_aster_runtime": runtime}
        save("runtime-before.json", before)
        if versions.get("code_aster") != "17.4.0":
            raise RuntimeError("Actual native Code_Aster17.4.0 required")
        mapping_bytes = (output.parent / "mesh-reuse" / "mapping.json").read_bytes()
        if _pin(mapping_bytes) != config["mapping_entry"]:
            raise RuntimeError("Captured mapping bytes differ before native import")
        mapping = json.loads(mapping_bytes)
        qualified_volumes(json.loads((output.parent / "mesh-reuse" / "quality.json").read_bytes()),
                          settings["components"])
        phase = "IMPORT"
        mesh = LIRE_MAILLAGE(FORMAT="GMSH", UNITE=20)
        catalog = importer.capture_native_catalog(mesh)
        catalog_pin = save("native-catalog.json", catalog)
        phase = "PRE_MECA_IDENTITY"
        comparison = importer.validate_native_catalog(mapping, catalog)
        save("pre-meca-import-comparison.json", comparison)
        source, _, boundary = body_layout(mapping, catalog, settings["components"])
        save("native-boundary.json", boundary)
        # Node groups add no surface-element stiffness or contact connectivity.
        face_names = sorted(name for name, g in source["groups"].items() if g["dim"] == 2)
        node_names = tuple("N" + name for name in face_names)
        if (set(node_names) | {"AFF_EXT"}) & set(mesh.getGroupsOfNodes()):
            raise RuntimeError("Generated native node-group name collision")
        modified = DEFI_GROUP(reuse=mesh, MAILLAGE=mesh, CREA_GROUP_NO=tuple(
            _F(NOM=node_name, GROUP_MA=face, CRIT_NOEUD="TOUS")
            for face, node_name in zip(face_names, node_names)))
        if modified is not mesh:
            raise RuntimeError("Node-group creation replaced the checked native Mesh object")
        modified = DEFI_GROUP(reuse=mesh, MAILLAGE=mesh,
                              CREA_GROUP_NO=_F(NOM="AFF_EXT", UNION=node_names))
        if modified is not mesh:
            raise RuntimeError("Exterior union replaced the checked native Mesh object")
        expected_exterior = sorted(i for body in boundary for i in body["exterior_node_indices"])
        observed_exterior = list(mesh.getNodes("AFF_EXT"))
        if len(observed_exterior) != len(set(observed_exterior)) or sorted(observed_exterior) != expected_exterior:
            raise RuntimeError("Actual affine boundary is not exactly the topology-verified exterior")
        for face, node_name in zip(face_names, node_names):
            if sorted(mesh.getNodes(node_name)) != sorted(catalog["group_node_indices"][face]):
                raise RuntimeError("Actual generated face node membership differs")
        if (set(mesh.getGroupsOfNodes()) != set(node_names) | {"AFF_EXT"} or
                set(mesh.getGroupsOfCells()) != set(catalog["group_names"]) or
                mesh.getConnectivity() != [c["node_indices"] for c in sorted(catalog["cells"], key=lambda c: c["index"])] or
                mesh.getCoordinates().toNumpy().tolist() != catalog["coordinates_mm"]):
            raise RuntimeError("Native geometry/topology/group identity changed before modelling")
        for group in catalog["group_names"]:
            if sorted(mesh.getCells(group)) != sorted(catalog["group_cell_indices"][group]):
                raise RuntimeError("Native original physical membership changed")
        guard_sources()
        if _pin((output.parent / "mesh-reuse" / "mapping.json").read_bytes()) != config["mapping_entry"]:
            raise RuntimeError("Mapping drift before MECA")
        volumes = [source["bodies"][component] for component in settings["components"]]
        phase = "MODEL"
        model = AFFE_MODELE(MAILLAGE=mesh, AFFE=_F(GROUP_MA=volumes, PHENOMENE="MECANIQUE", MODELISATION="3D"))
        material = DEFI_MATERIAU(ELAS=_F(E=settings["material"]["youngs_modulus_mpa"],
                                       NU=settings["material"]["poisson_ratio"]))
        material_field = AFFE_MATERIAU(MAILLAGE=mesh, AFFE=_F(GROUP_MA=volumes, MATER=material))
        kinematics = settings["kinematics"]
        formulae = []
        for offset, row in zip(kinematics["translation_mm"], kinematics["gradient"]):
            expression = repr(offset) + "".join(" + (" + repr(value) + ")*" + axis
                                                for value, axis in zip(row, ("X", "Y", "Z")))
            formulae.append(FORMULE(NOM_PARA=("X", "Y", "Z"), VALE=expression))
        boundary_load = AFFE_CHAR_CINE_F(MODELE=model, MECA_IMPO=_F(
            GROUP_NO="AFF_EXT", DX=formulae[0], DY=formulae[1], DZ=formulae[2]))
        phase = "MECA"
        result = MECA_STATIQUE(MODELE=model, CHAM_MATER=material_field, INST=0.0,
                              EXCIT=_F(CHARGE=boundary_load), OPTION="SIEF_ELGA",
                              SOLVEUR=_F(METHODE="MUMPS", STOP_SINGULIER="OUI"))
        result = CALC_CHAMP(reuse=result, RESULTAT=result, FORCE="REAC_NODA")
        orders = list(result.getIndexes())
        if len(orders) != 1 or type(orders[0]) is not int or orders[0] <= 0:
            raise RuntimeError("One actual native static result order required")
        order = orders[0]
        phase = "FIELDS"
        tables, table_entries = {}, {}
        for field, components in (("DEPL", foundation.VECTOR_COMPONENTS),
                                  ("REAC_NODA", foundation.VECTOR_COMPONENTS),
                                  ("SIEF_ELGA", foundation.STRESS_COMPONENTS)):
            selection = {"GROUP_MA": volumes} if field == "SIEF_ELGA" else {"TOUT": "OUI"}
            table = CREA_TABLE(RESU=_F(RESULTAT=result, NOM_CHAM=field,
                                     NUME_ORDRE=order, NOM_CMP=components, **selection))
            tables[field] = table.EXTR_TABLE().values()
            table_entries[field] = save(field.lower() + ".table.json", tables[field])
        geometry = CALC_CHAM_ELEM(MODELE=model, GROUP_MA=volumes, OPTION="COOR_ELGA")
        table = CREA_TABLE(RESU=_F(CHAM_GD=geometry, GROUP_MA=volumes, NOM_CMP=("X", "Y", "Z", "W")))
        tables["COOR_ELGA"] = table.EXTR_TABLE().values()
        table_entries["COOR_ELGA"] = save("coor_elga.table.json", tables["COOR_ELGA"])
        energy = {}
        for component, group in zip(settings["components"], volumes):
            selection = {"GROUP_MA": group, "NUME_ORDRE": order, "option": "ENER_POT"}
            try:
                table = POST_ELEM(RESULTAT=result, NUME_ORDRE=order, ENER_POT=_F(GROUP_MA=group))
                observation = {"status": "OBSERVED", "selection": selection,
                               "table": table.EXTR_TABLE().values()}
            except Exception as error:
                observation = {"status": "UNKNOWN", "selection": selection,
                               "reason": type(error).__name__ + ": " + str(error), "table": None}
            energy[component] = observation
            save("energy-" + component + ".table.json", observation)
        phase = "EXPORT"
        IMPR_RESU(FORMAT="MED", UNITE=80, RESU=(
            _F(RESULTAT=result, NOM_CHAM=("DEPL", "SIEF_ELGA", "REAC_NODA"), NUME_ORDRE=order),
            _F(CHAM_GD=geometry, NOM_CHAM_MED="COOR_ELGA_RAW")))
        versions_after, runtime_after = foundation._runtime_versions()
        after = {"versions": versions_after, "code_aster_runtime": runtime_after}
        save("runtime-after.json", after)
        if before != after:
            raise RuntimeError("Actual native runtime drift during affine execution")
        guard_sources()
        save("worker-result.json", {"schema_version": 1, "status": "AFFINE_NATIVE_OBSERVED_NOT_COMPARED",
            "input_entry": _pin(input_bytes), "native_sources": config["native_sources"],
            "transport_entry": config["transport_entry"], "mesh_revision": config["mesh_revision"],
            "parent": config["parent"], "profile": config["profile"], "catalog_entry": catalog_pin,
            "runtime_before": before, "runtime_after": after, "identity_verified_before_model": True,
            "boundary": boundary, "order": order, "available_orders": orders,
            "access_parameters": result.getAccessParameters(), "table_entries": table_entries,
            "tables": tables, "native_energy": energy,
            "geometry_context": {"basis": "CHAM_GD from CALC_CHAM_ELEM on the same imported model",
                "result_order_binding": "DERIVED_COMMAND_CONTEXT_NOT_NATIVE_GEOMETRY_ORDER",
                "selected_result_order": order, "volume_groups": volumes},
            "solver_status": "COMPLETED", "converged": True, "decision": "NOT_RELEASED",
            "linear_residual": {"value": None, "status": "UNKNOWN", "reason": "No assembled A/u/b exported"}})
        phase = "FIN"
        FIN()
    except Exception as error:
        save("native-failure.json", {"phase": phase, "error": type(error).__name__ + ": " + str(error),
            "numerical_verdict": "UNKNOWN", "decision": "NOT_RELEASED"})
        raise
