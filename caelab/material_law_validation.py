"""Law-specific admission for the existing Numerical Plan, not a new compiler."""
from .adapters import felupe_material as original
from plugins.material_point import law_native as native


def validate_parameters(model, parameters):
    if model in ('drucker_prager_linear', 'single_branch_maxwell'):
        return native.validate_parameters(model, parameters)
    return original.validate_parameters(model, parameters)


def validate_settings(settings):
    if 'initial_state' in settings and settings.get('model') in native.MODELS:
        return native.validate_settings(settings)
    return original.validate_settings(settings)


def parameter_unit(settings, name):
    if 'initial_state' in settings and settings.get('model') in native.MODELS:
        return native.parameter_unit(settings['model'], name, settings['stress_unit'])
    return '1' if name == 'nu' else settings['stress_unit']


def measure(settings):
    return ('infinitesimal_Cauchy' if settings['model'] in
            ('linear_elastic', 'drucker_prager_linear', 'single_branch_maxwell') else 'first_Piola')


def fit_notice(settings, variables, experiments):
    """Identifiability warnings, not fictitious physical identification certificates."""
    if settings.get('model') != 'drucker_prager_linear':
        return []
    free = {v['id'] for v in variables if v['free']}
    notes = ['SYNTHETIC fit is not physical material identification; strength/failure UNKNOWN.']
    if 'beta' in free:
        notes.append('Dilatancy beta needs measured volumetric/lateral plastic response; axial stress alone is insufficient.')
    if {'alpha', 'k0'} <= free:
        notes.append('Friction and cohesion require independent pressure states; tensile fit alone is not a certificate.')
    if not any(e['role'] == 'holdout' for e in experiments):
        notes.append('No holdout selected: independent validation is NOT_ASSESSED.')
    return notes
