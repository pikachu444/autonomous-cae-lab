"""Trusted cards, process admission and typed output regressions; no solver runs.

The fixture stream is explicitly synthetic parser test data, not native proof.
Actual native physics acceptance uses scripts.verify_openradioss and
scripts.verify_compliant_drop in fresh stores with frozen source.
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
from scripts.verify_compliant_drop import specification as compliant_specification


def small_settings(wall=False):
    s = specification("rigid_cube_ground_stop" if wall else "rigid_cube_freefall")
    s.update(end_time_s=.02 if wall else .002, history_interval_s=1e-4)
    if wall: s["center_height_m"] = .051
    return s


def starter_text(s):
    compliant = s["case"] == "rigid_cube_compliant_stop"
    extra = ["NPART: parts 2", "NUMGEO: properties 2", "NUMELR: springs 1", "NUMBCS: constraints 1",
             "NUMBER OF NODES 9", f"NEW X,Y,Z 0 0 {s['center_height_m']}",
             f"NEW MASS {s['mass_kg'] + s['spring_mass_kg']/2}", "TOTAL MASS AND MASS CENTER",
             "MASS X Y Z", f"{s['mass_kg'] + s['spring_mass_kg']} 0 0 1"] if compliant else []
    return "\n".join(["TEST ONLY: no native executable has run", "NO SYNTAX ERROR DETECTED", "NORMAL TERMINATION",
        "0 ERROR(S)", "0 WARNING(S)", "WORK UNIT SYSTEM ( kg , m , s ) 1 1 1",
        "INPUT UNIT SYSTEM ( kg , m , s ) 1 1 1", f"NUMNOD: nodes {11 if compliant else 9}", "NUMELS: solids 1",
        "NRBODY: bodies 1", f"NRWALL: walls {int(s['case']=='rigid_cube_ground_stop')}",
        "PRIMARY NODE 9", "REMOVE SECONDARY NODES FROM RIGID WALL(IF=0) 0", "CENTER OF MASS FLAG 3",
        "NO TRUE INCOMPATIBLE KINEMATIC CONDITION", *extra]) + "\n"


def engine_text(s):
    count = round(s["end_time_s"] / s["time_step_s"])
    mass = s["mass_kg"] + s.get("spring_mass_kg", 0)
    control = "SPRIN 2" if s["case"]=="rigid_cube_compliant_stop" else "FIXED 0"
    rows = [f"{i} {i*s['time_step_s']:.12g} {s['time_step_s']:.12g} {control} 0.0% 0 0 0 0 0 {mass:.12g} 0"
            for i in range(count + 1)]
    return "TEST ONLY: no native executable has run\n" + f"FINAL TIME {s['end_time_s']}\n" + "\n".join(rows) + f"\nNORMAL TERMINATION\nTOTAL NUMBER OF CYCLES : {count+2}\n"


def typed_stream(s, *, change=None, skip=None, observation=None):
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
    compliant = s["case"] == "rigid_cube_compliant_stop"
    record([(6,"I")], [2,2,2,1,3,22] if compliant else [1,2,1,1,3 if wall else 2,22])
    record([(22,"I")], list(range(1,23)))
    record([(1,"I"),(40,"C"),(4,"I")], entity(1,"RIGID_CUBE") + "".join(f"{v:5}" for v in [0,1,1,0]))
    if compliant:
        record([(1,"I"),(40,"C"),(4,"I")], entity(2,"STOP_SPRING") + "".join(f"{v:5}" for v in [0,2,2,0]))
    descriptions = [(1,"RIGID_MASS_CARRIER_NOT_QUALIFIED"),(0,"no_title"),(1,"RIGID_MASS_CARRIER")]
    if compliant: descriptions.append((2,"STOP_SPRING_PROPERTY"))
    for identifier,title in descriptions:
        record([(1,"I"),(40,"C")],entity(identifier,title))
    record([(5,"I"),(40,"C")],"".join(f"{v:10}" for v in [0,0,0,2 if compliant else 1,0])+"GLOBAL MODEL".ljust(40))
    record([(2 if compliant else 1,"I")],[1,2] if compliant else [1])
    groups = [(3,102,[1],[3],"WALL_NORMAL_IMPULSE")] if wall else []
    if compliant: groups.append((4,6,[2],[1,2,3,4,5,6,7,8,14],"STOP_CONSTITUTIVE_HISTORY"))
    groups += [(1,0,[1,9,10,11] if compliant else [1,9],[3,6,9,18],"NODAL_KINEMATICS"),(2,103,[1],[3,7,8,9],"BODY_IMPULSES_ROTATIONS")]
    for identifier,kind,ids,variables,title in groups:
        record([(5,"I"),(40,"C")],"".join(f"{v:10}" for v in [identifier,kind,0,len(ids),len(variables)])+title.ljust(40))
        for i in ids:record([(1,"I"),(40,"C")],entity(i,"TEST ONLY entity"))
        record([(len(variables),"I")],variables)
    for index,t in enumerate(expected_history_times(s)):
        if index == skip: continue
        ref=observation(index,t) if observation is not None else reference(s,t)
        dt=s["time_step_s"];h=s["center_height_m"]
        hit=wall and t>=ref["impact_time_s"]
        velocity=ref["velocity_m_s"] if observation is not None else (0 if hit else reference(s,max(0,t-dt/2))["velocity_m_s"])
        a=ref["acceleration_m_s2"] if observation is not None else (0 if hit else -s["gravity_m_s2"])
        if compliant:
            a=ref["acceleration_m_s2"]
            velocity=ref["velocity_m_s"] if t==0 else ref["velocity_m_s"]-.5*dt*a
        glob=[0.0]*22;glob[1]=ref["kinetic_energy_j"];glob[4]=s["mass_kg"]*ref["velocity_m_s"]
        glob[5]=s["mass_kg"];glob[6]=dt;glob[8]=glob[1]-.5*s["mass_kg"]*s["initial_velocity_m_s"]**2
        if compliant:
            glob[0]=ref["spring_internal_energy_j"];glob[9]=glob[0];glob[4]=ref["moving_mass_kg"]*ref["velocity_m_s"]
            glob[5]=ref["total_mass_kg"];glob[8]=glob[0]+glob[1]-.5*ref["moving_mass_kg"]*s["initial_velocity_m_s"]**2
        node=[ref["z_m"]-h,velocity,a,ref["z_m"]-s["edge_m"]/2,ref["z_m"]-h,velocity,a,ref["z_m"]]
        channels={1:node,2:[0,0,0,0],3:[-ref["ground_impulse_n_s"]]}
        if compliant:
            channels[1] += [0,0,0,-1]
            channels[1] += [ref["z_m"]-h,velocity,a,ref["z_m"]]
            channels[4]=[1,-ref["spring_force_n"],0,0,0,0,0,ref["spring_length_change_m"],ref["spring_internal_energy_j"]]
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


def small_compliant_settings():
    # Small synthetic parser case whose source-derived terminal clock includes
    # the end record; canonical actual runs retain their prescribed .5 seconds.
    s=compliant_specification(stiffness=100000);s.update(center_height_m=.05001,end_time_s=.02)
    return s


def test_compliant_trusted_cards_force_scale_mass_anchor_and_actual_channels():
    starter,_=decks(compliant_specification())
    assert "/RWALL" not in starter
    assert "/BCS/1\nANCHOR_TRANSLATIONS_FIXED\n   111 000         0         3\n" in starter
    assert "/PROP/SPRING/2\nSTOP_SPRING_PROPERTY\n" in starter
    prop=starter.split("/PROP/SPRING/2\nSTOP_SPRING_PROPERTY\n")[1].splitlines()
    assert float(prop[0][:20]) == .002 and prop[0][20:50] == " "*30
    assert [float(prop[1][i:i+20]) for i in range(0,100,20)] == [10000,0,1,0,1]
    assert [int(prop[2][i:i+10]) for i in range(0,50,10)] == [2,8,0,0,0]
    assert "/TH/SPRING/4\nSTOP_CONSTITUTIVE_HISTORY\n       OFF        FX        FY        FZ        MX        MY        MZ        LX        IE\n         2\n" in starter
    assert "/SPRING/2\n         2        10        11" in starter
    stiff,_=decks(compliant_specification(stiffness=20000))
    curve=stiff.split("/FUNCT/2\nFORCE_N_VS_ABSOLUTE_LENGTH_M\n")[1].splitlines()
    assert [float(curve[0][i:i+20]) for i in (0,20)] == [0,-21000]


def test_compliant_typed_native_observations_keep_force_ie_mass_and_fixed_anchor(tmp_path):
    s=small_compliant_settings();native_fixture(tmp_path,s)
    parsed=parse_history(tmp_path,s)
    assert parsed["hierarchy"] == [2,2,2,1,3,22]
    assert len(parsed["rows"]) == 201
    assert next(group for group in parsed["groups"] if group["id"]==4)["variables"] == [1,2,3,4,5,6,7,8,14]
    peak=max(parsed["rows"],key=lambda row:row["ground_force_n"])
    assert peak["spring_axial_force_n"] < 0 and peak["spring_internal_energy_j"] > 0
    assert peak["moving_mass_kg"] == pytest.approx(1.001)
    assert peak["fixed_mass_kg"] == pytest.approx(.001)
    assert peak["mass_kg"] == pytest.approx(1.002)
    assert peak["spring_length_m"] == pytest.approx(peak["z_m"]+1)
    assert all(row["anchor_z_m"]==-1 and row["anchor_velocity_m_s"]==0 for row in parsed["rows"])
    from plugins.explicit_dynamics.reference import assess
    assert all(check["status"]=="PASS" for check in assess(s,parsed["rows"])["checks"])


@pytest.mark.parametrize("residue",[-1e-4,1e-4])
def test_compliant_signed_work_residue_is_preserved_and_fixed_energy_gates_remain(tmp_path,residue):
    """Synthetic signed integration residue exercises semantics, not native proof."""
    s=small_compliant_settings()
    release=reference(s,0)["release_time_s"]
    def change(i,t,glob,ch):
        if t >= release:
            ch[4][8]=residue;glob[0]=residue;glob[9]=residue
    native_fixture(tmp_path,s,change=change)
    parsed=parse_history(tmp_path,s)
    assert parsed["rows"][-1]["spring_internal_energy_j"] == residue
    assert parsed["rows"][-1]["internal_energy_j"] == residue
    assert parsed["rows"][-1]["spring_global_internal_energy_j"] == residue
    from plugins.explicit_dynamics.reference import assess
    result=assess(s,parsed["rows"])
    assert all(check["status"]=="PASS" for check in result["checks"])
    for code in ("compliant_full_spring_energy","compliant_full_mechanical_energy","native_total_energy_work_balance"):
        check=next(check for check in result["checks"] if check["code"]==code)
        assert check["limit"]==.01 and check["observed"]==pytest.approx(abs(residue),abs=1e-8)
    assert result["metrics"]["minimum_signed_spring_work"]["value"] == min(0,residue)
    assert all(value["valid"] for value in result["metrics"].values())


@pytest.mark.parametrize("category",[0,9])
def test_compliant_inconsistent_global_work_category_cannot_hide_behind_energy_budget(tmp_path,category):
    s=small_compliant_settings()
    def change(i,t,glob,ch):
        if i==100:glob[category]+=.001
    native_fixture(tmp_path,s,change=change)
    with pytest.raises(ValueError,match="global/category spring energy"):
        parse_history(tmp_path,s)


def test_compliant_raw_force_acceleration_balance_detects_coordinated_clock_corruption(tmp_path):
    s=small_compliant_settings()
    def change(i,t,glob,ch):
        if i==190:
            # Preserve centered momentum and all rigid/half-step witnesses.
            # The tiny incoming-V change alone stays below its 0.002 m/s gate.
            for start in (0,4,12):
                ch[1][start+2]+=.001
                ch[1][start+1]-=.5*s["time_step_s"]*.001
    native_fixture(tmp_path,s,change=change)
    parsed=parse_history(tmp_path,s)
    from plugins.explicit_dynamics.reference import assess
    result=assess(s,parsed["rows"])
    failed=[check for check in result["checks"] if check["status"]=="FAIL"]
    assert [check["code"] for check in failed]==["native_force_acceleration_balance"]
    assert failed[0]["limit"]==1e-5 and failed[0]["observed"]==pytest.approx(.001001,abs=1e-7)
    assert not any(value["valid"] for value in result["metrics"].values())


@pytest.mark.parametrize("bad_control",["FIXED 0","SPRIN 1","SPRIN 3"])
def test_compliant_source_control_tag_does_not_replace_actual_dt_id_or_cycle_gates(tmp_path,bad_control):
    s=small_compliant_settings();native_fixture(tmp_path,s)
    path=tmp_path/"drop_0001.out"
    path.write_text(path.read_text().replace("SPRIN 2",bad_control))
    with pytest.raises(ValueError,match="cycle observation"):
        parse_history(tmp_path,s)


def test_compliant_engine_part_table_is_not_mistaken_for_cycle_output(tmp_path):
    s=small_compliant_settings();native_fixture(tmp_path,s)
    path=tmp_path/"drop_0001.out"
    path.write_text("1 1.0000 0.002000 0.05000 100.0 0 0 0\n"+path.read_text())
    parsed=parse_history(tmp_path,s)
    assert len(parsed["native_cycle_observations"])==201
    assert all(row["controlling_element_type"]=="SPRIN" and row["controlling_element_id"]==2
               and row["time_step_s"]==s["time_step_s"] for row in parsed["native_cycle_observations"])


@pytest.mark.parametrize("wall",[False,True])
def test_original_rigid_cases_keep_their_zero_spring_category_gate(tmp_path,wall):
    s=small_settings(wall)
    def change(i,t,glob,ch):
        if i==3:glob[9]=-.0001
    native_fixture(tmp_path,s,change=change)
    with pytest.raises(ValueError,match="contact-energy"):
        parse_history(tmp_path,s)


@pytest.mark.parametrize("damage",["anchor","attachment","torque","global_mass","negative_force","negative_ie","off","metadata","tail","interior"])
def test_compliant_parser_rejects_wrong_native_layout_mass_fixed_state_or_coverage(tmp_path,damage):
    s=small_compliant_settings()
    def change(i,t,glob,ch):
        if i==20:
            if damage=="anchor":ch[1][9]=.01
            elif damage=="attachment":ch[1][13]=.01
            elif damage=="torque":ch[4][4]=.01
            elif damage=="global_mass":glob[5]=1
            elif damage=="negative_force":ch[4][1]=.1
            elif damage=="negative_ie":ch[4][8]=-.1
            elif damage=="off":ch[4][0]=0
    skip=len(expected_history_times(s))-1 if damage=="tail" else 100 if damage=="interior" else None
    native_fixture(tmp_path,s,change=change,skip=skip)
    if damage=="metadata":
        p=tmp_path/"dropT01";p.write_text(p.read_text().replace("1 2 3 4 5 6 7 8 14","1 2 3 4 5 6 7 8 13"))
    with pytest.raises(ValueError):parse_history(tmp_path,s)


@pytest.mark.parametrize("damage",["force","ie","length"])
def test_complete_native_compliant_channels_do_not_get_replaced_by_reference(tmp_path,damage):
    s=small_compliant_settings()
    def change(i,t,glob,ch):
        if i==100:
            if damage=="force":ch[4][1]-=.1
            elif damage=="ie":ch[4][8]+=.02;glob[0]+=.02;glob[9]+=.02
            else:ch[4][7]+=.001
    native_fixture(tmp_path,s,change=change)
    parsed=parse_history(tmp_path,s)
    from plugins.explicit_dynamics.reference import assess
    result=assess(s,parsed["rows"])
    assert any(check["status"]=="FAIL" for check in result["checks"])
    assert not any(value["valid"] for value in result["metrics"].values())


@pytest.mark.parametrize("damage",["moving_mass","total_mass","total_nonfinite","center","secondary_count","warning"])
def test_compliant_actual_starter_mass_and_warning_admission_blocks_engine(tmp_path,monkeypatch,damage):
    s=small_compliant_settings();calls=[]
    monkeypatch.setattr(transport,"runtime",lambda:(tmp_path,{}, {"test_only":True}))
    def fake_process(command,output,name,env):
        calls.append(name)
        if name=="starter":
            text=starter_text(s)
            replacements={"moving_mass":("NEW MASS 1.001","NEW MASS 1"), "total_mass":("1.002 0 0 1","1 0 0 1"),
                          "total_nonfinite":("1.002 0 0 1","nan 0 0 1"), "center":("NEW X,Y,Z 0 0","NEW X,Y,Z .01 0"),
                          "secondary_count":("NUMBER OF NODES 9","NUMBER OF NODES 8"), "warning":("0 WARNING(S)","1 WARNING(S)")}
            a,b=replacements[damage];text=text.replace(a,b)
            (output/"drop_0000.out").write_text(text)
        if name=="engine":pytest.fail("Engine cannot follow bad actual Starter assembly")
        return "TEST ONLY version"
    monkeypatch.setattr(transport,"process",fake_process)
    result=OpenRadiossAdapter().solve(tmp_path/"simulation",s)
    assert result["status"]=="REJECTED" and result["solver_status"]=="NOT_RUN"
    assert calls==["starter_version","engine_version","starter"]
    assert "peak_contact_force" in result["metrics"] and not any(value["valid"] for value in result["metrics"].values())


@pytest.mark.parametrize("key,value",[("spring_stiffness_n_m",0),("spring_stiffness_n_m",float("nan")),("mass_kg",-1)])
def test_compliant_real_core_invalid_inputs_do_not_read_runtime_or_execute(tmp_path,monkeypatch,key,value):
    adapter=OpenRadiossAdapter()
    monkeypatch.setattr(transport,"runtime",lambda:pytest.fail("Invalid model cannot read runtime"))
    lab=Lab(tmp_path,adapters={},analysis_adapters={},doe_adapters={},optimization_adapters={},pde_adapters={},model_analysis_adapters={adapter.backend:adapter})
    lab.create_study("S-compliant","TEST ONLY","Invalid input?","Blocked","No solver")
    s=compliant_specification();s[key]=value
    if isinstance(value,float) and value != value:
        with pytest.raises(ValueError,match="JSON compliant"):
            lab.run_model_analysis(study_id="S-compliant",experiment_id="E-invalid",backend=adapter.backend,settings=s)
        assert not (tmp_path/"experiments/E-invalid").exists()
        return
    result=lab.run_model_analysis(study_id="S-compliant",experiment_id="E-invalid",backend=adapter.backend,settings=s)
    assert result["status"]=="REJECTED" and result["solver_status"]=="NOT_RUN"
    assert not (tmp_path/"experiments/E-invalid/simulation").exists()
    assert lab.inspect_experiment("E-invalid")==result


def test_compliant_full_rebound_velocity_error_is_not_hidden_by_correct_last_sample(tmp_path):
    s=small_compliant_settings()
    def change(i,t,glob,ch):
        if i==190:
            ch[1][1]+=.01;ch[1][5]+=.01
            ch[1][13]+=.01
            glob[4]+=1.001*.01
            glob[1]=.5*1.001*(glob[4]/1.001)**2;glob[8]=glob[1]+glob[0]
    native_fixture(tmp_path,s,change=change)
    parsed=parse_history(tmp_path,s)
    from plugins.explicit_dynamics.reference import assess
    result=assess(s,parsed["rows"])
    assert {"compliant_full_raw_velocity","compliant_full_centered_velocity"} <= {check["code"] for check in result["checks"] if check["status"]=="FAIL"}
    assert parsed["rows"][-1]["energy_velocity_m_s"] == pytest.approx(reference(s,.02)["velocity_m_s"])
    assert not any(value["valid"] for value in result["metrics"].values())


def test_compliant_core_exit0_with_corrupt_actual_ie_keeps_artifacts_and_invalid_metrics(tmp_path,monkeypatch):
    s=small_compliant_settings();adapter=OpenRadiossAdapter()
    monkeypatch.setattr(transport,"runtime",lambda:(tmp_path,{}, {"test_only":True}))
    def fake_process(command,output,name,env):
        if name=="starter":(output/"drop_0000.out").write_text(starter_text(s))
        elif name=="engine":
            (output/"drop_0001.out").write_text(engine_text(s))
            def corrupt(i,t,glob,ch):
                if i==100:ch[4][8]+=.02
            (output/"dropT01").write_text(typed_stream(s,change=corrupt))
        return "NORMAL TERMINATION TEST ONLY"
    monkeypatch.setattr(transport,"process",fake_process)
    lab=Lab(tmp_path/"store",adapters={},analysis_adapters={},doe_adapters={},optimization_adapters={},pde_adapters={},model_analysis_adapters={adapter.backend:adapter})
    lab.create_study("S-compliant","TEST ONLY corruption","Can analytical IE replace a corrupt actual channel?","No","No solver")
    result=lab.run_model_analysis(study_id="S-compliant",experiment_id="E-corrupt",backend=adapter.backend,settings=s)
    assert result["status"]=="REJECTED" and result["solver_status"]=="COMPLETED"
    assert not any(value["valid"] for value in result["metrics"].values())
    assert result["model_revision"]==canonical_hash({"settings":s,"declaration":adapter.describe_model(s)})
    assert result["cad_revision"] is None and "parent_experiment_id" not in result
    assert result["decision"]=="NOT_RELEASED" and "rotational_surface_contact" in lab.research_summary("E-corrupt")["unknown"]
    assert {"simulation/dropT01","simulation/domain_reference.py"} <= {artifact["path"] for artifact in result["artifacts"]}
    assert any(v["type"]=="native_history_integrity" and v["status"]=="FAIL" for v in result["validations"])
    assert lab.inspect_experiment("E-corrupt")==result


def test_compliant_script_retains_aggregate_failed_admission_and_invalid_input_without_invented_unknowns(tmp_path,monkeypatch):
    from scripts import verify_compliant_drop as benchmark
    monkeypatch.setattr(benchmark,"runtime",lambda:None)
    monkeypatch.setattr(benchmark,"source_identity",lambda path:{"core_dirty":False,"test_only":True})
    monkeypatch.setattr(transport,"runtime",lambda:(tmp_path,{}, {"test_only":True}))
    def fake_process(command,output,name,env):
        if name=="starter":
            (output/"drop_0000.out").write_text(starter_text(compliant_specification()).replace("0 WARNING(S)","1 WARNING(S)"))
        if name=="engine":pytest.fail("Engine cannot run after a Starter warning")
        return "TEST ONLY version"
    monkeypatch.setattr(transport,"process",fake_process)
    store=tmp_path/"store";report=benchmark.run(store)
    assert report["status"]=="REJECTED" and report["invalid_input_admission"]=="PASS"
    assert len(report["experiments"])==5 and load_json(store/"acceptance.json")==report
    assert all(entry["history"] is None for entry in report["native"].values())
    for name in ["E-invalid-mass","E-invalid-stiffness"]:
        assert not (store/"experiments"/name/"simulation").exists()
    with pytest.raises(ValueError,match="fresh store"):benchmark.run(store)


def selected_settings(compliant=False):
    from plugins.explicit_dynamics.reference import selected_history_settings
    s = selected_history_settings("rigid_cube_compliant_stop" if compliant else "rigid_cube_freefall")
    s.update(end_time_s=.02, initial_velocity_m_s=.5)
    s["acceleration_history"] = {"time_s": [0, .01, .02], "acceleration_z_m_s2": [-10, 20, -5]}
    s["input_provenance"] = {"origin": "SYNTHETIC", "reference": "TEST ONLY transport/coverage samples, not a native trajectory"}
    return s


def selected_observation(s):
    """TEST ONLY native-shaped channel data; no physical trajectory inference."""
    def observe(index, time):
        compliant = s["case"] == "rigid_cube_compliant_stop"
        moving = s["mass_kg"] + (s["spring_mass_kg"] / 2 if compliant else 0)
        z = s["center_height_m"] + s["initial_velocity_m_s"] * time
        if compliant and (50 <= index <= 70 or 120 <= index <= 140):
            z = s["edge_m"] / 2 - .001
        force = s.get("spring_stiffness_n_m", 0) * max(0, s["edge_m"] / 2 - z)
        work = -.0001 if compliant and index > 70 else 0
        return {"z_m": z, "velocity_m_s": s["initial_velocity_m_s"], "acceleration_m_s2": 0,
            "kinetic_energy_j": .5 * moving * s["initial_velocity_m_s"] ** 2, "ground_impulse_n_s": 0,
            "spring_internal_energy_j": work, "spring_force_n": force,
            "spring_length_change_m": z - s["center_height_m"], "moving_mass_kg": moving,
            "total_mass_kg": s["mass_kg"] + s.get("spring_mass_kg", 0)}
    return observe


@pytest.mark.parametrize("compliant", [False, True])
def test_selected_deck_is_exact_signed_piecewise_linear_body_load_and_original_topology(compliant):
    s = selected_settings(compliant); before = deepcopy(s); starter, engine = decks(s)
    curve = starter.split("/FUNCT/1\nDECLARED_GLOBAL_Z_BODY_ACCELERATION\n")[1].split("/GRAV/1")[0].splitlines()
    assert [[float(row[:20]), float(row[20:])] for row in curve] == [[0, -10], [.01, 20], [.02, -5]]
    grav = starter.split("/GRAV/1\nGRAVITY_ALL_NODES\n")[1].splitlines()[0]
    assert int(grav[:10]) == 1 and grav[10:20] == "         Z"
    assert [float(grav[start:start+20]) for start in (60, 80)] == [1, 1]
    assert "/RWALL" not in starter and "/BRICK/1" in starter and "/DTIX" in engine
    assert ("/PROP/SPRING/2" in starter) == compliant
    assert s == before and "CONSTANT_GRAVITY" not in starter


@pytest.mark.parametrize("compliant", [False, True])
def test_selected_parser_preserves_full_native_layout_and_signed_work_without_oracle(tmp_path, monkeypatch, compliant):
    from plugins.explicit_dynamics import reference as domain
    s = selected_settings(compliant)
    monkeypatch.setattr(domain, "reference", lambda *a, **k: pytest.fail("Selected parser needs no oracle"))
    native_fixture(tmp_path, s, observation=selected_observation(s))
    parsed = parse_history(tmp_path, s)
    assert len(parsed["rows"]) == len(parsed["raw_samples"]) == 201
    assert parsed["global_variable_ids"] == list(range(1, 23))
    assert parsed["rows"][-1]["time_s"] == pytest.approx(.02)
    assert parsed["rows"][-1]["velocity_time_s"] == pytest.approx(.01995)
    assert "time-dependent" in parsed["external_work_policy"]
    assert "no gravitational potential" in parsed["external_work_policy"]
    result = domain.assess(s, parsed["rows"])
    assert result["reference"] is None and all(item["status"] == "PASS" for item in result["checks"])
    if compliant:
        assert parsed["rows"][-1]["spring_internal_energy_j"] == -.0001
        assert min(row["spring_axial_force_n"] for row in parsed["rows"]) == pytest.approx(-10)


@pytest.mark.parametrize("damage", ["interior", "tail", "nan", "metadata", "mass"])
def test_selected_typed_parser_refuses_corruption_and_mass_classification_is_not_exit_success(tmp_path, damage):
    from plugins.explicit_dynamics import reference as domain
    s = selected_settings()
    def change(index, time, glob, channels):
        if index == 20:
            if damage == "nan": glob[8] = float("nan")
            elif damage == "mass": glob[5] = 1.01
    native_fixture(tmp_path, s, observation=selected_observation(s), change=change,
        skip=50 if damage == "interior" else 200 if damage == "tail" else None)
    if damage == "metadata":
        path = tmp_path / "dropT01"
        path.write_text(path.read_text().replace("3 6 9 18", "3 6 9 17"))
    if damage == "mass":
        # Coordinated mass/clock inconsistency may be refused by the parser;
        # either result must never become valid numerical evidence.
        with pytest.raises(ValueError): parse_history(tmp_path, s)
    else:
        with pytest.raises(ValueError): parse_history(tmp_path, s)


def test_selected_native_schedule_missing_binary64_terminal_remains_unavailable(tmp_path):
    from plugins.explicit_dynamics import reference as domain
    s = selected_settings(); s.update(end_time_s=.002)
    s["acceleration_history"] = {"time_s": [0, .002], "acceleration_z_m_s2": [0, 0]}
    native_fixture(tmp_path, s, observation=selected_observation(s))
    parsed = parse_history(tmp_path, s)
    assert parsed["rows"][-1]["time_s"] < .002 - s["time_step_s"] / 2
    with pytest.raises(ValueError, match="complete declared interval"):
        domain.assess(s, parsed["rows"])


def test_selected_unrecordable_terminal_is_refused_before_native_work(tmp_path, monkeypatch):
    s = selected_settings(); s.update(end_time_s=.04, history_interval_s=.001)
    s["acceleration_history"] = {"time_s": [0, .04], "acceleration_z_m_s2": [0, 0]}
    monkeypatch.setattr(transport, "runtime", lambda: pytest.fail("Preflight cannot probe runtime"))
    monkeypatch.setattr(transport, "run_owned_command", lambda *a, **k: pytest.fail("Preflight cannot start native"))
    with pytest.raises(ValueError, match="HIST2 schedule"):
        OpenRadiossAdapter().describe_model(s)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("returncode", [0, 7])
def test_selected_owned_process_has_no_hidden_budget_preserves_parser_bytes_and_receipts(tmp_path, monkeypatch, returncode):
    payload = b"TEST ONLY original stdout bytes\x00\xff"
    def owned(command, cwd, label, *, timeout, env):
        assert command == ["TEST_ONLY_EXECUTABLE"] and timeout is None and env == {"TEST_ONLY": "private"}
        (cwd / f"{label}.stdout.log").write_bytes(payload)
        (cwd / f"{label}.stderr.log").write_bytes(b"TEST ONLY stderr")
        (cwd / f"{label}.execution.json").write_text('{"status":"TEST_ONLY"}')
        return subprocess.CompletedProcess(command, returncode, "TEST ONLY stdout", "TEST ONLY stderr")
    monkeypatch.setattr(transport, "run_owned_command", owned)
    monkeypatch.setattr(transport, "_budget", lambda: pytest.fail("Selected must not set CPU/address cap"))
    monkeypatch.setattr(transport.subprocess, "run", lambda *a, **k: pytest.fail("Selected must use owned live runner"))
    if returncode:
        with pytest.raises(RuntimeError, match="exited 7"):
            transport.selected_process(["TEST_ONLY_EXECUTABLE"], tmp_path, "engine", {"TEST_ONLY": "private"})
    else:
        assert transport.selected_process(["TEST_ONLY_EXECUTABLE"], tmp_path, "engine", {"TEST_ONLY": "private"}) == "TEST ONLY stdout"
    assert (tmp_path / "engine_stdout.log").read_bytes() == payload
    assert (tmp_path / "engine_stderr.log").read_bytes() == b"TEST ONLY stderr"
    command = load_json(tmp_path / "engine_command.json")
    assert command["cpu_seconds"] is None and command["address_space_bytes"] is None and command["timeout_seconds"] is None
    assert "env" not in command and "private" not in (tmp_path / "engine_command.json").read_text()
    assert (tmp_path / "engine.execution.json").is_file()


def test_selected_cancel_preserves_partial_owned_logs_and_propagates_to_common_core(tmp_path, monkeypatch):
    from caelab.execution_control import ExecutionCancelled
    from caelab import declared_model
    monkeypatch.setattr(transport, "runtime", lambda: (tmp_path, {"TEST_ONLY": "yes"}, {"test_only": True}))
    monkeypatch.setattr(declared_model, "source_identity", lambda root: {"core_commit": "0" * 40, "test_only": True})
    def owned(command, cwd, label, **kwargs):
        assert kwargs == {"env": {"TEST_ONLY": "yes"}, "timeout": None}
        (cwd / f"{label}.stdout.log").write_bytes(b"TEST ONLY interrupted")
        (cwd / f"{label}.stderr.log").write_bytes(b"")
        (cwd / f"{label}.execution.json").write_text('{"status":"CANCELLED","pid":null}')
        raise ExecutionCancelled("TEST ONLY cancellation")
    monkeypatch.setattr(transport, "run_owned_command", owned)
    adapter = OpenRadiossAdapter()
    lab = Lab(tmp_path / "store", adapters={}, analysis_adapters={}, doe_adapters={}, optimization_adapters={},
              pde_adapters={}, model_analysis_adapters={adapter.backend: adapter})
    lab.create_study("S-selected", "TEST ONLY", "Cancellation", "Retained", "No native run")
    result = lab.run_model_analysis(study_id="S-selected", experiment_id="E-cancel", backend=adapter.backend,
                                    settings=selected_settings())
    assert result["status"] == "CANCELLED" and result["solver_status"] == "CANCELLED"
    assert result["decision"] == "NOT_RELEASED" and not any(item["valid"] for item in result["metrics"].values())
    folder = lab.store / "experiments/E-cancel/simulation"
    assert (folder / "starter_version_stdout.log").read_bytes() == b"TEST ONLY interrupted"
    assert (folder / "starter_version.execution.json").is_file()
    assert not (folder / "analytical_reference.json").exists()


@pytest.mark.parametrize("compliant", [False, True])
def test_selected_full_mock_native_route_preserves_source_scope_and_never_calls_legacy_process(tmp_path, monkeypatch, compliant):
    s = selected_settings(compliant); before = deepcopy(s); calls = []
    monkeypatch.setattr(transport, "runtime", lambda: (tmp_path, {"TEST_ONLY": "yes"}, {"test_only": True}))
    monkeypatch.setattr(transport, "process", lambda *a: pytest.fail("Selected must not enter legacy budgeted process"))
    def owned(command, cwd, label, **kwargs):
        calls.append(label)
        assert kwargs == {"env": {"TEST_ONLY": "yes"}, "timeout": None}
        if label == "starter": (cwd / "drop_0000.out").write_text(starter_text(s))
        if label == "engine": native_fixture(cwd, s, observation=selected_observation(s))
        text = "NORMAL TERMINATION TEST ONLY"
        (cwd / f"{label}.stdout.log").write_text(text)
        (cwd / f"{label}.stderr.log").write_text("")
        (cwd / f"{label}.execution.json").write_text('{"status":"TEST_ONLY"}')
        return subprocess.CompletedProcess(command, 0, text, "")
    monkeypatch.setattr(transport, "run_owned_command", owned)
    result = OpenRadiossAdapter().solve(tmp_path / "simulation", s)
    assert calls == ["starter_version", "engine_version", "starter", "engine"]
    assert result["status"] == "COMPLETED" and result["solver_status"] == "COMPLETED"
    assert result["mode"] == result["provenance"]["mode"] == "selected_history"
    assert result["input_provenance"] == result["provenance"]["input_provenance"] == s["input_provenance"]
    assert result["assessment"]["reference"] is None
    assert not result["metrics"]["mechanical_energy_error"]["valid"]
    assert {"reference_agreement", "time_step_sensitivity", "physical_validation"} <= set(result["pending_validations"])
    assert not (tmp_path / "simulation/analytical_reference.json").exists()
    assert load_json(tmp_path / "simulation/input.json") == s and s == before
    assert result["provenance"]["resource_limits"]["cpu_seconds"] is None


def test_declared_input_runtime_inspection_starts_no_native_and_pins_execution_control(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from caelab.model_parameters import describe
    adapter = OpenRadiossAdapter()
    monkeypatch.setattr(transport, "runtime", lambda: (tmp_path, {}, {"release": "TEST_ONLY_PINNED_IDENTITY"}))
    monkeypatch.setattr(transport, "process", lambda *a: pytest.fail("Discovery cannot execute native commands"))
    monkeypatch.setattr(transport, "run_owned_command", lambda *a, **k: pytest.fail("Discovery cannot execute native commands"))
    lab = SimpleNamespace(model_analysis_adapters={adapter.backend: adapter}, adapters={})
    description = describe(lab, adapter.backend, selected_settings(True))
    assert [item.native["path"] for item in description["candidates"]] == [
        "initial_velocity_m_s", "acceleration_z_0", "acceleration_z_1", "acceleration_z_2", "spring_stiffness_n_m"]
    assert "caelab/execution_control.py" in description["fingerprint"]["source_files"]
    assert description["fingerprint"]["runtime"] == {"release": "TEST_ONLY_PINNED_IDENTITY"}
