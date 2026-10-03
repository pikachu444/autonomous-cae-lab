"""Bounded, solver-independent SSNP121A frictionless contact patch rules."""

from .reference import analytical_reference, assess, model_declaration, validate_settings

__version__ = "1.0"
__all__ = ["validate_settings", "analytical_reference", "model_declaration", "assess"]
