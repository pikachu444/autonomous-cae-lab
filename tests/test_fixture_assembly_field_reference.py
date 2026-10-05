"""Independent rational/manual controls; no native or engineering evidence."""

import copy
from decimal import Decimal
from fractions import Fraction
import importlib.util
import json
import math
from pathlib import Path
import sys
import unittest

_SOURCE = Path(__file__).resolve().parents[1] / "plugins/fixture_design/assembly_field_reference.py"
_SPEC = importlib.util.spec_from_file_location("_private_fixture_assembly_field_reference", _SOURCE)
reference = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(reference)

_MANUAL_SETTINGS = {
    "case": "fixture_assembly_affine_field_patch_v1",
    "intent": "SYNTHETIC_HOMOGENEOUS_ISOTROPIC_NUMERICAL_PATCH",
    "units": {"length": "mm", "force": "N", "stress": "MPa"},
    "components": ["printed_base", "printed_support_left", "printed_support_right",
                   "metal_roller_left", "metal_roller_right", "metal_loading_nose", "specimen"],
    "material": {"youngs_modulus_mpa": 2000.0, "poisson_ratio": 0.25,
                 "qualification": "HYPOTHETICAL_NOT_MEASURED"},
    "kinematics": {"gradient": [[1e-4, 4e-5, -5e-5], [-2e-5, -2e-4, 6e-5],
                               [9e-5, -8e-5, 3e-4]],
                   "translation_mm": [0.012, -0.007, 0.003]},
    "boundary": "AFFINE_ON_ALL_EXTERIOR_NODES_INTERIOR_FREE",
    "limits": {"displacement_absolute_mm": 1e-7, "stress_absolute_mpa": 1e-6,
               "mesh_volume_relative": 1e-8, "energy_relative": 1e-6,
               "force_balance_scaled": 1e-7, "moment_balance_scaled": 1e-7},
}


def _replace(settings, path, value):
    target = settings
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value


