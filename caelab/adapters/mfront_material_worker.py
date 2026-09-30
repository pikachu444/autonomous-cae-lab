"""Fixed TFEL5 generic/3D build and MGIS3/MTest native worker.

Only adapter-written bounded JSON reaches this process. No DSL or executable
path is accepted from callers. Importing this module needs no native library.
"""

from copy import deepcopy
import hashlib
import json
import math
import os
import faulthandler
from pathlib import Path
import platform
import shutil
import shlex
import subprocess
import sys

SOURCE_SHA256 = "61714d5b29544090f15e94f083969fb1cc85726ece94806996f151ff49711312"
TFEL_COMMIT = "85554f233306548d8c9c4d36af54b715c608b8c7"
SOURCE_URL = f"https://raw.githubusercontent.com/thelfer/tfel/{TFEL_COMMIT}/mfront/tests/behaviours/Elasticity.mfront"
TFEL_PREFIX = "/opt/spack/opt/spack/linux-zen2/tfel-5.0.0-flantzxx3vcxkf4qlpwnl7midzoe33ma"
MGIS_PREFIX = "/opt/spack/opt/spack/linux-zen2/mgis-3.0-dfpytmkwj5iza5npkbvk5hils7heaxad"
SOURCE_PATH = Path(TFEL_PREFIX) / "share/doc/mfront/tests/behaviours/Elasticity.mfront"
BUILD_ARGUMENTS = ["--omake", "--interface=generic", "--@SelectedModellingHypothesis=Tridimensional", "Elasticity.mfront"]
COMPILER_POLICY = "TFEL_oflags0_portable_O2_no_architecture_specific_flags"
SQRT2 = math.sqrt(2.)
MAX_FILE_BYTES = 128 * 1024 * 1024


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(data)
    return h.hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def state_hash(state):
    return hashlib.sha256(json.dumps(state, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def kelvin(physical):
    return list(physical[:3]) + [SQRT2 * item for item in physical[3:]]


def physical(native):
    return list(native[:3]) + [item / SQRT2 for item in native[3:]]


def _floats(array):
    return [float(item) for item in array.reshape(-1)]


def _state_buffers(behaviour):
    fields = [("gradients", "gradients_kelvin"), ("thermodynamic_forces", "stress_kelvin_mpa")]
    # MGIS3 NumPySupport divides by the number of columns. The zero-ISV
    # getter therefore performs integer division by zero; energy getters
    # explicitly raise when the behavior does not compute those outputs.
    # These are absent buffers, not missing stress/strain observations.
    if behaviour is None or behaviour.internal_state_variables:
        fields.append(("internal_state_variables", "internal_state_variables"))
    if behaviour is None or behaviour.computesStoredEnergy:
        fields.append(("stored_energies", "stored_energies"))
    if behaviour is None or behaviour.computesDissipatedEnergy:
        fields.append(("dissipated_energies", "dissipated_energies"))
    return fields


def snapshot(state, properties, external, dt, behaviour=None):
    arrays = {"internal_state_variables": [], "stored_energies": [], "dissipated_energies": []}
    arrays.update({saved: _floats(getattr(state, native)) for native, saved in _state_buffers(behaviour)})
    return {"gradients_kelvin": _floats(state.gradients),
            "stress_kelvin_mpa": _floats(state.thermodynamic_forces),
            **arrays,
            "material_properties": deepcopy(properties), "external_state_variables": deepcopy(external),
            "dt_s": float(dt)}


def fresh_manager(binding, behaviour, baseline):
    """Allocate independent native buffers and restore the immutable baseline.

    MaterialStateManager exposes property/ESV setters, not property-array getters
    in this MGIS3 build. Their applied scalar dictionaries are retained exactly.
    Both states receive properties/ESVs explicitly; all exposed state buffers are
    copied, including internal variables and energy, without a shallow clone.
    """
    manager = binding.MaterialDataManager(behaviour, 1)
    for state in (manager.s0, manager.s1):
        for name, value in baseline["material_properties"].items():
            binding.setMaterialProperty(state, name, value)
        for name, value in baseline["external_state_variables"].items():
            binding.setExternalStateVariable(state, name, value)
        for native_name, saved_name in _state_buffers(behaviour):
            array = getattr(state, native_name)
            values = baseline[saved_name]
            if array.size != len(values):
                raise ValueError(f"Native {native_name} does not match the complete baseline shape")
            array.reshape(-1)[:] = values
    return manager


def _integrate(binding, manager, dt):
    options = binding.BehaviourIntegrationOptions()
    # MGIS3 exposes these properties read-only; its C++ defaults are the required
    # consistent tangent and no speed of sound. Assert actual runtime defaults
    # instead of pretending this binding supports mutable options.
    if (options.integration_type != binding.IntegrationType.IntegrationWithConsistentTangentOperator or
            options.compute_speed_of_sound is not False):
        raise ValueError("MGIS native options drifted from consistent tangent/no speed-of-sound policy")
    result = binding.integrate(manager, options, dt, 0, 1)
    return {"integration_return": int(result.exit_status),
            "time_step_increase_factor": float(result.time_step_increase_factor),
            "error_message": str(result.error_message), "failure_or_unreliable_point_index": int(result.n)}


def _observation(state):
    gradients, stress = _floats(state.gradients), _floats(state.thermodynamic_forces)
    return {"gradients_kelvin": gradients, "strain_physical": physical(gradients),
            "stress_kelvin_mpa": stress, "stress_physical_mpa": physical(stress)}


def integrate_history(binding, behaviour, settings, library_sha, output):
    properties = {"YoungModulus": settings["material"]["youngs_modulus_mpa"],
                  "PoissonRatio": settings["material"]["poisson_ratio"]}
    external = {"Temperature": settings["temperature_k"]}
    initial = binding.MaterialDataManager(behaviour, 1)
    for state in (initial.s0, initial.s1):
        for key, value in properties.items():
            binding.setMaterialProperty(state, key, value)
        binding.setExternalStateVariable(state, "Temperature", settings["temperature_k"])
        for name, _ in _state_buffers(behaviour):
            getattr(state, name).reshape(-1)[:] = 0.
    baseline = snapshot(initial.s0, properties, external, 0., behaviour)
    result = {"library_sha256": library_sha, "material_properties": properties,
              "external_state_variables": external, "initial_state": deepcopy(baseline),
              "initial": {"time_s": 0., **_observation(initial.s0)}, "steps": []}
    for index, entry in enumerate(settings["history"][1:], 1):
        dt = entry["time_s"] - settings["history"][index - 1]["time_s"]
        baseline = {**deepcopy(baseline), "dt_s": dt}
        nominal = fresh_manager(binding, behaviour, baseline)
        saved_initial = snapshot(nominal.s0, properties, external, dt, behaviour)
        nominal.s1.gradients[0, :] = kelvin(entry["strain"])
        integration = _integrate(binding, nominal, dt)
        record = {"time_s": entry["time_s"], "initial_state": saved_initial,
                  "initial_state_sha256": state_hash(saved_initial), **integration, **_observation(nominal.s1),
                  "tangent_kelvin_mpa": nominal.K.reshape(6, 6).tolist(),
                  "nominal_before_probes": snapshot(nominal.s1, properties, external, dt, behaviour),
                  "finite_differences": []}
        if integration["integration_return"] != 1:
            result["native_rejection"] = {"phase": "nominal", "step": index, **integration}
            result["steps"].append(record)
            save(output / "mgis.partial.json", result)
            return result
        for h in settings["limits"]["finite_difference_steps"]:
            probes, columns = [], []
            for column in range(6):
                signed = {}
                for sign in (-1, 1):
                    probe = fresh_manager(binding, behaviour, baseline)
                    probe_initial = snapshot(probe.s0, properties, external, dt, behaviour)
                    probe.s1.gradients[0, :] = nominal.s1.gradients[0, :]
                    probe.s1.gradients[0, column] += sign * h
                    probe_result = _integrate(binding, probe, dt)
                    item = {"column": column, "sign": sign, "initial_state": probe_initial,
                            "initial_state_sha256": state_hash(probe_initial), **probe_result, **_observation(probe.s1)}
                    probes.append(item)
                    signed[sign] = item["stress_kelvin_mpa"]
                    if probe_result["integration_return"] != 1:
                        result["native_rejection"] = {"phase": "finite_difference", "step": index,
                            "h": h, "column": column, "sign": sign, **probe_result}
                        record["finite_differences"].append({"h": h, "probes": probes})
                        result["steps"].append(record)
                        save(output / "mgis.partial.json", result)
                        return result
                columns.append([(a - b) / (2 * h) for a, b in zip(signed[1], signed[-1])])
            record["finite_differences"].append({"h": h, "probes": probes,
                "tangent_kelvin_mpa": [[columns[j][i] for j in range(6)] for i in range(6)]})
        record["nominal_after_probes"] = snapshot(nominal.s1, properties, external, dt, behaviour)
        record["nominal_initial_after_probes"] = snapshot(nominal.s0, properties, external, dt, behaviour)
        record["initial_state_unchanged"] = saved_initial == record["nominal_initial_after_probes"]
        result["steps"].append(record)
        save(output / "mgis.partial.json", result)
        # Probe buffers are discarded; only this reliable nominal state advances.
        binding.update(nominal)
        baseline = snapshot(nominal.s0, properties, external, dt, behaviour)
    return result


def mtest_history(module, library, settings, output):
    library_sha = sha256(library)
    test = module.MTest()
    test.setModellingHypothesis("Tridimensional")
    test.setBehaviour("generic", str(library), "Elasticity")
    # TFEL5 GenericSolver increments the failed-step counter before comparing
    # it to mSubSteps. A limit of 1 throws on the first failure, before reduction;
    # zero would never match that incremented counter and would permit retries.
    test.setMaximumNumberOfSubSteps(1)
    test.setMaximumNumberOfIterations(10)
    test.setStrainEpsilon(1e-14)
    test.setStressEpsilon(1e-10)
    properties = {"YoungModulus": settings["material"]["youngs_modulus_mpa"],
                  "PoissonRatio": settings["material"]["poisson_ratio"]}
    for key, value in properties.items():
        test.setMaterialProperty(key, value)
    test.setExternalStateVariable("Temperature", settings["temperature_k"])
    strains = [kelvin(entry["strain"]) for entry in settings["history"]]
    for column, name in enumerate(("EXX", "EYY", "EZZ", "EXY", "EXZ", "EYZ")):
        test.setImposedStrain(name, {entry["time_s"]: strain[column] for entry, strain in zip(settings["history"], strains)})
    test.setStrain([0.] * 6)
    test.setStress([0.] * 6)
    test.setOutputFileName(str(output / "mtest.res"))
    test.setOutputFilePrecision(17)
    test.completeInitialisation()
    state, workspace = module.MTestCurrentState(), module.MTestWorkSpace()
    test.initializeCurrentState(state)
    test.initializeWorkSpace(workspace)
    result = {"library_sha256": library_sha, "material_properties": properties,
              "external_state_variables": {"Temperature": settings["temperature_k"]},
              "substep_limit": 1, "strain_epsilon": 1e-14, "stress_epsilon_mpa": 1e-10,
              "states": []}

    def retain(time):
        gradients, forces = list(state.e1), list(state.s1)
        if len(gradients) != 6 or len(forces) != 6:
            raise ValueError("MTest returned incomplete 3D tensor components")
        row = {"time_s": time, "state_phase": "INITIAL_UNPREPARED" if time == 0 else "INTEGRATED",
               "gradients_kelvin": [float(x) for x in gradients],
               "strain_physical": physical(gradients), "stress_kelvin_mpa": [float(x) for x in forces],
               "stress_physical_mpa": physical(forces), "internal_state_variables": [float(x) for x in state.iv1],
               "properties_native": [float(x) for x in state.mprops1],
               "external_state_variables_native": [float(x) for x in state.evs0],
               "iterations": int(state.iterations), "substeps": int(state.subSteps)}
        result["states"].append(row)
        test.printOutput(time, state)
        save(output / "mtest.partial.json", result)

    retain(0.)
    for previous, entry in zip(settings["history"], settings["history"][1:]):
        test.execute(state, workspace, previous["time_s"], entry["time_s"])
        retain(entry["time_s"])
    if sha256(library) != library_sha:
        raise ValueError("Generated behavior binary changed during MTest")
    return result


def _command(argv, output, label, timeout=120):
    save(output / (label + ".command.json"), {"argv": argv, "cwd": str(output), "timeout_seconds": timeout})
    try:
        process = subprocess.run(argv, cwd=output, capture_output=True, text=True, timeout=timeout, check=False)
    except (subprocess.TimeoutExpired, OSError) as exc:
        stdout = getattr(exc, "stdout", "") or ""
        stderr = getattr(exc, "stderr", "") or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode(errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode(errors="replace")
        (output / (label + ".stdout.log")).write_text(stdout, encoding="utf-8")
        (output / (label + ".stderr.log")).write_text(stderr + f"\n{type(exc).__name__}: {exc}\n", encoding="utf-8")
        raise RuntimeError(f"{label} could not complete; partial logs retained") from exc
    (output / (label + ".stdout.log")).write_text(process.stdout, encoding="utf-8")
    (output / (label + ".stderr.log")).write_text(process.stderr, encoding="utf-8")
    if process.returncode != 0:
        raise RuntimeError(f"{label} exited {process.returncode}: {process.stderr[-1200:]}")
    return process.stdout.strip()


def _executable(name):
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f"Required vendor executable unavailable: {name}")
    return str(Path(path).resolve())


def installed_package_identity(prefix, name, version, binding_path, output):
    prefix = Path(prefix).resolve()
    binding_path = Path(binding_path).resolve()
    if not binding_path.is_file() or not binding_path.is_relative_to(prefix):
        raise ValueError(f"The loaded {name} binding is outside its fixed installed package prefix")
    path = prefix / ".spack/spec.json"
    spec = json.loads(path.read_text())
    nodes = [node for node in spec["spec"]["nodes"] if node.get("name") == name]
    if len(nodes) != 1 or nodes[0].get("version") != version or not isinstance(nodes[0].get("hash"), str):
        raise ValueError(f"Installed {name} package metadata is missing or its version drifted")
    destination = output / (name + "_installed_spec.json")
    shutil.copyfile(path, destination)
    return {"name": name, "version": nodes[0]["version"], "spack_hash": nodes[0]["hash"],
            "package_prefix": str(prefix), "spec_sha256": sha256(path), "spec_artifact": destination.name,
            "binding_path": str(binding_path), "binding_sha256": sha256(binding_path),
            "upstream_binary_source_commit": "UNKNOWN"}


def portable_compiler_flags(oflags0, cppflags, include_path):
    flags = ["-Wall", "-Wfatal-errors", "-ansi", *shlex.split(oflags0), "-fPIC", "-I../include",
             *shlex.split(cppflags), "-I" + include_path]
    if ("-O2" not in flags or "-fno-fast-math" not in flags or "-std=c++20" not in flags or
            any(flag.startswith(("-march", "-mtune")) or flag in ("-ffast-math", "-ftree-vectorize") for flag in flags)):
        raise ValueError("Native TFEL compiler configuration drifted from portable O2/no fast-math policy")
    if include_path != TFEL_PREFIX + "/include":
        raise ValueError("TFEL include path differs from the fixed installed package")
    return flags


def solve(input_path):
    import resource
    faulthandler.enable()
    input_path = Path(input_path).resolve()
    output = input_path.parent
    if output != Path("/work") or input_path.name != "input.json":
        raise ValueError("Worker input must be the fixed experiment /work/input.json")
    resource.setrlimit(resource.RLIMIT_AS, (4 * 1024 ** 3,) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (180, 180))
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_FILE_BYTES,) * 2)
    os.umask(0o077)
    settings = json.loads(input_path.read_text(encoding="utf-8"))
    if sha256(SOURCE_PATH) != SOURCE_SHA256:
        raise ValueError("Installed Elasticity.mfront differs from the pinned official TFEL5 source")
    build = output / "build"
    build.mkdir(exist_ok=False)
    shutil.copyfile(SOURCE_PATH, build / "Elasticity.mfront")
    licenses = output / "licenses"
    licenses.mkdir(exist_ok=False)
    license_records = []
    for name in ("LICENCE-GNU-GPL", "LICENCE-CECILL-A-EN", "LICENCE-CECILL-A-FR"):
        path = Path(TFEL_PREFIX) / "share/doc/tfel" / name
        if not path.is_file() or path.stat().st_size > 1024 ** 2:
            raise ValueError("The pinned TFEL installed license inventory is missing/unbounded")
        shutil.copyfile(path, licenses / name)
        license_records.append({"name": name, "sha256": sha256(path), "artifact": "licenses/" + name})
    save(output / "source_attribution.json", {"author": "Helfer Thomas", "source_url": SOURCE_URL,
        "reference_commit": TFEL_COMMIT, "source_sha256": SOURCE_SHA256,
        "installed_source_path": str(SOURCE_PATH), "binary_upstream_commit": "UNKNOWN",
        "installed_tfel_license_files": license_records,
        "mgis_installed_license_directory": "ABSENT in this package; pinned primary source inventory in MATERIAL_POINT_PLAN.md",
        "license_and_redistribution_approval": "UNKNOWN; retain TFEL GPL/CeCILL inventory separately"})
    mfront, compiler, make, config = (_executable(name) for name in ("mfront", "g++", "make", "tfel-config"))
    runtime = {"python": platform.python_version(), "tfel": _command([config, "--version"], output, "tfel_version", 10),
        "mfront": _command([mfront, "--version"], output, "mfront_version", 10),
        "compiler": _command([compiler, "--version"], output, "compiler_version", 10),
        "make": _command([make, "--version"], output, "make_version", 10),
        "tfel_cxx_standard": _command([config, "--cxx-standard"], output, "cxx_standard", 10),
        "tfel_recommended_oflags0": _command([config, "--oflags0"], output, "tfel_oflags0", 10),
        "tfel_cpp_compiler_flags": _command([config, "--cppflags", "--compiler-flags"], output, "tfel_cpp_flags", 10),
        "tfel_include_path": _command([config, "--include-path"], output, "tfel_include_path", 10),
        "executables": {name: {"path": path, "sha256": sha256(path)} for name, path in
            (("mfront", mfront), ("mtest", _executable("mtest")), ("compiler", compiler), ("make", make), ("tfel_config", config))}}
    save(output / "runtime.json", runtime)
    _command([mfront, *BUILD_ARGUMENTS], build, "generate")
    flags_override = portable_compiler_flags(runtime["tfel_recommended_oflags0"],
                                            runtime["tfel_cpp_compiler_flags"], runtime["tfel_include_path"])
    compile_output = _command([make, "-C", "src", "-f", "Makefile.mfront", "-j1", "--trace",
                               "CXX=" + compiler, "CXXFLAGS=" + shlex.join(flags_override)], build, "compile")
    compiler_commands = [line for line in compile_output.splitlines() if compiler in line and
                         any(flag in line for flag in (" -c", " -shared", " -M "))]
    if not compiler_commands:
        raise ValueError("The actual expanded compiler commands were not retained")
    library = build / "src/libBehaviour.so"
    if not library.is_file() or library.stat().st_size == 0:
        raise ValueError("MFront did not generate the fixed libBehaviour.so")
    library_sha = sha256(library)
    makefile = build / "src/Makefile.mfront"
    compiler_flags = [line for line in makefile.read_text().splitlines() if any(
        key in line for key in ("CXXFLAGS", "CPPFLAGS", "LDFLAGS", "CXX ", "CXX=", "INCLUDES", "-std="))]
    dependencies = _command([_executable("ldd"), str(library)], output, "library_dependencies", 10)
    dependency_hashes = {}
    for line in dependencies.splitlines():
        parts = line.split()
        native = parts[2] if len(parts) > 2 and parts[1] == "=>" else (parts[0] if parts else "")
        if native.startswith("/") and Path(native).is_file():
            dependency_hashes[native] = sha256(native)
    save(output / "build_identity.json", {"library_path": "build/src/libBehaviour.so", "library_sha256": library_sha,
        "source_sha256": SOURCE_SHA256, "generation_arguments": BUILD_ARGUMENTS,
        "compiler_flags_makefile": compiler_flags, "makefile_sha256": sha256(makefile),
        "actual_compiler_commands": compiler_commands,
        "compiler_flags_policy": COMPILER_POLICY, "compiler_flags_override": flags_override,
        "compiler_commands_artifact": "build/compile.stdout.log", "dependency_sha256": dependency_hashes})
    import numpy as np
    import mgis.behaviour as binding
    # TFEL's top-level initializer imports std, registering the Boost.Python
    # vector/map converters required by MTest's history dictionary overloads.
    import tfel
    import tfel.math
    import mtest
    mgis_package = installed_package_identity(MGIS_PREFIX, "mgis", "3.0", binding.__file__, output)
    tfel_package = installed_package_identity(TFEL_PREFIX, "tfel", "5.0.0", mtest._mtest.__file__, output)
    behaviour = binding.load(str(library), "Elasticity", binding.Hypothesis.Tridimensional)
    if behaviour.hypothesis != binding.Hypothesis.Tridimensional:
        raise ValueError("The generated behavior must implement the fixed Tridimensional hypothesis")
    descriptor = {key: str(getattr(behaviour, key)) for key in ("behaviour", "function", "source", "hypothesis", "tfel_version", "btype", "kinematic", "symmetry", "build_id")}
    descriptor.update({key: [variable.name for variable in getattr(behaviour, key)] for key in
        ("gradients", "thermodynamic_forces", "material_properties", "internal_state_variables", "external_state_variables")})
    descriptor.update(computes_stored_energy=bool(behaviour.computesStoredEnergy),
                      computes_dissipated_energy=bool(behaviour.computesDissipatedEnergy),
                      absent_state_buffers_policy="Do not call MGIS3 zero-column or unsupported-energy getters; absence is explicit, no substituted responses")
    if descriptor["material_properties"] != ["YoungModulus", "PoissonRatio"] or descriptor["external_state_variables"] != ["Temperature"]:
        raise ValueError("Unexpected Elasticity generic/3D material or external-state descriptor")
    runtime.update({"numpy": np.__version__, "mgis_binding_sha256": sha256(binding.__file__),
                    "mgis_binding_path": binding.__file__, "mtest_binding_path": mtest._mtest.__file__,
                    "mtest_binding_sha256": sha256(mtest._mtest.__file__),
                    "mgis": mgis_package["version"], "mgis_package": mgis_package, "tfel_package": tfel_package,
                    "mgis_version_source": "Actual .spack/spec.json plus fixed-prefix resolved loaded binding"})
    save(output / "runtime.json", runtime)
    raw = {"schema_version": "1", "input_sha256": sha256(input_path), "source_sha256": SOURCE_SHA256,
           "worker_sha256": sha256(__file__), "library_sha256": library_sha,
           "runtime": runtime, "behaviour_description": descriptor,
           "conventions": {"physical": "xx,yy,zz,xy,xz,yz", "native": "xx,yy,zz,sqrt2*xy,sqrt2*xz,sqrt2*yz",
                           "strain": "infinitesimal, not engineering shear", "stress_unit": "MPa"}}
    raw["mgis"] = integrate_history(binding, behaviour, settings, library_sha, output)
    if "native_rejection" in raw["mgis"]:
        raw["native_rejection"] = raw["mgis"]["native_rejection"]
    else:
        raw["mtest"] = mtest_history(mtest, library, settings, output)
    if sha256(library) != library_sha or sha256(input_path) != raw["input_sha256"] or sha256(SOURCE_PATH) != SOURCE_SHA256:
        raise ValueError("Native input/source/library identity drifted during execution")
    save(output / "native_raw.json", raw)


if __name__ == "__main__":
    solve("/work/input.json")
