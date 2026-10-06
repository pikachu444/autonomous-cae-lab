"""Pure component-axis diffusion, region inputs and retained-field verdicts."""

from collections import defaultdict
import copy
import json
import math

if __name__ == "coupled_reference":
    import domain_reference as rectangle
    import fenicsx_expression as expression
else:
    from plugins.pde_elliptic import reference as rectangle
    from caelab.adapters import fenicsx_worker as expression

VERSION = "1.1"
COMPONENTS = ["u0", "u1"]
REGIONS = ("left", "right")
SIDES = rectangle.SIDES
PDEInputError = expression.PDEInputError
_keys, _number, _same, _ids = rectangle._keys, rectangle._number, rectangle._same, rectangle._ids
finite_number = expression.finite_number
LIMITATIONS = ["Dimensionless stationary two-scalar-field, component-axis SPD diffusion and common PSD reaction.",
               "One serial real64 blocked P1 rectangle shares nodes across the midpoint interface; whole-vector side conditions only.",
               "Native degree8 symbolic component/vector L2 and full-gradient H1 are observations; Domain independently checks inputs, topology, rates and identities.",
               "Prescribed operator flux D*grad(u)*normal is not physical Fick flux, full physical balance or material qualification.",
               "Cellwise P1 flux jumps are not forced to zero; no added interface load or pointwise flux-jump acceptance gate.",
               "Time/nonlinear/MPI/imported/Robin/partial-component models and engineering release remain unsupported or UNKNOWN."]
SELECTED_SCOPE = "SELECTED_DIMENSIONLESS_TWO_COMPONENT_REGION_RECTANGLE"
SELECTED_PENDING = ["reference_agreement", "mesh_convergence", "physical_validation", "model_qualification"]
SELECTED_LIMITATIONS = [
    "Selected dimensionless stationary two-scalar-field rectangle with regional component-axis SPD diffusion and common PSD reaction.",
    "One even conforming P1 mesh shares original nodes across the x midpoint interface; whole-vector side conditions only.",
    "Native full fields, region/interface/split-side topology, operator input traces, solver synchronization and constrained residual are checked.",
    "No reference solution or mesh sweep is declared; reference errors/rates are null and agreement/sensitivity remain UNKNOWN.",
    "Signed component extrema are original nodal u0/u1 observations, not displacement, temperature or a physical Fick field.",
    "Prescribed D*grad(u)*normal is mathematical operator flux, not complete physical balance or heat-structure/material coupling.",
    "Time/nonlinear/MPI/imported/Robin/partial-component models and engineering release remain unsupported or UNKNOWN.",
]
_REFERENCE_METRICS = ("l2_error", "h1_seminorm_error", "l2_convergence_rate", "h1_seminorm_convergence_rate")
SELECTED_FIELD_METRICS = [f"component_{component}_field_{kind}" for component in range(2) for kind in ("min", "max")]


def touching(side):
    return ("left",) if side == "xmin" else ("right",) if side == "xmax" else REGIONS


def _matrix(value, label, *, positive=False):
    if (not isinstance(value, list) or len(value) != 2 or
            any(not isinstance(row, list) or len(row) != 2 or any(not finite_number(item) for item in row) for row in value)):
        raise PDEInputError(f"{label} requires a finite real 2x2 matrix")
    if value[0][1] != value[1][0]:
        raise PDEInputError(f"{label} must be exactly symmetric")
    a, b, d = float(value[0][0]), float(value[0][1]), float(value[1][1])
    if a < 0. or d < 0. or (positive and (a == 0. or d == 0.)):
        raise PDEInputError(f"{label} has an inadmissible principal diagonal")
    if a == 0. or d == 0.:
        if b != 0.: raise PDEInputError(f"{label} zero principal diagonal has a nonzero coupling")
        return copy.deepcopy(value)
    scale = max(abs(a), abs(b), abs(d))
    if not scale:
        if positive: raise PDEInputError(f"{label} is not positive definite")
        return copy.deepcopy(value)
    sa, sb, sd = a/scale, b/scale, d/scale
    if any(original != 0. and scaled == 0. for original, scaled in ((a, sa), (b, sb), (d, sd))):
        raise PDEInputError(f"{label} positivity cannot be established in supported real64 arithmetic")
    diagonal, off_diagonal = sa*sd, sb*sb
    if diagonal == 0. and sa != 0. and sd != 0.:
        raise PDEInputError(f"{label} principal minor underflows supported arithmetic")
    determinant = diagonal-off_diagonal
    if determinant < 0. or (positive and determinant <= 0.):
        raise PDEInputError(f"{label} is not {'positive definite' if positive else 'positive semidefinite'}")
    return copy.deepcopy(value)


def _vector(value, label):
    if not isinstance(value, list) or len(value) != 2:
        raise PDEInputError(f"{label} requires two ordered safe scalar expressions")
    return [expression.parse_expression(source) for source in value]


def _trees(problem):
    return {"rhs": {region: _vector(problem["weak_form"]["rhs"][region], "regional RHS") for region in REGIONS},
            "reference": None if problem["reference"] is None else {region: _vector(problem["reference"]["solution"][region], "regional reference") for region in REGIONS},
            "boundaries": {side: {region: _vector(problem["boundaries"][side]["value"][region], "side vector") for region in touching(side)} for side in SIDES}}


