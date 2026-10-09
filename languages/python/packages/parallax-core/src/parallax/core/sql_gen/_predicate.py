from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, assert_never

from parallax.core.base import STRING, Bytes, ManagedValue, NeutralType
from parallax.core.dialect import Dialect, projection_result_key
from parallax.core.document_codec import comparison_text, is_text_compared
from parallax.core.inheritance import InheritanceFacet
from parallax.core.metamodel import (
    AttributeMetadata,
    EntityIdentity,
    EntityMetadata,
    Metamodel,
    Multiplicity,
    OccurrenceMetadata,
    ValueObjectAttributeMetadata,
    ValueObjectMetadata,
    entity_by_name,
)
from parallax.core.predicate import MembershipOp, StringOp
from parallax.core.predicate._resolved import (
    DeferredKeySet,
    ResolvedAnd,
    ResolvedComparison,
    ResolvedConstant,
    ResolvedGroup,
    ResolvedMembership,
    ResolvedNarrow,
    ResolvedNot,
    ResolvedNullCheck,
    ResolvedOr,
    ResolvedPredicate,
    ResolvedPredicateMember,
    ResolvedQuantifier,
    ResolvedRange,
    ResolvedSemiJoin,
    ResolvedStringMatch,
)
from parallax.core.sql_gen._context import SqlGenError, StatementBuilder
from parallax.core.sql_gen._context import table_layout as _table_layout

# The family LANE of the compiler — distinct from `parallax.core.inheritance`
# above, which is the metamodel module. Aliased down to the module-private
# spelling, so a use site below never confuses the two.
from parallax.core.sql_gen._inheritance import entity_view as _entity_view
from parallax.core.sql_gen._inheritance import (
    plan_resolved_branch_narrow as _plan_resolved_branch_narrow,
)
from parallax.core.sql_gen._inheritance import tag_guard as _tph_tag_guard

# The navigation LANE: hop plans in, one correlated `EXISTS` (or a grouped `or`
# of them) out. Same aliasing-down convention as the family lane above.
from parallax.core.sql_gen._navigation import open_branch as _open_branch
from parallax.core.sql_gen._navigation import plan_resolved_hop as _plan_resolved_hop
from parallax.core.storage_layout import (
    ColumnContributor,
    DirectColumn,
    DocumentPath,
    StorageLayoutFacet,
    TableLayout,
)

_COMPARATORS: dict[str, str] = {
    "eq": "=",
    "notEq": "<>",
    "greaterThan": ">",
    "greaterThanEquals": ">=",
    "lessThan": "<",
    "lessThanEquals": "<=",
}


@dataclass(frozen=True, slots=True)
class MemberSubject:
    """One resolved scalar member as a predicate or ordering term reads it.

    ``extraction`` is what the member's value is read out of — an
    alias-qualified Column under a `DirectColumn` placement, the dialect's
    document text extraction under a `DocumentPath` one. ``compared`` is that
    expression with the declared type's cast applied where the comparison casts
    at all (`m-dialect`), and is identical to ``extraction`` for a direct Column,
    which is already typed, and for a document-resident member of one of the six
    text-compared types.

    The two are not interchangeable: an equality, range, or membership test
    compares ``compared`` while a null check and a string pattern read
    ``extraction``, exactly as the conventional nested vocabulary already does.
    ``document_resident`` is what decides which literal form a compared value
    binds in. ``text_compared`` is the narrower fact a REBIND needs: whether
    ``compared`` yields the codec's comparison text rather than a value of the
    declared type. It is not derivable from the other three — a wrapped `union
    all` names a `bytes` member by the result key its branches already
    hex-encoded, so that expression compares as text while claiming no document
    residence at all.
    """

    extraction: str
    compared: str
    type: NeutralType
    document_resident: bool
    text_compared: bool = False


