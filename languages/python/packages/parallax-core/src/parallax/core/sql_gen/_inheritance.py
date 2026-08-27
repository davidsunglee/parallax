"""Inheritance-family read PLANNING (m-sql "Metamodel-extension lowering").

Two `inheritance` names meet in this file, and they are not the same thing:

* ``parallax.core.inheritance`` — the METAMODEL module (`m-inheritance`), whose
  compiled :class:`~parallax.core.inheritance.InheritanceFacet` this module
  reads. It answers model questions: a family's root, its effective concrete
  subtypes, its ancestry chain, its projection supersets.
* ``parallax.core.sql_gen._inheritance`` — THIS module, the family lane of the SQL
  compiler. It answers lowering questions: what a family read projects, which tag
  predicate it carries, how a table-per-concrete-subtype union splits into
  branches, and how a row's `familyVariant` is materialized. Siblings import it
  by its dotted path and alias each name down (`plan_inheritance_read as
  _plan_inheritance_read`).

Every family answer arrives PRECOMPUTED. A plan reads an
:class:`~parallax.core.inheritance.InheritanceEntityView` (one Entity's position)
or an :class:`~parallax.core.inheritance.InheritancePositionView` (a narrow's
resolved members), never an ancestry walk of its own — the two view shapes agree
on the three members this module needs (``concrete_subtypes``,
``superset_attributes``, ``superset_value_objects``), which is what lets the
narrowed and un-narrowed lanes share one planner.

**This module returns PLANS and never lowers a predicate.** Every plan below
carries its read's own predicate as an un-lowered node, and the tag guard as its
INPUTS (:class:`TagPredicate`) rather than as anything bound. `_compile`
constructs the statement's :class:`~parallax.core.sql_gen._context.Ctx` and
assembles the family reads; `_predicate` owns every descent, including the
mid-predicate `narrow` that :func:`plan_branch_narrow` describes. Either way the
caller lowers its own operand first and only THEN calls :func:`tag_guard` and
appends what it returns. That split is what keeps the m-sql "Grouped branch
predicates" ordering (binds read branch-predicate-first, then tag) structural
rather than contingent.

Two rules make it checkable by reading this file alone. **Nothing here lowers a
predicate**: the module imports no predicate lowering, and contains no `match`
over the node union — the one Predicate node it inspects is a TOP-LEVEL `narrow`,
and only to resolve the read's position, never to descend into it. **Nothing here
binds**, and that is now checked rather than asserted: lowering state reaches
this module through exactly one signature, :func:`tag_guard`, and it arrives as a
:class:`~parallax.core.sql_gen._context.ColumnScope` — a protocol carrying
`own_column` and nothing else, so `bind`, `binds`, and `next_alias` are not
merely unused here, they are unreachable.

The read's queried **position** is the resolved effective concrete-subtype set
the whole read targets: the query's own `narrowTo` clause replaces its `target`'s
position with that clause's resolved set; a `narrow` inside the predicate (nested
inside and/or/not/group) is a local BRANCH guard and never changes the read's own
position (`m-inheritance-015`'s `or` of two narrowed branches is the corpus
witness — the projection and the whole-family "no tag" rule stay keyed to the
query's `target`, only each branch's own tag guard is injected).

Named without a leading underscore because the MODULE carries the privacy, the
package convention `_context` already established: importers alias to the
module-private spelling.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol, cast

from parallax.core.base import (
    JSON,
    DocumentReadOrdinals,
    NeutralType,
    PresentDocument,
    SqlNull,
    unwrap_document_read,
)
from parallax.core.dialect import Dialect, LockMode, projection_result_key
from parallax.core.document_codec import (
    UNAVAILABLE,
    DecodedMember,
    DocumentFinding,
    DocumentShape,
    Occurrence,
    Present,
    decode_located_member_classified,
    decode_occurrence_classified,
    entity_shape,
    locate_entity_member,
    occurrence_shape,
    reduce_declared_members_classified,
)
from parallax.core.inheritance import (
    InheritanceEntityView,
    InheritanceFacet,
    InheritancePositionView,
    family_variant_name,
)
from parallax.core.metamodel import (
    AbstractRoot,
    AbstractSubtype,
    AttributeIdentity,
    AttributeMetadata,
    EntityIdentity,
    EntityMetadata,
    Metamodel,
    Multiplicity,
    TablePerHierarchy,
    ValueObjectIdentity,
    ValueObjectMetadata,
    entity_by_name,
)
from parallax.core.predicate import Narrow, PredicateNode
from parallax.core.sql_gen._context import ColumnScope as _ColumnScope
from parallax.core.sql_gen._context import SqlGenError
from parallax.core.sql_gen._context import table_layout as _table_layout
from parallax.core.storage_layout import (
    ColumnContributor,
    ColumnSlot,
    ColumnTier,
    DirectColumn,
    DocumentPath,
    InheritanceDiscriminator,
    PositionBranch,
    PositionLayoutView,
    RelationalDocument,
    StorageLayoutFacet,
    TableLayout,
)


# --------------------------------------------------------------------------- #
# Facet reads. Each of the four below is total for an accepted model, so its   #
# absence branch names a state formation cannot produce rather than a model    #
# defect a read could carry.                                                    #
# --------------------------------------------------------------------------- #
def entity_view(facet: InheritanceFacet, entity: EntityIdentity) -> InheritanceEntityView:
    """``entity``'s family-effective view; the facet covers every accepted Entity."""
    view = facet.entity(entity)
    if view is None:  # pragma: no cover - the facet covers every accepted Entity
        raise SqlGenError(f"{entity.canonical}: the model declares no such entity")
    return view


def tag_column(layout: TableLayout, root: EntityIdentity) -> str:
    """The physical discriminator Column ``root``'s family discriminates by."""
    slot = layout.contribution(InheritanceDiscriminator(root))
    if slot is None:  # pragma: no cover - every table-per-hierarchy layout carries one
        raise SqlGenError(f"{root.canonical}: this family's Table Layout has no discriminator")
    return slot.column.name


def tag_value(facet: InheritanceFacet, concrete: EntityIdentity) -> str:
    """The value ``concrete``'s rows carry in its family's shared tag column."""
    value = entity_view(facet, concrete).tag_value
    if value is None:  # pragma: no cover - a validated TPH concrete always declares one
        raise SqlGenError(
            f"{concrete.canonical}: table-per-hierarchy concrete subtype declares no tagValue"
        )
    return value


# --------------------------------------------------------------------------- #
# Row transforms: what a read's own projection decided each observed row still #
# needs (m-case-format / m-conformance-adapter). Table-per-hierarchy derives   #
# `familyVariant` from the projected raw tag column, table-per-concrete-       #
# subtype reads it straight from the projected literal column, a Relational    #
# Document Layout read fans its one projected Structured Column out into the   #
# members it asked for, and every other read carries none. This lane is not    #
# family-specific — it lives here because the projection it mirrors does.      #
#                                                                              #
# A UNION of frozen forms rather than one class with a `kind` tag and          #
# optional fields: every field of every form is required, so there is no       #
# illegal state to assert against at materialization time, and each form's     #
# `materialize` is total — which is what lets `CompiledRead.materialize_row`   #
# be a single structural delegation with no dispatch. This is the module's own  #
# documented style (the `m-predicate` node union), and each form pickles,       #
# compares, and reprs as a plain dataclass with no `__reduce__` and no stored  #
# callable.                                                                    #
#                                                                              #
# The forms keep their module-private spelling: no sibling names them —        #
# `_compile` reaches them only through :data:`RowTransform` (the declared type #
# of `CompiledRead._transform`) and :data:`IDENTITY_TRANSFORM`. Those two are  #
# this module's published surface for the family; the forms themselves are     #
# construction details of the planners below.                                  #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class RowTransformResult:
    """One row transform's values and all provenance needed by its consumers."""

    values: dict[str, object]
    resolved_entity: EntityIdentity | None = None
    family_variant: str | None = None
    family_tag_unknown: bool = False
    findings: tuple[DocumentFinding, ...] = ()
    classified_members: frozenset[str] = frozenset()


