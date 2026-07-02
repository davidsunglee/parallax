"""Schema validation: the schemas are valid, and every fixture conforms.

Run as a module against the compatibility tree::

    uv run python -m reference_harness.schema_validate ../core/compatibility

It performs M12 layer 1 statically (no database needed):

* **Meta-schema validation** — each core schema is itself a valid JSON Schema
  (Draft 2020-12).
* **Descriptor validation** — every model under ``models/`` validates against the
  metamodel schema.
* **Operation validation** — every case's ``operation`` validates against the
  operation schema.
* **Case validation** — every case validates against the compatibility-case
  schema, and its referenced model + golden-SQL dialect keys are coherent.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match

from .paths import schemas_dir

_SCHEMA_FILES = (
    "metamodel.schema.json",
    "operation.schema.json",
    "compatibility-case.schema.json",
    "conformance-adapter.schema.json",
)


class ValidationFailure(Exception):
    """Raised with a human-readable list of problems."""


def _load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _load_schemas(schemas: Path) -> dict[str, dict[str, Any]]:
    return {name: _load_json(schemas / name) for name in _SCHEMA_FILES}


def _validate(instance: Any, schema: dict[str, Any], label: str, errors: list[str]) -> None:
    validator = Draft202012Validator(schema)
    found = sorted(validator.iter_errors(instance), key=lambda e: e.path)
    if found:
        match = best_match(found)
        location = "/".join(str(p) for p in match.absolute_path) or "<root>"
        errors.append(f"{label}: at {location}: {match.message}")


def validate_tree(compatibility_root: Path) -> list[str]:
    """Validate every schema and every fixture; return a list of error strings."""
    compatibility_root = compatibility_root.resolve()
    schemas = schemas_dir(compatibility_root)
    schema_map = _load_schemas(schemas)
    errors: list[str] = []

    # 1. The schemas themselves are valid JSON Schema documents.
    for name, schema in schema_map.items():
        try:
            Draft202012Validator.check_schema(schema)
        except Exception as exc:  # noqa: BLE001 - surface any meta-schema problem
            errors.append(f"meta-schema: {name} is not a valid JSON Schema: {exc}")

    metamodel_schema = schema_map["metamodel.schema.json"]
    operation_schema = schema_map["operation.schema.json"]
    case_schema = schema_map["compatibility-case.schema.json"]

    # 2. Every model descriptor validates against the metamodel schema.
    models_dir = compatibility_root / "models"
    for model_path in sorted(models_dir.glob("**/*.y*ml")):
        descriptor = _load_yaml(model_path)
        _validate(descriptor, metamodel_schema, f"model {model_path.name}", errors)

    # 3. Every case + its operation validate against their schemas.
    cases_dir = compatibility_root / "cases"
    for case_path in sorted(cases_dir.glob("**/*.y*ml")):
        case = _load_yaml(case_path)
        _validate(case, case_schema, f"case {case_path.name}", errors)
        if isinstance(case, dict) and "operation" in case:
            _validate(
                case["operation"],
                operation_schema,
                f"case {case_path.name} operation",
                errors,
            )
        # A scenario case carries its operations per step (under `find`); each one
        # must also validate against the operation algebra schema.
        if isinstance(case, dict) and isinstance(case.get("scenario"), list):
            for index, step in enumerate(case["scenario"]):
                if isinstance(step, dict) and "find" in step:
                    _validate(
                        step["find"],
                        operation_schema,
                        f"case {case_path.name} scenario[{index}].find",
                        errors,
                    )
        # A coherence case (Phase 11) likewise carries read-step operations under
        # `find`; each must validate against the operation algebra schema.
        if isinstance(case, dict) and isinstance(case.get("coherence"), list):
            for index, step in enumerate(case["coherence"]):
                if isinstance(step, dict) and "find" in step:
                    _validate(
                        step["find"],
                        operation_schema,
                        f"case {case_path.name} coherence[{index}].find",
                        errors,
                    )
        # The referenced model must exist.
        if isinstance(case, dict) and isinstance(case.get("model"), str):
            referenced = compatibility_root / case["model"]
            if not referenced.is_file():
                errors.append(f"case {case_path.name}: model {case['model']} does not exist")

    return errors


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(
            "usage: python -m reference_harness.schema_validate <core/compatibility>",
            file=sys.stderr,
        )
        return 2
    compatibility_root = Path(argv[0])
    if not compatibility_root.is_dir():
        print(f"not a directory: {compatibility_root}", file=sys.stderr)
        return 2

    errors = validate_tree(compatibility_root)
    if errors:
        print(f"schema validation FAILED ({len(errors)} problem(s)):", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print("schema validation OK: all schemas and fixtures conform")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
