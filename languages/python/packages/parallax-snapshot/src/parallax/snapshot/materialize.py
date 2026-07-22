"""``parallax.snapshot.materialize`` enforcement scope (m-snapshot-read).

The **one assembler**: rows-per-level in, neutral (class-free) graph nodes out.
:class:`Node` is the whole vocabulary — a plain mutable field dict plus its
declared primary-key columns (for cycle-stub rendering) — because corpus models
have no Python classes and the production developer surface (`Snapshot[T]`, in
`parallax.snapshot.handle`) is a frozen wrapping over these SAME nodes, not a
different graph.

:class:`Assembler` is the stateful per-materialization builder a production find
executor (``parallax.snapshot.handle``) or the conformance run lane drives, one
level at a time, in :class:`~parallax.core.deep_fetch.FetchPlan` dependency
order:

- :meth:`Assembler.materialize_root` decodes the root query's own rows.
- :meth:`Assembler.attach_level` decodes one level's fetched child rows (or,
  for an empty parent-key level, attaches the empty/null relationship result;
  or, for a back-reference level, resolves the ancestor already in the
  identity map — no rows to decode at all) and fans them back to their
  parents under the level's own ``attach_key`` — a list for a to-many
  relationship (preserving fetched order), a single node or ``None`` for a
  to-one.

Graph-local identity (`m-snapshot-read` "Graph-local identity resolution") is
the assembler's own bookkeeping: every row it decodes registers under
:func:`identity_key` — ``(family-normalized name, primary-key tuple)`` — the
FIRST node registered for a key is the one every later reference to that same
row reuses (never re-decoded, never a second copy) — the mechanism a
back-reference level's resolution depends on and what a future identity-check
observation compares by Python reference (`is`), never by value.

Per the amended dependency graph, ``m-snapshot-read`` depends on ``m-deep-fetch``
alone (transitively reaching ``m-descriptor`` / ``m-inheritance`` /
``m-temporal-read``, all of which this module imports directly — the same
transitive-reachability latitude every other scope in this DAG already uses).
It never imports ``m-sql`` / ``m-dialect``: `familyVariant` materialization
(the raw tag column -> subtype name, or the projected literal rename) is
`m-sql`-owned, carried by the compiled read itself
(`~parallax.core.sql_gen.CompiledRead.transform_row`) and applied by the CALLER
to a level's rows before handing them here — this module only ever sees rows
whose keys are already the neutral wire-shaped ones (scalars, a `familyVariant`
string when present, and each declared value-object's own document column).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import cast

from parallax.core import inheritance
from parallax.core.deep_fetch import FetchLevel
from parallax.core.descriptor import Metamodel, NestedValueObject, ValueObject

__all__ = [
    "Assembler",
    "MaterializeError",
    "Node",
    "decode_row",
    "identity_key",
]


class MaterializeError(ValueError):
    """The assembler cannot materialize a row or resolve a back-reference."""


@dataclass(slots=True)
class Node:
    """One neutral, class-free snapshot graph node (m-snapshot-read).

    ``fields`` is a plain mutable dict: scalar/value-object/`familyVariant`
    values at construction, plus a relationship-attached ``Node`` / ``list[Node]``
    / ``None`` entry per attached level, keyed by that level's own
    ``attach_key`` — absence of a key IS the closed-world "not loaded" state,
    never a sentinel value. ``pk_columns`` names the declared primary-key
    columns among ``fields`` (in declaration order) — what a serializer's
    back-reference-cycle truncation renders as the PK-only stub.

    ``resolved_entity`` is this row's own STATICALLY known concrete entity
    name — the compile-time-resolved position `_materialize` decoded this
    row against (never wire-visible: unlike ``fields``, it is assembler-only
    bookkeeping the `then.graph` renderer never walks). A table-per-concrete-
    subtype read resolving to exactly ONE concrete emits no `familyVariant`
    column at all (`m-sql`'s `_compile_tpcs_single`), so this is the ONLY
    place that knowledge survives past the SQL boundary for
    `parallax.snapshot.handle` to recover the row's own concrete class instead
    of falling back to a (possibly abstract) declared default (S3, COR-3
    Phase 7 increment 7 round-2). ``None`` only for a ``Node`` built outside
    the assembler (test-only direct construction) — a caller reading it
    falls back to its own declared default in that defensive case.
    """

    fields: dict[str, object]
    pk_columns: tuple[str, ...]
    resolved_entity: str | None = None


def _resolved_position(
    meta: Metamodel, entity_name: str, narrow_to: tuple[str, ...] | None
) -> tuple[str, ...]:
    """The row's resolved effective concrete-subtype set — mirrors `m-sql`'s own
    narrow resolution (`_narrow_effective_set`) so a level's value-object
    superset decodes the SAME position the compiled projection actually
    fetched, whether reached by an authored narrow or a bare polymorphic
    target's own full effective set."""
    entity = meta.entity(entity_name)
    if entity.inheritance is None:
        return (entity_name,)
    if narrow_to is None:
        return tuple(inheritance.effective_concrete_subtypes(meta, entity_name))
    resolved: set[str] = set()
    for name in narrow_to:
        resolved.update(inheritance.effective_concrete_subtypes(meta, name))
    return tuple(sorted(resolved))


def _superset_value_objects(meta: Metamodel, position: Sequence[str]) -> list[ValueObject]:
    """Every value object reachable from ``position`` (ancestry prefix, then
    each concrete's own — the SAME ordering `m-sql`'s own projection uses, not
    that it matters for decoding: only the SET of declared value objects, not
    their order, decides what a row's document columns hold) — the shared
    `inheritance.superset_value_objects` resolution (also used by `m-sql`'s
    abstract-read/union-all projection)."""
    return inheritance.superset_value_objects(meta, position)


def identity_key(
    meta: Metamodel,
    entity_name: str,
    row: Mapping[str, object],
    narrow_to: tuple[str, ...] | None = None,
) -> tuple[str, tuple[object, ...]] | None:
    """The row's graph-local identity key (m-snapshot-read): ``(family-normalized
    name, primary-key value tuple)``. Family-normalized — an inheritance
    participant's identity is keyed to its family ROOT's name, never the
    concrete/position a particular level happened to reach it through
    (projection independence) — and degrades to the entity's own name for a
    non-participant. Returns ``None`` when the (resolved) entity declares no
    primary key at all (defensive; every corpus entity does).

    TABLE-PER-CONCRETE-SUBTYPE is the one exception to root-normalization
    (ledger D-22, COR-3 Phase 8 part C): each concrete owns its OWN physical
    table with its OWN independent primary-key namespace (m-inheritance-109's
    own fixture: "Primary keys are per-table, so id 1 recurs across
    Invoice/Receipt/Memo — the rows are distinguished by their concrete
    variant, never by id"), so normalizing to the bare family-root name would
    wrongly conflate two DIFFERENT physical rows that merely share a PK
    VALUE — identity is the row's own resolved CONCRETE name instead:
    ``familyVariant`` when the row carries one (a 2+-concrete union-all
    position), else the compile-time-resolved position's OWN sole member
    when it resolves to exactly one concrete (S3, COR-3 Phase 7 increment 7
    round-2 — a single-resolved-position read's SQL legitimately omits
    `familyVariant`, `m-sql`'s `_compile_tpcs_single`, so ``entity_name`` alone
    is NOT already that row's concrete whenever the QUERIED position itself
    was abstract, e.g. an abstract root/subtype narrowed, or naturally
    resolving, down to one concrete — :func:`_resolved_position` (the SAME
    resolution `decode_row`'s own value-object superset already shares)
    recovers it).

    The coordinate component m-snapshot-read's identity triple names (the
    lowered as-of per axis) is intentionally omitted from this key: within ONE
    materialization every node represents the SAME whole-graph pin (m-snapshot-
    read "The whole-graph pin"), so two rows sharing a family + primary key can
    never carry two different coordinates in the same graph — the coordinate is
    a graph-wide constant here, never a distinguishing key component.
    """
    entity = meta.entity(entity_name)
    # `inheritance.declaring_entity`: the family root for a participant (the
    # primary key, like the temporal axes, is family-wide metadata declared
    # only there — m-inheritance "Inherited members") — else `entity` itself.
    # Graph-identity FAMILY normalization and temporal-coordinate resolution
    # are conceptually distinct questions, but under the family-wide
    # root-ownership invariant (ADR 0026) both resolve identically, so this
    # reuses the ONE shared resolver rather than a second, duplicate walk.
    declaring = inheritance.declaring_entity(meta, entity)
    if not declaring.primary_key:
        return None
    pk = tuple(row[attr.column] for attr in declaring.primary_key)
    name = declaring.name
    if declaring.inheritance is not None and declaring.inheritance.strategy == (
        "table-per-concrete-subtype"
    ):
        variant = row.get("familyVariant")
        name = (
            variant
            if isinstance(variant, str)
            else _resolved_concrete(meta, entity_name, narrow_to)
        )
    return (name, pk)


def _resolved_concrete(meta: Metamodel, entity_name: str, narrow_to: tuple[str, ...] | None) -> str:
    """``entity_name``'s own statically-known concrete entity name for THIS
    decode call (S3, COR-3 Phase 7 increment 7 round-2): the resolved position
    (:func:`_resolved_position`) reduced to its sole member when it resolves
    to exactly one concrete — the SAME position `decode_row`'s value-object
    superset already derives from ``narrow_to``, so identity and decoding can
    never disagree on what a `familyVariant`-less row's own concrete is.
    Degrades to ``entity_name`` unchanged when the position spans 2+ concretes
    (a row's own ``familyVariant`` field is authoritative there instead — this
    helper is consulted only when the row carries none)."""
    position = _resolved_position(meta, entity_name, narrow_to)
    return position[0] if len(position) == 1 else entity_name


def _pk_columns(meta: Metamodel, entity_name: str) -> tuple[str, ...]:
    declaring = inheritance.declaring_entity(meta, meta.entity(entity_name))
    return tuple(attr.column for attr in declaring.primary_key)


# --------------------------------------------------------------------------- #
# Value-object document decoding (m-value-object "Materialization and          #
# navigation contract"): only declared members appear, every declared member   #
# is present (null / [] where the document does not supply it) — the same     #
# absence-state vocabulary the predicate side collapses (m-op-algebra).       #
# --------------------------------------------------------------------------- #
def _decode_element(
    raw: object, container: ValueObject | NestedValueObject
) -> dict[str, object] | None:
    """Decode one ``one``-shaped value-object document (or array element) to its
    DECLARED shape: a non-mapping (SQL NULL, JSON null, a non-object scalar)
    collapses to ``None`` — the whole composite absent — never a partial dict."""
    if not isinstance(raw, Mapping):
        return None
    document = cast("Mapping[str, object]", raw)
    result: dict[str, object] = {}
    for attribute in container.attributes:
        result[attribute.name] = document.get(attribute.name)
    for nested in container.value_objects:
        nested_raw = document.get(nested.name)
        result[nested.name] = (
            _decode_many(nested_raw, nested)
            if nested.multiplicity == "many"
            else _decode_element(nested_raw, nested)
        )
    return result


def _decode_many(
    raw: object, container: ValueObject | NestedValueObject
) -> list[dict[str, object] | None]:
    """Decode a ``many``-multiplicity member: a non-list (SQL NULL, JSON null, a
    non-array scalar or object) collapses to an EMPTY list — never a
    nullability violation, per m-value-object's own array-absence rule."""
    if not isinstance(raw, list):
        return []
    items = cast("list[object]", raw)
    return [_decode_element(item, container) for item in items]


def _decode_value_object(raw: object, vo: ValueObject) -> object:
    if vo.multiplicity == "many":
        return _decode_many(raw, vo)
    return _decode_element(raw, vo)


def decode_row(
    meta: Metamodel,
    entity_name: str,
    row: Mapping[str, object],
    narrow_to: tuple[str, ...] | None = None,
) -> dict[str, object]:
    """Decode one raw wire-shaped row (already family-variant-materialized by the
    caller) into a neutral node's field dict: every non-value-object key
    (scalars, `familyVariant`) passes through unchanged; each value object
    reachable from the row's resolved position decodes to its declared shape,
    keyed by its own document column — the LAST-projected columns (`m-sql`
    *Read projection* slot 4), rendered here in whatever order the caller's own
    dict iterates (graph comparison is structural, never key-order-sensitive).

    Deliberately UNNARROWED at this layer (ledger D-22, COR-3 Phase 8 part C):
    a multi-concrete position's row keeps every sibling's own null-padded
    column here — the SAME neutral `Node` this module's own callers share
    between the row-form values-lane witnesses (whose `then.graph` / wire
    rendering, `parallax.conformance.engine._render_node`, WANTS the padded
    superset, e.g. `m-snapshot-read-012`'s own root-typed `animals` level) and
    `parallax.snapshot.handle`'s object-lane wrapping. Per-variant narrowing is
    `wrap`'s OWN job (see its module docstring / `_wrap`): it already resolves
    each column through the CONCRETE class's own `wire_names_of`, so a
    sibling's column — absent from that class's own declared members — is
    skipped, never assigned. Narrowing here would corrupt the values-lane
    goldens that share this exact same `Node`.
    """
    position = _resolved_position(meta, entity_name, narrow_to)
    value_objects = _superset_value_objects(meta, position)
    vo_columns = {vo.storage_column for vo in value_objects}
    fields: dict[str, object] = {key: value for key, value in row.items() if key not in vo_columns}
    for vo in value_objects:
        fields[vo.storage_column] = _decode_value_object(row.get(vo.storage_column), vo)
    return fields


# --------------------------------------------------------------------------- #
# The assembler.                                                              #
# --------------------------------------------------------------------------- #
def _new_identity_map() -> dict[tuple[str, tuple[object, ...]], Node]:
    return {}


@dataclass(slots=True)
class Assembler:
    """One materialization's graph builder: identity-keyed node registry plus
    per-level row decoding and fan-back. Not reused across materializations —
    graph-local identity resolution never promises a same-node reuse beyond one
    graph (m-snapshot-read)."""

    meta: Metamodel
    _identity: dict[tuple[str, tuple[object, ...]], Node] = field(default_factory=_new_identity_map)

    def materialize_root(
        self,
        entity_name: str,
        rows: Sequence[Mapping[str, object]],
        narrow_to: tuple[str, ...] | None = None,
    ) -> list[Node]:
        """Decode the root query's own rows into fresh, identity-registered nodes.

        ``narrow_to`` is the root read's OWN top-level authored narrow (S3,
        COR-3 Phase 7 increment 7 round-2), when the caller's find executor
        supplies one (`~parallax.core.sql_gen.CompiledRead.narrow_to`)
        — the root-level analogue of a deep-fetch child level's own
        ``FetchLevel.narrow_to``, which :meth:`attach_level` already threads.
        Omitted (``None``) for a bare, un-narrowed root read, or a caller that
        predates this parameter — a non-family or already-concrete
        ``entity_name`` resolves identically either way.
        """
        return self._materialize(entity_name, rows, narrow_to=narrow_to)

    def attach_level(
        self,
        level: FetchLevel,
        parent_nodes: Sequence[Node],
        parent_rows: Sequence[Mapping[str, object]],
        child_rows: Sequence[Mapping[str, object]] | None,
    ) -> list[Node]:
        """Attach one level's children to ``parent_nodes`` under its own
        ``attach_key``; returns the level's OWN materialized child nodes (empty
        for a back-reference or an empty level) — the next level's own
        ``parent_nodes`` when a further level attaches beneath this one.

        ``child_rows`` is ``None`` exactly when the level's gathered parent-key
        set was empty (m-deep-fetch: no child SQL issued for that level) — every
        parent gets the empty/null relationship result. A back-reference level
        (``level.is_back_reference``) never receives rows at all: each parent's
        own gathered key resolves directly against the graph-local identity map.
        """
        if level.is_back_reference:
            return self._attach_back_reference(level, parent_nodes, parent_rows)
        if child_rows is None:
            empty: object = [] if level.to_many else None
            for node in parent_nodes:
                node.fields[level.attach_key] = empty
            return []
        assert level.child_target is not None
        assert level.related_column is not None
        child_nodes = self._materialize(level.child_target, child_rows, level.narrow_to)
        buckets: dict[object, list[Node]] = {}
        for row, node in zip(child_rows, child_nodes, strict=True):
            buckets.setdefault(row[level.related_column], []).append(node)
        for row, node in zip(parent_rows, parent_nodes, strict=True):
            matched = buckets.get(row[level.parent_column], [])
            node.fields[level.attach_key] = matched if level.to_many else _one_or_none(matched)
        return child_nodes

    def _attach_back_reference(
        self,
        level: FetchLevel,
        parent_nodes: Sequence[Node],
        parent_rows: Sequence[Mapping[str, object]],
    ) -> list[Node]:
        assert level.back_reference_family is not None
        for row, node in zip(parent_rows, parent_nodes, strict=True):
            fk = row[level.parent_column]
            if fk is None:
                node.fields[level.attach_key] = [] if level.to_many else None
                continue
            referenced = self._identity.get((level.back_reference_family, (fk,)))
            if referenced is None:  # pragma: no cover - guards a malformed plan
                raise MaterializeError(
                    f"back-reference {level.attach_key!r}: no already-materialized "
                    f"{level.back_reference_family} node for key {fk!r} (m-case-format "
                    "'Back-reference cycles' guarantees the ancestor is already known)"
                )
            node.fields[level.attach_key] = [referenced] if level.to_many else referenced
        return []

    def _materialize(
        self,
        entity_name: str,
        rows: Sequence[Mapping[str, object]],
        narrow_to: tuple[str, ...] | None,
    ) -> list[Node]:
        pk_columns = _pk_columns(self.meta, entity_name)
        resolved_entity = _resolved_concrete(self.meta, entity_name, narrow_to)
        nodes: list[Node] = []
        for row in rows:
            node = Node(
                fields=decode_row(self.meta, entity_name, row, narrow_to),
                pk_columns=pk_columns,
                resolved_entity=resolved_entity,
            )
            key = identity_key(self.meta, entity_name, row, narrow_to)
            if key is not None:
                self._identity.setdefault(key, node)
            nodes.append(node)
        return nodes


def _one_or_none(matched: list[Node]) -> Node | None:
    return matched[0] if matched else None