class _RowMaterializer(Protocol):
    def materialize(self, row: Mapping[str, object]) -> RowTransformResult: ...


@dataclass(frozen=True, slots=True)
class _IdentityTransform:
    """No `familyVariant` to materialize: a non-family read, a concrete-target
    table-per-hierarchy read, or a table-per-concrete-subtype read whose
    position resolved to a single concrete. Still returns a FRESH dict, so
    every caller may mutate the result regardless of which form it got."""

    def materialize(self, row: Mapping[str, object]) -> RowTransformResult:
        return RowTransformResult(dict(row))


@dataclass(frozen=True, slots=True)
class _TagTransform:
    """Table-per-hierarchy: pop the framework-owned raw tag column (it never
    reaches the caller) and map its value to the declaring concrete's name.

    ``tag_pairs`` is the WHOLE family's `(tagValue, Identity, variant spelling)` mapping in the
    facet's canonical concrete-subtype order — never the read's own resolved
    position, since a narrowed abstract read still projects the shared table's
    tag column and may observe any of them. A tuple of pairs rather than a
    `Mapping` is what keeps `CompiledRead` hashable and its `repr` stable.

    "The whole family" is the family as this model COMPOSES it, which need not be
    the family the shared Table holds: a model may compose a family's concrete
    leaves partially (`m-inheritance`), and an abstract-root read injects no tag
    predicate, so a row tagged for an uncomposed sibling can reach this transform.
    ``root`` is carried so that row is refused by name — the family it belongs to
    and the composed tags it could have matched — rather than by a bare mapping
    miss.
    """

    column: str
    root: EntityIdentity
    tag_pairs: tuple[tuple[str, EntityIdentity, str], ...]

    def materialize(self, row: Mapping[str, object]) -> RowTransformResult:
        materialized = dict(row)
        raw = materialized.pop(self.column)
        pairs = {tag: (identity, spelling) for tag, identity, spelling in self.tag_pairs}
        resolved = pairs.get(cast("str", raw))
        if resolved is None:
            return RowTransformResult(materialized, self.root, family_tag_unknown=True)
        identity, spelling = resolved
        return RowTransformResult(materialized, identity, spelling)


@dataclass(frozen=True, slots=True)
class _LiteralTransform:
    """Table-per-concrete-subtype `union all`: rename the per-branch projected
    subtype-name literal column — there is no tag column to derive it from."""

    column: str
    variants: tuple[tuple[str, EntityIdentity], ...]
    projected_fields: tuple[tuple[str, tuple[tuple[str, str], ...]], ...]
    narrow_to_owned: bool

    def materialize(self, row: Mapping[str, object]) -> RowTransformResult:
        materialized = dict(row)
        spelling = cast("str", materialized.pop(self.column))
        fields = dict(self.projected_fields)
        projected_aliases = {
            alias
            for variant_fields in fields.values()
            for alias, rendered_key in variant_fields
            if self.narrow_to_owned or alias != rendered_key
        }
        values = {key: value for key, value in materialized.items() if key not in projected_aliases}
        for alias, rendered_key in fields[spelling]:
            if alias in materialized:
                values[rendered_key] = materialized[alias]
        return RowTransformResult(values, dict(self.variants)[spelling], spelling)


@dataclass(frozen=True, slots=True)
class _DocumentTransform:
    """Relational Document Layout: fan the one projected Structured Column out
    into the members the read asked for, and drop the raw document.

    The Structured Column is never a result field (`m-sql`), so `column` is
    popped rather than renamed. Each member is decoded by its DECLARED Neutral
    Type through the codec, not by the JSON value's own shape, and lands under
    the very result key it would have carried as a direct Column — which is what
    makes one read's logical output the same under either layout. A member that
    is absent or explicitly null in the document reads as `None`, the same one
    logical answer a NULL Column gives.

    ``members`` may be empty: an observation-bearing read of an owner with no
    document-resident member projects the column for the stored document itself,
    and naming it here is what keeps that document off the row's values.
    """

    column: str
    shape: DocumentShape
    members: tuple[tuple[str, tuple[str, ...]], ...]

    def materialize(self, row: Mapping[str, object]) -> RowTransformResult:
        materialized = dict(row)
        document_read = materialized.pop(self.column)
        members = _materialize_document_members(self.shape, document_read, self.members)
        materialized.update(members.values)
        return RowTransformResult(
            materialized,
            findings=members.findings,
            classified_members=members.classified_members,
        )


@dataclass(frozen=True, slots=True)
class _TphVariantDocument:
    identity: EntityIdentity
    spelling: str
    discriminator_value: str
    shape: DocumentShape
    members: tuple[tuple[str, tuple[str, ...]], ...]


@dataclass(frozen=True, slots=True)
class _TpcsVariantDocument:
    identity: EntityIdentity
    spelling: str
    document_column: str
    shape: DocumentShape
    members: tuple[tuple[str, tuple[str, ...]], ...]


@dataclass(frozen=True, slots=True)
class _MaterializedDocumentMembers:
    values: dict[str, object]
    findings: tuple[DocumentFinding, ...]
    classified_members: frozenset[str]


def _materialize_document_members(
    shape: DocumentShape,
    document_read: object,
    members: tuple[tuple[str, tuple[str, ...]], ...],
) -> _MaterializedDocumentMembers:
    values: dict[str, object] = {}
    findings: list[DocumentFinding] = []
    for key, path in members:
        decoded = _classified_entity_member(shape, document_read, path)
        findings.extend(decoded.findings)
        if isinstance(decoded.presence, Present):
            values[key] = decoded.presence.value
        elif decoded.presence is UNAVAILABLE:
            values[key] = UNAVAILABLE
        else:
            values[key] = None
    return _MaterializedDocumentMembers(
        values,
        tuple(findings),
        frozenset(values),
    )


@dataclass(frozen=True, slots=True)
class _TphDocumentTransform:
    """Resolve a TPH row's tag before decoding its heterogeneous document."""

    column: str
    tag_column: str
    root: EntityIdentity
    variants: tuple[_TphVariantDocument, ...]
    padding: tuple[str, ...]

    def materialize(self, row: Mapping[str, object]) -> RowTransformResult:
        materialized = dict(row)
        raw_tag = materialized.pop(self.tag_column)
        document_read = materialized.pop(self.column)
        variant = next(
            (candidate for candidate in self.variants if candidate.discriminator_value == raw_tag),
            None,
        )
        if variant is None:
            materialized.pop(self.column, None)
            return RowTransformResult(materialized, self.root, family_tag_unknown=True)
        for key in self.padding:
            materialized[key] = None
        members = _materialize_document_members(variant.shape, document_read, variant.members)
        materialized.update(members.values)
        return RowTransformResult(
            materialized,
            variant.identity,
            variant.spelling,
            findings=members.findings,
            classified_members=members.classified_members,
        )


@dataclass(frozen=True, slots=True)
class _TpcsDocumentTransform:
    """Decode a TPCS union row with the concrete branch's document shape."""

    base: _LiteralTransform
    documents: tuple[_TpcsVariantDocument, ...]
    padding: tuple[str, ...]

    def materialize(self, row: Mapping[str, object]) -> RowTransformResult:
        base = self.base.materialize(row)
        materialized = base.values
        identity = cast("EntityIdentity", base.resolved_entity)
        spelling = cast("str", base.family_variant)
        variant = next(
            (document for document in self.documents if document.identity == identity), None
        )
        for key in self.padding:
            materialized[key] = None
        if variant is None:
            materialized.pop(self.documents[0].document_column, None)
            return RowTransformResult(
                materialized,
                identity,
                spelling,
                base.family_tag_unknown,
                base.findings,
                base.classified_members | frozenset(self.padding),
            )
        document_read = materialized.pop(variant.document_column)
        members = _materialize_document_members(variant.shape, document_read, variant.members)
        materialized.update(members.values)
        return RowTransformResult(
            materialized,
            identity,
            spelling,
            base.family_tag_unknown,
            (*base.findings, *members.findings),
            base.classified_members | members.classified_members,
        )


