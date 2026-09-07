"""DB-free schema and model-aware validation for edit cases."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from reference_harness.case import load_model
from reference_harness.schema_validate import _validate_edit_case
from reference_harness.schemas import build_registry, load_schemas

_REPO_ROOT = Path(__file__).resolve().parents[2]
_COMPATIBILITY_ROOT = _REPO_ROOT / "core" / "compatibility"
_SCHEMA_PATH = _REPO_ROOT / "core" / "schemas" / "compatibility-case.schema.json"
_REGISTRY = build_registry(load_schemas(_SCHEMA_PATH.parents[1]))


def _case_validator() -> Draft202012Validator:
    return Draft202012Validator(json.loads(_SCHEMA_PATH.read_text()), registry=_REGISTRY)


def _valid_edit_case() -> dict[str, Any]:
    return {
        "model": "models/note.yaml",
        "tags": ["m-edit", "m-value-object"],
        "shape": "edit",
        "lane": "api-conformance",
        "when": {
            "edit": {
                "source": {
                    "origin": "constructed",
                    "value": {
                        "id": 1,
                        "title": "alpha",
                        "body": "first",
                        "tag": {"label": "a", "weight": 3},
                        "marks": [],
                    },
                    "path": "parallax.compatibility.Note.tag",
                },
                "set": {"weight": 1},
            }
        },
        "then": {
            "result": {"members": {"label": "a", "weight": 1}},
            "carry": {
                "auxiliary": {
                    "identity": "shared",
                    "binding": "independent",
                    "hooks": "none",
                },
                "derivedCache": {"value": "A", "evaluations": 1},
            },
            "source": {"unchanged": True},
        },
    }


def test_schema_accepts_edit_case_on_the_api_conformance_lane() -> None:
    assert list(_case_validator().iter_errors(_valid_edit_case())) == []


def test_schema_rejects_edit_case_missing_lane() -> None:
    case = _valid_edit_case()
    del case["lane"]
    assert list(_case_validator().iter_errors(case))


def test_schema_rejects_edit_case_on_the_harness_lane() -> None:
    case = _valid_edit_case()
    case["lane"] = "harness"
    assert list(_case_validator().iter_errors(case))


def test_schema_rejects_edit_case_with_golden_sql() -> None:
    case = _valid_edit_case()
    case["then"]["statements"] = []
    assert list(_case_validator().iter_errors(case))


def test_model_aware_validation_rejects_an_unassignable_edit_member() -> None:
    model = load_model(_COMPATIBILITY_ROOT, "models/note.yaml")
    edit = _valid_edit_case()["when"]["edit"]
    edit["set"] = {"missing": 1}
    errors: list[str] = []

    _validate_edit_case(edit, model.entity_defs, "probe", errors)

    assert errors == [
        "probe: `edit` set Note.tag.missing: names no assignable attribute or value object"
    ]