@dataclass(frozen=True, slots=True)
class EntityScope:
    """A predicate resolving against an ENTITY: the active target, its alias, and
    whether this statement qualifies its own columns at all.

    ``unaliased`` is the write lane (`m-batch-write.md` "Predicate-selected
    readless forms"): a write's rendered predicate is UNALIASED (`where balance
    < ?`), contrasting the resolving read's aliased `t0.balance < ?` form.
    ``False`` — the read compiler's default — for every ordinary read scope. It
    lives on the scope rather than on the context precisely so that
    `compile_write_predicate` reaches the very same vocabulary a read does, one
    flag apart.

    ``layout`` is the ONE physical Table this statement (or `union all` branch)
    reads, so every reference to a member's column is answered by a Storage
    Layout slot rather than by re-reading the member's own storage declaration.
    A branch of a table-per-concrete-subtype union carries its OWN branch layout
    even though its active entity stays the read's queried `target`, which is what
    makes "does this branch physically carry that member?" a question the scope
    can answer at all.

    ``wrapped`` says :attr:`alias` is a derived table over a union of branches
    that already applied their own per-type projection, so a direct member is
    named by the RESULT key a branch projected it under rather than by the
    physical Column no such union yields — and a `bytes` member is then the
    hex-encoded text that key carries rather than octets.
    """

    ctx: StatementBuilder
    entity: EntityMetadata
    layout: TableLayout
    alias: str = "t0"
    unaliased: bool = False
    position: Sequence[EntityIdentity] | None = None
    variant: EntityIdentity | None = None
    wrapped: bool = False

    @property
    def meta(self) -> Metamodel:
        return self.ctx.meta

    @property
    def facet(self) -> InheritanceFacet:
        return self.ctx.facet

    @property
    def storage(self) -> StorageLayoutFacet:
        return self.ctx.storage

    @property
    def dialect(self) -> Dialect:
        return self.ctx.dialect

    def own_column(self, column: str) -> str:
        """Render one of THIS scope's own columns, honoring :attr:`unaliased`.

        The single consultant of :attr:`unaliased` — every reference to a column
        of the active target must route through here so a write's bare-column
        form can never be bypassed. :meth:`column_of` and :meth:`subject_for` are
        the attribute-resolving front doors; a Structured Column is not an
        ``Attribute`` and so has no Attribute to resolve, but it is just as much
        this target's own column and takes the same rendering decision, which is
        why :meth:`document_root` returns a rendered reference rather than a name.

        Not every column reference is "this scope's own": an unnested array
        element's ``t1.value`` is always alias-qualified, because the subquery
        that produced it declares that alias itself regardless of whether the
        enclosing statement is a read or a write. Those callers reach for
        :meth:`Dialect.qualified` directly, and correctly so.
        """
        if self.unaliased:
            return self.dialect.quote(column)
        return self.dialect.qualified(self.alias, column)

    def column_of(self, attr_ref: str) -> str:
        """Render one DIRECT Attribute Column of the active target.

        The join lane's front door. Member Placement is the sole authority here
        too (`m-storage-layout`), and what it must answer is `DirectColumn`:
        both endpoints of a Relationship Join hold a direct-column role under
        either layout, so a hop's correlation always has a Column to name and
        never extracts from a document.

        The reference resolves by name against the active target's family
        (:meth:`entity_attribute`), so an endpoint addressed at a descendant
        position reaches the ancestor declaration the placement is keyed by.
        """
        return self.column_for(self.entity_attribute(attr_ref))

    def column_for(self, attribute: AttributeMetadata) -> str:
        """Render a validated direct-column Attribute by identity."""
        placement = self.layout.placement(attribute.identity)
        if not isinstance(placement, DirectColumn):  # pragma: no cover
            raise SqlGenError(
                f"{attribute.identity!r} is not a direct Column of table "
                f"{self.layout.table.name!r}, so it cannot carry a join correlation"
            )
        return self.own_column(placement.slot.column.name)

    def subject_for(self, attribute: AttributeMetadata) -> MemberSubject:
        """Render a validated Attribute without revisiting its authored spelling.

        Member Placement is the sole authority (`m-storage-layout`): a
        `DirectColumn` renders the Column, and a `DocumentPath` renders the
        dialect's extraction over the Structured Column the placement names,
        binding that path's segments here — so the path comes from the compiled
        placement rather than from splitting an authored string, and the segments
        are already on the context before the caller binds its compared value.
        """
        placement = self.layout.placement(attribute.identity)
        if not isinstance(placement, DocumentPath):
            spelling = self.slot_column(attribute.identity)
            encoded = self.wrapped and isinstance(attribute.type, Bytes)
            column = self.own_column(
                projection_result_key(spelling, attribute.type) if self.wrapped else spelling
            )
            return MemberSubject(
                column, column, attribute.type, document_resident=False, text_compared=encoded
            )
        self._record_document_applicability(attribute.identity.entity)
        document = self.own_column(placement.slot.column.name)
        extraction, path_binds = self.dialect.nested_extract(document, placement.path)
        self.ctx.bind_structural_all(path_binds)
        return MemberSubject(
            extraction,
            self.dialect.nested_cast(extraction, attribute.type),
            attribute.type,
            document_resident=True,
            text_compared=is_text_compared(attribute.type),
        )

    def document_resident(self, attribute: AttributeMetadata) -> bool:
        """Whether this scope reads ``attribute`` out of a document.

        The same Member Placement question :meth:`subject_for` renders from,
        asked without emitting anything: resolving a subject binds the
        extraction's path segments on the context, so a caller deciding whether
        to emit an occurrence at all cannot ask by resolving one.
        """
        return isinstance(self.layout.placement(attribute.identity), DocumentPath)

    def document_root(self, vo: ValueObjectMetadata) -> tuple[str, tuple[str, ...]]:
        """The rendered document reference carrying ``vo``, and the path reaching it.

        One occurrence sits in two places depending on the Entity's layout, and
        its placement says which: under `Columns` it owns a Structured Column of
        its own and the prefix is empty, while under `Document` it is a subtree of
        the Table's one shared Structured Column and the prefix is its own path
        from that document's root. Every path a nested predicate walks is
        prefixed with it, so one extraction site serves both layouts.
        """
        placement = self.layout.placement(vo.identity)
        if isinstance(placement, DocumentPath):
            self._record_document_applicability(vo.identity.entity)
            return self.own_column(placement.slot.column.name), placement.path
        return self.own_column(self.slot_column(vo.identity)), ()

    def slot_column(self, contributor: ColumnContributor) -> str:
        """``contributor``'s physical Column in the Table this scope reads.

        The one place a member reaches its column: `m-sql` resolves accepted
        member Identities through the Storage Layout slot index rather than
        re-reading each declaration's own storage location, so a predicate and
        the projection beside it can never disagree about the physical Table.
        """
        slot = self.layout.contribution(contributor)
        if slot is None:
            raise SqlGenError(f"{contributor} has no Column in table {self.layout.table.name!r}")
        return slot.column.name

    def entity_attribute(self, attr_ref: str) -> AttributeMetadata:
        owner_ref, _, name = attr_ref.rpartition(".")
        owner = entity_by_name(self.meta, owner_ref)
        if owner is not None:
            attribute = _entity_view(self.facet, owner.identity).applicable_attribute(name)
            root = _entity_view(self.facet, self.entity.identity).root
            searchable = {
                candidate.identity
                for candidate in _entity_view(self.facet, root).superset_attributes
            }
            if attribute is not None and attribute.identity in searchable:
                return attribute
        raise SqlGenError(f"{attr_ref!r} names no attribute on {self.entity.identity.name}")

    def _record_document_applicability(self, owner: EntityIdentity) -> None:
        if self.position is None:
            return
        owner_view = _entity_view(self.facet, owner)
        if self.variant is not None:
            exposed = (self.variant,)
        else:
            root = _entity_view(self.facet, self.entity.identity).root
            exposed = _entity_view(self.facet, root).concrete_subtypes
        if not set(exposed) <= set(owner_view.concrete_subtypes):
            self.ctx.requires_variant_partition = True

    def next_alias(self) -> str:
        return self.ctx.next_alias()

    def child(self, entity: EntityMetadata, alias: str) -> EntityScope:
        """A nested scope for a correlated hop's interior: the SAME statement
        context (so a nested hop's binds and aliases continue this statement's
        single sequence), a different active entity and alias.

        ``unaliased`` deliberately does NOT travel: the subquery this scope
        describes declares `alias` itself, so its columns are alias-qualified
        even inside a write's otherwise-unaliased predicate (`t1.folder_id = id`
        — the child correlation qualified, the parent column bare). The child's
        own Table Layout does travel, because the hop selects from the child's
        own table.
        """
        return EntityScope(
            ctx=self.ctx,
            entity=entity,
            layout=_table_layout(self.ctx.storage, self.ctx.facet, entity.identity),
            alias=alias,
        )


