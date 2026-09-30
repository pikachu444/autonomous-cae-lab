"""Trusted cards, process admission and typed output regressions; no solver runs.

The fixture stream is explicitly synthetic parser test data, not native proof.
Actual native physics acceptance is exclusively scripts.verify_openradioss.
"""

from copy import deepcopy
import hashlib
from pathlib import Path
import subprocess

import pytest

from caelab import Lab
from caelab.adapters import openradioss as transport
from caelab.adapters.openradioss import OpenRadiossAdapter, decks
from caelab.adapters.openradioss_worker import (expected_history_times, parse_history, starter_admission)
from caelab.storage import canonical_hash, load_json
from plugins.explicit_dynamics.reference import reference
from scripts.verify_openradioss import specification


def small_settings(wall=False):
    s = specification("rigid_cube_ground_stop" if wall else "rigid_cube_freefall")
    s.update(end_time_s=.02 if wall else .002, history_interval_s=1e-4)
    if wall: s["center_height_m"] = .051
    return s


def starter_text(s):
    return "\n".join(["TEST ONLY: no native executable has run", "NO SYNTAX ERROR DETECTED", "NORMAL TERMINATION",
        "0 ERROR(S)", "0 WARNING(S)", "WORK UNIT SYSTEM ( kg , m , s ) 1 1 1",
        "INPUT UNIT SYSTEM ( kg , m , s ) 1 1 1", "NUMNOD: nodes 9", "NUMELS: solids 1",
        "NRBODY: bodies 1", f"NRWALL: walls {int(s['case']=='rigid_cube_ground_stop')}",
        "PRIMARY NODE 9", "REMOVE SECONDARY NODES FROM RIGID WALL(IF=0) 0", "CENTER OF MASS FLAG 3",
        "NO TRUE INCOMPATIBLE KINEMATIC CONDITION"]) + "\n"


def engine_text(s):
    count = round(s["end_time_s"] / s["time_step_s"])
    rows = [f"{i} {i*s['time_step_s']:.12g} {s['time_step_s']:.12g} FIXED 0 0.0% 0 0 0 0 0 {s['mass_kg']:.12g} 0"
            for i in range(count + 1)]
    return "TEST ONLY: no native executable has run\n" + f"FINAL TIME {s['end_time_s']}\n" + "\n".join(rows) + f"\nNORMAL TERMINATION\nTOTAL NUMBER OF CYCLES : {count+2}\n"


def typed_stream(s, *, change=None, skip=None):
    parts = ["dropT01 FORMAT"]
    def record(specs, value):
        parts.append("ZZZZZEOR " + " ".join(str(n) + kind for n, kind in specs))
        if isinstance(value, str): parts.append(value)
        else:
            width = 16 if specs[0][1] == "I" else 5
            for start in range(0, len(value), width):
                parts.append(" ".join(str(v) if specs[0][1] == "I" else f"{v:.8E}" for v in value[start:start+width]))
    def entity(identifier, title): return f"{identifier:10d}{title:40}"
    record([(1,"I"),(72,"C")], f"{3040:5d}" + "TEST ONLY parser data".ljust(72))
    record([(80,"C")], "TEST ONLY parser data; no native execution".ljust(80))
    wall = s["case"] == "rigid_cube_ground_stop"
    record([(6,"I")], [1,2,1,1,3 if wall else 2,22])
    record([(22,"I")], list(range(1,23)))
    record([(1,"I"),(40,"C"),(4,"I")], entity(1,"RIGID_CUBE") + "".join(f"{v:5}" for v in [0,1,1,0]))
    for identifier,title in [(1,"RIGID_MASS_CARRIER_NOT_QUALIFIED"),(0,"no_title"),(1,"RIGID_MASS_CARRIER")]:
        record([(1,"I"),(40,"C")],entity(identifier,title))
    record([(5,"I"),(40,"C")],"".join(f"{v:10}" for v in [0,0,0,1,0])+"GLOBAL MODEL".ljust(40))
    record([(1,"I")],[1])
    groups = [(3,102,[1],[3],"WALL_NORMAL_IMPULSE")] if wall else []
    groups += [(1,0,[1,9],[3,6,9,18],"NODAL_KINEMATICS"),(2,103,[1],[3,7,8,9],"BODY_IMPULSES_ROTATIONS")]
    for identifier,kind,ids,variables,title in groups:
        record([(5,"I"),(40,"C")],"".join(f"{v:10}" for v in [identifier,kind,0,len(ids),len(variables)])+title.ljust(40))
        for i in ids:record([(1,"I"),(40,"C")],entity(i,"TEST ONLY entity"))
        record([(len(variables),"I")],variables)
    for index,t in enumerate(expected_history_times(s)):
        if index == skip: continue
        ref=reference(s,t);dt=s["time_step_s"];h=s["center_height_m"]
        hit=wall and t>=ref["impact_time_s"]
        velocity=0 if hit else reference(s,max(0,t-dt/2))["velocity_m_s"]
        a=0 if hit else -s["gravity_m_s2"]
        glob=[0.0]*22;glob[1]=ref["kinetic_energy_j"];glob[4]=s["mass_kg"]*ref["velocity_m_s"]
        glob[5]=s["mass_kg"];glob[6]=dt;glob[8]=glob[1]-.5*s["mass_kg"]*s["initial_velocity_m_s"]**2
        node=[ref["z_m"]-h,velocity,a,ref["z_m"]-s["edge_m"]/2,ref["z_m"]-h,velocity,a,ref["z_m"]]
        channels={1:node,2:[0,0,0,0],3:[-ref["ground_impulse_n_s"]]}
        if change: change(index,t,glob,channels)
        record([(1,"R")],[t]);record([(22,"R")],glob)
        for identifier,_,ids,variables,_ in groups:record([(len(ids)*len(variables),"R")],channels[identifier])
    return "\n".join(parts)+"\n"


