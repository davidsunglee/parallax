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
constructs the statement's :class:`~parallax.core.sql_gen._context.StatementBuilder` and
assembles the family reads; `_predicate` owns every descent, including the
mid-predicate `narrow` that :func:`plan_validated_branch_narrow` describes. Either way the
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
from dataclasses import dataclass, field, replace
from typing import Literal, cast

from parallax.core.base import (
    JSON,
    SQL_NULL,
    DocumentReadOrdinals,
    NeutralType,
    PresentDocument,
    SqlNull,
    UnknownFamilyTag,
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
)
from parallax.core.predicate import PredicateNode
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
# Row materialization stages: what a read's own projection decided each observed #
# row still needs (m-case-format / m-conformance-adapter). Table-per-hierarchy  #
# derives `familyVariant` from the projected raw tag column, table-per-concrete- #
# subtype reads it straight from the projected literal column, a Relational     #
# Document Layout read fans its one projected Structured Column out into the    #
# members it asked for, and a Value Object stored in its own Column is          #
# classified where it lies. This lane is not family-specific — it lives here    #
# because the projection it mirrors does.                                       #
#                                                                              #
# ONE staged record rather than a union of forms with a `kind` tag: a read      #
# fills the stages its projection decided and leaves the rest `None`, so every  #
# point of the stage product is a legal materializer and materialization        #
# asserts nothing. An absent stage does not run, and a present stage's          #
# per-entity index answers a `dict.get` whose miss means "this stage does not   #
# apply to this row". Every fact a row would otherwise re-derive — the tag map, #
# a branch's renames, each occurrence's document shape, the member keys the     #
# codec already judged — is compiled once here, so a row allocates its own      #
# values dict and the few pairs a branch rename moves, and no map, set, scan,   #
# or shape of its own — save the row that reaches materialization without a     #
# projected occurrence Column, which narrows the compiled classified-key set to #
# the keys it held. Stored fields stay tuples of pairs and every index is       #
# derived in `__post_init__`, so a compiled read still pickles, deep-copies,    #
# compares, and reprs exactly.                                                  #
#                                                                              #
# The stages keep their module's spelling and `_compile` aliases each down, the #
# package convention `_context` established. `_compile` sequences them because  #
# the carrier they fill is its own (`MaterializedReadRow`) and this module      #
# sits below it: what a stage cannot write into the row's values it returns,    #
# and nothing here names the carrier.                                          #
# --------------------------------------------------------------------------- #
type ResolvedVariant = tuple[EntityIdentity, str | None, UnknownFamilyTag | None]
"""What resolving one row answers: the concrete Entity it names, the
`familyVariant` spelling it publishes, and the stored discriminator no composed
concrete subtype claimed."""


@dataclass(frozen=True, slots=True)
class ByTag:
    """Table-per-hierarchy: pop the framework-owned raw tag column (it never
    reaches the caller) and map its value to the declaring concrete's name.

    ``tag_pairs`` is a `(tagValue, Identity, variant spelling)` mapping in the
    facet's canonical concrete-subtype order. For a homogeneous read it is the
    WHOLE family's — never the read's own resolved position, since a narrowed
    abstract read still projects the shared table's tag column and may observe
    any of them — and for a heterogeneous shared document it is the position's,
    which is the pairing the document shapes are keyed by. A tuple of pairs
    rather than a `Mapping` is what keeps `CompiledRead` hashable and its `repr`
    stable; ``by_tag`` holds the whole answer a hit gives, so a resolved row
    allocates nothing here.

    "The whole family" is the family as this model COMPOSES it, which need not be
    the family the shared Table holds: a model may compose a family's concrete
    leaves partially (`m-inheritance`), and an abstract-root read injects no tag
    predicate, so a row tagged for an uncomposed sibling can reach this stage.
    ``root`` is carried so that row is refused by name — the family it belongs to
    and the composed tags it could have matched — rather than by a bare mapping
    miss.
    """

    column: str
    root: EntityIdentity
    tag_pairs: tuple[tuple[str, EntityIdentity, str], ...]
    by_tag: Mapping[str, ResolvedVariant] = field(init=False, compare=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "by_tag",
            {tag: (identity, spelling, None) for tag, identity, spelling in self.tag_pairs},
        )

    @property
    def resolvable(self) -> tuple[EntityIdentity, ...]:
        return (self.root, *(identity for _, identity, _ in self.tag_pairs))

    def resolve(self, values: dict[str, object]) -> ResolvedVariant:
        raw = values.pop(self.column)
        resolved = self.by_tag.get(cast("str", raw))
        if resolved is None:
            return self.root, None, UnknownFamilyTag(raw)
        return resolved


