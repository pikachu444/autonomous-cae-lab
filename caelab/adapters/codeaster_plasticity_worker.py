"""Pinned 17.4 small-strain J2 worker, isolated from the Lab Python runtime.

Reuse the exercised native mesh guard and table primitives. The added parser
requires complete time/order, displacement, stress, V1 and reaction histories;
native tables remain unchanged evidence, including the initial order zero.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

if __package__:
    from .codeaster_worker import (COORDINATE_COMPONENTS, GAUSS_POINT_IDS,
        STRESS_COMPONENTS, VECTOR_COMPONENTS, _field_order, _finite, _identifier,
        _name, _native_mesh_catalog, _runtime_versions, _save, _table,
        _table_identifier, _vector, validate_native_mesh)
else:
    from codeaster_worker import (COORDINATE_COMPONENTS, GAUSS_POINT_IDS,
        STRESS_COMPONENTS, VECTOR_COMPONENTS, _field_order, _finite, _identifier,
        _name, _native_mesh_catalog, _runtime_versions, _save, _table,
        _table_identifier, _vector, validate_native_mesh)


NONLINEAR_POLICY = {"command": "STAT_NON_LINE", "relation": "VMIS_ISOT_LINE",
    "deformation": "PETIT", "integration": "ANALYTIQUE", "linear_method": "MUMPS",
    "relative_residual_limit": 1e-10, "absolute_residual_limit": 1e-8,
    "maximum_iterations": 40, "archive": "Every declared instant including initial zero",
    "automatic_subdivision": False}


def _order(value: Any) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("Native nonlinear result order must be an actual nonnegative integer")
    return value


def _order_times(access: dict, indexes: list[int], expected_times: list[float]) -> list[tuple[int, float]]:
    if (not isinstance(access, dict) or not isinstance(indexes, list) or
            any(type(index) is not int or index < 0 for index in indexes) or
            len(set(indexes)) != len(indexes) or len(indexes) != len(expected_times)):
        raise ValueError("Incomplete native nonlinear storage indexes")
    orders, times = access.get("NUME_ORDRE"), access.get("INST")
    if (not isinstance(orders, list) or not isinstance(times, list) or
            len(orders) != len(indexes) or len(times) != len(indexes) or
            any(type(index) is not int or index < 0 for index in orders) or
            len(set(orders)) != len(orders) or set(orders) != set(indexes)):
        raise ValueError("Native result access order/time bijection is missing")
    pairs = sorted(zip(orders, [_finite(value, "result instant") for value in times]), key=lambda pair: pair[1])
    if any(actual != expected for (_, actual), expected in zip(pairs, expected_times)):
        raise ValueError("Native result instants differ from the frozen requested history")
    return pairs


def _catalog(catalog: Any) -> tuple[dict[int, list[float]], set[int], dict[str, list[int]]]:
    if not isinstance(catalog, dict):
        raise ValueError("Missing actual native mesh catalogue")
    nodes, elements = catalog.get("nodes"), catalog.get("body_elements")
    if not isinstance(nodes, list) or len(nodes) < 4 or not isinstance(elements, list) or not elements:
        raise ValueError("Incomplete actual native mesh catalogue")
    coordinates = {}
    for item in nodes:
        if not isinstance(item, dict):
            raise ValueError("Malformed actual node catalogue")
        identifier = _identifier(item.get("node_id"), "node id")
        if _table_identifier(item.get("name"), "NOEUD") != identifier or identifier in coordinates:
            raise ValueError("Duplicate or mismatched actual native node id")
        coordinates[identifier] = _vector(item.get("coordinates_mm"), "mesh coordinates")
    body = set()
    for item in elements:
        if not isinstance(item, dict):
            raise ValueError("Malformed actual volume element catalogue")
        identifier = _identifier(item.get("element_id"), "volume element id")
        if _table_identifier(item.get("name"), "MAILLE") != identifier or identifier in body:
            raise ValueError("Duplicate or mismatched actual native BODY id")
        body.add(identifier)
    groups = catalog.get("group_node_ids")
    if not isinstance(groups, dict) or set(groups) != {"X0", "XL", "Y0", "Z0"}:
        raise ValueError("Missing actual boundary node groups")
    for name, identifiers in groups.items():
        if (not isinstance(identifiers, list) or not identifiers or
                any(type(node) is not int or node <= 0 for node in identifiers) or
                len(set(identifiers)) != len(identifiers) or not set(identifiers) <= coordinates.keys()):
            raise ValueError(f"Invalid actual boundary node group: {name}")
    support = catalog.get("support_node_ids")
    if (not isinstance(support, list) or any(type(node) is not int for node in support) or
            len(set(support)) != len(support) or
            set(support) != set(groups["X0"]) | set(groups["Y0"]) | set(groups["Z0"])):
        raise ValueError("Native support union is not the complete deduplicated support set")
    if catalog.get("gauss_point_ids") != list(GAUSS_POINT_IDS):
        raise ValueError("Only the verified TETRA10 five-point RIGI family is supported")
    return coordinates, body, groups


def _nodal(table: Any, order: int, instant: float, coordinates: dict, label: str) -> dict:
    # Pinned CREA_TABLE(RESU=...NUME_ORDRE=...) does not emit INST. The
    # required actual getAccessParameters order/time bijection supplies time;
    # a time column, when explicitly present, must agree rather than be ignored.
    values, count = _table(table, ("NOEUD", "NUME_ORDRE", *COORDINATE_COMPONENTS, *VECTOR_COMPONENTS), label)
    if count != len(coordinates):
        raise ValueError(f"{label} must cover every native node exactly once")
    result = {}
    for row in range(count):
        identifier = _table_identifier(values["NOEUD"][row], label + " NOEUD")
        if identifier not in coordinates or identifier in result:
            raise ValueError(f"Unknown/duplicate node in {label}")
        _field_order(values, row, order, label)
        if "INST" in values and _finite(values["INST"][row], label + " INST") != instant:
            raise ValueError(f"Wrong native instant in {label}")
        observed = [_finite(values[column][row], label + " XYZ") for column in COORDINATE_COMPONENTS]
        if any(not math.isclose(a, b, rel_tol=1e-13, abs_tol=1e-13)
               for a, b in zip(observed, coordinates[identifier])):
            raise ValueError(f"Native {label} node coordinates differ from catalogue")
        result[identifier] = [_finite(values[column][row], label + " component") for column in VECTOR_COMPONENTS]
    return result


def _gauss(table: Any, components: tuple, order: int, instant: float, body: set, label: str) -> dict:
    values, count = _table(table, ("MAILLE", "POINT", "SOUS_POINT", "NUME_ORDRE",
                                  *COORDINATE_COMPONENTS, *components), label)
    if count != len(body) * len(GAUSS_POINT_IDS):
        raise ValueError(f"{label} must cover all five points of every actual BODY TETRA10")
    result = {}
    for row in range(count):
        element = _table_identifier(values["MAILLE"][row], label + " MAILLE")
        point = _identifier(values["POINT"][row], label + " POINT")
        subpoint = _identifier(values["SOUS_POINT"][row], label + " SOUS_POINT")
        key = (element, point, subpoint)
        if element not in body or point not in GAUSS_POINT_IDS or subpoint != 1 or key in result:
            raise ValueError(f"Unknown/duplicate actual BODY point in {label}")
        _field_order(values, row, order, label)
        if "INST" in values and _finite(values["INST"][row], label + " INST") != instant:
            raise ValueError(f"Wrong native instant in {label}")
        result[key] = {"coordinates_mm": [_finite(values[column][row], label + " XYZ") for column in COORDINATE_COMPONENTS],
                       "components": [_finite(values[column][row], label + " component") for column in components]}
    return result


def parse_history_tables(raw: dict, mesh_size_mm: float, times_s: list[float]) -> dict:
    """Parse real indexed histories without interpolating or fabricating states.

    The drive face is also constrained in DX. Its intersection with Y0/Z0
    contributes drive DX reactions, so a vector sum over the support union is
    incorrect. Sum each constrained component over its own verified plane.
    """
    if (not isinstance(raw, dict) or raw.get("schema_version") != "1" or
            raw.get("solver_status") != "COMPLETED" or raw.get("converged") is not True):
        raise ValueError("Incomplete native nonlinear result")
    pairs = _order_times(raw.get("access_parameters"), raw.get("available_orders"), times_s)
    coordinates, body, groups = _catalog(raw.get("mesh"))
    observed_states = raw.get("states")
    if not isinstance(observed_states, list) or len(observed_states) != len(pairs):
        raise ValueError("Missing complete native history tables")
    sorted_ids = sorted(coordinates)
    parsed, previous_points = [], None
    for observed, (order, instant) in zip(observed_states, pairs):
        if (not isinstance(observed, dict) or _order(observed.get("order")) != order or
                _finite(observed.get("time_s"), "state instant") != instant or
                not isinstance(observed.get("tables"), dict)):
            raise ValueError("Native state identity differs from actual access parameters")
        tables = observed["tables"]
        displacement = _nodal(tables.get("DEPL"), order, instant, coordinates, "DEPL")
        reactions = _nodal(tables.get("REAC_NODA"), order, instant, coordinates, "REAC_NODA")
        stress = _gauss(tables.get("SIEF_ELGA"), STRESS_COMPONENTS, order, instant, body, "SIEF_ELGA")
        plastic = _gauss(tables.get("VARI_ELGA"), ("V1", "V2"), order, instant, body, "VARI_ELGA")
        if stress.keys() != plastic.keys():
            raise ValueError("Stress and equivalent-plastic tables have different native point coverage")
        points = sorted(stress)
        point_coordinates = [stress[key]["coordinates_mm"] for key in points]
        if (any(any(not math.isclose(a, b, rel_tol=1e-13, abs_tol=1e-13) for a, b in
                    zip(stress[key]["coordinates_mm"], plastic[key]["coordinates_mm"])) for key in points) or
                (previous_points is not None and point_coordinates != previous_points)):
            raise ValueError("Native stress/V1 coordinates drifted between fields or time states")
        previous_points = point_coordinates
        support_resultant = [math.fsum(reactions[node][axis] for node in groups[group])
                             for axis, group in enumerate(("X0", "Y0", "Z0"))]
        drive_resultant = math.fsum(reactions[node][0] for node in groups["XL"])
        post, count = _table(tables.get("BOUNDARY_RESULTANTS"),
                             ("INTITULE", "NUME_ORDRE", "INST", *VECTOR_COMPONENTS), "BOUNDARY_RESULTANTS")
        if count != 4:
            raise ValueError("Native boundary resultants require exactly four actual plane rows")
        post_rows = {}
        for row in range(count):
            name = _name(post["INTITULE"][row], "boundary resultant title")
            if name not in groups or name in post_rows:
                raise ValueError("Unknown/duplicate native resultant plane")
            _field_order(post, row, order, "BOUNDARY_RESULTANTS")
            if _finite(post["INST"][row], "resultant instant") != instant:
                raise ValueError("Wrong native resultant instant")
            post_rows[name] = [_finite(post[key][row], "native boundary resultant") for key in VECTOR_COMPONENTS]
            direct = [math.fsum(reactions[node][axis] for node in groups[name]) for axis in range(3)]
            tolerance = 1e-12 * max(1.0, *(abs(value) for value in [*direct, *post_rows[name]]))
            if any(abs(a - b) > tolerance for a, b in zip(direct, post_rows[name])):
                raise ValueError("Native POST_RELEVE_T disagrees with complete deduplicated nodal reactions")
        parsed.append({"time_s": instant, "actual_result_order": order,
            "displacements_mm": [displacement[node] for node in sorted_ids],
            "stresses_mpa": [stress[key]["components"] for key in points],
            "eq_plastic_strain": [plastic[key]["components"][0] for key in points],
            "plastic_indicator": [plastic[key]["components"][1] for key in points],
            "reaction_n": support_resultant, "drive_reaction_x_n": drive_resultant,
            "nodal_reactions_n": [reactions[node] for node in sorted_ids],
            "stress_point_coordinates_mm": point_coordinates,
            "stress_identifiers": [{"element_id": key[0], "point": key[1], "subpoint": key[2], "order": order} for key in points],
            "native_boundary_resultants_n": post_rows})
    return {"mesh_size_mm": _finite(mesh_size_mm, "mesh size"), "node_ids": sorted_ids,
            "coordinates_mm": [coordinates[node] for node in sorted_ids], "element_count": len(body),
            "states": parsed, "group_node_ids": groups,
            "reaction_method": "Component-specific constrained DOFs: X0.DX/Y0.DY/Z0.DZ; drive XL.DX recorded separately",
            "stress_component_order": ["xx", "yy", "zz", "xy", "xz", "yz"]}


def solve_level(input_path: str) -> None:
    from code_aster.Commands import (AFFE_CHAR_MECA, AFFE_MATERIAU, AFFE_MODELE,
        CALC_CHAMP, CREA_TABLE, DEBUT, DEFI_FONCTION, DEFI_GROUP, DEFI_LIST_REEL,
        DEFI_MATERIAU, FIN, IMPR_RESU, LIRE_MAILLAGE, POST_RELEVE_T, STAT_NON_LINE)
    from code_aster.Cata.Syntax import _F

    input_file = Path(input_path)
    config = json.loads(input_file.read_text(encoding="utf-8"))
    output, settings = input_file.parent, config["settings"]
    DEBUT()
    mesh_file = Path("fort.20")
    if not mesh_file.is_file():
        raise RuntimeError("Native deferred unit20 mesh input is missing after DEBUT")
    mesh_sha = hashlib.sha256(mesh_file.read_bytes()).hexdigest()
    if mesh_sha != config["mesh_sha256"]:
        raise RuntimeError("Native unit20 differs from the checked immutable mesh")
    versions, runtime = _runtime_versions()
    _save(output / "runtime.json", {"versions": versions, "code_aster_runtime": runtime})
    if versions.get("code_aster") != "17.4.0":
        raise RuntimeError("This nonlinear benchmark requires the pinned native 17.4 API")
    mesh = LIRE_MAILLAGE(FORMAT="GMSH", UNITE=20)
    try:
        expected_file = output / "expected_mesh.json"
        expected_sha = hashlib.sha256(expected_file.read_bytes()).hexdigest()
        if expected_sha != config["expected_mesh_sha256"]:
            raise ValueError("Checked source mesh catalogue SHA256 drifted")
        guard = validate_native_mesh(mesh, json.loads(expected_file.read_text(encoding="utf-8")))
        guard.update({"expected_mesh_sha256": expected_sha, "checked_msh_sha256": mesh_sha,
                      "solver_gate": "Verified before STAT_NON_LINE"})
        _save(output / "native_mesh_checks.json", guard)
    except (ValueError, OSError, TypeError, KeyError) as exc:
        _save(output / "native_mesh_checks.json", {"status": "FAIL", "error": str(exc), "solver_status": "NOT_RUN"})
        raise RuntimeError(f"Reused native mesh guard rejected import before nonlinear solve: {exc}") from exc
    mesh = DEFI_GROUP(reuse=mesh, MAILLAGE=mesh, CREA_GROUP_NO=tuple(
        _F(NOM="N" + name, GROUP_MA=name, CRIT_NOEUD="TOUS") for name in ("X0", "XL", "Y0", "Z0")))
    mesh = DEFI_GROUP(reuse=mesh, MAILLAGE=mesh,
                      CREA_GROUP_NO=_F(NOM="SUPPORT", UNION=("NX0", "NY0", "NZ0")))
    support = list(mesh.getNodes("SUPPORT"))
    expected_support = set().union(*(set(guard["native_group_node_indices"][name]) for name in ("X0", "Y0", "Z0")))
    if len(support) != len(set(support)) or set(support) != expected_support:
        guard.update({"status": "FAIL", "error": "Native support union differs from verified groups", "solver_status": "NOT_RUN"})
        _save(output / "native_mesh_checks.json", guard)
        raise RuntimeError("Native support union failed before nonlinear solve")
    guard["support_union_verified"] = True
    _save(output / "native_mesh_checks.json", guard)
    model = AFFE_MODELE(MAILLAGE=mesh, AFFE=_F(TOUT="OUI", PHENOMENE="MECANIQUE", MODELISATION="3D"))
    material = settings["material"]
    young, hardening = material["youngs_modulus_mpa"], material["plastic_modulus_mpa"]
    tangent = young * (hardening / (young + hardening))
    material_spec = {"ELAS": {"E": young, "NU": material["poisson_ratio"]},
                     "ECRO_LINE": {"SY": material["yield_stress_mpa"], "D_SIGM_EPSI": tangent},
                     "translation": "D_SIGM_EPSI is uniaxial total-strain tangent E*H/(E+H), not plastic modulus H"}
    _save(output / "native_material.json", material_spec)
    native_material = DEFI_MATERIAU(ELAS=_F(**material_spec["ELAS"]), ECRO_LINE=_F(**material_spec["ECRO_LINE"]))
    field = AFFE_MATERIAU(MAILLAGE=mesh, AFFE=_F(TOUT="OUI", MATER=native_material))
    fixed = AFFE_CHAR_MECA(MODELE=model, DDL_IMPO=(
        _F(GROUP_MA="X0", DX=0.0), _F(GROUP_MA="Y0", DY=0.0), _F(GROUP_MA="Z0", DZ=0.0)))
    drive = AFFE_CHAR_MECA(MODELE=model, DDL_IMPO=_F(GROUP_MA="XL", DX=settings["dimensions_mm"][0]))
    history = settings["history"]
    strain = DEFI_FONCTION(NOM_PARA="INST", ABSCISSE=history["times_s"], ORDONNEE=history["axial_strain"],
                           INTERPOL="LIN", PROL_GAUCHE="EXCLU", PROL_DROITE="EXCLU")
    increments = DEFI_LIST_REEL(VALE=history["times_s"])
    _save(output / "nonlinear_policy.json", NONLINEAR_POLICY)
    result = STAT_NON_LINE(MODELE=model, CHAM_MATER=field,
        EXCIT=(_F(CHARGE=fixed), _F(CHARGE=drive, FONC_MULT=strain)),
        COMPORTEMENT=_F(TOUT="OUI", RELATION="VMIS_ISOT_LINE", DEFORMATION="PETIT", ALGO_INTE="ANALYTIQUE"),
        INCREMENT=_F(LIST_INST=increments),
        NEWTON=_F(MATRICE="TANGENTE", REAC_ITER=1),
        CONVERGENCE=_F(RESI_GLOB_RELA=NONLINEAR_POLICY["relative_residual_limit"],
                       RESI_GLOB_MAXI=NONLINEAR_POLICY["absolute_residual_limit"],
                       ITER_GLOB_MAXI=NONLINEAR_POLICY["maximum_iterations"], ARRET="OUI", VERIF="TOUT"),
        SOLVEUR=_F(METHODE="MUMPS"), ARCHIVAGE=_F(LIST_INST=increments), MESURE=_F(TABLE="OUI", UNITE=81), INFO=1)
    result = CALC_CHAMP(reuse=result, RESULTAT=result, FORCE="REAC_NODA")
    access = result.getAccessParameters()
    indexes = list(result.getIndexes())
    pairs = _order_times(access, indexes, history["times_s"])
    _save(output / "native_access_parameters.json", {"available_orders": indexes, "access_parameters": access})
    states = []
    for order, instant in pairs:
        tables = {}
        for name, components in (("DEPL", VECTOR_COMPONENTS), ("REAC_NODA", VECTOR_COMPONENTS),
                                 ("SIEF_ELGA", STRESS_COMPONENTS), ("VARI_ELGA", ("V1", "V2"))):
            selection = {"GROUP_MA": "BODY"} if name in ("SIEF_ELGA", "VARI_ELGA") else {"TOUT": "OUI"}
            table = CREA_TABLE(RESU=_F(RESULTAT=result, NOM_CHAM=name, NUME_ORDRE=order, NOM_CMP=components, **selection))
            tables[name] = table.EXTR_TABLE().values()
            _save(output / f"order_{order}_{name.lower()}.table.json", tables[name])
        resultant = POST_RELEVE_T(ACTION=tuple(_F(INTITULE=name, OPERATION="EXTRACTION", REPERE="GLOBAL",
            RESULTAT=result, NOM_CHAM="REAC_NODA", NUME_ORDRE=order, GROUP_NO="N" + name,
            RESULTANTE=VECTOR_COMPONENTS) for name in ("X0", "XL", "Y0", "Z0")))
        tables["BOUNDARY_RESULTANTS"] = resultant.EXTR_TABLE().values()
        _save(output / f"order_{order}_boundary_resultants.table.json", tables["BOUNDARY_RESULTANTS"])
        states.append({"order": order, "time_s": instant, "tables": tables})
    catalog = _native_mesh_catalog(mesh, states[-1]["tables"], pairs[-1][0])
    _save(output / "mesh_catalog.json", catalog)
    IMPR_RESU(FORMAT="MED", UNITE=80, RESU=_F(RESULTAT=result,
        NOM_CHAM=("DEPL", "SIEF_ELGA", "VARI_ELGA", "REAC_NODA"), TOUT_ORDRE="OUI"))
    lock = Path("/opt/spack/var/spack/environments/simvia_env/spack.lock")
    libraries = None
    if lock.is_file():
        lock_data = json.loads(lock.read_text(encoding="utf-8"))
        _save(output / "spack.lock.json", lock_data)
        libraries = [{"name": spec.get("name"), "version": spec.get("version"), "hash": digest}
                     for digest, spec in lock_data.get("concrete_specs", {}).items()]
    raw = {"schema_version": "1", "solver_status": "COMPLETED", "converged": True,
        "available_orders": indexes, "access_parameters": access, "states": states, "mesh": catalog,
        "versions": versions, "code_aster_runtime": runtime, "numerical_libraries": libraries,
        "input_sha256": hashlib.sha256(input_file.read_bytes()).hexdigest(), "mesh_input_sha256": mesh_sha,
        "native_mesh_checks": guard, "native_material": material_spec, "nonlinear_policy": NONLINEAR_POLICY,
        "convergence_evidence": "Native .mess/stdout iteration histories and MESURE unit81, plus complete actual archived orders",
        "measured_linear_residual": None}
    _save(output / "worker_result.json", raw)
    FIN()
