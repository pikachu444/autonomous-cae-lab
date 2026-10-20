"""Headless FEM presentation restoration must leave native physics untouched."""
from copy import deepcopy
import sys
from types import SimpleNamespace as NS

import pytest

from apps.desktop_pre.native_presentation import restore_fem_viewproviders, _PROVIDERS


@pytest.mark.parametrize('identity,provider_name', _PROVIDERS.items())
def test_missing_official_fem_view_attaches_native_provider_only(monkeypatch, identity, provider_name):
    module, class_name = identity
    cls = type(class_name, (), {'__module__': 'femobjects.' + module})
    view = NS(Proxy=None)
    obj = NS(Name='UserObject', Proxy=cls(), ViewObject=view,
             physics={'force': 123., 'material': {'plastic': [(210., 0.01)]}, 'mesh': [4, 9, 11]})
    doc = NS(Objects=[obj])
    calls = []
    def native_provider(vobj):
        calls.append(vobj)
        vobj.Proxy = NS(native=True)
    monkeypatch.setitem(sys.modules, cls.__module__, NS(**{class_name: cls}))
    monkeypatch.setitem(sys.modules, 'femviewprovider.view_' + module,
                        NS(**{provider_name: native_provider}))
    before = deepcopy(obj.physics)
    app_proxy = obj.Proxy
    assert restore_fem_viewproviders(doc) == ['UserObject']
    assert calls == [view] and view.Proxy.native
    assert obj.Proxy is app_proxy and obj.physics == before and doc.Objects == [obj]
    assert restore_fem_viewproviders(doc) == []
    assert calls == [view]


@pytest.mark.parametrize('case', ['existing', 'custom', 'inherited', 'cpp'])
def test_existing_custom_and_cpp_native_presentation_is_preserved(monkeypatch, case):
    cls = type('SolverCcxTools', (), {'__module__': 'femobjects.solver_ccxtools'})
    monkeypatch.setitem(sys.modules, cls.__module__, NS(SolverCcxTools=cls))
    view = NS(Proxy=None)
    proxy = cls()
    if case == 'existing':
        view.Proxy = object()
    elif case == 'custom':
        proxy = type('SolverCcxTools', (), {'__module__': 'user_extension'})()
    elif case == 'inherited':
        proxy = type('UserSolver', (cls,), {})()
    else:
        view = NS()  # A C++ native ViewProvider has no Python Proxy property.
    obj = NS(Name='UserObject', Proxy=proxy, ViewObject=view)
    original_view = getattr(view, 'Proxy', None)
    assert restore_fem_viewproviders(NS(Objects=[obj])) == []
    assert obj.Proxy is proxy and getattr(view, 'Proxy', None) is original_view
