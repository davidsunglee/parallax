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

    # --- groups (given / when / then) --------------------------------------

    @property
    def given(self) -> dict[str, Any]:
        """The setup group: ambient world-state established before the action.

        Holds ``fixtures`` (whether to load the model's fixtures), ``apply`` (naive
        statement entries a conflict case runs verbatim before the golden UPDATE),
        and ``fault`` (a boundary case's injected fault). Absent for a case that
        starts from the model's default fixtures and injects nothing.
        """
        return self.raw.get("given", {})

    @property
    def when(self) -> dict[str, Any]:
        """The action group: the action under test and how the client performs it.

        Holds exactly one action member per shape (``operation`` | ``writeSequence``
        | ``scenario`` | ``coherence`` | ``concurrency`` | ``boundary`` | ``attempts``
        | ``write``) plus the context members ``uow`` / ``at`` / ``observedInZ`` /
        ``equivalentEncodings``.
        """
        return self.raw.get("when", {})

    @property
    def then(self) -> dict[str, Any]:
        """The assertions group: everything the case asserts after the action runs.

        Holds ``statements`` (the golden SQL entries), ``referenceSql``, the observed
        data (``rows`` / ``graph`` / ``tableState``), the counts/codes (``affectedRows``
        / ``errorClass`` / ``nativeCode`` / ``roundTrips``), the boundary ``outcome``,
        and the comparison ``tolerance``.
        """
        return self.raw.get("then", {})

    @property
    def shape(self) -> str | None:
        """The explicit case-shape discriminator (top-level ``shape``).

        Cases are self-describing: the ``is_*`` booleans read this field directly
        rather than sniffing which action keys happen to be present.
        """
        return self.raw.get("shape")

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

        A case MAY carry a ``when.uow`` block
        (``{"concurrency": "locking" | "optimistic"}``) declaring the mode its
        golden SQL runs under. The block is DESCRIPTIVE — the harness executes the
        authored golden SQL either way — so this accessor exists for
        self-description / tooling, not to change execution.
        """
        return self.when.get("uow", {})

    @property
    def concurrency_mode(self) -> str:
        """The declared unit-of-work concurrency mode (``locking`` default | ``optimistic``).

        Named ``concurrency_mode`` to avoid clashing with :attr:`concurrency`
        (the two-connection choreography of an error case).
        """
        return self.uow.get("concurrency", "locking")

    @property
    def operation(self) -> dict[str, Any]:
        return self.when["operation"]

    @property
    def is_write_sequence(self) -> bool:
        """True for a milestone-chaining write case (Phase 5, m-audit-write).

        A write-sequence case carries ``when.writeSequence`` (ordered mutations) and
        a ``then.tableState`` instead of an operation + ``then.rows``.
        """
        return self.shape == "writeSequence"

    @property
    def write_sequence(self) -> list[dict[str, Any]]:
        return self.when.get("writeSequence", [])

    @property
    def expected_table_state(self) -> dict[str, list[dict[str, Any]]]:
        return self.then.get("tableState", {})

    @property
    def load_fixtures(self) -> bool:
        """Whether the case loads the model's fixtures first (``given.fixtures``).

        Defaults to ``False`` (the m-audit-write milestone-chaining and m-unit-work batched-insert
        cases build their own state from an empty schema). The m-detach detached-update
        merge-back case sets it ``True`` so the original persisted row exists
        before the merge-back DML mutates it.
        """
        return bool(self.given.get("fixtures", False))

    @property
    def is_conflict(self) -> bool:
        """True for an m-opt-lock optimistic-lock conflict / success case (Phase 7).

        A single-attempt conflict carries ``when.write`` + ``then.affectedRows`` (the
        affected-row count a golden ``UPDATE`` leaves behind) and an OPTIONAL out-of-band
        ``given.apply`` (a concurrent mutation, e.g. a version bump) instead of an
        operation + ``then.rows`` — OR an ordered ``when.attempts`` retry sequence
        (each attempt carrying its own golden UPDATE + affected-row count) that
        proves the stale-then-retry contract.
        """
        return self.shape == "conflict"

    @property
    def attempts(self) -> list[dict[str, Any]]:
        """The ordered optimistic-lock UPDATE attempts of a retry conflict case.

        Empty for the single-attempt conflict form. Each attempt carries its own
        golden ``statements`` entry, its ``write``, and its ``affectedRows`` count.
        """
        return self.when.get("attempts", [])

    @property
    def apply(self) -> list[dict[str, Any]]:
        """The out-of-band naive statement entries a conflict case applies before
        the golden UPDATE (``given.apply``).

        Each entry is a ``{sql, binds}`` statement whose ``sql`` is a plain string
        (dialect-agnostic naive SQL, run verbatim on every dialect); ``binds`` is
        authored once and defaults to ``[]``.
        """
        return self.given.get("apply", [])

    @property
    def write(self) -> dict[str, Any] | None:
        """The single-attempt conflict's neutral write input (``when.write``)."""
        return self.when.get("write")

    @property
    def at(self) -> Any:
        """A single-form temporal conflict close's instant (``when.at``)."""
        return self.when.get("at")

    @property
    def observed_in_z(self) -> Any:
        """A single-form temporal conflict close's observed in_z (``when.observedInZ``)."""
        return self.when.get("observedInZ")

    @property
    def expected_affected_rows(self) -> int | None:
        return self.then.get("affectedRows")

    @property
    def is_scenario(self) -> bool:
        """True for a scenario case (Phase 6 — unit-of-work / cache / identity shape).

        A scenario case carries ``when.scenario`` (an ordered list of operation
        steps with per-step round-trip counts) instead of a single operation;
        golden SQL lives per step (as each step's ``statements``).
        """
        return self.shape == "scenario"

    @property
    def scenario(self) -> list[dict[str, Any]]:
        return self.when.get("scenario", [])

    @property
    def is_boundary(self) -> bool:
        """True for an m-auto-retry/m-opt-lock bounded-automatic-retry boundary case (Phase 4).

        A boundary case carries ``when.boundary`` (the portable unit-of-work actions)
        and a ``then.outcome`` (the portable outcome) instead of an operation /
        writeSequence / etc.; it is always ``lane: api-conformance`` (the m-case-format
        harness cannot provoke its injected-fault / retry-loop observable), so it is
        schema-validated but not executed.
        """
        return self.shape == "boundary"

    @property
    def boundary(self) -> list[dict[str, Any]]:
        return self.when.get("boundary", [])

    @property
    def fault(self) -> str | None:
        """The portable fault a boundary case injects at the DB-port seam, or None."""
        return self.given.get("fault")

    @property
    def outcome(self) -> str | None:
        """The portable outcome a boundary case asserts (``committed`` / error kind)."""
        return self.then.get("outcome")

    @property
    def is_coherence(self) -> bool:
        """True for a cross-process cache-coherence case (Phase 11).

        A coherence case carries ``when.coherence`` — a two-node operation sequence
        (run over two connections to one database) instead of a single operation;
        golden SQL lives per step, and the final node-B re-fetch asserts
        ``observeRows`` (node A's committed write).
        """
        return self.shape == "coherence"

    @property
    def coherence(self) -> list[dict[str, Any]]:
        return self.when.get("coherence", [])

    @property
    def is_error(self) -> bool:
        """True for an m-db-error error-code classification case.

        An error case carries ``then.errorClass`` (the neutral category a triggered
        DB error MUST classify to) plus a ``then.nativeCode`` witness keyed by
        dialect. It triggers a real error EITHER single-connection (ordered
        ``then.statements`` whose last statement raises -- ``uniqueViolation``) OR
        two-connection (a ``when.concurrency`` choreography -- ``deadlock`` /
        ``lockWaitTimeout``).
        """
        return self.shape == "error"

    @property
    def error_class(self) -> str | None:
        return self.then.get("errorClass")

    @property
    def expected_native_code(self) -> dict[str, Any]:
        """Per-dialect native code the trigger MUST raise (SQLSTATE / errno)."""
        return self.then.get("nativeCode", {})

    @property
    def concurrency(self) -> dict[str, Any] | None:
        """The two-connection choreography for deadlock / timeout cases (else None).

        ``{"rounds": [ {"A": step, "B": step}, ... ]}`` where each ``step`` carries
        ``statements`` ({sql, binds} entries), an optional ``kind``, and an optional
        ``expectRows``. Rounds are barrier-separated; a node absent from a round does
        nothing that round. Shared by the error/concurrency shape (``deadlock`` /
        ``lockWaitTimeout``) and the concurrency-success shape
        (:attr:`is_concurrency_success`).
        """
        return self.when.get("concurrency")

    @property
    def is_concurrency_success(self) -> bool:
        """True for an m-read-lock behavioral read-lock concurrency-SUCCESS case.

        A concurrency-success case carries a ``when.concurrency`` choreography with NO
        ``then.errorClass`` (the discriminator that keeps it distinct from an
        error/concurrency case). It runs the barrier-separated rounds on two held
        non-autocommit sessions and asserts that NO error is raised — each read
        step's optional ``expectRows`` observed on its HELD session. Proves the
        shared read lock is COMPATIBLE with a second reader (``m-read-lock-007``) and that an
        unlocked projection ADMITS a writer (``m-read-lock-008``), the non-error counterpart to
        the error branch's lock CONTENTION (``m-read-lock-006``).
        """
        return self.shape == "concurrencySuccess"

    @property
    def equivalent_encodings(self) -> list[dict[str, Any]]:
        """Alternate surface encodings that MUST canonicalize to ``operation``.

        Optional. Each entry is a full operation node authored in a different
        surface shape (e.g. a prefix vs a fluent spelling, or differently-ordered
        object keys); the runner asserts every one collapses to the canonical
        ``operation`` via the serde seam, proving precedence/serialization
        fidelity without a database.
        """
        return self.when.get("equivalentEncodings", [])

    def golden_entries(self) -> list[dict[str, Any]]:
        """The ordered golden statement entries (``then.statements``).

        Each entry is a ``{sql, binds}`` object whose ``sql`` is a dialect-keyed map
        (``postgres`` / ``mariadb``) and whose ``binds`` are authored once
        (dialect-agnostic), defaulting to ``[]``.
        """
        return self.then.get("statements", [])

    def golden_statements(self, dialect: str) -> list[str]:
        """The ordered golden SQL statements for *dialect* (1+ per case).

        The single statement-entry normalization point: reads each entry's per-dialect
        ``sql`` text in authored order.
        """
        return [entry["sql"][dialect] for entry in self.golden_entries()]

    def statement_binds(self, index: int, dialect: str | None = None) -> list[Any]:
        """The authored binds for golden statement *index* (default ``[]``).

        ``binds`` follows the same scalar-or-dialect-keyed polymorphism as ``sql``:
        a flat list when the bind holes are shared across dialects, OR a
        dialect-keyed map (``postgres`` / ``mariadb``) when the hole structure
        diverges (a Postgres per-segment JSON key list vs a MariaDB single
        ``'$.a.b'`` path bind). When a map, this resolves the list for *dialect*;
        *dialect* is REQUIRED in that case (a flat list ignores it).
        """
        entries = self.golden_entries()
        if index >= len(entries):
            return []
        raw = entries[index].get("binds", [])
        if isinstance(raw, dict):
            if dialect is None:
                raise KeyError(
                    f"{self.path.name}: statement {index} has dialect-keyed binds; "
                    f"a dialect is required to resolve them"
                )
            if dialect not in raw:
                raise KeyError(
                    f"{self.path.name}: statement {index} binds map has no key "
                    f"{dialect!r} (keys: {sorted(raw)})"
                )
            return list(raw[dialect])
        return list(raw)

    @property
    def golden_dialects(self) -> set[str]:
        """The dialects every golden statement entry declares (empty if none).

        Computed as the intersection across entries, so ``golden_statements(d)`` is
        defined for every ``d`` this returns.
        """
        entries = self.golden_entries()
        dialect_sets = [set(e["sql"]) for e in entries if isinstance(e.get("sql"), dict)]
        if not dialect_sets:
            return set()
        return set.intersection(*dialect_sets)

    def reference_sql_for(self, dialect: str) -> str | None:
        """The independent naive oracle for *dialect*, or ``None`` if unauthored.

        ``referenceSql`` is a plain string when one naive spelling runs verbatim on
        every dialect (the authored default), OR a dialect-keyed map when the naive
        spelling itself is dialect-specific (the structured-document extraction:
        Postgres spells it ``->>`` over a bare key, MariaDB
        ``nullif(json_unquote(json_extract(col, '$.path')), 'null')`` — a different
        function family from the ``json_value`` golden, with ``nullif(…, 'null')``
        collapsing the JSON ``null`` leaf).
        When a map, its keys MUST equal the golden ``sql`` map's keys
        (``case_runner._assert_reference_sql_dialect_keys``), so resolving a dialect
        the golden ``sql`` declares always succeeds. A request for a *dialect* the map
        does NOT carry is a loud :class:`KeyError` — never a silently skipped oracle,
        which would let a per-dialect golden go unchecked. An entirely UNAUTHORED
        ``referenceSql`` (absent) still yields ``None``: a trivial case legitimately
        runs no oracle.
        """
        raw = self.then.get("referenceSql")
        if raw is None:
            return None
        if isinstance(raw, dict):
            if dialect not in raw:
                raise KeyError(
                    f"{self.path.name}: referenceSql map has no key {dialect!r} "
                    f"(keys: {sorted(raw)})"
                )
            return raw[dialect]
        return raw

    @property
    def expected_rows(self) -> list[dict[str, Any]]:
        return self.then.get("rows", [])

    @property
    def expected_graph(self) -> dict[str, list[dict[str, Any]]] | None:
        return self.then.get("graph")

    @property
    def round_trips(self) -> int:
        return self.then.get("roundTrips", 1)

    @property
    def tolerance(self) -> Decimal | None:
        """Absolute numeric comparison tolerance, or ``None`` for exact.

        Declared only by cases whose results are inherently inexact (stddev /
        variance / repeating-decimal avg) and so cannot be authored exactly.
        Authored as a plain number; parsed through ``str`` so a YAML ``1.0e-9``
        becomes ``Decimal('1.0E-9')`` without float noise.
        """
        raw = self.then.get("tolerance")
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
