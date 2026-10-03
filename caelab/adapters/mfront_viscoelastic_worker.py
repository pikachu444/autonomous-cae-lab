"""Fixed single-branch Maxwell native worker; import starts no native process.

The captured original material worker supplies transport/compiler/package helpers.
All law observations come from the newly compiled trusted behavior, never Python
reference responses. Complete nonzero state/energy and tangent caches are cloned.
"""

from copy import deepcopy
import faulthandler
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import shlex

SOURCE_NAME = "mfront_single_branch_maxwell.mfront"
SOURCE_SHA256 = "8501f6d338d0d58fd9391031274dd0d15ecaf333f6158f0c80a73ffdb99e3d7a"
# Exactly reviewed working-byte variants, never a normalized digest.
TRANSPORT_VARIANTS = {
    "3d909f2e68a29807a6e9333817b6eed3308c51bca126a029465f347f61b71c99": 25001,
    "3200b2beb25fb04f45dd9eaeff426237802c62021861c90242cff7be79f4197f": 25425}
COMPILER_HELPER_NAME = "mfront_hyperelastic_worker.py"
TRANSPORT_KEY = "caelab/adapters/mfront_material_worker.py"
COMPILER_HELPER_KEY = "caelab/adapters/mfront_hyperelastic_worker.py"
MTEST_LIMITS = {"substep_limit": 1, "iteration_limit": 10,
                "strain_epsilon": 1e-14, "stress_epsilon_mpa": 1e-10}
MTEST_COMPONENTS = ["EXX", "EYY", "EZZ", "EXY", "EXZ", "EYZ"]
MTEST_BUFFER_MAPPING = {
    "source_commit": "85554f233306548d8c9c4d36af54b715c608b8c7",
    "hypothesis": "Tridimensional", "gradient_count": 6,
    "imposed_gradient_constraint_count": 6, "global_unknown_count": 12,
    "global_gradient_slice": [0, 6],
    "global_u0": "StudyCurrentState.u0", "global_u1": "StudyCurrentState.u1",
    "prepared_e0_kelvin": "CurrentState.e0 (prepared start of increment)",
    "gradients_kelvin": "CurrentState.e1 (last constitutive evaluation)",
    "stress_kelvin_mpa": "CurrentState.s1", "internal_state_variables": "CurrentState.iv1",
    "committed_s0_kelvin_mpa": "CurrentState.s0", "committed_iv0": "CurrentState.iv0",
    "initial_phase": "INITIAL_UNPREPARED", "post_execute_phase": "AFTER_EXECUTE_COMMIT",
    "iterations": "StudyCurrentState.iterations (cumulative)",
    "iterations_increment": "actual iterations_after minus actual iterations_before"}
MTEST_TABLE_MAPPING = {"time": "time_s", "gradients": "StudyCurrentState.u0[0:6]",
    "stress": "CurrentState.s0", "branch": "CurrentState.iv0",
    "stored_energy": "CurrentState.se0", "dissipated_energy": "CurrentState.de0"}
REFERENCE_SOURCE_SHA256 = "d1e378bf9c473c93d7e292b403196a750e72df70e1a8737ed0df80a7bc2dce86"
TFEL_COMMIT = "85554f233306548d8c9c4d36af54b715c608b8c7"
REFERENCE_SOURCE_URL = f"https://raw.githubusercontent.com/thelfer/tfel/{TFEL_COMMIT}/mfront/tests/behaviours/GeneralizedMaxwell.mfront"
BEHAVIOUR = "SingleBranchMaxwell"
BUILD_ARGUMENTS = ["--omake", "--interface=generic", "--@SelectedModellingHypothesis=Tridimensional", SOURCE_NAME]
TFEL_PREFIX = "/opt/spack/opt/spack/linux-zen2/tfel-5.0.0-flantzxx3vcxkf4qlpwnl7midzoe33ma"
MGIS_PREFIX = "/opt/spack/opt/spack/linux-zen2/mgis-3.0-dfpytmkwj5iza5npkbvk5hils7heaxad"
MAX_FILE_BYTES = 128 * 1024 ** 2
MAX_RAW_BYTES = 32 * 1024 ** 2
MATERIAL_KEYS = ["equilibrium_bulk_modulus_mpa", "equilibrium_shear_modulus_mpa",
                 "branch_bulk_modulus_mpa", "branch_shear_modulus_mpa", "relaxation_time_s"]
PROPERTY_NAMES = ["EquilibriumBulkModulus", "EquilibriumShearModulus",
                  "BranchBulkModulus", "BranchShearModulus", "RelaxationTime"]
ARRAYS = {"gradients": "gradients_kelvin", "thermodynamic_forces": "stress_kelvin_mpa",
          "internal_state_variables": "internal_state_variables", "stored_energies": "stored_energies",
          "dissipated_energies": "dissipated_energies"}
EXPECTED_SHAPES = {"gradients_kelvin": [1, 6], "stress_kelvin_mpa": [1, 6],
                   "internal_state_variables": [1, 6], "stored_energies": [1], "dissipated_energies": [1]}


SEALED_MTEST_MATH_BINDING = {
    "loaded_path": "/opt/spack/var/spack/environments/simvia_env/.spack-env/view/lib/python3.11/site-packages/tfel/math.so",
    "resolved_path": TFEL_PREFIX + "/lib/python3.11/site-packages/tfel/math.so",
    "size_bytes": 927872,
    "sha256": "9685745ba9c4b2a4a83e3fa593767ff1e88649362a6a06cc86277b6780910245"}


