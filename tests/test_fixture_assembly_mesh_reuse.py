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
calls = []
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
               "parent_verifier/pin.json":b'{"synthetic":true}\n'}
    source_files = {name:write(bundle,"capsule/"+name, data) for name,data in sources.items()}
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


def test_imports_have_no_native_or_provider_admission():
    assert not any(name in sys.modules for name in ("gmsh","cadquery","OCP","code_aster"))
    assert not hasattr(r.QualifiedAssemblyMeshBundle,"solve")
    assert not hasattr(r.QualifiedAssemblyMeshBundle,"mesh_parent")