@dataclass(frozen=True, slots=True)
class _DirectDocumentVariant:
    identity: EntityIdentity
    occurrences: tuple[ValueObjectMetadata, ...]


@dataclass(frozen=True, slots=True)
class _DirectDocumentTransform:
    """Classify direct Value Object Columns after inheritance resolution.

    A provider folds every selected document pair before this transform runs,
    regardless of whether the carrier is the Table's shared Structured Column
    or a Value Object's own Column. This wrapper consumes the latter carriers,
    decodes their declared occurrence shapes, and preserves the base transform's
    concrete identity, family variant, and classified provenance.
    """

    base: _RowMaterializer
    variants: tuple[_DirectDocumentVariant, ...]

    def materialize(self, row: Mapping[str, object]) -> RowTransformResult:
        base = self.base.materialize(row)
        identity = base.resolved_entity
        variant = next(
            (
                candidate
                for candidate in self.variants
                if identity is None or candidate.identity == identity
            ),
            None,
        )
        if variant is None:
            return base
        values = base.values
        findings = list(base.findings)
        classified = set(base.classified_members)
        for occurrence in variant.occurrences:
            key = occurrence.storage.name
            if key not in values:
                continue
            document_read = values[key]
            if not isinstance(document_read, (SqlNull, PresentDocument)):
                raise SqlGenError(
                    f"the database port returned {type(document_read).__name__}, not a DocumentRead"
                )
            decoded = _classified_occurrence(
                occurrence_shape(occurrence),
                document_read,
                multiplicity=occurrence.multiplicity,
                nullable=occurrence.nullable,
            )
            name = occurrence.identity.path[-1]
            findings.extend(
                DocumentFinding(finding.code, (name, *finding.path)) for finding in decoded.findings
            )
            values[key] = decoded.presence.value if isinstance(decoded.presence, Present) else None
            classified.add(key)
        return RowTransformResult(
            values,
            base.resolved_entity,
            base.family_variant,
            base.family_tag_unknown,
            tuple(findings),
            frozenset(classified),
        )


def _classified_entity_member(
    shape: DocumentShape, document_read: object, path: tuple[str, ...]
) -> DecodedMember:
    """Classify one direct logical Entity member from its tagged carrier."""
    if len(path) != 1:  # pragma: no cover - read projection requests direct members only
        raise SqlGenError(
            f"an Entity document projection must address one direct member, got {path}"
        )
    member = path[0]
    declared = shape.member(member)
    if isinstance(declared, Occurrence):
        carrier = (
            document_read
            if isinstance(document_read, SqlNull)
            else locate_entity_member(document_read.document, member)
            if isinstance(document_read, PresentDocument)
            else None
        )
        if carrier is None:
            raise SqlGenError(
                f"the database port returned {type(document_read).__name__}, not a DocumentRead"
            )
        if not isinstance(carrier, PresentDocument):
            carrier = SqlNull()
        decoded = _classified_occurrence(
            declared.shape,
            carrier,
            multiplicity=declared.multiplicity,
            nullable=declared.nullable,
        )
        return DecodedMember(
            decoded.presence,
            tuple(
                DocumentFinding(finding.code, (member, *finding.path))
                for finding in decoded.findings
            ),
        )
    if isinstance(document_read, SqlNull):
        return decode_located_member_classified(shape, document_read, member)
    if not isinstance(document_read, PresentDocument):
        raise SqlGenError(
            f"the database port returned {type(document_read).__name__}, not a DocumentRead"
        )
    located = locate_entity_member(document_read.document, member)
    return decode_located_member_classified(shape, located, member)


def _classified_occurrence(
    shape: DocumentShape,
    document_read: SqlNull | PresentDocument,
    *,
    multiplicity: Multiplicity,
    nullable: bool,
) -> DecodedMember:
    """Classify and neutral-decode one complete occurrence exactly once."""
    outer = decode_occurrence_classified(
        shape,
        document_read,
        multiplicity=multiplicity,
        nullable=nullable,
    )
    if not isinstance(outer.presence, Present):
        return outer
    findings = list(outer.findings)
    if multiplicity is Multiplicity.MANY:
        reduced: list[object] = []
        for index, item in enumerate(cast("list[object]", outer.presence.value)):
            value, nested = reduce_declared_members_classified(shape, item)
            reduced.append(value)
            findings.extend(
                DocumentFinding(finding.code, (index, *finding.path)) for finding in nested
            )
        return DecodedMember(Present(reduced), tuple(findings))
    value, nested = reduce_declared_members_classified(shape, outer.presence.value)
    findings.extend(nested)
    return DecodedMember(Present(value), tuple(findings))


def observed_document(document_read: object) -> object | None:
    """Unwrap a provider-neutral document carrier for predecessor retention."""
    if not isinstance(document_read, (SqlNull, PresentDocument)):
        raise SqlGenError(
            f"the database port returned {type(document_read).__name__}, not a DocumentRead"
        )
    return unwrap_document_read(document_read)


RowTransform = (
    _IdentityTransform
    | _TagTransform
    | _LiteralTransform
    | _DocumentTransform
    | _TphDocumentTransform
    | _TpcsDocumentTransform
    | _DirectDocumentTransform
)

# The identity form is stateless, so one shared instance serves every read that
# carries no `familyVariant`; equality is structural, so a copied/unpickled
# `CompiledRead` still compares equal to one holding this very object.
IDENTITY_TRANSFORM = _IdentityTransform()


def direct_document_transform(
    base: RowTransform,
    candidates: Sequence[tuple[EntityIdentity, TableLayout, Sequence[ValueObjectMetadata]]],
) -> RowTransform:
    """Wrap ``base`` for every projected occurrence stored in its own Column."""
    variants = tuple(
        _DirectDocumentVariant(
            identity,
            tuple(
                occurrence
                for occurrence in occurrences
                if isinstance(layout.placement(occurrence.identity), DirectColumn)
            ),
        )
        for identity, layout, occurrences in candidates
    )
    if not any(variant.occurrences for variant in variants):
        return base
    return _DirectDocumentTransform(base, variants)


def transform_structured_column(transform: _RowMaterializer) -> str | None:
    """The Structured Column ``transform`` fans out, or absence when it fans out none.

    The document fan-out drops the raw column, so a caller that needs the stored
    document — a temporal observation, which retains it (`m-unit-work`) — reads it
    off the driver row by this name BEFORE the transform runs. Absence is the
    honest answer for every read that projected no Structured Column, `Columns`
    layout included.
    """
    if isinstance(transform, _DirectDocumentTransform):
        return transform_structured_column(transform.base)
    return (
        transform.column
        if isinstance(transform, (_DocumentTransform, _TphDocumentTransform))
        else transform.documents[0].document_column
        if isinstance(transform, _TpcsDocumentTransform) and transform.documents
        else None
    )


# --------------------------------------------------------------------------- #
# Position resolution.                                                         #
# --------------------------------------------------------------------------- #
def _referenced_entities(
    model: Metamodel, names: Sequence[str]
) -> tuple[EntityIdentity, ...] | None:
    """The Identities ``names`` denote as query references
    (:func:`~parallax.core.metamodel.entity_by_name`), or ``None`` when any of
    them denotes no single Entity."""
    resolved: list[EntityIdentity] = []
    for name in names:
        entity = entity_by_name(model, name)
        if entity is None:
            return None
        resolved.append(entity.identity)
    return tuple(resolved)