def checked_mtest_math_binding(record):
    """The extra converter binding is adapter-specific, separate from six tools."""
    if (not isinstance(record, dict) or set(record) != set(SEALED_MTEST_MATH_BINDING) or
            type(record.get("size_bytes")) is not int or
            any(type(record.get(key)) is not str for key in ("loaded_path", "resolved_path", "sha256")) or
            record != SEALED_MTEST_MATH_BINDING):
        raise ValueError("Actual installed tfel.math converter binding differs from its exact sealed identity")
    return deepcopy(record)


def capture_mtest_math_binding(module):
    """Read actual loaded bytes after importing the installed converter module."""
    loaded = Path(module.__file__)
    resolved = loaded.resolve(strict=True)
    if not resolved.is_file():
        raise ValueError("Actual installed tfel.math converter binding is not a file")
    return checked_mtest_math_binding({"loaded_path": str(loaded), "resolved_path": str(resolved),
        "size_bytes": resolved.stat().st_size, "sha256": sha256(resolved)})


def _mtest_native_vector(value, size, label):
    values = list(value)
    if (len(values) != size or any(type(x) not in (int, float) or not math.isfinite(x) for x in values)):
        raise ValueError(label + " requires complete finite actual native vector components")
    return [float(x) for x in values]


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 ** 2), b""):
            h.update(block)
    return h.hexdigest()


def save(path, value):
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    limit = MAX_RAW_BYTES if Path(path).name in ("native_raw.json", "mgis.partial.json", "mtest.partial.json") else MAX_FILE_BYTES
    if len(text.encode("utf-8")) > limit:
        raise ValueError("Native artifact exceeds its predeclared byte budget")
    Path(path).write_text(text, encoding="utf-8")


def state_hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _checked_module(path, expected, name):
    path = Path(path)
    if (not isinstance(expected, str) or re.fullmatch("[0-9a-f]{64}", expected) is None or
            path.is_symlink() or not path.is_file() or sha256(path) != expected):
        raise ValueError("Captured helper source is missing, linked or differs from the selected exact digest")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if sha256(path) != expected:
        raise ValueError("Captured helper source changed while loading")
    return module


def _transport(expected=None, *, output=None):
    path = Path(__file__).with_name("mfront_material_worker.py") if __package__ else Path(output or "/work") / "mfront_material_worker.py"
    actual = sha256(path)
    if (actual not in TRANSPORT_VARIANTS or path.stat().st_size != TRANSPORT_VARIANTS[actual] or
            expected is not None and actual != expected):
        raise ValueError("Original transport is not the selected exact reviewed LF/CRLF source")
    return _checked_module(path, actual, "captured_material_transport")


def _compiler_helper(expected, *, output=None):
    path = Path(__file__).with_name(COMPILER_HELPER_NAME) if __package__ else Path(output or "/work") / COMPILER_HELPER_NAME
    return _checked_module(path, expected, "captured_viscoelastic_compiler_evidence")


def native_preflight(settings):
    """Native-specific representability, without a scientific minimum dt."""
    tau = settings["material"]["relaxation_time_s"]
    for previous, entry in zip(settings["history"], settings["history"][1:]):
        dt = entry["time_s"] - previous["time_s"]
        ratio = dt / tau
        if not math.isfinite(dt) or dt <= 0 or not math.isfinite(ratio) or ratio <= 0:
            raise ValueError("Native dt/tau is zero or nonfinite in binary64; native representability is unqualified")
    return settings


def resource_limits(budgets):
    return {"threads": 1, "address_space_bytes": 4 * 1024 ** 3,
            "cpu_seconds": budgets["solver_time_seconds"],
            "timeout_seconds": budgets["subprocess_timeout_seconds"],
            "maximum_single_artifact_bytes": MAX_FILE_BYTES,
            "maximum_raw_bytes": MAX_RAW_BYTES, "maximum_history_states": 32}


def assert_captures(output, policy):
    pins = policy.get("source_files")
    required = {"caelab/adapters/mfront_viscoelastic.py", "caelab/adapters/mfront_viscoelastic_worker.py",
        "caelab/adapters/mfront_single_branch_maxwell.mfront", "plugins/material_point/viscoelastic_reference.py",
        "caelab/adapters/mfront_material.py", TRANSPORT_KEY, "plugins/material_point/reference.py",
        "plugins/material_point/inverse_reference.py", "caelab/adapters/mfront_inverse.py",
        "caelab/adapters/mfront_inverse_runtime_probe.py", COMPILER_HELPER_KEY,
        "caelab/adapters/codeaster_elasticity.py", "caelab/adapters/codeaster_execution.py", "caelab/execution_control.py"}
    if not isinstance(pins, dict) or set(pins) != required or len({Path(name).name for name in pins}) != len(pins):
        raise ValueError("Complete unique source inventory is required")
    inventory_path = Path(output) / "source_inventory.json"
    if (inventory_path.is_symlink() or not inventory_path.is_file() or
            state_hash(json.loads(inventory_path.read_text())) != state_hash(pins) or
            policy.get("domain_sha256") != pins["plugins/material_point/viscoelastic_reference.py"] or
            sha256(__file__) != pins["caelab/adapters/mfront_viscoelastic_worker.py"]):
        raise ValueError("Actual inventory/Domain/worker source binding differs from the frozen policy")
    # The older physical reference intentionally has a distinct capture name.
    for key, digest in pins.items():
        name = "elastic_reference.py" if key == "plugins/material_point/reference.py" else Path(key).name
        path = Path(output) / name
        if (path.is_symlink() or not path.is_file() or not isinstance(digest, str) or
                re.fullmatch("[0-9a-f]{64}", digest) is None or sha256(path) != digest):
            raise ValueError("Captured exact source inventory drifted")
    actual_transport = pins.get(TRANSPORT_KEY)
    if (actual_transport not in TRANSPORT_VARIANTS or policy.get("transport_sha256") != actual_transport or
            (Path(output) / "mfront_material_worker.py").stat().st_size != TRANSPORT_VARIANTS[actual_transport]):
        raise ValueError("Frozen policy does not bind the actual selected transport source")
    if policy.get("compiler_helper_sha256") != pins.get(COMPILER_HELPER_KEY):
        raise ValueError("Frozen policy does not bind the actual compiler classifier source")
    return pins


