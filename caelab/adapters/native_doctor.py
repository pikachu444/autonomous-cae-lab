"""Selected local native-runtime diagnostics; discovery never implies a solve."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


def service_platform():
    """The service host, never the desktop client or a submitted setting."""
    return sys.platform


def execution_environment(backend, *, host):
    """Cheap platform declaration only; no import, process, install or solve."""
    key=backend if isinstance(backend,str) else ""
    native=(key.startswith("pde.fenicsx") or key.startswith("material.mfront") or
            key in {"thermal.fenicsx.rectangle","structural.fenicsx.thermoelastic_rectangle"})
    local={"pde.scipy.ode":"SciPy","material.felupe":"FELUPE"}.get(key)
    known=isinstance(host,str) and bool(host)
    blocked=bool(native and known and not host.startswith("linux"))
    runtime="MFront/MGIS" if key.startswith("material.mfront") else "FEniCSx" if native else local
    return {"service_platform":host,"runtime":runtime,"requires_linux":native,
            "blocked":blocked,"installation":"NOT_CHECKED","execution":"NOT_REQUESTED",
            "label":("이 계산은 Linux 서비스 필요" if blocked else
                     "Linux 계산 ("+runtime+")" if native and known else
                     "계산 환경 확인 필요" if native else
                     ("Windows" if host=="win32" else "현재 서비스")+" 계산 ("+local+")" if local else ""),
            "message":("현재 서비스에서는 "+runtime+" 계산을 지원하지 않습니다. 편집·저장·보존 결과 읽기는 가능합니다. "
                       "계산하려면 해당 도구가 설치된 Linux 서비스에 명시적으로 연결하세요. 자동 전환은 하지 않습니다."
                       if blocked else
                       runtime+" 설치와 실행 환경은 계산 전에 별도 확인해야 합니다." if runtime else "")}


def require_execution_platform(backend):
    state=execution_environment(backend,host=service_platform())
    if state["blocked"]:raise RuntimeError(state["message"])
    return state


def _command(argv, *, environment=None):
    result = subprocess.run(argv, capture_output=True, text=True, check=False,
                            timeout=30, env=environment)
    if result.returncode:
        raise RuntimeError(f"Version/dependency command exited {result.returncode}: {(result.stderr or result.stdout)[-400:]}")
    return (result.stdout or result.stderr).strip()


def _discover(backend):
    if backend in {"pde.scipy.ode","material.felupe"}:
        from importlib.util import find_spec
        from importlib.metadata import version, PackageNotFoundError
        dependency="scipy" if backend=="pde.scipy.ode" else "felupe"
        if find_spec(dependency) is None:raise RuntimeError(dependency+" 설치가 필요합니다.")
        try:installed_version=version(dependency)
        except PackageNotFoundError as error:raise RuntimeError(dependency+" 설치 정보를 확인하지 못했습니다.") from error
        return {"python":sys.executable,"versions":{dependency:installed_version},
                "kind":"service_python","calculation":"NOT_EXECUTED"}
    if backend.startswith("pde.fenicsx"):
        python = os.environ.get("CAELAB_FENICSX_PYTHON", "/usr/bin/python3")
        version = _command([python, "-c", "import dolfinx, petsc4py, ufl; "
                            "print('dolfinx=' + dolfinx.__version__ + ', petsc4py=' + petsc4py.__version__ + ', ufl=' + ufl.__version__)"])
        return {"python": python, "versions": version, "kind": "isolated_system_python"}
    if backend == "explicit.openradioss":
        from .openradioss import runtime
        root, env, identity = runtime()
        return {"root": str(root), "release": identity["release"], "archive_sha256": identity["archive_sha256"],
                "versions": {name: _command([str(root / f"exec/{name}_linux64_gf"), "-version"], environment=env)
                             for name in ("starter", "engine")}}
    if backend.startswith("structural.code_aster") or backend == "structural.families.code_aster":
        from .codeaster_elasticity import _image_identity
        image, digest, runtime, gmsh, prlimit = _image_identity(Path.cwd())
        return {"image": str(image), "image_sha256": digest, "gmsh": gmsh, "prlimit": prlimit,
                "versions": {"singularity": _command([runtime, "--version"]), "gmsh": _command([gmsh, "-version"])}}
    if backend.startswith("material.mfront"):
        from .mfront_material import _runtime_identity
        image, digest, runtime = _runtime_identity()
        return {"image": str(image), "image_sha256": digest,
                "versions": {"singularity": _command([runtime, "--version"])},
                "native_law_loading": "NOT_TESTED; use --execute for an actual MGIS/MTest update"}
    return None


def _smoke_settings(backend):
    if backend == "pde.fenicsx.transient":
        from plugins.pde_transient.reference import manufactured_settings
        return manufactured_settings()
    if backend == "pde.fenicsx.vector":
        from plugins.pde_vector.reference import manufactured_settings
        settings = manufactured_settings()
        settings["mesh"]["cell_counts"] = [16, 32, 64]
        return settings
    if backend == "explicit.openradioss":
        return {"case": "rigid_cube_freefall", "edge_m": .1, "mass_kg": 1., "center_height_m": 1.,
                "gravity_m_s2": 9.81, "initial_velocity_m_s": 0., "end_time_s": .2,
                "time_step_s": 1e-4, "history_interval_s": 1e-3,
                "limits": {"displacement_abs_m": 2e-4, "velocity_abs_m_s": .002,
                           "energy_abs_j": .01, "mass_relative": 1e-8,
                           "impact_time_abs_s": 2e-4, "impulse_abs_n_s": .005,
                           "penetration_abs_m": .001}}
    if backend == "structural.code_aster":
        return {"case": "uniaxial_block", "dimensions_mm": [20., 4., 2.],
                "material": {"youngs_modulus_mpa": 210000., "poisson_ratio": .3},
                "traction_mpa": 10., "mesh_sizes_mm": [2., 1.],
                "limits": {"displacement_relative": 1e-8, "displacement_absolute_mm": 1e-12,
                           "stress_relative": 1e-8, "reaction_relative": 1e-8,
                           "mesh_agreement_relative": 1e-8}}
    if backend == "structural.families.code_aster":
        from plugins.structural_families.reference import specification
        return specification("ansys_vmd1_regular", "Fx")
    if backend == "material.mfront":
        from plugins.material_point.reference import FIXED_LIMITS
        return {"case": "isotropic_small_strain", "material": {"youngs_modulus_mpa": 200., "poisson_ratio": .25},
                "temperature_k": 293.15, "history": [{"time_s": 0., "strain": [0.] * 6},
                                                {"time_s": 1., "strain": [.001, 0., 0., 0., 0., 0.]}],
                "limits": dict(FIXED_LIMITS)}
    return None


def doctor_native_backend(backend, *, execute=False, output=None):
    """Return discovery, dependency and requested real-execution states separately."""
    row = {"backend": backend, "discovery": "NOT_SUPPORTED", "dependencies": "NOT_CHECKED",
           "execution": "NOT_REQUESTED"}
    row["environment"]=execution_environment(backend,host=service_platform())
    if row["environment"]["blocked"]:
        row.update(discovery="UNAVAILABLE",dependencies="UNAVAILABLE",reason=row["environment"]["message"])
        return row
    try:
        details = _discover(backend)
        if details is None:
            return row
        row.update(discovery="FOUND", dependencies="READY", details=details)
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
        row.update(discovery="UNAVAILABLE", dependencies="UNAVAILABLE",
                   reason=f"{type(exc).__name__}: {exc}")
        return row
    if not execute:
        return row
    settings = _smoke_settings(backend)
    if settings is None:
        row["execution"] = "UNSUPPORTED_SMOKE_FOR_THIS_BACKEND"
        return row
    if output is None:
        raise ValueError("A new --output directory is required for an actual native doctor solve")
    from ..backends import get_backend
    path = Path(output).resolve()
    if path.exists():
        raise FileExistsError("Native doctor refuses an existing output directory")
    try:
        outcome = get_backend(backend).solve(path, settings)
    except Exception as exc:
        row.update(execution="FAILED_EXECUTION", output=str(path), reason=f"{type(exc).__name__}: {exc}")
        return row
    row.update(execution="COMPLETED" if outcome.get("solver_status") == "COMPLETED" else
               str(outcome.get("solver_status", "UNKNOWN")),
               numerical_status=outcome.get("status"), output=str(path),
               failed_checks=[check for check in outcome.get("checks", []) if check.get("status") == "FAIL"],
               outcome_artifact=outcome.get("raw_result"))
    return row
