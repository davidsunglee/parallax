"""``parallax.snapshot.materialize`` enforcement scope (m-snapshot-read).

The **one assembler**: rows-per-level in, neutral (class-free) graph nodes out.
:class:`Node` is the whole vocabulary — provenance-separated scalar, Value Object,
relationship, and synthetic-variant fields plus its declared primary-key columns
(for cycle-stub rendering) — because corpus models
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
from parallax.core.base import decode_neutral_literal
from parallax.core.deep_fetch import FetchLevel
from parallax.core.metamodel import (
    AttributeMetadata,
    EntityIdentity,
    EntityMetadata,
    Metamodel,
    Multiplicity,
    NestedValueObjectMetadata,
    PrimaryKey,
    TablePerConcreteSubtype,
    ValueObjectMetadata,
    entity_by_name,
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


def _new_field_map() -> dict[str, object]:
    return {}


@dataclass(slots=True)
class Node:
    """One neutral, class-free snapshot graph node (m-snapshot-read).

    ``fields`` contains scalar physical-column values. ``value_objects`` retains
    decoded documents under physical storage keys, ``relationships`` contains a
    relationship-attached ``Node`` / ``list[Node]`` / ``None`` entry per attached
    level, and ``family_variant`` carries the synthetic polymorphic spelling.
    Keeping those categories separate lets a Value Object storage key equal a
    relationship name without either overwriting or renaming the other. Absence
    from ``relationships`` IS the closed-world "not loaded" state, never a
    sentinel value. ``pk_columns`` names the declared primary-key columns among
    ``fields`` (in declaration order) — what a serializer's
    back-reference-cycle truncation renders as the PK-only stub.

    ``resolved_entity`` is this row's own STATICALLY known canonical Entity
    Identity — the sole concrete resolved by `_materialize` when one is known,
    otherwise the queried inheritance position whose family contains the row.
    It is never wire-visible: unlike ``fields``, it is assembler-only
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
    resolved_entity: EntityIdentity | None = None
    value_objects: dict[str, object] = field(default_factory=_new_field_map)
    relationships: dict[str, object] = field(default_factory=_new_field_map)
    family_variant: str | None = None


def _entity(meta: Metamodel, name: str) -> EntityMetadata:
    """The accepted Metadata a bare-or-canonical Entity spelling names.

    m-snapshot-read resolves within the accepted model itself: a level's target
    is an unambiguous declared name, resolved by
    :func:`~parallax.core.metamodel.entity_by_name`'s ambiguity-rejecting
    bare-or-canonical rule. Raises :class:`KeyError` when the model declares no
    such Entity."""
    entity = entity_by_name(meta, name)
    if entity is None:  # pragma: no cover - a level target always names a declared Entity
        raise KeyError(name)
    return entity


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
    meta: Metamodel,
    entity: EntityMetadata,
    narrow_to: tuple[str, ...] | None,
    resolved_position: tuple[EntityIdentity, ...] | None = None,
) -> tuple[EntityIdentity, ...]:
    """The exact effective concrete-subtype set the compiled read projected.

    Production callers pass ``CompiledRead.resolved_position`` so no local-name
    round trip can erase namespaces. ``narrow_to`` remains only as the defensive
    direct-call fallback used by tests and older callers; its entries are
    operation references and resolve model-wide by :func:`entity_by_name`'s rule,
    the same rule the read's own lowering resolved them by.
    """
    if resolved_position is not None:
        return resolved_position
    if entity.inheritance is None:
        return (entity.identity,)
    facet = inheritance.view(meta)
    if narrow_to is None:
        view = facet.entity(entity.identity)
        if view is None:  # pragma: no cover - the facet covers every accepted Entity
            return (entity.identity,)
        return tuple(view.concrete_subtypes)
    members: list[EntityIdentity] = []
    for name in narrow_to:
        member = entity_by_name(meta, name)
        if member is None:  # pragma: no cover - a validated narrow names declared entities
            return (entity.identity,)
        members.append(member.identity)
    position = facet.position(members)
    if position is None:  # pragma: no cover - a validated narrow names one family
        return (entity.identity,)
    return tuple(position.concrete_subtypes)


def _superset_value_objects(
    meta: Metamodel,
    position: Sequence[EntityIdentity],
    documents: Sequence[ValueObjectMetadata] | None = None,
) -> tuple[ValueObjectMetadata, ...]:
    """The value objects ``position``'s rows can carry.

    Production callers pass the compiled read's own ``documents`` — the resolved
    position's `Document` tier contributors, decided once where the projection
    was — so no level re-derives document provenance from a round-tripped Entity
    name. The Inheritance Facet projection remains the defensive direct-call
    fallback used by tests and older callers; only the SET of value objects, not
    their order, decides what a row's document columns hold."""
    if documents is not None:
        return tuple(documents)
    view = inheritance.view(meta).position(position)
    return () if view is None else tuple(view.superset_value_objects)


