"""Fixed read-only loaded-binding/tool identity probe; never integrates a material.

Executed only by the opt-in inverse runtime admission path inside the checked
SIF. No input, path, command, behavior or model comes from research settings.
"""

import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import shutil
import sys


TFEL_PREFIX = Path("/opt/spack/opt/spack/linux-zen2/tfel-5.0.0-flantzxx3vcxkf4qlpwnl7midzoe33ma")
MGIS_PREFIX = Path("/opt/spack/opt/spack/linux-zen2/mgis-3.0-dfpytmkwj5iza5npkbvk5hils7heaxad")


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def binding_identity(path, prefix):
    original, resolved = Path(path), Path(path).resolve()
    if not resolved.is_file() or not resolved.is_relative_to(prefix):
        raise ValueError("Loaded native binding is outside the fixed installed prefix")
    return {"loaded_path": str(original), "resolved_path": str(resolved), "sha256": sha256(resolved)}


def tool_identity(name):
    location = shutil.which(name)
    if not location:
        raise ValueError("Fixed native tool is unavailable: " + name)
    path = Path(location).resolve()
    if not path.is_file():
        raise ValueError("Fixed native tool is not a file")
    return {"path": str(path), "sha256": sha256(path)}


def probe():
    if Path(__file__).resolve() != Path("/probe/mfront_inverse_runtime_probe.py"):
        raise ValueError("Only the fixed read-only /probe script is admitted")
    resource.setrlimit(resource.RLIMIT_AS, (4 * 1024 ** 3,) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
    resource.setrlimit(resource.RLIMIT_FSIZE, (65536, 65536))
    os.umask(0o077)
    import mgis.behaviour as binding
    import tfel
    import tfel.math
    import mtest

    # Imports establish the actually loaded .so identities; no behavior load,
    # state manager, energy getter or constitutive integration is called.
    return {"schema_version": "1", "probe_sha256": sha256(__file__),
            "python": {"version": platform.python_version(), "executable": str(Path(sys.executable).resolve())},
            "bindings": {"mgis_binding": binding_identity(binding.__file__, MGIS_PREFIX),
                         "mtest_binding": binding_identity(mtest._mtest.__file__, TFEL_PREFIX)},
            "executables": {"compiler": tool_identity("g++"), "mfront": tool_identity("mfront"),
                            "mtest": tool_identity("mtest"), "tfel_config": tool_identity("tfel-config")}}


if __name__ == "__main__":
    if len(sys.argv) != 1:
        raise ValueError("The runtime probe accepts no arguments")
    print(json.dumps(probe(), sort_keys=True, separators=(",", ":"), allow_nan=False), flush=True)
