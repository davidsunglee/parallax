"""``parallax.core.inheritance`` enforcement scope (m-inheritance).

The closed inheritance-tree model: exactly one abstract ``root``, interior
``abstract-subtype`` nodes, row-owning ``concrete-subtype`` leaves, and the two
strategies (table-per-hierarchy with a tag discriminator,
table-per-concrete-subtype). This scope owns the family invariants a model must
satisfy and the Inheritance Facet that answers, once per formation, every
family-effective question — ancestry, family identity, effective
concrete-subtype sets, member applicability, physical container and tag, and the
root-owned Persistence Mode — so a consumer reads a precomputed family fact
instead of recomputing it. ``m-inheritance`` depends on ``m-descriptor``,
``m-metamodel``, and ``m-model-formation``.

It also owns :func:`column_order`, the canonical physical column order of an
Entity's table: the order is family-effective, and the table-per-hierarchy tag
is the one physical column no declared Attribute backs.

Consumers reach the facet through :func:`view`, so generic facet retrieval stays
an internal formation seam.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from parallax.core.base import decode_neutral_literal, matches_neutral_type
from parallax.core.descriptor import (
    Attribute,
    Entity,
    Inheritance,
    Metamodel,
    ValueObject,
)
from parallax.core.descriptor import declaring_entity as _resolve_declaring_entity
from parallax.core.inheritance._columns import column_order
from parallax.core.inheritance._compile import (
    MODEL_COMPILER,
    InheritanceModelCompiler,
    compile_facet,
    root_metadata,
)
from parallax.core.inheritance._facet import (
    FACET_KEY,
    INHERITANCE_MODULE,
    InheritanceEntityView,
    InheritanceFacet,
    InheritancePositionView,
    view,
)
from parallax.core.inheritance._rules import (
    CONCRETE_WITHOUT_ABSTRACT_ROOT,
    CYCLE,
    DUPLICATE_TAG_VALUE,
    ISSUE_CODES,
    MEMBER_SHADOWING,
    MISSING_ROOT,
    MISSING_TAG_VALUE,
    OPTIMISTIC_LOCKING_NOT_ROOT_OWNED,
    PERSISTENCE_NOT_ROOT_OWNED,
    PRIMARY_KEY_MISSING,
    PRIMARY_KEY_MULTIPLE,
    RULE_SET,
    STRATEGY_REDECLARED,
    TAG_ON_CONCRETE_SUBTYPE_STRATEGY,
    TEMPORAL_AXES_NOT_ROOT_OWNED,
    TPCS_ABSTRACT_TABLE_FORBIDDEN,
    TPCS_CONCRETE_TABLE_REQUIRED,
    TPH_DESCENDANT_TABLE_FORBIDDEN,
    TPH_ROOT_TABLE_REQUIRED,
    InheritanceRuleSet,
)
from parallax.core.metamodel import (
    AbstractRoot,
    AbstractSubtype,
    ConcreteSubtype,
    EntityIdentity,
    EntityMetadata,
    PrimaryKey,
    VoDocumentViolation,
    vo_document_violation,
)
from parallax.core.metamodel import Metamodel as AcceptedMetamodel

__all__ = [
    "CONCRETE_WITHOUT_ABSTRACT_ROOT",
    "CYCLE",
    "DUPLICATE_TAG_VALUE",
    "FACET_KEY",
    "INHERITANCE_MODULE",
    "ISSUE_CODES",
    "MEMBER_SHADOWING",
    "MISSING_ROOT",
    "MISSING_TAG_VALUE",
    "MODEL_COMPILER",
    "OPTIMISTIC_LOCKING_NOT_ROOT_OWNED",
    "PERSISTENCE_NOT_ROOT_OWNED",
    "PRIMARY_KEY_MISSING",
    "PRIMARY_KEY_MULTIPLE",
    "RULE_SET",
    "STRATEGY_REDECLARED",
    "TAG_ON_CONCRETE_SUBTYPE_STRATEGY",
    "TEMPORAL_AXES_NOT_ROOT_OWNED",
    "TPCS_ABSTRACT_TABLE_FORBIDDEN",
    "TPCS_CONCRETE_TABLE_REQUIRED",
    "TPH_DESCENDANT_TABLE_FORBIDDEN",
    "TPH_ROOT_TABLE_REQUIRED",
    "Family",
    "InheritanceEntityView",
    "InheritanceError",
    "InheritanceFacet",
    "InheritanceModelCompiler",
    "InheritancePositionView",
    "InheritanceRuleSet",
    "WriteAssignmentError",
    "ancestor_chain",
    "column_order",
    "compile_facet",
    "declaring_entity",
    "effective_concrete_subtypes",
    "effective_table",
    "family_attributes",
    "family_of",
    "family_primary_key",
    "family_root",
    "reject_predicate_write",
    "root_metadata",
    "superset_value_objects",
    "validate",
    "validate_subtype_write",
    "validate_write_assignment",
    "view",
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
    """The inheritance :class:`Family` of ``metamodel`` (empty when none participate).

    ``root`` is named only when the descriptor declares exactly one: a
    descriptor carrying several independent families (or none at all) has no
    single root to name, so ``root`` is ``None`` and a caller needing a
    particular position's root resolves it with :func:`family_root`.
    """
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
        return (entity.name,)
    return tuple(sorted(family_of(metamodel).concrete_descendants(entity.name)))


def effective_table(metamodel: Metamodel, entity: Entity) -> str | None:
    """The physical table used by ``entity`` under its family's strategy.

    A TPH participant resolves to the root-owned shared table without copying that
    declaration into descendant Metadata. A TPCS participant and a standalone
    Entity use their own declared table.
    """
    if entity.inheritance is None:
        return entity.table
    root = family_root(metamodel, entity)
    if root.inheritance is not None and root.inheritance.strategy == "table-per-hierarchy":
        return root.table
    return entity.table


def _root_name(meta: Metamodel, entity: Entity) -> str | None:
    """The name of ``entity``'s family root, or ``None`` if unresolvable.

    Composes with the shared ``m-descriptor``-scope ancestry walk
    (:func:`~parallax.core.descriptor.declaring_entity`) rather than
    re-deriving it: the descriptor-level resolver already "resolves to what
    it can reach" for a malformed (cyclic/unresolvable) ancestry, falling back
    to ``entity`` itself, which is never a root — so this only needs to check
    the resolved entity's own role, never re-walk ``parent`` links itself.
    """
    if entity.inheritance is None:
        return None
    resolved = _resolve_declaring_entity(meta, entity)
    if resolved.inheritance is None or resolved.inheritance.role != "root":
        return None
    return resolved.name


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
    is a FAMILY-WIDE property,
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

    A thin ``m-inheritance``-scope alias over the shared ``m-descriptor``-scope
    walk (:func:`~parallax.core.descriptor.declaring_entity`) — never re-derived
    here — kept as its own name in this module because every caller above
    already depends on ``m-inheritance``, never ``m-descriptor`` directly, for
    this family-aware resolution.
    """
    return _resolve_declaring_entity(meta, entity)


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


