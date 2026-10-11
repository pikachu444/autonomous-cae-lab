"""Observe a native mesh/source association without meshing, recompute or save.

An initial association records what was loaded, not whether that mesh was made
from that shape. Its engineering qualification remains UNKNOWN. Once recorded,
a changed shape cannot reuse the old mesh, even after save/reopen or recompute.
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


def _current(mesh):
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
    if not nodes or not native.Volumes:
        raise ValueError("Mesh association requires a nonempty native solid mesh")
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
    return {
        "source": {"name": source.Name, "type": source.TypeId,
                   "brep_sha256": _digest(brep)},
        "mesh": {"name": mesh.Name,
                 "ordered_mesh_sha256": _digest(_json({"nodes": nodes, "elements": elements}))},
    }


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
        require(value["schema_version"] == 1 and type(value["schema_version"]) is int)
        require(value["status"] in (INITIAL, REPLACED))
        require(value["qualification"] == "UNKNOWN")
        require(set(value["source"]) == {"name", "type", "brep_sha256"})
        require(set(value["mesh"]) == {"name", "ordered_mesh_sha256"})
        require(value["mesh"]["name"] == mesh.Name)
        for name in ("name", "type"):
            require(isinstance(value["source"][name], str) and bool(value["source"][name]))
        for digest in (value["source"]["brep_sha256"], value["mesh"]["ordered_mesh_sha256"]):
            require(isinstance(digest, str) and re.fullmatch("[0-9a-f]{64}", digest))
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
        current = _current(mesh)
        mesh.addProperty("App::PropertyString", PROPERTY_NAME, "CAELab",
                         "Recorded mesh/source association; initial provenance remains unknown",
                         attr=PROPERTY_ATTRIBUTES, locked=True)
        value = dict(current, schema_version=1, status=INITIAL, qualification="UNKNOWN")
        setattr(mesh, PROPERTY_NAME, _json(value))
        return self.validate(mesh)

    def validate(self, mesh):
        self._check_document(mesh)
        value = _record(mesh)
        current = _current(mesh)
        if value["source"] != current["source"]:
            raise ValueError("Source geometry changed after the recorded mesh association; regenerate the native mesh before export")
        if value["mesh"] != current["mesh"]:
            raise ValueError("Native mesh changed without an observed replacement; its source association is unknown")
        return dict(value, binding_validation="CURRENT_SOURCE_AND_MESH_MATCH")

    def slotChangedObject(self, obj, prop):
        if prop != "FemMesh" or (self.document is not None and obj.Document is not self.document):
            return
        # Native callbacks must not throw through FreeCAD. A failed observation
        # leaves the prior stamp intact; validate remains the fail-closed gate.
        if obj.Document.Restoring or obj.Document.Importing:
            return
        try:
            self._check_document(obj)
            current = _current(obj)
            if PROPERTY_NAME not in obj.PropertiesList:
                self.track(obj)  # First observation has no historical baseline.
            else:
                value = _record(obj)  # Malformed metadata is never overwritten.
                if value["mesh"] != current["mesh"]:
                    setattr(obj, PROPERTY_NAME,
                            _json(dict(current, schema_version=1, status=REPLACED,
                                       qualification="UNKNOWN")))
                # Touching/reassigning identical mesh content cannot rebind it
                # to changed CAD. Such an association still fails validation.
            self.last_error = None
        except Exception as exc:
            self.last_error = str(exc)