def narrow_position(
    model: Metamodel, facet: InheritanceFacet, to: Sequence[str]
) -> InheritancePositionView:
    """The projection a `narrow`'s authored ``to`` list denotes.

    Each authored name is a query reference and resolves model-wide by
    `entity_by_name`'s rule, never into the queried Entity's own namespace, and
    the facet resolves the members' union to the position's canonical effective
    concrete-subtype set and its projection supersets.

    `validate_predicate` runs upstream and guarantees the resolved set is
    non-empty and a subset of the active position (`m-predicate` "the four-step
    validation rule") before this compiler ever sees the node, so this need
    only resolve — never re-validate.
    """
    members = _referenced_entities(model, to)
    position = None if members is None else facet.position(members)
    if position is None:
        raise SqlGenError(
            f"narrow to {list(to)} names an entity the model does not declare, "
            "or spans more than one inheritance family"
        )
    return position


def query_narrow_position(
    facet: InheritanceFacet, to: tuple[EntityIdentity, ...]
) -> InheritancePositionView:
    """The canonical position denoted by an Entity Query's resolved narrowing."""
    position = facet.position(to)
    if position is None:
        raise SqlGenError(
            f"narrow to {[identity.canonical for identity in to]} spans more than one "
            "inheritance family"
        )
    return position


# --------------------------------------------------------------------------- #
# The DEFERRED tag guard.                                                      #
# --------------------------------------------------------------------------- #
def family_tag_pairs(
    facet: InheritanceFacet, root: EntityIdentity
) -> tuple[tuple[str, EntityIdentity, str], ...]:
    """The WHOLE family's `(tagValue, Identity, variant spelling)` triples, in the facet's
    canonical concrete-subtype order.

    Deliberately the family's set, not the read's resolved position: a narrowed
    abstract read still projects the shared table's raw tag column, and the
    mapping that interprets it is a property of the family, not of the narrow
    (`m-inheritance-012`).
    """
    return tuple(
        (tag_value(facet, concrete), concrete, family_variant_name(facet, concrete))
        for concrete in entity_view(facet, root).concrete_subtypes
    )


TagKind = Literal["eq", "in"]


@dataclass(frozen=True, slots=True)
class TagPredicate:
    """The inputs ONE tag guard needs, as one value (m-sql *Tag-predicate
    selection*).

    These travelled as three separate parameters and as three fields on each of
    two plans, and they are meaningless apart — a tag column with nothing to
    compare it against, or a position with no column to compare it in, is not a
    guard. A read or hop carrying NO tag predicate at all (an untouched abstract
    ROOT target) spells that as ``None`` rather than as a sentinel string, so
    "is there a guard here?" is a question the type answers.

    :attr:`kind` is DERIVED rather than stored: m-sql keys the guard's shape
    purely to the resolved position's size, so this cannot describe a
    one-concrete position guarded by `in`, or several guarded by `=`, even by
    accident. The rule is therefore written once, here.
    """

    column: str
    position: tuple[EntityIdentity, ...]

    @property
    def kind(self) -> TagKind:
        """`=` for a single concrete, `in` for several (m-sql *Tag-predicate
        selection*)."""
        return "eq" if len(self.position) == 1 else "in"


def tag_guard(
    scope: _ColumnScope, facet: InheritanceFacet, tag: TagPredicate
) -> tuple[str, tuple[object, ...]]:
    """PLAN the tag-predicate guard for ``tag`` (m-sql *Tag-predicate
    selection*): `t0.<tag> = ?` for one concrete, `t0.<tag> in (?, …)` for several
    — the `in` list in the position's already-canonical order, so its tag values
    follow suit.

    This returns the fragment AND its bind values and pushes nothing; every caller
    binds them itself, after it has lowered its own interior predicate. That split
    is not stylistic. A bind-as-you-render helper can only be sequenced correctly
    if the caller never evaluates it early — and the natural spelling at the
    correlated-hop call site was to pass it as an ARGUMENT to the function that
    lowers the interior, which Python evaluates BEFORE the call. The guard's bind
    then landed ahead of the interior's own while the emitted text still put the
    guard last, so SQL and binds disagreed (`bark_volume = ? and kind = ?` against
    `('dog', 5)`). m-sql "Grouped branch predicates" fixes the contract exactly:
    the guard is appended after the branch predicate and "binds read
    branch-predicate-first then tag". Returning data makes the ordering the
    caller's explicit, visible statement rather than an evaluation-order accident.

    ``scope`` is a :class:`~parallax.core.sql_gen._context.ColumnScope`, not the
    whole context: the ONE capability rendering a guard needs is "how does this
    statement spell its own column", and taking no more than that is what makes
    the paragraph above a type rule rather than a promise. A caller still just
    passes its own resolution scope, which satisfies the protocol structurally.

    The tag column is THIS scope's own column, so it renders through
    :meth:`ColumnScope.own_column` like every other one: the framework-owned tag
    is no more alias-qualified than a declared attribute is. On every read
    scope ``unaliased`` is ``False`` and this is exactly ``qualified(alias,
    tag.column)``, so no emitted read SQL depends on the distinction — it exists
    so the leak cannot reopen from a caller that arrives with an unaliased
    scope, rather than resting on every such caller being rejected upstream
    first.
    """
    col = scope.own_column(tag.column)
    tag_values = [tag_value(facet, concrete) for concrete in tag.position]
    if tag.kind == "eq":
        return f"{col} = ?", (tag_values[0],)
    holes = ", ".join("?" for _ in tag_values)
    return f"{col} in ({holes})", tuple(tag_values)


# --------------------------------------------------------------------------- #
# The plans.                                                                   #
#                                                                              #
# Each is a frozen description of ONE family read: what it selects from, what  #
# it projects (rendered on demand against the statement's own alias, the one   #
# thing only `_compile` knows), the un-lowered `inner` predicate, the tag       #
# guard's inputs, and the row transform. Nothing here holds a `Ctx`, a bind     #
# list, or an alias.                                                           #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class ProjectedColumn:
    """One selected physical Column and the seam the dialect renders it through.

    ``type`` is the contributing Attribute's neutral type, or ``None`` for a slot
    with no scalar rendering seam — a top-level Value Object document column or
    the framework-owned discriminator — which projects as a plain
    alias-qualified reference.
    """

    column: str
    type: NeutralType | None
    document: bool = False


def position_slots(
    layout: TableLayout, position: Sequence[EntityIdentity]
) -> tuple[ColumnSlot, ...]:
    """``layout``'s slots applicable to ``position``, in canonical Table order."""
    selected = frozenset(position)
    return tuple(slot for slot in layout.columns if slot.applicable_entities & selected)


def position_documents(
    facet: InheritanceFacet,
    storage: StorageLayoutFacet,
    position: Sequence[EntityIdentity],
) -> tuple[ValueObjectMetadata, ...]:
    """The top-level Value Object occurrences ``position``'s rows can carry.

    The compiled read carries this so materialization decodes documents from the
    occurrences the position actually has, in the Position Layout's own order,
    rather than re-projecting the family superset from a round-tripped name. It
    is keyed to the position and not to the read's result form: a default
    row-form read projects no document column, while the explicit
    materializing-write widening lane may project selected or complete documents.

    Answered from the Position Layout's logical MEMBER sequence and each
    branch's placements rather than from its physical columns, because an
    occurrence is a member under either layout while it is a Column only under
    `Columns` — under `Document` it is a subtree of the shared Structured Column
    and contributes no column entry at all, which would leave this answering
    nothing and materialization decoding nothing.
    """
    view = facet.position(tuple(position))
    layout_view = storage.position(tuple(position))
    if view is None or layout_view is None:  # pragma: no cover - a resolved position is total
        return ()
    by_identity = {member.identity: member for member in view.superset_value_objects}
    placed = {
        member
        for branch in layout_view.branches
        for member, placement in zip(layout_view.members, branch.placements, strict=True)
        if placement is not None
    }
    return tuple(
        by_identity[member]
        for member in layout_view.members
        if member in by_identity and member in placed
    )


