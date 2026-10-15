"""DB-free probes of what provisioning through `given.provisioningModel` hands a provider."""

from __future__ import annotations

import copy
import shutil
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from reference_harness.case import Case, Model, load_case, load_model
from reference_harness.case_assertions import CaseFailure
from reference_harness.case_preflight import preflight_case_literals
from reference_harness.data_loader import load_model as load_fixture_rows
from reference_harness.providers import DatabaseProvider
from reference_harness.provisioning import provision
from reference_harness.schema_validate import validate_tree

_REPO_ROOT = Path(__file__).resolve().parents[2]
_COMPATIBILITY_ROOT = _REPO_ROOT / "core" / "compatibility"
_PARTIAL_ROOT = "m-inheritance-147-partial-tph-root-read-unknown-tag.yaml"
_ORDINARY_ROOT = "m-inheritance-003-tph-abstract-root-read.yaml"


class _RecordingProvider:
    dialect = "postgres"

    def __init__(self) -> None:
        self.ddl: list[str] = []
        self.loads: dict[str, list[dict[str, Any]]] = {}

    def reset(self) -> None:
        self.ddl.clear()
        self.loads.clear()

    def apply_ddl(self, statements: Sequence[str]) -> None:
        self.ddl.extend(statements)

    def load(self, table: str, columns: Sequence[str], rows: Sequence[Sequence[Any]]) -> None:
        self.loads.setdefault(table, []).extend(
            dict(zip(columns, row, strict=True)) for row in rows
        )


def _case(name: str) -> Case:
    return load_case(_COMPATIBILITY_ROOT, _COMPATIBILITY_ROOT / "cases" / name)


def _provisioned(case: Case) -> _RecordingProvider:
    provider = _RecordingProvider()
    provision(case, cast("DatabaseProvider", provider))
    return provider


def test_a_read_case_names_separate_setup_and_reader_models() -> None:
    case = _case(_PARTIAL_ROOT)

    assert case.model.path.stem == "composed-beast-reader"
    assert case.setup_model.path.stem == "composed-beast-provisioning"
    assert "parallax.compatibility.Bear" not in {e.canonical_name for e in case.model.entities}


def test_a_case_naming_no_provisioning_model_provisions_through_its_own() -> None:
    case = _case(_ORDINARY_ROOT)

    assert case.provisioning_model is None
    assert case.setup_model is case.model


def test_provisioning_applies_the_setup_models_ddl_and_fixtures() -> None:
    provider = _provisioned(_case(_PARTIAL_ROOT))

    assert set(provider.loads) == {"beast", "keeper", "den"}
    assert [keeper["badge"] for keeper in provider.loads["keeper"]] == ["K-10", "K-11", "K-12"]
    kinds = {beast["id"]: beast["kind"] for beast in provider.loads["beast"]}
    assert kinds == {1: "wolf", 2: "bear", 3: "wolf"}
    assert any("roar" in statement for statement in provider.ddl)


def test_setup_fixtures_resolved_through_the_reader_are_refused() -> None:
    case = _case(_PARTIAL_ROOT)
    misread = Model(case.model.path, case.model.descriptor, case.setup_model.fixtures)

    with pytest.raises((KeyError, ValueError)):
        load_fixture_rows(misread, cast("DatabaseProvider", _RecordingProvider()))


def test_a_corruption_addresses_a_row_only_the_setup_model_declares() -> None:
    reader = load_model(_COMPATIBILITY_ROOT, "models/composed-beast-document-reader.yaml")
    setup = load_model(_COMPATIBILITY_ROOT, "models/composed-beast-document-provisioning.yaml")
    raw = copy.deepcopy(_case(_PARTIAL_ROOT).raw)
    raw["model"] = "models/composed-beast-document-reader.yaml"
    raw["given"] = {
        "provisioningModel": "models/composed-beast-document-provisioning.yaml",
        "corrupt": [
            {"entity": "parallax.compatibility.Den", "key": 1, "member": ["name"], "value": 7}
        ],
    }
    case = Case(Path("probe.yaml"), raw, reader, provisioning_model=setup)

    provider = _provisioned(case)

    (den,) = provider.loads["den_document"]
    assert den["payload"] == {"name": 7}


def test_preflight_judges_fixture_literals_by_the_setup_model() -> None:
    case = _case(_PARTIAL_ROOT)
    preflight_case_literals(case)
    fixtures = copy.deepcopy(dict(case.setup_model.fixtures))
    fixtures["parallax.compatibility.Bear"][0]["id"] = "two"
    damaged_setup = Model(case.setup_model.path, case.setup_model.descriptor, fixtures)
    damaged = Case(case.path, case.raw, case.model, provisioning_model=damaged_setup)

    with pytest.raises(CaseFailure, match=r"fixtures\.parallax\.compatibility\.Bear\[0\]\.id"):
        preflight_case_literals(damaged)


def _validate_with(tmp_path: Path, case_name: str, provisioning_model: str) -> list[str]:
    core = tmp_path / "core"
    shutil.copytree(_REPO_ROOT / "core", core)
    case_path = core / "compatibility" / "cases" / case_name
    document = yaml.safe_load(case_path.read_text(encoding="utf-8"))
    document["given"]["provisioningModel"] = provisioning_model
    case_path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return validate_tree(core / "compatibility")


def test_a_missing_provisioning_model_is_refused_statically(tmp_path: Path) -> None:
    errors = _validate_with(tmp_path, _PARTIAL_ROOT, "models/composed-beast-absent.yaml")

    assert any(
        _PARTIAL_ROOT in error and "models/composed-beast-absent.yaml does not exist" in error
        for error in errors
    )
