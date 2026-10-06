"""New controlled source/capture tests; no CAD, SDK, mesh or solver operation.

The captured helper/Domain and Main CAD verifier below are explicitly synthetic
boundary observations. They do not fake a qualified finite-element data set.
Numerical qualification remains the original verifier's separate tested scope.
"""
from copy import deepcopy
import hashlib
import importlib.util
import json
import marshal
import os
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace

import pytest


BASE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("caelab.adapters._mesh_reuse_candidate",
    BASE / "caelab/adapters/fixture_assembly_mesh_reuse.py")
r = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = r
spec.loader.exec_module(r)


HELPER = b'''"""SYNTHETIC captured verification boundary, never native qualification."""
from pathlib import Path
import hashlib
import json
calls = []

def validate_parent(actual, root):
    recorded = json.loads((root / "result.json").read_text())
    if actual != recorded:
        raise ValueError("Synthetic live result differs")
    cad = _cad_adapter()
    expected = actual["native_source_fingerprint"]
    # Real production CAD source assert, not a MainBoundary-only observation.
    cad.verify_result(root / "cad", {"cad_generated":False, "native_revision":None,
        "source_sha256":expected["source_sha256"], "source_fingerprint_before":expected}, expected)
    cad.assembly_declarations()
    cad.full_input({})
    files = {p.relative_to(root).as_posix(): {"sha256":hashlib.sha256(p.read_bytes()).hexdigest(),
             "size_bytes":p.stat().st_size} for p in root.rglob("*") if p.is_file()}
    return {"identity":recorded["identity"], "files":files}
def verify_output(root, result, request):
    calls.append(str(root))
    if str(root) != request["synthetic_original_root"]:
        raise ValueError("Synthetic verifier must use original root")
    if result["status"] != "VALID_PREPROCESSING" or result["decision"] != "NOT_RELEASED":
        raise ValueError("Synthetic invalid result")
    if result["mesh_revision"] != request["synthetic_revision"]:
        raise ValueError("Synthetic revision differs")
    d = standalone(root / "capsule/assembly_mesh.py", "_captured_mesh_domain")
    d.check_profile(request["profile"])
    return result
'''
DOMAIN = b'''"""SYNTHETIC frozen Domain-only source; no native calls."""
def check_profile(value):
    if value != {"name":"coarse3", "mesh_size_mm":3.0, "limits":{"body_mesh_volume_relative":0.01}}:
        raise ValueError("Synthetic profile changed")
'''