def native_fixture(path,s,**kwargs):
    path.mkdir(exist_ok=True)
    (path/"drop_0000.out").write_text(starter_text(s))
    (path/"drop_0001.out").write_text(engine_text(s))
    (path/"dropT01").write_text(typed_stream(s,**kwargs))


def test_trusted_cards_have_exact_rigid_main_wall_units_and_bounded_histories():
    flight,engine=decks(specification())
    wall,_=decks(specification("rigid_cube_ground_stop"))
    assert "/RWALL" not in flight and "/RWALL/PLANE/1" in wall
    assert "/DTIX\n" in engine and "/TFILE/3\n" in engine and "/PRINT/1" in engine
    body=wall.split("/RBODY/1\nRIGID_CENTER9\n")[1].splitlines()[0]
    assert body[:40] == "".join(f"{v:10}" for v in [9,0,0,2])
    assert body[60:] == "".join(f"{v:10}" for v in [1,0,3,0])
    grav=flight.split("/GRAV/1\nGRAVITY_ALL_NODES\n")[1].splitlines()[0]
    assert grav[50:60] == " "*10
    assert "/GRNOD/NODE/3\nBODY_MAIN_CONTACT\n         9\n" in wall


def test_source_clock_reconstructs_actual_known_record_admission_without_curve_fit():
    flight=expected_history_times(specification())
    wall=expected_history_times(specification("rigid_cube_ground_stop"))
    assert len(flight)==200 and flight[-1] == pytest.approx(.1991)
    assert flight[3] == pytest.approx(.0031)
    assert len(wall)==5001 and wall[-1] == pytest.approx(.5)


@pytest.mark.parametrize("wall",[False,True])
def test_typed_metadata_channels_raw_observations_and_cumulative_impulse(tmp_path,wall):
    s=small_settings(wall);native_fixture(tmp_path,s)
    parsed=parse_history(tmp_path,s)
    assert len(parsed["rows"])==len(expected_history_times(s))
    assert parsed["native_cycle_count"] == round(s["end_time_s"]/s["time_step_s"])+2
    assert parsed["rows"][-1]["ground_impulse_n_s"] == pytest.approx(reference(s,parsed["rows"][-1]["time_s"])["ground_impulse_n_s"])
    assert parsed["raw_samples"] and parsed["native_cycle_observations"]
    assert parsed["rows"][0]["ground_force_interval_average_n"] is None
    for a,b in zip(parsed["rows"],parsed["rows"][1:]):
        assert b["ground_force_interval_average_n"] == pytest.approx(
            (b["ground_impulse_n_s"]-a["ground_impulse_n_s"])/(b["time_s"]-a["time_s"]))


def test_constraint_witness_preserves_raw_incoming_child_v_and_correct_advance(tmp_path):
    s=small_settings(True)
    def change(i,t,glob,ch):
        if i==150:
            ch[1][1]=-.1;ch[1][2]=.1/s["time_step_s"]
    native_fixture(tmp_path,s,change=change)
    row=parse_history(tmp_path,s)["rows"][150]
    assert row["bottom_velocity_m_s"] == -.1 and row["velocity_m_s"] == 0
    assert abs(row["rigid_advance_residual_m_s"]) < 1e-8


