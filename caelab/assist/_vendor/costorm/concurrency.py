"""Keep native cancellation ownership and deterministic bounded host ordering."""
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context


class ContextExecutor(ThreadPoolExecutor):
    def __init__(self, *args, **kwargs):
        # Protocol remains multi-role; provider execution is deliberately serial.
        kwargs.pop('max_workers', None)
        super().__init__(max_workers=1, **kwargs)

    def submit(self, fn, /, *args, **kwargs):
        context = copy_context()
        def execute():
            from .prompting import last_completion_key
            last_completion_key.set(None)
            try:
                return fn(*args, **kwargs)
            except ValueError as error:
                # Carry the rejecting worker's exact completion, not whichever
                # later queued task happened to finish last.
                if not hasattr(error, 'completion_key'):
                    error.completion_key = last_completion_key.get()
                raise
        return super().submit(context.run, execute)