@dataclass(frozen=True, slots=True)
class ElementScope:
    """A predicate resolving against ONE UNNESTED value-object array element
    (m-value-object same-element semantics).

    Every leaf a quantifier's `where` reads is element-relative (`type`,
    `geo.country` — no leading `Class.valueObject`) and resolves against
    :attr:`container`, the same array element they all share, extracted through
    the alias the unnest declared. There is no
    ``unaliased`` here and there cannot be one: that alias is this statement's
    own declaration, so it qualifies in a write's predicate exactly as it does
    in a read's.
    """

    ctx: StatementBuilder
    container: OccurrenceMetadata
    alias: str

    @property
    def dialect(self) -> Dialect:
        return self.ctx.dialect

    def element_reference(self) -> str:
        """This element's own `t<n>.value` document reference."""
        return self.dialect.qualified(self.alias, "value")


ResolutionScope = EntityScope | ElementScope

type _Operation = (
    ResolvedComparison
    | ResolvedRange
    | ResolvedMembership
    | ResolvedStringMatch
    | ResolvedNullCheck
)
type _EntityPredicate = ResolvedConstant | ResolvedNarrow | ResolvedQuantifier | ResolvedSemiJoin


def lower_predicate(predicate: ResolvedPredicate, scope: ResolutionScope) -> str:
    """Lower one resolved predicate to a SQL fragment, appending binds in order.

    Boolean structure and scalar operations are legal in either scope; an
    operation reads its member from the scope's current position. Everything
    else needs an Entity position, which an element scope refuses with one
    message: `m-predicate`'s `elementPredicate` grammar is a single named
    production, so what an element `where` gets wrong is always the same thing.
    """
    match predicate:
        case ResolvedAnd(operands=operands):
            return " and ".join(lower_predicate(operand, scope) for operand in operands)
        case ResolvedOr(operands=operands):
            return " or ".join(lower_predicate(operand, scope) for operand in operands)
        case ResolvedNot(operand=operand):
            return f"not {lower_predicate(operand, scope)}"
        case ResolvedGroup(operand=operand):
            return f"({lower_predicate(operand, scope)})"
        case (
            ResolvedComparison()
            | ResolvedRange()
            | ResolvedMembership()
            | ResolvedStringMatch()
            | ResolvedNullCheck()
        ):
            return _lower_operation(predicate, scope)
        case _:
            if isinstance(scope, ElementScope):
                raise SqlGenError(
                    f"{type(predicate).__name__} is not a legal nestedExists/nestedNotExists "
                    "element predicate (m-predicate elementPredicate)"
                )
            return _lower_entity_predicate(predicate, scope)


