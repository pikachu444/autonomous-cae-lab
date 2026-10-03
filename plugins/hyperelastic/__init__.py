"""Bounded, solver-independent finite-kinematics SVK material point."""

from .reference import analytical_reference, assess, canonical_settings, model_declaration, validate_settings

__all__ = ["canonical_settings", "validate_settings", "analytical_reference", "model_declaration", "assess"]
