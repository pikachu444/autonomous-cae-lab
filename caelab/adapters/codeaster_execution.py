"""Local Code_Aster execution policy, independent of physical model settings."""

import os
import re


# Pinned run_aster 17.4 uses 86400 when time_limit is omitted. Zero is NOT
# unlimited: its runner clamps the CPU ulimit to one second.
RUN_ASTER_DEFAULT_TIME_SECONDS = 86400


def process_budgets() -> dict:
    def positive_seconds(name: str, default: int | None) -> int | None:
        value = os.environ.get(name)
        if value is None:
            return default
        if not re.fullmatch(r"[0-9]+", value) or not 0 < int(value) <= 2**31 - 1:
            raise ValueError(f"{name} must be a positive integer no greater than 2147483647")
        return int(value)

    return {
        "solver_memory_mb": 1024,
        "solver_time_seconds": positive_seconds(
            "CAELAB_CODEASTER_TIME_LIMIT_SECONDS", RUN_ASTER_DEFAULT_TIME_SECONDS),
        "subprocess_timeout_seconds": positive_seconds(
            "CAELAB_CODEASTER_WALL_TIMEOUT_SECONDS", None),
        "solver_time_source": ("USER_ENVIRONMENT" if "CAELAB_CODEASTER_TIME_LIMIT_SECONDS" in os.environ
                               else "PINNED_RUN_ASTER_DEFAULT"),
        "wall_time_source": ("USER_ENVIRONMENT" if "CAELAB_CODEASTER_WALL_TIMEOUT_SECONDS" in os.environ
                             else "NO_WALL_TIME_LIMIT"),
        "qualification": "UNKNOWN",
    }
