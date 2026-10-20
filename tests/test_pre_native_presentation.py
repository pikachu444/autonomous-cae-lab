"""Headless FEM presentation restoration must leave native physics untouched."""
from copy import deepcopy
import sys
from types import SimpleNamespace as NS

import pytest

from apps.desktop_pre.native_presentation import restore_fem_viewproviders, _PROVIDERS


@pytest.mark.parametrize('identity,provider_name', _PROVIDERS.items())
@pytest.mark.parametrize('missing', [None, 1])
def test_missing_official_fem_view_attaches_native_provider_only(monkeypatch, identity, provider_name, missing):
    module, class_name = identity
    cls = type(class_name, (), {'__module__': 'femobjects.' + module})
    view = NS(Proxy=missing)
    obj = NS(Name='UserObject', Proxy=cls(), ViewObject=view,
             physics={'force': 123., 'material': {'plastic': [(210., 0.01)]}, 'mesh': [4, 9, 11]})
    view.Object = obj
    doc = NS(Objects=[obj])
    calls = []
    def native_provider(vobj):
        calls.append(vobj)
        proxy = NS(native=True)
        def attach(current):
            proxy.Object, proxy.ViewObject = current.Object, current
            calls.append('attach')
        proxy.attach = attach
        vobj.Proxy = proxy
        if missing is None:
            attach(vobj)  # Native C++ first attachment; marker 1 already did it.
    monkeypatch.setitem(sys.modules, cls.__module__, NS(**{class_name: cls}))
    monkeypatch.setitem(sys.modules, 'femviewprovider.view_' + module,
                        NS(**{provider_name: native_provider}))
    before = deepcopy(obj.physics)
    app_proxy = obj.Proxy
    assert restore_fem_viewproviders(doc) == ['UserObject']
    assert calls == [view, 'attach'] and view.Proxy.native
    assert view.Proxy.Object is obj and view.Proxy.ViewObject is view
    assert obj.Proxy is app_proxy and obj.physics == before and doc.Objects == [obj]
    assert restore_fem_viewproviders(doc) == []
    assert calls == [view, 'attach']


@pytest.mark.parametrize('case', ['existing', 'custom', 'inherited', 'cpp', 'integer_zero', 'boolean', 'equal_one'])
def test_existing_custom_and_cpp_native_presentation_is_preserved(monkeypatch, case):
    cls = type('SolverCcxTools', (), {'__module__': 'femobjects.solver_ccxtools'})
    monkeypatch.setitem(sys.modules, cls.__module__, NS(SolverCcxTools=cls))
    view = NS(Proxy=None)
    proxy = cls()
    if case == 'existing':
        view.Proxy = object()
    elif case == 'integer_zero':
        view.Proxy = 0
    elif case == 'boolean':
        view.Proxy = True
    elif case == 'equal_one':
        class CustomView:
            def __eq__(self, other):
                return other == 1
        view.Proxy = CustomView()
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


def test_native_subsequent_file_open_repairs_after_restore_without_an_owner(monkeypatch):
    from apps.desktop_pre import native_presentation
    queued, registered, removed, callbacks, restored = [], [], [], [], []
    main = NS()
    documents = {}
    app = NS(addDocumentObserver=registered.append, removeDocumentObserver=removed.append,
             listDocuments=lambda: documents, Console=NS(PrintError=lambda text: pytest.fail(text)))
    core = NS(QTimer=NS(singleShot=lambda delay, callback: queued.append(callback)))
    widgets = NS(QApplication=NS(instance=lambda: NS(aboutToQuit=NS(connect=callbacks.append))))
    monkeypatch.setattr(native_presentation, 'restore_fem_viewproviders', restored.append)
    observer = native_presentation.install_restore_observer(app, NS(getMainWindow=lambda: main), core, widgets)
    assert native_presentation.install_restore_observer(app, NS(getMainWindow=lambda: main), core, widgets) is observer
    assert registered == [observer]
    first = NS(Name='First', Label='First model', FileName='first.FCStd', Restoring=True)
    documents[first.Name] = first
    observer.slotActivateDocument(first)
    observer.slotActivateDocument(first)
    assert len(queued) == 1 and not restored
    first.Restoring = False
    queued.pop(0)()
    second = NS(Name='Second', Label='Second model', FileName='second.FCStd', Restoring=False)
    documents[second.Name] = second
    observer.slotActivateDocument(second)
    queued.pop(0)()
    assert restored == [first, second]
    observer.slotActivateDocument(second)
    assert not queued  # Switching back to an existing tab performs no repair.
    third = NS(Name='Third', Label='Third model', FileName='third.FCStd', Restoring=False)
    documents[third.Name] = third
    observer.slotActivateDocument(third)
    documents.pop(third.Name)  # Closed before the queued callback.
    queued.pop(0)()
    assert restored == [first, second]
    observer.slotDeletedDocument(first)
    observer.slotActivateDocument(first)
    callbacks[0]()
    queued.pop(0)()
    assert removed == [observer] and restored == [first, second]