@dataclass(frozen=True, slots=True)
class ByLiteral:
    """Table-per-concrete-subtype `union all`: rename the per-branch projected
    subtype-name literal column — there is no tag column to derive it from.

    The branch that produced a row owns some of the union's result aliases and
    reads the rest as its siblings' typed `NULL` padding. ``drop`` is every alias
    the read's own lane discards, compiled from ``projected_fields`` once: a
    narrow-to-owned read keeps only what the resolved branch owns, while a
    row-form read keeps a sibling's null padding under an unrenamed alias, as the
    corpus expects. The moved values are lifted before the drop, so an alias may
    be both a source and discarded.
    """

    column: str
    variants: tuple[tuple[str, EntityIdentity], ...]
    projected_fields: tuple[tuple[str, tuple[tuple[str, str], ...]], ...]
    narrow_to_owned: bool
    by_spelling: Mapping[str, ResolvedVariant] = field(init=False, compare=False, repr=False)
    renames: Mapping[str, tuple[tuple[str, str], ...]] = field(
        init=False, compare=False, repr=False
    )
    drop: frozenset[str] = field(init=False, compare=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "by_spelling",
            {spelling: (identity, spelling, None) for spelling, identity in self.variants},
        )
        object.__setattr__(self, "renames", dict(self.projected_fields))
        object.__setattr__(
            self,
            "drop",
            frozenset(
                alias
                for _, variant_fields in self.projected_fields
                for alias, rendered_key in variant_fields
                if self.narrow_to_owned or alias != rendered_key
            ),
        )

    @property
    def resolvable(self) -> tuple[EntityIdentity, ...]:
        return tuple(identity for _, identity in self.variants)

    def resolve(self, values: dict[str, object]) -> ResolvedVariant:
        spelling = cast("str", values.pop(self.column))
        moved = tuple(
            (rendered_key, values[alias])
            for alias, rendered_key in self.renames[spelling]
            if alias in values
        )
        for alias in self.drop:
            values.pop(alias, None)
        for rendered_key, value in moved:
            values[rendered_key] = value
        return self.by_spelling[spelling]


@dataclass(frozen=True, slots=True)
class DocumentFanOut:
    """One resolved concrete's share of a read's shared Structured Column.

    ``shape`` is absent for a `union all` branch that stores no document of its
    own: such a row carries no document to decode and still pads the members its
    siblings' documents carry, which is the state that padding stands for.
    ``members`` may be empty for a present shape too — an observation-bearing
    read of an owner with no document-resident member projects the column for the
    stored document itself, and naming it keeps that document off the row's
    values.
    """

    shape: DocumentShape | None
    members: tuple[tuple[str, tuple[str, ...]], ...]
    padding: tuple[str, ...] = ()

    @property
    def classified(self) -> frozenset[str]:
        """The keys this fan-out judged, which conversion must not judge again."""
        if self.shape is None:
            return frozenset(self.padding)
        return frozenset(key for key, _path in self.members)