def family_primary_key(meta: Metamodel, entity: Entity) -> tuple[Attribute, ...]:
    """``entity``'s FAMILY-EFFECTIVE primary key (m-inheritance "Inherited
    members"): declared on the root alone and inherited unchanged by every
    abstract and concrete descendant — exactly the temporal-axis and
    optimistic-locking root-ownership rules, applied to the identity key
    itself. ``Entity.primary_key`` is a bare LOCAL view (``self.attributes``
    filtered): for a concrete subtype whose key is declared on an ancestor
    (every corpus family), that view is wrongly EMPTY, which would silently
    make a keyed write / observation / coalescing lookup unidentifiable
    (`m-unit-work` object identity, `m-sql` keyed DML). Composes with
    :func:`family_attributes` rather than re-deriving the family walk.
    """
    return tuple(attr for attr in family_attributes(meta, entity) if attr.primary_key)


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

    The check order pins each corpus ``rejectedRule``: parent resolution,
    acyclicity, strategy and family-owned-fact locality, ancestry-reaches-a-root,
    missing-root detection, then the selected strategy's table/tag formation
    rules. The last three are asked once per independent family, so a descriptor
    declaring several never has one family's root or strategy answer for another.
    """
    participants = _participants(metamodel)
    if not participants:
        return
    by_name = {entity.name: entity for entity in metamodel.entities}

    _reject_unknown_parent(participants, by_name)
    _reject_cycles(participants)
    _reject_strategy_redeclared(participants)
    _reject_descendant_temporal_axes(participants)
    _reject_descendant_optimistic_locking(participants)
    _reject_concrete_without_root(participants, by_name)
    rooted = [
        (_reject_missing_root(root, members), members)
        for root, members in _families(participants, by_name)
    ]
    for root, members in rooted:
        _reject_strategy_storage(root, members)
    for root, members in rooted:
        _reject_tph_tag_values(root, members)


def _families(
    participants: tuple[Entity, ...], by_name: dict[str, Entity]
) -> list[tuple[Entity | None, tuple[Entity, ...]]]:
    """Each independent inheritance family of ``participants``: the topmost
    position its members' parent links reach (``None`` when that position is not
    a root), paired with the members themselves in declaration order.

    A position has at most one parent, so two roots can never share an ancestry
    and every participant belongs to exactly one family. Valid only once unknown
    parents and cycles are rejected: either would leave the upward walk without
    a terminating top.
    """
    grouped: dict[str, list[Entity]] = {}
    for entity in participants:
        grouped.setdefault(_family_top(entity, by_name).name, []).append(entity)
    families: list[tuple[Entity | None, tuple[Entity, ...]]] = []
    for name, members in grouped.items():
        top = by_name[name]
        families.append((top if _inh(top).role == "root" else None, tuple(members)))
    return families


def _family_top(entity: Entity, by_name: dict[str, Entity]) -> Entity:
    """The highest participant ``entity``'s parent links reach — itself when it
    declares no parent, and the last participant on the chain when the chain
    leaves the family (a parent that declares no inheritance of its own)."""
    top = entity
    while True:
        parent = _inh(top).parent
        if parent is None:
            return top
        ancestor = by_name.get(parent)
        if ancestor is None or ancestor.inheritance is None:
            return top
        top = ancestor


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
        if _inh(entity).role != "root" and entity.as_of_axes:
            raise InheritanceError(
                "inheritance-temporal-axes-not-root-owned",
                f"non-root {entity.name} declares its own as-of axes; temporal axes are a "
                "family-wide property and MUST be declared only on the root",
                entity=entity.name,
            )


def _reject_descendant_optimistic_locking(participants: tuple[Entity, ...]) -> None:
    """Reject any ``abstract-subtype`` or ``concrete-subtype`` that declares its
    own ``optimisticLocking`` attribute.

    The version attribute is a family-wide property (ADR 0027): only the
    family ROOT may declare it, and every descendant inherits exactly that
    column — regardless of whether the root itself is versioned. This is
    structural per-entity (it does not need to look at the root's own
    attributes), so it fires uniformly for both malformed shapes: a
    non-versioned root with a version-declaring descendant, and a versioned
    root whose descendant redeclares or adds a second version attribute.
    """
    for entity in participants:
        if _inh(entity).role == "root":
            continue
        if any(attribute.optimistic_locking for attribute in entity.attributes):
            raise InheritanceError(
                "inheritance-optimistic-locking-not-root-owned",
                f"non-root {entity.name} declares its own optimisticLocking attribute; "
                "the version attribute is family-wide and MUST be declared only on the "
                "root",
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


def _reject_missing_root(root: Entity | None, members: tuple[Entity, ...]) -> Entity:
    """``root`` itself once it is one, so a family that reaches no root is
    rejected here rather than surfacing as a missing strategy downstream."""
    if root is None:
        raise InheritanceError(
            "inheritance-missing-root",
            f"inheritance participants {sorted(member.name for member in members)} declare no root",
        )
    return root


def _reject_strategy_storage(root: Entity, participants: tuple[Entity, ...]) -> None:
    strategy = _inh(root).strategy
    if strategy == "table-per-hierarchy":
        if root.table is None:
            raise InheritanceError(
                "inheritance-tph-root-table-required",
                f"table-per-hierarchy root {root.name} declares no shared table",
                entity=root.name,
            )
        for entity in participants:
            if entity is not root and entity.table is not None:
                raise InheritanceError(
                    "inheritance-tph-descendant-table-forbidden",
                    f"table-per-hierarchy descendant {entity.name} repeats the root-owned "
                    "shared table",
                    entity=entity.name,
                )
        return

    if strategy != "table-per-concrete-subtype":
        return
    for entity in participants:
        role = _inh(entity).role
        if role in ("root", "abstract-subtype") and entity.table is not None:
            raise InheritanceError(
                "inheritance-tpcs-abstract-table-forbidden",
                f"table-per-concrete-subtype abstract position {entity.name} declares a table",
                entity=entity.name,
            )
        if role == "concrete-subtype" and entity.table is None:
            raise InheritanceError(
                "inheritance-tpcs-concrete-table-required",
                f"table-per-concrete-subtype concrete {entity.name} declares no table",
                entity=entity.name,
            )
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


def _reject_tph_tag_values(root: Entity, participants: tuple[Entity, ...]) -> None:
    if _inh(root).strategy != "table-per-hierarchy":
        return
    concretes = [entity for entity in participants if _inh(entity).role == "concrete-subtype"]
    seen_values: dict[str, str] = {}
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


# --------------------------------------------------------------------------- #
# Concrete-subtype write protocol (m-inheritance "Concrete-subtype writes"):  #
# the payload-shape rules a model-aware write                                 #
# validator MUST enforce before the target-validity rule, pre-SQL. `entity`   #
# is the write's resolved target (a concrete subtype for an idiomatic keyed   #
# verb; the family root by the rejected lane's own "no explicit handle"       #
# default, `m-op-algebra`'s target-resolution convention reused for writes)   #
# -- an abstract `entity` is itself the LAST-checked defect, never short-     #
# circuited ahead of the more specific payload-shape rules.                   #
# --------------------------------------------------------------------------- #
_FORBIDDEN_METADATA_KEYS: frozenset[str] = frozenset({"tag", "tagValue", "familyVariant"})


def validate_subtype_write(
    model: AcceptedMetamodel, entity: EntityMetadata, row: Mapping[str, object]
) -> None:
    """Validate a concrete-subtype write payload's SHAPE, raising :class:`InheritanceError`.

    A no-op for a non-participant ``entity`` (every entity outside an inheritance
    family accepts any well-formed row shape here). For a participant, checks in
    the normative order (m-inheritance "A validator checks these payload-shape
    rules... before the target-validity rule"): **keyless**
    (``subtype-write-set-based-unsupported`` -- ``row`` carries none of the
    family's root-owned primary-key attributes, denoting an unsupported
    set-based write), **metadata** (``subtype-write-metadata-field`` -- ``row``
    carries the framework-owned tag column / ``tag`` / ``tagValue`` /
    ``familyVariant``), **sibling** (``subtype-write-sibling-attribute`` -- no
    single concrete subtype in ``entity``'s effective set accepts every field
    ``row`` carries), then **target-validity**
    (``abstract-write-target`` -- ``entity`` itself is not a concrete subtype).
    A payload tripping more than one defect pins the earliest, most specific one.
    """
    if entity.inheritance is None:
        return
    facet = view(model)
    position = _entity_view(facet, entity.identity)
    root = _entity_view(facet, position.root)
    pk_names = frozenset(
        attribute.identity.name
        for attribute in root.applicable_attributes
        if isinstance(attribute.primary_key, PrimaryKey)
    )
    name = entity.identity.name
    if not pk_names & row.keys():
        raise InheritanceError(
            "subtype-write-set-based-unsupported",
            f"{name}: write carries none of the family's primary-key attribute(s) "
            f"{sorted(pk_names)} -- a keyless payload denotes an unsupported set-based "
            "inheritance write",
            entity=name,
        )
    forbidden = _FORBIDDEN_METADATA_KEYS
    if position.tag_column is not None:
        forbidden = forbidden | {position.tag_column}
    carried_metadata = sorted(forbidden & row.keys())
    if carried_metadata:
        raise InheritanceError(
            "subtype-write-metadata-field",
            f"{name}: write carries framework-owned metadata field(s) "
            f"{carried_metadata} -- the tag / tagValue / familyVariant are derived, never "
            "authored",
            entity=name,
        )
    effective = tuple(concrete.name for concrete in position.concrete_subtypes)
    accepted = _concrete_accepted_field_names(facet, position.concrete_subtypes)
    candidate_fields = frozenset(row)
    if not any(candidate_fields <= names for names in accepted):
        raise InheritanceError(
            "subtype-write-sibling-attribute",
            f"{name}: no single concrete subtype in the effective set {sorted(effective)} "
            f"accepts every field {sorted(candidate_fields)} -- the accepted fields are exactly "
            "the target's own ancestry chain",
            entity=name,
        )
    if not isinstance(entity.inheritance, ConcreteSubtype):
        raise InheritanceError(
            "abstract-write-target",
            f"{name}: a create/update/delete/terminate handle MUST name a concrete "
            f"subtype, not the abstract {_ABSTRACT_ROLES[type(entity.inheritance)]}",
            entity=name,
        )


# The role spellings an abstract position reports. The variant is the role, so
# the algebra carries no role field of its own; a concrete position never
# reaches this table.
_ABSTRACT_ROLES: Mapping[type, str] = {
    AbstractRoot: "root",
    AbstractSubtype: "abstract-subtype",
}


def _entity_view(facet: InheritanceFacet, identity: EntityIdentity) -> InheritanceEntityView:
    """``identity``'s family-effective view; the facet covers every accepted Entity."""
    position = facet.entity(identity)
    if position is None:  # pragma: no cover - the facet covers every accepted Entity
        raise ValueError(f"{identity.canonical}: the model declares no such entity")
    return position


def reject_predicate_write(entity: EntityMetadata) -> None:
    """Reject a predicate-selected (set-based) write on ANY inheritance-family
    ``entity`` — root, abstract-subtype, or concrete-subtype alike — with the
    SAME ``subtype-write-set-based-unsupported`` classification
    :func:`validate_subtype_write`'s keyless-row branch raises (`m-inheritance`
    "Per-object writes are keyed; set-based inheritance writes are out of
    scope").

    A deliberate, TARGET-ENTITY-ONLY call shape:
    a predicate-selected write is set-based BY CONSTRUCTION (there is no row at
    all, keyed or otherwise), so this needs no row inspection and never
    synthesizes a fake keyless row just to trigger
    :func:`validate_subtype_write`'s own branch — both the developer-facing
    ``_where`` verb family (`python.md` §5) and the conformance engine's
    predicate-write translation call this SAME function, so the two callers
    can never classify an inheritance-family predicate write differently. A
    no-op for a non-participant ``entity`` (every entity outside an
    inheritance family accepts a predicate-selected write, subject to every
    OTHER m-batch-write / m-opt-lock rule).
    """
    if entity.inheritance is None:
        return
    name = entity.identity.name
    raise InheritanceError(
        "subtype-write-set-based-unsupported",
        f"{name}: a predicate-selected (set-based) write on an inheritance-family "
        "entity is unsupported (subtype-write-set-based-unsupported) — per-object writes "
        "are keyed (m-inheritance 'Per-object writes are keyed; set-based inheritance "
        "writes are out of scope')",
        entity=name,
    )


class WriteAssignmentError(ValueError):
    """A predicate-write assignment (`.set(...)`-built or case-authored) names
    an unassignable target or an ill-typed value (`python.md:667-676`;
    `m-case-format.md:700`/`:711` "framework-owned/unassignable assignments").
    ``rule`` is the shared classification both callers reuse verbatim in their
    own error text."""

    def __init__(self, rule: str, message: str) -> None:
        super().__init__(message)
        self.rule = rule


def validate_write_assignment(
    model: AcceptedMetamodel, entity: EntityMetadata, name: str, value: object
) -> None:
    """The ONE predicate-write assignment check every caller applies to one
    `{attr, value}` pair (`m-opt-lock` "Version values are framework-owned";
    `python.md` §5 "each field may be assigned at most once"): mirroring
    `model_copy`'s own assignability rule (`parallax.core.entity.base.
    _validate_copy_keys`), a primary-key or optimistic-locking (version)
    target is rejected outright — a family's version/key columns are declared
    only on the root, so this walk reads the Inheritance Facet's FAMILY-EFFECTIVE
    applicable members, exactly like every other write-side member-name
    resolution. Neither `entity.expressions.AttributeExpr.set` (the typed path,
    `parallax.core.entity`) nor `unit_work.instructions.validate_instruction`
    (the case-authored engine/serialized path, `parallax.core.unit_work`) may
    import the other (`core/spec/modules.md` §7 DAG), so this classification
    lives here, the ONE scope both already depend on — the "one validator, two
    callers" pattern (`parallax.core.op_algebra.validate_operation` /
    `parallax.core.unit_work.write_validate.validate_write`'s own precedent)
    extended across a DAG boundary neither scope alone can bridge.

    For an ordinary scalar attribute, a non-``None`` ``value`` MUST also
    conform to its declared `m-core` neutral type (`matches_neutral_type` over
    the decoded literal, the SAME exact scalar-value policy `write_validate`
    applies to a keyed write row). A ``None`` value is a legal CLEARING
    assignment ONLY when the attribute is declared ``nullable`` (mirroring
    `write_validate`'s own null short-circuit, which is likewise
    nullable-gated, `_check_entity_attribute`) — a NON-nullable scalar assigned
    ``None`` is rejected with the SAME `"required attribute is absent (or
    null)"` wording `write_validate`'s own required-attribute check uses
    (`None` is an explicit clearing attempt here, never an omitted/sparse
    member the way an absent keyed-write row key is, so this check is
    UNCONDITIONAL — there is no mutation-aware sparseness concept at the
    assignment boundary, every named assignment is "present" by construction).

    A ``name`` naming a VALUE-OBJECT member instead (FAMILY-EFFECTIVE through the
    same facet view) is likewise validated: a non-``None`` ``value`` MUST be a
    well-formed document against the member's declared composite — the SAME
    error-neutral structural walk `write_validate`'s own declared-composite
    check reuses (`parallax.core.metamodel.vo_document_violation`), so a
    non-document value (e.g. ``Customer.address.set(42)``, typed or the
    equivalent serialized ``PredicateWrite`` assignment) is rejected with this
    function's OWN established wording style; a well-formed document is accepted
    — assigning a value object is not itself rejected (the combination is
    structurally accepted). A ``None`` value is likewise a legal clearing
    assignment ONLY when the value object is declared ``nullable``
    (`m-value-object` "A `nullable: false` value object MUST be present at write
    time") — a NON-nullable value object assigned ``None`` is rejected reusing
    `vo_document_violation`'s own ``"value-object-missing"`` rendering
    (`_vo_assignment_error`, the SAME `"required value object is absent (or
    null)"` wording a nested required-VO violation already renders) rather than
    forking new text. A ``name`` this family declares NEITHER a scalar attribute
    NOR a value object for (one `validate_instruction`'s own
    member-name-honesty gate already rejects as wholly undeclared) is out of
    this function's scope — it returns silently, leaving that classification to
    its own owning check.
    """
    position = _entity_view(view(model), entity.identity)
    owner = entity.identity.name
    for attribute in position.applicable_attributes:
        if attribute.identity.name != name:
            continue
        if isinstance(attribute.primary_key, PrimaryKey):
            raise WriteAssignmentError(
                "primary-key", f"{owner}.{name}: primary-key fields may not be assigned"
            )
        if attribute.optimistic_locking:
            raise WriteAssignmentError(
                "optimistic-locking",
                f"{owner}.{name}: framework-owned fields (the version column) may not be assigned",
            )
        if value is None:
            if not attribute.nullable:
                raise WriteAssignmentError(
                    "value-type-mismatch",
                    f"{owner}.{name}: required attribute is absent (or null)",
                )
            return
        if not matches_neutral_type(decode_neutral_literal(value, attribute.type), attribute.type):
            raise WriteAssignmentError(
                "value-type-mismatch",
                f"{owner}.{name}: value {value!r} does not match the declared type "
                f"{attribute.type!r}",
            )
        return
    for value_object in position.applicable_value_objects:
        if value_object.identity.path[-1] != name:
            continue
        if value is None:
            if not value_object.nullable:
                raise _vo_assignment_error(
                    owner, name, VoDocumentViolation("", "value-object-missing")
                )
            return
        violation = vo_document_violation(value_object, value)
        if violation is not None:
            raise _vo_assignment_error(owner, name, violation)
        return


def _vo_assignment_error(
    entity_name: str, name: str, violation: VoDocumentViolation
) -> WriteAssignmentError:
    """Render :func:`validate_write_assignment`'s OWN rule vocabulary and
    message text (the ``"value-type-mismatch"`` rule, the SAME one a scalar
    mismatch raises — a malformed value-object assignment is, from this
    function's own vocabulary, just another shape of "the value does not
    match the declared type") from a shared, error-neutral
    ``parallax.core.descriptor.vo_document`` violation — that module owns no
    text of its own, see its own docstring."""
    path = _joined(f"{entity_name}.{name}", violation.path)
    if violation.reason == "not-a-list":
        return WriteAssignmentError(
            "value-type-mismatch",
            f"{path}: value {violation.value!r} does not match the declared type — a `many` "
            "value object must bind a list of documents",
        )
    if violation.reason == "not-a-document":
        return WriteAssignmentError(
            "value-type-mismatch",
            f"{path}: value {violation.value!r} does not match the declared type — expected a "
            "document (mapping)",
        )
    if violation.reason == "attribute-missing":
        return WriteAssignmentError(
            "value-type-mismatch", f"{path}: required attribute is absent (or null)"
        )
    if violation.reason == "value-object-missing":
        return WriteAssignmentError(
            "value-type-mismatch", f"{path}: required value object is absent (or null)"
        )
    return WriteAssignmentError(
        "value-type-mismatch",
        f"{path}: value {violation.value!r} does not match the declared type "
        f"{violation.declared_type!r}",
    )


def _joined(base: str, path: str) -> str:
    """``base`` plus a shared-walk violation's own relative ``path`` — a nested
    member dot-joins, a ``many`` element index attaches bracket-first (no dot,
    mirroring `write_validate`'s own owner-string convention, e.g.
    ``"Customer.address.phones[0].number"``)."""
    if not path:
        return base
    if path.startswith("["):
        return f"{base}{path}"
    return f"{base}.{path}"


def _concrete_accepted_field_names(
    facet: InheritanceFacet, effective: Sequence[EntityIdentity]
) -> tuple[frozenset[str], ...]:
    """Each concrete subtype in ``effective`` mapped to its OWN accepted field set.

    A concrete position's applicable members are exactly its own ancestry chain's
    declarations, which is the set a write targeting it may name; a sibling
    branch's member is absent from every one of them.
    """
    return tuple(
        frozenset(
            {member.identity.name for member in position.applicable_attributes}
            | {member.identity.path[-1] for member in position.applicable_value_objects}
        )
        for position in (_entity_view(facet, concrete) for concrete in effective)
    )