def _lower_entity_predicate(predicate: _EntityPredicate, scope: EntityScope) -> str:
    match predicate:
        case ResolvedConstant(truth=truth):
            return "" if truth else "1 = 0"
        case ResolvedNarrow():
            return _lower_branch_narrow(predicate, scope)
        case ResolvedQuantifier():
            return _lower_quantifier(predicate, scope)
        case ResolvedSemiJoin():
            return _lower_semi_join(predicate, scope)
        case _:  # pragma: no cover - exhaustiveness guard
            assert_never(predicate)


def _lower_operation(operation: _Operation, scope: ResolutionScope) -> str:
    """One scalar operation over its member's subject expression.

    The subject resolves FIRST: a document-resident member's path segments bind
    ahead of the compared values, which is the order the emitted text puts their
    holes in.
    """
    subject = _subject(operation.member, scope)
    match operation:
        case ResolvedComparison(op=tag, value=value, framework=framework):
            _bind_operand(value, subject, scope, framework=framework)
            # A Value Object leaf's inequality keeps its negated-equality form.
            if tag == "notEq" and not isinstance(operation.member, AttributeMetadata):
                return f"not {subject.compared} = ?"
            return f"{subject.compared} {_COMPARATORS[tag]} ?"
        case ResolvedRange(lower=lower, upper=upper):
            _bind_operand(lower, subject, scope)
            _bind_operand(upper, subject, scope)
            return f"{subject.compared} between ? and ?"
        case ResolvedMembership(op=tag, values=values):
            return _lower_membership(tag, values, subject, scope)
        case ResolvedStringMatch(op=tag, pattern=pattern, case_insensitive=folded):
            return _lower_like(tag, pattern, folded, subject.extraction, scope)
        case ResolvedNullCheck(op=tag):
            column = subject.extraction
            return f"{column} is null" if tag == "isNull" else f"not {column} is null"
        case _:  # pragma: no cover - exhaustiveness guard
            assert_never(operation)


