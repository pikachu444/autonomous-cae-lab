"""Observe a native mesh/source association without meshing, recompute or save.

An initial association records what was loaded, not whether that mesh was made
from that shape. Its engineering qualification remains UNKNOWN. A changed shape
cannot reuse the old mesh. Different BRep serialization needs retained original
geometry and unchanged subelement correspondence; it never creates a new stamp.
Only an observed change of native mesh contents can record a new association.
"""
import hashlib
import json
import math
import re


PROPERTY_NAME = "CAELabMeshSourceBinding"
INITIAL = "INITIAL_ASSOCIATION_UNVERIFIED"
REPLACED = "OBSERVED_NATIVE_MESH_REPLACEMENT"

# Pinned FreeCAD 1.1.4 src/App/PropertyContainer.h PropertyType enum:
# https://github.com/FreeCAD/FreeCAD/blob/1.1.4/src/App/PropertyContainer.h
# Output avoids touching the container; NoRecompute alone still marks it Touched
# (src/App/DocumentObject.cpp onChanged). None of these prevent persistence.
PROP_READ_ONLY = 1
PROP_OUTPUT = 8
PROP_NO_RECOMPUTE = 16
PROPERTY_ATTRIBUTES = PROP_READ_ONLY | PROP_OUTPUT | PROP_NO_RECOMPUTE
_PROPERTY_TYPES = {"ReadOnly", "Output", "NoRecompute"}


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def _digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _identifier(value):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("Mesh association requires positive native IDs")
    return value


def global_placement(obj):
    """Gmsh uses getGlobalPlacement, including all ancestor App::Parts."""
    if not hasattr(obj, 'getGlobalPlacement'):
        raise ValueError('Native source global placement is unavailable; its mesh/region cannot be confirmed')
    pose = obj.getGlobalPlacement()
    value = [float(pose.Base.x), float(pose.Base.y), float(pose.Base.z),
             *[float(v) for v in pose.Rotation.Q]]
    if len(value) != 7 or not all(math.isfinite(v) for v in value):
        raise ValueError('Native source global placement is invalid')
    return value


def _current(mesh, *, retain_brep=False):
    source = mesh.Shape
    if source is None or source.Document is not mesh.Document:
        raise ValueError("Mesh association requires a source in the same document")
    brep = source.Shape.exportBrepToString()
    if not isinstance(brep, str) or not brep:
        raise ValueError("Mesh association requires an exact native source BRep")
    native = mesh.FemMesh
    nodes = []
    for identifier, point in sorted(native.Nodes.items()):
        xyz = [float(point.x), float(point.y), float(point.z)]
        if not all(math.isfinite(value) for value in xyz):
            raise ValueError("Mesh association contains nonfinite coordinates")
        nodes.append([_identifier(identifier), xyz])
    if not nodes or not any(getattr(native, family) for family in ("Volumes", "Faces", "Edges")):
        raise ValueError("Mesh association requires a nonempty native mesh")
    known_nodes = {row[0] for row in nodes}
    elements = {}
    # Native IDs are sorted, but each element's native node order is retained.
    # FreeCAD 1.1.4 femmesh/meshtools.py uses these same accessors.
    for family in ("Volumes", "Faces", "Edges"):
        identifiers = list(getattr(native, family))
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("Mesh association contains duplicate element IDs")
        rows = []
        for identifier in sorted(identifiers):
            connectivity = [_identifier(node) for node in native.getElementNodes(identifier)]
            if not connectivity or not set(connectivity) <= known_nodes:
                raise ValueError("Mesh association contains invalid connectivity")
            rows.append([_identifier(identifier), connectivity])
        elements[family] = rows
    current = {
        "source": {"name": source.Name, "type": source.TypeId,
                   "brep_sha256": _digest(brep), "global_placement": global_placement(source)},
        "mesh": {"name": mesh.Name,
                 "ordered_mesh_sha256": _digest(_json({"nodes": nodes, "elements": elements}))},
    }
    if retain_brep:
        current['source']['brep'] = brep
    return current


