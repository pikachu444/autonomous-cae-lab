"""Fixed SVK material-point native worker; importing it executes no native code.

Only captured adapter inputs select a history. The constitutive source, generic
interface, finite-strain measures, build policy and package prefixes are fixed.
"""

from copy import deepcopy
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import re
import shlex
import time


TFEL_PREFIX = "/opt/spack/opt/spack/linux-zen2/tfel-5.0.0-flantzxx3vcxkf4qlpwnl7midzoe33ma"
MGIS_PREFIX = "/opt/spack/opt/spack/linux-zen2/mgis-3.0-dfpytmkwj5iza5npkbvk5hils7heaxad"
TFEL_COMMIT = "85554f233306548d8c9c4d36af54b715c608b8c7"
BEHAVIOUR = "SaintVenantKirchhoffElasticity"
SOURCE_SHA256 = "d97fcce350a40060c287aaad9928603e8b144039a7cef95045073b00079efff4"
SOURCE_URL = f"https://raw.githubusercontent.com/thelfer/tfel/{TFEL_COMMIT}/mfront/tests/behaviours/{BEHAVIOUR}.mfront"
SOURCE_PATH = Path(TFEL_PREFIX) / "share/doc/mfront/tests/behaviours" / (BEHAVIOUR + ".mfront")
BUILD_ARGUMENTS = ["--omake", "--interface=generic", "--@SelectedModellingHypothesis=Tridimensional", BEHAVIOUR + ".mfront"]
COMPILER_POLICY = "TFEL_oflags0_portable_O2_no_architecture_specific_flags"
MAX_FILE_BYTES = 128 * 1024 ** 2
F_COMPONENTS = ("xx", "yy", "zz", "xy", "yx", "xz", "zx", "yz", "zy")
F_NAMES = ("FXX", "FYY", "FZZ", "FXY", "FYX", "FXZ", "FZX", "FYZ", "FZY")
IDENTITY = [1., 1., 1., 0., 0., 0., 0., 0., 0.]
MTEST_DEFORMATION_GRADIENT_EPSILON = 1e-14
SOURCE_NAMES = {"domain_reference.py", "domain_init.py", "mfront_hyperelastic.py",
    "mfront_hyperelastic_worker.py", "mfront_material.py", "mfront_material_worker.py",
    "codeaster_elasticity.py", "codeaster_execution.py", "execution_control.py"}