def _structured_column_slot(layout: TableLayout) -> ColumnSlot | None:
    """``layout``'s shared Structured Column slot, or absence under `Columns`.

    A governed Table carries exactly one whatever its members' placements are,
    an owner whose every member holds a direct-column role included: its
    Structured Column is still physically present and still holds a document.
    """
    return next(
        (slot for slot in layout.columns if isinstance(slot.contributor, RelationalDocument)), None
    )


def document_projection(
    layout: TableLayout,
    attributes: Sequence[AttributeMetadata],
    value_objects: Sequence[ValueObjectMetadata],
    *,
    observation: bool = False,
) -> tuple[ProjectedColumn | None, RowTransform]:
    """The Structured Column a read projects, and the transform that fans it back
    out (`m-sql` *Read projection*, rule 5).

    ``attributes`` and ``value_objects`` are the members this read must produce.
    Each one's Member Placement decides whether it already has a Column of its
    own; the ones placed at a Document Path are what make the Structured Column
    needed, and it is then projected **once**, raw, whatever their number.

    ``observation`` is the read's own lane: an instance-form read, or the
    materializing predicate-write resolve that widens its projection to every
    declared member. Such a read observes the stored document itself and not only
    the members decoded out of it — a Predecessor Row retains the raw document
    (`m-unit-work`) — so it projects the Table's Structured Column wherever there
    is one, fanning out however many members it asked for, zero included. Outside
    that lane a read whose members are all direct — every read under `Columns`
    layout, and a `Document`-layout row-form read of direct members alone —
    projects no document column and transforms by identity, so this is inert
    rather than conditional at the call site.
    """
    document_slot: ColumnSlot | None = None
    document_attributes: list[AttributeMetadata] = []
    document_occurrences: list[ValueObjectMetadata] = []
    members: list[tuple[str, tuple[str, ...]]] = []
    for attribute in attributes:
        placement = layout.placement(attribute.identity)
        if isinstance(placement, DocumentPath):
            document_slot = placement.slot
            document_attributes.append(attribute)
            members.append((attribute.storage.name, placement.path))
    for value_object in value_objects:
        placement = layout.placement(value_object.identity)
        if isinstance(placement, DocumentPath):
            document_slot = placement.slot
            document_occurrences.append(value_object)
            members.append((value_object.storage.name, placement.path))
    if document_slot is None and observation:
        document_slot = _structured_column_slot(layout)
    if document_slot is None:
        return None, IDENTITY_TRANSFORM
    return (
        ProjectedColumn(document_slot.column.name, None, document=True),
        _DocumentTransform(
            document_slot.column.name,
            entity_shape(document_attributes, document_occurrences),
            tuple(members),
        ),
    )


def _tph_document_projection(
    layout: TableLayout,
    facet: InheritanceFacet,
    root: EntityIdentity,
    concretes: Sequence[EntityIdentity],
    *,
    instance_form: bool,
    abstract_target: bool,
    tag_col: str,
) -> tuple[ProjectedColumn | None, RowTransform | None]:
    slot = _structured_column_slot(layout)
    if slot is None:
        return None, None

    variants: list[_TphVariantDocument] = []
    projects_document = False
    for concrete in concretes:
        view = entity_view(facet, concrete)
        projected, transform = document_projection(
            layout,
            view.applicable_attributes,
            view.applicable_value_objects if instance_form else (),
            observation=instance_form,
        )
        if isinstance(transform, _DocumentTransform):
            projects_document = True
            shape = transform.shape
            members = transform.members
        else:
            shape = entity_shape((), ())
            members = ()
        variants.append(
            _TphVariantDocument(
                identity=concrete,
                spelling=family_variant_name(facet, concrete),
                discriminator_value=tag_value(facet, concrete),
                shape=shape,
                members=members,
            )
        )
    if not projects_document:
        return None, None
    projected = ProjectedColumn(slot.column.name, None, document=True)
    if abstract_target:
        return projected, _TphDocumentTransform(
            slot.column.name,
            tag_col,
            root,
            tuple(variants),
            (
                ()
                if instance_form
                else tuple(
                    dict.fromkeys(key for variant in variants for key, _path in variant.members)
                )
            ),
        )
    only = variants[0]
    return projected, _DocumentTransform(projected.column, only.shape, only.members)


def select_projection(
    slots: Sequence[ColumnSlot],
    attributes: Sequence[AttributeMetadata],
    value_objects: Sequence[ValueObjectMetadata],
    *,
    project_discriminator: bool,
) -> tuple[ProjectedColumn, ...]:
    """The m-sql projection order for a single-Table read, taken from ``slots``.

    ``slots`` is already the canonical `Identity`, `Discriminator`, `Domain`,
    `Temporal`, `Audit`, `Document` tier sequence restricted to the read's
    position, so this selects rather than orders: a contributor absent from
    ``attributes`` / ``value_objects`` is not projected, which is how a row-form
    read omits every `Document` slot. The discriminator is projected iff the
    read's own queried `target` is abstract, independently of what the position
    resolved to, and keeps its own tier position rather than trailing the
    scalars.
    """
    types: dict[object, tuple[NeutralType | None, bool]] = {
        attribute.identity: (attribute.type, False) for attribute in attributes
    }
    types.update({member.identity: (None, True) for member in value_objects})
    selected: list[ProjectedColumn] = []
    for slot in slots:
        if isinstance(slot.contributor, InheritanceDiscriminator):
            if project_discriminator:
                selected.append(ProjectedColumn(slot.column.name, None))
            continue
        if slot.contributor not in types:
            continue
        neutral_type, document = types[slot.contributor]
        selected.append(ProjectedColumn(slot.column.name, neutral_type, document=document))
    return tuple(selected)


def render_projection(
    dialect: Dialect,
    alias: str,
    columns: Sequence[ProjectedColumn],
    *,
    document_pairs: bool = True,
) -> tuple[str, tuple[object, ...], tuple[DocumentReadOrdinals, ...]]:
    """Render one select list and its ordered projection binds against ``alias``.

    A `bytes` column projects `encode(col, ?)`, which is where a projection BIND
    comes from and why projection binds lead the statement's bind tuple.
    """
    exprs: list[str] = []
    binds: list[object] = []
    document_reads: list[DocumentReadOrdinals] = []
    ordinal = 0
    for projected in columns:
        if projected.document and document_pairs:
            expression = dialect.qualified(alias, projected.column)
            presence, document = dialect.project_document_read(expression)
            exprs.extend((presence, document))
            document_reads.append((ordinal, ordinal + 1))
            ordinal += 2
            continue
        if projected.type is None:
            exprs.append(dialect.qualified(alias, projected.column))
        else:
            expr, extra = dialect.project(alias, projected.column, projected.type)
            exprs.append(expr)
            binds.extend(extra)
        ordinal += 1
    return ", ".join(exprs), tuple(binds), tuple(document_reads)


@dataclass(frozen=True, slots=True)
class TphPlan:
    """Table-per-hierarchy: one shared single-table SELECT (m-sql "Inheritance —
    table-per-hierarchy lowering").

    The tag PREDICATE (:attr:`tag`) is keyed purely to the resolved position's
    SIZE — one concrete lowers to `=` whether reached by a directly concrete
    `target` or by result narrowing, several lower to `in`, and only an untouched
    abstract-**root** `target` (no `narrowTo` at all) carries no tag predicate at
    all, which is ``None``. Whether the discriminator slot appears in
    :attr:`columns` is instead keyed to whether the queried `target` itself is
    abstract — independent of the narrow's resolved cardinality
    (`m-inheritance-012`: `Animal` narrowed to the single concrete `Dog` still
    projects `t0.kind` and still carries `familyVariant`, because the caller
    queried the polymorphic `Animal` position). These are deliberately two
    different conditions: a bare abstract root projects the tag it does not
    guard on, and a concrete target guards on the tag it does not project.
    """

    table: str
    position: tuple[EntityIdentity, ...]
    columns: tuple[ProjectedColumn, ...]
    inner: PredicateNode
    tag: TagPredicate | None
    transform: RowTransform

    def projection(
        self, dialect: Dialect, alias: str, *, document_pairs: bool = True
    ) -> tuple[str, tuple[object, ...], tuple[DocumentReadOrdinals, ...]]:
        """The select list and its ordered projection binds, against ``alias``."""
        return render_projection(dialect, alias, self.columns, document_pairs=document_pairs)


