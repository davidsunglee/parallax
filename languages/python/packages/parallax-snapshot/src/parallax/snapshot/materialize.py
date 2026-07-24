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
alone (transitively reaching ``m-metamodel`` / ``m-inheritance`` /
``m-temporal-read``, whose accepted Metadata and Inheritance Facet this module
reads directly — the same transitive-reachability latitude every other scope in
this DAG already uses). It never imports ``m-sql`` / ``m-dialect``:
`familyVariant` materialization (the raw tag column -> subtype name, or the
projected literal rename) is `m-sql`-owned, carried by the compiled read itself
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
from parallax.core.metamodel import (
    AttributeMetadata,
    EntityMetadata,
    Metamodel,
    Multiplicity,
    NestedValueObjectMetadata,
    PrimaryKey,
    TablePerConcreteSubtype,
    ValueObjectMetadata,
)

__all__ = [
    "Assembler",
    "MaterializeError",
    "Node",
    "decode_row",
    "identity_key",
]

_VoContainer = ValueObjectMetadata | NestedValueObjectMetadata


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
    of falling back to a (possibly abstract) declared default. ``None`` only
    for a ``Node`` built outside
    the assembler (test-only direct construction) — a caller reading it
    falls back to its own declared default in that defensive case.
    """

    fields: dict[str, object]
    pk_columns: tuple[str, ...]
    resolved_entity: str | None = None


def _entity(meta: Metamodel, name: str) -> EntityMetadata:
    """The accepted Metadata a bare-or-canonical Entity spelling names.

    m-snapshot-read resolves within the accepted model itself: a level's target
    is an unambiguous declared name, so a canonical-or-bare Identity match is
    exact. Raises :class:`KeyError` when the model declares no such Entity."""
    for entity in meta.entities:
        if name in (entity.identity.canonical, entity.identity.name):
            return entity
    raise KeyError(name)  # pragma: no cover - a level target always names a declared Entity


def _declaring(meta: Metamodel, entity: EntityMetadata) -> EntityMetadata:
    """``entity``'s family root (itself for a standalone Entity): the primary key,
    like the temporal axes, is family-wide metadata declared only there
    (m-inheritance "Inherited members")."""
    position = inheritance.view(meta).entity(entity.identity)
    if position is None:  # pragma: no cover - the facet covers every accepted Entity
        return entity
    root = meta.entity(position.root)
    return entity if root is None else root


def _declared_primary_key(entity: EntityMetadata) -> tuple[AttributeMetadata, ...]:
    return tuple(
        attribute
        for attribute in entity.declared_attributes
        if isinstance(attribute.primary_key, PrimaryKey)
    )


def _resolved_position(
    meta: Metamodel, entity_name: str, narrow_to: tuple[str, ...] | None
) -> tuple[str, ...]:
    """The row's resolved effective concrete-subtype set — mirrors `m-sql`'s own
    narrow resolution so a level's value-object superset decodes the SAME
    position the compiled projection actually fetched, whether reached by an
    authored narrow or a bare polymorphic target's own full effective set."""
    entity = _entity(meta, entity_name)
    if entity.inheritance is None:
        return (entity_name,)
    facet = inheritance.view(meta)
    if narrow_to is None:
        view = facet.entity(entity.identity)
        if view is None:  # pragma: no cover - the facet covers every accepted Entity
            return (entity_name,)
        return tuple(identity.name for identity in view.concrete_subtypes)
    members = [_entity(meta, name).identity for name in narrow_to]
    position = facet.position(members)
    if position is None:  # pragma: no cover - a validated narrow names one family
        return (entity_name,)
    return tuple(identity.name for identity in position.concrete_subtypes)