class AssemblyFieldReferenceTests(unittest.TestCase):
    def settings(self):
        return copy.deepcopy(_MANUAL_SETTINGS)

    def close(self, observed, expected):
        self.assertTrue(math.isclose(observed, float(expected), rel_tol=1e-14, abs_tol=1e-18),
                        f"{observed!r} differs from independent {expected!r}")

    def test_canonical_exact_frozen_json(self):
        actual = reference.canonical_settings()
        self.assertEqual(actual, _MANUAL_SETTINGS)
        self.assertEqual(json.loads(json.dumps(actual, allow_nan=False)), _MANUAL_SETTINGS)

    def test_canonical_every_mutable_branch_is_independent(self):
        first, second = reference.canonical_settings(), reference.canonical_settings()
        first["units"]["length"] = "m"
        first["components"].reverse()
        first["material"]["qualification"] = "MEASURED"
        first["kinematics"]["gradient"][0][1] = 99
        first["kinematics"]["translation_mm"][1] = 99
        first["limits"]["energy_relative"] = 1
        self.assertEqual(second, _MANUAL_SETTINGS)
        self.assertEqual(reference.canonical_settings(), _MANUAL_SETTINGS)

    def test_validation_normalizes_without_mutation_or_aliases(self):
        settings = self.settings()
        settings["material"]["youngs_modulus_mpa"] = 2000
        before = copy.deepcopy(settings)
        normalized = reference.validate_settings(settings)
        self.assertEqual(settings, before)
        self.assertIs(type(normalized["material"]["youngs_modulus_mpa"]), float)
        self.assertEqual(normalized, _MANUAL_SETTINGS)
        normalized["kinematics"]["gradient"][2][0] = 1
        normalized["kinematics"]["translation_mm"].clear()
        normalized["components"].clear()
        normalized["limits"].clear()
        normalized["units"].clear()
        normalized["material"].clear()
        self.assertEqual(settings, before)

    def test_validation_exact_keys_at_every_dictionary_level(self):
        for path in ((), ("units",), ("material",), ("kinematics",), ("limits",)):
            for change in ("omit", "extra"):
                with self.subTest(path=path, change=change):
                    settings = self.settings()
                    target = settings
                    for key in path:
                        target = target[key]
                    if change == "omit":
                        del target[next(iter(target))]
                    else:
                        target["frame"] = "implicit alternate frame"
                    before = copy.deepcopy(settings)
                    with self.assertRaises(ValueError):
                        reference.validate_settings(settings)
                    self.assertEqual(settings, before)

    def test_changed_case_units_material_kinematics_boundary_refused(self):
        changes = [(("case",), "another_case"), (("intent",), "PHYSICAL_FIXTURE"),
                   (("units", "length"), "m"), (("units", "force"), "N/m"),
                   (("units", "stress"), "Pa"),
                   (("material", "youngs_modulus_mpa"), 210000),
                   (("material", "poisson_ratio"), 0.3),
                   (("material", "qualification"), "MEASURED"),
                   (("kinematics", "gradient", 0, 1), -4e-5),
                   (("kinematics", "translation_mm", 2), 0.004),
                   (("boundary",), "ALL_VOLUME_NODES_FIXED")]
        for path, value in changes:
            with self.subTest(path=path):
                settings = self.settings()
                _replace(settings, path, value)
                with self.assertRaises(ValueError):
                    reference.validate_settings(settings)

    def test_all_six_limits_are_immutable(self):
        for name, value in _MANUAL_SETTINGS["limits"].items():
            with self.subTest(limit=name):
                settings = self.settings()
                settings["limits"][name] = math.nextafter(value, math.inf)
                with self.assertRaises(ValueError):
                    reference.validate_settings(settings)

    def test_active_identity_order_and_membership_are_frozen(self):
        names = _MANUAL_SETTINGS["components"]
        for variant in (list(reversed(names)), names[:-1], names + ["metal_bolt"],
                        [names[0]] * 7, tuple(names)):
            with self.subTest(variant=variant):
                settings = self.settings()
                settings["components"] = variant
                with self.assertRaises(ValueError):
                    reference.validate_settings(settings)

    def test_json_list_matrix_and_translation_shapes_are_exact(self):
        changes = [(("kinematics", "gradient"), tuple(_MANUAL_SETTINGS["kinematics"]["gradient"])),
                   (("kinematics", "gradient"), [[1e-4, 4e-5, -5e-5]] * 2),
                   (("kinematics", "gradient", 1), (-2e-5, -2e-4, 6e-5)),
                   (("kinematics", "gradient", 1), [-2e-5, -2e-4]),
                   (("kinematics", "gradient", 1), [-2e-5, -2e-4, 6e-5, 0]),
                   (("kinematics", "translation_mm"), (0.012, -0.007, 0.003)),
                   (("kinematics", "translation_mm"), [0.012, -0.007])]
        for path, value in changes:
            with self.subTest(path=path, value=value):
                settings = self.settings()
                _replace(settings, path, value)
                with self.assertRaises(ValueError):
                    reference.validate_settings(settings)

    def test_numeric_declarations_reject_non_json_and_nonfinite_values(self):
        bad_values = [True, False, "0.25", float("nan"), float("inf"), -float("inf"),
                      10 ** 1000, Decimal("0.25"), Fraction(1, 4), None, 0.25 + 0j]
        paths = [("material", "poisson_ratio"), ("kinematics", "gradient", 2, 0),
                 ("kinematics", "translation_mm", 0), ("limits", "energy_relative")]
        for path in paths:
            for value in bad_values:
                with self.subTest(path=path, value_type=type(value).__name__, value=repr(value)):
                    settings = self.settings()
                    _replace(settings, path, value)
                    with self.assertRaises(ValueError):
                        reference.validate_settings(settings)

    def test_settings_container_and_strings_are_real_json_types(self):
        class DictSubclass(dict):
            pass

        for value in (None, [], "settings", DictSubclass(self.settings())):
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaises(ValueError):
                    reference.validate_settings(value)
        settings = self.settings()
        settings["case"] = True
        with self.assertRaises(ValueError):
            reference.validate_settings(settings)

    def test_constitutive_all_six_signed_rational_components(self):
        actual = reference.constitutive_reference(self.settings())
        self.assertEqual(set(actual), {"strain6_tensor", "stress6_mpa", "lambda_mpa", "mu_mpa",
                                       "energy_density_mpa"})
        self.assertEqual(actual["lambda_mpa"], 800.0)
        self.assertEqual(actual["mu_mpa"], 800.0)
        epsilon = [Fraction(1, 10000), Fraction(-1, 5000), Fraction(3, 10000),
                   Fraction(1, 100000), Fraction(1, 50000), Fraction(-1, 100000)]
        sigma = [Fraction(8, 25), Fraction(-4, 25), Fraction(16, 25),
                 Fraction(2, 125), Fraction(4, 125), Fraction(-2, 125)]
        self.assertEqual(len(actual["strain6_tensor"]), 6)
        self.assertEqual(len(actual["stress6_mpa"]), 6)
        for index, (strain, stress) in enumerate(zip(epsilon, sigma)):
            with self.subTest(component=index):
                self.close(actual["strain6_tensor"][index], strain)
                self.close(actual["stress6_mpa"][index], stress)
        self.close(actual["energy_density_mpa"], Fraction(806, 6250000))

    def test_energy_uses_tensor_shear_factor_two(self):
        # Independent manual normal energy=800/6250000; shear contribution=6/6250000.
        energy = reference.constitutive_reference(self.settings())["energy_density_mpa"]
        self.close(energy - float(Fraction(800, 6250000)), Fraction(6, 6250000))
        self.assertFalse(math.isclose(energy, float(Fraction(803, 6250000)), rel_tol=1e-10))

    def test_displacement_independent_manual_points_and_translation(self):
        points = [([10, 20, 30], [Fraction(123, 10000), Fraction(-94, 10000), Fraction(113, 10000)]),
                  ([0, 0, 0], [Fraction(12, 1000), Fraction(-7, 1000), Fraction(3, 1000)]),
                  ([1, 0, 0], [Fraction(121, 10000), Fraction(-702, 100000), Fraction(309, 100000)]),
                  ([0, 1, 0], [Fraction(1204, 100000), Fraction(-72, 10000), Fraction(292, 100000)]),
                  ([0, 0, 1], [Fraction(1195, 100000), Fraction(-694, 100000), Fraction(33, 10000)]),
                  ([-10, -20, -30], [Fraction(117, 10000), Fraction(-46, 10000), Fraction(-53, 10000)])]
        for xyz, expected in points:
            with self.subTest(xyz=xyz):
                before = list(xyz)
                actual = reference.displacement_reference(self.settings(), xyz)
                self.assertEqual(xyz, before)
                self.assertEqual(len(actual), 3)
                for observed, value in zip(actual, expected):
                    self.close(observed, value)

    def test_displacement_coordinates_require_finite_json_triples(self):
        bad_coordinates = [None, (1, 2, 3), "123", [1, 2], [1, 2, 3, 4],
                           [True, 2, 3], [1, False, 3], [1, 2, "3"], [float("nan"), 2, 3],
                           [1, float("inf"), 3], [1, 2, -float("inf")], [10 ** 1000, 2, 3],
                           [Decimal(1), 2, 3], [Fraction(1, 1), 2, 3], [[1], 2, 3]]
        for xyz in bad_coordinates:
            with self.subTest(xyz=repr(xyz)):
                with self.assertRaises(ValueError):
                    reference.displacement_reference(self.settings(), xyz)

    def test_body_energy_scales_and_zero_references_independent_cubes(self):
        # For these independent cubes V^(2/3) is rational; no production oracle is used.
        bodies = [(Fraction(1), Fraction(1)), (Fraction(8), Fraction(4)),
                  (Fraction(27), Fraction(9)), (Fraction(1000), Fraction(100)),
                  (Fraction(1, 8), Fraction(1, 4))]
        for volume, area_scale in bodies:
            with self.subTest(volume=volume):
                actual = reference.body_reference(self.settings(), float(volume))
                self.assertEqual(set(actual), {"mesh_volume_mm3", "strain_energy_n_mm", "force_scale_n",
                                               "moment_scale_n_mm", "expected_force_n", "expected_moment_n_mm"})
                self.close(actual["mesh_volume_mm3"], volume)
                self.close(actual["strain_energy_n_mm"], Fraction(806, 6250000) * volume)
                self.close(actual["force_scale_n"], Fraction(16, 25) * area_scale)
                self.close(actual["moment_scale_n_mm"], Fraction(16, 25) * volume)
                self.assertEqual(actual["expected_force_n"], [0.0, 0.0, 0.0])
                self.assertEqual(actual["expected_moment_n_mm"], [0.0, 0.0, 0.0])

    def test_body_finite_extremes_remain_positive_when_representable(self):
        for volume in (1e-300, 1e300, sys.float_info.max):
            with self.subTest(volume=volume):
                actual = reference.body_reference(self.settings(), volume)
                for key in ("mesh_volume_mm3", "strain_energy_n_mm", "force_scale_n", "moment_scale_n_mm"):
                    self.assertTrue(math.isfinite(actual[key]))
                    self.assertGreater(actual[key], 0.0)

    def test_body_rejects_invalid_volume_and_computed_energy_underflow(self):
        for volume in (True, False, 0, -1, "1", None, float("nan"), float("inf"),
                       -float("inf"), 10 ** 1000, Decimal(1), Fraction(1),
                       math.ulp(0.0), 1e-320):
            with self.subTest(volume=repr(volume)):
                with self.assertRaises(ValueError):
                    reference.body_reference(self.settings(), volume)

    def test_references_do_not_mutate_settings_or_share_returned_vectors(self):
        settings = self.settings()
        before = copy.deepcopy(settings)
        tensor = reference.constitutive_reference(settings)
        displacement = reference.displacement_reference(settings, [10, 20, 30])
        body = reference.body_reference(settings, 8)
        tensor["strain6_tensor"].clear()
        tensor["stress6_mpa"].clear()
        displacement.clear()
        body["expected_force_n"][0] = 123
        self.assertEqual(body["expected_moment_n_mm"], [0.0, 0.0, 0.0])
        fresh = reference.body_reference(settings, 8)
        self.assertEqual(fresh["expected_force_n"], [0.0, 0.0, 0.0])
        self.assertEqual(settings, before)
        self.assertEqual(len(reference.constitutive_reference(settings)["stress6_mpa"]), 6)

    def test_all_reference_entrypoints_refuse_changed_settings(self):
        settings = self.settings()
        settings["boundary"] = "CONTACT_FIXTURE"
        for call in (lambda: reference.constitutive_reference(settings),
                     lambda: reference.displacement_reference(settings, [0, 0, 0]),
                     lambda: reference.body_reference(settings, 8)):
            with self.subTest(entrypoint=call):
                with self.assertRaises(ValueError):
                    call()


if __name__ == "__main__":
    unittest.main()