@dataclass(frozen=True, slots=True)
class SharedDocument:
    """Relational Document Layout: fan the one projected Structured Column out
    into the members the read asked for, and drop the raw document.

    The Structured Column is never a result field (`m-sql`), so ``column`` is
    popped rather than renamed. Each member is decoded by its DECLARED Neutral
    Type through the codec, not by the JSON value's own shape, and lands under
    the very result key it would have carried as a direct Column — which is what
    makes one read's logical output the same under either layout. A member that
    is absent or explicitly null in the document reads as `None`, the same one
    logical answer a NULL Column gives.

    ``column`` is ONE row key for the whole read, including a `union all` whose
    branches each hold their own Structured Column: Storage Layout is root-owned,
    so every branch of a family spells that column the way the root declared it,
    and the union projects the document tier under one result alias
    (`_contributor_column`) whatever the branch that rendered the row.
    """

    column: str
    per_entity: tuple[tuple[EntityIdentity, DocumentFanOut], ...]
    by_entity: Mapping[EntityIdentity, DocumentFanOut] = field(
        init=False, compare=False, repr=False
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "by_entity", dict(self.per_entity))

    def fan_out(
        self, values: dict[str, object], resolved: EntityIdentity
    ) -> tuple[DocumentFinding, ...]:
        """Fan ``resolved``'s members out of ``values``' raw document, in place."""
        entry = self.by_entity.get(resolved)
        if entry is None or entry.shape is None:
            values.pop(self.column, None)
            if entry is not None:
                for key in entry.padding:
                    values[key] = None
            return ()
        document_read = values.pop(self.column)
        for key in entry.padding:
            values[key] = None
        findings: tuple[DocumentFinding, ...] = ()
        for key, path in entry.members:
            decoded = _classified_entity_member(entry.shape, document_read, path)
            if decoded.findings:
                findings += decoded.findings
            if isinstance(decoded.presence, Present):
                values[key] = decoded.presence.value
            elif decoded.presence is UNAVAILABLE:
                values[key] = UNAVAILABLE
            else:
                values[key] = None
        return findings


@dataclass(frozen=True, slots=True)
class DirectDocuments:
    """Classify each projected Value Object occurrence stored in its own Column.

    A provider folds every selected document pair before materialization,
    regardless of whether the carrier is the Table's shared Structured Column or
    a Value Object's own Column. This stage consumes the latter carriers and
    decodes each against the shape its occurrence declares, resolved once at
    compile time rather than per row. It keys on the concrete the row RESOLVED
    to, so a read whose position holds several concretes classifies the
    occurrences of the one its row names.
    """

    per_entity: tuple[
        tuple[EntityIdentity, tuple[tuple[ValueObjectMetadata, DocumentShape], ...]], ...
    ]
    by_entity: Mapping[EntityIdentity, tuple[tuple[ValueObjectMetadata, DocumentShape], ...]] = (
        field(init=False, compare=False, repr=False)
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "by_entity", dict(self.per_entity))

    def classify(
        self, values: dict[str, object], resolved: EntityIdentity
    ) -> tuple[tuple[DocumentFinding, ...], bool]:
        """Classify ``resolved``'s direct occurrences in place.

        Answers its findings and whether every one of them was there to classify:
        a column absent from the row is left alone, which is the only way the
        compiled classified-key set overstates what this row carries.
        """
        findings: tuple[DocumentFinding, ...] = ()
        complete = True
        for occurrence, shape in self.by_entity.get(resolved, ()):
            key = occurrence.storage.name
            if key not in values:
                complete = False
                continue
            document_read = values[key]
            if not isinstance(document_read, (SqlNull, PresentDocument)):
                raise SqlGenError(
                    f"the database port returned {type(document_read).__name__}, not a DocumentRead"
                )
            decoded = _classified_occurrence(
                shape,
                document_read,
                multiplicity=occurrence.multiplicity,
                nullable=occurrence.nullable,
            )
            if decoded.findings:
                name = occurrence.identity.path[-1]
                findings += tuple(
                    replace(finding, path=(name, *finding.path)) for finding in decoded.findings
                )
            values[key] = decoded.presence.value if isinstance(decoded.presence, Present) else None
        return findings, complete