def _same_source_geometry(reference_brep, current_shape):
    """Prove geometry AND native subelement order from the retained original.

    Never compare volume/bounds alone or apply a found face permutation to the
    old mesh. All operations use copies and the existing kernel tolerances.
    """
    import Part
    from caelab.adapters.freecad_face_catalog_worker import _verify_geometry, _close
    from caelab.adapters.native_face_catalog import GEOMETRY_TOLERANCES
    reference = Part.Shape()
    reference.importBrepFromString(reference_brep)
    current = current_shape.copy()
    limits = GEOMETRY_TOLERANCES.copy()
    if any(shape.isNull() or not shape.isValid() for shape in (reference, current)):
        raise ValueError('Native source geometry is invalid')
    families = ('Solids', 'Shells', 'Faces', 'Wires', 'Edges', 'Vertexes')
    if (reference.ShapeType != current.ShapeType or
            any(len(getattr(reference, family)) != len(getattr(current, family)) for family in families)):
        raise ValueError('Native source topology changed')
    # The face-catalog helper requires one solid. Surface/line meshes have no
    # solids, and a contact source can contain several: compare each SolidN.
    solids = [_verify_geometry(new, old, limits)
              for old, new in zip(reference.Solids, current.Solids)]
    proof = {'status': 'PASS', 'method': 'Indexed native solid, face, edge and vertex geometry',
             'tolerances': limits, 'solid_comparisons': solids}
    for old, new in zip(reference.Faces, current.Faces):
        if str(old.Orientation) != str(new.Orientation):
            raise ValueError('Native source face orientation changed')
        common = old.common(new)
        if (common.isNull() or not common.isValid() or
                not all(math.isfinite(v) and v > 0 for v in (old.Area, new.Area, common.Area)) or
                abs(common.Area / old.Area - 1) > limits['relative'] or
                abs(common.Area / new.Area - 1) > limits['relative']):
            raise ValueError('Native source FaceN correspondence changed')
    if len(reference.Edges) != len(current.Edges) or len(reference.Vertexes) != len(current.Vertexes):
        raise ValueError('Native source edge/vertex topology changed')
    for old, new in zip(reference.Edges, current.Edges):
        if str(old.Orientation) != str(new.Orientation):
            raise ValueError('Native source edge orientation changed')
        common = old.common(new)
        lengths = (old.Length, new.Length, common.Length)
        if (common.isNull() or not common.isValid() or
                not all(math.isfinite(v) and v > 0 for v in lengths) or
                abs(common.Length / old.Length - 1) > limits['relative'] or
                abs(common.Length / new.Length - 1) > limits['relative']):
            raise ValueError('Native source EdgeN correspondence changed')
    for old, new in zip(reference.Vertexes, current.Vertexes):
        if any(not _close(a, b, limits['length_mm'], limits['relative'])
               for a, b in zip(old.Point, new.Point)):
            raise ValueError('Native source VertexN correspondence changed')
    return {**proof, 'subelement_correspondence': 'SAME_FACE_EDGE_VERTEX_ORDER_AND_ORIENTATION',
            'reference': 'ORIGINAL_RETAINED_BREP'}


def _record(mesh):
    if PROPERTY_NAME not in mesh.PropertiesList:
        raise ValueError("Mesh association has not been recorded; track the loaded mesh first")
    if (mesh.getTypeIdOfProperty(PROPERTY_NAME) != "App::PropertyString"
            or set(mesh.getTypeOfProperty(PROPERTY_NAME)) != _PROPERTY_TYPES):
        raise ValueError("Mesh association property has invalid native type or persistence attributes")
    try:
        def require(condition):
            if not condition:
                raise ValueError("Invalid mesh association field")
        def unique_pairs(pairs):
            value = {}
            for key, item in pairs:
                if key in value:
                    raise ValueError("Duplicate mesh association field")
                value[key] = item
            return value
        value = json.loads(getattr(mesh, PROPERTY_NAME), object_pairs_hook=unique_pairs)
        require(set(value) == {"schema_version", "status", "qualification", "source", "mesh"})
        require(value["schema_version"] in (1, 2, 3) and type(value["schema_version"]) is int)
        require(value["status"] in (INITIAL, REPLACED))
        require(value["qualification"] == "UNKNOWN")
        fields = {"name", "type", "brep_sha256"} | ({"global_placement"} if value['schema_version'] >= 2 else set())
        if value['schema_version'] == 3:
            fields.add('brep')
        require(set(value["source"]) == fields)
        if value['schema_version'] >= 2:
            pose = value['source']['global_placement']
            require(isinstance(pose, list) and len(pose) == 7
                    and all(type(v) in (int, float) and math.isfinite(v) for v in pose))
        require(set(value["mesh"]) == {"name", "ordered_mesh_sha256"})
        require(value["mesh"]["name"] == mesh.Name)
        for name in ("name", "type"):
            require(isinstance(value["source"][name], str) and bool(value["source"][name]))
        for digest in (value["source"]["brep_sha256"], value["mesh"]["ordered_mesh_sha256"]):
            require(isinstance(digest, str) and re.fullmatch("[0-9a-f]{64}", digest))
        if value['schema_version'] == 3:
            brep = value['source']['brep']
            require(isinstance(brep, str) and bool(brep) and _digest(brep) == value['source']['brep_sha256'])
    except (TypeError, KeyError, ValueError) as exc:
        raise ValueError("Malformed recorded mesh association; it cannot be reset automatically") from exc
    return value