def _values(array):
    values = [float(x) for x in array.reshape(-1)]
    if any(not math.isfinite(x) for x in values):
        raise ValueError("Native array contains nonfinite observations")
    return values


def _physical(v):
    return list(v[:3]) + [x / math.sqrt(2.) for x in v[3:]]


def _kelvin(v):
    return list(v[:3]) + [x * math.sqrt(2.) for x in v[3:]]


def validate_descriptor(binding, behaviour):
    if behaviour.hypothesis != binding.Hypothesis.Tridimensional:
        raise ValueError("Trusted behavior requires exactly the 3D hypothesis")
    descriptor = {key: str(getattr(behaviour, key)) for key in
                  ("behaviour", "function", "source", "hypothesis", "tfel_version", "btype", "kinematic", "symmetry", "build_id")}
    descriptor.update({key: [v.name for v in getattr(behaviour, key)] for key in
        ("gradients", "thermodynamic_forces", "material_properties", "internal_state_variables", "external_state_variables")})
    descriptor["internal_state_variable_sizes"] = [int(binding.getVariableSize(v, behaviour.hypothesis)) for v in behaviour.internal_state_variables]
    descriptor["gradient_size"] = int(binding.getArraySize(behaviour.gradients, behaviour.hypothesis))
    descriptor["force_size"] = int(binding.getArraySize(behaviour.thermodynamic_forces, behaviour.hypothesis))
    descriptor["computes_stored_energy"] = bool(behaviour.computesStoredEnergy)
    descriptor["computes_dissipated_energy"] = bool(behaviour.computesDissipatedEnergy)
    if (descriptor["behaviour"] != BEHAVIOUR or descriptor["hypothesis"] != "TRIDIMENSIONAL" or
            descriptor["material_properties"] != PROPERTY_NAMES or descriptor["external_state_variables"] != ["Temperature"] or
            descriptor["internal_state_variables"] != ["BranchStress"] or descriptor["internal_state_variable_sizes"] != [6] or
            descriptor["gradient_size"] != 6 or descriptor["force_size"] != 6 or
            not descriptor["computes_stored_energy"] or not descriptor["computes_dissipated_energy"]):
        raise ValueError("Full branch-state and both native energy capabilities are mandatory")
    return descriptor


class ManagerHandle:
    """Keep actual native-bound property/temperature arrays alive with their manager."""
    def __init__(self, manager, property_buffers, external_buffers):
        self.manager = manager
        self.property_buffers = property_buffers
        self.external_buffers = external_buffers


def clone_manager(binding, behaviour, np, properties, temperature, baseline=None):
    if not behaviour.computesStoredEnergy or not behaviour.computesDissipatedEnergy:
        raise ValueError("Native energy descriptors must be enabled before touching getters")
    if set(properties) != set(PROPERTY_NAMES) or any(type(x) not in (int, float) or not math.isfinite(x) or x <= 0 for x in properties.values()):
        raise ValueError("Exactly five finite positive trusted material properties are required")
    if type(temperature) not in (int, float) or not math.isfinite(temperature) or temperature <= 0:
        raise ValueError("Finite positive temperature is required")
    if baseline is not None:
        if not isinstance(baseline, dict) or set(baseline) != {"s0", "s1", "tangent_cache_kelvin_mpa", "dt_s", "metadata"}:
            raise ValueError("Complete full baseline manager is required")
        for label in ("s0", "s1"):
            if baseline[label]["shapes"] != EXPECTED_SHAPES:
                raise ValueError("Baseline buffer shapes changed")
            if baseline[label]["material_properties"] != {k: [v] for k, v in properties.items()} or baseline[label]["external_state_variables"] != {"Temperature": [temperature]}:
                raise ValueError("Baseline actual properties/temperature changed")
        cache = baseline["tangent_cache_kelvin_mpa"]
        if not isinstance(cache, list) or len(cache) != 6 or any(not isinstance(row, list) or len(row) != 6 for row in cache) or any(type(x) not in (int, float) or not math.isfinite(x) for row in cache for x in row):
            raise ValueError("Complete finite native tangent baseline is required")
    manager = binding.MaterialDataManager(behaviour, 1)
    manager.allocateArrayOfTangentOperatorBlocks()
    if list(manager.K.shape) != [1, 6, 6] or manager.K.size != 36:
        raise ValueError("Complete native tangent cache is required")
    props, external = {}, {}
    for label, state in (("s0", manager.s0), ("s1", manager.s1)):
        props[label] = {}
        for name, value in properties.items():
            array = np.array([value], dtype=np.float64)
            if baseline is not None:
                array[:] = baseline[label]["material_properties"][name]
            binding.setMaterialProperty(state, name, array, binding.MaterialStateManagerStorageMode.EXTERNAL_STORAGE)
            props[label][name] = array
        array = np.array([temperature], dtype=np.float64)
        if baseline is not None:
            array[:] = baseline[label]["external_state_variables"]["Temperature"]
        binding.setExternalStateVariable(state, "Temperature", array, binding.MaterialStateManagerStorageMode.EXTERNAL_STORAGE)
        external[label] = {"Temperature": array}
        for attribute, saved in ARRAYS.items():
            array = getattr(state, attribute)
            if list(array.shape) != EXPECTED_SHAPES[saved] or array.size != (1 if "energies" in saved else 6):
                raise ValueError("Native buffer shape/size differs from complete 3D single-branch declaration")
            values = baseline[label][saved] if baseline is not None else [0.] * array.size
            if len(values) != array.size or any(type(x) not in (int, float) or not math.isfinite(x) for x in values):
                raise ValueError("Complete finite baseline buffers are required")
            array.reshape(-1)[:] = values
    manager.K.reshape(6, 6)[:, :] = baseline["tangent_cache_kelvin_mpa"] if baseline is not None else 0.
    # Each clone owns every state/cache/property/temperature buffer. Equal
    # contents must not hide shared native memory between s0 and s1 or clones.
    owned = [manager.K]
    for label, state in (("s0", manager.s0), ("s1", manager.s1)):
        owned.extend(getattr(state, name) for name in ARRAYS)
        owned.extend(props[label].values())
        owned.extend(external[label].values())
    if any(np.shares_memory(a, b) for i, a in enumerate(owned) for b in owned[i + 1:]):
        raise ValueError("Independent owned native state/cache/property/temperature buffers are required")
    return ManagerHandle(manager, props, external)


