"""Read retained Maxwell channels, without executing or changing native results.

Tensor order, drivers, and actual timestamps belong here, not to the common
comparison layer. Analytical work is deliberately not exposed as native energy.
"""

from copy import deepcopy
import math


COMPONENTS = ("xx", "yy", "zz", "xy", "xz", "yz")


def _number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _vector(value, length):
    if not isinstance(value, list) or len(value) != length or not all(_number(v) for v in value):
        raise ValueError("Retained Maxwell history requires exact finite array dimensions")
    return value


def channels(result, settings, raw, artifact):
    """Project verified, valid native metrics onto their recorded time axis."""
    if result["provenance"]["adapter"] != "material.mfront.viscoelastic":
        return []
    conventions = raw.get("conventions", {})
    if (conventions.get("physical") != "xx,yy,zz,xy,xz,yz"
            or conventions.get("stress_unit") != "MPa"
            or conventions.get("strain") != "infinitesimal_tensor_not_engineering_shear"
            or conventions.get("energy_unit") != "MPa = MJ/m^3 per reference volume"):
        raise ValueError("Retained Maxwell physical conventions are missing or unsupported")
    mgis = raw["mgis"]
    rows = [mgis["initial"], *mgis["steps"]]
    times = [row["time_s"] for row in rows]
    if not 2 <= len(rows) <= 32 or not all(_number(t) for t in times) or times[0] != 0.:
        raise ValueError("Retained Maxwell requires its bounded native time history")
    if any(b <= a for a, b in zip(times, times[1:])):
        raise ValueError("Retained native time must increase strictly")
    if times != _vector([row["time_s"] for row in settings["history"]], len(times)):
        raise ValueError("Native time history differs from the declared model history")
    other = raw["mtest"]["states"]
    if _vector([row["time_s"] for row in other], len(times)) != times:
        raise ValueError("MGIS and MTest must retain their own matching recorded timestamps")
    available = []

    def metric(name):
        item = result["metrics"].get(name)
        if not isinstance(item, dict) or item.get("valid") is not True:
            return None
        if item.get("unit") != "MPa":
            raise ValueError("Retained native channel unit changed")
        return item

    def add(identifier, label, name, quantity, component, measure, values, driver, field, mapping):
        _vector(values, len(times))
        available.append({"id": identifier, "label": label, "metric": name,
            "quantity": quantity, "component": component, "measure": measure,
            "coordinate_frame": "Tridimensional model component basis; sensor/world alignment UNKNOWN", "location": "single homogeneous material point",
            "unit": "MPa", "axis": {"quantity": "time", "unit": "s", "values": list(times)},
            "values": list(values), "initial_state": {"index": 0, "kind": "UNPREPARED_INITIAL_CONDITION"},
            "origin": {"kind": "NATIVE", "driver": driver, "artifact": artifact["path"],
                       "sha256": artifact["sha256"], "native_field": field, "mapping": mapping}})

    for name, field, quantity, prefix, label, measure in (
        ("stress_history", "stress_physical_mpa", "stress", "stress", "응력", "infinitesimal Cauchy stress"),
        ("branch_stress_history", "branch_stress_physical_mpa", "branch_stress", "branch", "점탄성 분기 응력", "internal branch stress")):
        item = metric(name)
        if item is None:
            continue
        matrix = item["value"]
        if not isinstance(matrix, list) or len(matrix) != len(rows):
            raise ValueError("Recorded stress history length differs from native time")
        matrix = [_vector(row, 6) for row in matrix]
        native = [_vector(row[field], 6) for row in rows]
        if matrix != native:
            raise ValueError("Recorded physical stress history differs from its native observations")
        for index, component in enumerate(COMPONENTS):
            add(f"mgis-{prefix}-{component}", f"{label} {component} · MGIS", name, quantity, component,
                measure, [row[index] for row in matrix], "mgis", field, "RECORDED_PHYSICAL_COMPONENT")
    item = metric("native_energy_history")
    if item is not None:
        if item.get("drivers") != ["mgis", "mtest"] or item.get("components") != ["stored", "dissipated"]:
            raise ValueError("Native energy driver/component order must be explicit")
        matrices = item["value"]
        if not isinstance(matrices, list) or len(matrices) != 2:
            raise ValueError("Native energy requires the two recorded drivers")
        for driver_index, (driver, driver_rows) in enumerate((("mgis", rows), ("mtest", other))):
            matrix = matrices[driver_index]
            if not isinstance(matrix, list) or len(matrix) != len(times):
                raise ValueError("Native energy length differs from native time")
            matrix = [_vector(row, 2) for row in matrix]
            for index, (component, label) in enumerate((("stored", "저장 에너지 밀도"), ("dissipated", "소산 에너지 밀도"))):
                field = component + "_energy_mpa"
                values = [row[index] for row in matrix]
                if values != _vector([row[field] for row in driver_rows], len(times)):
                    raise ValueError("Recorded energy differs from the selected native driver")
                add(f"{driver}-{component}", f"{label} · {driver.upper()}", "native_energy_history",
                    component + "_energy_density", component, "reference-volume energy density", values,
                    driver, field, "NATIVE_SCALAR")
    return deepcopy(available)
