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
    def lane(self) -> str:
        """Which executor satisfies this case (``harness`` default | ``api-conformance``).

        A ``harness``-lane case executes as today; an ``api-conformance``-lane case
        (every boundary case, plus the read-lock matrix reads
        ``m-read-lock-002``-``m-read-lock-005``) is schema-validated by the
        m-case-format harness but NOT executed — each language's API Conformance
        Suite satisfies it. :func:`case_runner.run_case` early-returns for the
        api-conformance lane.
        """
        return self.raw.get("lane", "harness")

    @property
    def uow(self) -> dict[str, Any]:
        """The declared unit-of-work config (m-unit-work strategy selection), or empty.

        A case MAY carry a top-level ``uow`` block
        (``{"concurrency": "locking" | "optimistic"}``) declaring the mode its
        golden SQL runs under. The block is DESCRIPTIVE — the harness executes the
        authored golden SQL either way — so this accessor exists for
        self-description / tooling, not to change execution.
        """
        return self.raw.get("uow", {})

    @property
    def concurrency_mode(self) -> str:
        """The declared unit-of-work concurrency mode (``locking`` default | ``optimistic``).

        Named ``concurrency_mode`` to avoid clashing with :attr:`concurrency`
        (the two-connection choreography of an error case).
        """
        return self.uow.get("concurrency", "locking")

    @property
    def operation(self) -> dict[str, Any]:
        return self.raw["operation"]

    @property
    def is_write_sequence(self) -> bool:
        """True for a milestone-chaining write case (Phase 5, m-audit-write).

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

        Defaults to ``False`` (the m-audit-write milestone-chaining and m-unit-work batched-insert
        cases build their own state from an empty schema). The m-detach detached-update
        merge-back case sets it ``True`` so the original persisted row exists
        before the merge-back DML mutates it.
        """
        return bool(self.raw.get("loadFixtures", False))

    @property
    def is_conflict(self) -> bool:
        """True for an m-opt-lock optimistic-lock conflict / success case (Phase 7).

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
        """True for a scenario case (Phase 6 — unit-of-work / cache / identity shape).

        A scenario case carries a ``scenario`` (an ordered list of operation
        steps with per-step round-trip counts) instead of a single
        ``operation`` + ``goldenSql``; golden SQL lives per step.
        """
        return "scenario" in self.raw

    @property
    def scenario(self) -> list[dict[str, Any]]:
        return self.raw.get("scenario", [])

    @property
    def is_boundary(self) -> bool:
        """True for an m-auto-retry/m-opt-lock bounded-automatic-retry boundary case (Phase 4).

        A boundary case carries a ``boundary`` (the portable unit-of-work actions)
        and an ``expect`` (the portable outcome) instead of an ``operation`` /
        ``writeSequence`` / etc.; it is always ``lane: api-conformance`` (the m-case-format
        harness cannot provoke its injected-fault / retry-loop observable), so it is
        schema-validated but not executed.
        """
        return "boundary" in self.raw

    @property
    def boundary(self) -> list[dict[str, Any]]:
        return self.raw.get("boundary", [])

    @property
    def inject(self) -> str | None:
        """The portable fault a boundary case injects at the DB-port seam, or None."""
        return self.raw.get("inject")

    @property
    def expect(self) -> str | None:
        """The portable outcome a boundary case asserts (``committed`` / error kind)."""
        return self.raw.get("expect")

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
    def is_error(self) -> bool:
        """True for an m-db-error error-code classification case.

        An error case carries an ``errorClass`` (the neutral category a triggered
        DB error MUST classify to) plus an ``expectedNativeCode`` witness keyed by
        dialect, instead of an ``operation``/``expectedRows``. It triggers a real
        error EITHER single-connection (ordered ``goldenSql`` whose last statement
        raises -- ``uniqueViolation``) OR two-connection (a ``concurrency``
        choreography -- ``deadlock`` / ``lockWaitTimeout``).
        """
        return "errorClass" in self.raw

    @property
    def error_class(self) -> str | None:
        return self.raw.get("errorClass")

    @property
    def expected_native_code(self) -> dict[str, Any]:
        """Per-dialect native code the trigger MUST raise (SQLSTATE / errno)."""
        return self.raw.get("expectedNativeCode", {})

    @property
    def concurrency(self) -> dict[str, Any] | None:
        """The two-connection choreography for deadlock / timeout cases (else None).

        ``{"rounds": [ {"A": step, "B": step}, ... ]}`` where each ``step`` is
        ``{"goldenSql": {dialect: stmt}, "binds": [...], "expectRows": [...]}``.
        Rounds are barrier-separated; a node absent from a round does nothing that
        round. Shared by the error/concurrency shape (``deadlock`` / ``lockWaitTimeout``)
        and the concurrency-success shape (:attr:`is_concurrency_success`).
        """
        return self.raw.get("concurrency")

    @property
    def is_concurrency_success(self) -> bool:
        """True for an m-read-lock behavioral read-lock concurrency-SUCCESS case.

        A concurrency-success case carries a ``concurrency`` choreography with NO
        ``errorClass`` (the discriminator that keeps it distinct from an
        error/concurrency case). It runs the barrier-separated rounds on two held
        non-autocommit sessions and asserts that NO error is raised — each read
        step's optional ``expectRows`` observed on its HELD session. Proves the
        shared read lock is COMPATIBLE with a second reader (``m-read-lock-007``) and that an
        unlocked projection ADMITS a writer (``m-read-lock-008``), the non-error counterpart to
        the error branch's lock CONTENTION (``m-read-lock-006``).
        """
        return self.concurrency is not None and "errorClass" not in self.raw

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
