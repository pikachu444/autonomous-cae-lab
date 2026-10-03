"""Independent high-precision ODE/integral checks; no native material calls."""
from copy import deepcopy
from decimal import Decimal, localcontext
import math

import pytest

from plugins.material_point import viscoelastic_reference as ref


def dec(value):
    return value if isinstance(value, Decimal) else Decimal.from_float(float(value))


def dot(a, b):
    return sum((x * y * (1 if i < 3 else 2) for i, (x, y) in enumerate(zip(a, b))), Decimal(0))


def c_apply(v, k, mu):
    # Independent dense constitutive tensor, accurate in high precision even
    # for the admitted hydrostatic contrast; not the production modal helper.
    tr = sum(v[:3], Decimal(0))
    return [(k - 2 * mu / 3) * tr + 2 * mu * x for x in v[:3]] + [2 * mu * x for x in v[3:]]


def c_inverse(v, k, mu):
    tr = sum(v[:3], Decimal(0))
    return [tr / (9 * k) + (x - tr / 3) / (2 * mu) for x in v[:3]] + [x / (2 * mu) for x in v[3:]]


def oracle(material, e0, e1, q0, dt):
    """180-digit scalar ODE series / exact exponential integrals on float inputs.

    Small-x q(v)=q0+t*sum(c_n*v^n), t=z-x*q0, c_1=1,
    c_(n+1)=-x*c_n/(n+1). Integrate the polynomial stress and its
    compliance quadratic directly. This does not use the production PSD
    completion or its rational beta/delta coefficients.
    """
    with localcontext() as context:
        context.prec = 180
        k0, g0, k1, g1, tau = [dec(material[k]) for k in ref.MATERIAL_KEYS]
        e0, e1, q0 = [list(map(dec, values)) for values in (e0, e1, q0)]
        x = dec(dt) / tau
        de = [b - a for a, b in zip(e0, e1)]
        z = c_apply(de, k1, g1)
        if x < Decimal('0.0001'):
            t = [v - x * q for v, q in zip(z, q0)]
            coefficients = [Decimal(1)]
            while len(coefficients) < 200:
                nxt = -x * coefficients[-1] / (len(coefficients) + 1)
                if abs(nxt) < Decimal('1e-165'):
                    break
                coefficients.append(nxt)
            endpoint = sum(coefficients, Decimal(0))
            mean = sum((c / (n + 2) for n, c in enumerate(coefficients)), Decimal(0))
            square_integral = sum((a * b / (i + j + 3) for i, a in enumerate(coefficients)
                                   for j, b in enumerate(coefficients)), Decimal(0))
            q1 = [q + endpoint * v for q, v in zip(q0, t)]
            inverse_q, inverse_t = c_inverse(q0, k1, g1), c_inverse(t, k1, g1)
            diss = x * (dot(q0, inverse_q) + 2 * mean * dot(q0, inverse_t) + square_integral * dot(t, inverse_t))
            mean_q = [q + mean * v for q, v in zip(q0, t)]
            f = endpoint
        else:
            # For x>=1000, exp(-x)<1e-434; omitting that term is bounded
            # far below 180-digit oracle precision and the unchanged gates.
            a = (-x).exp() if x < 1000 else Decimal(0)
            qinf = [v / x for v in z]
            b = [q - v for q, v in zip(q0, qinf)]
            q1 = [a * q + (1 - a) * v for q, v in zip(q0, qinf)]
            inv_inf, inv_b = c_inverse(qinf, k1, g1), c_inverse(b, k1, g1)
            diss = x * dot(qinf, inv_inf) + 2 * (1 - a) * dot(qinf, inv_b) + (1 - a * a) / 2 * dot(b, inv_b)
            f = (1 - a) / x
            mean_q = [v + f * w for v, w in zip(qinf, b)]
        s0, s1 = c_apply(e0, k0, g0), c_apply(e1, k0, g0)
        stress = [s + q for s, q in zip(s1, q1)]
        psi0 = (dot(e0, s0) + dot(q0, c_inverse(q0, k1, g1))) / 2
        psi = (dot(e1, s1) + dot(q1, c_inverse(q1, k1, g1))) / 2
        work = dot([a + b for a, b in zip(s0, s1)], de) / 2 + dot(mean_q, de)
        k, mu = k0 + f * k1, g0 + f * g1
        tangent = [[(k - 2 * mu / 3 if i < 3 and j < 3 else Decimal(0)) + (2 * mu if i == j else 0)
                    for j in range(6)] for i in range(6)]
        assert abs(psi - psi0 + diss - work) <= Decimal('1e-130') * max(Decimal(1), abs(psi), abs(work))
        return {'stress': stress, 'q': q1, 'psi': psi, 'psi0': psi0, 'D': diss, 'W': work, 'tangent': tangent}