def _superset_value_objects(
    meta: Metamodel, position: Sequence[str]
) -> tuple[ValueObjectMetadata, ...]:
    """Every value object reachable from ``position`` (an effective concrete set)
    — the Inheritance Facet's own projection superset (ancestry prefix, then each
    concrete's own; only the SET of declared value objects, not their order,
    decides what a row's document columns hold)."""
    members = [_entity(meta, name).identity for name in position]
    view = inheritance.view(meta).position(members)
    return () if view is None else tuple(view.superset_value_objects)


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

    TABLE-PER-CONCRETE-SUBTYPE is the one exception to root-normalization:
    each concrete owns its OWN physical
    table with its OWN independent primary-key namespace (m-inheritance-109's
    own fixture: "Primary keys are per-table, so id 1 recurs across
    Invoice/Receipt/Memo — the rows are distinguished by their concrete
    variant, never by id"), so normalizing to the bare family-root name would
    wrongly conflate two DIFFERENT physical rows that merely share a PK
    VALUE — identity is the row's own resolved CONCRETE name instead:
    ``familyVariant`` when the row carries one (a 2+-concrete union-all
    position), else the compile-time-resolved position's OWN sole member
    when it resolves to exactly one concrete (:func:`_resolved_position`).

    The coordinate component m-snapshot-read's identity triple names (the
    lowered as-of per axis) is intentionally omitted from this key: within ONE
    materialization every node represents the SAME whole-graph pin (m-snapshot-
    read "The whole-graph pin"), so two rows sharing a family + primary key can
    never carry two different coordinates in the same graph — the coordinate is
    a graph-wide constant here, never a distinguishing key component.
    """
    entity = _entity(meta, entity_name)
    view = inheritance.view(meta).entity(entity.identity)
    if view is None:  # pragma: no cover - the facet covers every accepted Entity
        return None
    declaring = meta.entity(view.root)
    if declaring is None:  # pragma: no cover - a family root is always accepted
        return None
    pk_attrs = _declared_primary_key(declaring)
    if not pk_attrs:
        return None
    pk = tuple(row[attr.storage.name] for attr in pk_attrs)
    name = declaring.identity.name
    if isinstance(view.strategy, TablePerConcreteSubtype):
        variant = row.get("familyVariant")
        name = (
            variant
            if isinstance(variant, str)
            else _resolved_concrete(meta, entity_name, narrow_to)
        )
    return (name, pk)


def _resolved_concrete(meta: Metamodel, entity_name: str, narrow_to: tuple[str, ...] | None) -> str:
    """``entity_name``'s own statically-known concrete entity name for THIS
    decode call: the resolved position reduced to its sole member when it
    resolves to exactly one concrete — the SAME position `decode_row`'s
    value-object superset already derives from ``narrow_to``, so identity and
    decoding can never disagree on what a `familyVariant`-less row's own concrete
    is. Degrades to ``entity_name`` unchanged when the position spans 2+
    concretes (a row's own ``familyVariant`` field is authoritative there
    instead — this helper is consulted only when the row carries none)."""
    position = _resolved_position(meta, entity_name, narrow_to)
    return position[0] if len(position) == 1 else entity_name


def _pk_columns(meta: Metamodel, entity_name: str) -> tuple[str, ...]:
    declaring = _declaring(meta, _entity(meta, entity_name))
    return tuple(attr.storage.name for attr in _declared_primary_key(declaring))


# --------------------------------------------------------------------------- #
# Value-object document decoding (m-value-object "Materialization and          #
# navigation contract"): only declared members appear, every declared member   #
# is present (null / [] where the document does not supply it) — the same     #
# absence-state vocabulary the predicate side collapses (m-op-algebra).       #
# --------------------------------------------------------------------------- #
def _decode_element(raw: object, container: _VoContainer) -> dict[str, object] | None:
    """Decode one ``one``-shaped value-object document (or array element) to its
    DECLARED shape: a non-mapping (SQL NULL, JSON null, a non-object scalar)
    collapses to ``None`` — the whole composite absent — never a partial dict."""
    if not isinstance(raw, Mapping):
        return None
    document = cast("Mapping[str, object]", raw)
    result: dict[str, object] = {}
    for attribute in container.attributes:
        result[attribute.identity.name] = document.get(attribute.identity.name)
    for nested in container.value_objects:
        member_name = nested.identity.path[-1]
        nested_raw = document.get(member_name)
        result[member_name] = (
            _decode_many(nested_raw, nested)
            if nested.multiplicity is Multiplicity.MANY
            else _decode_element(nested_raw, nested)
        )
    return result


def _decode_many(raw: object, container: _VoContainer) -> list[dict[str, object] | None]:
    """Decode a ``many``-multiplicity member: a non-list (SQL NULL, JSON null, a
    non-array scalar or object) collapses to an EMPTY list — never a
    nullability violation, per m-value-object's own array-absence rule."""
    if not isinstance(raw, list):
        return []
    items = cast("list[object]", raw)
    return [_decode_element(item, container) for item in items]


def _decode_value_object(raw: object, vo: ValueObjectMetadata) -> object:
    if vo.multiplicity is Multiplicity.MANY:
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

    Deliberately UNNARROWED at this layer:
    a multi-concrete position's row keeps every sibling's own null-padded
    column here — the SAME neutral `Node` this module's own callers share
    between the row-form values-lane witnesses (whose `then.graph` / wire
    rendering, `parallax.conformance.engine._render_node`, WANTS the padded
    superset) and `parallax.snapshot.handle`'s object-lane wrapping. Per-variant
    narrowing is `wrap`'s OWN job (see its module docstring / `_wrap`): it
    already resolves each column through the CONCRETE class's own
    `wire_names_of`, so a sibling's column — absent from that class's own
    declared members — is skipped, never assigned. Narrowing here would corrupt
    the values-lane goldens that share this exact same `Node`.
    """
    position = _resolved_position(meta, entity_name, narrow_to)
    value_objects = _superset_value_objects(meta, position)
    vo_columns = {vo.storage.name for vo in value_objects}
    fields: dict[str, object] = {key: value for key, value in row.items() if key not in vo_columns}
    for vo in value_objects:
        fields[vo.storage.name] = _decode_value_object(row.get(vo.storage.name), vo)
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

        ``narrow_to`` is the root read's OWN top-level authored narrow, when
        the caller's find executor
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
