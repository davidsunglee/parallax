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
from decimal import Decimal
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

    @property
    def value_objects(self) -> list[dict[str, Any]]:
        """Embedded composites mapped to dialect-native document columns."""
        return self.definition.get("valueObjects", [])

    @property
    def as_of_attributes(self) -> list[dict[str, Any]]:
        return self.definition.get("asOfAttributes", [])

    @property
    def is_temporal(self) -> bool:
        return bool(self.as_of_attributes)

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
    def is_write_sequence(self) -> bool:
        """True for a milestone-chaining write case (Phase 5, M7).

        A write-sequence case carries a ``writeSequence`` (ordered mutations) and
        an ``expectedTableState`` instead of an ``operation`` + ``expectedRows``.
        """
        return "writeSequence" in self.raw

    @property
    def write_sequence(self) -> list[dict[str, Any]]:
        return self.raw.get("writeSequence", [])

    @property
    def expected_table_state(self) -> dict[str, list[dict[str, Any]]]:
        return self.raw.get("expectedTableState", {})

    @property
    def load_fixtures(self) -> bool:
        """Whether a writeSequence case loads the model's fixtures first (Phase 7).

        Defaults to ``False`` (the M7 milestone-chaining and M8 batched-insert
        cases build their own state from an empty schema). The M9 detached-update
        merge-back case sets it ``True`` so the original persisted row exists
        before the merge-back DML mutates it.
        """
        return bool(self.raw.get("loadFixtures", False))

    @property
    def is_conflict(self) -> bool:
        """True for an M10 optimistic-lock conflict / success case (Phase 7).

        A conflict case carries ``expectedAffectedRows`` (the affected-row count a
        golden ``UPDATE`` leaves behind) and an OPTIONAL out-of-band
        ``precondition`` (a concurrent mutation, e.g. a version bump) instead of an
        ``operation`` + ``expectedRows`` — OR an ordered ``attempts`` retry
        sequence (each attempt carrying its own golden UPDATE + affected-row
        count) that proves the stale-then-retry contract.
        """
        return "expectedAffectedRows" in self.raw or "attempts" in self.raw

    @property
    def attempts(self) -> list[dict[str, Any]]:
        """The ordered optimistic-lock UPDATE attempts of a retry conflict case.

        Empty for the single-attempt conflict form. Each attempt carries its own
        dialect-keyed ``goldenSql``, ``binds``, and ``expectedAffectedRows``.
        """
        return self.raw.get("attempts", [])

    @property
    def precondition(self) -> list[str]:
        """The out-of-band SQL a conflict case applies before the golden UPDATE."""
        raw = self.raw.get("precondition")
        if raw is None:
            return []
        return [raw] if isinstance(raw, str) else list(raw)

    @property
    def precondition_binds(self) -> list[Any]:
        return self.raw.get("preconditionBinds", [])

    @property
    def expected_affected_rows(self) -> int | None:
        return self.raw.get("expectedAffectedRows")

    @property
    def is_scenario(self) -> bool:
        """True for an M8 cache/identity scenario case (Phase 6).

        A scenario case carries a ``scenario`` (an ordered list of operation
        steps with per-step round-trip counts) instead of a single
        ``operation`` + ``goldenSql``; golden SQL lives per step.
        """
        return "scenario" in self.raw

    @property
    def scenario(self) -> list[dict[str, Any]]:
        return self.raw.get("scenario", [])

    @property
    def is_coherence(self) -> bool:
        """True for a cross-process cache-coherence case (Phase 11).

        A coherence case carries a ``coherence`` two-node operation sequence (run
        over two connections to one database) instead of a single
        ``operation`` + ``goldenSql``; golden SQL lives per step, and the final
        node-B re-fetch asserts ``observeRows`` (node A's committed write).
        """
        return "coherence" in self.raw

    @property
    def coherence(self) -> list[dict[str, Any]]:
        return self.raw.get("coherence", [])

    @property
    def equivalent_encodings(self) -> list[dict[str, Any]]:
        """Alternate surface encodings that MUST canonicalize to ``operation``.

        Optional. Each entry is a full operation node authored in a different
        surface shape (e.g. a prefix vs a fluent spelling, or differently-ordered
        object keys); the runner asserts every one collapses to the canonical
        ``operation`` via the serde seam, proving precedence/serialization
        fidelity without a database.
        """
        return self.raw.get("equivalentEncodings", [])

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

    @property
    def tolerance(self) -> Decimal | None:
        """Absolute numeric comparison tolerance, or ``None`` for exact.

        Declared only by cases whose results are inherently inexact (stddev /
        variance / repeating-decimal avg) and so cannot be authored exactly.
        Authored as a plain number; parsed through ``str`` so a YAML ``1.0e-9``
        becomes ``Decimal('1.0E-9')`` without float noise.
        """
        raw = self.raw.get("tolerance")
        return None if raw is None else Decimal(str(raw))


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