def sha256(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def state_hash(state):
    return hashlib.sha256(json.dumps(state, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def _vector(array, count, label):
    values = [float(value) for value in array.reshape(-1)]
    if len(values) != count or not all(math.isfinite(value) for value in values):
        raise ValueError(f"Native {label} must contain exactly {count} finite components")
    return values


def _cache(manager):
    array = manager.K
    if tuple(array.shape) != (1, 9, 9):
        raise ValueError("Native single-point PK1/DPK1_DF tangent cache must have shape (1,9,9)")
    values = _vector(array, 81, "DPK1_DF")
    return [values[index:index + 9] for index in range(0, 81, 9)]


def snapshot(manager, state, properties, external, dt):
    # The descriptor has already proved absent ISV/dissipation. Never call the
    # MGIS3 zero-column getters, nor manufacture an absent stored-energy buffer.
    return {"deformation_gradient": _vector(state.gradients, 9, "F"),
        "pk1_stress_mpa": _vector(state.thermodynamic_forces, 9, "PK1"),
        "stored_energies": _vector(state.stored_energies, 1, "stored energy"),
        "internal_state_variables": [], "dissipated_energies": [],
        "material_properties": deepcopy(properties), "external_state_variables": deepcopy(external),
        "manager_tangent_cache_mpa": _cache(manager), "dt_s": float(dt)}


def fresh_manager(binding, behaviour, baseline):
    required = {"deformation_gradient", "pk1_stress_mpa", "stored_energies", "internal_state_variables", "dissipated_energies",
        "material_properties", "external_state_variables", "manager_tangent_cache_mpa", "dt_s"}
    if (set(baseline) != required or baseline["internal_state_variables"] != [] or baseline["dissipated_energies"] != [] or
            set(baseline["material_properties"]) != {"YoungModulus", "PoissonRatio"} or
            set(baseline["external_state_variables"]) != {"Temperature"} or type(baseline["dt_s"]) not in (int, float) or
            not math.isfinite(baseline["dt_s"]) or baseline["dt_s"] < 0 or
            any(type(v) not in (int, float) or not math.isfinite(v) for v in
                (*baseline["material_properties"].values(), *baseline["external_state_variables"].values()))):
        raise ValueError("Complete finite native baseline/properties/absent-state policy required")
    manager = binding.MaterialDataManager(behaviour, 1)
    manager.allocateArrayOfTangentOperatorBlocks()
    _cache(manager)
    for state in (manager.s0, manager.s1):
        for name, value in baseline["material_properties"].items():
            binding.setMaterialProperty(state, name, value)
        for name, value in baseline["external_state_variables"].items():
            binding.setExternalStateVariable(state, name, value)
        for native, key, count in (("gradients", "deformation_gradient", 9),
            ("thermodynamic_forces", "pk1_stress_mpa", 9), ("stored_energies", "stored_energies", 1)):
            array = getattr(state, native)
            _vector(array, count, native)
            values = baseline[key]
            if len(values) != count or not all(type(v) in (int, float) and math.isfinite(v) for v in values):
                raise ValueError("Incomplete baseline native state")
            array.reshape(-1)[:] = values
    values = baseline["manager_tangent_cache_mpa"]
    if len(values) != 9 or any(len(row) != 9 for row in values):
        raise ValueError("Incomplete baseline manager tangent cache")
    manager.K.reshape(-1)[:] = [v for row in values for v in row]
    _cache(manager)
    return manager


def initial_manager(binding, behaviour, properties, external):
    manager = binding.MaterialDataManager(behaviour, 1)
    manager.allocateArrayOfTangentOperatorBlocks()
    _cache(manager)
    for state in (manager.s0, manager.s1):
        for name, value in properties.items():
            binding.setMaterialProperty(state, name, value)
        for name, value in external.items():
            binding.setExternalStateVariable(state, name, value)
        for name, count in (("gradients", 9), ("thermodynamic_forces", 9), ("stored_energies", 1)):
            array = getattr(state, name)
            _vector(array, count, name)
            array.reshape(-1)[:] = IDENTITY if name == "gradients" else [0.] * count
    manager.K.reshape(-1)[:] = 0.
    return manager


def _integrate(binding, manager, dt):
    options = binding.BehaviourIntegrationOptions()
    if (options.integration_type != binding.IntegrationType.IntegrationWithConsistentTangentOperator or
            options.compute_speed_of_sound is not False):
        raise ValueError("MGIS integration options differ from consistent tangent/no sound-speed policy")
    started = time.perf_counter()
    result = binding.integrate(manager, options, dt, 0, 1)
    code = int(result.exit_status)
    if code not in (-1, 0, 1):
        raise ValueError("Unexpected MGIS native integration return")
    return {"integration_return": code, "time_step_increase_factor": float(result.time_step_increase_factor),
        "error_message": str(result.error_message), "failure_or_unreliable_point_index": int(result.n),
        "elapsed_seconds": time.perf_counter() - started, "native_dt_s": float(dt)}


def cauchy_from_pk1(f, p):
    # A measured PK1 conversion, never the independent constitutive reference.
    indices = ((0, 0), (1, 1), (2, 2), (0, 1), (1, 0), (0, 2), (2, 0), (1, 2), (2, 1))
    fm, pm = [[0.] * 3 for _ in range(3)], [[0.] * 3 for _ in range(3)]
    for (i, j), fv, pv in zip(indices, f, p):
        fm[i][j], pm[i][j] = fv, pv
    a, b, c = fm
    determinant = a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0]) + a[2] * (b[0] * c[1] - b[1] * c[0])
    if not math.isfinite(determinant) or determinant <= 0.:
        raise ValueError("Observed native F has no positive finite Jacobian")
    matrix = [[math.fsum(pm[i][k] * fm[j][k] for k in range(3)) / determinant for j in range(3)] for i in range(3)]
    return [matrix[i][j] for i, j in ((0, 0), (1, 1), (2, 2), (0, 1), (0, 2), (1, 2))]


def integrate_history(binding, behaviour, settings, library_sha, output):
    properties = {"YoungModulus": settings["material"]["youngs_modulus_mpa"], "PoissonRatio": settings["material"]["poisson_ratio"]}
    external = {"Temperature": settings["temperature_k"]}
    initial = initial_manager(binding, behaviour, properties, external)
    baseline = snapshot(initial, initial.s0, properties, external, 0.)
    raw = {"library_sha256": library_sha, "initial": {"phase": "INITIAL_UNPREPARED", "time_s": 0.,
        "deformation_gradient": list(IDENTITY), "state": deepcopy(baseline), "state_sha256": state_hash(baseline)}, "steps": []}
    probe_root = output / "probes"
    probe_root.mkdir(exist_ok=False)
    save(output / "mgis.partial.json", raw)
    try:
        for index, entry in enumerate(settings["history"][1:], 1):
            dt = entry["time_s"] - settings["history"][index - 1]["time_s"]
            baseline = {**deepcopy(baseline), "dt_s": float(dt)}
            nominal = fresh_manager(binding, behaviour, baseline)
            before = snapshot(nominal, nominal.s0, properties, external, dt)
            nominal.s1.gradients.reshape(-1)[:] = entry["deformation_gradient"]
            returned = _integrate(binding, nominal, dt)
            final = snapshot(nominal, nominal.s1, properties, external, dt)
            step = {"time_s": entry["time_s"], "dt_s": float(dt), "deformation_gradient": list(final["deformation_gradient"]),
                "pk1_stress_mpa": list(final["pk1_stress_mpa"]), "cauchy_stress_mpa": cauchy_from_pk1(final["deformation_gradient"], final["pk1_stress_mpa"]),
                "pk1_tangent_mpa": deepcopy(final["manager_tangent_cache_mpa"]), "stored_energy_density_mpa": final["stored_energies"][0],
                **returned, "initial_state": deepcopy(before), "initial_state_sha256": state_hash(before),
                "nominal_before_probes": deepcopy(final), "finite_differences": []}
            raw["steps"].append(step)
            if returned["integration_return"] != 1:
                raw["native_rejection"] = {"driver": "MGIS", "history_index": index, "phase": "nominal", **returned}
                break
            nominal_sha = state_hash(final)
            for h in settings["limits"]["finite_difference_steps"]:
                fd = {"h": h, "probes": []}
                step["finite_differences"].append(fd)
                folder = probe_root / f"step_{index:04d}" / f"h_{h:.0e}"
                folder.mkdir(parents=True, exist_ok=False)
                for column in range(9):
                    for sign in (-1, 1):
                        probe_manager = fresh_manager(binding, behaviour, baseline)
                        probe_before = snapshot(probe_manager, probe_manager.s0, properties, external, dt)
                        target = list(entry["deformation_gradient"])
                        target[column] += sign * h
                        probe_manager.s1.gradients.reshape(-1)[:] = target
                        result = _integrate(binding, probe_manager, dt)
                        probe_final = snapshot(probe_manager, probe_manager.s1, properties, external, dt)
                        probe = {"column": column, "sign": sign, "deformation_gradient": list(probe_final["deformation_gradient"]),
                            "pk1_stress_mpa": list(probe_final["pk1_stress_mpa"]), "stored_energy_density_mpa": probe_final["stored_energies"][0],
                            **result, "initial_state": deepcopy(probe_before), "initial_state_sha256": state_hash(probe_before),
                            "final_state": deepcopy(probe_final), "final_state_sha256": state_hash(probe_final)}
                        fd["probes"].append(probe)
                        save(folder / f"column_{column}_{'plus' if sign == 1 else 'minus'}.json", probe)
                        if state_hash(snapshot(nominal, nominal.s1, properties, external, dt)) != nominal_sha:
                            raise ValueError("Independent probes mutated the successful nominal buffers/cache")
                        if result["integration_return"] != 1:
                            raw["native_rejection"] = {"driver": "MGIS", "history_index": index,
                                "phase": "finite_difference", "column": column, "sign": sign, "h": h, **result}
                            break
                    if "native_rejection" in raw:
                        break
                if "native_rejection" in raw:
                    break
                signed = {(probe["column"], probe["sign"]): probe for probe in fd["probes"]}
                fd["pk1_tangent_mpa"] = [[(signed[j, 1]["pk1_stress_mpa"][i] - signed[j, -1]["pk1_stress_mpa"][i]) / (2. * h)
                    for j in range(9)] for i in range(9)]
                fd["energy_gradient_mpa"] = [(signed[j, 1]["stored_energy_density_mpa"] - signed[j, -1]["stored_energy_density_mpa"]) / (2. * h) for j in range(9)]
                save(output / "mgis.partial.json", raw)
            step["nominal_after_probes"] = snapshot(nominal, nominal.s1, properties, external, dt)
            if state_hash(step["nominal_after_probes"]) != nominal_sha:
                raise ValueError("Nominal buffers/cache changed before successful history update")
            save(output / "mgis.partial.json", raw)
            if "native_rejection" in raw:
                break
            # Copy the actual post-update native state, not our previous Python
            # observation; no finite-difference manager is ever updated.
            binding.update(nominal)
            baseline = snapshot(nominal, nominal.s0, properties, external, dt)
            step["nominal_after_update"] = deepcopy(baseline)
            step["nominal_after_update_sha256"] = state_hash(baseline)
            save(output / "mgis.partial.json", raw)
    except BaseException as error:
        raw["execution_failure"] = {"type": type(error).__name__, "message": str(error)}
        save(output / "mgis.partial.json", raw)
        raise
    save(output / "mgis.partial.json", raw)
    return raw


def mtest_history(module, library, settings, output):
    library_sha = sha256(library)
    test = module.MTest()
    test.setModellingHypothesis("Tridimensional")
    test.setBehaviour("generic", str(library), BEHAVIOUR)
    test.setMaximumNumberOfSubSteps(1)
    test.setMaximumNumberOfIterations(10)
    test.setDeformationGradientEpsilon(MTEST_DEFORMATION_GRADIENT_EPSILON)
    test.setStressEpsilon(1e-10)
    for name, value in {"YoungModulus": settings["material"]["youngs_modulus_mpa"], "PoissonRatio": settings["material"]["poisson_ratio"]}.items():
        test.setMaterialProperty(name, value)
    test.setExternalStateVariable("Temperature", settings["temperature_k"])
    for column, name in enumerate(F_NAMES):
        test.setImposedDeformationGradient(name, {row["time_s"]: row["deformation_gradient"][column] for row in settings["history"]})
    test.setDeformationGradient(list(IDENTITY))
    test.setStress([0.] * 6)
    test.setOutputFileName(str(output / "mtest.res"))
    test.setOutputFilePrecision(17)
    test.completeInitialisation()
    state, workspace = module.MTestCurrentState(), module.MTestWorkSpace()
    test.initializeCurrentState(state)
    test.initializeWorkSpace(workspace)
    record = {"library_sha256": library_sha, "steps": [], "stress_measure": "Cauchy_Kelvin6",
        "gradient_names": list(F_NAMES), "substep_limit": 1, "stored_energy": "UNKNOWN", "dissipated_energy": "UNKNOWN",
        "deformation_gradient_epsilon": MTEST_DEFORMATION_GRADIENT_EPSILON}
    save(output / "mtest.partial.json", record)
    try:
        for previous, entry in zip(settings["history"], settings["history"][1:]):
            started = time.perf_counter()
            returned = test.execute(state, workspace, previous["time_s"], entry["time_s"])
            if returned is not None:
                raise ValueError("MTest execute(state,workspace,t0,t1) must have its documented void return")
            gradients, stress = [float(v) for v in state.e1], [float(v) for v in state.s1]
            if len(gradients) != 9 or len(stress) != 6 or not all(math.isfinite(v) for v in gradients + stress):
                raise ValueError("MTest did not expose complete finite physical9 F/Kelvin6 Cauchy")
            record["steps"].append({"phase": "INTEGRATED", "time_s": entry["time_s"], "dt_s": entry["time_s"] - previous["time_s"],
                "deformation_gradient": gradients, "imposed_deformation_gradient": list(entry["deformation_gradient"]),
                "cauchy_stress_kelvin_mpa": stress, "integration_return": 1,
                "return_semantics": "Documented void execute completed without exception", "iterations": int(state.iterations), "substeps": int(state.subSteps),
                "elapsed_seconds": time.perf_counter() - started})
            test.printOutput(entry["time_s"], state)
            save(output / "mtest.partial.json", record)
    except BaseException as error:
        record["execution_failure"] = {"type": type(error).__name__, "message": str(error)}
        save(output / "mtest.partial.json", record)
        raise
    if sha256(library) != library_sha:
        raise ValueError("Generated behaviour library changed during MTest")
    return record


def finite_options(binding):
    options = binding.FiniteStrainBehaviourOptions()
    options.stress_measure = binding.FiniteStrainBehaviourOptionsStressMeasure.PK1
    options.tangent_operator = binding.FiniteStrainBehaviourOptionsTangentOperator.DPK1_DF
    if (options.stress_measure != binding.FiniteStrainBehaviourOptionsStressMeasure.PK1 or
            options.tangent_operator != binding.FiniteStrainBehaviourOptionsTangentOperator.DPK1_DF):
        raise ValueError("Explicit PK1/DPK1_DF finite-strain options did not bind")
    return options


def descriptor(binding, behaviour):
    h = binding.Hypothesis.Tridimensional
    if (behaviour.hypothesis != h or behaviour.btype != binding.BehaviourType.STANDARDFINITESTRAINBEHAVIOUR or
            behaviour.kinematic != binding.BehaviourKinematic.FINITESTRAINKINEMATIC_F_CAUCHY or
            behaviour.behaviour != BEHAVIOUR or not str(behaviour.tfel_version).startswith("5.0.0") or
            not behaviour.computesStoredEnergy or behaviour.computesDissipatedEnergy or behaviour.internal_state_variables):
        raise ValueError("SVK finite-strain/energy/absent-state descriptor differs from the pinned law")
    gradients, forces, blocks = list(behaviour.gradients), list(behaviour.thermodynamic_forces), list(behaviour.tangent_operator_blocks)
    if (len(gradients) != 1 or len(forces) != 1 or len(blocks) != 1 or gradients[0].name != "DeformationGradient" or
            forces[0].name != "FirstPiolaKirchhoffStress" or binding.getArraySize(gradients, h) != 9 or binding.getArraySize(forces, h) != 9 or
            blocks[0][0].name != forces[0].name or blocks[0][1].name != gradients[0].name or
            any(binding.getVariableSize(variable, h) != 9 for variable in (gradients[0], forces[0], *blocks[0])) or
            any(variable.getType() != "Tensor" for variable in (gradients[0], forces[0], *blocks[0])) or
            [v.name for v in behaviour.material_properties] != ["YoungModulus", "PoissonRatio"] or
            [v.name for v in behaviour.external_state_variables] != ["Temperature"]):
        raise ValueError("SVK requires physical9 F/PK1 and exactly one 9x9 DPK1_DF block")
    return {"behaviour": behaviour.behaviour, "hypothesis": "Tridimensional", "behavior_type": "STANDARD_FINITE_STRAIN",
        "kinematic": "F_CAUCHY", "native_btype": str(behaviour.btype), "native_kinematic": str(behaviour.kinematic),
        "tfel_version": str(behaviour.tfel_version), "build_id": str(behaviour.build_id), "source": str(behaviour.source),
        "gradients": ["DeformationGradient"], "gradient_sizes": [9], "thermodynamic_forces": ["FirstPiolaKirchhoffStress"], "force_sizes": [9],
        "tangent_operator_blocks": [{"force": "FirstPiolaKirchhoffStress", "gradient": "DeformationGradient", "shape": [9, 9]}],
        "material_properties": ["YoungModulus", "PoissonRatio"], "external_state_variables": ["Temperature"],
        "internal_state_variables": [], "computes_stored_energy": True, "computes_dissipated_energy": False,
        "stress_measure": "PK1", "tangent_operator": "DPK1_DF", "component_order": list(F_COMPONENTS),
        "stored_energy_measure": "per_reference_volume", "binary_upstream_source_commit": "UNKNOWN"}


def _load_module(path, expected, name):
    if path.is_symlink() or not path.is_file() or sha256(path) != expected:
        raise ValueError("Captured source is missing, linked or differs from bound raw bytes")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def assert_captures(output, envelope):
    pins = envelope["captured_source_sha256"]
    if set(pins) != SOURCE_NAMES:
        raise ValueError("Complete current native transport/Domain source capture required")
    for name, digest in pins.items():
        path = output / name
        if path.is_symlink() or not path.is_file() or sha256(path) != digest:
            raise ValueError("Captured native source drifted")


def validated_policy(policy):
    required = {"solver_memory_mb", "solver_time_seconds", "subprocess_timeout_seconds", "solver_time_source", "wall_time_source", "qualification"}
    if not isinstance(policy, dict) or set(policy) != required:
        raise ValueError("Exact existing execution policy required")
    cpu, wall = policy["solver_time_seconds"], policy["subprocess_timeout_seconds"]
    if (type(cpu) is not int or not 0 < cpu <= 2 ** 31 - 1 or
            (wall is not None and (type(wall) is not int or not 0 < wall <= 2 ** 31 - 1)) or
            policy["solver_memory_mb"] != 1024 or policy["qualification"] != "UNKNOWN" or
            policy["solver_time_source"] not in ("USER_ENVIRONMENT", "PINNED_RUN_ASTER_DEFAULT") or
            policy["wall_time_source"] not in ("USER_ENVIRONMENT", "NO_WALL_TIME_LIMIT") or
            (policy["solver_time_source"] == "PINNED_RUN_ASTER_DEFAULT" and cpu != 86400) or
            (policy["wall_time_source"] == "NO_WALL_TIME_LIMIT" and wall is not None) or
            (policy["wall_time_source"] == "USER_ENVIRONMENT" and wall is None)):
        raise ValueError("Positive existing CPU/optional wall policy required; zero is not unlimited")
    return deepcopy(policy)


COMPILER_COMMAND_POLICY = "SVK_exact_compile_dependency_and_non_LTO_shared_link_v1"
_LINK_LIBRARIES = ["MFrontProfiling", "TFELMaterial", "TFELMath", "TFELUtilities", "TFELException", "TFELNUMODIS"]
_COMPILER_NAME = re.compile(
    r"(?:^|[\s/\"';&|()])(?:[\w.+]+-)*(?:g\+\+|gcc|clang\+\+|clang|c\+\+|cc)"
    r"(?:-[\d.]+)?(?=$|[\s\"';&|(),])")
_COMPILER_WRAPPERS = {"sh", "bash", "dash", "zsh", "ksh", "env", "command", "exec", "ccache", "sccache", "distcc", "icecc"}


def _logical_build_lines(text):
    """Remove POSIX escaped newlines without executing or repairing the log."""
    if not isinstance(text, str) or not text or "\x00" in text:
        raise ValueError("Actual compiler log is empty, malformed or contains NUL")
    buffer, quote, index = [], None, 0
    while index < len(text):
        char = text[index]
        if char == "\\" and quote != "'":
            if index + 1 == len(text):
                raise ValueError("Unterminated compiler-log escape/continuation")
            following = text[index + 1]
            if following == "\n":
                if index + 2 == len(text):
                    raise ValueError("Unterminated compiler-log continuation")
                index += 2
                continue
            if following == "\r" and text[index + 2:index + 3] == "\n":
                if index + 3 == len(text):
                    raise ValueError("Unterminated compiler-log continuation")
                index += 3
                continue
            buffer.extend((char, following))
            index += 2
            continue
        if char in ("'", '"'):
            if quote is None:
                quote = char
            elif quote == char:
                quote = None
        if char in ("\r", "\n"):
            if quote is not None:
                raise ValueError("Unterminated or unsupported multiline compiler-log quote")
            if char == "\r":
                if text[index + 1:index + 2] != "\n":
                    raise ValueError("Malformed compiler-log line ending")
                index += 1
            yield "".join(buffer)
            buffer = []
        else:
            buffer.append(char)
        index += 1
    if quote is not None:
        raise ValueError("Unterminated compiler-log quote")
    if buffer:
        yield "".join(buffer)


def compiler_command_evidence(text, compiler, flags, *, behaviour=BEHAVIOUR):
    """Classify a fixed generated generic build; shell tokens are never executed.

    The original recipes remain in the hashed log. Normalized command strings
    and full joined recipes bind every token, including continued flags. Source
    compilation/dependency stages use the exact queried portable flags. The
    non-LTO link consumes only their two objects and the fixed TFEL libraries.
    A backend supplies its trusted source identifier; settings cannot select it.
    The default preserves the existing SVK build and admission policy.
    """
    if (not isinstance(compiler, str) or not compiler.startswith("/") or
            any(char in compiler for char in ("\x00", "\n", "\r")) or
            not isinstance(flags, list) or not all(isinstance(flag, str) for flag in flags) or
            not {"-O2", "-fno-fast-math", "-std=c++20"}.issubset(flags)):
        raise ValueError("Fixed compiler/exact portable flag identity is required")
    if not isinstance(behaviour, str) or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", behaviour) is None:
        raise ValueError("Trusted behaviour must be one ASCII source identifier")
    sources = [behaviour + ".cxx", behaviour + "-generic.cxx"]
    objects = [behaviour + "-generic.o", behaviour + ".o"]
    records = []
    for recipe in _logical_build_lines(text):
        lexer = shlex.shlex(recipe, posix=True, punctuation_chars=";&|<>")
        lexer.whitespace_split, lexer.commenters = True, ""
        tokens = list(lexer)
        segments, segment = [], []
        for token in tokens:
            if token == ";":
                segments.append(segment)
                segment = []
            else:
                segment.append(token)
        segments.append(segment)
        for command in segments:
            if not command:
                continue
            executable = Path(command[0]).name
            # A quoted nested command is one shlex token, so exact list-member
            # checks lose its compiler and flags. Such payloads/wrappers are
            # refused, never recursively executed or counted as harmless text.
            compiler_like = (executable in _COMPILER_WRAPPERS or "g++" in executable or
                             any(compiler in token or _COMPILER_NAME.search(token) for token in command))
            if not compiler_like:
                continue
            if command[0] != compiler or command.count(compiler) != 1:
                raise ValueError("Unknown/wrapped compiler command in actual build log")
            if any(token in ("&", "&&", "|", "||", "<", "<<", ">>", "#") or
                   "$(" in token or "`" in token for token in command):
                raise ValueError("Unsupported compiler shell syntax in actual build log")
            if any(token.startswith(("-march", "-mtune", "-flto")) or
                   token in ("-ffast-math", "-ftree-vectorize", "-Ofast", "-fuse-linker-plugin")
                   for token in command):
                raise ValueError("Actual compiler command violates portable/non-LTO policy")
            args = command[1:]
            record = {"command": shlex.join(command), "tokens": command, "logical_recipe": recipe}
            if "-M" in args:
                if args.count("-M") != 1 or "-c" in args or "-shared" in args:
                    raise ValueError("Ambiguous actual dependency command")
                source = next((name for name in sources if name in args), None)
                target = source[:-4] + ".d.$$" if source else None
                if args != ["-M", *flags, source, ">", target]:
                    raise ValueError("Actual dependency flags/source/output differ from fixed build")
                record.update(stage="DEPENDENCY", source=source, target=target)
            elif "-c" in args:
                source = next((name for name in sources if name in args), None)
                target = source[:-4] + ".o" if source else None
                if args != [*flags, source, "-o", target, "-c"]:
                    raise ValueError("Actual source compilation flags/source/object differ from fixed build")
                record.update(stage="COMPILE", source=source, target=target)
            elif "-shared" in args:
                expected = ["-shared", *objects, "-o", "libBehaviour.so", "-L" + TFEL_PREFIX + "/lib",
                            *("-l" + name for name in _LINK_LIBRARIES)]
                if args != expected:
                    raise ValueError("Actual non-LTO shared link objects/target/TFEL dependencies differ")
                record.update(stage="LINK", objects=objects, target="libBehaviour.so",
                              library_search_paths=[TFEL_PREFIX + "/lib"], libraries=list(_LINK_LIBRARIES))
            else:
                raise ValueError("Unclassifiable actual compiler command")
            records.append(record)
    for stage in ("DEPENDENCY", "COMPILE"):
        observed = [record["source"] for record in records if record["stage"] == stage]
        if len(observed) != 2 or set(observed) != set(sources):
            raise ValueError("Complete unique actual dependency/source compilations are required")
    if len(records) != 5 or sum(record["stage"] == "LINK" for record in records) != 1:
        raise ValueError("One actual shared-library link and no extra compiler commands are required")
    return records


def library_dependency_paths(text):
    """Bind the recorded native ldd paths, without claiming current host bytes."""
    if not isinstance(text, str) or "\x00" in text or "not found" in text:
        raise ValueError("Malformed/unresolved native library dependency log")
    paths = []
    for line in text.splitlines():
        parts = line.split()
        path = parts[2] if len(parts) > 2 and parts[1] == "=>" else (parts[0] if parts else "")
        if path.startswith("/"):
            if path in paths or ".." in Path(path).parts:
                raise ValueError("Duplicate/noncanonical actual library dependency path")
            paths.append(path)
        elif parts and not parts[0].startswith("linux-vdso."):
            raise ValueError("Unknown actual native library dependency line")
    if not paths:
        raise ValueError("Actual library dependency paths are absent")
    return paths


def build_native(output, transport):
    if not SOURCE_PATH.is_file() or SOURCE_PATH.stat().st_size != 3002 or sha256(SOURCE_PATH) != SOURCE_SHA256:
        raise ValueError("Installed tests SVK source differs from exact pinned 3002-byte source; gallery fallback forbidden")
    build = output / "build"
    build.mkdir(exist_ok=False)
    transport.shutil.copyfile(SOURCE_PATH, build / (BEHAVIOUR + ".mfront"))
    licenses = output / "licenses"
    licenses.mkdir(exist_ok=False)
    license_records = []
    for name in ("LICENCE-GNU-GPL", "LICENCE-CECILL-A-EN", "LICENCE-CECILL-A-FR"):
        source = Path(TFEL_PREFIX) / "share/doc/tfel" / name
        if not source.is_file() or source.stat().st_size > 1024 ** 2:
            raise ValueError("Fixed installed TFEL license inventory unavailable/unbounded")
        transport.shutil.copyfile(source, licenses / name)
        license_records.append({"name": name, "sha256": sha256(source)})
    save(output / "source_attribution.json", {"source_url": SOURCE_URL, "source_sha256": SOURCE_SHA256,
        "reference_commit": TFEL_COMMIT, "installed_source_path": str(SOURCE_PATH), "binary_source_equivalence": "UNKNOWN",
        "licenses": license_records, "license_and_corporate_approval": "UNKNOWN"})
    tools = {name: transport._executable(name) for name in ("mfront", "mtest", "g++", "make", "tfel-config", "ldd")}
    for name in ("mfront", "mtest", "tfel-config"):
        if not Path(tools[name]).is_relative_to(Path(TFEL_PREFIX)):
            raise ValueError("TFEL executable is outside the fixed installed prefix")
    runtime = {"python": platform.python_version(), "executables": {name: {"path": path, "sha256": sha256(path)} for name, path in tools.items()}}
    for label, name, arguments in (("tfel", "tfel-config", ["--version"]), ("mfront", "mfront", ["--version"]),
        ("compiler", "g++", ["--version"]), ("make", "make", ["--version"]), ("tfel_cxx_standard", "tfel-config", ["--cxx-standard"]),
        ("tfel_recommended_oflags0", "tfel-config", ["--oflags0"]), ("tfel_cpp_compiler_flags", "tfel-config", ["--cppflags", "--compiler-flags"]),
        ("tfel_include_path", "tfel-config", ["--include-path"])):
        runtime[label] = transport._command([tools[name], *arguments], output, label, 10)
    save(output / "runtime.json", runtime)
    flags = transport.portable_compiler_flags(runtime["tfel_recommended_oflags0"], runtime["tfel_cpp_compiler_flags"], runtime["tfel_include_path"])
    transport._command([tools["mfront"], *BUILD_ARGUMENTS], build, "generate", None)
    transport._command([tools["make"], "-C", "src", "-f", "Makefile.mfront", "-j1", "--trace",
        "CXX=" + tools["g++"], "CXXFLAGS=" + shlex.join(flags)], build, "compile", None)
    compile_log = build / "compile.stdout.log"
    if compile_log.is_symlink() or not compile_log.is_file() or not 0 < compile_log.stat().st_size <= MAX_FILE_BYTES:
        raise ValueError("Actual compiler log missing/linked/unbounded")
    command_records = compiler_command_evidence(compile_log.read_text(encoding="utf-8"), tools["g++"], flags)
    commands = [record["command"] for record in command_records]
    library, makefile = build / "src/libBehaviour.so", build / "src/Makefile.mfront"
    if not commands or not library.is_file() or not library.stat().st_size or not makefile.is_file():
        raise ValueError("Expanded actual compiler commands/library/Makefile missing")
    dependencies = transport._command([tools["ldd"], str(library)], output, "library_dependencies", 10)
    dependency_hashes = {}
    for name in library_dependency_paths(dependencies):
        if not Path(name).is_file():
            raise ValueError("Actual generated library dependency file is unavailable")
        dependency_hashes[name] = sha256(name)
    dependency_log = output / "library_dependencies.stdout.log"
    if (dependency_log.is_symlink() or not dependency_log.is_file() or
            library_dependency_paths(dependency_log.read_text(encoding="utf-8")) != list(dependency_hashes)):
        raise ValueError("Generated library dependency identities missing")
    identity = {"library_path": "build/src/libBehaviour.so", "library_sha256": sha256(library), "source_sha256": SOURCE_SHA256,
        "generation_arguments": list(BUILD_ARGUMENTS), "makefile_sha256": sha256(makefile), "actual_compiler_commands": commands,
        "compiler_commands_artifact": "build/compile.stdout.log", "compiler_flags_policy": COMPILER_POLICY,
        "compiler_commands_sha256": sha256(compile_log), "compiler_command_policy": COMPILER_COMMAND_POLICY,
        "compiler_command_evidence": command_records,
        "dependency_artifact": "library_dependencies.stdout.log", "dependency_artifact_sha256": sha256(dependency_log),
        "compiler_flags_override": flags, "compiler_flags_makefile": [line for line in makefile.read_text().splitlines()
            if any(token in line for token in ("CXXFLAGS", "CPPFLAGS", "LDFLAGS", "CXX ", "CXX=", "INCLUDES", "-std="))],
        "dependency_sha256": dependency_hashes}
    save(output / "build_identity.json", identity)
    return library, runtime, identity


def solve(input_path):
    import resource
    import faulthandler
    faulthandler.enable()
    input_path = Path(input_path).resolve()
    if input_path != Path("/work/input.json"):
        raise ValueError("Fixed contained /work/input.json required")
    output = input_path.parent
    if input_path.stat().st_size > 128 * 1024:
        raise ValueError("Bounded material input required")
    envelope = json.loads(input_path.read_text(encoding="utf-8"))
    assert_captures(output, envelope)
    pins = envelope["captured_source_sha256"]
    transport = _load_module(output / "mfront_material_worker.py", pins["mfront_material_worker.py"], "captured_mfront_transport")
    domain = _load_module(output / "domain_reference.py", pins["domain_reference.py"], "captured_hyperelastic_domain")
    settings = domain.validate_settings(envelope["settings"])
    policy = validated_policy(envelope["process_policy"])
    cpu = policy["solver_time_seconds"]
    resource.setrlimit(resource.RLIMIT_AS, (4 * 1024 ** 3,) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_FILE_BYTES,) * 2)
    os.umask(0o077)
    library, runtime, identity = build_native(output, transport)
    import numpy as np
    import tfel
    import tfel.math
    import mgis.behaviour as binding
    import mtest
    runtime.update(numpy=np.__version__, mgis="3.0",
        mgis_binding_path=str(Path(binding.__file__).resolve()), mgis_binding_sha256=sha256(binding.__file__),
        mtest_binding_path=str(Path(mtest._mtest.__file__).resolve()), mtest_binding_sha256=sha256(mtest._mtest.__file__),
        mgis_package=transport.installed_package_identity(MGIS_PREFIX, "mgis", "3.0", binding.__file__, output),
        tfel_package=transport.installed_package_identity(TFEL_PREFIX, "tfel", "5.0.0", mtest._mtest.__file__, output))
    save(output / "runtime.json", runtime)
    options = finite_options(binding)
    behaviour = binding.load(options, str(library), BEHAVIOUR, binding.Hypothesis.Tridimensional)
    desc = descriptor(binding, behaviour)
    save(output / "behaviour_description.json", desc)
    raw = {"schema_version": "1", "input_sha256": sha256(input_path), "source_sha256": SOURCE_SHA256,
        "worker_sha256": sha256(__file__), "captured_source_sha256": deepcopy(pins), "library_sha256": identity["library_sha256"],
        "runtime": runtime, "behaviour_description": desc, "finite_strain_options": {"stress_measure": "PK1", "tangent_operator": "DPK1_DF"},
        "process_policy": deepcopy(policy), "conventions": {"general_order": list(F_COMPONENTS), "stress_measure": "PK1",
            "tangent": "rows_P_columns_F", "stored_energy": "native_per_reference_volume_MPa", "MTest": "Cauchy_Kelvin6"}}
    try:
        raw.update(integrate_history(binding, behaviour, settings, identity["library_sha256"], output))
        save(output / "native.partial.json", raw)
        if "native_rejection" not in raw:
            raw["mtest"] = mtest_history(mtest, library, settings, output)
        assert_captures(output, envelope)
        if (sha256(input_path) != raw["input_sha256"] or sha256(library) != identity["library_sha256"] or
                sha256(SOURCE_PATH) != SOURCE_SHA256):
            raise ValueError("Native input/source/library identity drifted during execution")
        save(output / "native_raw.json", raw)
    except BaseException as error:
        raw["execution_failure"] = {"type": type(error).__name__, "message": str(error)}
        save(output / "native.partial.json", raw)
        raise


if __name__ == "__main__":
    solve("/work/input.json")
