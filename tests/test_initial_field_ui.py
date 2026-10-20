"""Native solver entry preserves saved initial conditions without a second editor."""
from copy import deepcopy
from types import SimpleNamespace as NS
import pytest
from apps.desktop_pre.initial_field_controls import route


@pytest.mark.parametrize('stored_for_selected', [False, True])
def test_native_solver_keeps_saved_initial_conditions_without_opening_custom_ui(stored_for_selected):
    solver = NS(Name='UserSolver')
    analysis = NS(Name='ThermalStudy', Label='사용자 초기온도 해석', TypeId='Fem::FemAnalysis', Group=[solver])
    data = {'initial_fields': {('ThermalStudy' if stored_for_selected else 'OtherStudy'):
        {'draft': {'temperature': {'expansion_per_K': '1e'}}, 'applied': {'temperature_object': 'NativeInitialTemperature'}}}}
    owner = NS(doc=NS(Objects=[analysis]), read_metadata=lambda: deepcopy(data))
    connection = NS(show_panel=lambda *a, **kw: pytest.fail('Native solver must not create a duplicate editor'))
    before = deepcopy(data)
    if stored_for_selected:
        with pytest.raises(ValueError, match='사용자 초기온도 해석.*계산 관리'):
            route(connection, owner, solver)
    else:
        assert route(connection, owner, solver) is False
    assert data == before and analysis.Group == [solver]


def test_native_only_initial_temperature_uses_existing_freecad_task_path():
    solver = NS(Name='UserSolver')
    temperature = NS(Name='NativeTemperature', initialTemperature=293.15, FinalTemperature=393.15)
    analysis = NS(Name='NativeStudy', TypeId='Fem::FemAnalysis', Group=[solver, temperature])
    owner = NS(doc=NS(Objects=[analysis]), read_metadata=lambda: {})
    assert route(NS(), owner, solver) is False
    assert temperature.initialTemperature == 293.15 and temperature.FinalTemperature == 393.15
