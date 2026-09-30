"""Bounded scalar nonlinear-diffusion benchmark domain reference."""

from .reference import (NEWTON_ATOL, NEWTON_MAX_ITERATIONS, NEWTON_RTOL, VERSION,
                        assess, manufactured_rhs, manufactured_settings,
                        model_declaration, source_value, validate_settings)

__all__ = ["VERSION", "NEWTON_RTOL", "NEWTON_ATOL", "NEWTON_MAX_ITERATIONS",
           "validate_settings", "manufactured_rhs", "manufactured_settings",
           "source_value", "model_declaration", "assess"]
