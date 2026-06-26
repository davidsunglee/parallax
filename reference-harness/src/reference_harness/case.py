"""In-memory representations of a model descriptor and a compatibility case.

A :class:`Case` binds together everything the runner needs: the parsed case
envelope, the model descriptor it references, and the fixture rows for that
model. The model descriptor is a pure metamodel document (an instance of
``metamodel.schema.json``); fixture rows live in a sibling
``fixtures/<model-stem>.yaml`` file, keyed by class name.

A descriptor declares EITHER a single ``entity`` (Phase 1/2 models) OR an
``entities`` list (Phase 3+, so relationships can name sibling entities). The
:class:`Model` normalizes both into a uniform list of :class:`Entity` views; the
single-entity convenience properties (``class_name``/``table``/``attributes``/
``rows``) resolve to the model's *root* entity (the first declared entity, which
the single-entity cases always query).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class Entity:
    """A single entity within a model descriptor, plus its fixture rows."""

    definition: dict[str, Any]
    rows: list[dict[str, Any]] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.definition["name"]

    @property
    def table(self) -> str:
        return self.definition["table"]

    @property
    def attributes(self) -> list[dict[str, Any]]:
        return self.definition["attributes"]

    @property
    def relationships(self) -> list[dict[str, Any]]:
        return self.definition.get("relationships", [])

    def attribute_by_name(self, name: str) -> dict[str, Any]:
        for attribute in self.attributes:
            if attribute["name"] == name:
                return attribute
        raise KeyError(f"{self.name} has no attribute {name!r}")

    def relationship_by_name(self, name: str) -> dict[str, Any]:
        for relationship in self.relationships:
            if relationship["name"] == name:
                return relationship
        raise KeyError(f"{self.name} has no relationship {name!r}")


@dataclass(frozen=True)
class Model:
    """A parsed model descriptor plus its fixture rows.

    Supports both the single-``entity`` and the multi-``entities`` descriptor
    shapes. The convenience single-entity properties resolve to the root entity
    (the first declared one) so the Phase 1/2 runner path is unchanged.
    """

    path: Path
    descriptor: dict[str, Any]
    fixtures: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    @property
    def entity_defs(self) -> list[dict[str, Any]]:
        if "entities" in self.descriptor:
            return self.descriptor["entities"]
        return [self.descriptor["entity"]]

    @property
    def entities(self) -> list[Entity]:
        return [
            Entity(definition=definition, rows=self.fixtures.get(definition["name"], []))
            for definition in self.entity_defs
        ]

    def entity(self, name: str) -> Entity:
        for entity in self.entities:
            if entity.name == name:
                return entity
        raise KeyError(f"model {self.path.name} has no entity {name!r}")

    @property
    def root_entity(self) -> Entity:
        """The first declared entity — the one single-entity cases query."""
        return self.entities[0]

    # --- single-entity convenience (root entity) ---------------------------

    @property
    def entity_def(self) -> dict[str, Any]:
        return self.root_entity.definition

    @property
    def class_name(self) -> str:
        return self.root_entity.name

    @property
    def table(self) -> str:
        return self.root_entity.table

    @property
    def attributes(self) -> list[dict[str, Any]]:
        return self.root_entity.attributes

    @property
    def rows(self) -> list[dict[str, Any]]:
        """Fixture rows for this model's root class (empty if none authored)."""
        return self.root_entity.rows


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
    def golden_sql(self) -> dict[str, str | list[str]]:
        return self.raw["goldenSql"]

    def golden_statements(self, dialect: str) -> list[str]:
        """The ordered golden SQL statements for *dialect* (1+ per case)."""
        value = self.golden_sql[dialect]
        return [value] if isinstance(value, str) else list(value)

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
    def expected_graph(self) -> dict[str, list[dict[str, Any]]] | None:
        return self.raw.get("expectedGraph")

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