def _subject(member: ResolvedPredicateMember, scope: ResolutionScope) -> MemberSubject:
    """``member`` as read from ``scope``'s current position.

    An Attribute is read through its Member Placement. A Value Object leaf is a
    document extraction: from the Entity's document through single occurrences,
    or from the element a quantifier binds, relative to its occurrence.
    """
    if isinstance(member, AttributeMetadata):
        if isinstance(scope, ElementScope):
            raise SqlGenError(f"{member.identity} is not read from a Value Object element")
        return scope.subject_for(member)
    if isinstance(scope, EntityScope):
        vo, segments = _resolved_vo_path(member, scope)
        document, prefix = scope.document_root(vo)
        reference, path = document, (*prefix, *segments)
    else:
        base = scope.container.identity.path
        leaf_path = member.identity.value_object.path
        if leaf_path[: len(base)] != base:
            raise SqlGenError("resolved element leaf is outside its resolved container")
        reference, path = scope.element_reference(), (*leaf_path[len(base) :], member.identity.name)
    extraction, path_binds = scope.dialect.nested_extract(reference, path)
    scope.ctx.bind_structural_all(path_binds)
    return MemberSubject(
        extraction,
        scope.dialect.nested_cast(extraction, member.type),
        member.type,
        document_resident=True,
        text_compared=is_text_compared(member.type),
    )


def _lower_membership(
    tag: MembershipOp,
    values: tuple[ManagedValue, ...] | DeferredKeySet,
    subject: MemberSubject,
    scope: ResolutionScope,
) -> str:
    if isinstance(values, DeferredKeySet):
        if tag != "in":  # pragma: no cover - generated child reads are positive
            raise SqlGenError("a deferred key set supports only positive membership")
        if scope.dialect.name == "postgres":
            scope.ctx.bind_managed_array(values, values.neutral_type)
            return f"{subject.compared} = any(?)"
        scope.ctx.bind_managed(values, values.neutral_type)
        return f"{subject.compared} in (__parallax_deferred_keys__)"
    holes = ", ".join("?" for _ in values)
    for value in values:
        _bind_operand(value, subject, scope)
    fragment = f"{subject.compared} in ({holes})"
    return fragment if tag == "in" else f"not {fragment}"


def _bind_operand(
    value: object, subject: MemberSubject, scope: ResolutionScope, *, framework: bool = False
) -> None:
    """Bind one compared operand in the form ``subject``'s expression compares.

    A direct Column is compared in the engine's own column type, so its operand
    crosses the seam as its managed value with explicit neutral-type metadata,
    or as itself when it is a framework sentinel. A document-resident member is
    compared through an extraction: the codec-owned comparison text where the
    extraction compares as text, the managed value in its declared Neutral Type
    where the extraction casts. Wire decoding already occurred in predicate
    validation.
    """
    if not subject.document_resident:
        if framework:
            scope.ctx.bind_framework(value)
        else:
            scope.ctx.bind_managed(value, subject.type)
    elif subject.text_compared:
        scope.ctx.bind_comparison_text(comparison_text(subject.type, value), subject.type)
    else:
        scope.ctx.bind_managed(value, subject.type)