def snapshot_manager(handle, dt):
    manager = handle.manager
    result = {}
    for label, state in (("s0", manager.s0), ("s1", manager.s1)):
        arrays, shapes = {}, {}
        for native, saved in ARRAYS.items():
            array = getattr(state, native)
            shapes[saved] = list(array.shape)
            if shapes[saved] != EXPECTED_SHAPES[saved] or str(array.dtype) != "float64":
                raise ValueError("Native buffer shape drifted")
            arrays[saved] = _values(array)
        result[label] = {**arrays, "material_properties": {key: _values(value) for key, value in handle.property_buffers[label].items()},
            "external_state_variables": {key: _values(value) for key, value in handle.external_buffers[label].items()}, "shapes": shapes}
    if list(manager.K.shape) != [1, 6, 6]:
        raise ValueError("Native tangent cache shape drifted")
    result.update(tangent_cache_kelvin_mpa=[_values(row) for row in manager.K.reshape(6, 6)], dt_s=float(dt),
        metadata={"tangent_cache_shape": list(manager.K.shape), "native_dtype": str(manager.K.dtype), "integration_points": int(manager.n), "gradient_stride": int(manager.s0.gradients_stride),
            "force_stride": int(manager.s0.thermodynamic_forces_stride), "isv_stride": int(manager.s0.internal_state_variables.strides[0] // manager.s0.internal_state_variables.itemsize),
            "property_storage": "EXTERNAL_STORAGE_owned_arrays", "temperature_storage": "EXTERNAL_STORAGE_owned_array",
            "computes_stored_energy": True, "computes_dissipated_energy": True,
            "speed_of_sound": "NOT_REQUESTED", "native_copy_policy": "fresh_independent_full_buffers"})
    return result


def observation(handle, time):
    state = handle.manager.s1
    strain, stress, q = (_values(getattr(state, name)) for name in
                         ("gradients", "thermodynamic_forces", "internal_state_variables"))
    se, de = _values(state.stored_energies), _values(state.dissipated_energies)
    if len(strain) != 6 or len(stress) != 6 or len(q) != 6 or len(se) != 1 or len(de) != 1:
        raise ValueError("Complete native stress/q and energy observations are required")
    return {"time_s": float(time), "gradients_kelvin": strain, "strain_physical": _physical(strain),
            "stress_kelvin_mpa": stress, "stress_physical_mpa": _physical(stress),
            "branch_stress_kelvin_mpa": q, "branch_stress_physical_mpa": _physical(q),
            "stored_energy_mpa": se[0], "dissipated_energy_mpa": de[0]}


def integrate_history(binding, behaviour, settings, library_sha, output, np, transport=None):
    transport = transport or _transport()
    properties = dict(zip(PROPERTY_NAMES, (settings["material"][key] for key in MATERIAL_KEYS)))
    temperature = settings["temperature_k"]
    initial = clone_manager(binding, behaviour, np, properties, temperature)
    baseline = snapshot_manager(initial, 0.)
    result = {"library_sha256": library_sha, "material_properties": properties,
              "external_state_variables": {"Temperature": temperature}, "initial_manager": deepcopy(baseline),
              "initial": observation(initial, 0.), "steps": []}
    for index, entry in enumerate(settings["history"][1:], 1):
        dt = entry["time_s"] - settings["history"][index - 1]["time_s"]
        if not dt > 0:
            raise ValueError("Native increments must have strictly positive dt")
        baseline = {**deepcopy(baseline), "dt_s": dt}
        nominal = clone_manager(binding, behaviour, np, properties, temperature, baseline)
        start = snapshot_manager(nominal, dt)
        nominal.manager.s1.gradients[0, :] = _kelvin(entry["strain"])
        integration = transport._integrate(binding, nominal.manager, dt)
        record = {**observation(nominal, entry["time_s"]), **integration, "initial_manager": start,
                  "initial_state_sha256": state_hash(start),
                  "tangent_kelvin_mpa": [_values(row) for row in nominal.manager.K.reshape(6, 6)],
                  "nominal_before_probes": snapshot_manager(nominal, dt), "finite_differences": []}
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
                    probe = clone_manager(binding, behaviour, np, properties, temperature, baseline)
                    probe_start = snapshot_manager(probe, dt)
                    probe.manager.s1.gradients[0, :] = nominal.manager.s1.gradients[0, :]
                    probe.manager.s1.gradients[0, column] += sign * h
                    integration = transport._integrate(binding, probe.manager, dt)
                    final = snapshot_manager(probe, dt)
                    item = {**observation(probe, entry["time_s"]), **integration, "column": column, "sign": sign,
                            "initial_manager": probe_start, "initial_state_sha256": state_hash(probe_start),
                            "final_manager": final, "final_state_sha256": state_hash(final)}
                    probes.append(item)
                    signed[sign] = item["stress_kelvin_mpa"]
                    if integration["integration_return"] != 1:
                        result["native_rejection"] = {"phase": "finite_difference", "step": index, "h": h,
                            "column": column, "sign": sign, **integration}
                        record["finite_differences"].append({"h": h, "probes": probes})
                        result["steps"].append(record)
                        save(output / "mgis.partial.json", result)
                        return result
                columns.append([(a - b) / (2 * h) for a, b in zip(signed[1], signed[-1])])
            record["finite_differences"].append({"h": h, "probes": probes,
                "tangent_kelvin_mpa": [[columns[j][i] for j in range(6)] for i in range(6)]})
        record["nominal_after_probes"] = snapshot_manager(nominal, dt)
        result["steps"].append(record)
        save(output / "mgis.partial.json", result)
        if record["nominal_after_probes"] != record["nominal_before_probes"]:
            raise ValueError("Independent probes changed the successful nominal state/cache")
        binding.update(nominal.manager)
        baseline = snapshot_manager(nominal, dt)
        record["nominal_after_update"] = deepcopy(baseline)
        record["nominal_after_update_sha256"] = state_hash(baseline)
        # Save the actual commit even for the final increment, and also retain
        # malformed update evidence before refusing it. No K is manufactured.
        save(output / "mgis.partial.json", result)
        if (baseline["s0"] != baseline["s1"] or baseline["s1"] != record["nominal_after_probes"]["s1"] or
                any(baseline[key] != record["nominal_after_probes"][key] for key in ("dt_s", "metadata")) or
                any(value != 0. for row in baseline["tangent_cache_kelvin_mpa"] for value in row)):
            raise ValueError("Native commit did not advance the complete reliable nominal state")
    return result


def parse_mtest_table(path, states):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_RAW_BYTES:
        raise ValueError("Actual MTest output table is absent/unbounded")
    headers, rows = {}, []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        if line.startswith("#"):
            first = re.fullmatch(r"#\s*first\s+column:\s*time\s*", line)
            match = re.fullmatch(r"#\s*(\d+)\s+column:\s*(.+)", line)
            if first:
                index, description = 1, "time"
            elif match:
                index, description = int(match.group(1)), match.group(2).strip()
            else:
                raise ValueError("MTest output includes an unsupported native header")
            if index in headers:
                raise ValueError("Duplicate native MTest output column")
            headers[index] = description
        else:
            tokens = line.split()
            if len(tokens) != 21:
                raise ValueError("Native MTest output requires exactly 21 columns")
            row = [float(x) for x in tokens]
            if any(not math.isfinite(x) for x in row):
                raise ValueError("Nonfinite native MTest output")
            rows.append(row)
    if (set(headers) != set(range(1, 22)) or headers[1] != "time" or headers[20] != "stored energy" or
            headers[21] != "disspated energy" or any("strain" not in headers[i] for i in range(2, 8)) or
            any("stress" not in headers[i] for i in range(8, 14)) or
            any("BranchStress" not in headers[i] for i in range(14, 20)) or len(rows) != len(states)):
        raise ValueError("Pinned MTest time/tensor/q/native-energy header/count contract changed")
    for row, state in zip(rows, states):
        u0 = _mtest_native_vector(state.get("global_u0", []), 12, "MTest global u0")
        u1 = _mtest_native_vector(state.get("global_u1", []), 12, "MTest global u1")
        s0 = _mtest_native_vector(state.get("committed_s0_kelvin_mpa", []), 6, "MTest committed s0")
        iv0 = _mtest_native_vector(state.get("committed_iv0", []), 6, "MTest committed iv0")
        if (u0 != u1 or s0 != state["stress_kelvin_mpa"] or iv0 != state["internal_state_variables"] or
                row[0] != state["time_s"] or row[1:7] != u0[:6] or
                row[7:13] != s0 or row[13:19] != iv0):
            raise ValueError("Actual MTest table disagrees with ordered native state buffers")
        state["stored_energy_mpa"], state["dissipated_energy_mpa"] = row[19:21]
    return {"artifact": "mtest.res", "sha256": sha256(path), "rows": len(rows), "column_count": 21,
            "stored_energy_column": 20, "dissipated_energy_column": 21,
            "columns": {str(k): v for k, v in headers.items()},
            "source_commit": TFEL_COMMIT, "method": "Actual pinned MTest printOutput cs.se0/cs.de0",
            "buffer_mapping": deepcopy(MTEST_TABLE_MAPPING)}


def mtest_history(module, library, settings, output):
    library_sha = sha256(library)
    test = module.MTest()
    test.setModellingHypothesis("Tridimensional")
    test.setBehaviour("generic", str(library), BEHAVIOUR)
    test.setMaximumNumberOfSubSteps(MTEST_LIMITS["substep_limit"])
    test.setMaximumNumberOfIterations(MTEST_LIMITS["iteration_limit"])
    test.setStrainEpsilon(MTEST_LIMITS["strain_epsilon"])
    test.setStressEpsilon(MTEST_LIMITS["stress_epsilon_mpa"])
    properties = dict(zip(PROPERTY_NAMES, (settings["material"][key] for key in MATERIAL_KEYS)))
    for name, value in properties.items():
        test.setMaterialProperty(name, value)
    test.setExternalStateVariable("Temperature", settings["temperature_k"])
    imposed = [{"time_s": row["time_s"], "gradients_kelvin": _kelvin(row["strain"])}
               for row in settings["history"]]
    for column, name in enumerate(MTEST_COMPONENTS):
        test.setImposedStrain(name, {row["time_s"]: row["gradients_kelvin"][column] for row in imposed})
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
              **deepcopy(MTEST_LIMITS), "imposed_components": list(MTEST_COMPONENTS),
              "imposed_interpolation": "piecewise_linear", "imposed_history": deepcopy(imposed),
              "buffer_mapping": deepcopy(MTEST_BUFFER_MAPPING), "states": []}
    def retain(time, iterations_before):
        gradients, forces, q = (_mtest_native_vector(v, 6, "MTest actual e1/s1/iv1")
                                for v in (state.e1, state.s1, state.iv1))
        u0, u1 = (_mtest_native_vector(v, 12, "MTest actual six gradients plus six multipliers")
                  for v in (state.u0, state.u1))
        e0, s0, iv0 = (_mtest_native_vector(v, 6, "MTest actual prepared/committed e0/s0/iv0")
                       for v in (state.e0, state.s0, state.iv0))
        if type(state.iterations) is not int or type(state.subSteps) is not int:
            raise ValueError("Actual native cumulative iteration/substep counters are required")
        iterations_after = state.iterations
        result["states"].append({"time_s": float(time), "state_phase": "INITIAL_UNPREPARED" if time == 0 else "INTEGRATED",
            "gradients_kelvin": gradients, "strain_physical": _physical(gradients),
            "stress_kelvin_mpa": forces, "stress_physical_mpa": _physical(forces),
            "branch_stress_kelvin_mpa": q, "branch_stress_physical_mpa": _physical(q), "internal_state_variables": q,
            "properties_native": [float(x) for x in state.mprops1],
            "external_state_variables_native": [float(x) for x in state.evs0],
            "iterations": int(state.iterations), "substeps": int(state.subSteps),
            "iterations_before": iterations_before, "iterations_after": iterations_after,
            "iterations_increment": iterations_after - iterations_before,
            "buffer_phase": "INITIAL_UNPREPARED" if time == 0 else "AFTER_EXECUTE_COMMIT",
            "global_u0": u0, "global_u1": u1, "prepared_e0_kelvin": e0,
            "committed_s0_kelvin_mpa": s0, "committed_iv0": iv0})
        test.printOutput(time, state)
        save(output / "mtest.partial.json", result)
    retain(0., 0)
    for previous, entry in zip(settings["history"], settings["history"][1:]):
        if type(state.iterations) is not int:
            raise ValueError("Actual native cumulative iteration counter is required before execute")
        iterations_before = state.iterations
        test.execute(state, workspace, previous["time_s"], entry["time_s"])
        retain(entry["time_s"], iterations_before)
    if sha256(library) != library_sha:
        raise ValueError("Behavior binary drifted during MTest")
    # The CPython local MTest object closes/flushed its native output on return.
    # The caller reads the resulting real table; no invented Python energy fields.
    return result


