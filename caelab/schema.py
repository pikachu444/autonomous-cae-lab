"""Runtime validation of versioned common experiment and result envelopes."""

import json
from pathlib import Path

from jsonschema import Draft202012Validator


SCHEMAS = Path(__file__).resolve().parents[1] / "schemas"


def validate(name: str, value: dict) -> None:
    if name not in ("experiment", "result"):
        raise ValueError("Unknown common schema")
    schema = json.loads((SCHEMAS / f"{name}.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(value)