def entry(path):
    data = path.read_bytes()
    return {"sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}


def write(root, name, data):
    file = root / name
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_bytes(data)
    return entry(file)


def save(root, name, value):
    return write(root, name, r._canonical(value) + b"\n")


@pytest.fixture
def context(tmp_path, monkeypatch):
    bundle, parent = tmp_path / "original_bundle", tmp_path / "live_cad_parent"
    bundle.mkdir(); parent.mkdir()
    identity = {"experiment_id":"SYNTHETIC-CAD", "cad_revision":"c"*64, "native_revision":"d"*64,
                "cad_prefix":"cad", "cad_provenance":{"source_commit":"SYNTHETIC-NOT-A-COMMIT"}}
    parent_result = {"identity":identity, "status":"COMPLETED_REVIEW_REQUIRED", "decision":"NOT_RELEASED",
                     "solver_status":"NOT_RUN", "converged":None, "fixture":"SYNTHETIC; not CAD geometry"}
    parent_files = {"result.json":save(parent,"result.json",parent_result),
                    "proposal.json":save(parent,"proposal.json",{"synthetic":True,"width_mm":10.}),
                    "cad/assembly_catalog.json":save(parent,"cad/assembly_catalog.json",{"synthetic":True}),
                    "cad/component.bin":write(parent,"cad/component.bin",bytes(range(256))*9)}
    for name in parent_files:
        write(bundle, "parent/" + name, (parent / name).read_bytes())
    sources = {"fixture_assembly_mesh.py":HELPER, "assembly_mesh.py":DOMAIN,
               "fixture_assembly_mesh_worker.py":b"# SYNTHETIC worker; never executed\n",
               "gmsh.py":b"# SYNTHETIC SDK source; never imported\n",
               "parent_verifier/pin.json":b'{"synthetic":true}\n',
               "parent_verifier/platform/contracts.py":b"# SYNTHETIC original contracts\n",
               "parent_verifier/platform/execution_control.py":b"# SYNTHETIC original ownership\n"}
    for name,path in {
        "adapter/fixture_assembly.py":"caelab/adapters/fixture_assembly.py",
        "adapter/fixture_assembly_worker.py":"caelab/adapters/fixture_assembly_worker.py",
        "domain/assembly_interfaces.py":"plugins/fixture_design/assembly_interfaces.py",
        "upstream/examples/bend_4mm.json":"plugins/fixture_design/upstream/examples/bend_4mm.json"}.items():
        sources["parent_verifier/"+name]=(BASE/path).read_bytes()
    source_files = {name:write(bundle,"capsule/"+name, data) for name,data in sources.items()}
    cad_files={name.removeprefix("parent_verifier/"):pin for name,pin in source_files.items()
               if name.startswith("parent_verifier/")}
    definition={"backend":"fixture.assembly","model":"bending_assembly","version":"1",
        "paths":{"specimen.length":["Specimen length","mm"],"specimen.width":["Specimen width","mm"],
                 "specimen.thickness":["Specimen thickness","mm"],"specimen.span_ratio":["Support span / specimen thickness","1"]},
        "intrinsic_bounds":"No independent usable bounds claimed; original positive/resource/coupled relation checks remain authoritative",
        "files":cad_files}
    parent_result["native_source_fingerprint"]={"commit":"UNKNOWN","git_dirty":None,
        "recorded_upstream_pin":"3e48bf6138f495299f45b1af254bfb4aaff307b8",
        "git_observation":"NOT_QUERIED; actual source bytes are frozen independently","files":cad_files,
        "files_sha256":hashlib.sha256(r._canonical(cad_files)).hexdigest(),
        "source_sha256":hashlib.sha256(r._canonical(definition)).hexdigest()}
    parent_files["result.json"]=save(parent,"result.json",parent_result)
    write(bundle,"parent/result.json",(parent/"result.json").read_bytes())
    profile = {"name":"coarse3", "mesh_size_mm":3.0,"limits":{"body_mesh_volume_relative":.01}}
    revision = hashlib.sha256(b"SYNTHETIC ORIGINAL MESH REVISION; no FE qualification").hexdigest()
    request = {"schema_version":1, "source_files":deepcopy(source_files), "parent":deepcopy(identity),
        "parent_files":parent_files,"profile":deepcopy(profile), "synthetic_original_root":str(bundle),
        "synthetic_revision":revision}
    request_entry = save(bundle,"request.json",request)
    outputs = {name:write(bundle,name,("SYNTHETIC RAW BYTES; NOT NATIVE: " + name).encode()) for name in sorted(r._OUTPUTS)}
    runtime = {"sdk_path":str(bundle/"capsule/gmsh.py"),"library_path":"/synthetic/original/libgmsh.so",
               "observation":"SYNTHETIC ORIGINAL EXECUTION; not an actual runtime"}
    result = {"schema_version":1,"mesh_revision":revision,"profile":deepcopy(profile),
        "parent":deepcopy(identity),"source_files":deepcopy(source_files),"output_files":outputs,
        "runtime_before":deepcopy(runtime),"runtime_after":deepcopy(runtime),
        "status":"VALID_PREPROCESSING","decision":"NOT_RELEASED"}
    result_entry = save(bundle,"result.json",result)
    events, loaded = [], []
    # Explicitly injected Main boundary; production provides no switch or bypass.
    frozen_main_sources = deepcopy(source_files)
    class MainBoundary:
        def source_files(self):
            files={name:bundle/"capsule"/name for name in source_files}
            files["parent_verifier/adapter/fixture_assembly.py"]=BASE/"caelab/adapters/fixture_assembly.py"
            return files
        def source_fingerprint(self):
            events.append("main-source-read")
            return deepcopy(frozen_main_sources)
        def validate_parent(self, actual, root):
            events.append("main-live-parent-read")
            recorded = json.loads((root/"result.json").read_text())
            if actual != recorded:
                raise ValueError("Synthetic live result differs")
            for name,pin in parent_files.items():
                if entry(root/name) != pin:
                    raise ValueError("Synthetic live parent byte drift")
            return {"identity":deepcopy(recorded["identity"]), "files":deepcopy(parent_files)}
    current = MainBoundary()
    monkeypatch.setattr(r,"_main_helper",lambda: current)
    original = r.QualifiedAssemblyMeshBundle._original_helper
    def load(self):
        module = original(self); loaded.append(module)
        return module
    monkeypatch.setattr(r.QualifiedAssemblyMeshBundle,"_original_helper",load)
    def constructor(**changes):
        args = {"request_entry":deepcopy(request_entry), "result_entry":deepcopy(result_entry),
                "mesh_revision":revision,"source_files":deepcopy(source_files)}
        args.update(changes)
        return r.QualifiedAssemblyMeshBundle(bundle,**args)
    return SimpleNamespace(bundle=bundle,parent=parent,parent_result=parent_result,parent_files=parent_files,
        request=request,result=result,request_entry=request_entry,result_entry=result_entry,revision=revision,
        source_files=source_files,current=current,main_sources=frozen_main_sources,events=events,loaded=loaded,
        constructor=constructor,output=tmp_path/"new_capture",monkeypatch=monkeypatch)


def capture(ctx, obj=None):
    obj = obj or ctx.constructor()
    descriptor = obj.capture(ctx.parent_result,ctx.parent,ctx.output)
    return obj,descriptor


def test_frozen_original_reuse_independent_copies_and_unmodified_runtime(context):
    c=context
    before={p.relative_to(c.bundle).as_posix():entry(p) for p in c.bundle.rglob('*') if p.is_file()}
    obj,descriptor=capture(c)
    assert len(c.loaded)==1 and c.loaded[0].calls==[str(c.bundle)]
    receipt=json.loads((c.output/r._RECEIPT).read_text())
    for name,pin in receipt["captured_files"].items():
        assert entry(c.output/name)==pin==entry(c.bundle/name)
        assert not os.path.samefile(c.output/name,c.bundle/name)
        assert (c.output/name).stat().st_nlink==1
        assert ((c.output/name).stat().st_dev,(c.output/name).stat().st_ino) != ((c.bundle/name).stat().st_dev,(c.bundle/name).stat().st_ino)
    assert receipt["original_runtime_before"]==c.result["runtime_before"]
    assert receipt["original_runtime_after"]==c.result["runtime_after"]
    assert str(c.output) not in json.dumps(receipt["original_runtime_after"])
    assert receipt["parent"]==c.request["parent"] and receipt["profile"]==c.request["profile"]
    assert set(receipt["output_files"])==r._OUTPUTS
    assert descriptor["capture_only"] is True and descriptor["solver_status"]=="NOT_RUN"
    assert descriptor["decision"]=="NOT_RELEASED"
    assert [receipt[k] for k in ("native_calls","solver_calls","provider_calls")]==[0,0,0]
    assert before=={p.relative_to(c.bundle).as_posix():entry(p) for p in c.bundle.rglob('*') if p.is_file()}
    assert not list(c.bundle.rglob('__pycache__'))


def test_later_recheck_uses_pins_not_numerical_verifier_and_returns_defensive_descriptor(context):
    c=context
    obj,descriptor=capture(c)
    original=deepcopy(descriptor)
    descriptor["profile"]["limits"]["body_mesh_volume_relative"]=.5
    descriptor["receipt"]["sha256"]="f"*64
    # Future solver ownership may retain its own unrelated output alongside capture.
    (c.output/"future-owner.log").write_text("SYNTHETIC; no execution")
    assert obj.recheck(c.output)==original
    assert c.loaded[0].calls==[str(c.bundle)] and len(c.loaded)==1


def test_constructor_freezes_nested_operator_pins(context):
    c=context
    pins=deepcopy(c.source_files); request=deepcopy(c.request_entry); result=deepcopy(c.result_entry)
    obj=c.constructor(source_files=pins,request_entry=request,result_entry=result)
    pins["fixture_assembly_mesh.py"]["sha256"]="f"*64
    pins["foreign.py"]={"sha256":"f"*64,"size_bytes":0}
    request["size_bytes"]=0; result.clear()
    assert capture(c,obj)[1]["mesh_revision"]==c.revision


def explicit_current(c, changes=None):
    """Operator pins for SYNTHETIC current source observations, not settings."""
    pins=deepcopy(c.source_files)
    changed=changes or r._CURRENT_PARENT_CHANGES
    for name in changed:
        data=("SYNTHETIC current parent verifier: "+name).encode()
        pins[name]={"sha256":hashlib.sha256(data).hexdigest(),"size_bytes":len(data)}
    c.main_sources.clear(); c.main_sources.update(deepcopy(pins))
    return pins


def alter_isolated_parent(c, transform):
    original=r.QualifiedAssemblyMeshBundle._mesh_helper
    def controlled(self, module_name):
        helper=original(self,module_name)
        if module_name=="_qualified_historical_parent_helper":
            validate=helper.validate_parent
            def altered(*args):
                actual=validate(*args)
                return transform(actual)
            helper.validate_parent=altered
        return helper
    c.monkeypatch.setattr(r.QualifiedAssemblyMeshBundle,"_mesh_helper",controlled)


def test_default_remains_original_exact_and_refuses_known_current_evolution(context):
    c=context; explicit_current(c)
    with pytest.raises(ValueError,match="source differs"):
        capture(c)
    assert not c.loaded and not c.output.exists()


@pytest.mark.parametrize("changed",[
    ["parent_verifier/platform/contracts.py"],
    ["parent_verifier/platform/execution_control.py"],
    sorted(r._CURRENT_PARENT_CHANGES)])
def test_explicit_current_preserves_original_maps_qualification_and_provenance(context,changed):
    c=context; current=explicit_current(c,changed)
    original=deepcopy(c.source_files)
    before={p.relative_to(c.bundle).as_posix():entry(p) for p in c.bundle.rglob('*') if p.is_file()}
    obj,descriptor=capture(c,c.constructor(current_source_files=current))
    receipt=json.loads((c.output/r._RECEIPT).read_text())
    assert receipt["source_files"]==receipt["original_source_files"]==original
    assert receipt["current_parent_verifier_source_files"]==current!=original
    assert descriptor["original_source_files"]==original
    assert descriptor["current_parent_verifier_source_files"]==current
    assert descriptor["source_admission"]==receipt["source_admission"]=={
        "mode":"EXPLICIT_CURRENT_PARENT_VERIFIER", "changed_paths":sorted(changed),
        "allowed_changed_paths":sorted(r._CURRENT_PARENT_CHANGES),
        "scope":"Original captured preprocessing qualification; current verifier of the same CAD bytes; no new meshing or mechanics qualification"}
    assert receipt["original_runtime_before"]==c.result["runtime_before"]
    assert receipt["original_runtime_after"]==c.result["runtime_after"]
    assert receipt["parent"]==c.request["parent"]==c.parent_result["identity"]
    assert receipt["parent_files"]==c.parent_files
    assert receipt["profile"]==c.result["profile"]
    assert descriptor["mesh_revision"]==c.revision and descriptor["solver_status"]=="NOT_RUN"
    assert [receipt[k] for k in ("native_calls","solver_calls","provider_calls")]==[0,0,0]
    for name in original:
        assert entry(c.output/"capsule"/name)==entry(c.bundle/"capsule"/name)==original[name]
    assert before=={p.relative_to(c.bundle).as_posix():entry(p) for p in c.bundle.rglob('*') if p.is_file()}
    assert len(c.loaded)==1 and c.loaded[0].calls==[str(c.bundle)]
    assert obj.recheck(c.output)==descriptor
    assert len(c.loaded)==1


def test_default_records_original_exact_without_version_inference(context):
    _,descriptor=capture(context)
    assert descriptor["source_admission"]["mode"]=="ORIGINAL_EXACT"
    assert descriptor["source_admission"]["changed_paths"]==[]
    assert descriptor["original_source_files"]==descriptor["current_parent_verifier_source_files"]==context.source_files


def test_explicit_current_nested_config_and_returned_context_are_defensive(context):
    c=context; pins=explicit_current(c); frozen=deepcopy(pins)
    obj=c.constructor(current_source_files=pins)
    pins["parent_verifier/platform/contracts.py"]["sha256"]="f"*64
    pins.clear()
    _,descriptor=capture(c,obj)
    before=deepcopy(descriptor)
    descriptor["current_parent_verifier_source_files"]["gmsh.py"]["size_bytes"]=0
    descriptor["original_source_files"].clear()
    descriptor["source_admission"]["changed_paths"].append("gmsh.py")
    actual=obj.recheck(c.output)
    assert actual==before and actual["current_parent_verifier_source_files"]==frozen


@pytest.mark.parametrize("kind",["missing","extra","alias","duplicate","bool_size","wrong_hash","wrong_type"])
def test_explicit_current_requires_complete_exact_typed_operator_map(context,kind):
    c=context; current=explicit_current(c)
    if kind=="missing": current.pop("gmsh.py")
    elif kind=="extra": current["foreign.py"]={"sha256":"f"*64,"size_bytes":1}
    elif kind=="alias": current["GMSH.PY"]=current["gmsh.py"]
    elif kind=="duplicate":
        class Duplicate(dict):
            def items(self): return list(super().items())+[next(iter(super().items()))]
        current=Duplicate(current)
    elif kind=="bool_size": current["parent_verifier/platform/contracts.py"]["size_bytes"]=True
    elif kind=="wrong_hash": current["parent_verifier/platform/contracts.py"]["sha256"]="invalid"
    else: current="same version, assume compatible"
    with pytest.raises(ValueError): c.constructor(current_source_files=current)
    assert not c.loaded and not c.output.exists()


@pytest.mark.parametrize("name",["fixture_assembly_mesh.py","fixture_assembly_mesh_worker.py","assembly_mesh.py",
    "gmsh.py","parent_verifier/pin.json"])
def test_explicit_current_cannot_allow_mesh_cad_domain_sdk_or_other_verifier_changes(context,name):
    c=context; current=explicit_current(c)
    current[name]={"sha256":"f"*64,"size_bytes":12}
    c.main_sources[name]=deepcopy(current[name])
    with pytest.raises(ValueError,match="only for the two named"):
        c.constructor(current_source_files=current)
    assert not c.loaded and not c.output.exists()


def test_explicit_current_never_replaces_original_capsule_operator_map(context):
    c=context; current=explicit_current(c)
    with pytest.raises(ValueError,match="independently trusted source map"):
        capture(c,c.constructor(source_files=current,current_source_files=current))
    assert not c.loaded and not c.output.exists()


def test_explicit_current_requires_actual_fingerprint_not_only_allowlisted_change(context):
    c=context; current=explicit_current(c)
    current["parent_verifier/platform/contracts.py"]["sha256"]="f"*64
    with pytest.raises(ValueError,match="source differs"):
        capture(c,c.constructor(current_source_files=current))
    assert not c.output.exists() and not c.loaded


@pytest.mark.parametrize("moment",["before_capture","live_validation","numerical_verification","after_copy","recheck"])
def test_explicit_current_drift_at_each_boundary_refuses_success(context,moment):
    c=context; current=explicit_current(c)
    obj=c.constructor(current_source_files=current)
    def drift(): c.main_sources["parent_verifier/platform/contracts.py"]["sha256"]="f"*64
    if moment=="before_capture": drift()
    elif moment=="live_validation":
        def altered(value): drift(); return value
        alter_isolated_parent(c,altered)
    elif moment=="numerical_verification":
        original=r.QualifiedAssemblyMeshBundle._original_helper
        def altered(self):
            helper=original(self); verification=helper.verify_output
            def verify(*args):
                value=verification(*args); drift(); return value
            helper.verify_output=verify
            return helper
        c.monkeypatch.setattr(r.QualifiedAssemblyMeshBundle,"_original_helper",altered)
    elif moment=="after_copy":
        original=r._read
        def altered(root,name,pin,**kwargs):
            value=original(root,name,pin,**kwargs)
            if root==c.output and name=="mesh.msh": drift()
            return value
        c.monkeypatch.setattr(r,"_read",altered)
    else:
        capture(c,obj); drift()
        with pytest.raises(ValueError,match="source differs"): obj.recheck(c.output)
        return
    with pytest.raises(ValueError,match="source differs"): capture(c,obj)
    if moment in ("before_capture","live_validation","numerical_verification"):
        assert not c.output.exists()
    else:
        assert c.output.exists() and not (c.output/r._RECEIPT).exists()


@pytest.mark.parametrize("part",["identity","bytes"])
def test_explicit_current_still_binds_same_original_live_cad(context,part):
    c=context; current=explicit_current(c)
    obj=c.constructor(current_source_files=current)
    if part=="identity":
        def altered(actual): actual["identity"]["native_revision"]="f"*64; return actual
        alter_isolated_parent(c,altered)
    else: (c.parent/"cad/component.bin").write_bytes(b"FOREIGN CURRENT CAD")
    with pytest.raises(ValueError): capture(c,obj)
    assert not c.output.exists() and not c.loaded


def test_explicit_current_checks_parent_bytes_after_live_validation_and_on_recheck(context):
    c=context; current=explicit_current(c)
    obj,_=capture(c,c.constructor(current_source_files=current))
    def altered(actual):
        (c.parent/"cad/component.bin").write_bytes(b"DRIFT AFTER VALIDATION")
        return actual
    alter_isolated_parent(c,altered)
    with pytest.raises(ValueError,match="pin drift|identity drift"): obj.recheck(c.output)


@pytest.mark.parametrize("part",["nonempty","overlap","hardlink"])
def test_explicit_current_keeps_append_only_and_alias_guards(context,tmp_path,part):
    c=context; obj=c.constructor(current_source_files=explicit_current(c))
    if part=="nonempty":
        c.output.mkdir(); (c.output/"keep.txt").write_bytes(b"KEEP")
        with pytest.raises(ValueError,match="Fresh empty"): capture(c,obj)
        assert (c.output/"keep.txt").read_bytes()==b"KEEP"
    elif part=="overlap":
        with pytest.raises(ValueError,match="overlap"):
            obj.capture(c.parent_result,c.parent,c.bundle/"nested-capture")
    else:
        os.link(c.bundle/"mesh.msh",tmp_path/"foreign-alias")
        with pytest.raises(ValueError,match="Regular unshared"): capture(c,obj)
    assert not c.loaded


@pytest.mark.parametrize("name",["capsule/fixture_assembly_mesh.py","mesh.msh","quality.json","result.json"])
def test_explicit_current_does_not_authorize_original_qualification_tamper(context,name):
    c=context; current=explicit_current(c)
    obj=c.constructor(current_source_files=current)
    (c.bundle/name).write_bytes((c.bundle/name).read_bytes()+b"TAMPER")
    with pytest.raises(ValueError,match="pin drift"): capture(c,obj)
    assert not c.output.exists()


def test_explicit_current_receipt_change_cannot_rebind_parent_or_original_sources(context):
    c=context; obj,_=capture(c,c.constructor(current_source_files=explicit_current(c)))
    receipt=json.loads((c.output/r._RECEIPT).read_text())
    receipt["source_files"]=deepcopy(receipt["current_parent_verifier_source_files"])
    save(c.output,r._RECEIPT,receipt)
    with pytest.raises(ValueError,match="pin drift"): obj.recheck(c.output)


def test_real_cad_source_assert_is_preserved_in_private_capsule_configuration(context,monkeypatch):
    c=context; obj=c.constructor(current_source_files=explicit_current(c))
    spec=importlib.util.spec_from_file_location("caelab.adapters._host_cad_assert_control",
                                              BASE/"caelab/adapters/fixture_assembly.py")
    host=importlib.util.module_from_spec(spec); spec.loader.exec_module(host)
    expected=c.parent_result["native_source_fingerprint"]
    raw={"cad_generated":False,"native_revision":None,"source_sha256":expected["source_sha256"],
         "source_fingerprint_before":expected}
    with pytest.raises(ValueError,match="Assembly source changed"):
        host.verify_result(c.parent/"cad",raw,expected)
    before={p.relative_to(c.bundle).as_posix():entry(p) for p in c.bundle.rglob('*') if p.is_file()}
    cad=obj._original_cad(c.current)
    for name in ("fingerprint","assert_sources","full_input","verify_result","validate_catalog","assembly_declarations"):
        assert getattr(cad,name).__code__.co_code==getattr(host,name).__code__.co_code
        assert getattr(cad,name).__code__.co_filename==str(c.bundle/"capsule/parent_verifier/adapter/fixture_assembly.py")
    assert cad.fingerprint()==expected
    cad.verify_result(c.parent/"cad",raw,expected)
    assert len(cad.assembly_declarations()["component_roles"])==15
    assert cad.full_input({})["specimen"]["length"]==80
    assert cad.assembly_declarations.__defaults__==(cad.DOMAIN,)
    assert all(path.is_relative_to(c.bundle/"capsule/parent_verifier") for path in cad.source_files().values())
    with pytest.raises(ValueError,match="exact pinned CAD Domain"):
        cad.importlib.util.spec_from_file_location("__main__",cad.DOMAIN)
    assert not list(c.bundle.rglob('__pycache__'))
    assert before=={p.relative_to(c.bundle).as_posix():entry(p) for p in c.bundle.rglob('*') if p.is_file()}
    # No mutation of the host verifier or actual source policy.
    assert host.source_files()["platform/contracts.py"]==BASE/"caelab/contracts.py"


@pytest.mark.parametrize("name",["parent_verifier/adapter/fixture_assembly.py",
    "parent_verifier/domain/assembly_interfaces.py","parent_verifier/platform/contracts.py"])
def test_original_cad_verifier_capsule_tamper_blocks_before_native(context,name):
    c=context; obj=c.constructor(current_source_files=explicit_current(c))
    (c.bundle/"capsule"/name).write_bytes((c.bundle/"capsule"/name).read_bytes()+b"TAMPER")
    with pytest.raises(ValueError,match="pin drift"): capture(c,obj)
    assert not c.output.exists() and not c.loaded


def test_current_drift_during_original_cad_code_load_refuses_before_capture(context):
    c=context; obj=c.constructor(current_source_files=explicit_current(c))
    original=r.QualifiedAssemblyMeshBundle._source_module
    def changed(self,name,*args,**kwargs):
        module=original(self,name,*args,**kwargs)
        if name=="parent_verifier/adapter/fixture_assembly.py":
            c.main_sources["parent_verifier/platform/contracts.py"]["sha256"]="f"*64
        return module
    c.monkeypatch.setattr(r.QualifiedAssemblyMeshBundle,"_source_module",changed)
    with pytest.raises(ValueError,match="source differs"): capture(c,obj)
    assert not c.output.exists() and not c.loaded


def test_changed_mode_uses_preserved_cad_assert_not_host_source_override(context,monkeypatch):
    import subprocess
    c=context; obj=c.constructor(current_source_files=explicit_current(c))
    def forbidden(*args,**kwargs): raise AssertionError("No native/provider operation admitted")
    monkeypatch.setattr(subprocess,"Popen",forbidden)
    monkeypatch.setattr(subprocess,"run",forbidden)
    # The former path failed here; the unchanged envelope helper now receives
    # its own isolated original CAD verifier, without changing this host hook.
    monkeypatch.setattr(c.current,"validate_parent",lambda *a: (_ for _ in ()).throw(
        ValueError("Assembly source changed; preserved outputs must not be admitted")))
    _,descriptor=capture(c,obj)
    assert descriptor["parent_verification_basis"]["cad_sources"]=="ORIGINAL_CAPSULE"
    assert descriptor["parent_verification_basis"]["common_runtime_imports"]=="CURRENT_CORE_INTERFACES"
    with pytest.raises(ValueError,match="Assembly source changed"):
        c.current.validate_parent(c.parent_result,c.parent)


@pytest.mark.parametrize("name",["request.json","result.json","capsule/assembly_mesh.py","mesh.msh","parent/cad/component.bin"])
def test_post_capture_original_byte_drift_refuses(context,name):
    c=context; obj,_=capture(c)
    (c.bundle/name).write_bytes((c.bundle/name).read_bytes()+b"CHANGED")
    with pytest.raises(ValueError,match="pin drift|identity drift"):
        obj.recheck(c.output)
    assert len(c.loaded)==1 and c.loaded[0].calls==[str(c.bundle)]


@pytest.mark.parametrize("name",["request.json","result.json","capsule/fixture_assembly_mesh.py",
    "parent/cad/assembly_catalog.json","mesh.msh",r._RECEIPT])
def test_post_capture_copied_bytes_refuse(context,name):
    c=context; obj,_=capture(c)
    (c.output/name).write_bytes((c.output/name).read_bytes()+b"CHANGED")
    with pytest.raises(ValueError,match="pin drift|identity drift"):
        obj.recheck(c.output)


def test_consistently_rewritten_copy_result_cannot_replace_operator_pins(context):
    c=context; obj,_=capture(c)
    (c.output/"mesh.msh").write_bytes(b"NEW INTERNALLY CONSISTENT SELF-DECLARED MESH")
    rewritten=deepcopy(c.result)
    rewritten["output_files"]["mesh.msh"]=entry(c.output/"mesh.msh")
    rewritten["mesh_revision"]=hashlib.sha256(r._canonical(rewritten)).hexdigest()
    save(c.output,"result.json",rewritten)
    with pytest.raises(ValueError,match="result.json|identity drift"):
        obj.recheck(c.output)


@pytest.mark.parametrize("pin",["request_entry","result_entry","mesh_revision","source_files"])
def test_foreign_trusted_identity_rejects_before_capsule_execution(context,pin):
    c=context
    changes={pin:"f"*64} if pin=="mesh_revision" else {pin:{"sha256":"f"*64,"size_bytes":0}}
    if pin=="source_files":
        changes={pin:deepcopy(c.source_files)}
        changes[pin]["fixture_assembly_mesh.py"]["sha256"]="f"*64
    with pytest.raises(ValueError):
        capture(c,c.constructor(**changes))
    assert not c.loaded and not c.output.exists()


def test_changed_source_sentinel_rejects_before_python_exec(context,tmp_path):
    c=context; sentinel=tmp_path/"must-not-execute"
    (c.bundle/"capsule/fixture_assembly_mesh.py").write_text(f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('bad')\n")
    with pytest.raises(ValueError,match="pin drift"):
        capture(c)
    assert not sentinel.exists() and not c.loaded and not c.events


def test_source_matching_malicious_pyc_is_rejected_before_exec(context,tmp_path):
    c=context; sentinel=tmp_path/"cached-code-must-not-execute"
    code=compile(f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('bad')\n","cached","exec")
    cached=c.bundle/"capsule/__pycache__/fixture_assembly_mesh.cpython-312.pyc"
    cached.parent.mkdir()
    cached.write_bytes(importlib.util.MAGIC_NUMBER+b"\x00"*12+marshal.dumps(code))
    assert entry(c.bundle/"capsule/fixture_assembly_mesh.py")==c.source_files["fixture_assembly_mesh.py"]
    with pytest.raises(ValueError,match="Unexpected reuse tree member.*cache forbidden"):
        capture(c)
    assert not sentinel.exists() and not c.loaded and not c.events


@pytest.mark.parametrize("path,name",[("foreign.py","_captured_mesh_domain"),("assembly_mesh.py","__main__")])
def test_private_domain_loader_rejects_other_source_or_module(context,path,name):
    c=context; obj=c.constructor()
    helper=obj._original_helper()
    with pytest.raises(ValueError,match="Only the exact pinned assembly Domain"):
        helper.standalone(c.bundle/"capsule"/path,name)


def test_private_loader_executes_pinned_domain_without_cache(context):
    c=context; obj=c.constructor()
    helper=obj._original_helper()
    for name in ("_captured_mesh_domain","_assembly_mesh_domain"):
        helper.standalone(c.bundle/"capsule/assembly_mesh.py",name).check_profile(c.request["profile"])
    assert not list(c.bundle.rglob('__pycache__'))


@pytest.mark.parametrize("kind",["hash","bool_size","path","case_alias","missing_source","file_directory"])
def test_malformed_operator_configuration_rejects(context,kind):
    c=context
    changes={}
    if kind=="hash":
        changes={"request_entry":{"sha256":"NotAHash","size_bytes":1}}
    elif kind=="bool_size":
        changes={"result_entry":{"sha256":"a"*64,"size_bytes":True}}
    else:
        values=deepcopy(c.source_files)
        if kind=="path": values["../escape.py"]={"sha256":"a"*64,"size_bytes":0}
        if kind=="case_alias": values["GMSH.PY"]=values["gmsh.py"]
        if kind=="missing_source": values.pop("gmsh.py")
        if kind=="file_directory": values["gmsh.py/file"]={"sha256":"a"*64,"size_bytes":0}
        changes={"source_files":values}
    with pytest.raises(ValueError): c.constructor(**changes)
    assert not c.loaded


def test_duplicate_operator_map_items_reject(context):
    class Duplicate(dict):
        def items(self): return list(super().items())+[next(iter(super().items()))]
    with pytest.raises(ValueError,match="Duplicate/aliased"):
        context.constructor(source_files=Duplicate(context.source_files))


@pytest.mark.parametrize("data",[b'{"source_files":{},"source_files":{}}',b'{"synthetic":1e999}',b'{"synthetic":NaN}',b'\xff'])
def test_strict_original_json_before_source_execution(context,data):
    c=context; write(c.bundle,"request.json",data)
    with pytest.raises((ValueError,UnicodeDecodeError)):
        capture(c,c.constructor(request_entry=entry(c.bundle/"request.json")))
    assert not c.loaded and not c.events


@pytest.mark.parametrize("kind",["bundle_child","parent_child","parent_ancestor","captured_parent"])
def test_overlap_and_captured_mesh_parent_are_not_live_cad(context,kind):
    c=context
    output=c.output; parent=c.parent
    if kind=="bundle_child": output=c.bundle/"new"
    if kind=="parent_child": output=c.parent/"new"
    if kind=="parent_ancestor": output=c.parent.parent
    if kind=="captured_parent": parent=c.bundle/"parent"
    with pytest.raises(ValueError,match="overlap"):
        c.constructor().capture(c.parent_result,parent,output)
    assert not c.loaded


def test_nonempty_destination_preserved_and_refused(context):
    c=context; c.output.mkdir(); (c.output/"old.txt").write_bytes(b"KEEP")
    with pytest.raises(ValueError,match="Fresh empty"):
        capture(c)
    assert (c.output/"old.txt").read_bytes()==b"KEEP" and not c.loaded


@pytest.mark.parametrize("kind",["source","output_ancestor","live_parent"])
def test_symlink_paths_refused(context,tmp_path,kind):
    c=context; obj=c.constructor(); output=c.output; parent=c.parent
    if kind=="source":
        original=c.bundle/"capsule/gmsh.py"; target=tmp_path/"external-sdk"
        original.rename(target); original.symlink_to(target)
    elif kind=="output_ancestor":
        target=tmp_path/"real-target"; target.mkdir(); link=tmp_path/"link"
        link.symlink_to(target,target_is_directory=True); output=link/"new"
    else:
        link=tmp_path/"live-link"; link.symlink_to(parent,target_is_directory=True); parent=link
    with pytest.raises(ValueError,match="Symlink/junction/reparse"):
        obj.capture(c.parent_result,parent,output)
    assert not c.loaded


def test_windows_reparse_attribute_control_is_explicitly_synthetic(context):
    c=context; real=Path.lstat; marked=c.bundle/"capsule/gmsh.py"
    def observation(path):
        info=real(path)
        if path==marked:
            fields={name:getattr(info,name) for name in dir(info) if name.startswith('st_')}
            fields["st_file_attributes"]=0x400
            return SimpleNamespace(**fields)
        return info
    c.monkeypatch.setattr(Path,"lstat",observation)
    with pytest.raises(ValueError,match="Symlink/junction/reparse"):
        capture(c)
    assert not c.loaded  # This is not an actual Windows junction qualification.


@pytest.mark.parametrize("where",["original","copy"])
def test_hardlinked_artifacts_refused(context,tmp_path,where):
    c=context; obj=c.constructor()
    if where=="original":
        os.link(c.bundle/"mesh.msh",tmp_path/"aliased-input")
        with pytest.raises(ValueError,match="Regular unshared"):
            capture(c,obj)
    else:
        capture(c,obj); os.link(c.output/"mesh.msh",tmp_path/"aliased-copy")
        with pytest.raises(ValueError,match="Regular unshared"):
            obj.recheck(c.output)


@pytest.mark.parametrize("change",["identity","files","source"])
def test_exact_main_live_parent_and_source_join_required(context,change):
    c=context
    if change=="source":
        c.main_sources["assembly_mesh.py"]["sha256"]="f"*64
    else:
        old=c.current.validate_parent
        def altered(*args):
            values=old(*args)
            if change=="identity": values["identity"]["cad_revision"]="f"*64
            else: values["files"].pop("proposal.json")
            return values
        c.monkeypatch.setattr(c.current,"validate_parent",altered)
    with pytest.raises(ValueError,match="source differs|identity/files differ"):
        capture(c)
    assert not c.output.exists() and not c.loaded


def test_live_parent_post_capture_drift_refuses(context):
    c=context; obj,_=capture(c)
    (c.parent/"cad/component.bin").write_bytes(b"FOREIGN PARENT")
    with pytest.raises(ValueError,match="pin drift|identity drift"):
        obj.recheck(c.output)


@pytest.mark.parametrize("where",["original","copy"])
def test_same_bytes_replaced_file_identity_is_not_silent_mutation(context,where):
    c=context; obj,_=capture(c)
    root=c.bundle if where=="original" else c.output
    old=root/"mesh.msh"; before=entry(old)
    replacement=root/"replacement.tmp"
    replacement.write_bytes(old.read_bytes()); replacement.replace(old)
    assert entry(old)==before
    with pytest.raises(ValueError,match="identity drift"):
        obj.recheck(c.output)


def test_partial_exclusive_capture_failure_is_preserved(context):
    c=context; original=r._read
    def controlled(root,name,pin,**kwargs):
        if root==c.output and name=="capsule/assembly_mesh.py":
            raise OSError("Synthetic after-copy verification failure")
        return original(root,name,pin,**kwargs)
    c.monkeypatch.setattr(r,"_read",controlled)
    with pytest.raises(OSError,match="Synthetic after-copy"):
        capture(c)
    assert (c.output/"request.json").read_bytes()==(c.bundle/"request.json").read_bytes()
    assert (c.output/"capsule/assembly_mesh.py").read_bytes()==DOMAIN
    assert not (c.output/r._RECEIPT).exists()
    with pytest.raises(ValueError,match="Fresh empty"):
        capture(c)


def test_unknown_capture_cannot_self_admit_a_receipt(context):
    c=context; obj,_=capture(c)
    foreign=c.output.with_name("copied-capture")
    shutil.copytree(c.output,foreign)
    with pytest.raises(ValueError,match="completed frozen capture"):
        obj.recheck(foreign)
    with pytest.raises(ValueError,match="completed frozen capture"):
        c.constructor().recheck(c.output)


def test_imports_have_no_native_or_provider_admission(tmp_path):
    import subprocess

    reader=(BASE/"caelab/adapters/fixture_assembly_mesh_reuse.py").resolve()
    source=reader.read_bytes()
    expected={"filename":str(reader),"sha256":hashlib.sha256(source).hexdigest(),
              "size_bytes":len(source)}
    guarded_roots=("gmsh","cadquery","OCP","code_aster","FreeCAD","Part",
                   "mgis","mtest","openai","anthropic","ollama","litellm")
    # An unrelated earlier test may have loaded these modules in the parent.
    # Preserve that evidence; admission is checked in an isolated interpreter.
    parent_modules={name:module for name,module in sys.modules.copy().items()
                    if name.split(".",1)[0] in guarded_roots}
    script=r'''
import builtins
import hashlib
import importlib
import importlib.abc
import json
from pathlib import Path
import sys
from types import ModuleType

filename=Path(sys.argv[1]).resolve()
source=filename.read_bytes()
pin={"filename":str(filename),"sha256":hashlib.sha256(source).hexdigest(),
     "size_bytes":len(source)}
assert pin=={"filename":sys.argv[1],"sha256":sys.argv[2],
             "size_bytes":int(sys.argv[3])},pin
roots=set(json.loads(sys.argv[4]))
def loaded_guarded_modules():
    return sorted(name for name in sys.modules if name.split(".",1)[0] in roots)
assert loaded_guarded_modules()==[]
attempts=[]
class BlockedImport(RuntimeError):
    pass
def reject(name):
    if name.split(".",1)[0] in roots:
        attempts.append(name)
        raise BlockedImport(name)
original_import=builtins.__import__
def guarded_import(name,*args,**kwargs):
    reject(name)
    return original_import(name,*args,**kwargs)
class ImportGuard(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        reject(fullname)
        return None
builtins.__import__=guarded_import
sys.meta_path.insert(0,ImportGuard())

# Execute the checked read buffer directly, so an existing pyc cannot be used.
module=ModuleType("_qualified_mesh_reader_import_control")
module.__file__=str(filename)
module.__package__=""
sys.modules[module.__name__]=module
code=compile(source,str(filename),"exec")
exec(code,module.__dict__)
assert code.co_filename==pin["filename"]
assert attempts==[]
assert loaded_guarded_modules()==[]
reader_attempts=list(attempts)
assert module._Pin("a"*64,0).value()=={"sha256":"a"*64,"size_bytes":0}
assert not hasattr(module.QualifiedAssemblyMeshBundle,"solve")
assert not hasattr(module.QualifiedAssemblyMeshBundle,"mesh_parent")
decimal=importlib.import_module("decimal")
assert decimal.Decimal("1.25")+decimal.Decimal("2.75")==decimal.Decimal("4")
assert attempts==[]

rejections=[]
for name,operation in (("openai",lambda:__import__("openai")),
                       ("gmsh",lambda:importlib.import_module("gmsh"))):
    try:
        operation()
    except BlockedImport as error:
        assert str(error)==name
        rejections.append(name)
    else:
        raise AssertionError("Import guard admitted "+name)
assert attempts==["openai","gmsh"]
assert loaded_guarded_modules()==[]
print(json.dumps({"executed_reader":pin,"reader_import_attempts":reader_attempts,
                  "standard_library_positive_control":True,
                  "reader_positive_control":True,"rejected_imports":rejections,
                  "loaded_guarded_modules":loaded_guarded_modules(),
                  "solve_admitted":False,"mesh_parent_admitted":False},sort_keys=True))
'''
    command=[sys.executable,"-I","-S","-B","-c",script,str(reader),
             expected["sha256"],str(expected["size_bytes"]),json.dumps(guarded_roots)]
    completed=subprocess.run(command,capture_output=True,text=True,timeout=30)
    (tmp_path/"reader-import-command.json").write_text(json.dumps(command),encoding="utf-8")
    (tmp_path/"reader-import.stdout.json").write_text(completed.stdout,encoding="utf-8")
    (tmp_path/"reader-import.stderr.txt").write_text(completed.stderr,encoding="utf-8")
    assert completed.returncode==0,(completed.stdout,completed.stderr)
    receipt=json.loads(completed.stdout)
    assert receipt["executed_reader"]==expected
    assert receipt["reader_import_attempts"]==[]
    assert receipt["standard_library_positive_control"] is True
    assert receipt["reader_positive_control"] is True
    assert receipt["rejected_imports"]==["openai","gmsh"]
    assert receipt["loaded_guarded_modules"]==[]
    assert receipt["solve_admitted"] is False
    assert receipt["mesh_parent_admitted"] is False
    after_modules={name:module for name,module in sys.modules.copy().items()
                   if name.split(".",1)[0] in guarded_roots}
    assert after_modules.keys()==parent_modules.keys()
    assert all(after_modules[name] is module for name,module in parent_modules.items())
    assert not hasattr(r.QualifiedAssemblyMeshBundle,"solve")
    assert not hasattr(r.QualifiedAssemblyMeshBundle,"mesh_parent")