def _lower_like(
    kind: StringOp,
    value: str,
    case_insensitive: bool,
    subject_sql: str,
    scope: ResolutionScope,
) -> str:
    """Render one string predicate over an ALREADY-RESOLVED subject expression.

    The whole rule lives here once (m-sql "Wildcard / escape rendering"), because a
    scalar column, a nested extraction, and an unnested element's extraction differ
    only in how the subject was resolved: `like`/`notLike` bind the pattern verbatim,
    the affix forms bind an escaped pattern and append `escape ?` plus its bind ONLY
    when escaping actually changed the literal, `notLike` negates INFIX (the
    normalizer's fixed point for this operator, unlike membership's leading `not`),
    and case-insensitive matching folds both sides.
    """
    if kind in ("like", "notLike"):
        scope.ctx.bind_comparison_text(value, STRING)
        needs_escape = False
    else:
        # The affix pattern is folded to lower case under case-insensitive matching,
        # so the pattern bind is already lowercased (the corpus's affix convention);
        # `like`/`notLike` keep the pattern verbatim and rely on `lower(?)` alone.
        literal = value.lower() if case_insensitive else value
        pattern, needs_escape = _affix_pattern(kind, literal)
        scope.ctx.bind_comparison_text(pattern, STRING)
    subject_expr = f"lower({subject_sql})" if case_insensitive else subject_sql
    rhs = "lower(?)" if case_insensitive else "?"
    operator = "not like" if kind == "notLike" else "like"
    fragment = f"{subject_expr} {operator} {rhs}"
    if needs_escape:
        scope.ctx.bind_structural("\\")
        fragment = f"{fragment} escape ?"
    return fragment


# The three AFFIX kinds, whose `value` is literal text this module wraps in
# wildcards. `like` / `notLike` are deliberately absent: their value is already a
# pattern, and `_lower_like` routes them away before any affix rendering — so the
# narrower domain makes that contract unrepresentable rather than merely documented.
_AffixOp = Literal["startsWith", "endsWith", "contains"]


def _affix_pattern(kind: _AffixOp, value: str) -> tuple[str, bool]:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    needs_escape = escaped != value
    if kind == "startsWith":
        return f"{escaped}%", needs_escape
    if kind == "endsWith":
        return f"%{escaped}", needs_escape
    if kind == "contains":
        return f"%{escaped}%", needs_escape
    assert_never(kind)  # pragma: no cover - exhaustiveness guard


def _lower_branch_narrow(narrow: ResolvedNarrow, scope: EntityScope) -> str:
    """A `narrow` reached MID-predicate (nested inside and/or/not/group) — a
    **grouped branch predicate** (m-sql "Grouped branch predicates"): the
    branch's own operand composes with its own tag guard via `and`, and the
    composition is wrapped in parens whenever there is a branch predicate to
    disambiguate against a sibling branch joined by `or` (`m-inheritance-015`).
    """
    plan = _plan_resolved_branch_narrow(scope.facet, scope.storage, scope.entity, narrow.position)
    if scope.variant is not None:
        if scope.variant not in plan.position:
            return "1 = 0"
        return lower_predicate(narrow.operand, scope) or "1 = 1"
    if plan.tag is None:  # pragma: no cover - TPCS union branches always carry a variant
        raise SqlGenError("a TPCS branch narrow requires a concrete branch scope")
    # Branch predicate first, THEN the guard's binds — the same explicit ordering
    # the top-level read states, for the same reason.
    branch_sql = lower_predicate(narrow.operand, scope)
    tag_sql, tag_binds = _tph_tag_guard(scope, scope.facet, plan.tag)
    scope.ctx.bind_framework_all(tag_binds)
    if not branch_sql:
        return tag_sql
    return f"({branch_sql} and {tag_sql})"


