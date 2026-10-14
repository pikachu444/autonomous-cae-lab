"""Native ParaView analysis; VTK owns interpolation and geometry operations.

Comparisons require explicit compatible declarations. The caller verifies admitted
readers and their file pins. No helper changes animation time or creates a view.
"""
from copy import deepcopy
import hashlib
import json
import math
import re
import uuid

import numpy as np
from paraview import simple as p, servermanager
try:
    from paraview.numpy_support import vtk_to_numpy
except ImportError:
    from vtk.util.numpy_support import vtk_to_numpy
try:
    from . import external
except ImportError:
    import external

OUTPUT_ARRAYS = {"a": "A_original", "b": "B_at_A", "delta": "B_minus_A",
                 "percent": "percent_change", "valid": "comparison_valid",
                 "percent_valid": "percent_valid", "reason": "comparison_reason",
                 "percent_reason": "percent_reason"}
REASONS = {0: "valid", 1: "outside_b_domain", 2: "nonfinite_a", 3: "nonfinite_b",
           4: "nonfinite_difference", 5: "zero_a", 6: "nonfinite_percent", 7: "percent_disabled", 8: "nonfinite_denominator"}
DECLARATIONS = ("quantity", "units", "measure", "frame", "coordinate_units", "coordinate_frame")


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _name(namespace, role):
    if not isinstance(namespace, str) or not namespace.strip():
        raise ValueError("A nonempty native registration namespace is required")
    return namespace + " | " + role + " | " + uuid.uuid4().hex


def _preserve_active():
    return p.GetActiveSource(), p.GetActiveView()


def _restore_active(previous):
    p.SetActiveSource(previous[0])
    p.SetActiveView(previous[1])


def _fetch(source):
    source.UpdatePipeline()
    return servermanager.Fetch(source)


def _scalar(data, name):
    array = data.GetPointData().GetArray(name)
    if array is None or array.GetNumberOfComponents() != 1:
        raise ValueError("Comparison requires an existing numeric scalar POINTS array: " + str(name))
    if array.GetNumberOfTuples() != data.GetNumberOfPoints():
        raise ValueError("Point array length does not match native geometry")
    return np.asarray(vtk_to_numpy(array)).reshape(-1)


def _mesh(data):
    if data is None or data.GetClassName() != "vtkUnstructuredGrid":
        raise ValueError("Comparison requires a single native vtkUnstructuredGrid")
    if not data.GetNumberOfPoints() or not data.GetNumberOfCells():
        raise ValueError("Comparison requires a nonempty tetrahedral grid")
    coords = np.asarray(vtk_to_numpy(data.GetPoints().GetData()), dtype=np.float64)
    if coords.shape != (data.GetNumberOfPoints(), 3) or not np.isfinite(coords).all():
        raise ValueError("Native coordinates must be finite 3D points")
    connectivity = np.empty((data.GetNumberOfCells(), 4), dtype=np.int64)
    for index in range(data.GetNumberOfCells()):
        if data.GetCellType(index) != 10:
            raise ValueError("Comparison supports only linear VTK_TETRA cells (type 10)")
        ids = data.GetCell(index).GetPointIds()
        if ids.GetNumberOfIds() != 4:
            raise ValueError("Invalid linear tetrahedral connectivity")
        connectivity[index] = [ids.GetId(j) for j in range(4)]
    h = hashlib.sha256()
    h.update(np.asarray(coords.shape, dtype="<i8").tobytes())
    h.update(coords.astype("<f8").tobytes())
    h.update(np.asarray(connectivity.shape, dtype="<i8").tobytes())
    h.update(connectivity.astype("<i8").tobytes())
    return coords, connectivity, h.hexdigest()


def _values_hash(values):
    # Canonical finite mask and NaN payload; distinguish +/-Inf without JSON NaN.
    values = np.asarray(values, dtype="<f8").copy()
    values[np.isnan(values)] = np.nan
    return hashlib.sha256(values.tobytes()).hexdigest()


def _stats(values):
    values = np.asarray(values)
    finite = np.isfinite(values)
    return {"finite": int(finite.sum()), "nonfinite": int((~finite).sum()),
            "min": float(values[finite].min()) if finite.any() else None,
            "max": float(values[finite].max()) if finite.any() else None}


def _times(source):
    source.UpdatePipelineInformation()
    return [float(t) for t in getattr(source, "TimestepValues", [])]