@dataclass(frozen=True, slots=True)
class TpcsSinglePlan:
    """A table-per-concrete-subtype read resolving to exactly one concrete: an
    ordinary single-table read of that subtype's own table, no tag, no union, no
    `familyVariant` — attribute resolution still widens across the family (the
    RESOLUTION SCOPE's entity stays the read's own queried `target`, e.g. an
    abstract position narrowed down to this one concrete, so its attribute search
    spans the family's superset rather than only that entity's own declared
    attributes), matching the table-per-hierarchy concrete-target form.
    """

    table: str
    position: tuple[EntityIdentity, ...]
    columns: tuple[ProjectedColumn, ...]
    inner: PredicateNode
    transform: RowTransform

    def projection(
        self, dialect: Dialect, alias: str, *, document_pairs: bool = True
    ) -> tuple[str, tuple[object, ...], tuple[DocumentReadOrdinals, ...]]:
        """The select list and its ordered projection binds, against ``alias``.

        The discriminator is always absent: this reads the resolved concrete's
        OWN table, whose layout carries no discriminator slot.
        """
        return render_projection(dialect, alias, self.columns, document_pairs=document_pairs)


@dataclass(frozen=True, slots=True)
class BranchColumn:
    """One Position Layout contributor as one `union all` branch renders it.

    ``owned`` is that branch's slot presence taken from the Position Layout's own
    slot-or-absence mapping; an unowned contributor renders the typed `NULL`
    placeholder under the same allocated ``result_alias`` its owning branches use.
    """

    column: str
    type: NeutralType | None
    max_length: int | None
    owned: bool
    result_alias: str
    document: bool = False


@dataclass(frozen=True, slots=True)
class TpcsBranchPlan:
    """One `union all` branch: its own table, and the Position Layout's one
    logical contributor sequence paired with this branch's slot presence."""

    identity: EntityIdentity
    variant: str
    table: str
    columns: tuple[BranchColumn, ...]

    def projection(
        self, dialect: Dialect, alias: str, *, document_pairs: bool = True
    ) -> tuple[str, tuple[object, ...], tuple[DocumentReadOrdinals, ...]]:
        """The branch's select list, its binds, and its document-read ordinals.

        ``document_pairs`` is ``False`` when the union is wrapped by an ordered or
        limited outer select: a presence cell has no result alias to be addressed
        by from outside the derived table, so the document slot stays a single
        aliased cell here and :meth:`TpcsUnionPlan.projection` expands the pair
        against the union alias instead.
        """
        exprs: list[str] = []
        binds: list[object] = []
        document_reads: list[DocumentReadOrdinals] = []
        ordinal = 0
        for branch_column in self.columns:
            if branch_column.owned:
                if branch_column.document:
                    expression = dialect.qualified(alias, branch_column.column)
                    if not document_pairs:
                        exprs.append(
                            expression
                            if branch_column.result_alias == branch_column.column
                            else f"{expression} {branch_column.result_alias}"
                        )
                        ordinal += 1
                        continue
                    presence, document = dialect.project_document_read(expression)
                    if branch_column.result_alias != branch_column.column:
                        document = f"{document} {branch_column.result_alias}"
                    exprs.extend((presence, document))
                    document_reads.append((ordinal, ordinal + 1))
                    ordinal += 2
                    continue
                if branch_column.type is None:  # pragma: no cover - formation makes it universal
                    expr, extra = dialect.qualified(alias, branch_column.column), ()
                else:
                    expr, extra = dialect.project(
                        alias,
                        branch_column.column,
                        branch_column.type,
                        result_key=branch_column.result_alias,
                    )
                exprs.append(expr)
                binds.extend(extra)
            else:
                if branch_column.document:
                    document_type = dialect.null_cast(JSON, None)
                    placeholder = f"cast(null as {document_type}) {branch_column.result_alias}"
                    if not document_pairs:
                        exprs.append(placeholder)
                        ordinal += 1
                        continue
                    exprs.extend(("false", placeholder))
                    document_reads.append((ordinal, ordinal + 1))
                    ordinal += 2
                    continue
                if branch_column.type is None:
                    raise SqlGenError(  # pragma: no cover
                        "a TPCS document column must be owned by every concrete branch"
                    )
                cast_type = dialect.null_cast(branch_column.type, branch_column.max_length)
                exprs.append(f"cast(null as {cast_type}) {branch_column.result_alias}")
            ordinal += 1
        # The settled TPH/TPCS asymmetry: TPCS projects the variant NAME literal
        # per branch directly — there is no discriminator slot to derive it from.
        exprs.append(f"'{self.variant}' family_variant")
        return ", ".join(exprs), tuple(binds), tuple(document_reads)


@dataclass(frozen=True, slots=True)
class TpcsUnionColumn:
    """One union RESULT column: the contributor it carries and the result alias
    every branch projects it under.

    A branch column is what one branch selects; this is what the union yields, so
    it is what an outer select over the union alias — and therefore an ordering
    key measured against it — can name.
    """

    contributor: AttributeIdentity | ValueObjectIdentity | RelationalDocument
    result_alias: str
    document: bool


@dataclass(frozen=True, slots=True)
class TpcsUnionPlan:
    """A position resolving to two or more concretes: canonical `union all`, one
    branch per concrete in canonical order, every branch restarting its own
    alias at `t0` and projecting the same stable superset with `cast(null as
    <type>)` placeholders for columns it does not own, plus its own
    `familyVariant` subtype-name literal.

    ``inner`` is the SAME predicate for every branch — each branch lowers it
    against its own fresh context, which is what restarts the aliases and keeps
    the per-branch binds separable for concatenation in branch order.

    ``columns`` is the union's own result sequence, aligned with every branch's
    :attr:`TpcsBranchPlan.columns`. A `union all` has no clause tail of its own,
    so an ordered or limited read wraps it as a derived table and applies the
    tail against :meth:`projection` — the only place a Position Layout
    contributor is reachable by the one name all branches agree on.
    """

    branches: tuple[TpcsBranchPlan, ...]
    position: tuple[EntityIdentity, ...]
    columns: tuple[TpcsUnionColumn, ...]
    inner: PredicateNode
    transform: RowTransform

    def projection(
        self, dialect: Dialect, alias: str
    ) -> tuple[str, tuple[object, ...], tuple[DocumentReadOrdinals, ...]]:
        """The select list of an outer read over the union's ``alias``.

        Every branch already applied its own per-type rendering, so this selects
        each result alias through rather than projecting it a second time — the
        one exception being a `Document` slot, whose presence cell is expanded
        here because the branch left it unexpanded for exactly that reason.
        """
        exprs: list[str] = []
        document_reads: list[DocumentReadOrdinals] = []
        ordinal = 0
        for column in self.columns:
            reference = dialect.qualified(alias, column.result_alias)
            if column.document:
                presence, document = dialect.project_document_read(reference)
                exprs.extend((presence, document))
                document_reads.append((ordinal, ordinal + 1))
                ordinal += 2
                continue
            exprs.append(reference)
            ordinal += 1
        exprs.append(dialect.qualified(alias, "family_variant"))
        return ", ".join(exprs), (), tuple(document_reads)

    def column_of(self, contributor: ColumnContributor) -> TpcsUnionColumn:
        """``contributor``'s union result column.

        A member the layout placed inside a Structured Column makes no Column
        claim of its own, so it is reached through the contributor of the slot
        that carries it rather than through its own identity — which is what
        makes this total for every member the position can order by, the
        positional rule (`m-object-query`) having already excluded the rest.
        """
        for column in self.columns:
            if column.contributor == contributor:
                return column
        raise SqlGenError(  # pragma: no cover - a validated Sort Key names a projected member
            f"{contributor} has no Column in the table-per-concrete-subtype union"
        )