def solve(input_path):
    import resource
    faulthandler.enable()
    input_path = Path(input_path).resolve()
    output = input_path.parent
    if output != Path("/work") or input_path.name != "input.json":
        raise ValueError("Fixed output-bound /work/input.json is required")
    if input_path.is_symlink() or input_path.stat().st_size > 128 * 1024:
        raise ValueError("Bounded original native input is required")
    policy = json.loads((output / "frozen_execution_policy.json").read_text())
    pins = assert_captures(output, policy)
    transport = _transport(policy["transport_sha256"], output=output)
    compiler_helper = _compiler_helper(policy["compiler_helper_sha256"], output=output)
    budgets = compiler_helper.validated_policy(policy["process_policy"])
    limits = resource_limits(budgets)
    if (policy.get("resource_limits") != limits or policy.get("behavior") != BEHAVIOUR or
            policy.get("native_interface") != "generic" or policy.get("native_hypothesis") != "Tridimensional" or
            state_hash(policy.get("mtest_limits")) != state_hash(MTEST_LIMITS) or
            state_hash(policy.get("mtest_buffer_mapping")) != state_hash(MTEST_BUFFER_MAPPING) or
            state_hash(policy.get("mtest_table_mapping")) != state_hash(MTEST_TABLE_MAPPING) or
            state_hash(policy.get("extra_native_bindings")) != state_hash({"tfel_math": SEALED_MTEST_MATH_BINDING}) or
            policy.get("compiler_policy") != transport.COMPILER_POLICY):
        raise ValueError("Frozen native execution/resource/driver policy changed")
    resource.setrlimit(resource.RLIMIT_AS, (limits["address_space_bytes"],) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (budgets["solver_time_seconds"],) * 2)
    resource.setrlimit(resource.RLIMIT_FSIZE, (limits["maximum_single_artifact_bytes"],) * 2)
    os.umask(0o077)
    domain_path = output / "viscoelastic_reference.py"
    if sha256(domain_path) != policy["domain_sha256"]:
        raise ValueError("Captured validation plugin source changed")
    domain = _checked_module(domain_path, policy["domain_sha256"], "captured_viscoelastic_domain")
    settings = native_preflight(domain.validate_settings(json.loads(input_path.read_text())))
    if policy.get("settings_sha256") != state_hash(settings) or policy.get("limits") != settings["limits"]:
        raise ValueError("Frozen settings/limits differ from the original input")
    wall = budgets["subprocess_timeout_seconds"]
    source = output / SOURCE_NAME
    if sha256(source) != SOURCE_SHA256:
        raise ValueError("Trusted Maxwell behavior source changed before compiler")
    reference_source = Path(TFEL_PREFIX) / "share/doc/mfront/tests/behaviours/GeneralizedMaxwell.mfront"
    if sha256(reference_source) != REFERENCE_SOURCE_SHA256:
        raise ValueError("Installed upstream Maxwell reference source differs from pinned official bytes")
    shutil.copyfile(reference_source, output / "upstream_GeneralizedMaxwell.mfront")
    build = output / "build"
    build.mkdir(exist_ok=False)
    shutil.copyfile(source, build / SOURCE_NAME)
    licenses = output / "licenses"
    licenses.mkdir(exist_ok=False)
    license_records = []
    for name in ("LICENCE-GNU-GPL", "LICENCE-CECILL-A-EN", "LICENCE-CECILL-A-FR"):
        path = Path(TFEL_PREFIX) / "share/doc/tfel" / name
        if not path.is_file() or path.stat().st_size > 1024 ** 2:
            raise ValueError("Installed TFEL license evidence is absent/unbounded")
        shutil.copyfile(path, licenses / name)
        license_records.append({"name": name, "sha256": sha256(path), "artifact": "licenses/" + name})
    save(output / "source_attribution.json", {"reference_author": "Benoit Bary", "reference_commit": TFEL_COMMIT,
        "reference_url": REFERENCE_SOURCE_URL, "reference_sha256": REFERENCE_SOURCE_SHA256,
        "adaptation": "One exact-exponential Maxwell branch plus consistent tangent/native energy hooks",
        "source_sha256": SOURCE_SHA256, "installed_tfel_license_files": license_records,
        "binary_upstream_commit": "UNKNOWN", "corporate_license_security_approval": "UNKNOWN"})
    mfront, compiler, make, config = (transport._executable(name) for name in ("mfront", "g++", "make", "tfel-config"))
    runtime = {"python": platform.python_version(), "tfel": transport._command([config, "--version"], output, "tfel_version", wall),
        "mfront": transport._command([mfront, "--version"], output, "mfront_version", wall),
        "compiler": transport._command([compiler, "--version"], output, "compiler_version", wall),
        "make": transport._command([make, "--version"], output, "make_version", wall),
        "process_policy": deepcopy(budgets), "resource_limits": deepcopy(limits),
        "tfel_cxx_standard": transport._command([config, "--cxx-standard"], output, "cxx_standard", wall),
        "tfel_recommended_oflags0": transport._command([config, "--oflags0"], output, "tfel_oflags0", wall),
        "tfel_cpp_compiler_flags": transport._command([config, "--cppflags", "--compiler-flags"], output, "tfel_cpp_flags", wall),
        "tfel_include_path": transport._command([config, "--include-path"], output, "tfel_include_path", wall),
        "executables": {name: {"path": path, "sha256": sha256(path)} for name, path in
            (("mfront", mfront), ("mtest", transport._executable("mtest")), ("compiler", compiler), ("make", make), ("tfel_config", config))}}
    import numpy as np
    import mgis.behaviour as binding
    import tfel
    import tfel.math
    math_binding = capture_mtest_math_binding(tfel.math)
    import mtest
    mgis_package = transport.installed_package_identity(MGIS_PREFIX, "mgis", "3.0", binding.__file__, output)
    tfel_package = transport.installed_package_identity(TFEL_PREFIX, "tfel", "5.0.0", mtest._mtest.__file__, output)
    runtime.update(numpy=np.__version__, mgis=mgis_package["version"], mgis_package=mgis_package, tfel_package=tfel_package,
        mgis_binding_sha256=sha256(binding.__file__), mtest_binding_sha256=sha256(mtest._mtest.__file__),
        mgis_binding_path=binding.__file__, mtest_binding_path=mtest._mtest.__file__,
        extra_native_bindings={"tfel_math": math_binding})
    save(output / "runtime.json", runtime)
    sealed = policy["sealed_installed_native_binaries"]
    for name, field in (("mgis_binding", "mgis_binding_sha256"), ("mtest_binding", "mtest_binding_sha256")):
        if runtime[field] != sealed[name]["sha256"]:
            raise ValueError("Actual loaded native binding changed before compiler execution")
    for name in ("compiler", "mfront", "mtest", "tfel_config"):
        if runtime["executables"][name]["sha256"] != sealed[name]["sha256"]:
            raise ValueError("Actual native tool changed before compiler execution")
    transport._command([mfront, *BUILD_ARGUMENTS], build, "generate", wall)
    flags = transport.portable_compiler_flags(runtime["tfel_recommended_oflags0"], runtime["tfel_cpp_compiler_flags"], runtime["tfel_include_path"])
    transport._command([make, "-C", "src", "-f", "Makefile.mfront", "-j1", "--trace",
        "CXX=" + compiler, "CXXFLAGS=" + shlex.join(flags)], build, "compile", wall)
    compile_log = build / "compile.stdout.log"
    if compile_log.is_symlink() or not compile_log.is_file() or not 0 < compile_log.stat().st_size <= MAX_FILE_BYTES:
        raise ValueError("Original compiler log is absent/linked/unbounded")
    command_records = compiler_helper.compiler_command_evidence(
        compile_log.read_text(encoding="utf-8"), compiler, flags, behaviour=BEHAVIOUR)
    commands = [record["command"] for record in command_records]
    library = build / "src/libBehaviour.so"
    if not library.is_file() or not library.stat().st_size:
        raise ValueError("Fixed trusted library generation failed")
    library_sha = sha256(library)
    makefile = build / "src/Makefile.mfront"
    transport._command([transport._executable("ldd"), str(library)], output, "library_dependencies", wall)
    dependency_log = output / "library_dependencies.stdout.log"
    if dependency_log.is_symlink() or not dependency_log.is_file() or not 0 < dependency_log.stat().st_size <= MAX_FILE_BYTES:
        raise ValueError("Original dependency log is absent/linked/unbounded")
    dependency_hashes = {}
    for path in compiler_helper.library_dependency_paths(dependency_log.read_text(encoding="utf-8")):
        if not Path(path).is_file():
            raise ValueError("Actual generated library dependency is absent")
        dependency_hashes[path] = sha256(path)
    save(output / "build_identity.json", {"library_path": "build/src/libBehaviour.so", "library_sha256": library_sha,
        "source_sha256": SOURCE_SHA256, "generation_arguments": BUILD_ARGUMENTS,
        "makefile_sha256": sha256(makefile),
        "compiler_flags_makefile": [line for line in makefile.read_text().splitlines() if any(key in line for key in ("CXXFLAGS", "CPPFLAGS", "LDFLAGS", "CXX", "INCLUDES", "-std="))],
        "actual_compiler_commands": commands, "compiler_flags_policy": transport.COMPILER_POLICY,
        "compiler_flags_override": flags, "dependency_sha256": dependency_hashes,
        "compiler_commands_artifact": "build/compile.stdout.log", "compiler_commands_sha256": sha256(compile_log),
        "compiler_command_policy": compiler_helper.COMPILER_COMMAND_POLICY,
        "compiler_command_evidence": command_records, "compiler_helper_sha256": policy["compiler_helper_sha256"],
        "dependency_artifact": "library_dependencies.stdout.log", "dependency_artifact_sha256": sha256(dependency_log)})
    behaviour = binding.load(str(library), BEHAVIOUR, binding.Hypothesis.Tridimensional)
    descriptor = validate_descriptor(binding, behaviour)
    raw = {"schema_version": "1", "input_sha256": sha256(input_path), "worker_sha256": sha256(__file__),
        "source_sha256": SOURCE_SHA256, "transport_sha256": policy["transport_sha256"], "library_sha256": library_sha,
        "compiler_helper_sha256": policy["compiler_helper_sha256"], "source_files": deepcopy(pins),
        "process_policy": deepcopy(budgets), "resource_limits": deepcopy(limits),
        "runtime": runtime, "extra_native_bindings": {"tfel_math": deepcopy(math_binding)},
        "behaviour_description": descriptor,
        "conventions": {"physical": "xx,yy,zz,xy,xz,yz", "native": "xx,yy,zz,sqrt2*xy,sqrt2*xz,sqrt2*yz",
                        "strain": "infinitesimal_tensor_not_engineering_shear", "stress_unit": "MPa",
                        "energy_unit": "MPa = MJ/m^3 per reference volume"}}
    save(output / "native.partial.json", raw)
    try:
        raw["mgis"] = integrate_history(binding, behaviour, settings, library_sha, output, np, transport)
        if "native_rejection" in raw["mgis"]:
            raw["native_rejection"] = raw["mgis"]["native_rejection"]
        else:
            raw["mtest"] = mtest_history(mtest, library, settings, output)
            raw["mtest"]["native_output_table"] = parse_mtest_table(output / "mtest.res", raw["mtest"]["states"])
            save(output / "mtest.partial.json", raw["mtest"])
        assert_captures(output, policy)
        if capture_mtest_math_binding(tfel.math) != math_binding:
            raise ValueError("Actual installed tfel.math converter binding changed during native execution")
        if (sha256(source) != SOURCE_SHA256 or sha256(library) != library_sha or
                sha256(input_path) != raw["input_sha256"] or sha256(__file__) != raw["worker_sha256"]):
            raise ValueError("Native source/input/worker/library identity drifted")
        save(output / "native_raw.json", raw)
    except BaseException as error:
        raw["execution_failure"] = {"type": type(error).__name__, "message": str(error),
                                    "numerical_verdict": "UNKNOWN"}
        save(output / "native.partial.json", raw)
        raise



if __name__ == "__main__":
    solve("/work/input.json")
