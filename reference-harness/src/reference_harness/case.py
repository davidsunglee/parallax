"""In-memory representations of a model descriptor and a compatibility case.

A :class:`Case` binds together everything the runner needs: the parsed case
envelope, the model descriptor it references, and the fixture rows for that
model. The model descriptor is a pure metamodel document (an instance of
``metamodel.schema.json``); fixture rows live in a sibling
``fixtures/<model-stem>.yaml`` file, keyed by class name.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class Model:
    """A parsed model descriptor plus its fixture rows."""

    path: Path
    descriptor: dict[str, Any]
    fixtures: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    @property
    def entity_def(self) -> dict[str, Any]:
        return self.descriptor["entity"]

    @property
    def class_name(self) -> str:
        return self.entity_def["name"]

    @property
    def table(self) -> str:
        return self.entity_def["table"]

    @property
    def attributes(self) -> list[dict[str, Any]]:
        return self.entity_def["attributes"]

    @property
    def rows(self) -> list[dict[str, Any]]:
        """Fixture rows for this model's primary class (empty if none authored)."""
        return self.fixtures.get(self.class_name, [])


@dataclass(frozen=True)
class Case:
    """A parsed compatibility case bound to its model + fixtures."""

    path: Path
    raw: dict[str, Any]
    model: Model

    @property
    def tags(self) -> list[str]:
        return self.raw.get("tags", [])

    @property
    def operation(self) -> dict[str, Any]:
        return self.raw["operation"]

    @property
    def golden_sql(self) -> dict[str, str]:
        return self.raw["goldenSql"]

    @property
    def binds(self) -> list[Any]:
        return self.raw.get("binds", [])

    @property
    def reference_sql(self) -> str | None:
        return self.raw.get("referenceSql")

    @property
    def expected_rows(self) -> list[dict[str, Any]]:
        return self.raw.get("expectedRows", [])

    @property
    def round_trips(self) -> int:
        return self.raw.get("roundTrips", 1)


def _load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_model(compatibility_root: Path, model_rel: str) -> Model:
    """Load a model descriptor (relative to ``core/compatibility``) + its fixtures."""
    model_path = (compatibility_root / model_rel).resolve()
    descriptor = _load_yaml(model_path)

    fixtures_path = compatibility_root / "fixtures" / f"{model_path.stem}.yaml"
    fixtures: dict[str, list[dict[str, Any]]] = {}
    if fixtures_path.is_file():
        loaded = _load_yaml(fixtures_path)
        if loaded:
            fixtures = loaded
    return Model(path=model_path, descriptor=descriptor, fixtures=fixtures)


def load_case(compatibility_root: Path, case_path: Path) -> Case:
    """Load a single compatibility case, resolving and loading its model."""
    raw = _load_yaml(case_path)
    model = load_model(compatibility_root, raw["model"])
    return Case(path=case_path.resolve(), raw=raw, model=model)


def discover_cases(compatibility_root: Path) -> list[Case]:
    """Discover and load every case under ``cases/`` (sorted by path)."""
    cases_dir = compatibility_root / "cases"
    case_files = sorted(cases_dir.glob("**/*.yaml")) + sorted(cases_dir.glob("**/*.yml"))
    return [load_case(compatibility_root, p) for p in sorted(set(case_files))]
