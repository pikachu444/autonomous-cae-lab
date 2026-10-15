"""Test-only source-path IO tripwire. It grants no application capability."""
from contextlib import ExitStack
import builtins
import io
import os
from unittest.mock import patch


class SourceGuardTripwire:
    def __init__(self, receipt):
        self.guards = [row['path'] for row in receipt['review']['source']['source_guard']]
        self.attempts = []
        self.stack = ExitStack()

    def _wrapped(self, original):
        def guarded(path, *args, **kwargs):
            if isinstance(path, (str, bytes, os.PathLike)):
                text = os.fsdecode(os.fspath(path)).replace('\\', '/')
                for raw in self.guards:
                    # Also detects .resolve() prepending a POSIX cwd to Windows text.
                    root = raw.replace('\\', '/').rsplit('/documents/', 1)[0]
                    if root in text:
                        self.attempts.append({'operation': original.__name__, 'path': os.fsdecode(os.fspath(path))})
                        raise AssertionError('FORBIDDEN_SOURCE_GUARD_IO: ' + text)
            return original(path, *args, **kwargs)
        return guarded

    def __enter__(self):
        try:
            for module, name in ((builtins, 'open'), (io, 'open'), (os, 'open'), (os, 'stat'), (os, 'lstat')):
                self.stack.enter_context(patch.object(module, name, self._wrapped(getattr(module, name))))
        except BaseException:
            self.stack.close()
            raise
        return self

    def __exit__(self, *error):
        return self.stack.__exit__(*error)