def check_increment(material, e0, e1, q0, dt):
    expected = oracle(material, e0, e1, q0, dt)
    before = deepcopy((material, e0, e1, q0))
    observed = ref.increment(material, e0, e1, q0, dt)
    assert (material, e0, e1, q0) == before
    assert observed['stored_energy_mpa'] >= 0 and observed['dissipation_increment_mpa'] >= 0
    stress_scale = max(1., *(abs(float(v)) for key in ('stress', 'q') for v in expected[key]))
    energy_scale = max(1e-3, *(abs(float(expected[k])) for k in ('psi0', 'psi', 'D', 'W')))
    stress_limit = ref.FIXED_LIMITS['stress_absolute_mpa'] + ref.FIXED_LIMITS['stress_relative'] * stress_scale
    energy_limit = ref.FIXED_LIMITS['energy_absolute_mpa'] + ref.FIXED_LIMITS['energy_relative'] * energy_scale
    for key, name in [('stress', 'stress_physical_mpa'), ('q', 'branch_stress_physical_mpa')]:
        assert max(abs(dec(a) - b) for a, b in zip(observed[name], expected[key])) <= dec(stress_limit)
    for key, name in [('psi', 'stored_energy_mpa'), ('D', 'dissipation_increment_mpa'), ('W', 'work_increment_mpa')]:
        assert math.isfinite(observed[name])
        assert abs(dec(observed[name]) - expected[key]) <= dec(energy_limit)
    assert abs(dec(observed['stored_energy_mpa']) - expected['psi0'] + dec(observed['dissipation_increment_mpa']) - dec(observed['work_increment_mpa'])) <= dec(energy_limit)
    scale = max(abs(float(v)) for row in expected['tangent'] for v in row)
    assert max(abs(dec(a) - b) for row, other in zip(observed['tangent_kelvin_mpa'], expected['tangent'])
               for a, b in zip(row, other)) <= dec(ref.FIXED_LIMITS['tangent_relative'] * scale)
    return observed, expected


@pytest.mark.parametrize('refined', [False, True])
@pytest.mark.parametrize('tau', [1., 2., 1e6])
def test_canonical_history_prefix_identity_preserves_original_combined_gate(refined, tau):
    settings = ref.canonical_settings(refined=refined, relaxation_time_s=tau)
    original = deepcopy(settings)
    reference = ref.analytical_reference(settings)
    q = [Decimal(0)] * 6
    D, W = Decimal(0), Decimal(0)
    expected = []
    with localcontext() as context:
        context.prec = 180
        for a, b in zip(settings['history'], settings['history'][1:]):
            # The oracle returns high-precision q. The mathematical recurrence
            # remains high precision, separate from production float q state.
            result = oracle(settings['material'], a['strain'], b['strain'], q, b['time_s'] - a['time_s'])
            q = result['q']
            D += result['D']; W += result['W']
            expected.append((result, D, W))
    scale = max(1e-3, *(abs(float(v)) for result, d, w in expected for v in (result['psi'], d, w)))
    limit = ref.FIXED_LIMITS['energy_absolute_mpa'] + ref.FIXED_LIMITS['energy_relative'] * scale
    for row, (result, D, W) in zip(reference['states'][1:], expected):
        assert row['stored_energy_mpa'] >= 0 and row['dissipated_energy_mpa'] >= 0
        assert abs(dec(row['stored_energy_mpa']) - result['psi']) <= dec(limit)
        assert abs(dec(row['dissipated_energy_mpa']) - D) <= dec(limit)
        assert abs(dec(row['work_mpa']) - W) <= dec(limit)
        assert abs(row['stored_energy_mpa'] + row['dissipated_energy_mpa'] - row['work_mpa']) <= limit
    assert settings == original


