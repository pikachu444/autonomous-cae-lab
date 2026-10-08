"""Independent calculation APIs; optional backends load only on selection."""

__all__ = ["Lab", "prepare", "evaluate", "run", "read_result", "list_backends"]


def __getattr__(name):
    if name == "Lab":
        from .engine import Lab
        return Lab
    if name == "list_backends":
        from .backends import list_backends
        return list_backends
    if name in {"prepare", "evaluate", "run", "read_result"}:
        from . import evaluation
        return getattr(evaluation, name)
    raise AttributeError(name)