def _validate_recipe(a, b, recipe):
    if not isinstance(recipe, dict) or recipe.get("method") not in ("same_mesh", "linear_tetra_b_to_a"):
        raise ValueError("Choose same_mesh or linear_tetra_b_to_a explicitly")
    tolerance = recipe.get("tolerance")
    if type(tolerance) not in (int, float) or not math.isfinite(tolerance) or tolerance < 0:
        raise ValueError("An explicit finite nonnegative native tolerance is required")
    for source, side in ((a, "a"), (b, "b")):
        row = recipe.get(side)
        if not isinstance(row, dict):
            raise ValueError("Declare both comparison sides")
        for key in ("source_ref", "array", *DECLARATIONS):
            if not isinstance(row.get(key), str) or not row[key].strip():
                raise ValueError("Declare comparison " + side + " " + key + " explicitly")
        if row.get("association") != "POINTS":
            raise ValueError("Comparison supports scalar POINTS arrays only")
        if not {"time", "time_units", "time_origin"} <= row.keys():
            raise ValueError("Declare time, time_units and time_origin explicitly")
        native_times = _times(source)
        if row["time"] is None:
            if native_times or row["time_units"] is not None or row["time_origin"] is not None:
                raise ValueError("Temporal results require an exact declared native time and clock")
        else:
            if (type(row["time"]) not in (int, float) or not math.isfinite(row["time"])
                    or row["time"] not in native_times):
                raise ValueError("Choose an exact common native timestep; time interpolation is unsupported")
            for key in ("time_units", "time_origin"):
                if not isinstance(row[key], str) or not row[key].strip():
                    raise ValueError("Declare the temporal clock's " + key)
    for key in (*DECLARATIONS, "time", "time_units", "time_origin"):
        if recipe["a"][key] != recipe["b"][key]:
            raise ValueError("Comparison requires identical declared " + key + "; conversion is explicit")


def _freeze(source, time, namespace, proxies):
    if time is None:
        return source
    if not callable(getattr(p, "ForceTime", None)):
        raise RuntimeError("Native ForceTime is required to freeze comparison time")
    result = p.ForceTime(registrationName=_name(namespace, "frozen native time"), Input=source)
    proxies.append(result)
    required = {"ForcedTime", "IgnorePipelineTime"}
    if not required <= set(result.ListProperties()):
        raise RuntimeError("Native ForceTime lacks ForcedTime/IgnorePipelineTime")
    result.ForcedTime = float(time)
    result.IgnorePipelineTime = 1
    result.UpdatePipeline()
    return result


# The arithmetic executes server-side. It receives native resampling output;
# this script does not locate cells, derive weights, or interpolate values.
ARITHMETIC_SCRIPT = r'''
import numpy as np
try:
    from paraview.numpy_support import vtk_to_numpy, numpy_to_vtk
except ImportError:
    from vtk.util.numpy_support import vtk_to_numpy, numpy_to_vtk
original = self.GetInputDataObject(0, 0)
sampled = self.GetInputDataObject(0, 1)
out = self.GetOutputDataObject(0)
out.ShallowCopy(original)
out.GetPointData().Initialize()
out.GetCellData().Initialize()
out.GetFieldData().Initialize()
# Only original A identity arrays survive, never interpolated B identities.
import re
for source_data, output_data in ((original.GetPointData(), out.GetPointData()),
                                  (original.GetCellData(), out.GetCellData())):
    identities = [source_data.GetGlobalIds(), source_data.GetPedigreeIds()]
    for i in range(source_data.GetNumberOfArrays()):
        arr = source_data.GetAbstractArray(i)
        name = arr.GetName() or ''
        if arr in identities or re.search(r'(?:^|_)ids?$|Ids?$|IDs?$', name) or name.lower() in {'nativenodeid', 'nativeelementid', 'globalnodeid', 'globalelementid', 'vtkoriginalpointids', 'vtkoriginalcellids', 'globalids', 'pedigreeids'}:
            output_data.AddArray(arr)
a = np.asarray(vtk_to_numpy(original.GetPointData().GetArray(A_NAME)), dtype=np.float64).reshape(-1)
b = np.asarray(vtk_to_numpy(sampled.GetPointData().GetArray(B_NAME)), dtype=np.float64).reshape(-1).copy()
if METHOD == 'same_mesh':
    inside = np.ones(len(a), dtype=bool)
else:
    mask = sampled.GetPointData().GetArray('vtkValidPointMask')
    if mask is None:
        raise RuntimeError('Native resampling did not produce vtkValidPointMask')
    inside = np.asarray(vtk_to_numpy(mask)).reshape(-1) != 0
finite_a = np.isfinite(a)
finite_b = np.isfinite(b)
valid = inside & finite_a & finite_b
reason = np.zeros(len(a), dtype=np.uint8)
reason[~inside] = 1
reason[inside & ~finite_a] = 2
reason[inside & finite_a & ~finite_b] = 3
b[~inside | ~finite_b] = np.nan
with np.errstate(over='ignore', divide='ignore', invalid='ignore'):
    delta = b - a
valid &= np.isfinite(delta)
reason[inside & finite_a & finite_b & ~np.isfinite(delta)] = 4
delta[~valid] = np.nan
percent_valid = valid & (a != 0)
percent_reason = reason.copy()
percent_reason[valid & (a == 0)] = 5
percent = np.full(len(a), np.nan)
with np.errstate(over='ignore', divide='ignore', invalid='ignore'):
    percent[percent_valid] = 100.0 * (delta[percent_valid] / np.abs(a[percent_valid]))
percent_reason[percent_valid & ~np.isfinite(percent)] = 6
percent_valid &= np.isfinite(percent)
percent[~percent_valid] = np.nan
for key, values in [('a', a), ('b', b), ('delta', delta), ('percent', percent),
                    ('valid', valid.astype(np.uint8)), ('percent_valid', percent_valid.astype(np.uint8)),
                    ('reason', reason), ('percent_reason', percent_reason)]:
    arr = numpy_to_vtk(np.ascontiguousarray(values), deep=True)
    arr.SetName(NAMES[key])
    out.GetPointData().AddArray(arr)
mask = numpy_to_vtk(inside.astype(np.uint8), deep=True)
mask.SetName('vtkValidPointMask')
out.GetPointData().AddArray(mask)
'''