@dataclass(frozen=True, slots=True)
class BranchNarrowPlan:
    """A `narrow` reached MID-predicate (nested inside and/or/not/group) — a
    **grouped branch predicate** (m-sql "Grouped branch predicates"). Carries the
    branch's own un-lowered ``operand`` and the inputs its tag guard needs; the
    caller lowers the operand FIRST, then guards.
    """

    operand: PredicateNode
    position: tuple[EntityIdentity, ...]
    tag: TagPredicate | None


# --------------------------------------------------------------------------- #
# Planning.                                                                    #
# --------------------------------------------------------------------------- #
def plan_inheritance_read(
    entity: EntityMetadata,
    predicate: PredicateNode,
    narrow_to: tuple[EntityIdentity, ...] | None,
    model: Metamodel,
    facet: InheritanceFacet,
    storage: StorageLayoutFacet,
    instance_form: bool,
    lock: LockMode | None,
) -> TphPlan | TpcsSinglePlan | TpcsUnionPlan:
    """Plan an inheritance-family read for its family's declared strategy.

    Only an inheritance participant reaches here, and m-inheritance admits
    exactly two strategies, so the table-per-hierarchy test decides between them
    outright.

    ``instance_form`` is the object lane (`result_form == "instance"`), the only
    thing about the read's consumption lane the family projection depends on.
    ``lock`` is here rather than at the assembly site because the union lane must
    REFUSE a genuinely requested shared row lock before any branch is assembled;
    ordering and the cap are the assembler's, since a union applies them to its
    own outer select rather than to any branch.
    """
    view = entity_view(facet, entity.identity)
    position, inner, narrowed = _read_position(view, predicate, narrow_to, facet)
    if isinstance(view.strategy, TablePerHierarchy):
        return _plan_tph_read(
            entity, view, position, inner, facet, storage, instance_form, narrowed
        )
    return _plan_tpcs_read(position, inner, facet, storage, instance_form, lock)


def _read_position(
    view: InheritanceEntityView,
    predicate: PredicateNode,
    narrow_to: tuple[EntityIdentity, ...] | None,
    facet: InheritanceFacet,
) -> tuple[InheritancePositionView, PredicateNode, bool]:
    """The read's queried position, the predicate left to lower under it, and
    whether a top-level `narrow` produced it.

    Entity Query narrowing replaces the target's own position with its resolved
    identity set. The predicate is already separate and is lowered whole.
    """
    if narrow_to is not None:
        return query_narrow_position(facet, narrow_to), predicate, True
    return view, predicate, False


def _plan_tph_read(
    entity: EntityMetadata,
    view: InheritanceEntityView,
    position: InheritancePositionView,
    inner: PredicateNode,
    facet: InheritanceFacet,
    storage: StorageLayoutFacet,
    instance_form: bool,
    narrowed: bool,
) -> TphPlan:
    layout = _table_layout(storage, facet, view.entity)
    tag_col = tag_column(layout, view.root)
    abstract_target = isinstance(entity.inheritance, (AbstractRoot, AbstractSubtype))
    # Only an UNTOUCHED abstract root queries the whole family, so only it carries
    # no tag predicate at all.
    guarded = narrowed or not isinstance(entity.inheritance, AbstractRoot)

    # `familyVariant` rides the SAME condition as the discriminator projection:
    # the transform reads the column this read projects, or there is no column to
    # read and nothing to materialize.
    transform: RowTransform = (
        _TagTransform(tag_col, view.root, family_tag_pairs(facet, view.root))
        if abstract_target
        else IDENTITY_TRANSFORM
    )
    columns = select_projection(
        position_slots(layout, position.concrete_subtypes),
        position.superset_attributes,
        position.superset_value_objects if instance_form else (),
        project_discriminator=abstract_target,
    )
    document, document_transform = _tph_document_projection(
        layout,
        facet,
        view.root,
        position.concrete_subtypes,
        instance_form=instance_form,
        abstract_target=abstract_target,
        tag_col=tag_col,
    )
    if document is not None:
        columns = (*columns, document)
    if document_transform is not None:
        transform = document_transform
    transform = direct_document_transform(
        transform,
        tuple(
            (
                concrete,
                layout,
                entity_view(facet, concrete).applicable_value_objects if instance_form else (),
            )
            for concrete in position.concrete_subtypes
        ),
    )
    return TphPlan(
        table=layout.table.name,
        position=tuple(position.concrete_subtypes),
        columns=columns,
        inner=inner,
        tag=TagPredicate(tag_col, tuple(position.concrete_subtypes)) if guarded else None,
        transform=transform,
    )


def _projects_document_slot(
    contributor: ColumnContributor, *, instance_form: bool, document_resident: bool
) -> bool:
    """Whether a `union all` branch projects ``contributor``'s `Document` slot.

    A top-level Value Object occurrence owns a Structured Column of its own under
    `Columns` layout, and `m-sql` *Read projection* rule 3 gives it to an
    instance-form read alone — a row-form read omits it. A Relational Document
    Layout's shared Structured Column additionally answers rule 5's other need:
    a row-form read still projects it to produce a member the layout placed at a
    Document Path, which ``document_resident`` is.
    """
    if isinstance(contributor, ValueObjectIdentity):
        return instance_form
    return isinstance(contributor, RelationalDocument) and (instance_form or document_resident)


