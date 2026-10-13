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
        return super().submit(context.run, fn, *args, **kwargs)
