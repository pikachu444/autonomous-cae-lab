"""Fresh-process original fixture generator, pre-export gate and named STEP catalog.

Native imports occur only after byte-frozen source capture in a new directory.
Geometry observations/face identities are local to the captured native revision.
No fixture mechanics, preload, solver, research or release is introduced here.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
import importlib.metadata
import importlib.util
import itertools
import json
import math
from pathlib import Path
import platform
import sys
import time


def _adapter():
    file = Path(__file__).with_name("fixture_assembly.py")
    for folder in file.resolve().parents:
        if (folder / "PROJECT_SCOPE.md").is_file():
            sys.path.insert(0, str(folder))
            break
    spec = importlib.util.spec_from_file_location("caelab.adapters._fixture_assembly_frozen", file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ad = _adapter()
DECLARATIONS = ad.assembly_declarations()
REQUIRED = DECLARATIONS["component_roles"]
UPSTREAM_GEOMETRY_POLICY = {"collision_volume_mm3": 1e-5, "step_roundtrip_relative_volume": 1e-6,
    "basis": "Exact reused fixturelab.cad.export_and_check; identification tolerance is separately observed native Precision.Confusion"}


def save(folder: Path, name: str, value: dict) -> None:
    ad._save(folder / name, value)


def source_capture(output: Path, expected: dict) -> Path:
    ad.assert_sources(expected)
    snapshot = output / "captured_source"
    snapshot.mkdir()
    for name, source in ad.source_files().items():
        target = snapshot / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as file:
            file.write(source.read_bytes())
        item = expected["files"][name]
        if ad.sha256(target) != item["sha256"] or target.stat().st_size != item["size_bytes"]:
            raise ValueError("Source snapshot changed while captured: " + name)
    save(output, "source_fingerprint_before.json", expected)
    # The upstream tree is new and contains no cached bytecode. Import actual
    # captured bytes, never possibly stale modules/pyc from a prior operation.
    if any(name == "fixturelab" or name.startswith("fixturelab.") or name == "legacy" or name.startswith("legacy.") for name in sys.modules):
        raise ValueError("Fresh assembly worker may not reuse cached fixture imports")
    sys.path.insert(0, str(snapshot / "upstream"))
    return snapshot


def native_modules():
    import cadquery as cq
    from fixturelab import core, cad, functional_checks, handcheck
    return cq, core, cad, functional_checks, handcheck


def bounds(shape) -> dict:
    bb = shape.BoundingBox()
    return {"min_mm": [bb.xmin, bb.ymin, bb.zmin], "max_mm": [bb.xmax, bb.ymax, bb.zmax],
        "size_mm": [bb.xlen, bb.ylen, bb.zlen]}


def signature(shape) -> dict:
    value = {"bounds": bounds(shape), "center_of_mass_mm": list(shape.Center().toTuple()),
        "area_mm2": shape.Area(), "volume_mm3": shape.Volume(), "solid_count": len(shape.Solids()), "valid": shape.isValid()}
    numeric = [*value["center_of_mass_mm"], value["area_mm2"], value["volume_mm3"], *value["bounds"]["min_mm"], *value["bounds"]["max_mm"]]
    if not all(type(x) in (float, int) and math.isfinite(x) for x in numeric):
        raise ValueError("Nonfinite actual native shape signature")
    return value


def pre_export_parts(parts: list, result: dict, functional) -> list[dict]:
    if not isinstance(parts, list) or any(not isinstance(p, dict) for p in parts) or Counter(p.get("name") for p in parts) != Counter(REQUIRED.keys()):
        raise ValueError("Exact15 unique original named components required")
    for part in parts:
        if part.get("kind") != REQUIRED[part["name"]]:
            raise ValueError("Original component role changed")
        s = signature(part["shape"])
        if not s["valid"] or s["solid_count"] != 1 or s["volume_mm3"] <= 0:
            raise ValueError("Each original assembly component must be a valid positive-volume single solid")
    checks = functional.bending_interfaces(parts, result)
    collisions = []
    for p, q in itertools.combinations(parts, 2):
        volume = p["shape"].intersect(q["shape"]).Volume()
        if not math.isfinite(volume):
            raise ValueError("Nonfinite initial interference observation")
        if volume > UPSTREAM_GEOMETRY_POLICY["collision_volume_mm3"]:
            collisions.append({"a": p["name"], "b": q["name"], "overlap_mm3": volume})
    checks.append({"code": "pre_export_initial_position_interference", "status": "FAIL" if collisions else "PASS",
        "detail": {"actual_pair_count": 105, "overlaps": collisions}, "limit": 1e-5})
    if any(c["status"] != "PASS" for c in checks):
        return checks
    return [{"code": "pre_export_actual_named_single_solids", "status": "PASS", "observed": len(parts)}, *checks]


def native_name(label):
    from OCP.TDataStd import TDataStd_Name
    attr = TDataStd_Name()
    return attr.Get().ToExtString() if label.FindAttribute(TDataStd_Name.GetID_s(), attr) else None


def read_named_step(file: Path, cq) -> tuple[Any, dict]:
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPCAFControl import STEPCAFControl_Reader
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDF import TDF_Label, TDF_LabelSequence
    from OCP.TDocStd import TDocStd_Document
    from OCP.XCAFDoc import XCAFDoc_DocumentTool
    doc = TDocStd_Document(TCollection_ExtendedString("fixture-assembly-readback"))
    reader = STEPCAFControl_Reader()
    reader.SetNameMode(True)
    if reader.ReadFile(str(file)) != IFSelect_RetDone or not reader.Transfer(doc):
        raise ValueError("Native STEP transfer failed")
    tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    roots = TDF_LabelSequence()
    tool.GetFreeShapes(roots)
    if roots.Length() != 1 or not tool.IsAssembly_s(roots.Value(1)):
        raise ValueError("STEP must contain one named original assembly root")
    root = cq.Shape.cast(tool.GetShape_s(roots.Value(1)))
    seq = TDF_LabelSequence()
    if not tool.GetComponents_s(roots.Value(1), seq, False):
        raise ValueError("Native STEP contains no named components")
    bodies = {}
    for i in range(1, seq.Length() + 1):
        instance, referred = seq.Value(i), TDF_Label()
        if not tool.IsReference_s(instance) or not tool.GetReferredShape_s(instance, referred):
            raise ValueError("Unexpected unnamed native STEP component")
        name = native_name(referred)
        if name not in REQUIRED or name in bodies:
            raise ValueError("Missing, foreign or duplicate actual XDE product identity")
        shape = cq.Shape.cast(tool.GetShape_s(instance))
        s = signature(shape)
        if not s["valid"] or s["solid_count"] != 1 or s["volume_mm3"] <= 0:
            raise ValueError("Malformed actual native component")
        bodies[name] = {"shape": shape, "xde_product_name": name, "xde_instance_name": native_name(instance)}
    if set(bodies) != set(REQUIRED) or len(root.Solids()) != 15:
        raise ValueError("Incomplete actual named STEP assembly")
    return root, bodies


def geometric_match(source, native) -> dict:
    from OCP.Precision import Precision
    tolerance = Precision.Confusion_s()
    before, after = signature(source), signature(native)
    difference = source.cut(native).Volume() + native.cut(source).Volume()
    bbox_error = max(abs(a-b) for key in ("min_mm", "max_mm") for a,b in zip(before["bounds"][key], after["bounds"][key]))
    relative_difference = difference / before["volume_mm3"]
    if not math.isfinite(difference) or relative_difference >= 1e-6 or bbox_error > tolerance:
        raise ValueError("Actual named STEP body differs from the original built geometry")
    return {"symmetric_difference_mm3": difference, "relative_symmetric_difference": relative_difference,
        "bbox_max_difference_mm": bbox_error, "kernel_linear_identity_tolerance_mm": tolerance,
        "relative_identity_limit": UPSTREAM_GEOMETRY_POLICY["step_roundtrip_relative_volume"],
        "basis": "Actual XDE product name plus geometric Boolean comparison; no solid-array-order association"}


def face_catalog(name: str, shape, output: Path) -> tuple[list, dict]:
    from OCP.Precision import Precision
    records, shapes = [], {}
    folder = output / "native_faces" / name
    folder.mkdir(parents=True)
    for ordinal, face in enumerate(shape.Faces(), 1):
        file = folder / f"face-{ordinal:03d}.brep"
        face.exportBrep(str(file))
        digest = ad.sha256(file)
        identity = f"{name}:face:{ordinal}:{digest}"
        row = {"id": identity, "component_id": name, "local_ordinal": ordinal,
            "identity_scope": "Only exact captured STEP/BREP revision; not a stable cross-revision topology ID",
            "geom_type": face.geomType(), "orientation": str(face.wrapped.Orientation()),
            "area_mm2": face.Area(), "center_of_mass_mm": list(face.Center().toTuple()), "bounds": bounds(face),
            "native_geometry_sha256": digest, "native_brep_path": file.relative_to(output).as_posix(),
            "wire_count": len(face.Wires()), "vertex_coordinates_mm": [list(v.Center().toTuple()) for v in face.Vertices()]}
        adaptor = face._geomAdaptor()
        vector = lambda v: [float(v.X()), float(v.Y()), float(v.Z())]
        if row["geom_type"] == "PLANE":
            plane = adaptor.Pln()
            row["surface"] = {"origin_mm": vector(plane.Location()), "normal": vector(plane.Axis().Direction())}
        elif row["geom_type"] == "CYLINDER":
            cylinder = adaptor.Cylinder()
            row["surface"] = {"radius_mm": cylinder.Radius(), "axis_origin_mm": vector(cylinder.Axis().Location()), "axis_direction": vector(cylinder.Axis().Direction())}
        numbers = [row["area_mm2"], *row["center_of_mass_mm"], *row["bounds"]["min_mm"], *row["bounds"]["max_mm"]]
        if not all(math.isfinite(v) for v in numbers) or row["area_mm2"] <= 0:
            raise ValueError("Invalid actual native face geometry")
        records.append(row)
        shapes[identity] = face
    return records, shapes


def interface_catalog(bodies: dict, cq) -> list:
    from OCP.Precision import Precision
    tol = Precision.Confusion_s()
    def unique(rows, reason):
        if len(rows) != 1:
            raise ValueError("Ambiguous or missing required actual interface face: " + reason)
        return rows[0]
    def plane(name, z, xy=None):
        rows = [f for f in bodies[name]["faces"] if f["geom_type"] == "PLANE" and
            max(abs(f["bounds"][k][2]-z) for k in ("min_mm", "max_mm")) <= tol and
            abs(abs(f["surface"]["normal"][2])-1) <= tol and
            (xy is None or max(abs(f["center_of_mass_mm"][i]-xy[i]) for i in (0,1)) <= tol)]
        return unique(rows, name + " plane")
    def cylinder(name, radius):
        return unique([f for f in bodies[name]["faces"] if f["geom_type"] == "CYLINDER" and
            abs(f["surface"]["radius_mm"]-radius) <= tol and abs(abs(f["surface"]["axis_direction"][1])-1) <= tol], name+" Y cylinder")
    def face(name, row):
        return bodies[name]["face_shapes"][row["id"]]
    def distance(a, b):
        from OCP.BRepExtrema import BRepExtrema_DistShapeShape
        native = BRepExtrema_DistShapeShape(a.wrapped, b.wrapped)
        native.Perform()
        if not native.IsDone() or not math.isfinite(native.Value()):
            raise ValueError("Native geometric distance unavailable")
        return native.Value()
    interfaces = []
    def pair(id, a, fa, b, fb, meaning, extra=None):
        observed = distance(face(a,fa), face(b,fb))
        interfaces.append({"id": id, "a": {"component_id":a,"face_ids":[fa["id"]]},
            "b": {"component_id":b,"face_ids":[fb["id"]]}, "geometry_observation": {"minimum_distance_mm":observed,
                "meaning":meaning, "identity_linear_tolerance_mm":tol, **(extra or {})},
            "contact_law":"UNKNOWN", "contact_force":"UNKNOWN", "loaded_contact_gap":"UNKNOWN", "preload":"UNKNOWN"})
    for declaration in DECLARATIONS["interfaces"]:
        a, b, identity, kind = (declaration[key] for key in ("a", "b", "id", "kind"))
        if kind == "base_support":
            bottom = bodies[b]["bounds"]["min_mm"][2]
            pair(identity,a,plane(a,bottom),b,plane(b,bottom),"Actual base top/support bottom geometry")
        elif kind == "cradle_roller":
            pair(identity,a,cylinder(a,4.15),b,cylinder(b,4),"Actual original gravity-seated cradle/roller geometry")
        elif kind == "roller_specimen":
            bottom = bodies[b]["bounds"]["min_mm"][2]
            pair(identity,a,cylinder(a,4),b,plane(b,bottom),"Actual roller cylindrical face/specimen bottom geometry")
        elif kind == "nose_specimen":
            top = bodies[b]["bounds"]["max_mm"][2]
            pair(identity,a,cylinder(a,4),b,plane(b,top),"Actual loading-nose cylindrical face/specimen top geometry")
        elif kind == "bolt_head_seat":
            candidates = [f for f in bodies[a]["faces"] if f["geom_type"] == "PLANE" and f["wire_count"] == 2]
            head = unique(candidates, a+" actual annular head underside")
            xy = head["center_of_mass_mm"][:2]
            seat = plane(b,head["center_of_mass_mm"][2],xy)
            head_face, seat_face = face(a,head), face(b,seat)
            overlap = head_face.intersect(seat_face).Area()
            head_normal, seat_normal = head_face.normalAt().toTuple(), seat_face.normalAt().toTuple()
            opposed = sum(a*b for a,b in zip(head_normal,seat_normal))
            if seat["wire_count"] != 2 or overlap <= 0 or opposed >= 0 or distance(head_face,seat_face) > tol:
                raise ValueError("Actual bolt head/unique XY support seat association failed")
            pair(identity,a,head,b,seat,"Actual unique bolt XY, annular loop and opposed contact-plane geometry",
                {"actual_bolt_xy_mm":xy,"actual_seat_xy_mm":seat["center_of_mass_mm"][:2],
                 "coplanar_overlap_area_mm2":overlap,"normal_dot":opposed,"head_wire_count":head["wire_count"],"seat_wire_count":seat["wire_count"]})
        else:
            raise ValueError("Unsupported declared Domain interface kind")
    return interfaces


def make_catalog(output: Path, parts: list, result: dict, cq) -> tuple[dict, dict]:
    root, native = read_named_step(output / "assembly.step", cq)
    original = {p["name"]:p["shape"] for p in parts}
    bodies, surface_faces = {}, []
    for name in sorted(native):
        shape = native[name]["shape"]
        identity = geometric_match(original[name],shape)
        global_file = output / "components" / (name+".step")
        global_file.parent.mkdir(exist_ok=True)
        cq.exporters.export(shape,str(global_file))
        readback = cq.importers.importStep(str(global_file)).val()
        separate_identity = geometric_match(shape,readback)
        body_brep = output / "native_bodies" / (name+".brep")
        body_brep.parent.mkdir(exist_ok=True)
        shape.exportBrep(str(body_brep))
        faces, face_shapes = face_catalog(name,shape,output)
        row = {"id":name,"role":REQUIRED[name],"frame":"global_assembly_cartesian_mm",
            "xde_product_name":native[name]["xde_product_name"],"xde_instance_name":native[name]["xde_instance_name"],
            **signature(shape),"native_geometry_sha256":ad.sha256(body_brep),"native_brep_path":body_brep.relative_to(output).as_posix(),
            "global_step_path":global_file.relative_to(output).as_posix(),"native_build_to_step_identity":identity,
            "separate_global_step_identity":separate_identity,"faces":faces,"face_shapes":face_shapes}
        bodies[name] = row
        for face_record in faces:
            vertices, triangles = face_shapes[face_record["id"]].tessellate(.08,.15)
            triangles = [[float(v) for index in tri for v in vertices[index].toTuple()] for tri in triangles]
            if not triangles or any(len(tri)!=9 or not all(math.isfinite(x) for x in tri) for tri in triangles):
                raise ValueError("Invalid actual native display tessellation")
            render_id = len(surface_faces) + 1
            if render_id > 0xffffff:
                raise ValueError("Native display face count exceeds reserved 24-bit viewer identity")
            surface_faces.append({"id":render_id,"type":face_record["geom_type"],"component_id":name,
                "catalog_face_id":face_record["id"],"triangles":triangles})
    interfaces = interface_catalog(bodies,cq)
    native_files = {}
    for file in sorted(output.rglob("*")):
        if file.is_file() and file.suffix.lower() in (".step",".brep",".stl",".3mf"):
            native_files[file.relative_to(output).as_posix()] = {"sha256":ad.sha256(file),"size_bytes":file.stat().st_size}
    for body in bodies.values():
        body.pop("face_shapes")
        if body["role"] == "printed":
            bb = body["bounds"]
            body["manufacturing_export_frame"] = {"meaning":"Original STL/3MF recentered print frame; NOT assembled geometry or analysis input",
                "translation_from_global_mm":[-(bb["min_mm"][i]+bb["max_mm"][i])/2 for i in (0,1)]+[-bb["min_mm"][2]]}
    common = {"schema_version":1,"source_sha256":result["source_sha256"],"input_sha256":result["input_sha256"],
        "assembly_step_sha256":native_files["assembly.step"]["sha256"],"frame":"global_assembly_cartesian_mm"}
    catalog = {**common,"units":{"length":"mm","area":"mm^2","volume":"mm^3"},"native_files":native_files,
        "components":list(bodies.values()),"interfaces":interfaces,"component_count":len(bodies),
        "face_count":len(surface_faces),"bounds":bounds(root),"geometry_policy":UPSTREAM_GEOMETRY_POLICY,
        "geometry_hash_semantics":"Actual serialized BREP bytes in observed runtime; not cross-version canonical geometry",
        "mechanics":"NOT_RUN","production_release":"UNKNOWN","pending_validations":ad.PENDING}
    surface = {**common,"bounds":[bounds(root)["min_mm"],bounds(root)["max_mm"]],"faces":surface_faces,
        "units":"mm","display_only":True,"tessellation":{"linear_tolerance_mm":.08,"angular_tolerance_rad":.15,
            "basis":"Same native CadQuery display tessellation settings as reused fixturelab.cad.mesh_of; NOT a solver mesh"}}
    return catalog,surface


def _build(data, core, cad, functional, handcheck):
    result = core.evaluate(data)
    result["specimen_hand_check"] = handcheck.compare_specimen_scale_check(data,result["metrics"])
    parts=[]
    if result["decision"] != "REJECTED":
        parts=cad.build(result)
        result["cad_checks"]=pre_export_parts(parts,result,functional)
        if any(c["status"]!="PASS" for c in result["cad_checks"]):
            result["decision"]="COMPUTATION_ERROR"
    return result,parts


def effects(request, core, cad, functional, handcheck) -> dict:
    defaults=ad.full_input({})
    if request["action"] == "probe":
        name=request["target"]
        if name not in ad.PARAMETERS:
            raise ValueError("Undiscovered assembly probe path")
        lower,upper=request["bounds"]
        if type(lower) not in (int,float) or type(upper) not in (int,float) or not all(math.isfinite(x) for x in (lower,upper)) or not lower<upper:
            raise ValueError("Invalid probe bounds")
        default=defaults["specimen"][name.split(".")[1]]
        # Probe points are explicit request bounds, never clipped engineering inputs.
        alternatives=[value for value in (lower,upper) if value!=default]
        baseline,baseparts=_build(defaults,core,cad,functional,handcheck)
        checks=[]
        for value in alternatives:
            proposed,parts=_build(ad.full_input({name:value}),core,cad,functional,handcheck)
            if proposed["decision"] in ("REJECTED","COMPUTATION_ERROR"):
                checks.append({"probe_value":value,"status":"REJECTED","checks":[*proposed["checks"],*proposed.get("cad_checks",[])]})
                continue
            difference=assembly_difference(baseparts,parts)
            if difference>0:
                return {"effect":{"status":"PASS","method":"Actual native body Boolean symmetric difference; source unchanged",
                    "native_value":default,"probe_value":value,"symmetric_difference_mm3":difference,"solver_tolerance":None},"checks":checks}
        return {"effect":{"status":"FAIL","reason":"No valid changed assembly at requested bounds","checks":checks},"checks":checks}
    proposed,parts=_build(ad.full_input(request["native_values"]),core,cad,functional,handcheck)
    if proposed["decision"] in ("REJECTED","COMPUTATION_ERROR"):
        return {"checks":[*proposed["checks"],*proposed.get("cad_checks",[])],"decision":proposed["decision"]}
    checks=[]
    for name,value in request["native_values"].items():
        default=defaults["specimen"][name.split(".")[1]]
        if value==default:
            continue
        counter,oldparts=_build(ad.full_input({**request["native_values"],name:default}),core,cad,functional,handcheck)
        if counter["decision"] in ("REJECTED","COMPUTATION_ERROR"):
            checks.append({"code":"geometry_effect_"+name,"status":"UNKNOWN","observed":"Invalid counterfactual; isolated effect UNKNOWN"})
        else:
            difference=assembly_difference(oldparts,parts)
            checks.append({"code":"geometry_effect_"+name,"status":"PASS" if difference>0 else "FAIL","observed":difference,
                "unit":"mm^3","method":"Actual Boolean symmetric difference","limit":0,"interpretation":"Geometry effect only, not mechanics tolerance"})
    return {"checks":checks}


def assembly_difference(first:list,second:list) -> float:
    a,b={p["name"]:p["shape"] for p in first},{p["name"]:p["shape"] for p in second}
    if set(a)!=set(b):
        raise ValueError("Actual assembly parts differ during parameter-effect check")
    values=[a[name].cut(b[name]).Volume()+b[name].cut(a[name]).Volume() for name in sorted(a)]
    if not all(math.isfinite(x) and x>=0 for x in values):
        raise ValueError("Malformed Boolean parameter-effect observation")
    return math.fsum(values)


def run(request_path:Path) -> dict:
    global DECLARATIONS, REQUIRED
    output=request_path.parent
    request=json.loads(request_path.read_text(encoding="utf-8"))
    expected=request["source_fingerprint"]
    started=time.perf_counter()
    result={"source_sha256":expected["source_sha256"],"source_fingerprint_before":expected,"cad_generated":False,
        "native_revision":None,"production_release":"UNKNOWN","mechanical_solver":"NOT_RUN","checks":[],"cad_checks":[],"bom":[]}
    try:
        if request.get("model")!=ad.MODEL or request.get("action") not in ("regenerate","probe","effects"):
            raise ValueError("Unsupported assembly worker action/model")
        keys = {"action", "model", "native_values", "source_fingerprint"}
        if request["action"] == "probe":
            keys |= {"target", "bounds"}
        if set(request) != keys:
            raise ValueError("Unexpected assembly worker control fields")
        snapshot = source_capture(output,expected)
        DECLARATIONS = ad.assembly_declarations(snapshot / "domain/assembly_interfaces.py")
        REQUIRED = DECLARATIONS["component_roles"]
        cq,core,cad,functional,handcheck=native_modules()
        data=ad.full_input(request["native_values"])
        if request["action"] != "regenerate":
            result.update(effects(request,core,cad,functional,handcheck))
        else:
            save(output,"input.json",data)
            result["input_sha256"]=ad.sha256(output/"input.json")
            original,parts=_build(data,core,cad,functional,handcheck)
            result.update(original)
            result.setdefault("cad_checks",[])
            if result["decision"] not in ("REJECTED","COMPUTATION_ERROR"):
                ad.assert_sources(expected) # No export can cross a failed source/preflight gate.
                post,bom=cad.export_and_check(parts,output)
                result["cad_checks"].extend(post)
                result["bom"]=bom
                if any(c["status"]!="PASS" for c in post):
                    result["decision"]="COMPUTATION_ERROR"
                else:
                    catalog,surface=make_catalog(output,parts,result,cq)
                    save(output,"assembly_catalog.json",catalog)
                    save(output,"surface.json",surface)
                    recipe={"schema_version":1,"backend":ad.BACKEND,"model":ad.MODEL,"editable_paths":list(ad.PARAMETERS),
                        "native_values":request["native_values"],"captured_input":data,"input_sha256":result["input_sha256"],
                        "source_sha256":result["source_sha256"],"recorded_upstream_pin":ad.RECORDED_UPSTREAM_PIN,
                        "rebuild_operation":"Existing CADAdapter regenerate with four typed geometry leaves and the captured pinned source",
                        "parametric_definition":"Captured original Python builders + full input JSON; STEP is static native geometry",
                        "portable_rebuild":"NOT_VERIFIED","freecad_parametric_document":"NOT_PROVIDED"}
                    save(output,"rebuild_recipe.json",recipe)
                    result.update(cad_generated=True,catalog_sha256=ad.sha256(output/"assembly_catalog.json"),
                        surface_sha256=ad.sha256(output/"surface.json"),recipe_sha256=ad.sha256(output/"rebuild_recipe.json"),
                        native_files=catalog["native_files"],cad_metrics={"cad_volume":{"value":sum(c["volume_mm3"] for c in catalog["components"]),"unit":"mm^3","valid":True},
                            "cad_bounds":{"value":catalog["bounds"]["size_mm"],"unit":"mm","valid":True},
                            "cad_component_count":{"value":len(catalog["components"]),"unit":"1","valid":True}})
        ad.assert_sources(expected)
        result["source_fingerprint_after"]=expected
        save(output,"source_fingerprint_after.json",expected)
        result["native_revision"]=hashlib.sha256(ad.canonical(ad.revision_material(result))).hexdigest() if result["cad_generated"] else None
    except Exception as error:
        result.update(decision="COMPUTATION_ERROR",cad_generated=False,native_revision=None)
        result["checks"].append({"code":"assembly_generation_integrity","status":"FAIL","observed":f"{type(error).__name__}: {error}"})
        if request.get("action") == "probe":
            result["effect"] = {"status": "FAIL", "reason": "Retained assembly probe computation failure", "checks": result["checks"]}
    versions = {}
    for name in ("cadquery", "cadquery-ocp", "numpy", "trimesh"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "UNKNOWN"
    result["runtime"]={"python":platform.python_version(),"libraries":versions}
    result["elapsed_seconds"]=time.perf_counter()-started
    result["pending_validations"]=ad.PENDING
    save(output,"result.json",result)
    return result


if __name__ == "__main__":
    payload=run(Path(sys.argv[1]))
    print(json.dumps({"decision":payload.get("decision"),"generated":payload["cad_generated"],"native_revision":payload.get("native_revision")}))