@pytest.mark.parametrize('dt,tau', [(1e-5, 1.), (1e-8, 1.), (1e-16, 1.),
    (1e-8, 1e6), (1e-300, 1.), (1e-320, 1e6), (math.ulp(0.), 1e6)])
def test_admitted_small_and_underflowed_causal_history_is_finite_without_clamping(dt, tau):
    settings = ref.canonical_settings(relaxation_time_s=tau)
    settings['history'] = settings['history'][:2]
    settings['history'][1]['time_s'] = dt
    settings = ref.validate_settings(settings)
    before = deepcopy(settings)
    row = ref.analytical_reference(settings)['states'][1]
    expected = oracle(settings['material'], [0.] * 6, settings['history'][1]['strain'], [0.] * 6, dt)
    limit = ref.FIXED_LIMITS['energy_absolute_mpa'] + ref.FIXED_LIMITS['energy_relative'] * max(1e-3, abs(float(expected['psi'])), abs(float(expected['W'])))
    for key, field in [('psi', 'stored_energy_mpa'), ('D', 'dissipated_energy_mpa'), ('W', 'work_mpa')]:
        assert math.isfinite(row[field]) and abs(dec(row[field]) - expected[key]) <= dec(limit)
    assert row['dissipated_energy_mpa'] >= 0 and row['stored_energy_mpa'] > 0
    assert row['stress_physical_mpa'] == pytest.approx(list(map(float, expected['stress'])), rel=1e-8, abs=1e-10)
    assert settings == before


@pytest.mark.parametrize('x', [1e-8, 1e-16, math.nextafter(.125, 0.), .125,
    math.nextafter(.125, 1.), .2, 2., 10., 100., 1e12])
@pytest.mark.parametrize('mode', ['unload', 'hold', 'signed'])
def test_signed_ode_integrals_on_both_switch_sides_and_short_long_limits(x, mode):
    material = ref.canonical_settings()['material']
    e0 = [.001, -.0002, .0003, .0004, -.0003, .0002]
    e1 = [0.] * 6 if mode == 'unload' else (list(e0) if mode == 'hold' else [-v / 2 for v in e0])
    q0 = [1., -2., 3., .4, -.5, .6]
    result, expected = check_increment(material, e0, e1, q0, x)
    if mode == 'unload' and x < 1:
        assert result['work_increment_mpa'] < 0 and expected['W'] < 0
    if mode == 'hold':
        assert result['work_increment_mpa'] == 0.


@pytest.mark.parametrize('bulk,shear', [(1e-6, 1e9), (1e9, 1e-6)])
@pytest.mark.parametrize('strain', [[.007, .007, .007, 0., 0., 0.], [0., 0., 0., .007, -.003, .002]])
def test_extreme_admitted_modal_response_work_and_energy(bulk, shear, strain):
    material = ref.canonical_settings()['material']
    for prefix in ('equilibrium', 'branch'):
        material[prefix + '_bulk_modulus_mpa'] = bulk
        material[prefix + '_shear_modulus_mpa'] = shear
    result, expected = check_increment(material, [0.] * 6, strain, [0.] * 6, .2)
    if strain[0] == strain[1] == strain[2] and strain[0] != 0.:
        assert result['stress_physical_mpa'][0] == result['stress_physical_mpa'][1] == result['stress_physical_mpa'][2]
        assert ref.stiffness(strain, bulk, shear) == pytest.approx([3 * bulk * strain[0]] * 3 + [0.] * 3, rel=1e-15)
    # Dense tangent entries have the original component gate; this is not a
    # claim about reconstructing a tiny bulk eigenmode from their subtraction.
    assert expected['psi'] > 0 and expected['D'] > 0


