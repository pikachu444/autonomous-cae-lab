"""Explicitly loaded, editable teaching inputs, never execution defaults."""
from copy import deepcopy


def native_example(backend):
    if backend == 'pde.fenicsx.transient':
        from plugins.pde_transient.reference import manufactured_settings
        return manufactured_settings()
    if backend == 'explicit.openradioss':
        # Same documented SI freefall declaration as verify_openradioss.
        return deepcopy({
            'case':'rigid_cube_freefall','edge_m':.1,'mass_kg':1.,
            'center_height_m':1.,'gravity_m_s2':9.81,'initial_velocity_m_s':0.,
            'end_time_s':.2,'time_step_s':1e-4,'history_interval_s':1e-3,
            'limits':{'displacement_abs_m':2e-4,'velocity_abs_m_s':.002,
                'energy_abs_j':.01,'mass_relative':1e-8,'impact_time_abs_s':2e-4,
                'impulse_abs_n_s':.005,'penetration_abs_m':.001}})
    return None
