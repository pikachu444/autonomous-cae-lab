"""Pinned native OpenRadioss SMP transport for bounded SI rigid-cube cases."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess

from plugins.explicit_dynamics import reference as domain
from ..storage import save_json


RELEASE = "latest-20260728"
SOURCE_COMMIT = "a62b27e6baa555d222a580d6218867d0be4d70b5"
ARCHIVE_SHA256 = "598ed7b2905a7bacc8d1781470c250ac79d7558c39ba962768edf3644644fe33"
CONFIGURATION_SHA256 = "201fbbf6a17fa97e1a7ce301d215ad4712c0aab7bc88b31d566b46cfb0a89433"
RUNTIME_HASHES = {
    "exec/starter_linux64_gf": "65f1bd91c1b1dcad18234aca7797fa9e2c53a1a2cf1a4b3f5d6be4154c62c8e4",
    "exec/engine_linux64_gf": "7fdedddbcf5753a53d7c8d8872aa6ead3b4e9983237997f6dd3b8cdd8375e3ed",
    "extlib/hm_reader/linux64/libhm_reader_linux64.so": "8df18883dc50bb29295f87c669d7ede95c8bc3de856c402c2daa741f272d1676",
    "extlib/hm_reader/linux64/libapr-1.so.0": "f76d9796e59b675cb374fc3f3403f7878bdcb348e4c6f8af017c3dc3046be89c",
    "extlib/h3d/lib/linux64/libh3dwriter.so": "9975a8faf57853a06237a370cd3b8c76479ebf59fb41edc9ff95b6e1fd8bb675",
}
DOMAIN_PATH = Path(domain.__file__).resolve()
DOMAIN_BYTES = DOMAIN_PATH.read_bytes()
DOMAIN_SHA256 = hashlib.sha256(DOMAIN_BYTES).hexdigest()
ADAPTER_PATH = Path(__file__).resolve()
ADAPTER_BYTES = ADAPTER_PATH.read_bytes()
ADAPTER_SHA256 = hashlib.sha256(ADAPTER_BYTES).hexdigest()
PROCESS_TIMEOUT = 90


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _int(*values):
    return "".join(f"{value:10d}" for value in values)


def _real(*values):
    return "".join(f"{value:20.12g}" for value in values)


def decks(settings):
    """Only trusted card templates are accepted; settings are domain-validated."""
    s = domain.validate_settings(settings)
    compliant = s["case"] == domain.COMPLIANT_CASE
    half, height = s["edge_m"] / 2, s["center_height_m"]
    corners = [(-half, -half, -half), (half, -half, -half), (half, half, -half), (-half, half, -half),
               (-half, -half, half), (half, -half, half), (half, half, half), (-half, half, half)]
    nodes = [_int(i) + _real(x, y, height + z) for i, (x, y, z) in enumerate(corners, 1)]
    nodes.append(_int(9) + _real(0, 0, height))
    if compliant:
        nodes.append(_int(10) + _real(0, 0, domain.ANCHOR_Z_M))
        nodes.append(_int(11) + _real(0, 0, height))
    rigid_nodes = [*range(1, 9), *([11] if compliant else [])]
    moving_nodes = [*range(1, 10), *([11] if compliant else [])]
    starter = ["#RADIOSS STARTER", "/BEGIN", "drop", _int(2022, 0),
               "                  kg                   m                   s",
               "                  kg                   m                   s",
               "/MAT/LAW1/1", "RIGID_MASS_CARRIER_NOT_QUALIFIED", _real(s["mass_kg"] / s["edge_m"] ** 3),
               _real(1e5, .3), "/PROP/SOLID/1", "RIGID_MASS_CARRIER", _int(1, 4, 0, 0, 0, 0, 0, 0) + _real(0),
               _real(0, 0, 0, 0, 0), _real(0, 0, 0, 0, 0), _int(0, 0, 0, 0),
               "/PART/1", "RIGID_CUBE", _int(1, 1, 0), "/NODE", *nodes, "/BRICK/1", _int(1, 1, 2, 3, 4, 5, 6, 7, 8),
               "/GRNOD/NODE/1", "CUBE_CORNERS", _int(*rigid_nodes),
               "/GRNOD/NODE/2", "ALL_CUBE_NODES", _int(*moving_nodes),
               "/RBODY/1", "RIGID_CENTER9", _int(9, 0, 0, 2) + _real(0) + _int(1, 0, 3, 0),
               _real(0, 0, 0), _real(0, 0, 0), _int(0, 0, 0),
               "/FUNCT/1", "CONSTANT_GRAVITY", _real(0, -s["gravity_m_s2"]),
               _real(s["end_time_s"] + s["time_step_s"], -s["gravity_m_s2"]),
               "/GRAV/1", "GRAVITY_ALL_NODES", _int(1) + "         Z" + _int(0, 0, 2) + " " * 10 + _real(1, 1),
               "/INIVEL/TRA/1", "DECLARED_INITIAL_VELOCITY", _real(0, 0, s["initial_velocity_m_s"]) + _int(2, 0)]
    if compliant:
        # Official TYPE4 H1=8 uses absolute length, A1=Ascale1=1. K1 is
        # the initial stiffness, not a multiplier for the curve force ordinate.
        k, rest = s["spring_stiffness_n_m"], half - domain.ANCHOR_Z_M
        starter.extend(["/GRNOD/NODE/3", "FIXED_ANCHOR10", _int(10),
                        "/BCS/1", "ANCHOR_TRANSLATIONS_FIXED", "   111 000" + _int(0, 3),
                        "/PROP/SPRING/2", "STOP_SPRING_PROPERTY",
                        _real(s["spring_mass_kg"]) + " " * 30 + _int(0, 0, 0),
                        _real(k, 0, 1, 0, 1), _int(2, 8, 0, 0, 0) + " " * 10 + _real(-1e30, 1e30),
                        _real(1, 0, 1, 1), "/FUNCT/2", "FORCE_N_VS_ABSOLUTE_LENGTH_M",
                        _real(0, -k * rest), _real(rest, 0), _real(3, 0),
                        "/PART/2", "STOP_SPRING", _int(2, 0), "/SPRING/2",
                        _int(2, 10, 11, 0, 0, 0, 0) + " " * 20 + _int(0)])
    if s["case"] == "rigid_cube_ground_stop":
        # Official FAQ: put the RBODY main node in RWALL; secondary constraints
        # conflict. For this nonrotating cube, center>=edge/2 iff bottom>=0.
        starter.extend(["/GRNOD/NODE/3", "BODY_MAIN_CONTACT", _int(9),
                        "/RWALL/PLANE/1", "GROUND_EFFECTIVE_CENTER_PLANE", _int(0, 0, 3, 0),
                        _real(0, 0, 0, 0) + _int(0), _real(0, 0, half), _real(0, 0, half + 1)])
    starter.extend(["/TH/NODE/1", "NODAL_KINEMATICS", "".join(f"{v:>10}" for v in ("Z", "DZ", "VZ", "AZ")),
                    _int(9, 0) + "CENTER9", _int(1, 0) + "BOTTOM1"])
    if compliant:
        starter.append(_int(10, 0) + "FIXED_ANCHOR10")
        starter.append(_int(11, 0) + "CENTER_ATTACHMENT11")
    starter.extend(["/TH/RBODY/2", "BODY_IMPULSES_ROTATIONS",
                    "".join(f"{v:>10}" for v in ("FZ", "RX", "RY", "RZ")), _int(1)])
    if s["case"] == "rigid_cube_ground_stop":
        starter.extend(["/TH/RWALL/3", "WALL_NORMAL_IMPULSE", f"{'FNZ':>10}", _int(1)])
    if compliant:
        starter.extend(["/TH/SPRING/4", "STOP_CONSTITUTIVE_HISTORY",
                        "".join(f"{v:>10}" for v in ("OFF", "FX", "FY", "FZ", "MX", "MY", "MZ", "LX", "IE")), _int(2)])
    starter.append("/END")
    engine = ["/RUN/drop/1", _real(s["end_time_s"]), "/VERS/100", "/DT", _real(.9, 0),
              "/DTIX", _real(s["time_step_s"], s["time_step_s"]), "/TFILE/3", _real(s["history_interval_s"]),
              "/TH/TITLE", "/ANIM/DT", _real(0, max(.01, s["end_time_s"] / 40)),
              "/ANIM/VECT/VEL", "/ANIM/VECT/DISP", "/PRINT/1"]
    return "\n".join(starter) + "\n", "\n".join(engine) + "\n"


def runtime():
    value = os.environ.get("CAELAB_OPENRADIOSS_ROOT")
    if not value:
        raise RuntimeError("Set CAELAB_OPENRADIOSS_ROOT to the isolated pinned official runtime")
    root = Path(value).resolve()
    archive = root.parent / "OpenRadioss_linux64.zip"
    if sha256(archive) != ARCHIVE_SHA256:
        raise RuntimeError("Preserved official OpenRadioss archive does not match its published SHA256")
    hashes = {name: sha256(root / name) for name in RUNTIME_HASHES}
    if hashes != RUNTIME_HASHES:
        raise RuntimeError("OpenRadioss executable/library bytes do not match the pinned official release")
    configuration = hashlib.sha256()
    for path in sorted(p for p in (root / "hm_cfg_files").rglob("*") if p.is_file()):
        configuration.update(path.relative_to(root).as_posix().encode())
        configuration.update(hashlib.sha256(path.read_bytes()).digest())
    if not (root / "hm_cfg_files").is_dir():
        raise RuntimeError("Pinned native reader configurations are required")
    if configuration.hexdigest() != CONFIGURATION_SHA256:
        raise RuntimeError("Native reader configurations differ from the pinned official archive")
    env = dict(os.environ)
    # Each native child receives isolated library/configuration paths; no shell activation.
    env.update(OPENRADIOSS_PATH=str(root), RAD_CFG_PATH=str(root / "hm_cfg_files"),
               RAD_H3D_PATH=str(root / "extlib/h3d/lib/linux64"), OMP_NUM_THREADS="2", OMP_STACKSIZE="64m",
               LD_LIBRARY_PATH=os.pathsep.join(str(root / p) for p in ("extlib/hm_reader/linux64", "extlib/h3d/lib/linux64")),
               LC_ALL="C", LANG="C")
    return root, env, {"release": RELEASE, "release_source_commit": SOURCE_COMMIT,
                       "archive_sha256": ARCHIVE_SHA256, "critical_file_sha256": hashes,
                       "configuration_sha256": configuration.hexdigest(), "license": "AGPL-3.0; bundled library terms also require deployment review"}


def _budget():
    if os.name == "posix":
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (2 * 1024 ** 3, 2 * 1024 ** 3))
        resource.setrlimit(resource.RLIMIT_CPU, (60, 60))


def process(command, output, name, env):
    save_json(output / (name + "_command.json"), {"argv": command, "cwd": str(output), "threads": 2,
        "address_space_bytes": 2 * 1024 ** 3, "cpu_seconds": 60, "timeout_seconds": PROCESS_TIMEOUT})
    try:
        run = subprocess.run(command, cwd=output, env=env, capture_output=True, text=True,
                             timeout=PROCESS_TIMEOUT, preexec_fn=_budget if os.name == "posix" else None)
    except subprocess.TimeoutExpired as exc:
        for stream in ("stdout", "stderr"):
            value = getattr(exc, stream) or b""
            (output / f"{name}_{stream}.log").write_bytes(value if isinstance(value, bytes) else value.encode())
        raise RuntimeError(f"OpenRadioss {name} exceeded the bounded timeout; partial evidence retained") from exc
    (output / (name + "_stdout.log")).write_text(run.stdout, encoding="utf-8")
    (output / (name + "_stderr.log")).write_text(run.stderr, encoding="utf-8")
    if run.returncode:
        raise RuntimeError(f"OpenRadioss {name} exited {run.returncode}: {(run.stderr or run.stdout)[-1500:]}")
    return run.stdout


class OpenRadiossAdapter:
    backend = "explicit.openradioss"
    version = "1.1"
    domain = "explicit_dynamics"
    physics_domain = "structural"
    analysis_type = "explicit_drop"
    default_metrics = ["final_displacement", "final_velocity", "final_kinetic_energy", "ground_impulse"]

    def describe_model(self, settings):
        return domain.model_declaration(settings)

    def solve(self, output, settings):
        from .openradioss_worker import parse_history, starter_admission, SOURCE_PATH, SOURCE_BYTES, SOURCE_SHA256
        s = domain.validate_settings(settings)
        if sha256(DOMAIN_PATH) != DOMAIN_SHA256 or sha256(ADAPTER_PATH) != ADAPTER_SHA256 or sha256(SOURCE_PATH) != SOURCE_SHA256:
            raise RuntimeError("Loaded implementation differs from current source bytes; restart with frozen source")
        output = Path(output)
        output.mkdir(parents=True, exist_ok=False)
        root, env, identity = runtime()
        save_json(output / "input.json", s)
        save_json(output / "model_declaration.json", self.describe_model(s))
        save_json(output / "analytical_reference.json", domain.reference(s, s["end_time_s"]))
        (output / "domain_reference.py").write_bytes(DOMAIN_BYTES)
        (output / "adapter_source.py").write_bytes(ADAPTER_BYTES)
        (output / "parser_source.py").write_bytes(SOURCE_BYTES)
        source_paths = {"adapter": ADAPTER_PATH, "parser": SOURCE_PATH}
        source_hashes = {"adapter": ADAPTER_SHA256, "parser": SOURCE_SHA256}
        starter, engine = decks(s)
        (output / "drop_0000.rad").write_text(starter, encoding="ascii")
        (output / "drop_0001.rad").write_text(engine, encoding="ascii")
        versions = {}
        for label in ("starter", "engine"):
            executable = root / f"exec/{label}_linux64_gf"
            versions[label] = process([str(executable), "-version"], output, label + "_version", env).strip()
        identity.update(versions=versions, domain_source_sha256=DOMAIN_SHA256,
                        implementation_sha256=source_hashes,
                        resource_limits={"omp_threads": 2, "address_space_bytes": 2 * 1024 ** 3, "cpu_seconds": 60})
        process([str(root / "exec/starter_linux64_gf"), "-i", "drop_0000.rad", "-np", "1", "-nt", "2"], output, "starter", env)
        try:
            admission = starter_admission(output, s)
            if (output / "drop_0000.rad").read_text(encoding="ascii") != starter or (output / "drop_0001.rad").read_text(encoding="ascii") != engine:
                raise ValueError("Trusted native deck bytes changed during Starter execution")
        except (ValueError, OSError) as exc:
            outcome = {"status": "REJECTED", "solver_status": "NOT_RUN", "converged": None,
                       "checks": [{"code": "native_starter_admission", "status": "FAIL", "observed": str(exc)}],
                       "metrics": domain.invalid_metrics(str(exc), compliant=s["case"] == domain.COMPLIANT_CASE), "pending_validations": list(domain.PENDING),
                       "provenance": {**identity, "starter_status": "COMPLETED", "engine_status": "NOT_RUN"},
                       "raw_result": "simulation/analysis_raw.json"}
            save_json(output / "analysis_raw.json", outcome)
            return outcome
        save_json(output / "starter_admission.json", admission)
        engine_log = process([str(root / "exec/engine_linux64_gf"), "-i", "drop_0001.rad", "-nt", "2"], output, "engine", env)
        if "NORMAL TERMINATION" not in engine_log:
            raise RuntimeError("Engine exit did not establish normal native termination")
        original_identity = {key: identity[key] for key in runtime()[2]}
        if (sha256(DOMAIN_PATH) != DOMAIN_SHA256 or runtime()[2] != original_identity
                or any(sha256(path) != source_hashes[name] for name, path in source_paths.items())
                or (output / "drop_0000.rad").read_text(encoding="ascii") != starter
                or (output / "drop_0001.rad").read_text(encoding="ascii") != engine):
            raise RuntimeError("Domain/runtime source changed during execution; evidence retained")
        try:
            native = parse_history(output, s)
            save_json(output / "parsed_history.json", native)
            assessment = domain.assess(s, native["rows"])
        except (ValueError, OSError) as exc:
            assessment = {"checks": [{"code": "native_history_integrity", "status": "FAIL", "observed": str(exc)}],
                          "metrics": domain.invalid_metrics(str(exc), compliant=s["case"] == domain.COMPLIANT_CASE), "pending_validations": domain.PENDING,
                          "limitations": ["Native history failed completeness/consistency; no response is usable"]}
        checks = assessment["checks"]
        outcome = {"status": "COMPLETED" if all(item["status"] == "PASS" for item in checks) else "REJECTED",
                   "solver_status": "COMPLETED", "converged": True, "checks": checks,
                   "metrics": assessment["metrics"], "pending_validations": assessment["pending_validations"],
                   "provenance": identity, "raw_result": "simulation/analysis_raw.json",
                   "assessment": assessment}
        save_json(output / "analysis_raw.json", outcome)
        return outcome
