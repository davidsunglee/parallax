"""In-memory representations of a model descriptor and a compatibility case.

A :class:`Case` binds together everything the runner needs: the parsed case
envelope, the model descriptor it references, and the fixture rows for that
model. The model descriptor is a pure metamodel document (an instance of
``metamodel.schema.json``); fixture rows live in a sibling
``fixtures/<model-stem>.yaml`` file, keyed by class name.

A descriptor declares either a single ``entity`` or an ``entities`` list. The
:class:`Model` normalizes both into a uniform list of :class:`Entity` views; the
single-entity convenience properties (``class_name``/``table``/``attributes``/
``rows``) resolve to the model's *root* entity (the first declared entity, which
the single-entity cases always query).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from decimal import Decimal
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING, Any, NoReturn

from .corpus_yaml import read_corpus_yaml
from .naming import default_column_name
from .temporality import derive_temporal_structure, temporal_axes

if TYPE_CHECKING:
    from .storage_layout import StorageLayout


def _entity_identity(definition: dict[str, Any]) -> str:
    """Return one definition's canonical Entity spelling."""
    namespace = definition.get("namespace")
    return definition["name"] if namespace is None else f"{namespace}.{definition['name']}"


def _definition_index(entity_defs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Index exact Entity identities and only unambiguous local aliases."""
    result = {_entity_identity(definition): definition for definition in entity_defs}
    local_counts: dict[str, int] = {}
    for definition in entity_defs:
        name = definition["name"]
        local_counts[name] = local_counts.get(name, 0) + 1
    for definition in entity_defs:
        if local_counts[definition["name"]] == 1:
            result[definition["name"]] = definition
    return result


def _resolve_definition(
    entity_defs: list[dict[str, Any]], owner: dict[str, Any], reference: str
) -> dict[str, Any]:
    """Resolve an exact or owner-relative Entity reference without global fallback."""
    if "." in reference:
        identity = reference
    else:
        namespace = owner.get("namespace")
        identity = reference if namespace is None else f"{namespace}.{reference}"
    try:
        return _definition_index(entity_defs)[identity]
    except KeyError as exc:
        raise KeyError(
            f"{_entity_identity(owner)} references unknown entity {reference!r}"
        ) from exc


def _compile_attribute(attribute: dict[str, Any]) -> dict[str, Any]:
    """Compile one authored Attribute while preserving canonical metadata facts."""
    compiled = copy.deepcopy(attribute)
    compiled.setdefault("column", default_column_name(compiled["name"]))
    return compiled


def _compile_value_object(value_object: dict[str, Any], *, top_level: bool) -> dict[str, Any]:
    """Compile conventional storage defaults without changing the Value Object algebra."""
    compiled = copy.deepcopy(value_object)
    if top_level:
        compiled.setdefault("column", default_column_name(compiled["name"]))
    compiled.setdefault("multiplicity", "one")
    compiled["attributes"] = [copy.deepcopy(item) for item in compiled.get("attributes", [])]
    compiled["valueObjects"] = [
        _compile_value_object(item, top_level=False) for item in compiled.get("valueObjects", [])
    ]
    return compiled


def _defining_relationships(
    entity_defs: list[dict[str, Any]],
) -> dict[tuple[str, str], tuple[dict[str, Any], dict[str, Any]]]:
    defining: dict[tuple[str, str], tuple[dict[str, Any], dict[str, Any]]] = {}
    for owner in entity_defs:
        for relationship in owner.get("relationships", []):
            if "join" in relationship:
                defining[(_entity_identity(owner), relationship["name"])] = (owner, relationship)
    return defining


def _compile_relationships(
    entity_defs: list[dict[str, Any]], owner: dict[str, Any]
) -> list[dict[str, Any]]:
    """Compile canonical declarations into directional Relationship Facet values."""
    owner_identity = _entity_identity(owner)
    defining = _defining_relationships(entity_defs)

    reverse_names: dict[tuple[str, str], str] = {}
    for reverse_owner in entity_defs:
        for relationship in reverse_owner.get("relationships", []):
            reverse_of = relationship.get("reverseOf")
            if isinstance(reverse_of, str):
                target_ref, target_relationship = reverse_of.rsplit(".", 1)
                defining_owner = _resolve_definition(entity_defs, reverse_owner, target_ref)
                reverse_names[(_entity_identity(defining_owner), target_relationship)] = (
                    relationship["name"]
                )

    adapted: list[dict[str, Any]] = []
    inverse = {
        "one-to-one": "one-to-one",
        "many-to-one": "one-to-many",
        "one-to-many": "many-to-one",
    }
    for relationship in owner.get("relationships", []):
        order_by = copy.deepcopy(relationship.get("orderBy", []))
        if "join" in relationship:
            join = relationship["join"]
            target = join["target"]
            target_definition = _resolve_definition(entity_defs, owner, target["entity"])
            target_identity = _entity_identity(target_definition)
            adapted.append(
                {
                    "name": relationship["name"],
                    "cardinality": relationship["cardinality"],
                    "join": {
                        "source": {"entity": owner_identity, "attribute": join["source"]},
                        "target": {
                            "entity": target_identity,
                            "attribute": target["attribute"],
                        },
                    },
                    "reverse": reverse_names.get((owner_identity, relationship["name"])),
                    "dependent": relationship.get("dependent", False),
                    "orderBy": order_by,
                }
            )
            continue

        reverse_of = relationship["reverseOf"]
        target_ref, target_relationship = reverse_of.rsplit(".", 1)
        defining_owner = _resolve_definition(entity_defs, owner, target_ref)
        defining_owner_identity = _entity_identity(defining_owner)
        _defining_owner, defining_relationship = defining[
            (defining_owner_identity, target_relationship)
        ]
        defining_join = defining_relationship["join"]
        adapted.append(
            {
                "name": relationship["name"],
                "cardinality": inverse[defining_relationship["cardinality"]],
                "join": {
                    "source": {
                        "entity": owner_identity,
                        "attribute": defining_join["target"]["attribute"],
                    },
                    "target": {
                        "entity": defining_owner_identity,
                        "attribute": defining_join["source"],
                    },
                },
                "reverse": target_relationship,
                "dependent": False,
                "orderBy": order_by,
            }
        )
    return adapted


def _compile_definition(definition: dict[str, Any]) -> dict[str, Any]:
    """Compile one Entity into the harness's sole accepted metadata graph."""
    compiled = copy.deepcopy(definition)
    compiled["attributes"] = [
        _compile_attribute(attribute) for attribute in definition.get("attributes", [])
    ]
    compiled["valueObjects"] = [
        _compile_value_object(value_object, top_level=True)
        for value_object in definition.get("valueObjects", [])
    ]
    return compiled


def _frozen(self: Any, *_args: Any, **_kwargs: Any) -> NoReturn:  # noqa: ARG001
    """Reject every in-place mutation of a parsed-corpus container.

    The first parameter must be named ``self``: these are bound as methods on
    :class:`FrozenDict`/:class:`FrozenList`, and the type checker matches the
    overridden signatures by parameter name.
    """
    raise TypeError(
        "the parsed compatibility corpus is immutable and shared between callers; "
        "take a copy.deepcopy() of the case (or of the sub-structure being damaged) "
        "before mutating it"
    )


class FrozenDict(dict[str, Any]):
    """A read-only ``dict`` — every mutator raises :class:`TypeError`.

    A *subclass* of ``dict`` rather than a ``MappingProxyType`` on purpose. The
    harness runs ~140 ``isinstance(x, dict)`` / ``isinstance(x, list)`` shape
    tests over parsed corpus documents (``schema_validate``, ``op_validate``,
    ``sql_lint``, ``inheritance``, ``case_runner``, …); a proxy would fail every
    one of them *silently*, turning a freeze into a behavior change. A subclass
    keeps ``isinstance``, equality against plain ``dict`` literals, and C-speed
    reads, while making a write a loud error.

    ``copy.deepcopy`` deliberately yields a plain, fully-mutable ``dict`` — that
    is the sanctioned escape hatch for a negative test that needs to build
    malformed input (see :func:`discover_cases`).
    """

    __slots__ = ()

    __setitem__ = _frozen
    __delitem__ = _frozen
    __ior__ = _frozen
    clear = _frozen
    pop = _frozen
    popitem = _frozen
    setdefault = _frozen
    update = _frozen

    def __copy__(self) -> dict[str, Any]:
        return dict(self)

    def __deepcopy__(self, memo: dict[int, Any]) -> dict[str, Any]:
        thawed: dict[str, Any] = {}
        memo[id(self)] = thawed
        for key, value in self.items():
            thawed[key] = copy.deepcopy(value, memo)
        return thawed


class FrozenList(list[Any]):
    """A read-only ``list`` — every mutator raises :class:`TypeError`.

    Companion to :class:`FrozenDict`; see that docstring for why this subclasses
    ``list`` instead of freezing to a ``tuple``. ``copy.deepcopy`` yields a
    plain, fully-mutable ``list``.
    """

    __slots__ = ()

    __setitem__ = _frozen
    __delitem__ = _frozen
    __iadd__ = _frozen
    __imul__ = _frozen
    append = _frozen
    clear = _frozen
    extend = _frozen
    insert = _frozen
    pop = _frozen
    remove = _frozen
    reverse = _frozen
    sort = _frozen

    def __copy__(self) -> list[Any]:
        return list(self)

    def __deepcopy__(self, memo: dict[int, Any]) -> list[Any]:
        thawed: list[Any] = []
        memo[id(self)] = thawed
        thawed.extend(copy.deepcopy(item, memo) for item in self)
        return thawed


def _freeze(value: Any) -> Any:
    """Recursively wrap *value*'s ``dict``/``list`` nodes in read-only views.

    Applied once, at parse time, to a whole document. The recursion is what makes
    the freeze load-bearing: ``inheritance._merge_ancestry_attributes`` splices
    the *original* ancestor attribute dicts into the list it returns, and
    ``resolve_effective_definition`` returns a non-inheritance entity's definition
    unchanged — so an aliased inner node left mutable would keep the whole graph
    writable through a side door. Scalars (including ``str``) are returned as-is.
    """
    if isinstance(value, (FrozenDict, FrozenList)):
        return value
    if isinstance(value, dict):
        return FrozenDict({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return FrozenList(_freeze(item) for item in value)
    return value


@dataclass(frozen=True)
class Entity:
    """A single entity within a model descriptor, plus its fixture rows."""

    definition: dict[str, Any]
    effective_definition: dict[str, Any] | None = field(default=None, repr=False)
    relationship_facet: tuple[dict[str, Any], ...] = field(default=(), repr=False)
    rows: list[dict[str, Any]] = field(default_factory=list)

    @property
    def runtime_facts(self) -> dict[str, Any]:
        """The ancestry-flattened declarations behind this entity's semantics.

        These answer which members, temporal axes, and tag an inheritance
        participant behaves as if it declared locally. They are not a physical
        table: column sequence, effective nullability, physical keys, and table
        membership come from :attr:`Model.storage_layout` alone.
        """
        return self.definition if self.effective_definition is None else self.effective_definition

    @property
    def name(self) -> str:
        return self.definition["name"]

    @property
    def canonical_name(self) -> str:
        return _entity_identity(self.definition)

    @property
    def table(self) -> str:
        """The physical table, or ``""`` for a tableless abstract inheritance node.

        An abstract root / abstract-subtype (m-inheritance) declares no table (its
        rows live in a concrete descendant's table), so this returns the empty
        string rather than raising — callers that provision or read physical rows
        filter abstract entities out (:attr:`is_abstract`).
        """
        return self.runtime_facts.get("table", "")

    @property
    def inheritance(self) -> dict[str, Any] | None:
        block = self.definition.get("inheritance")
        return block if isinstance(block, dict) else None

    @property
    def role(self) -> str | None:
        """This entity's inheritance role (``root`` / ``abstract-subtype`` /
        ``concrete-subtype``), or ``None`` for a non-inheritance entity."""
        block = self.inheritance
        return block.get("role") if block else None

    @property
    def is_abstract(self) -> bool:
        """True for a tableless, rowless abstract node (root / abstract-subtype)."""
        return self.role in ("root", "abstract-subtype")

    @property
    def attributes(self) -> list[dict[str, Any]]:
        return [_compile_attribute(attribute) for attribute in self.runtime_facts["attributes"]]

    @property
    def relationships(self) -> list[dict[str, Any]]:
        """Canonical accepted local defining/reverse Relationship Declarations."""
        return self.definition.get("relationships", [])

    @property
    def relationship_metadata(self) -> list[dict[str, Any]]:
        """Directional values supplied by the compiled Relationship Facet."""
        return list(self.relationship_facet)

    @property
    def value_objects(self) -> list[dict[str, Any]]:
        """Embedded composites mapped to dialect-native document columns."""
        return [
            _compile_value_object(value_object, top_level=True)
            for value_object in self.runtime_facts.get("valueObjects", [])
        ]

    @property
    def temporal_runtime_axes(self) -> list[dict[str, Any]]:
        """Physical runtime projection of the As-Of Axes the profile derives."""
        return [
            {
                "dimension": axis.dimension,
                "start_column": axis.start.column,
                "end_column": axis.end.column,
                "infinity": "infinity",
            }
            for axis in temporal_axes(self.runtime_facts)
        ]

    @property
    def is_temporal(self) -> bool:
        return bool(self.temporal_runtime_axes)

    def attribute_by_name(self, name: str) -> dict[str, Any]:
        for attribute in self.attributes:
            if attribute["name"] == name:
                return attribute
        raise KeyError(f"{self.name} has no attribute {name!r}")

    def relationship_by_name(self, name: str) -> dict[str, Any]:
        """Return one canonical accepted local Relationship Declaration."""
        for relationship in self.relationships:
            if relationship["name"] == name:
                return relationship
        raise KeyError(f"{self.name} has no relationship {name!r}")

    def relationship_metadata_by_name(self, name: str) -> dict[str, Any]:
        """Return one directional value from the compiled Relationship Facet."""
        for relationship in self.relationship_metadata:
            if relationship["name"] == name:
                return relationship
        raise KeyError(f"{self.name} has no relationship metadata {name!r}")

    def value_object_by_name(self, name: str) -> dict[str, Any]:
        """The top-level value object named *name* (m-value-object), else KeyError.

        A neutral write input (①) names a value object like a scalar attribute; it
        resolves to the single Document-tier slot the whole composite binds into,
        never to its inner members.
        """
        for value_object in self.value_objects:
            if value_object["name"] == name:
                return value_object
        raise KeyError(f"{self.name} has no value object {name!r}")


@dataclass(frozen=True)
class Model:
    """A parsed model descriptor plus its fixture rows.

    Supports both the single-``entity`` and the multi-``entities`` descriptor
    shapes. The convenience single-entity properties resolve to the root entity
    (the first declared one).
    """

    path: Path
    descriptor: dict[str, Any]
    fixtures: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    @property
    def entity_defs(self) -> list[dict[str, Any]]:
        if "entities" in self.descriptor:
            return self.descriptor["entities"]
        return [self.descriptor["entity"]]

    @cached_property
    def storage_layout(self) -> StorageLayout:
        """The independently compiled immutable physical layout graph."""
        from .storage_layout import compile_storage_layout

        return compile_storage_layout(self.entity_defs)

    def __deepcopy__(self, memo: dict[int, Any]) -> Model:
        """A copy with a thawed descriptor and no layout carried over from the source.

        Copying a model is how a caller obtains a *mutable* descriptor, so the copy
        may describe a different model than the one it was copied from. The layout
        is derived state and is re-compiled on demand from the copy's own
        descriptor; carrying the memoized graph across would silently answer for
        the source descriptor instead.
        """
        copied = Model(
            path=self.path,
            descriptor=copy.deepcopy(self.descriptor, memo),
            fixtures=copy.deepcopy(self.fixtures, memo),
        )
        memo[id(self)] = copied
        return copied

    @property
    def entities(self) -> list[Entity]:
        # Present each entity as its FLATTENED (inheritance-resolved) definition: a
        # concrete subtype does not repeat inherited attributes, so the harness
        # derives the full inherited chain (root -> ... -> self) plus, for
        # table-per-hierarchy, the synthesized tag column (m-inheritance). A
        # non-inheritance entity is returned unchanged. Imported lazily to avoid the
        # case <- value_object_resolve <- inheritance import cycle.
        from .inheritance import resolve_effective_definition

        defs = self.entity_defs
        entities: list[Entity] = []
        for definition in defs:
            effective = (
                resolve_effective_definition(defs, _entity_identity(definition))
                if isinstance(definition.get("inheritance"), dict)
                else definition
            )
            entities.append(
                Entity(
                    definition=_compile_definition(definition),
                    effective_definition=_compile_definition(effective),
                    relationship_facet=tuple(_compile_relationships(defs, effective)),
                    rows=self.fixtures.get(
                        _entity_identity(definition), self.fixtures.get(definition["name"], [])
                    ),
                )
            )
        return entities

    def entity(self, name: str) -> Entity:
        entities = self.entities
        for entity in entities:
            if entity.canonical_name == name:
                return entity
        local = [entity for entity in entities if entity.name == name]
        if len(local) == 1:
            return local[0]
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


def conflict_write_rows(attempt: dict[str, Any]) -> list[dict[str, Any]]:
    """The ordered neutral write rows one conflict attempt authors (``write``).

    A lone row object is the one-element case of the MULTI-KEY array form, whose
    rows one unit of work buffers together and the batching rule may collapse
    into a single set-based statement carrying one Key Target. Empty when the
    attempt authors no ``write`` at all.
    """
    raw = attempt.get("write")
    if raw is None:
        return []
    if isinstance(raw, list):
        return list(raw)
    return [raw]


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
        statement entries a conflict case runs verbatim before the golden write),
        and ``fault`` (a boundary case's injected fault). Absent for a case that
        starts from the model's default fixtures and injects nothing.
        """
        return self.raw.get("given", {})

    @property
    def when(self) -> dict[str, Any]:
        """The action group: the action under test and how the client performs it.

        Holds exactly one action member per shape (``operation`` | ``writeSequence``
        | ``scenario`` | ``coherence`` | ``concurrency`` | ``boundary`` | ``attempts``
        | ``write``) plus the context members ``uow`` / ``at`` / ``observedTxStart`` /
        ``observedValidStart`` / ``equivalentEncodings``.
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
        ``m-read-lock-002``, ``m-read-lock-004``, and ``m-read-lock-005``) is
        schema-validated by the
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
        """True for a milestone-chaining write case (m-txtime-write).

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

        Defaults to ``False`` (the m-txtime-write milestone-chaining and m-unit-work batched-insert
        cases build their own state from an empty schema). The m-detach detached-update
        merge-back case sets it ``True`` so the original persisted row exists
        before the merge-back DML mutates it.
        """
        return bool(self.given.get("fixtures", False))

    @property
    def is_conflict(self) -> bool:
        """True for an m-opt-lock optimistic-lock conflict or success case.

        A single-attempt conflict carries ``when.write`` + ``then.affectedRows`` (the
        affected-row count the golden write leaves behind) and an OPTIONAL out-of-band
        ``given.apply`` (a concurrent mutation, e.g. a version bump) instead of an
        operation + ``then.rows`` — OR an ordered ``when.attempts`` retry sequence
        (each attempt carrying its own golden write + affected-row count) that
        proves the stale-then-retry contract.
        """
        return self.shape == "conflict"

    @property
    def attempts(self) -> list[dict[str, Any]]:
        """The ordered optimistic-lock write attempts of a retry conflict case.

        Empty for the single-attempt conflict form. Each attempt carries its own
        golden ``statements`` entry, its ``write``, and its ``affectedRows`` count.
        """
        return self.when.get("attempts", [])

    @property
    def apply(self) -> list[dict[str, Any]]:
        """The out-of-band naive statement entries a case applies after its own
        provisioning and before its lane's first golden statement or step
        (``given.apply``).

        Each entry is a ``{sql, binds}`` statement whose ``sql`` is a plain string
        (dialect-agnostic naive SQL, run verbatim on every dialect); ``binds`` is
        authored once and defaults to ``[]``. What the entries stand for is the
        lane's: a concurrent transaction's mutation on a conflict case, and
        otherwise state no authored member of the model could produce.
        """
        return self.given.get("apply", [])

    @property
    def write_rows(self) -> list[dict[str, Any]]:
        """The single-attempt conflict's neutral write input (``when.write``) as the
        ordered row list both authored forms denote.

        Empty for the retry form, whose rows live per attempt
        (:func:`conflict_write_rows` reads those).
        """
        return conflict_write_rows(self.when)

    @property
    def conflict_mutation(self) -> str:
        """The keyed verb a NON-temporal conflict case writes (``when.mutation``).

        ``update`` by default; ``delete`` selects the versioned keyed DELETE,
        whose golden carries no ``set`` clause. A temporal target ignores this —
        its conflict write is always the milestone close.
        """
        return self.when.get("mutation", "update")

    @property
    def at(self) -> Any:
        """A single-form temporal conflict close's instant (``when.at``)."""
        return self.when.get("at")

    @property
    def observed_tx_start(self) -> Any:
        """A temporal conflict close's observed Transaction-Time start."""
        return self.when.get("observedTxStart")

    @property
    def observed_valid_start(self) -> Any:
        """A temporal conflict close's observed Valid-Time start.

        Paired with ``observedTxStart`` it is the observed milestone's own EDGE
        coordinate, which names the milestone the close observed instead of
        naming the close's address directly.
        """
        return self.when.get("observedValidStart")

    @property
    def expected_affected_rows(self) -> int | None:
        return self.then.get("affectedRows")

    @property
    def is_scenario(self) -> bool:
        """True for a unit-of-work, cache, or identity scenario case.

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
        """True for an m-auto-retry/m-opt-lock bounded-retry boundary case.

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
        """True for a cross-process cache-coherence case.

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
        shared read lock is COMPATIBLE with a second reader (``m-read-lock-007``),
        the non-error counterpart to the error branch's lock CONTENTION
        (``m-read-lock-006``).
        """
        return self.shape == "concurrencySuccess"

    @property
    def is_rejected(self) -> bool:
        """True for a negative-validation case (m-value-object / m-op-algebra, Q7).

        A ``rejected`` case carries the invalid input under ``when.operation`` (a
        schema-valid m-op-algebra node) OR ``when.write`` (a neutral write row) and
        a ``then.rejectedRule`` naming the violated normative rule. A model-aware
        validator MUST refuse it BEFORE any SQL is emitted — no golden SQL, no
        dialect, no provisioning; :func:`case_runner.run_case` runs it dialect-free.
        """
        return self.shape == "rejected"

    @property
    def rejected_rule(self) -> str | None:
        """The normative rule a ``rejected`` case expects the input to violate.

        One of the ``then.rejectedRule`` vocabulary
        (:data:`value_object_resolve.REJECTED_RULES`); the runner asserts the
        model-aware validator raises exactly this rule.
        """
        return self.then.get("rejectedRule")

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
    def expected_graphs(self) -> list[dict[str, Any]] | None:
        """The ordered per-milestone edge-pinned graphs of a `history` / `asOfRange`
        snapshot read (``then.graphs``), or ``None`` (m-snapshot-read, Q5a).

        Each entry is ``{"pin": {dimension: start-instant}, "graph": {Class: [node, …]}}``:
        the milestone's own edge coordinate paired with the graph materialized at it.
        Coexists with :attr:`expected_graph` exactly as ``then.rows`` does.
        """
        return self.then.get("graphs")

    @property
    def round_trips(self) -> int:
        """The statements this case costs: what ``then.roundTrips`` declares, or
        the shape's own default where it is absent.

        One for a shape that reaches the database, and ZERO for a ``rejected``
        case, whose input a validator refuses before any statement is composed
        (``m-conformance-adapter``: a rejected observation reports
        ``roundTrips: 0``). The schema pins the declared value to ``0`` there, so
        the shape-aware default is the same number a declaration would carry —
        and it is the number every rejected case actually answers, since none of
        them declares the field.
        """
        return self.then.get("roundTrips", 0 if self.is_rejected else 1)

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
    return read_corpus_yaml(path)


# One parsed template per corpus artifact, for the life of the process.
#
# Un-memoized, ``discover_cases`` opens 1,186 YAML files to read a 463-file
# corpus — every case re-reads its model descriptor and that model's fixtures —
# and the harness suite calls it from ~40 sites. Memoizing is sound only because
# the parsed graph is deeply frozen (see :func:`discover_cases`): every caller
# gets the *same* objects, and a caller that needs to damage a case takes its own
# ``copy.deepcopy`` first. This is a pure memoization of a pure function of the
# filesystem, so it holds no semantic state.
#
# Every key is a ``.resolve()``d path, so a relative, symlinked, or
# ``..``-containing spelling of the same root cannot produce a second parse. The
# corollary is that these caches assume the corpus does not change on disk within
# a process; nothing in the suite writes to a corpus it has already read, and a
# test that builds a throwaway corpus gets a distinct ``tmp_path`` root and so a
# distinct key.
_MODEL_CACHE: dict[tuple[Path, str], Model] = {}
_CASE_CACHE: dict[tuple[Path, Path], Case] = {}
_TEMPLATE_CACHE: dict[Path, tuple[Case, ...]] = {}


def load_model(compatibility_root: Path, model_rel: str) -> Model:
    """Load a model descriptor (relative to ``core/compatibility``) + its fixtures.

    Memoized per resolved root + ``model_rel``. The returned descriptor and
    fixtures are deeply frozen and shared between callers — see
    :func:`discover_cases` for the contract.
    """
    root = compatibility_root.resolve()
    key = (root, model_rel)
    cached = _MODEL_CACHE.get(key)
    if cached is not None:
        return cached

    model_path = (root / model_rel).resolve()
    descriptor = _freeze(derive_temporal_structure(_load_yaml(model_path)))

    fixtures_path = root / "fixtures" / f"{model_path.stem}.yaml"
    fixtures: dict[str, list[dict[str, Any]]] = FrozenDict()
    if fixtures_path.is_file():
        loaded = _load_yaml(fixtures_path)
        if loaded:
            fixtures = _freeze(loaded)
    model = Model(path=model_path, descriptor=descriptor, fixtures=fixtures)
    _MODEL_CACHE[key] = model
    return model


def load_case(compatibility_root: Path, case_path: Path) -> Case:
    """Load a single compatibility case, resolving and loading its model.

    Memoized per resolved root + resolved case path. The returned case is deeply
    frozen and shared between callers — see :func:`discover_cases`.
    """
    root = compatibility_root.resolve()
    resolved_case_path = case_path.resolve()
    key = (root, resolved_case_path)
    cached = _CASE_CACHE.get(key)
    if cached is not None:
        return cached

    raw = _freeze(_load_yaml(resolved_case_path))
    model = load_model(root, raw["model"])
    case = Case(path=resolved_case_path, raw=raw, model=model)
    _CASE_CACHE[key] = case
    return case


def discover_cases(compatibility_root: Path) -> list[Case]:
    """Discover and load every case under ``cases/`` (sorted by path).

    The returned :class:`Case` / :class:`Model` graph — ``raw``, ``descriptor``,
    ``fixtures``, and every nested document node — is **deeply immutable**.
    Writing through any of it (item assignment, ``append``, ``+=``, …) raises
    :class:`TypeError`. A caller that needs to modify a case — every such caller
    today is a negative test building malformed input — must ``copy.deepcopy``
    it, or the sub-structure it damages, first::

        case = copy.deepcopy(next(c for c in discover_cases(root) if ...))
        case.when["writeSequence"][0]["statements"] += 1

    ``copy.deepcopy`` of any frozen node yields a plain, fully-mutable
    ``dict``/``list``, so the copy is writable all the way down. Stating the
    contract this way — enforced by the objects rather than by the accident of a
    fresh parse per call — is what lets the graph be shared instead of re-parsed.

    The corpus is parsed at most once per resolved root per process. Repeat calls
    return the same :class:`Case` objects in a fresh ``list``, so a caller may
    filter or re-sort the list it is handed without disturbing the next caller's.
    """
    root = compatibility_root.resolve()
    cached = _TEMPLATE_CACHE.get(root)
    if cached is None:
        cases_dir = root / "cases"
        case_files = sorted(cases_dir.glob("**/*.yaml")) + sorted(cases_dir.glob("**/*.yml"))
        cached = tuple(load_case(root, path) for path in sorted(set(case_files)))
        _TEMPLATE_CACHE[root] = cached
    return list(cached)


def dialect_executed_cases(compatibility_root: Path) -> list[Case]:
    """The discovered cases a dialect-parametrized runner executes, one run per dialect.

    Two exclusions, for unrelated reasons.

    An ``api-conformance``-lane case (boundary retry cases, read-lock matrix
    reads) is schema-validated by the harness but satisfied by each language's
    API Conformance Suite, so no harness runner executes it —
    :func:`case_runner.run_case` early-returns for that lane.

    A ``rejected``-shape case is refused before the dialect is read, so a
    dialect axis proves nothing about it: running one per available dialect
    repeats an identical database-free assertion. Its own dialect-independent
    runner owns it, and the two selections partition the harness lane — every
    case outside the api-conformance lane belongs to exactly one of them.
    """
    return [
        case
        for case in discover_cases(compatibility_root)
        if case.lane != "api-conformance" and case.shape != "rejected"
    ]