def identity_key(
    meta: Metamodel,
    entity_name: str,
    row: Mapping[str, object],
    narrow_to: tuple[str, ...] | None = None,
) -> tuple[EntityIdentity, tuple[object, ...]] | None:
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
    identity = declaring.identity
    if isinstance(view.strategy, TablePerConcreteSubtype):
        variant = row.get("familyVariant")
        identity = (
            _family_variant_identity(meta, entity, variant)
            if isinstance(variant, str)
            else _resolved_concrete_identity(meta, entity, narrow_to)
        )
    return (identity, pk)


def _resolved_concrete_identity(
    meta: Metamodel,
    entity: EntityMetadata,
    narrow_to: tuple[str, ...] | None,
    resolved_position: tuple[EntityIdentity, ...] | None = None,
) -> EntityIdentity:
    """The exact statically known concrete Identity for this decode call."""
    position = _resolved_position(meta, entity, narrow_to, resolved_position)
    return position[0] if len(position) == 1 else entity.identity


def _family_variant_identity(
    meta: Metamodel, entity: EntityMetadata, variant: object
) -> EntityIdentity:  # pragma: no cover - production supplies exact resolved identities
    """Resolve one familyVariant only inside ``entity``'s exact family."""
    if not isinstance(variant, str) or not variant:
        raise MaterializeError(f"familyVariant {variant!r} is not a nonempty Entity spelling")
    facet = inheritance.view(meta)
    view = facet.entity(entity.identity)
    if view is None:  # pragma: no cover - the facet covers every accepted Entity
        raise MaterializeError(f"{entity.identity.canonical}: no inheritance view")
    root = facet.entity(view.root)
    if root is None:  # pragma: no cover - every accepted family has a root view
        raise MaterializeError(f"{view.root.canonical}: no inheritance view")
    matches = (
        tuple(identity for identity in root.concrete_subtypes if identity.canonical == variant)
        if "." in variant
        else tuple(identity for identity in root.concrete_subtypes if identity.name == variant)
    )
    if len(matches) != 1:
        reason = "ambiguous" if len(matches) > 1 else "unknown"
        raise MaterializeError(
            f"familyVariant {variant!r} is {reason} within family {view.root.canonical!r}"
        )
    return matches[0]


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
    collapses to ``None`` — the whole composite absent — never a partial dict.

    Each leaf decodes by its DECLARED Neutral Type rather than by the JSON value's
    own shape, because a document stores a portable spelling and a member's
    materialized value is its managed one: a ``decimal`` is stored as an exact digit
    string, ``bytes`` as lowercase hexadecimal, and a ``timestamp`` as a UTC ISO
    instant, so copying the stored value through would hand a caller a ``str`` where
    the model declares a ``Decimal``, ``bytes``, or ``datetime``. A value the
    declared type does not spell passes through unchanged and stays whatever the row
    held.
    """
    if not isinstance(raw, Mapping):
        return None
    document = cast("Mapping[str, object]", raw)
    result: dict[str, object] = {}
    for attribute in container.attributes:
        stored = document.get(attribute.identity.name)
        result[attribute.identity.name] = (
            None if stored is None else decode_neutral_literal(stored, attribute.type)
        )
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
    entity = _entity(meta, entity_name)
    position = _resolved_position(meta, entity, narrow_to)
    value_objects = _superset_value_objects(meta, position)
    vo_columns = {vo.storage.name for vo in value_objects}
    fields: dict[str, object] = {key: value for key, value in row.items() if key not in vo_columns}
    for vo in value_objects:
        fields[vo.storage.name] = _decode_value_object(row.get(vo.storage.name), vo)
    return fields


def _decode_row_parts(
    meta: Metamodel,
    entity: EntityMetadata,
    row: Mapping[str, object],
    position: tuple[EntityIdentity, ...],
    documents: Sequence[ValueObjectMetadata] | None = None,
) -> tuple[dict[str, object], dict[str, object]]:
    """Decode one row while preserving scalar versus Value Object provenance."""
    value_objects = _superset_value_objects(meta, position, documents)
    vo_columns = {vo.storage.name for vo in value_objects}
    fields = {key: value for key, value in row.items() if key not in vo_columns}
    decoded = {
        vo.storage.name: _decode_value_object(row.get(vo.storage.name), vo) for vo in value_objects
    }
    return fields, decoded


# --------------------------------------------------------------------------- #
# The assembler.                                                              #
# --------------------------------------------------------------------------- #
def _new_identity_map() -> dict[tuple[EntityIdentity, tuple[object, ...]], Node]:
    return {}


@dataclass(slots=True)
class Assembler:
    """One materialization's graph builder: identity-keyed node registry plus
    per-level row decoding and fan-back. Not reused across materializations —
    graph-local identity resolution never promises a same-node reuse beyond one
    graph (m-snapshot-read)."""

    meta: Metamodel
    _identity: dict[tuple[EntityIdentity, tuple[object, ...]], Node] = field(
        default_factory=_new_identity_map
    )

    def materialize_root(
        self,
        entity_name: str,
        rows: Sequence[Mapping[str, object]],
        narrow_to: tuple[str, ...] | None = None,
        *,
        resolved_position: tuple[EntityIdentity, ...] | None = None,
        resolved_entities: Sequence[EntityIdentity] | None = None,
        family_variants: Sequence[str | None] | None = None,
        documents: Sequence[ValueObjectMetadata] | None = None,
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
        return self._materialize(
            entity_name,
            rows,
            narrow_to=narrow_to,
            resolved_position=resolved_position,
            resolved_entities=resolved_entities,
            family_variants=family_variants,
            documents=documents,
        )

    def attach_level(
        self,
        level: FetchLevel,
        parent_nodes: Sequence[Node],
        parent_rows: Sequence[Mapping[str, object]],
        child_rows: Sequence[Mapping[str, object]] | None,
        *,
        resolved_position: tuple[EntityIdentity, ...] | None = None,
        resolved_entities: Sequence[EntityIdentity] | None = None,
        family_variants: Sequence[str | None] | None = None,
        documents: Sequence[ValueObjectMetadata] | None = None,
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
                node.relationships[level.attach_key] = empty
            return []
        assert level.child_target is not None
        assert level.related_column is not None
        child_nodes = self._materialize(
            level.child_target,
            child_rows,
            level.narrow_to,
            resolved_position=resolved_position,
            resolved_entities=resolved_entities,
            family_variants=family_variants,
            documents=documents,
        )
        buckets: dict[object, list[Node]] = {}
        for row, node in zip(child_rows, child_nodes, strict=True):
            buckets.setdefault(row[level.related_column], []).append(node)
        for row, node in zip(parent_rows, parent_nodes, strict=True):
            matched = buckets.get(row[level.parent_column], [])
            node.relationships[level.attach_key] = (
                matched if level.to_many else _one_or_none(matched)
            )
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
                node.relationships[level.attach_key] = [] if level.to_many else None
                continue
            referenced = self._identity.get((level.back_reference_family, (fk,)))
            if referenced is None:  # pragma: no cover - guards a malformed plan
                raise MaterializeError(
                    f"back-reference {level.attach_key!r}: no already-materialized "
                    f"{level.back_reference_family} node for key {fk!r} (m-case-format "
                    "'Back-reference cycles' guarantees the ancestor is already known)"
                )
            node.relationships[level.attach_key] = [referenced] if level.to_many else referenced
        return []

    def _materialize(
        self,
        entity_name: str,
        rows: Sequence[Mapping[str, object]],
        narrow_to: tuple[str, ...] | None,
        *,
        resolved_position: tuple[EntityIdentity, ...] | None = None,
        resolved_entities: Sequence[EntityIdentity] | None = None,
        family_variants: Sequence[str | None] | None = None,
        documents: Sequence[ValueObjectMetadata] | None = None,
    ) -> list[Node]:
        entity = _entity(self.meta, entity_name)
        position = _resolved_position(self.meta, entity, narrow_to, resolved_position)
        pk_columns = _pk_columns(self.meta, entity_name)
        if resolved_entities is not None and len(resolved_entities) != len(rows):
            raise MaterializeError("resolved entity count does not match row count")
        if family_variants is not None and len(family_variants) != len(rows):
            raise MaterializeError("familyVariant count does not match row count")
        nodes: list[Node] = []
        for index, row in enumerate(rows):
            variant = (
                family_variants[index]
                if family_variants is not None
                else (
                    cast("str", row["familyVariant"])
                    if entity.inheritance is not None and isinstance(row.get("familyVariant"), str)
                    else None
                )
            )
            resolved_entity = (
                resolved_entities[index]
                if resolved_entities is not None
                else (
                    _family_variant_identity(self.meta, entity, variant)
                    if variant is not None
                    else _resolved_concrete_identity(
                        self.meta, entity, narrow_to, resolved_position
                    )
                )
            )
            fields, value_objects = _decode_row_parts(self.meta, entity, row, position, documents)
            if variant is not None:
                fields.pop("familyVariant", None)
            node = Node(
                fields=fields,
                pk_columns=pk_columns,
                resolved_entity=resolved_entity,
                value_objects=value_objects,
                family_variant=variant,
            )
            key = identity_key(self.meta, resolved_entity.canonical, row)
            if key is not None:
                self._identity.setdefault(key, node)
            nodes.append(node)
        return nodes


def _one_or_none(matched: list[Node]) -> Node | None:
    return matched[0] if matched else None