@pytest.mark.parametrize("damage",["tail","interior","clock","witness","negative","nonfinite","metadata","progress","termination"])
def test_complete_but_corrupt_native_files_are_rejected_even_with_normal_termination(tmp_path,damage):
    s=small_settings(True)
    def change(i,t,glob,ch):
        if i==3:
            if damage=="clock":glob[4]+=.0002
            if damage=="witness":ch[1][1]+=.0002
            if damage=="negative":glob[1]=-.1
            if damage=="nonfinite":glob[1]=float("nan")
    skip=len(expected_history_times(s))-1 if damage=="tail" else 5 if damage=="interior" else None
    native_fixture(tmp_path,s,change=change,skip=skip)
    if damage=="metadata":
        p=tmp_path/"dropT01";p.write_text(p.read_text().replace("3 6 9 18","3 6 8 18"))
    if damage in {"progress","termination"}:
        p=tmp_path/"drop_0001.out";lines=p.read_text().splitlines()
        if damage=="progress":lines=[l for l in lines if not l.startswith("10 ")]
        else:lines[-1]="TOTAL NUMBER OF CYCLES : 1"
        p.write_text("\n".join(lines)+"\n")
    with pytest.raises(ValueError):parse_history(tmp_path,s)


@pytest.mark.parametrize("bad",["warning","unit","count","constraint"])
def test_starter_preflight_native_report_blocks_before_engine(tmp_path,monkeypatch,bad):
    s=small_settings();adapter=OpenRadiossAdapter();calls=[]
    monkeypatch.setattr(transport,"runtime",lambda:(tmp_path,{}, {"test_only":True}))
    def fake_process(command,output,name,env):
        calls.append(name)
        if name=="starter":
            text=starter_text(s)
            replacements={"warning":("0 WARNING(S)","1 WARNING(S)"),"unit":("1 1 1","1 1000 1"),
                          "count":("NUMNOD: nodes 9","NUMNOD: nodes 8"),
                          "constraint":("NO TRUE INCOMPATIBLE KINEMATIC CONDITION","INCOMPATIBLE KINEMATIC CONDITION")}
            a,b=replacements[bad];(output/"drop_0000.out").write_text(text.replace(a,b))
        if name=="engine":pytest.fail("Engine must not execute after bad Starter admission")
        return "TEST ONLY version"
    monkeypatch.setattr(transport,"process",fake_process)
    result=adapter.solve(tmp_path/"simulation",s)
    assert result["status"]=="REJECTED" and result["solver_status"]=="NOT_RUN"
    assert calls==["starter_version","engine_version","starter"]
    assert all(not m["valid"] for m in result["metrics"].values())


def test_real_core_invalid_inputs_never_reach_starter_or_runtime(tmp_path,monkeypatch):
    adapter=OpenRadiossAdapter()
    monkeypatch.setattr(transport,"runtime",lambda:pytest.fail("Invalid model cannot inspect native runtime"))
    monkeypatch.setattr(transport,"process",lambda *a:pytest.fail("Invalid model cannot execute Starter"))
    lab=Lab(tmp_path,adapters={},analysis_adapters={},doe_adapters={},optimization_adapters={},pde_adapters={},
            model_analysis_adapters={adapter.backend:adapter})
    lab.create_study("S-explicit","TEST ONLY admission","Do invalid models block native execution?","Yes","No solver")
    s=specification();s["mass_kg"]=-1
    result=lab.run_model_analysis(study_id="S-explicit",experiment_id="E-invalid",backend=adapter.backend,settings=s)
    assert result["status"]=="REJECTED" and result["solver_status"]=="NOT_RUN"
    assert result["decision"]=="NOT_RELEASED" and result["cad_revision"] is None
    assert not (tmp_path/"experiments/E-invalid/simulation").exists()
    assert lab.inspect_experiment("E-invalid")==result


