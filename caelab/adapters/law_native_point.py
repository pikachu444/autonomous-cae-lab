"""Registered prepared point adapter; existing evaluator/fit/owner retain outputs."""
from copy import deepcopy
from ..evaluation import PreparedEvaluation
from plugins.material_point import law_native as law
from plugins.material_point.law_native_history import evaluate_history


class LawNativePointAdapter:
    backend=law.POINT
    version='1'
    default_settings=staticmethod(law.default_settings)
    validate_settings=staticmethod(law.validate_settings)
    describe_inputs=staticmethod(law.describe_inputs)
    bind_inputs=staticmethod(law.bind_inputs)
    describe_model=staticmethod(law.declaration)

    def describe_ports(self,settings):
        law.validate_settings(settings)
        return {'inputs':{},'outputs':{}}

    def prepare(self,settings,*,runtime=None):
        s=law.validate_settings(settings)
        if runtime and set(runtime)-{'threads','memory_mb'}:
            raise ValueError('No runtime/source/library injection in trusted law-native point adapter')
        def calculate(values):
            return evaluate_history(law.bind_inputs(deepcopy(s),values))
        return PreparedEvaluation(calculate,s)