def _value(tree, point):
    try:
        value = expression.interpret_expression(tree, point, {name: getattr(math, name) for name in expression.FUNCTION_NAMES})
    except (ArithmeticError, ValueError) as exc:
        raise PDEInputError("Regional expression is undefined at a required point") from exc
    return _number(value, "regional expression sample")


def validate_settings(settings):
    selected = isinstance(settings, dict) and "mode" in settings
    _keys(settings, {"mode", "problem", "mesh", "validation", "input_provenance"} if selected else
          {"problem", "mesh", "validation"}, "coupled settings")
    if selected:
        if settings["mode"] != "selected_mesh": raise PDEInputError("Explicit coupled mode must be selected_mesh")
        source = _keys(settings["input_provenance"], {"origin", "reference"}, "declared input provenance")
        if source["origin"] not in ("ASSUMED", "MEASURED_REPORTED", "PUBLISHED_REFERENCE", "SYNTHETIC"):
            raise PDEInputError("Selected input origin must be explicitly declared")
        if not isinstance(source["reference"], str) or not source["reference"].strip() or len(source["reference"]) > 2000:
            raise PDEInputError("Selected input source reference must be nonempty and bounded")
    problem = _keys(settings["problem"], {"domain", "weak_form", "boundaries", "reference"}, "coupled problem")
    geometry = _keys(problem["domain"], {"type", "lengths", "interface"}, "coupled rectangle")
    lengths = geometry["lengths"]
    if geometry["type"] != "rectangle" or not isinstance(lengths, list) or len(lengths) != 2 or any(not finite_number(value) or not .001 <= value <= 1000 for value in lengths):
        raise PDEInputError("Coupled rectangle lengths require finite 0.001..1000 values")
    interface = _keys(geometry["interface"], {"axis", "fraction"}, "straight interface")
    if type(interface["axis"]) is not int or interface["axis"] != 0 or not finite_number(interface["fraction"]) or interface["fraction"] != .5:
        raise PDEInputError("Only the conforming x midpoint interface is supported")
    weak = _keys(problem["weak_form"], {"family", "diffusion", "reaction", "rhs"}, "coupled weak form")
    if weak["family"] != "coupled_diffusion": raise PDEInputError("Unsupported coupled family")
    _keys(weak["diffusion"], REGIONS, "regional diffusion")
    _keys(weak["rhs"], REGIONS, "regional source")
    for region in REGIONS: _matrix(weak["diffusion"][region], "regional diffusion", positive=True)
    _matrix(weak["reaction"], "reaction")
    if selected:
        if problem["reference"] is not None: raise PDEInputError("Selected reference must be null; no reference is constructed")
    else:
        reference = _keys(problem["reference"], {"solution", "source"}, "coupled reference")
        _keys(reference["solution"], REGIONS, "regional reference")
        if not isinstance(reference["source"], str) or not reference["source"].strip() or len(reference["source"]) > 2000: raise PDEInputError("A bounded reference source is required")
    _keys(problem["boundaries"], SIDES, "coupled sides")
    for side, boundary in problem["boundaries"].items():
        _keys(boundary, {"type", "value"}, "whole side")
        if boundary["type"] not in ("dirichlet", "neumann"): raise PDEInputError("Only whole-vector Dirichlet/Neumann sides are supported")
        _keys(boundary["value"], touching(side), "touching side regions")
    if not any(boundary["type"] == "dirichlet" for boundary in problem["boundaries"].values()): raise PDEInputError("Pure Neumann is unsupported")
    mesh = _keys(settings["mesh"], {"cell_counts", "degree"}, "P1 mesh")
    counts = mesh["cell_counts"]
    if (type(mesh["degree"]) is not int or mesh["degree"] != 1 or not isinstance(counts, list) or
            (len(counts) != 1 if selected else not 3 <= len(counts) <= 8) or
            any(type(n) is not int or not 2 <= n <= 128 or n % 2 for n in counts) or
            (not selected and any(b != 2*a for a, b in zip(counts, counts[1:])))):
        raise PDEInputError("Selected mesh requires one even P1 count2..128" if selected else
                            "Even P1 mesh counts2..128 require3..8 successive doublings")
    thresholds = _keys(settings["validation"], {"max_residual_relative"} if selected else rectangle._VALIDATIONS, "numerical validation")
    if any(not finite_number(value, positive=True) for value in thresholds.values()): raise PDEInputError("All numerical thresholds must be finite and positive")
    trees, (lx, ly) = _trees(problem), lengths
    for count in counts:
        prescribed = {}
        for i in range(count+1):
            for j in range(count+1):
                point = (lx*i/count, ly*j/count)
                for region in REGIONS:
                    if (region == "left" and i <= count//2) or (region == "right" and i >= count//2):
                        for tree in trees["rhs"][region]+(trees["reference"][region] if trees["reference"] is not None else []): _value(tree, point)
                for side, selected in (("xmin", i == 0), ("xmax", i == count), ("ymin", j == 0), ("ymax", j == count)):
                    if not selected: continue
                    for region in touching(side):
                        if side[0] == "y" and ((region == "left" and i > count//2) or (region == "right" and i < count//2)): continue
                        values = [_value(tree, point) for tree in trees["boundaries"][side][region]]
                        if problem["boundaries"][side]["type"] == "dirichlet":
                            if point in prescribed and any(not math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12) for a, b in zip(values, prescribed[point])):
                                raise PDEInputError("Conflicting corner/interface Dirichlet component data")
                            prescribed[point] = values
    return json.loads(json.dumps(settings, allow_nan=False))


def selected_settings():
    """Editable mathematical inputs, independent of manufactured references."""
    return validate_settings({"mode": "selected_mesh",
        "problem": {"domain": {"type": "rectangle", "lengths": [2., 1.], "interface": {"axis": 0, "fraction": .5}},
            "weak_form": {"family": "coupled_diffusion", "diffusion": {"left": [[2., .5], [.5, 1.]], "right": [[4., -.5], [-.5, 2.]]},
                          "reaction": [[0., 0.], [0., 0.]], "rhs": {"left": ["1", "-0.5"], "right": ["2", "1"]}},
            "boundaries": {"xmin": {"type": "dirichlet", "value": {"left": ["0", "0"]}},
                           "xmax": {"type": "dirichlet", "value": {"right": ["0", "0"]}},
                           "ymin": {"type": "neumann", "value": {"left": ["0", "0"], "right": ["0", "0"]}},
                           "ymax": {"type": "neumann", "value": {"left": ["0", "0"], "right": ["0", "0"]}}},
            "reference": None},
        "mesh": {"cell_counts": [16], "degree": 1}, "validation": {"max_residual_relative": 1e-10},
        "input_provenance": {"origin": "ASSUMED", "reference": "Editable assumed dimensionless mathematical inputs; no physical material interpretation"}})


def manufactured_settings(case="polynomial", diffusions=None, reaction=None, lengths=(2., 1.)):
    diffusions = copy.deepcopy({"left": [[2., .5], [.5, 1.]], "right": [[4., -.5], [-.5, 2.]]} if diffusions is None else diffusions)
    reaction = copy.deepcopy([[0., 0.], [0., 0.]] if reaction is None else reaction)
    _keys(diffusions, REGIONS, "manufactured diffusion")
    for region in REGIONS: _matrix(diffusions[region], region, positive=True)
    _matrix(reaction, "manufactured reaction")
    if not isinstance(lengths, (tuple, list)) or len(lengths) != 2 or any(not finite_number(value) or not .001 <= value <= 1000 for value in lengths): raise PDEInputError("Manufactured coupled rectangle lengths are unsupported")
    if case not in ("polynomial", "harmonic"): raise PDEInputError("Unknown manufactured coupled case")
    left, right = diffusions["left"], diffusions["right"]
    flux = [left[row][0]-2*left[row][1] for row in range(2)]
    scale = max(abs(value) for row in right for value in row)
    a, b, d = right[0][0]/scale, right[0][1]/scale, right[1][1]/scale
    determinant = a*d-b*b
    coefficients = {"left": [1., -2.], "right": [_number((d*(flux[0]/scale)-b*(flux[1]/scale))/determinant, "right slope"),
                _number((a*(flux[1]/scale)-b*(flux[0]/scale))/determinant, "right slope")]}
    s = f"(x[0]-{float(lengths[0]/2)!r})"
    q = f"({s}**2*x[1]**2)" if case == "polynomial" else f"({s}**2-x[1]**2)"
    solutions, rhs, flux_x, flux_y = {}, {}, {}, {}
    for region in REGIONS:
        matrix, slope = diffusions[region], coefficients[region]
        beta_product = [matrix[row][0]+2*matrix[row][1] for row in range(2)]
        solutions[region] = [f"1+x[1]+{slope[0]!r}*{s}+{q}", f"2-3*x[1]+{slope[1]!r}*{s}+2*{q}"]
        rhs[region] = []
        for component in range(2):
            r0, r1 = reaction[component]
            reaction_source = f"{r0+2*r1!r}+{r0-3*r1!r}*x[1]+{r0*slope[0]+r1*slope[1]!r}*{s}+{r0+2*r1!r}*{q}"
            if not any(reaction[component]): reaction_source = "0.0"
            rhs[region].append(f"({reaction_source})-2*(x[1]**2+{s}**2)*{beta_product[component]!r}" if case == "polynomial" else reaction_source)
        x_factor = f"2*{s}*x[1]**2" if case == "polynomial" else f"2*{s}"
        y_factor = f"2*{s}**2*x[1]" if case == "polynomial" else "-2*x[1]"
        flux_x[region] = [f"{sum(matrix[row][column]*slope[column] for column in range(2))!r}+{beta_product[row]!r}*({x_factor})" for row in range(2)]
        flux_y[region] = [f"{matrix[row][0]-3*matrix[row][1]!r}+{beta_product[row]!r}*({y_factor})" for row in range(2)]
    return validate_settings({"problem": {"domain": {"type": "rectangle", "lengths": list(lengths), "interface": {"axis": 0, "fraction": .5}},
            "weak_form": {"family": "coupled_diffusion", "diffusion": diffusions, "reaction": reaction, "rhs": rhs},
            "boundaries": {"xmin": {"type": "dirichlet", "value": {"left": solutions["left"]}}, "ymin": {"type": "dirichlet", "value": copy.deepcopy(solutions)},
                           "xmax": {"type": "neumann", "value": {"right": flux_x["right"]}}, "ymax": {"type": "neumann", "value": flux_y}},
            "reference": {"solution": solutions, "source": f"Direct manufactured {case} component-axis diffusion with continuous shared interface value and operator flux"}},
            "mesh": {"cell_counts": [8, 16, 32], "degree": 1},
            "validation": {"max_l2_error": .04, "min_l2_rate": 1.8, "max_h1_seminorm_error": .8, "min_h1_rate": .9, "max_residual_relative": 1e-10}})


def model_declaration(settings):
    settings = validate_settings(settings)
    problem, weak = settings["problem"], settings["problem"]["weak_form"]
    declaration = {"case": "rectangle_coupled_diffusion", "version": VERSION,
            "model": {"geometry": {"type": "rectangle", "dimensions": copy.deepcopy(problem["domain"]["lengths"]), "origin": [0., 0.], "unit": "1",
                                    "interface": copy.deepcopy(problem["domain"]["interface"]), "regions": list(REGIONS)},
                      "mesh": {**copy.deepcopy(settings["mesh"]), "cell_type": "triangle", "space": "vector_lagrange", "components": list(COMPONENTS), "block_size": 2}},
            "constitutive_law": {"type": "dimensionless_coupled_diffusion_reaction", "diffusion": {region: {"value": copy.deepcopy(weak["diffusion"][region]), "unit": "1"} for region in REGIONS},
                                 "reaction": {"value": copy.deepcopy(weak["reaction"]), "unit": "1"}, "diffusion_axis": "component_rows_of_grad_u", "operator_flux": "D*grad(u)*outward_normal"},
            "boundary_conditions": [{"type": problem["boundaries"][side]["type"], "selection": {"type": "named_side", "name": side},
                    "expression": copy.deepcopy(problem["boundaries"][side]["value"]), "components": list(COMPONENTS), "unit": "1", "neumann_semantics": "D*grad(u)*outward_normal"} for side in SIDES],
            "loads": [{"type": "regional_source", "region": region, "expression": list(weak["rhs"][region]), "components": list(COMPONENTS), "unit": "1"} for region in REGIONS],
            "outputs": {"fields": [{"field": "u", "type": "vector", "components": list(COMPONENTS), "unit": "1"}]}, "reference": copy.deepcopy(problem["reference"])}
    if settings.get("mode") == "selected_mesh":
        declaration.update(mode="selected_mesh", scope=SELECTED_SCOPE,
                           input_provenance=copy.deepcopy(settings["input_provenance"]))
    return declaration


def describe_inputs(settings):
    """Bounded selected scalar locations; off-diagonal mirrors are explicit.

    ``settings_mirrors`` is a candidate additive Core descriptor seam. Core
    must independently apply/verify the frozen mirror locations before these
    descriptors are admitted to public DOE/DE. Matrix bounds here are a
    parameterization resource envelope, not SPD/PSD or engineering criteria;
    full scientific admission is repeated after every simultaneous binding.
    """
    s = validate_settings(settings)
    if s.get("mode") != "selected_mesh":
        raise PDEInputError("Declared scalar bindings require the opt-in selected_mesh mode")
    descriptors = [{"id": f"length_{axis}", "label": f"Dimensionless rectangle length {axis}", "unit": "1",
        "value": value, "lower": .001, "upper": 1000., "settings_path": ["problem", "domain", "lengths", axis],
        "declaration_paths": [["model", "geometry", "dimensions", axis]]}
        for axis, value in enumerate(s["problem"]["domain"]["lengths"])]
    for region in REGIONS:
        for i, j in ((0, 0), (0, 1), (1, 1)):
            value = s["problem"]["weak_form"]["diffusion"][region][i][j]
            item = {"id": f"diffusion_{region}_{i}{j}", "label": f"{region} component diffusion D{i}{j}" + (" = D10" if i != j else ""),
                "unit": "1", "value": value, "lower": 1e-6 if i == j else -1e6, "upper": 1e6,
                "settings_path": ["problem", "weak_form", "diffusion", region, i, j],
                "declaration_paths": [["constitutive_law", "diffusion", region, "value", i, j]]}
            if i != j:
                item["settings_mirrors"] = [["problem", "weak_form", "diffusion", region, j, i]]
                item["declaration_paths"].append(["constitutive_law", "diffusion", region, "value", j, i])
            descriptors.append(item)
    for i, j in ((0, 0), (0, 1), (1, 1)):
        item = {"id": f"reaction_{i}{j}", "label": f"Common component reaction R{i}{j}" + (" = R10" if i != j else ""),
            "unit": "1", "value": s["problem"]["weak_form"]["reaction"][i][j], "lower": 0. if i == j else -1e6, "upper": 1e6,
            "settings_path": ["problem", "weak_form", "reaction", i, j],
            "declaration_paths": [["constitutive_law", "reaction", "value", i, j]]}
        if i != j:
            item["settings_mirrors"] = [["problem", "weak_form", "reaction", j, i]]
            item["declaration_paths"].append(["constitutive_law", "reaction", "value", j, i])
        descriptors.append(item)
    if any(not item["lower"] <= item["value"] <= item["upper"] for item in descriptors):
        raise PDEInputError("Selected input lies outside the bounded scalar binding envelope")
    return descriptors


def bind_inputs(settings, values):
    s = copy.deepcopy(validate_settings(settings))
    descriptors = {item["id"]: item for item in describe_inputs(s)}
    if type(values) is not dict or not values or not set(values) <= set(descriptors):
        raise PDEInputError("Assignments must name advertised selected scalar inputs")
    for identifier, value in values.items():
        item = descriptors[identifier]
        _number(value, "bound " + identifier)
        if not item["lower"] <= value <= item["upper"]: raise PDEInputError("Assignment exceeds the scalar input envelope")
        for path in [item["settings_path"], *item.get("settings_mirrors", [])]:
            cursor = s
            for key in path[:-1]: cursor = cursor[key]
            cursor[path[-1]] = value
    # Do not repair/clamp a matrix or manufacture reference/RHS terms after a
    # change. The simultaneous declared inputs must still establish SPD/PSD.
    return validate_settings(s)


def _directed_rows(rows, count, label):
    if (not isinstance(rows, list) or len(rows) != count or any(not isinstance(row, list) or len(row) != 2 or any(not finite_number(value) for value in row) for row in rows)):
        raise PDEInputError(f"Incomplete/nonfinite directed {label}")
    return rows


def _ordered_ids(rows, expected, label, size):
    if _ids(rows, label, size=size) != expected or rows != sorted(rows): raise PDEInputError(f"Incomplete/unordered {label}")


def _retained_field(settings, study, field, trees):
    _keys(field, rectangle._FIELD_KEYS | {"field_type", "components", "block_size", "cell_ids", "cell_regions", "interface"}, "coupled field")
    if field["schema_version"] != "1" or field["coordinates_unit"] != "1" or field["field_unit"] != "1" or field["field_type"] != "vector" or field["components"] != COMPONENTS or type(field["block_size"]) is not int or field["block_size"] != 2: raise PDEInputError("Coupled field units/components/block mismatch")
    n, lengths, size, grid, xyz, exterior = rectangle._mesh_topology(settings, study, field)
    _ordered_ids(field["node_ids"], set(range(size)), "global node IDs", size)
    values = dict(zip(field["node_ids"], _directed_rows(field["values"], size, "field values")))
    ncells, cells = 2*n*n, field["cell_node_ids"]
    _ordered_ids(field["cell_ids"], set(range(ncells)), "global cell IDs", ncells)
    if not isinstance(field["cell_regions"], list) or len(field["cell_regions"]) != ncells: raise PDEInputError("Incomplete native region tags")
    region_cells, region_nodes, adjacent = {r: set() for r in REGIONS}, {r: set() for r in REGIONS}, defaultdict(list)
    for cell_id, cell, region in zip(field["cell_ids"], cells, field["cell_regions"]):
        xs = [grid[node][0] for node in cell]
        expected = "left" if max(xs) <= n//2 else "right" if min(xs) >= n//2 else None
        if expected is None or region != expected: raise PDEInputError("Native region tag reversal/crossing")
        region_cells[region].add(cell_id)
        region_nodes[region].update(cell)
        for a, b in ((0, 1), (1, 2), (2, 0)): adjacent[tuple(sorted((cell[a], cell[b])))].append((cell_id, region))
    if any(len(region_cells[region]) != n*n for region in REGIONS): raise PDEInputError("Regional cell coverage incomplete")
    total_facets = 3*n*n+2*n
    interface = _keys(field["interface"], {"facet_ids", "facet_node_ids", "node_ids", "adjacent_cell_ids", "measure", "plus_x_normal"}, "native interface")
    facets = _ids(interface["facet_ids"], "interface facets", size=total_facets)
    if len(facets) != n or interface["facet_ids"] != sorted(interface["facet_ids"]): raise PDEInputError("Incomplete interface facet IDs")
    expected_nodes = {node for node, point in grid.items() if point[0] == n//2}
    _ordered_ids(interface["node_ids"], expected_nodes, "interface shared nodes", size)
    if region_nodes["left"] & region_nodes["right"] != expected_nodes: raise PDEInputError("Interface nodes are not shared by exactly both regions")
    endpoints, neighbours = interface["facet_node_ids"], interface["adjacent_cell_ids"]
    if not isinstance(endpoints, list) or len(endpoints) != n or not isinstance(neighbours, list) or len(neighbours) != n: raise PDEInputError("Incomplete interface adjacency")
    seen = set()
    for pair, cell_pair in zip(endpoints, neighbours):
        if len(_ids(pair, "interface endpoints", size=size)) != 2: raise PDEInputError("Malformed interface endpoints")
        edge = tuple(sorted(pair))
        if edge in seen or not set(pair) <= expected_nodes or len(adjacent.get(edge, [])) != 2: raise PDEInputError("Interface is not an actual internal edge")
        actual = {region: cell for cell, region in adjacent[edge]}
        if set(actual) != set(REGIONS) or cell_pair != [actual["left"], actual["right"]] or any(type(cell) is not int for cell in cell_pair): raise PDEInputError("Native interface adjacency must be exact [left,right]")
        seen.add(edge)
    expected_edges = {edge for edge in adjacent if set(edge) <= expected_nodes}
    if seen != expected_edges or len(seen) != n: raise PDEInputError("Interface edge coverage incomplete")
    _same(interface["measure"], lengths[1], "interface measure")
    if not isinstance(interface["plus_x_normal"], list) or len(interface["plus_x_normal"]) != 2: raise PDEInputError("Missing prescribed plus-x interface orientation")
    for a, b in zip(interface["plus_x_normal"], (1., 0.)): _same(a, b, "plus-x interface orientation")
    boundaries = _keys(field["boundaries"], SIDES, "split native boundaries")
    exterior_seen, facet_seen, union, prescribed, errors, passed = set(), set(facets), set(), {}, [0., 0.], [True, True]
    for side in SIDES:
        segments = _keys(boundaries[side], touching(side), "touching native side regions")
        axis, slot = (0, 0) if side == "xmin" else (0, n) if side == "xmax" else (1, 0) if side == "ymin" else (1, n)
        for region in touching(side):
            segment = _keys(segments[region], rectangle._SIDE_KEYS, "native side segment")
            nodes = {node for node, point in grid.items() if point[axis] == slot and (axis == 0 or (point[0] <= n//2 if region == "left" else point[0] >= n//2))}
            _ordered_ids(segment["dof_ids"], nodes, "segment nodes", size)
            native_facets = _ids(segment["facet_ids"], "segment facets", size=total_facets)
            expected_count = n if axis == 0 else n//2
            if len(native_facets) != expected_count or native_facets & facet_seen or segment["facet_ids"] != sorted(segment["facet_ids"]): raise PDEInputError("Native segment tags overlap/omit actual facets")
            facet_seen.update(native_facets)
            pairs = segment["facet_node_ids"]
            if not isinstance(pairs, list) or len(pairs) != expected_count: raise PDEInputError("Incomplete segment endpoints")
            segment_edges = set()
            for pair in pairs:
                if len(_ids(pair, "segment endpoints", size=size)) != 2: raise PDEInputError("Invalid segment edge")
                edge = tuple(sorted(pair))
                if edge not in exterior or not set(pair) <= nodes or edge in exterior_seen: raise PDEInputError("Segment endpoints differ from disjoint actual exterior")
                segment_edges.add(edge)
                exterior_seen.add(edge)
            if segment_edges != {edge for edge in exterior if set(edge) <= nodes}: raise PDEInputError("Incomplete segment exterior coverage")
            length = lengths[1-axis]/(1 if axis == 0 else 2)
            _same(segment["measure"], length, "segment measure")
            normal = segment["normal_integral"]
            if not isinstance(normal, list) or len(normal) != 2: raise PDEInputError("Incomplete side normal")
            for component in range(2): _same(normal[component], length*(-1 if slot == 0 else 1) if component == axis else 0., "outward segment normal")
            _directed_rows(segment["prescribed_values"], len(nodes), "segment prescribed values")
            integral = segment["prescribed_integral"]
            if not isinstance(integral, list) or len(integral) != 2: raise PDEInputError("Incomplete directed segment integral")
            for value in integral: _number(value, "prescribed integral")
            for node, row in zip(segment["dof_ids"], segment["prescribed_values"]):
                expected = [_value(tree, xyz[node]) for tree in trees["boundaries"][side][region]]
                for component in range(2): _same(row[component], expected[component], "regional directed side value")
                if settings["problem"]["boundaries"][side]["type"] == "dirichlet":
                    if node in prescribed:
                        for a, b in zip(expected, prescribed[node]): _same(a, b, "retained duplicate Dirichlet data")
                    prescribed[node] = expected
                    union.add(node)
                    for component in range(2):
                        errors[component] = max(errors[component], abs(values[node][component]-expected[component]))
                        passed[component] = passed[component] and math.isclose(values[node][component], expected[component], rel_tol=1e-12, abs_tol=1e-12)
    if exterior_seen != exterior: raise PDEInputError("Split segments do not cover the exact exterior")
    _ordered_ids(field["dirichlet_node_ids"], union, "Dirichlet union", size)
    if study["dirichlet_nodes"] != len(union) or study["dirichlet_dofs"] != 2*len(union): raise PDEInputError("Native Dirichlet count differs from full vector union")
    return errors, passed, region_cells, region_nodes


def _coefficient_observations(settings, study):
    weak = settings["problem"]["weak_form"]
    _keys(study.get("region_coefficients"), REGIONS, "actual native diffusion matrices")
    for region in REGIONS:
        matrix = _matrix(study["region_coefficients"][region], "native regional matrix", positive=True)
        if matrix != weak["diffusion"][region]: raise PDEInputError("Native diffusion Constant differs from declared matrix")
    if _matrix(study.get("reaction_matrix"), "native reaction") != weak["reaction"]: raise PDEInputError("Native reaction Constant differs from declaration")


def assess(settings, studies, native_fields, bindings):
    settings = validate_settings(settings)
    selected = settings.get("mode") == "selected_mesh"
    counts, trees = settings["mesh"]["cell_counts"], _trees(settings["problem"])
    if not all(isinstance(rows, list) and len(rows) == len(counts) for rows in (studies, native_fields, bindings)): raise PDEInputError("Complete coupled mesh history/fields/bindings required")
    observed, boundary_pass, sync, residuals, reasons = copy.deepcopy(studies), [], [], [], []
    for index, (n, study, field, binding) in enumerate(zip(counts, observed, native_fields, bindings)):
        if not isinstance(study, dict) or not rectangle._STUDY_KEYS <= set(study): raise PDEInputError("Incomplete coupled study")
        for key, expected in (("cells_per_axis", n), ("degree", 1), ("global_nodes", (n+1)**2), ("global_dofs", 2*(n+1)**2), ("global_cells", 2*n*n), ("block_size", 2), ("interface_facets", n)):
            if type(study.get(key)) is not int or study[key] != expected: raise PDEInputError("Native block/grid/interface count mismatch")
        if study["cell_type"] != "triangle" or type(study.get("dirichlet_nodes")) is not int or type(study["dirichlet_dofs"]) is not int: raise PDEInputError("Malformed native Dirichlet counts")
        _keys(study.get("region_cell_counts"), REGIONS, "regional cell counts")
        if any(type(study["region_cell_counts"][region]) is not int or study["region_cell_counts"][region] != n*n for region in REGIONS): raise PDEInputError("Native region cell counts mismatch")
        _same(study["nominal_h"], math.hypot(*settings["problem"]["domain"]["lengths"])/n, "coupled h")
        _coefficient_observations(settings, study)
        errors, passed, region_cells, region_nodes = _retained_field(settings, study, field, trees)
        boundary_pass.extend(passed)
        components = study.get("components")
        if not isinstance(components, list) or len(components) != 2: raise PDEInputError("Missing coupled component diagnostics")
        for component, row in enumerate(components):
            _keys(row, {"index", "field", "l2_error", "h1_seminorm_error", "l2_convergence_rate", "h1_seminorm_convergence_rate", "boundary_value_error"}, "component diagnostic")
            if type(row["index"]) is not int or row["index"] != component or row["field"] != COMPONENTS[component]: raise PDEInputError("Component diagnostic order mismatch")
            _number(row["boundary_value_error"], "boundary_value_error", nonnegative=True)
            if selected:
                if any(row[name] is not None for name in _REFERENCE_METRICS): raise PDEInputError("Selected component reference diagnostics must all be null")
            else:
                for name in ("l2_error", "h1_seminorm_error"): _number(row[name], name, nonnegative=True)
            _same(row["boundary_value_error"], errors[component], "native/independent component boundary error")
            for name, rate in (() if selected else (("l2_error", "l2_convergence_rate"), ("h1_seminorm_error", "h1_seminorm_convergence_rate"))):
                expected = expression.error_rate(observed[index-1]["components"][component][name], row[name]) if index else None
                if expected is None:
                    if row[rate] is not None: raise PDEInputError("First/zero component error cannot establish rate")
                else: _same(row[rate], expected, "component refinement rate")
        _same(study["boundary_value_error"], max(errors), "aggregate boundary error")
        if selected and any(study[name] is not None for name in _REFERENCE_METRICS): raise PDEInputError("Selected aggregate reference diagnostics must all be null")
        for name, rate in (() if selected else (("l2_error", "l2_convergence_rate"), ("h1_seminorm_error", "h1_seminorm_convergence_rate"))):
            _number(study[name], name, nonnegative=True)
            _same(study[name], math.hypot(*(row[name] for row in components)), "component/aggregate norm")
            expected = expression.error_rate(observed[index-1][name], study[name]) if index else None
            if expected is None:
                if study[rate] is not None: raise PDEInputError("First/zero vector error cannot establish rate")
            else: _same(study[rate], expected, "vector refinement rate")
        _keys(binding, {"schema_version", "components", "regions"}, "coupled input binding")
        if binding["schema_version"] != "1" or binding["components"] != COMPONENTS: raise PDEInputError("Binding schema/components mismatch")
        _keys(binding["regions"], REGIONS, "bound regions")
        xyz = dict(zip(field["node_ids"], field["coordinates"]))
        for region in REGIONS:
            row = _keys(binding["regions"][region], {"cell_ids", "node_ids", "diffusion", "reaction", "rhs_values", "reference_values"}, "regional input binding")
            _ordered_ids(row["cell_ids"], region_cells[region], "bound region cells", 2*n*n)
            _ordered_ids(row["node_ids"], region_nodes[region], "bound region nodes", (n+1)**2)
            if _matrix(row["diffusion"], "bound diffusion", positive=True) != settings["problem"]["weak_form"]["diffusion"][region] or _matrix(row["reaction"], "bound reaction") != settings["problem"]["weak_form"]["reaction"]: raise PDEInputError("Bound input matrix differs from declaration")
            if selected and row["reference_values"] is not None: raise PDEInputError("Selected reference binding must be null, not invented values")
            for key, parsed in (("rhs_values", trees["rhs"][region]),) if selected else (("rhs_values", trees["rhs"][region]), ("reference_values", trees["reference"][region])):
                rows = _directed_rows(row[key], len(row["node_ids"]), "regional source/reference")
                for node, values in zip(row["node_ids"], rows):
                    for component in range(2): _same(values[component], _value(parsed[component], xyz[node]), "regional/interface RHS/reference trace")
        synchronization = _number(study.get("solution_sync_error"), "actual x/Function max sync error", nonnegative=True)
        sync.append(synchronization <= max(1e-12, max(abs(value) for row in field["values"] for value in row)*1e-12))
        if type(study["ksp_convergence_reason"]) is not int or type(study["ksp_iterations"]) is not int or study["ksp_iterations"] < 0: raise PDEInputError("Missing actual KSP observations")
        reasons.append(study["ksp_convergence_reason"])
        residual = _keys(study["linear_residual"], {"absolute", "rhs_norm", "relative", "normalization"}, "actual residual")
        for key in ("absolute", "rhs_norm", "relative"): _number(residual[key], key, nonnegative=True)
        expected = residual["absolute"]/residual["rhs_norm"] if residual["rhs_norm"] else residual["absolute"]
        if residual["normalization"] != ("rhs_l2_norm" if residual["rhs_norm"] else "absolute_for_zero_rhs") or not finite_number(expected) or not math.isclose(residual["relative"], expected, rel_tol=1e-12, abs_tol=0.): raise PDEInputError("Actual constrained residual normalization inconsistent")
        residuals.append(expected)
    fine, limits = observed[-1], settings["validation"]
    if selected:
        numerical = [("pde_boundary_and_mesh", all(boundary_pass), None, "Complete region/interface/split-side geometry and directed Dirichlet data"),
            ("pde_solution_sync", all(sync), [row["solution_sync_error"] for row in observed], "Actual scalar-DOF x/Function abs/rel1e-12"),
            ("pde_solver_convergence", all(reason > 0 for reason in reasons), reasons, "Positive KSP reason"),
            ("pde_linear_residual", max(residuals) <= limits["max_residual_relative"], residuals, limits["max_residual_relative"])]
        checks = [{"code": code, "status": "PASS" if passed else "FAIL", "observed": value, "limit": limit} for code, passed, value, limit in numerical]
        passed = all(row["status"] == "PASS" for row in checks)
        failures = ", ".join(row["code"] for row in checks if row["status"] == "FAIL")
        actual = {"linear_residual_relative": max(residuals)}
        for component in range(2):
            values = [row[component] for row in native_fields[0]["values"]]
            actual[f"component_{component}_field_min"] = min(values)
            actual[f"component_{component}_field_max"] = max(values)
        metrics = {name: {"value": value, "unit": "1", "valid": passed,
                   **({"reason": f"Selected coupled numerical validation failed: {failures}"} if not passed else {})} for name, value in actual.items()}
        metrics.update({name: {"value": None, "unit": "1", "valid": False,
                       "reason": "Not evaluated: selected_mesh supplies no reference solution or mesh sweep"}
                       for name in (*_REFERENCE_METRICS, *[f"component_{component}_{name}" for component in range(2) for name in ("l2_error", "h1_seminorm_error")])})
        return {"checks": checks, "metrics": metrics, "mesh_studies": observed,
            "reference": {"status": "UNKNOWN", "solution": None, "source": None, "components": list(COMPONENTS),
                          "family": "coupled_diffusion", "error_quadrature_degree": None,
                          "diffusion_axis": "component_rows_of_grad_u", "h1_semantics": None,
                          "interface_semantics": "CG shared value and natural operator-flux continuity; no dS load"},
            "pending_validations": list(SELECTED_PENDING), "limitations": list(SELECTED_LIMITATIONS),
            "scope": SELECTED_SCOPE, "input_provenance": copy.deepcopy(settings["input_provenance"])}
    rates = {name: [value for study in observed[1:] for value in [study[name], *[row[name] for row in study["components"]]]] for name in ("l2_convergence_rate", "h1_seminorm_convergence_rate")}
    conditions = [("pde_boundary_and_mesh", all(boundary_pass), None, "Complete region/interface/split-side geometry and directed Dirichlet data"),
        ("pde_solution_sync", all(sync), [row["solution_sync_error"] for row in observed], "Actual scalar-DOF x/Function abs/rel1e-12"),
        ("pde_solver_convergence", all(reason > 0 for reason in reasons), reasons, "Positive KSP reason"),
        ("pde_analytical_l2_error", fine["l2_error"] <= limits["max_l2_error"], fine["l2_error"], limits["max_l2_error"]),
        ("pde_analytical_h1_seminorm_error", fine["h1_seminorm_error"] <= limits["max_h1_seminorm_error"], fine["h1_seminorm_error"], limits["max_h1_seminorm_error"]),
        ("pde_l2_convergence_rate", all(rate is not None and rate >= limits["min_l2_rate"] for rate in rates["l2_convergence_rate"]), rates["l2_convergence_rate"], limits["min_l2_rate"]),
        ("pde_h1_seminorm_convergence_rate", all(rate is not None and rate >= limits["min_h1_rate"] for rate in rates["h1_seminorm_convergence_rate"]), rates["h1_seminorm_convergence_rate"], limits["min_h1_rate"]),
        ("pde_linear_residual", max(residuals) <= limits["max_residual_relative"], residuals, limits["max_residual_relative"])]
    checks = [{"code": code, "status": "PASS" if passed else "FAIL", "observed": value, "limit": limit} for code, passed, value, limit in conditions]
    valid, failures = all(row["status"] == "PASS" for row in checks), ", ".join(row["code"] for row in checks if row["status"] == "FAIL")
    metrics = {"l2_error": fine["l2_error"], "h1_seminorm_error": fine["h1_seminorm_error"], "l2_convergence_rate": fine["l2_convergence_rate"], "h1_seminorm_convergence_rate": fine["h1_seminorm_convergence_rate"], "linear_residual_relative": max(residuals)}
    for component in range(2):
        for name in ("l2_error", "h1_seminorm_error"): metrics[f"component_{component}_{name}"] = fine["components"][component][name]
    return {"checks": checks, "metrics": {name: {"value": value, "unit": "1", "valid": valid, **({"reason": f"Coupled numerical validation failed: {failures}"} if not valid else {})} for name, value in metrics.items()},
            "mesh_studies": observed, "reference": {**copy.deepcopy(settings["problem"]["reference"]), "components": list(COMPONENTS), "family": "coupled_diffusion", "error_quadrature_degree": 8,
            "diffusion_axis": "component_rows_of_grad_u", "h1_semantics": "full Frobenius gradient seminorm", "interface_semantics": "CG shared value and natural operator-flux continuity; no dS load"},
            "pending_validations": ["physical_validation", "model_qualification"], "limitations": list(LIMITATIONS)}