class MeshBindingObserver:
    """Keep alive while registered with FreeCAD.addDocumentObserver.

    Call track(mesh) after load/bind and validate(mesh) immediately before export.
    Remove this observer when the owner closes. Metadata is stored only in the
    native draft; an explicit native save persists it. No source file is saved.
    """

    def __init__(self, document=None):
        self.document = document
        self.last_error = None

    def _check_document(self, mesh):
        if self.document is not None and mesh.Document is not self.document:
            raise ValueError("Mesh association observer belongs to another document")
        # The pinned DocumentPy Restoring/Importing API guards native file restore
        # and import; loading serialized mesh data is not a mesh regeneration.
        if mesh.Document.Restoring or mesh.Document.Importing:
            raise ValueError("Mesh association cannot change during document restore/import")

    def track(self, mesh):
        self._check_document(mesh)
        if PROPERTY_NAME in mesh.PropertiesList:
            return self.validate(mesh)
        current = _current(mesh, retain_brep=True)
        mesh.addProperty("App::PropertyString", PROPERTY_NAME, "CAELab",
                         "Recorded mesh/source association; initial provenance remains unknown",
                         attr=PROPERTY_ATTRIBUTES, locked=True)
        value = dict(current, schema_version=3, status=INITIAL, qualification="UNKNOWN")
        setattr(mesh, PROPERTY_NAME, _json(value))
        return self.validate(mesh)

    def validate(self, mesh):
        self._check_document(mesh)
        value = _record(mesh)
        current = _current(mesh)
        if value['schema_version'] == 1:
            raise ValueError('Source placement was not recorded in this older mesh binding; regenerate the native mesh before export')
        recorded = {k: v for k, v in value['source'].items() if k != 'brep'}
        identity = ('name', 'type', 'global_placement')
        if any(recorded.get(k) != current['source'].get(k) for k in identity):
            raise ValueError("Source geometry changed after the recorded mesh association; regenerate the native mesh before export")
        proof = {}
        if recorded['brep_sha256'] != current['source']['brep_sha256']:
            if value['schema_version'] != 3:
                raise ValueError('Source geometry changed or was serialized differently; this older mesh binding has no original BRep to prove equivalence. Regenerate the native mesh before export')
            try:
                proof['source_equivalence'] = _same_source_geometry(value['source']['brep'], mesh.Shape.Shape)
            except Exception as error:
                raise ValueError('Source geometry changed or its exact subelement correspondence cannot be proved; regenerate the native mesh before export') from error
        if value["mesh"] != current["mesh"]:
            raise ValueError("Native mesh changed without an observed replacement; its source association is unknown")
        return dict(value, binding_validation="CURRENT_SOURCE_AND_MESH_MATCH", **proof)

    def slotChangedObject(self, obj, prop):
        if prop != "FemMesh" or (self.document is not None and obj.Document is not self.document):
            return
        # Native callbacks must not throw through FreeCAD. A failed observation
        # leaves the prior stamp intact; validate remains the fail-closed gate.
        if obj.Document.Restoring or obj.Document.Importing:
            return
        try:
            self._check_document(obj)
            current = _current(obj, retain_brep=True)
            if PROPERTY_NAME not in obj.PropertiesList:
                self.track(obj)  # First observation has no historical baseline.
            else:
                value = _record(obj)  # Malformed metadata is never overwritten.
                if value["mesh"] != current["mesh"]:
                    setattr(obj, PROPERTY_NAME,
                            _json(dict(current, schema_version=3, status=REPLACED,
                                       qualification="UNKNOWN")))
                # Touching/reassigning identical mesh content cannot rebind it
                # to changed CAD. Such an association still fails validation.
            self.last_error = None
        except Exception as exc:
            self.last_error = str(exc)
