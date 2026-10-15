"""Scripted SM API. XML shapes checked against tagged ParaView sources, not a native test."""
from types import SimpleNamespace

WIDTHS = {'BlockColorArrayNames': 3, 'BlockColors': 4, 'BlockUseSeparateColorMaps': 2,
          'BlockMapScalars': 2, 'BlockInterpolateScalarsBeforeMappings': 2, 'BlockOpacities': 2}


class StringProperty:
    def __init__(self, width, values=()):
        self.width, self.values = width, list(values)
    def IsA(self, kind): return kind == 'vtkSMStringVectorProperty'
    def GetNumberOfElementsPerCommand(self): return self.width
    def GetNumberOfElements(self): return len(self.values)
    def GetElement(self, i): return self.values[i]


class LookupProperty:
    def __init__(self, values=()): self.values = list(values)
    def IsA(self, kind): return kind == 'vtkSMProxyProperty'
    def GetNumberOfProxies(self): return len(self.values)
    def GetProxy(self, i): return self.values[i]


class RawRepresentation:
    def __init__(self):
        self.properties = {name: StringProperty(width) for name, width in WIDTHS.items()}
        self.properties['BlockLookupTables'] = LookupProperty()
    def GetProperty(self, name): return self.properties.get(name)


class Version:
    GetVersionMajor = staticmethod(lambda: 6)
    GetVersionMinor = staticmethod(lambda: 2)
    GetVersionPatch = staticmethod(lambda: 0)


def lookup(identity='lut', component=0, color='default'):
    return SimpleNamespace(GetGlobalIDAsString=lambda: identity, VectorComponent=component, Color=color)