def _arithmetic_script(recipe, b_name):
    return ("A_NAME = " + repr(recipe["a"]["array"]) + "\nB_NAME = " + repr(b_name)
            + "\nMETHOD = " + repr(recipe["method"]) + "\nNAMES = " + repr(OUTPUT_ARRAYS)
            + "\n" + ARITHMETIC_SCRIPT)


def _program(source, script, namespace, role, proxies):
    result = p.ProgrammableFilter(registrationName=_name(namespace, role), Input=source)
    proxies.append(result)
    result.Script = script
    result.UpdatePipeline()
    return result


def build_comparison(a, b, recipe, namespace="Comparison"):
    if recipe.get("version") == 2:
        from .comparison_native import build
        return build(a, b, recipe, namespace)
    """Create hidden, owned native proxies and return JSON summary plus handles."""
    previous = _preserve_active()
    bundle = {"source": None, "proxies": [], "summary": {}}
    proxies = bundle["proxies"]
    try:
        _validate_recipe(a, b, recipe)
        af = _freeze(a, recipe["a"]["time"], namespace, proxies)
        bf = _freeze(b, recipe["b"]["time"], namespace, proxies)
        ad, bd = _fetch(af), _fetch(bf)
        ac, ai, ah = _mesh(ad)
        bc, bi, bh = _mesh(bd)
        av, bv = _scalar(ad, recipe["a"]["array"]), _scalar(bd, recipe["b"]["array"])
        if recipe["method"] == "same_mesh":
            if not (np.array_equal(ac, bc) and np.array_equal(ai, bi)):
                raise ValueError("same_mesh requires exact ordered coordinates and connectivity; IDs do not prove correspondence")
            sampled, b_name = bf, recipe["b"]["array"]
        else:
            selected = external.physical_input(bf, [("POINTS", recipe["b"]["array"])])
            proxies.append(selected)
            p.RenameSource(_name(namespace, "B physical scalar only"), selected)
            # Rename the selected physical scalar to prevent any destination collision.
            b_name = "__post_B_scalar"
            renamed = _program(selected,
                "source = self.GetInputDataObject(0, 0)\nout = self.GetOutputDataObject(0)\nout.ShallowCopy(source)\n"
                "arr = source.GetPointData().GetArray(" + repr(recipe["b"]["array"]) + ")\n"
                "copy = arr.NewInstance()\ncopy.DeepCopy(arr)\ncopy.SetName(" + repr(b_name) + ")\n"
                "out.GetPointData().Initialize()\nout.GetPointData().AddArray(copy)\n"
                "out.GetCellData().Initialize()\nout.GetFieldData().Initialize()\n",
                namespace, "B scalar sampling input", proxies)
            sampled = p.ResampleWithDataset(registrationName=_name(namespace, "native B sampled at A"),
                                           SourceDataArrays=renamed, DestinationMesh=af)
            proxies.append(sampled)
            for key, value in {"ComputeTolerance": 0, "Tolerance": float(recipe["tolerance"]),
                               "SnapToCellWithClosestPoint": 0, "MarkBlankPointsAndCells": 0,
                               "PassPointArrays": 0, "PassCellArrays": 0, "PassFieldArrays": 0,
                               "CategoricalData": 0}.items():
                if key not in sampled.ListProperties():
                    raise RuntimeError("Native ResampleWithDataset lacks required property " + key)
                setattr(sampled, key, value)
            sampled.UpdatePipeline()
        result = _program([af, sampled], _arithmetic_script(recipe, b_name), namespace,
                          "point scalar difference", proxies)
        bundle["source"] = result
        output = _fetch(result)
        _, _, output_mesh = _mesh(output)
        if output_mesh != ah:
            raise RuntimeError("Native comparison changed the destination geometry")
        fields = {key: _scalar(output, name) for key, name in OUTPUT_ARRAYS.items()}
        counts = {REASONS[code]: int((fields["reason"] == code).sum()) for code in range(5)}
        bundle["summary"] = {"recipe": deepcopy(recipe), "arrays": deepcopy(OUTPUT_ARRAYS),
                             "points": len(ac), "cells": len(ai), "mesh_hash_a": ah, "mesh_hash_b": bh,
                             "original_a_id_arrays": _identity_arrays(ad.GetPointData()),
                             "mesh_hash": output_mesh, "input_hash_a": _values_hash(av),
                             "input_hash_b": _values_hash(bv), "finitecounts": {key: _stats(value) for key, value in fields.items()},
                             "validity_counts": counts, "percent_zero_a": int((fields["percent_reason"] == 5).sum()),
                             "output_hash": _comparison_fingerprint(output)["output_hash"],
                             "qualification": "UNQUALIFIED", "percent_definition": "100 * (B_at_A - A) / abs(A)"}
        bundle["summary"]["graph"] = graph_signature(bundle)
        return bundle
    except Exception:
        cleanup(bundle)
        raise
    finally:
        _restore_active(previous)