@dataclass(frozen=True, slots=True)
class RowStages:
    """The stages one read's projection filled, and the facts they share.

    ``classified_by_entity`` is the union of what both document stages judge for
    one resolved concrete, compiled here because the two stages are the only
    judges and their keys are fixed by the projection. A read that fills no stage
    at all is a plain record: a non-family read, a concrete-target
    table-per-hierarchy read, or a table-per-concrete-subtype read whose position
    resolved to a single concrete has no `familyVariant` to materialize and no
    document to fan out.
    """

    resolve: ByTag | ByLiteral | None = None
    shared_document: SharedDocument | None = None
    direct_documents: DirectDocuments | None = None
    classified_by_entity: Mapping[EntityIdentity, frozenset[str]] = field(
        init=False, compare=False, repr=False
    )

    def __post_init__(self) -> None:
        classified: dict[EntityIdentity, frozenset[str]] = {}
        if self.shared_document is not None:
            for identity, entry in self.shared_document.per_entity:
                keys = entry.classified
                if keys:
                    classified[identity] = keys
        if self.direct_documents is not None:
            for identity, occurrences in self.direct_documents.per_entity:
                keys = frozenset(occurrence.storage.name for occurrence, _shape in occurrences)
                if keys:
                    classified[identity] = classified.get(identity, frozenset()) | keys
        object.__setattr__(self, "classified_by_entity", classified)

    @property
    def structured_column(self) -> str | None:
        """The Structured Column these stages fan out, or absence for none.

        The fan-out drops the raw column, so a caller that needs the stored
        document — a temporal observation, which retains it (`m-unit-work`) —
        reads it off the driver row by this name. Absence is the honest answer
        for every read that projected no Structured Column, `Columns` layout
        included.
        """
        return None if self.shared_document is None else self.shared_document.column

    @property
    def resolvable(self) -> tuple[EntityIdentity, ...]:
        """Every Entity these stages can name, beyond the read's own position.

        A homogeneous tag map is the WHOLE family's rather than the read's
        narrow, so a narrowed abstract read still resolves a sibling's row to
        that sibling, and a tag no composed concrete claims resolves the row to
        the family root — which is never a concrete in the position. A consumer
        preparing one structure per Entity a row can carry therefore cannot read
        the position alone.
        """
        return () if self.resolve is None else self.resolve.resolvable


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
            carrier = SQL_NULL
        decoded = _classified_occurrence(
            declared.shape,
            carrier,
            multiplicity=declared.multiplicity,
            nullable=declared.nullable,
        )
        return DecodedMember(
            decoded.presence,
            tuple(replace(finding, path=(member, *finding.path)) for finding in decoded.findings),
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
            findings.extend(replace(finding, path=(index, *finding.path)) for finding in nested)
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


def direct_documents(
    candidates: Sequence[tuple[EntityIdentity, TableLayout, Sequence[ValueObjectMetadata]]],
) -> DirectDocuments | None:
    """The direct-Column occurrence stage, or absence when a read projects none."""
    per_entity = tuple(
        (
            identity,
            tuple(
                (occurrence, occurrence_shape(occurrence))
                for occurrence in occurrences
                if isinstance(layout.placement(occurrence.identity), DirectColumn)
            ),
        )
        for identity, layout, occurrences in candidates
    )
    if not any(occurrences for _identity, occurrences in per_entity):
        return None
    return DirectDocuments(per_entity)


# --------------------------------------------------------------------------- #
# Position resolution.                                                         #
# --------------------------------------------------------------------------- #
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
def tag_pairs(
    facet: InheritanceFacet, concretes: Sequence[EntityIdentity]
) -> tuple[tuple[str, EntityIdentity, str], ...]:
    """``concretes``' `(tagValue, Identity, variant spelling)` triples, in order."""
    return tuple(
        (tag_value(facet, concrete), concrete, family_variant_name(facet, concrete))
        for concrete in concretes
    )


def family_tag_pairs(
    facet: InheritanceFacet, root: EntityIdentity
) -> tuple[tuple[str, EntityIdentity, str], ...]:
    """The WHOLE family's triples, in the facet's canonical concrete-subtype order.

    Deliberately the family's set, not the read's resolved position: a narrowed
    abstract read still projects the shared table's raw tag column, and the
    mapping that interprets it is a property of the family, not of the narrow
    (`m-inheritance-012`). A read whose document shapes are keyed per concrete
    resolves the position's own pairs instead, so one row's tag and one row's
    document shape name the same concrete.
    """
    return tag_pairs(facet, entity_view(facet, root).concrete_subtypes)


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
# guard's inputs, and the row materialization stages. Nothing here holds a     #
# `StatementBuilder`, a bind list, or an alias.                                 #
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
) -> tuple[ProjectedColumn | None, DocumentFanOut | None]:
    """The Structured Column a read projects, and the fan-out that reads it back
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
    projects no document column and fans nothing out, so this is inert rather
    than conditional at the call site.
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
        return None, None
    return (
        ProjectedColumn(document_slot.column.name, None, document=True),
        DocumentFanOut(entity_shape(document_attributes, document_occurrences), tuple(members)),
    )


def _tph_document_projection(
    layout: TableLayout,
    facet: InheritanceFacet,
    concretes: Sequence[EntityIdentity],
    *,
    instance_form: bool,
    abstract_target: bool,
) -> tuple[ProjectedColumn | None, SharedDocument | None]:
    """The Structured Column a family read projects, and the per-concrete fan-out
    that reads it back out.

    Each concrete resolves its own shape and members against the shared Table, so
    a heterogeneous document is decoded by the shape of the concrete the ROW
    named rather than by any one branch's. A concrete with no document-resident
    member still takes an entry: its rows carry the shared column and fan nothing
    out of it. Padding is the abstract-target row-form lane's alone — a read that
    publishes flat rows renders every branch's document members, so a row carries
    its siblings' keys as null.
    """
    slot = _structured_column_slot(layout)
    if slot is None:
        return None, None

    fan_outs: list[tuple[EntityIdentity, DocumentFanOut | None]] = []
    for concrete in concretes:
        view = entity_view(facet, concrete)
        _projected, fan_out = document_projection(
            layout,
            view.applicable_attributes,
            view.applicable_value_objects if instance_form else (),
            observation=instance_form,
        )
        fan_outs.append((concrete, fan_out))
    if all(fan_out is None for _identity, fan_out in fan_outs):
        return None, None
    padding = (
        ()
        if instance_form or not abstract_target
        else tuple(
            dict.fromkeys(
                key
                for _identity, fan_out in fan_outs
                if fan_out is not None
                for key, _path in fan_out.members
            )
        )
    )
    nothing = DocumentFanOut(entity_shape((), ()), (), padding)
    return ProjectedColumn(slot.column.name, None, document=True), SharedDocument(
        slot.column.name,
        tuple(
            (identity, nothing if fan_out is None else replace(fan_out, padding=padding))
            for identity, fan_out in fan_outs
        ),
    )


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
    wrapped: bool = False,
) -> tuple[str, tuple[object, ...], tuple[DocumentReadOrdinals, ...]]:
    """Render one select list and its ordered projection binds against ``alias``.

    A `bytes` column projects `encode(col, ?)`, which is where a projection BIND
    comes from and why projection binds lead the statement's bind tuple.

    ``wrapped`` says ``alias`` is a derived table over a union whose branches
    already applied that rendering, so each column is selected THROUGH under the
    result key the branch projected it as — a second `encode` there would name a
    column the union does not yield.
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
        elif wrapped:
            exprs.append(
                dialect.qualified(alias, projection_result_key(projected.column, projected.type))
            )
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
    stages: RowStages

    def projection(
        self,
        dialect: Dialect,
        alias: str,
        *,
        document_pairs: bool = True,
        wrapped: bool = False,
    ) -> tuple[str, tuple[object, ...], tuple[DocumentReadOrdinals, ...]]:
        """The select list and its ordered projection binds, against ``alias``.

        ``wrapped`` is the variant-partitioned form, where ``alias`` is a derived
        table over the per-variant union rather than the family's own Table.
        """
        return render_projection(
            dialect, alias, self.columns, document_pairs=document_pairs, wrapped=wrapped
        )


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
    stages: RowStages

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
    stages: RowStages

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
    resolved effective position and the inputs its tag guard needs; the caller
    lowers the validated child FIRST, then guards.
    """

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

    columns = select_projection(
        position_slots(layout, position.concrete_subtypes),
        position.superset_attributes,
        position.superset_value_objects if instance_form else (),
        project_discriminator=abstract_target,
    )
    document, shared = _tph_document_projection(
        layout,
        facet,
        position.concrete_subtypes,
        instance_form=instance_form,
        abstract_target=abstract_target,
    )
    if document is not None:
        columns = (*columns, document)
    # `familyVariant` rides the SAME condition as the discriminator projection:
    # the tag stage reads the column this read projects, or there is no column to
    # read and nothing to materialize. A heterogeneous shared document is keyed by
    # the concretes whose shapes it holds, so the two agree on one pairing.
    return TphPlan(
        table=layout.table.name,
        position=tuple(position.concrete_subtypes),
        columns=columns,
        inner=inner,
        tag=TagPredicate(tag_col, tuple(position.concrete_subtypes)) if guarded else None,
        stages=RowStages(
            ByTag(
                tag_col,
                view.root,
                tag_pairs(facet, position.concrete_subtypes)
                if shared is not None
                else family_tag_pairs(facet, view.root),
            )
            if abstract_target
            else None,
            shared,
            direct_documents(
                tuple(
                    (
                        concrete,
                        layout,
                        entity_view(facet, concrete).applicable_value_objects
                        if instance_form
                        else (),
                    )
                    for concrete in position.concrete_subtypes
                )
            ),
        ),
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
        document, fan_out = document_projection(
            layout,
            position.superset_attributes,
            position.superset_value_objects if instance_form else (),
            observation=instance_form,
        )
        if document is not None:
            columns = (*columns, document)
        return TpcsSinglePlan(
            table=layout.table.name,
            position=concretes,
            columns=columns,
            inner=inner,
            # A single resolved concrete projects neither a tag column nor a
            # variant literal — the settled asymmetry with table-per-hierarchy,
            # whose abstract target keeps its tag however narrow the position
            # resolves — so it fills no resolution stage.
            stages=RowStages(
                None,
                None
                if document is None or fan_out is None
                else SharedDocument(document.column, ((concretes[0], fan_out),)),
                direct_documents(
                    (
                        (
                            concretes[0],
                            layout,
                            position.superset_value_objects if instance_form else (),
                        ),
                    )
                ),
            ),
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
    # Every branch projects its own `family_variant` literal, so resolution is
    # a plain rename — no tag map, no metamodel lookup.
    literal = ByLiteral(
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
    fan_outs: list[tuple[EntityIdentity, DocumentFanOut | None]] = []
    document_column: str | None = None
    for concrete in concretes:
        layout = _table_layout(storage, facet, concrete)
        view = entity_view(facet, concrete)
        projected, fan_out = document_projection(
            layout,
            view.applicable_attributes,
            view.applicable_value_objects if instance_form else (),
            observation=instance_form,
        )
        if projected is not None and fan_out is not None and document_column is None:
            document_column = projected.column
        fan_outs.append((concrete, fan_out))
    padding = (
        ()
        if instance_form
        else tuple(
            dict.fromkeys(
                key
                for _identity, fan_out in fan_outs
                if fan_out is not None
                for key, _path in fan_out.members
            )
        )
    )
    # A branch storing no document of its own still pads its siblings' document
    # members, and reads the shared column the union aliased for all of them.
    nothing = DocumentFanOut(None, (), padding)
    stages = RowStages(
        literal,
        None
        if document_column is None
        else SharedDocument(
            document_column,
            tuple(
                (identity, nothing if fan_out is None else replace(fan_out, padding=padding))
                for identity, fan_out in fan_outs
            ),
        ),
        direct_documents(
            tuple(
                (
                    concrete,
                    _table_layout(storage, facet, concrete),
                    entity_view(facet, concrete).applicable_value_objects if instance_form else (),
                )
                for concrete in concretes
            )
        ),
    )
    return TpcsUnionPlan(
        branches=branches,
        position=concretes,
        columns=union_columns,
        inner=inner,
        stages=stages,
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


def plan_validated_branch_narrow(
    facet: InheritanceFacet,
    storage: StorageLayoutFacet,
    entity: EntityMetadata,
    position: tuple[EntityIdentity, ...],
) -> BranchNarrowPlan:
    """Plan a mid-predicate narrow from its validated effective position."""
    view = entity_view(facet, entity.identity)
    if not isinstance(view.strategy, TablePerHierarchy):
        return BranchNarrowPlan(position, None)
    layout = _table_layout(storage, facet, entity.identity)
    return BranchNarrowPlan(position, TagPredicate(tag_column(layout, view.root), position))