def _lower_semi_join(join: ResolvedSemiJoin, scope: EntityScope) -> str:
    """One correlated `EXISTS` per planned branch of the reached Entity.

    A `where` that is itself a `narrow` selects the branches the hop plans
    rather than lowering as a guard inside each of them.
    """
    narrowed = join.where if isinstance(join.where, ResolvedNarrow) else None
    inner = join.where if narrowed is None else narrowed.operand
    plan = _plan_resolved_hop(
        join.target,
        join.source,
        join.related,
        position=None if narrowed is None else narrowed.position,
        scope=scope,
        negate=join.negated,
    )
    fragments: list[str] = []
    for branch in plan.branches:
        # Opened INSIDE the loop, not up front: a branch takes its alias
        # immediately before its own interior lowers, so a later branch's alias
        # follows everything the preceding branch's interior allocated. Hoisting
        # this would renumber a grouped table-per-concrete-subtype hop whose
        # interior itself navigates.
        opened = _open_branch(branch, scope)
        child_scope = scope.child(opened.entity, opened.alias)
        where = _hop_where(inner, opened.correlation, child_scope, *opened.tag_fragment)
        # AFTER the interior: the plan carried the guard's bind VALUES precisely so
        # this push is the caller's own visible statement (`_navigation` holds no
        # capability to have pushed them itself).
        child_scope.ctx.bind_framework_all(opened.tag_binds)
        fragments.append(opened.render(where))
    return plan.combine(fragments)


def _hop_where(
    inner: ResolvedPredicate | None,
    correlation: str,
    child_scope: EntityScope,
    *extra: str,
) -> str:
    """The correlated sub-select's `where` clause: correlation, then the (optional)
    interior predicate, then any trailing fragment (a TPH tag guard) — the shared
    term order every hop shape composes (m-sql "Grouped branch predicates":
    a user/interior predicate binds before a framework-injected guard)."""
    terms = [correlation]
    if inner is not None:
        inner_sql = lower_predicate(inner, child_scope)
        if inner_sql:
            terms.append(inner_sql)
    terms.extend(extra)
    return " and ".join(terms)


def _resolved_vo_path(
    leaf: ValueObjectAttributeMetadata, scope: EntityScope
) -> tuple[ValueObjectMetadata, tuple[str, ...]]:
    identity = leaf.identity.value_object
    vo = _entity_view(scope.facet, identity.entity).applicable_value_object(identity.path[0])
    if vo is None:
        raise SqlGenError(f"resolved Value Object {identity} is absent from the active position")
    return vo, (*identity.path[1:], leaf.identity.name)


def _lower_quantifier(quantifier: ResolvedQuantifier, scope: EntityScope) -> str:
    """A bare quantifier is a non-empty / empty-or-absent test over the guarded
    unnest; its `where` composes on the SAME unnested alias (same-element
    semantics, m-value-object), so separate quantifiers never share an alias.
    Postgres `EXISTS` is never NULL, so `none` needs no `coalesce` wrap:
    `not exists (...)` over zero unnested elements is already true (m-sql,
    explicit). MariaDB's containment form DOES need one — but this claim is
    Postgres-only and that form is not implemented here.

    The `where` is handed back to :func:`lower_predicate` under an
    :class:`ElementScope`; there is no second dispatcher for it.
    """
    occurrence = quantifier.occurrence
    identity = occurrence.identity
    vo = _entity_view(scope.facet, identity.entity).applicable_value_object(identity.path[0])
    if vo is None:
        raise SqlGenError(f"resolved Value Object {identity} is absent from the active position")
    if occurrence.multiplicity is not Multiplicity.MANY:
        raise SqlGenError(
            f"nestedExists/nestedNotExists over a `one`-multiplicity value object "
            f"({identity}) has no goldened lowering yet"
        )
    document, prefix = scope.document_root(vo)
    guard_sql, guard_binds = scope.dialect.array_guard(document, (*prefix, *identity.path[1:]))
    scope.ctx.bind_framework_all(guard_binds)
    element = ElementScope(ctx=scope.ctx, container=occurrence, alias=scope.next_alias())
    inner = f"select 1 from jsonb_array_elements({guard_sql}) {element.alias}"
    if quantifier.where is not None:
        inner = f"{inner} where {lower_predicate(quantifier.where, element)}"
    keyword = "not exists" if quantifier.kind == "none" else "exists"
    return f"{keyword} ({inner})"