def _plan_tpcs_read(
    position: InheritancePositionView,
    inner: PredicateNode,
    facet: InheritanceFacet,
    storage: StorageLayoutFacet,
    instance_form: bool,
    lock: LockMode | None,
) -> TpcsSinglePlan | TpcsUnionPlan:
    """Table-per-concrete-subtype (m-sql "Inheritance — table-per-concrete-subtype
    lowering"). Unlike table-per-hierarchy, the single-vs-several split is the ONLY
    thing that decides `familyVariant` here — there is no table-per-concrete-subtype
    analogue of the abstract-`target` slot-2 rule, because a resolved single
    concrete has no shared table to discriminate and no sibling branch to
    distinguish it from (m-sql, explicit).

    Every branch table is that branch's OWN concrete's container, resolved one
    concrete at a time. The position's own container is a different fact — the
    single container a read or write of the position itself targets (absent for
    an abstract table-per-concrete-subtype position) — and is deliberately never
    reached for here, because a concrete position may itself have concrete
    descendants, in which case its own table is one branch of several.
    """
    concretes = tuple(position.concrete_subtypes)

    if len(concretes) == 1:
        layout = _table_layout(storage, facet, concretes[0])
        columns = select_projection(
            position_slots(layout, concretes),
            position.superset_attributes,
            position.superset_value_objects if instance_form else (),
            project_discriminator=False,
        )
        document, transform = document_projection(
            layout,
            position.superset_attributes,
            position.superset_value_objects if instance_form else (),
            observation=instance_form,
        )
        if document is not None:
            columns = (*columns, document)
        transform = direct_document_transform(
            transform,
            (
                (
                    concretes[0],
                    layout,
                    position.superset_value_objects if instance_form else (),
                ),
            ),
        )
        return TpcsSinglePlan(
            table=layout.table.name,
            position=concretes,
            columns=columns,
            inner=inner,
            # A single resolved concrete projects neither a tag column nor a
            # variant literal — the settled asymmetry with table-per-hierarchy,
            # whose abstract target keeps its tag however narrow the position
            # resolves.
            transform=transform,
        )

    if lock == "locking":
        # A shared row lock is the one clause a derived-table wrap cannot rescue:
        # PostgreSQL forbids a locking clause over a `UNION` result and over every
        # input of one, and dropping it silently would leave a later ungated write
        # unlicensed. Ordering and limiting have an outer select to land on, so
        # only a GENUINELY requested lock refuses — matching the append site's own
        # `== "locking"` test, which is why a participating read carrying the
        # `optimistic` Effective Concurrency Strategy passes here.
        raise SqlGenError(
            "a read-lock suffix over a table-per-concrete-subtype union-all read "
            "(2+ effective concretes) has no goldened lowering yet"
        )
    layout_position = position_layout(storage, concretes)
    document_resident = any(
        isinstance(
            _table_layout(storage, facet, concrete).placement(attribute.identity), DocumentPath
        )
        for concrete in concretes
        for attribute in entity_view(facet, concrete).applicable_attributes
    )
    scalars = tuple(
        index
        for index, column in enumerate(layout_position.columns)
        if column.tier is not ColumnTier.DOCUMENT
        or _projects_document_slot(
            column.contributor, instance_form=instance_form, document_resident=document_resident
        )
    )
    by_identity: dict[AttributeIdentity | ValueObjectIdentity, AttributeMetadata] = {
        attribute.identity: attribute for attribute in position.superset_attributes
    }
    attributes = tuple(
        by_identity.get(contributor)
        if isinstance(contributor, (AttributeIdentity, ValueObjectIdentity))
        else None
        for index in scalars
        for contributor in (layout_position.columns[index].contributor,)
    )
    spellings = tuple(_contributor_column(layout_position.branches, index) for index in scalars)
    result_aliases = _result_aliases(spellings)
    union_columns = tuple(
        TpcsUnionColumn(
            contributor=layout_position.columns[index].contributor,
            result_alias=result_alias,
            document=layout_position.columns[index].tier is ColumnTier.DOCUMENT,
        )
        for index, result_alias in zip(scalars, result_aliases, strict=True)
    )
    branches = tuple(
        TpcsBranchPlan(
            identity=branch.concrete_entities[0],
            variant=family_variant_name(facet, branch.concrete_entities[0]),
            table=branch.layout.table.name,
            columns=tuple(
                BranchColumn(
                    column=spelling,
                    type=None if attribute is None else attribute.type,
                    max_length=None if attribute is None else attribute.max_length,
                    owned=branch.slots[index] is not None,
                    result_alias=result_alias,
                    document=layout_position.columns[index].tier is ColumnTier.DOCUMENT,
                )
                for index, attribute, spelling, result_alias in zip(
                    scalars, attributes, spellings, result_aliases, strict=True
                )
            ),
        )
        for branch in layout_position.branches
    )
    # Every branch projects its own `family_variant` literal, so the transform is
    # a plain rename — no tag map, no metamodel lookup.
    literal_transform = _LiteralTransform(
        "family_variant",
        tuple((branch.variant, branch.identity) for branch in branches),
        tuple(
            (
                branch.variant,
                tuple(
                    (
                        branch_column.result_alias,
                        branch_column.column
                        if branch_column.type is None
                        else projection_result_key(branch_column.column, branch_column.type),
                    )
                    for branch_column in branch.columns
                    if branch_column.owned
                ),
            )
            for branch in branches
        ),
        instance_form,
    )
    documents: list[_TpcsVariantDocument] = []
    for concrete in concretes:
        layout = _table_layout(storage, facet, concrete)
        view = entity_view(facet, concrete)
        projected, document_transform = document_projection(
            layout,
            view.applicable_attributes,
            view.applicable_value_objects if instance_form else (),
            observation=instance_form,
        )
        if projected is not None and isinstance(document_transform, _DocumentTransform):
            documents.append(
                _TpcsVariantDocument(
                    concrete,
                    family_variant_name(facet, concrete),
                    projected.column,
                    document_transform.shape,
                    document_transform.members,
                )
            )
    transform: RowTransform = (
        _TpcsDocumentTransform(
            literal_transform,
            tuple(documents),
            (
                ()
                if instance_form
                else tuple(
                    dict.fromkeys(key for document in documents for key, _path in document.members)
                )
            ),
        )
        if documents
        else literal_transform
    )
    transform = direct_document_transform(
        transform,
        tuple(
            (
                concrete,
                _table_layout(storage, facet, concrete),
                entity_view(facet, concrete).applicable_value_objects if instance_form else (),
            )
            for concrete in concretes
        ),
    )
    return TpcsUnionPlan(
        branches=branches,
        position=concretes,
        columns=union_columns,
        inner=inner,
        transform=transform,
    )


def position_layout(
    storage: StorageLayoutFacet, concretes: Sequence[EntityIdentity]
) -> PositionLayoutView:
    """``concretes``' one logical contributor sequence and per-Table branch map."""
    view = storage.position(tuple(concretes))
    if view is None:  # pragma: no cover - a validated position is one canonical family
        raise SqlGenError(
            f"position {sorted(identity.canonical for identity in concretes)} "
            "has no Position Layout"
        )
    return view


def _contributor_column(branches: Sequence[PositionBranch], index: int) -> str:
    """One logical contributor's physical Column spelling across ``branches``.

    An inherited contributor occupies one Column occurrence per concrete Table
    and every occurrence carries the declaration's own spelling, so the first
    branch that owns the slot fixes the result-alias candidate for all of them.
    """
    for branch in branches:
        slot = branch.slots[index]
        if slot is not None:
            return slot.column.name
    raise SqlGenError(  # pragma: no cover - a Position Layout contributor is owned somewhere
        "a table-per-concrete-subtype position contributor occupies no branch Column"
    )


def _result_aliases(spellings: Sequence[str]) -> tuple[str, ...]:
    """Hygienic result aliases for one union's logical contributor sequence.

    A contributor keeps its own physical spelling only when that spelling occurs
    once across the position and is not the synthetic `family_variant` carrier;
    every other contributor takes the first `parallax_attr_N` outside the
    complete reservation set, so an authored `parallax_attr_0` stays reserved.
    """
    counts: dict[str, int] = {}
    for spelling in spellings:
        counts[spelling] = counts.get(spelling, 0) + 1
    allocated = set(spellings) | {"family_variant"}
    next_internal = 0
    aliases: list[str] = []
    for spelling in spellings:
        if counts[spelling] == 1 and spelling != "family_variant":
            aliases.append(spelling)
            continue
        while f"parallax_attr_{next_internal}" in allocated:
            next_internal += 1
        internal = f"parallax_attr_{next_internal}"
        allocated.add(internal)
        aliases.append(internal)
        next_internal += 1
    return tuple(aliases)


def plan_branch_narrow(
    model: Metamodel,
    facet: InheritanceFacet,
    storage: StorageLayoutFacet,
    entity: EntityMetadata,
    narrow: Narrow,
) -> BranchNarrowPlan:
    """Plan a mid-predicate `narrow` (m-sql "Grouped branch predicates").

    The branch's own operand composes with its own tag guard via `and` at the
    caller, which lowers the operand first so its binds precede the guard's.
    """
    view = entity_view(facet, entity.identity)
    position = narrow_position(model, facet, narrow.to)
    if not isinstance(view.strategy, TablePerHierarchy):
        return BranchNarrowPlan(
            operand=narrow.operand,
            position=tuple(position.concrete_subtypes),
            tag=None,
        )
    layout = _table_layout(storage, facet, entity.identity)
    return BranchNarrowPlan(
        operand=narrow.operand,
        position=tuple(position.concrete_subtypes),
        tag=TagPredicate(tag_column(layout, view.root), tuple(position.concrete_subtypes)),
    )