def _comparison_fingerprint(data, *, version=1):
    if version == 2:
        from .comparison_native import geometry
        _, _, mesh_hash = geometry(data)
    else:
        _, _, mesh_hash = _mesh(data)
    arrays = []
    for association, attrs in (("POINTS", data.GetPointData()), ("CELLS", data.GetCellData())):
        for i in range(attrs.GetNumberOfArrays()):
            arr = attrs.GetAbstractArray(i)
            if arr.IsA("vtkDataArray"):
                values = np.asarray(vtk_to_numpy(arr)).copy()
                if values.dtype.kind == "f":
                    values[np.isnan(values)] = np.nan
                payload = values.astype(values.dtype.newbyteorder("<")).tobytes()
                checksum = hashlib.sha256(payload).hexdigest()
            else:
                checksum = _digest([arr.GetVariantValue(j).ToString()
                                    for j in range(arr.GetNumberOfValues())])
            arrays.append({"association": association, "name": arr.GetName(),
                           "components": arr.GetNumberOfComponents(), "tuples": arr.GetNumberOfTuples(),
                           "type": arr.GetDataTypeAsString(), "sha256": checksum})
    arrays.sort(key=lambda row: (row["association"], row["name"] or ""))
    fields = {key: _scalar(data, name) for key, name in OUTPUT_ARRAYS.items()}
    return {"mesh_hash": mesh_hash, "output_hash": _digest({"mesh_hash": mesh_hash, "arrays": arrays}),
            "finitecounts": {key: _stats(values) for key, values in fields.items()}}


def output_fingerprint(bundle):
    """Recompute comparison geometry, output arrays/IDs and finite counts natively.

    Callers compare this with the validated summary before consuming an applied
    result. This detects changed upstream data even when its labels are stable.
    """
    if bundle.get("summary", {}).get("comparison_version") == 3:
        from .curve_native import fingerprint
        return fingerprint(_fetch(bundle["source"]))
    return _comparison_fingerprint(_fetch(bundle["source"]), version=bundle.get("summary", {}).get("comparison_version", 1))


def cleanup(bundle):
    """Delete only owned proxies in reverse dependency order; inputs remain."""
    failures = []
    for proxy in reversed(bundle.get("proxies", [])):
        try:
            p.Delete(proxy)
        except Exception as error:
            failures.append(str(error))
    for proxy in bundle.get('selection_proxies', []):
        try:
            p.Delete(proxy)
        except Exception as error:
            failures.append(str(error))
    bundle['selection_proxies'] = []
    bundle["proxies"] = []
    bundle["source"] = None
    if failures:
        raise RuntimeError("Owned comparison cleanup failed: " + "; ".join(failures))


def _label(proxy, registered):
    labels = [label for (label, _), candidate in registered.items() if candidate == proxy]
    if len(labels) != 1:
        raise RuntimeError("Native graph node must have one unique registration label")
    # Duplicate labels across different proxies are equally ambiguous on restore.
    if sum(label == labels[0] for label, _ in registered) != 1:
        raise RuntimeError("Native graph registration label is duplicated: " + labels[0])
    return labels[0]


def _property_data(value, *, raw_ints=False):
    """Read checked native values without enum-domain display-label substitution."""
    native = getattr(value, 'SMProperty', None)
    if native is None:
        native = value
    if (raw_ints and callable(getattr(native, 'IsA', None))
            and native.IsA('vtkSMIntVectorProperty')):
        # EnumerationProperty.GetData uses its domain's text, which may be
        # empty before PVSM Save and numeric after reload. Read checked values;
        # pending/unchecked edits still belong to the existing owner guards.
        values = [native.GetElement(i) for i in range(native.GetNumberOfElements())]
        if native.GetRepeatable() or len(values) > 1:
            return values
        return values[0] if values else None
    if callable(getattr(value, 'GetData', None)):
        return value.GetData()
    if callable(getattr(native, 'GetNumberOfElements', None)) and callable(getattr(native, 'GetElement', None)):
        return [native.GetElement(i) for i in range(native.GetNumberOfElements())]
    if callable(getattr(native, 'GetNumberOfProxies', None)):
        return [servermanager._getPyProxy(native.GetProxy(i)) for i in range(native.GetNumberOfProxies())]
    raise RuntimeError('Unsupported native property data: ' + type(value).__name__)