def test_physical_kelvin_work_and_memory_energy_use_the_same_shear_weights():
    material = ref.canonical_settings()['material']
    e0, e1, q0 = [.001] * 6, [-.0005] * 6, [1., -2., 3., .4, -.5, .6]
    result, _ = check_increment(material, e0, e1, q0, 1e-16)
    physical_dot = sum(a * b * (1 if i < 3 else 2) for i, (a, b) in enumerate(zip(q0, e1)))
    kelvin_dot = sum(a * b for a, b in zip(ref.to_kelvin(q0), ref.to_kelvin(e1)))
    assert physical_dot == pytest.approx(kelvin_dot, rel=1e-15, abs=1e-18)
    assert ref.from_kelvin(ref.to_kelvin(result['stress_physical_mpa'])) == pytest.approx(result['stress_physical_mpa'], rel=1e-15)


@pytest.mark.parametrize('x', [1e-8, 1e-16, .125, .2])
def test_dissipation_remains_positive_near_the_completed_square_minimum(x):
    material = ref.canonical_settings()['material']
    e1 = [.001, -.0002, .0003, .0004, -.0003, .0002]
    with localcontext() as ctx:
        ctx.prec = 180
        k, mu = dec(material['branch_bulk_modulus_mpa']), dec(material['branch_shear_modulus_mpa'])
        z = c_apply(list(map(dec, e1)), k, mu)
    q0 = [-float(v) / 2 for v in z]
    observed, expected = check_increment(material, [0.] * 6, e1, q0, x)
    assert observed['dissipation_increment_mpa'] > 0 and expected['D'] > 0


def test_public_zero_ratio_helper_refuses_unproven_scope_but_validated_limit_has_instantaneous_tangent():
    material = ref.canonical_settings(relaxation_time_s=1e6)['material']
    dt = math.ulp(0.)
    with pytest.raises(ValueError, match='bounded validated causal-history'):
        ref.increment(material, [0.] * 6, [0.] * 6, [0.] * 6, dt)
    result = ref.increment(material, [0.] * 6, [0.] * 6, [0.] * 6, dt, _validated_history=True)
    assert result['decay'] == result['ramp_factor'] == 1.
    assert result['tangent_kelvin_mpa'] == ref.tangent(3000., 1500.)
    assert result['stored_energy_mpa'] == result['dissipation_increment_mpa'] == result['work_increment_mpa'] == 0.


@pytest.mark.parametrize('case', ['q', 'strain', 'modulus', 'tau'])
def test_underflow_limit_rechecks_its_explicit_material_strain_and_memory_bounds(case):
    material = ref.canonical_settings(relaxation_time_s=1e6)['material']
    e0, e1, q0 = [0.] * 6, [0.] * 6, [0.] * 6
    if case == 'q': q0[0] = 6e9
    if case == 'strain': e1[0] = .011
    if case == 'modulus': material['equilibrium_bulk_modulus_mpa'] = 1e-7
    if case == 'tau': material['relaxation_time_s'] = 1e9
    with pytest.raises(ValueError, match='bounded validated causal-history'):
        ref.increment(material, e0, e1, q0, math.ulp(0.), _validated_history=True)


@pytest.mark.parametrize('case', ['energy_overflow', 'ratio_overflow', 'modulus_overflow'])
def test_nonrepresentable_standalone_results_fail_closed(case):
    material = ref.canonical_settings()['material']
    q0, dt = [0.] * 6, .2
    if case == 'energy_overflow': q0[0] = 1e300
    if case == 'ratio_overflow': material['relaxation_time_s'], dt = 1e-300, 1e308
    if case == 'modulus_overflow': material['branch_shear_modulus_mpa'] = 1e308
    with pytest.raises(ValueError):
        ref.increment(material, [0.] * 6, [.01] * 6, q0, dt)