def test_core_preserves_corrupt_completed_native_evidence_without_valid_response(tmp_path,monkeypatch):
    adapter=OpenRadiossAdapter();s=small_settings()
    monkeypatch.setattr(transport,"runtime",lambda:(tmp_path,{}, {"test_only":True}))
    def fake_process(command,output,name,env):
        if name=="starter":(output/"drop_0000.out").write_text(starter_text(s))
        elif name=="engine":
            (output/"drop_0001.out").write_text(engine_text(s));(output/"dropT01").write_text("TEST ONLY truncated history\n")
        return "NORMAL TERMINATION TEST ONLY"
    monkeypatch.setattr(transport,"process",fake_process)
    lab=Lab(tmp_path/"store",adapters={},analysis_adapters={},doe_adapters={},optimization_adapters={},pde_adapters={},
            model_analysis_adapters={adapter.backend:adapter})
    lab.create_study("S-explicit","TEST ONLY corruption","Can exit0 qualify corrupt data?","No","No solver")
    result=lab.run_model_analysis(study_id="S-explicit",experiment_id="E-corrupt",backend=adapter.backend,settings=s)
    assert result["status"]=="REJECTED" and result["solver_status"]=="COMPLETED"
    assert result["decision"]=="NOT_RELEASED" and not any(m["valid"] for m in result["metrics"].values())
    assert result["cad_revision"] is None and "parent_experiment_id" not in result
    proposal=load_json(lab.store/"experiments/E-corrupt/proposal.json")
    assert result["model_revision"]==canonical_hash({"settings":s,"declaration":adapter.describe_model(s)})
    assert proposal["model"]["geometry"]["type"]=="cube" and proposal["loads"]
    assert "material_qualification" in lab.research_summary("E-corrupt")["unknown"]
    artifacts={a["path"]:a for a in result["artifacts"]}
    assert {"simulation/dropT01","simulation/drop_0000.out","simulation/drop_0001.out",
            "simulation/domain_reference.py","simulation/parser_source.py"} <= artifacts.keys()
    for name,artifact in artifacts.items():
        assert hashlib.sha256((lab.store/"experiments/E-corrupt"/name).read_bytes()).hexdigest()==artifact["sha256"]
    assert lab.inspect_experiment("E-corrupt")==result


def test_process_timeout_keeps_partial_evidence_and_never_uses_shell(tmp_path,monkeypatch):
    def timeout(command,**kwargs):
        assert not kwargs.get("shell") and kwargs["timeout"]==90 and kwargs["env"]=={"TEST":"ONLY"}
        raise subprocess.TimeoutExpired(command,90,output=b"TEST ONLY partial output",stderr=b"timeout")
    monkeypatch.setattr(transport.subprocess,"run",timeout)
    with pytest.raises(RuntimeError,match="evidence retained"):
        transport.process(["TEST ONLY executable"],tmp_path,"starter",{"TEST":"ONLY"})
    assert (tmp_path/"starter_stdout.log").read_bytes()==b"TEST ONLY partial output"
    assert (tmp_path/"starter_command.json").exists()


def test_runtime_checks_archive_executables_and_reader_configs_before_any_process(tmp_path,monkeypatch):
    """TEST ONLY miniature runtime bytes exercise the pin gate, not a solver."""
    root=tmp_path/"OpenRadioss";root.mkdir()
    archive=tmp_path/"OpenRadioss_linux64.zip";archive.write_bytes(b"TEST ONLY archive")
    executable=root/"exec/starter_linux64_gf";executable.parent.mkdir();executable.write_bytes(b"TEST ONLY executable")
    config=root/"hm_cfg_files/model.cfg";config.parent.mkdir();config.write_bytes(b"TEST ONLY configuration")
    config_digest=hashlib.sha256();config_digest.update(b"hm_cfg_files/model.cfg")
    config_digest.update(hashlib.sha256(config.read_bytes()).digest())
    monkeypatch.setenv("CAELAB_OPENRADIOSS_ROOT",str(root))
    monkeypatch.setattr(transport,"ARCHIVE_SHA256",hashlib.sha256(archive.read_bytes()).hexdigest())
    monkeypatch.setattr(transport,"RUNTIME_HASHES",{"exec/starter_linux64_gf":hashlib.sha256(executable.read_bytes()).hexdigest()})
    monkeypatch.setattr(transport,"CONFIGURATION_SHA256",config_digest.hexdigest())
    _,env,_=transport.runtime()
    assert env["OMP_NUM_THREADS"]=="2" and env["OMP_STACKSIZE"]=="64m"
    config.write_bytes(b"changed")
    with pytest.raises(RuntimeError,match="reader configurations"):transport.runtime()
    config.write_bytes(b"TEST ONLY configuration")
    executable.write_bytes(b"changed")
    with pytest.raises(RuntimeError,match="executable/library bytes"):transport.runtime()
    executable.write_bytes(b"TEST ONLY executable")
    archive.write_bytes(b"changed")
    with pytest.raises(RuntimeError,match="published SHA256"):transport.runtime()