def _property_value(value, registered, depth=0, *, raw_ints=False):
    if depth > 8:
        raise RuntimeError("Native graph property nesting exceeds eight levels")
    if value is None or type(value) in (str, bool, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    # Property wrappers forward GetXMLName to vtkSMProperty too. They are not
    # proxies and have no ListProperties; unwrap their typed data first.
    sm_property = getattr(value, 'SMProperty', None)
    is_property = sm_property is not None or (callable(getattr(value, 'IsA', None)) and value.IsA('vtkSMProperty'))
    if is_property:
        data = _property_data(value, raw_ints=raw_ints)
        if data is value:
            raise RuntimeError('Native property returned itself instead of typed data')
        return _property_value(data, registered, depth + 1, raw_ints=raw_ints)
    if callable(getattr(value, 'ListProperties', None)) and callable(getattr(value, 'GetXMLName', None)):
        labels = [label for (label, _), proxy in registered.items() if proxy == value]
        if labels:
            return {"source_label": _label(value, registered), "port": int(getattr(value, "Port", 0))}
        return {"proxy_type": value.GetXMLName(), "properties": _properties(value, registered, depth + 1, raw_ints=raw_ints)}
    if isinstance(value, (tuple, list)) or hasattr(value, "__iter__"):
        return [_property_value(item, registered, depth + 1, raw_ints=raw_ints) for item in value]
    raise RuntimeError("Unsupported native graph property value: " + type(value).__name__)


def _properties(proxy, registered, depth=0, *, raw_ints=False):
    result = {}
    for key in sorted(proxy.ListProperties()):
        prop = proxy.GetProperty(key)
        if prop is None:
            continue
        smprop = getattr(prop, "SMProperty", prop)
        if callable(getattr(smprop, "GetInformationOnly", None)) and smprop.GetInformationOnly():
            continue
        if callable(getattr(smprop, "GetIsInternal", None)) and smprop.GetIsInternal():
            continue
        # Keep array-selection/string/proxy wrappers' typed interfaces. The raw
        # mode changes only native integer vectors, before any enum GetData.
        value = _property_data(prop, raw_ints=raw_ints)
        result[key] = _property_value(value, registered, depth + 1, raw_ints=raw_ints)
    return result


def graph_signature(bundle, *, raw_ints=False):
    """Native properties and input links bound by labels, surviving PVSM reload.

    Existing analysis histories retain their legacy encoding by default.
    Contact overlays explicitly opt into stable checked vtkSM integer values.
    """
    registered = p.GetSources()
    nodes = [{"label": _label(proxy, registered), "type": proxy.GetXMLName(),
              "properties": _properties(proxy, registered, raw_ints=raw_ints)} for proxy in bundle.get("proxies", [])]
    nodes.sort(key=lambda row: row["label"])
    graph = {"nodes": nodes, "output_label": _label(bundle["source"], registered)}
    if raw_ints:
        graph["property_encoding"] = "vtk-sm-int-v1"
    return {**graph, "sha256": _digest(graph)}


def sample_page(bundle, offset=0, limit=100, point_index=None):
    """Bounded JSON samples from the actual native comparison output."""
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError("Sample offset must be nonnegative and page limit must be 1..1000")
    data = _fetch(bundle["source"])
    n = data.GetNumberOfPoints()
    if point_index is not None:
        if type(point_index) is not int or not 0 <= point_index < n:
            raise ValueError("Choose an original A point_index in the native point range")
        indices = [point_index]
    else:
        indices = range(offset, min(n, offset + limit))
    values = {key: _scalar(data, name) for key, name in OUTPUT_ARRAYS.items()}
    pd = data.GetPointData()
    # ProgrammableFilter can retain physical arrays in addition to its declared
    # outputs. Being left over never makes an array an original identity.
    identity_names = bundle.get('summary', {}).get('original_a_id_arrays')
    if identity_names is None:  # Retained r3 records predate the explicit list.
        identity_names = _identity_arrays(pd)
    rows = []
    for index in indices:
        identities = {}
        for name in identity_names:
            arr = pd.GetAbstractArray(name)
            if arr is not None and arr.GetNumberOfComponents() == 1:
                if arr.IsA("vtkDataArray"):
                    value = vtk_to_numpy(arr)[index].item()
                    identities[name] = value if not isinstance(value, float) or math.isfinite(value) else None
                else:
                    identities[name] = arr.GetVariantValue(index).ToString()
        row = {"point_index": index, "coordinates": list(data.GetPoint(index)), "original_a_ids": identities}
        for key in ("a", "b", "delta", "percent"):
            value = float(values[key][index])
            row[key] = value if math.isfinite(value) else None
        row.update(valid=bool(values["valid"][index]), percent_valid=bool(values["percent_valid"][index]),
                   validity_reason=REASONS[int(values["reason"][index])],
                   percent_reason=REASONS[int(values["percent_reason"][index])])
        if bundle.get("summary", {}).get("comparison_version") == 2:
            for key, name in (("a_raw", "A_source_value"), ("b_raw", "B_source_sampled")):
                value = float(_scalar(data, name)[index])
                row[key] = value if math.isfinite(value) else None
            for name in ("A_original_components", "B_sampled_original_components", "A_common_components", "B_common_components"):
                arr = pd.GetArray(name)
                if arr is None:
                    raise ValueError("Retained comparison component array is missing")
                row[name] = [float(v) if math.isfinite(v) else None for v in arr.GetTuple(index)]
        rows.append(row)
    return {"points": n, "offset": point_index if point_index is not None else offset,
            "limit": 1 if point_index is not None else limit, "rows": rows,
            "next_offset": None if point_index is not None or offset + limit >= n else offset + limit}


def inspect_source(source, array=None, time=None):
    """Inspect actual tetrahedral geometry without scene-time mutation."""
    previous = _preserve_active()
    owned = []
    try:
        native_times = _times(source)
        if native_times and (type(time) not in (int, float) or time not in native_times):
            raise ValueError("Choose an exact native timestep for inspection")
        if not native_times and time is not None:
            raise ValueError("Non-temporal data has no native timestep")
        frozen = _freeze(source, time, "Inspect", owned)
        data = _fetch(frozen)
        coords, cells, mesh_hash = _mesh(data)
        arrays = []
        for association, attrs in (("POINTS", data.GetPointData()), ("CELLS", data.GetCellData())):
            for i in range(attrs.GetNumberOfArrays()):
                item = attrs.GetArray(i)
                if item is not None:
                    arrays.append({"name": item.GetName(), "association": association,
                                   "components": item.GetNumberOfComponents(), "tuples": item.GetNumberOfTuples(),
                                   "units": None, "quantity": None, "frame": None, "metadata_status": "UNKNOWN"})
        result = {"points": len(coords), "cells": len(cells), "mesh_hash": mesh_hash,
                  "bounds": list(data.GetBounds()), "time": time, "timesteps": native_times, "arrays": arrays}
        if array is not None:
            values = _scalar(data, array)
            result.update(array=array, statistics=_stats(values), array_hash=_values_hash(values))
        return result
    finally:
        cleanup({"proxies": owned})
        _restore_active(previous)


FILTER_KINDS = {"Slice", "Clip", "Contour", "WarpByVector", "PlotOverLine"}


def _number(value, label, nonnegative=False):
    if type(value) not in (int, float) or not math.isfinite(value) or (nonnegative and value < 0):
        raise ValueError(label + " must be a finite" + (" nonnegative" if nonnegative else "") + " number")
    return float(value)


def _vector(value, label, nonzero=False):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(label + " needs three finite coordinates")
    result = [_number(item, label) for item in value]
    if nonzero and not any(result):
        raise ValueError(label + " must be nonzero")
    return result


def _boolean(settings, key, default=False):
    value = settings.get(key, default)
    if type(value) is not bool:
        raise ValueError(key + " must be an explicit boolean")
    return int(value)


def _identity_arrays(attributes):
    # VTK/NumPy wrappers overload equality with array-valued results. In
    # particular ``array in [None, None]`` can be truthy for a physical array.
    # These roles belong to this exact attributes collection, so compare the
    # explicitly declared names, never array equality or inferred value type.
    declared = {arr.GetName() for arr in (attributes.GetGlobalIds(), attributes.GetPedigreeIds())
                if arr is not None and arr.GetName()}
    return sorted({arr.GetName() for i in range(attributes.GetNumberOfArrays())
                   if (arr := attributes.GetAbstractArray(i)) is not None and arr.GetName()
                   and arr.GetNumberOfComponents() == 1
                   and (arr.GetName() in declared or _identity(arr.GetName()))})


def _identity(name):
    return (not name or name.lower().endswith("_input")
            or bool(re.search(r"(?:^|_)ids?$|Ids?$|IDs?$", name))
            or name.lower() in {"nativenodeid", "nativeelementid", "globalnodeid", "globalelementid",
                                "vtkoriginalpointids", "vtkoriginalcellids", "globalids", "pedigreeids"})


def _selected_physical(source, data, settings, namespace, proxies):
    if "array" in settings:
        associations = [(settings.get("association", "POINTS"), settings["array"])]
    else:
        associations = [(association, attrs.GetArrayName(i))
                        for association, attrs in (("POINTS", data.GetPointData()), ("CELLS", data.GetCellData()))
                        for i in range(attrs.GetNumberOfArrays())
                        if attrs.GetArray(i) is not None and not _identity(attrs.GetArrayName(i))]
    if not associations:
        raise ValueError("Select an existing physical response array for native filtering")
    selected = external.physical_input(source, associations)
    proxies.append(selected)
    p.RenameSource(_name(namespace, "physical filter input"), selected)
    return selected


def _assign(proxy, settings):
    available = set(proxy.ListProperties())
    for key, value in settings.items():
        if key not in available:
            raise RuntimeError("Native " + proxy.GetXMLName() + " lacks required property " + key)
        setattr(proxy, key, value)


def create_filter(source, kind, settings, namespace="Filter"):
    """Create a hidden native filter bundle; editing is recreation by its caller.

    Slice/Clip carry all numeric non-identity arrays unless an exact response is
    selected. Contour, WarpByVector and PlotOverLine require an explicit array.
    Temporal sources require settings.time to pin an exact native timestep.
    """
    if kind not in FILTER_KINDS or not isinstance(settings, dict):
        raise ValueError("Choose an admitted native filter and explicit settings")
    previous = _preserve_active()
    bundle = {"source": None, "proxies": [], "summary": {}}
    proxies = bundle["proxies"]
    try:
        time = settings.get("time")
        native_times = _times(source)
        if native_times:
            if type(time) not in (int, float) or not math.isfinite(time) or time not in native_times:
                raise ValueError("Choose an exact native timestep for filtering")
        elif time is not None:
            raise ValueError("Non-temporal data has no native timestep")
        frozen = _freeze(source, time, namespace, proxies)
        data = _fetch(frozen)
        attributes = {}
        if kind in ("Slice", "Clip"):
            origin = _vector(settings.get("origin"), "origin")
            normal = _vector(settings.get("normal"), "normal", nonzero=True)
            if kind == "Slice":
                offsets = settings.get("offsets", [0.0])
                if not isinstance(offsets, list) or not 1 <= len(offsets) <= 1024:
                    raise ValueError("Slice offsets need 1..1024 finite values")
                attributes = {"SliceOffsetValues": [_number(value, "slice offset") for value in offsets],
                              "Triangulatetheslice": _boolean(settings, "triangulate", True),
                              "Crinkleslice": _boolean(settings, "crinkle")}
            else:
                attributes = {"Invert": _boolean(settings, "invert"), "Crinkleclip": _boolean(settings, "crinkle"),
                              "Value": 0.0, "UseValueAsOffset": 0}
        else:
            if settings.get("association", "POINTS") != "POINTS" or not isinstance(settings.get("array"), str):
                raise ValueError(kind + " requires an exact POINTS array")
            array = data.GetPointData().GetArray(settings["array"])
            if array is None or _identity(settings["array"]):
                raise ValueError("Select an existing physical point array")
            if kind == "WarpByVector":
                if array.GetNumberOfComponents() != 3:
                    raise ValueError("WarpByVector requires a native three-component point vector")
                attributes = {"Vectors": ["POINTS", settings["array"]],
                              "ScaleFactor": _number(settings.get("scale_factor"), "scale_factor")}
            else:
                if array.GetNumberOfComponents() != 1:
                    raise ValueError(kind + " requires a scalar point response")
                if kind == "Contour":
                    values = settings.get("values")
                    if not isinstance(values, list) or not 1 <= len(values) <= 1024:
                        raise ValueError("Contour requires 1..1024 explicit finite isovalues")
                    attributes = {"ContourBy": ["POINTS", settings["array"]],
                                  "Isosurfaces": [_number(value, "contour value") for value in values]}
                else:
                    point1, point2 = _vector(settings.get("point1"), "point1"), _vector(settings.get("point2"), "point2")
                    if point1 == point2:
                        raise ValueError("Line endpoints must differ")
                    resolution = settings.get("resolution")
                    if type(resolution) is not int or not 1 <= resolution <= 10000:
                        raise ValueError("Line resolution must be an integer in 1..10000")
                    attributes = {"Point1": point1, "Point2": point2, "Resolution": resolution,
                                  "SamplingPattern": "Sample Uniformly", "ComputeTolerance": 0,
                                  "Tolerance": _number(settings.get("tolerance"), "tolerance", nonnegative=True)}
        upstream = frozen if kind == "WarpByVector" else _selected_physical(frozen, data, settings, namespace, proxies)
        constructor = getattr(p, kind, None)
        if not callable(constructor):
            raise RuntimeError("Native " + kind + " is unavailable")
        result = constructor(registrationName=_name(namespace, kind), Input=upstream)
        proxies.append(result)
        if kind in ("Slice", "Clip"):
            key = "SliceType" if kind == "Slice" else "ClipType"
            _assign(result, {key: "Plane"})
            _assign(getattr(result, key), {"Origin": origin, "Normal": normal})
        _assign(result, attributes)
        result.UpdatePipeline()
        bundle["source"] = result
        output = _fetch(result)
        bundle["summary"] = {"kind": kind, "settings": deepcopy(settings), "time": time,
                             "points": output.GetNumberOfPoints(), "cells": output.GetNumberOfCells(),
                             "data_type": output.GetClassName(), "qualification": "UNQUALIFIED"}
        bundle["summary"]["graph"] = graph_signature(bundle)
        return bundle
    except Exception:
        cleanup(bundle)
        raise
    finally:
        _restore_active(previous)


def sample_native_points(source, array, offset=0, limit=100, point_index=None):
    """Bounded native POINTS values for original picks or native line output.

    Temporal callers must supply their existing ForceTime-filtered proxy. Raw
    values are never converted to a different association or interpolated here.
    """
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError("Sample offset must be nonnegative and page limit must be 1..1000")
    data = _fetch(source)
    count = data.GetNumberOfPoints()
    values = data.GetPointData().GetArray(array)
    if values is None or values.GetNumberOfTuples() != count:
        raise ValueError("Select an existing numeric POINTS array")
    if point_index is not None:
        if type(point_index) is not int or not 0 <= point_index < count:
            raise ValueError("Choose a native point_index in the point range")
        indices = [point_index]
    else:
        indices = range(offset, min(count, offset + limit))
    native = np.asarray(vtk_to_numpy(values))
    mask = data.GetPointData().GetArray("vtkValidPointMask")
    valid_mask = vtk_to_numpy(mask) if mask is not None else None
    rows = []
    for index in indices:
        raw = np.asarray(native[index]).reshape(-1)
        valid = bool(np.isfinite(raw).all()) and (valid_mask is None or bool(valid_mask[index]))
        converted = [float(value) if valid and math.isfinite(float(value)) else None for value in raw]
        rows.append({"point_index": index, "coordinates": list(data.GetPoint(index)),
                     "value": converted[0] if len(converted) == 1 else converted, "valid": valid,
                     "validity_reason": "valid" if valid else ("outside_domain" if valid_mask is not None and not valid_mask[index] else "nonfinite")})
    return {"array": array, "association": "POINTS", "points": count,
            "components": values.GetNumberOfComponents(), "offset": point_index if point_index is not None else offset,
            "rows": rows, "next_offset": None if point_index is not None or offset + limit >= count else offset + limit}


def sample_data(source, offset=0, limit=100, point_index=None, association="POINTS", declarations=None):
    """Return bounded actual native rows, including line arc length if produced.

    Array names are retained. Unknown engineering metadata remains unknown.
    Cell rows carry their native point connectivity instead of invented centers.
    """
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError("Sample offset must be nonnegative and page limit must be 1..1000")
    if association not in ("POINTS", "CELLS"):
        raise ValueError("Choose native POINTS or CELLS without association conversion")
    data = _fetch(source)
    attrs = data.GetPointData() if association == "POINTS" else data.GetCellData()
    count = data.GetNumberOfPoints() if association == "POINTS" else data.GetNumberOfCells()
    if point_index is not None:
        if association != "POINTS" or type(point_index) is not int or not 0 <= point_index < count:
            raise ValueError("Choose a native point_index in the point range")
        indices = [point_index]
    else:
        indices = range(offset, min(count, offset + limit))
    arrays = []
    values = {}
    for i in range(attrs.GetNumberOfArrays()):
        arr = attrs.GetArray(i)
        if arr is None or not arr.GetName() or arr.GetNumberOfTuples() != count:
            continue
        arrays.append({"name": arr.GetName(), "association": association, "components": arr.GetNumberOfComponents(),
                       "quantity": None, "units": None, "frame": None, "measure": None, "metadata_status": "UNKNOWN"})
        values[arr.GetName()] = np.asarray(vtk_to_numpy(arr))
    declared = {row['name']: row for row in (declarations or {}).get('arrays', [])
                if row.get('association') == association and row.get('validity_policy') == 'declared_array'}
    mask_names = {'vtkValidPointMask', 'vtkGhostType'}
    if declared:
        mask_names.update(('comparison_valid', 'percent_valid', 'A_finite', 'B_finite', 'spatial_valid'))
    declared_flags = {}
    for name, declaration in declared.items():
        if name not in values:
            raise ValueError('Declared sample array is missing: ' + name)
        masks = declaration.get('validity_masks', [])
        spatial = declaration.get('spatial_mask')
        for key in [*masks, *([spatial] if spatial else [])]:
            flags = values.get(key)
            if flags is None or np.asarray(flags).shape not in ((count,), (count, 1)):
                raise ValueError('Declared sample mask is missing or has a different location: ' + key)
            flat = np.asarray(flags).reshape(-1)
            declared_flags[key] = np.isfinite(flat) & (flat != 0)
            mask_names.add(key)
    rows = []
    for index in indices:
        row = {"point_index" if association == "POINTS" else "cell_index": index, "values": {}, "validity": {}}
        if association == "POINTS":
            row["coordinates"] = list(data.GetPoint(index))
        else:
            connectivity = data.GetCell(index).GetPointIds()
            row["point_indices"] = [connectivity.GetId(j) for j in range(connectivity.GetNumberOfIds())]
        if declared:
            generic_mask = np.asarray(values["vtkValidPointMask"][index]).reshape(-1) if "vtkValidPointMask" in values else np.array([1])
            inside = len(generic_mask) == 1 and bool(np.isfinite(generic_mask).all()) and bool(generic_mask[0])
        else:
            # Preserve legacy row bytes and saved selection hashes.
            inside = "vtkValidPointMask" not in values or bool(values["vtkValidPointMask"][index])
        for name, native in values.items():
            raw = np.asarray(native[index]).reshape(-1)
            finite = bool(np.isfinite(raw).all())
            is_identity = _identity(name)
            is_mask = name in mask_names or (name in OUTPUT_ARRAYS.values() and native.dtype.kind in "iu")
            if name in declared and not is_identity and not is_mask:
                declaration = declared[name]
                spatial = declaration.get('spatial_mask')
                in_domain = not spatial or bool(declared_flags[spatial][index])
                quality = all(bool(declared_flags[key][index]) for key in declaration.get('validity_masks', []))
                valid = finite and in_domain and quality
                reason = ('valid' if valid else 'outside_domain' if not in_domain else
                          'nonfinite' if not finite else 'source_invalid')
            else:
                valid = finite and (inside or is_identity or is_mask)
                reason = "valid" if valid else ("outside_domain" if not inside and not is_identity and not is_mask else "nonfinite")
            converted = [(value.item() if native.dtype.kind in "iub" else float(value))
                         if valid and np.isfinite(value) else None for value in raw]
            row["values"][name] = converted[0] if len(converted) == 1 else converted
            row["validity"][name] = reason
            if declared:
                retained = [(value.item() if native.dtype.kind in "iub" else float(value))
                            if np.isfinite(value) else None for value in raw]
                row.setdefault('raw_values', {})[name] = retained[0] if len(retained) == 1 else retained
        rows.append(row)
    return {"data_type": data.GetClassName(), "association": association, "count": count,
            "points": data.GetNumberOfPoints(), "cells": data.GetNumberOfCells(), "arrays": arrays,
            "offset": point_index if point_index is not None else offset, "rows": rows,
            "next_offset": None if point_index is not None or offset + limit >= count else offset + limit}
