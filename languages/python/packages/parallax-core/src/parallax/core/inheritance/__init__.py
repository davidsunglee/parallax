"""``parallax.core.inheritance`` enforcement scope (m-inheritance).

The closed inheritance-tree model: exactly one abstract ``root`` per descriptor,
interior ``abstract-subtype`` nodes, row-owning ``concrete-subtype`` leaves, and
the two strategies (table-per-hierarchy with a ``tag``/``tagValue`` discriminator,
table-per-concrete-subtype). It computes the effective concrete-subtype set (in
alphabetical order) for any polymorphic position and hosts the semantic
descriptor-rejection validator whose ordering pins each corpus ``rejectedRule``.
``m-inheritance`` depends only on ``m-descriptor``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from parallax.core.descriptor import Attribute, Entity, Inheritance, Metamodel, ValueObject

__all__ = [
    "Family",
    "InheritanceError",
    "ancestor_chain",
    "declaring_entity",
    "effective_concrete_subtypes",
    "family_attributes",
    "family_of",
    "family_root",
    "superset_value_objects",
    "validate",
]


class InheritanceError(ValueError):
    """A descriptor violates an m-inheritance family invariant.

    ``rule`` is the corpus ``rejectedRule`` classification (e.g.
    ``inheritance-cycle``); ``entity`` names the offending participant when one.
    """

    def __init__(self, rule: str, message: str, *, entity: str | None = None) -> None:
        super().__init__(message)
        self.rule = rule
        self.entity = entity


@dataclass(frozen=True, slots=True)
class Family:
    """The inheritance participants of one descriptor, indexed for traversal."""

    participants: tuple[Entity, ...]
    root: Entity | None

    @property
    def strategy(self) -> str | None:
        """The family mapping strategy declared by its root (``None`` if no root)."""
        if self.root is None:
            return None
        return _inh(self.root).strategy

    def _children(self) -> dict[str, list[Entity]]:
        children: dict[str, list[Entity]] = {}
        for entity in self.participants:
            parent = _inh(entity).parent
            if parent is not None:
                children.setdefault(parent, []).append(entity)
        return children

    def concrete_descendants(self, name: str) -> frozenset[str]:
        """Every concrete-subtype name at or under the position ``name``."""
        children = self._children()
        by_name = {entity.name: entity for entity in self.participants}
        result: set[str] = set()
        stack = [name]
        seen: set[str] = set()
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            entity = by_name.get(current)
            if entity is not None and _inh(entity).role == "concrete-subtype":
                result.add(current)
            stack.extend(child.name for child in children.get(current, []))
        return frozenset(result)


def _inh(entity: Entity) -> Inheritance:
    if entity.inheritance is None:  # pragma: no cover - callers guard on participation
        raise ValueError(f"{entity.name} is not an inheritance participant")
    return entity.inheritance


def _participants(metamodel: Metamodel) -> tuple[Entity, ...]:
    return tuple(entity for entity in metamodel.entities if entity.inheritance is not None)


def family_of(metamodel: Metamodel) -> Family:
    """The inheritance :class:`Family` of ``metamodel`` (empty when none participate)."""
    participants = _participants(metamodel)
    roots = [entity for entity in participants if _inh(entity).role == "root"]
    root = roots[0] if len(roots) == 1 else None
    return Family(participants=participants, root=root)


def effective_concrete_subtypes(metamodel: Metamodel, position: str) -> tuple[str, ...]:
    """The alphabetically-ordered effective concrete-subtype set for ``position``.

    A concrete subtype resolves to itself; an abstract root or subtype resolves to
    all concrete descendants; a plain (non-participant) entity is its own trivial
    set. The order is alphabetical (the corpus's effective-set ordering).
    """
    entity = metamodel.entity(position)
    if entity.inheritance is None:
        return (position,)
    if entity.inheritance.role == "concrete-subtype":
        return (position,)
    return tuple(sorted(family_of(metamodel).concrete_descendants(position)))


def _root_name(meta: Metamodel, entity: Entity) -> str | None:
    """The name of ``entity``'s family root, or ``None`` if unresolvable.

    Walks the ``parent`` chain rather than assuming a metamodel holds only one
    family (`family_of` does, which is fine for its own single-family callers but
    would silently misattribute a multi-family model's ancestry lookups).
    """
    current = entity
    seen: set[str] = set()
    while current.inheritance is not None:
        if current.inheritance.role == "root":
            return current.name
        parent = current.inheritance.parent
        if parent is None or current.name in seen:
            return None
        seen.add(current.name)
        current = meta.entity(parent)
    return None


def family_root(meta: Metamodel, entity: Entity) -> Entity:
    """The abstract root of ``entity``'s inheritance family.

    Raises :class:`ValueError` if ``entity`` does not participate, or its
    ancestry does not resolve to a root (a malformed family; `validate` is the
    authority on rejecting those before this is ever called).
    """
    root_name = _root_name(meta, entity)
    if root_name is None:
        raise ValueError(f"{entity.name}: no resolvable inheritance root (m-inheritance)")
    return meta.entity(root_name)


def declaring_entity(meta: Metamodel, entity: Entity) -> Entity:
    """The entity that actually DECLARES ``entity``'s primary key and temporal
    (as-of) axes: the family root for an inheritance participant — temporality
    is a FAMILY-WIDE property (the binding COR-3 residual-finding correction),
    so the primary key and every as-of axis are always declared on the root
    ALONE and inherited unchanged by every abstract and concrete descendant
    ("Inherited members"); a descendant MUST NOT redeclare, add, remove,
    override, or shadow them (the `inheritance-temporal-axes-not-root-owned`
    family invariant, enforced by :func:`validate`) — else ``entity`` itself.

    The one shared resolution every DAG-legal caller needing an inheritance
    participant's declaring entity reuses: graph-local identity / primary-key
    resolution (`m-snapshot-read`), per-hop temporal propagation (`m-navigate`),
    frozen-node pin/edge attachment (the snapshot handle's wrap), and
    inheritance-aware DDL derivation (the conformance provisioning path).
    """
    if entity.inheritance is None:
        return entity
    return family_root(meta, entity)


def ancestor_chain(meta: Metamodel, effective_concretes: Sequence[str]) -> tuple[Entity, ...]:
    """Every abstract ancestor (root + abstract-subtype) reachable from any
    concrete in ``effective_concretes``, in canonical ancestry order (m-inheritance
    "Canonical concrete-subtype ordering": the inherited-column prefix of a
    superset stays ancestry order, root first, never alphabetized across the
    chain).

    Processes ``effective_concretes`` in the family's own canonical alphabetical
    order and appends each concrete's own ancestor chain (root-to-parent) in that
    order, skipping an ancestor already added — the deterministic "first
    encountered" union a shared ancestor (e.g. the root) needs when several
    concretes in the set pass through it.
    """
    ordered: list[Entity] = []
    seen: set[str] = set()
    for name in sorted(effective_concretes):
        chain: list[Entity] = []
        start_inheritance = meta.entity(name).inheritance
        parent_name = start_inheritance.parent if start_inheritance is not None else None
        while parent_name is not None:
            ancestor = meta.entity(parent_name)
            chain.append(ancestor)
            parent_name = ancestor.inheritance.parent if ancestor.inheritance is not None else None
        for ancestor in reversed(chain):
            if ancestor.name not in seen:
                seen.add(ancestor.name)
                ordered.append(ancestor)
    return tuple(ordered)


def family_attributes(meta: Metamodel, entity: Entity) -> tuple[Attribute, ...]:
    """Every attribute declared anywhere in ``entity``'s inheritance family.

    Used to resolve an attribute reference whose ``Class.attribute`` class-name
    prefix names any ancestor or sibling concrete within the same family (a
    concrete-target read referencing a root-inherited attribute, or a branch
    predicate inside a `narrow` referencing that branch's own attribute, m-sql
    predicate lowering) — narrow-position validity for the reference is already
    enforced upstream by `m-op-algebra`'s model-aware validator, so this need only
    search, never re-validate scope. Assumes attribute names are unique within one
    family (the shared-table / ancestry-derived column set is a disjoint union,
    m-inheritance).
    """
    root_name = _root_name(meta, entity)
    if root_name is None:
        return entity.attributes
    attrs: list[Attribute] = []
    for candidate in meta.entities:
        if candidate.inheritance is not None and _root_name(meta, candidate) == root_name:
            attrs.extend(candidate.attributes)
    return tuple(attrs)


def superset_value_objects(meta: Metamodel, position: Sequence[str]) -> list[ValueObject]:
    """Every value object reachable from ``position`` (an effective concrete
    set), in the family's stable superset order: each ancestor's own value
    objects in ancestry order, then each position concrete's own in canonical
    alphabetical order.

    The one shared resolution both `m-sql`'s abstract-read/union-all
    projection and `m-snapshot-read`'s row-decoding superset use — DAG-safe for
    both (each already depends on `m-inheritance` directly: `m-sql` through
    `m-op-algebra`, `m-snapshot-read` through `m-deep-fetch` -> `m-navigate`),
    so the identical family-value-object walk lives here once rather than
    staying duplicated in each caller.
    """
    value_objects: list[ValueObject] = []
    for ancestor in ancestor_chain(meta, position):
        value_objects.extend(ancestor.value_objects)
    for name in sorted(position):
        value_objects.extend(meta.entity(name).value_objects)
    return value_objects


def validate(metamodel: Metamodel) -> None:
    """Validate every inheritance family invariant, raising :class:`InheritanceError`.

    The check order pins each corpus ``rejectedRule``: parent resolution, then
    acyclicity, tableless-abstract nodes, strategy locality, temporal-axis root
    ownership, strategy-vs-tag coherence, ancestry-reaches-a-root, root
    cardinality, and the table-per-hierarchy tag rules.
    """
    participants = _participants(metamodel)
    if not participants:
        return
    by_name = {entity.name: entity for entity in metamodel.entities}
    roots = [entity for entity in participants if _inh(entity).role == "root"]

    _reject_unknown_parent(participants, by_name)
    _reject_cycles(participants)
    _reject_abstract_with_table(participants)
    _reject_strategy_redeclared(participants)
    _reject_descendant_temporal_axes(participants)
    _reject_tag_under_tpcs(roots, participants)
    _reject_concrete_without_root(participants, by_name)
    _reject_root_cardinality(roots)
    _reject_tph_tag_values(roots, participants)


def _reject_unknown_parent(participants: tuple[Entity, ...], by_name: dict[str, Entity]) -> None:
    for entity in participants:
        parent = _inh(entity).parent
        if parent is not None and parent not in by_name:
            raise InheritanceError(
                "inheritance-unknown-parent",
                f"{entity.name} names parent {parent!r}, which the descriptor does not declare",
                entity=entity.name,
            )


def _reject_cycles(participants: tuple[Entity, ...]) -> None:
    by_name = {entity.name: entity for entity in participants}
    for start in participants:
        seen: set[str] = set()
        current: str | None = start.name
        while current is not None and current in by_name:
            if current in seen:
                raise InheritanceError(
                    "inheritance-cycle",
                    f"parent links form a cycle through {current!r}",
                    entity=current,
                )
            seen.add(current)
            current = _inh(by_name[current]).parent


def _reject_abstract_with_table(participants: tuple[Entity, ...]) -> None:
    for entity in participants:
        role = _inh(entity).role
        if role in ("root", "abstract-subtype") and entity.table is not None:
            raise InheritanceError(
                "inheritance-abstract-node-with-table",
                f"abstract {role} {entity.name} is tableless and rowless but declares a table",
                entity=entity.name,
            )


def _reject_strategy_redeclared(participants: tuple[Entity, ...]) -> None:
    for entity in participants:
        inh = _inh(entity)
        if inh.role != "root" and inh.strategy is not None:
            raise InheritanceError(
                "inheritance-strategy-redeclared",
                f"non-root {entity.name} redeclares the family strategy",
                entity=entity.name,
            )


def _reject_descendant_temporal_axes(participants: tuple[Entity, ...]) -> None:
    """Reject any ``abstract-subtype`` or ``concrete-subtype`` that declares its
    own ``asOfAttributes``.

    Temporality is a family-wide property: only the family ROOT may declare
    as-of axes, and every descendant inherits exactly that set (never
    redeclares, adds, removes, overrides, or shadows an axis) — regardless of
    whether the root itself is temporal. A non-temporal root with a temporal
    descendant would leave the family's root-owned coordinate system
    ill-defined (mixed temporality is not supported); a temporal root whose
    descendant redeclares or adds an axis would make the descendant's own
    temporal profile diverge from the family it belongs to. Both shapes are
    rejected here, uniformly, before any SQL.
    """
    for entity in participants:
        if _inh(entity).role != "root" and entity.as_of_attributes:
            raise InheritanceError(
                "inheritance-temporal-axes-not-root-owned",
                f"non-root {entity.name} declares its own as-of axes; temporal axes are a "
                "family-wide property and MUST be declared only on the root",
                entity=entity.name,
            )


def _reject_tag_under_tpcs(roots: list[Entity], participants: tuple[Entity, ...]) -> None:
    if len(roots) != 1:
        return
    root = roots[0]
    if _inh(root).strategy != "table-per-concrete-subtype":
        return
    if _inh(root).tag_column is not None:
        raise InheritanceError(
            "inheritance-tag-on-concrete-subtype-strategy",
            f"table-per-concrete-subtype root {root.name} declares a tag column",
            entity=root.name,
        )
    for entity in participants:
        if _inh(entity).tag_value is not None:
            raise InheritanceError(
                "inheritance-tag-on-concrete-subtype-strategy",
                f"table-per-concrete-subtype subtype {entity.name} declares a tagValue",
                entity=entity.name,
            )


def _reject_concrete_without_root(
    participants: tuple[Entity, ...], by_name: dict[str, Entity]
) -> None:
    for entity in participants:
        if _inh(entity).role != "concrete-subtype":
            continue
        current: str | None = entity.name
        reached_root = False
        while current is not None:
            node = by_name.get(current)
            if node is None or node.inheritance is None:
                break
            if node.inheritance.role == "root":
                reached_root = True
                break
            current = node.inheritance.parent
        if not reached_root:
            raise InheritanceError(
                "inheritance-concrete-without-abstract-root",
                f"concrete subtype {entity.name} has no abstract root ancestor",
                entity=entity.name,
            )


def _reject_root_cardinality(roots: list[Entity]) -> None:
    if len(roots) == 0:
        raise InheritanceError(
            "inheritance-missing-root",
            "inheritance participants declare no root",
        )
    if len(roots) > 1:
        raise InheritanceError(
            "inheritance-multiple-roots",
            f"more than one inheritance root: {sorted(root.name for root in roots)}",
        )


def _reject_tph_tag_values(roots: list[Entity], participants: tuple[Entity, ...]) -> None:
    root = roots[0]
    if _inh(root).strategy != "table-per-hierarchy":
        return
    concretes = [entity for entity in participants if _inh(entity).role == "concrete-subtype"]
    seen_values: dict[str, str] = {}
    seen_tables: dict[str, str] = {}
    for entity in concretes:
        tag_value = _inh(entity).tag_value
        if tag_value is None:
            raise InheritanceError(
                "inheritance-missing-tag-value",
                f"table-per-hierarchy concrete subtype {entity.name} declares no tagValue",
                entity=entity.name,
            )
        if tag_value in seen_values:
            raise InheritanceError(
                "inheritance-duplicate-tag-value",
                f"tagValue {tag_value!r} is shared by {seen_values[tag_value]} and {entity.name}",
                entity=entity.name,
            )
        seen_values[tag_value] = entity.name
        if entity.table is not None:
            seen_tables[entity.table] = entity.name
    if len(seen_tables) > 1:
        raise InheritanceError(
            "inheritance-inconsistent-hierarchy-table",
            f"table-per-hierarchy concrete subtypes map to different tables: {sorted(seen_tables)}",
        )
