from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Literal

from parallax.core.document_codec import is_text_compared
from parallax.core.inheritance import InheritanceFacet
from parallax.core.metamodel import (
    AbstractRoot,
    AttributeIdentity,
    AttributeMetadata,
    EntityIdentity,
    EntityMetadata,
    Metamodel,
    OccurrenceMetadata,
    TablePerHierarchy,
    ValueObjectAttributeMetadata,
)
from parallax.core.navigate import TemporallyResolvedPredicate
from parallax.core.object_query._resolved import ResolvedOrderTerm
from parallax.core.predicate._perspective import TemporalPerspective
from parallax.core.predicate._resolved import (
    CurrentObject,
    ObjectPosition,
    RelatedObject,
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
    ResolvedPresence,
    ResolvedQuantifier,
    ResolvedRange,
    ResolvedRelationship,
    ResolvedStringMatch,
    ScalarCollection,
    ScalarElement,
)
from parallax.core.sql_gen._context import SqlGenError
from parallax.core.sql_gen._context import table_layout as _table_layout
from parallax.core.sql_gen._inheritance import TagPredicate as _TagPredicate
from parallax.core.sql_gen._inheritance import TpcsSinglePlan as _TpcsSinglePlan
from parallax.core.sql_gen._inheritance import TpcsUnionPlan as _TpcsUnionPlan
from parallax.core.sql_gen._inheritance import TphPlan as _TphPlan
from parallax.core.sql_gen._inheritance import entity_view as _entity_view
from parallax.core.sql_gen._inheritance import (
    plan_resolved_branch_narrow as _plan_resolved_branch_narrow,
)
from parallax.core.sql_gen._inheritance import tag_column as _tag_column
from parallax.core.storage_layout import DocumentPath, StorageLayoutFacet, TableLayout


@dataclass(frozen=True, slots=True)
class RelationshipCandidateBranch:
    """One physical Table a relationship's candidates are read from, which can
    yield zero, one, or several rows; it takes no alias until it renders."""

    entity: EntityMetadata
    table: str
    source: AttributeMetadata
    related: AttributeMetadata
    family_guard: _TagPredicate | None


@dataclass(frozen=True, slots=True)
class RelationshipCandidatePlan:
    branches: tuple[RelationshipCandidateBranch, ...]


def _entity(model: Metamodel, identity: EntityIdentity) -> EntityMetadata:
    entity = model.entity(identity)
    if entity is None:  # pragma: no cover - validated positions name accepted entities
        raise SqlGenError(f"{identity.canonical!r} names no declared entity")
    return entity


def plan_relationship_candidates(
    relationship: ResolvedRelationship,
    *,
    position: tuple[EntityIdentity, ...] | None,
    meta: Metamodel,
    facet: InheritanceFacet,
    storage: StorageLayoutFacet,
) -> RelationshipCandidatePlan:
    """Every physical branch ``relationship``'s candidates come from, read from
    canonical metadata and layout; ``position`` selects a narrower effective
    family where a quantifier's operand narrows its element."""
    target = relationship.target
    if target.inheritance is None:
        return _plan(_branch(target, relationship, facet, storage, None))
    view = _entity_view(facet, target.identity)
    effective = tuple(view.concrete_subtypes) if position is None else position
    if isinstance(view.strategy, TablePerHierarchy):
        is_bare_root = position is None and isinstance(target.inheritance, AbstractRoot)
        root = view.root
        layout = _table_layout(storage, facet, root)
        guard = None if is_bare_root else _TagPredicate(_tag_column(layout, root), effective)
        return _plan(_branch(_entity(meta, root), relationship, facet, storage, guard))
    return RelationshipCandidatePlan(
        tuple(
            _branch(_entity(meta, concrete), relationship, facet, storage, None)
            for concrete in effective
        )
    )


def _plan(branch: RelationshipCandidateBranch) -> RelationshipCandidatePlan:
    return RelationshipCandidatePlan((branch,))


def _branch(
    entity: EntityMetadata,
    relationship: ResolvedRelationship,
    facet: InheritanceFacet,
    storage: StorageLayoutFacet,
    family_guard: _TagPredicate | None,
) -> RelationshipCandidateBranch:
    return RelationshipCandidateBranch(
        entity=entity,
        table=_table_layout(storage, facet, entity.identity).table.name,
        source=relationship.source,
        related=relationship.related,
        family_guard=family_guard,
    )


def temporal_visibility(relationship: ResolvedRelationship) -> TemporalPerspective:
    """The perspective ``relationship``'s candidates are visible under."""
    visibility = relationship.temporal_visibility
    if visibility is None:  # pragma: no cover - temporal resolution reaches every relationship
        raise SqlGenError(f"{relationship.identity}: the relationship's visibility is unresolved")
    return visibility


def shared_relationship_is_eligible(
    relationship: ResolvedRelationship,
    candidates: RelationshipCandidatePlan,
    *,
    facet: InheritanceFacet,
    storage: StorageLayoutFacet,
) -> bool:
    """Whether ``relationship`` reaches at most one candidate row, so a shared
    join cannot multiply the rows it is joined to.

    Only one physical branch qualifies, because a Table's unique key says
    nothing about another concrete Table of the same family. Then either the
    strict equalities of its correlation and temporal visibility fix every
    Column of one of that Table's unique keys — strict equality never matches a
    null component, so a nullable unique Column qualifies too, and an axis seen
    at Latest fixes its end — or the correlation fixes the target family's
    logical key and the target is temporal: its visibility selects one
    perspective on every axis, which the full-history non-overlap invariant
    (`m-temporal-write`) makes one milestone. Declared cardinality, authored
    conditions, and operand-local subtype selection prove nothing.
    """
    if len(candidates.branches) != 1:
        return False
    (branch,) = candidates.branches
    guard = branch.family_guard
    if guard is not None and not guard.position:  # pragma: no cover - an empty family is unplanned
        return False
    visibility = temporal_visibility(relationship)
    related = branch.related.identity
    layout = _table_layout(storage, facet, branch.entity.identity)
    if any(
        key.columns
        and all(
            slot.contributor == related
            or (
                isinstance(slot.contributor, AttributeIdentity)
                and visibility.is_latest_end(slot.contributor)
            )
            for slot in key.columns
        )
        for key in layout.unique_keys
    ):
        return True
    logical_key = _entity_view(facet, relationship.target.identity).primary_key
    return visibility.is_temporal and related == logical_key.identity


# --------------------------------------------------------------------------- #
# Statement plans                                                              #
# --------------------------------------------------------------------------- #


class EvaluationContext(Enum):
    """Where a planned predicate may share sources.

    ``SHARING_ALLOWED`` permits proven, failure-safe sharing at each lexical row
    that has a `from` of its own; ``SHARING_FORBIDDEN`` keeps every evaluation
    and nested navigation unshared; ``WRITE_FILTER`` selects a
    :class:`WriteFilterForm` from the root's sharing needs, then plans that
    form's nested evaluations.
    """

    SHARING_ALLOWED = "sharing_allowed"
    SHARING_FORBIDDEN = "sharing_forbidden"
    WRITE_FILTER = "write_filter"


class WriteFilterForm(Enum):
    """Where a write filter's predicate is evaluated: in the update/delete's own
    `where` over unaliased root columns, or in a subquery selecting every
    physical primary-key Column through the predicate's shared sources."""

    DIRECT_PREDICATE = "direct_predicate"
    PRIMARY_KEY_SUBQUERY = "primary_key_subquery"


type PredicatePath = tuple[int, ...]
"""A predicate occurrence within one lexical plan: the child slots from its
root, an operand index for `and`/`or` and ``0`` for a unary operand or a body."""

type LexicalScopeId = int
"""An index into one statement plan's :attr:`StatementPlan.lexical_scopes`."""


@dataclass(frozen=True, slots=True)
class SharedSourceRef:
    scope_id: LexicalScopeId
    index: int

    @property
    def kind(self) -> Literal["source"]:
        return "source"


@dataclass(frozen=True, slots=True)
class OwnerResultsRef:
    scope_id: LexicalScopeId
    index: int

    @property
    def kind(self) -> Literal["owner_results"]:
        return "owner_results"


@dataclass(frozen=True, slots=True)
class SharedSourcePlan:
    """One relationship occurrence its lexical row reads through one left join,
    reached from ``parent`` or, where that is ``None``, from the row itself."""

    relationship: ResolvedRelationship
    candidate: RelationshipCandidateBranch
    parent: SharedSourceRef | None


@dataclass(frozen=True, slots=True)
class OwnerResultCell:
    """One quantifier occurrence's result: ``path`` addresses it in the owning
    lexical plan, and ``scope_id`` is the plan its cell is evaluated in, at the
    owner row and rooted at the quantifier itself."""

    path: PredicatePath
    scope_id: LexicalScopeId


@dataclass(frozen=True, slots=True)
class OwnerResultsPlan:
    """The collection quantifiers its lexical row evaluates once per row of
    ``owner``, each its own result cell, in first-use order."""

    owner: SharedSourceRef
    cells: tuple[OwnerResultCell, ...]


@dataclass(frozen=True, slots=True)
class PlannedHop:
    """One correlated scalar hop over every candidate branch of ``relationship``."""

    relationship: ResolvedRelationship
    candidates: RelationshipCandidatePlan


@dataclass(frozen=True, slots=True)
class ReachedRow:
    """The occurrence evaluated as stated at the row it reaches."""


@dataclass(frozen=True, slots=True)
class NoCandidate:
    """The next target has no concrete subtype, so the occurrence answers its
    absence where it was reached."""


@dataclass(frozen=True, slots=True)
class CandidateOperand:
    """One candidate branch of a relationship presence or quantifier, and the
    lexical plan its operand is evaluated in, if it has one."""

    branch: RelationshipCandidateBranch
    operand_scope: LexicalScopeId | None


@dataclass(frozen=True, slots=True)
class CandidateExistence:
    """A relationship presence or quantifier as one `exists` per candidate;
    no candidate at all where the relationship reaches no concrete subtype."""

    candidates: tuple[CandidateOperand, ...]


@dataclass(frozen=True, slots=True)
class JoinedTargetMatch:
    """A presence read from the shared join of its own target, matching its
    operand at that target's row."""

    operand_scope: LexicalScopeId | None


type SubtypeSelection = bool | _TagPredicate
"""Whether a narrowed row belongs to the selection: decided for a concrete
branch, else tested by its tag guard."""


@dataclass(frozen=True, slots=True)
class TargetSelection:
    """A narrowing of a reached target at one of its rows."""

    selection: SubtypeSelection
    operand_scope: LexicalScopeId | None


@dataclass(frozen=True, slots=True)
class BranchSelection:
    """A narrowing of the lexical row itself; its operand, when rendered, is
    the occurrence's child slot ``0`` in the same lexical plan."""

    selection: SubtypeSelection


type Terminal = (
    ReachedRow
    | NoCandidate
    | CandidateExistence
    | JoinedTargetMatch
    | TargetSelection
    | BranchSelection
)

REACHED_ROW: ReachedRow = ReachedRow()
NO_CANDIDATE: NoCandidate = NoCandidate()


@dataclass(frozen=True, slots=True)
class Continuation:
    """The correlated scalar hops an occurrence is evaluated through, and its
    terminal at each candidate branch of the last hop — or, past no hop, its
    one terminal at the row it starts from."""

    hops: tuple[PlannedHop, ...]
    terminals: tuple[Terminal, ...]

    @property
    def reaches_target(self) -> bool:
        return not isinstance(self.terminals[0], NoCandidate)


@dataclass(frozen=True, slots=True)
class UnsharedEvaluation:
    """Evaluated relative to the current lexical row without a shared source."""

    continuation: Continuation


@dataclass(frozen=True, slots=True)
class SharedRowEvaluation:
    """Evaluated at ``source``'s joined target row."""

    source: SharedSourceRef
    terminal: Terminal


@dataclass(frozen=True, slots=True)
class ConfinedScalarEvaluation:
    """Continued past the shared ``prefix`` through correlated scalar hops, the
    first hop's candidates confined to the prefix the row joined."""

    prefix: SharedSourceRef
    continuation: Continuation


@dataclass(frozen=True, slots=True)
class OwnerResultEvaluation:
    """Read from this quantifier occurrence's ``cell`` of ``results``."""

    results: OwnerResultsRef
    cell: int


type PredicatePlacement = (
    UnsharedEvaluation | SharedRowEvaluation | ConfinedScalarEvaluation | OwnerResultEvaluation
)

_AT_ROW: UnsharedEvaluation = UnsharedEvaluation(Continuation((), (REACHED_ROW,)))


@dataclass(frozen=True, slots=True)
class LexicalScopePlan:
    """The planned evaluation of one lexical predicate root at one row.

    ``placements`` holds every placement-bearing occurrence the plan renders;
    Boolean composition and constants hold none.
    """

    scope_id: LexicalScopeId
    predicate: ResolvedPredicate
    placements: Mapping[PredicatePath, PredicatePlacement]
    sources: tuple[SharedSourcePlan, ...]
    owner_results: tuple[OwnerResultsPlan, ...]


@dataclass(frozen=True, slots=True)
class StatementPlan:
    """One compilation's planned predicate evaluation.

    ``root_scopes`` names the lexical plan of each physical root: ``None`` for
    a root no concrete branch fixes, else that branch's concrete Entity.
    ``requires_tph_partition`` is whether a table-per-hierarchy read renders
    one partition per concrete; ``write_filter_form`` is present exactly for a
    write filter.
    """

    predicate: TemporallyResolvedPredicate
    lexical_scopes: tuple[LexicalScopePlan, ...]
    root_scopes: Mapping[EntityIdentity | None, LexicalScopeId]
    requires_tph_partition: bool
    write_filter_form: WriteFilterForm | None


type _InheritanceRead = _TphPlan | _TpcsSinglePlan | _TpcsUnionPlan


def plan_statement(
    predicate: TemporallyResolvedPredicate,
    *,
    evaluation_context: EvaluationContext,
    entity: EntityMetadata,
    meta: Metamodel,
    facet: InheritanceFacet,
    storage: StorageLayoutFacet,
    inheritance_read: _InheritanceRead | None = None,
    order_terms: Sequence[ResolvedOrderTerm] = (),
) -> StatementPlan:
    """Plan ``predicate`` over ``entity``'s rows before anything renders.

    ``inheritance_read`` is the family read's existing plan, which decides the
    physical roots, and ``order_terms`` the read's ordering, which order,
    cursor capture, and seek read at the root row. Planning allocates no alias
    and binds nothing.
    """
    planner = _StatementPlanner(meta, facet, storage)
    root = predicate.predicate
    if evaluation_context is EvaluationContext.WRITE_FILTER:
        row = _Row(entity, _table_layout(storage, facet, entity.identity), None)
        scope_id, form = planner.write_filter(root, row)
        return planner.sealed(predicate, {None: scope_id}, False, form)
    sharing = evaluation_context is EvaluationContext.SHARING_ALLOWED
    partition = isinstance(inheritance_read, _TphPlan) and planner.partitions(
        predicate, entity, order_terms
    )
    roots = {
        concrete: planner.scope(root, row, shares=sharing, sharing=sharing)
        for concrete, row in _root_rows(entity, inheritance_read, partition, facet, storage)
    }
    return planner.sealed(predicate, roots, partition, None)


@dataclass(frozen=True, slots=True)
class _Row:
    """The row a lexical plan evaluates at: its resolution entity, its Table,
    and the concrete Entity its physical branch fixes, if any."""

    entity: EntityMetadata
    layout: TableLayout
    branch_concrete: EntityIdentity | None


def _root_rows(
    entity: EntityMetadata,
    inheritance_read: _InheritanceRead | None,
    partition: bool,
    facet: InheritanceFacet,
    storage: StorageLayoutFacet,
) -> Iterator[tuple[EntityIdentity | None, _Row]]:
    match inheritance_read:
        case None:
            yield None, _Row(entity, _table_layout(storage, facet, entity.identity), None)
        case _TphPlan(position=position):
            layout = _table_layout(storage, facet, entity.identity)
            if not partition:
                yield None, _Row(entity, layout, None)
                return
            for concrete in position:
                yield concrete, _Row(entity, layout, concrete)
        case _TpcsSinglePlan(position=position):
            yield None, _Row(entity, _table_layout(storage, facet, position[0]), None)
        case _TpcsUnionPlan(branches=branches):
            for branch in branches:
                layout = _table_layout(storage, facet, branch.identity)
                yield branch.identity, _Row(entity, layout, branch.identity)


class _StatementPlanner:
    """Private construction state of one :func:`plan_statement` call."""

    __slots__ = ("_scopes", "facet", "meta", "storage")

    def __init__(
        self, meta: Metamodel, facet: InheritanceFacet, storage: StorageLayoutFacet
    ) -> None:
        self.meta = meta
        self.facet = facet
        self.storage = storage
        self._scopes: list[LexicalScopePlan | None] = []

    def scope(
        self, predicate: ResolvedPredicate, row: _Row, *, shares: bool, sharing: bool
    ) -> LexicalScopeId:
        """Plan ``predicate`` at ``row``: sharing sources there where ``shares``,
        and letting the candidate operands it opens share theirs where
        ``sharing``."""
        construction = _ScopeConstruction(
            self, self._reserve(), row, shares=shares, sharing=sharing
        )
        construction.place(predicate)
        return self._seal(construction, predicate)

    def cell(self, quantifier: ResolvedQuantifier, row: _Row) -> LexicalScopeId:
        """Plan one owner-result cell: ``quantifier`` evaluated at the owner
        ``row`` itself, whatever position the quantifier reached it from."""
        construction = _ScopeConstruction(self, self._reserve(), row, shares=False, sharing=False)
        construction.place_at_row(quantifier)
        return self._seal(construction, quantifier)

    def write_filter(
        self, predicate: ResolvedPredicate, row: _Row
    ) -> tuple[LexicalScopeId, WriteFilterForm]:
        """Plan a write filter's one root in the form its root sharing selects,
        planning nested evaluations for that form alone."""
        scope_id = self._reserve()
        construction = _ScopeConstruction(self, scope_id, row, shares=True, sharing=True)
        construction.decide(predicate)
        form = WriteFilterForm.PRIMARY_KEY_SUBQUERY
        if not construction.shares():
            form = WriteFilterForm.DIRECT_PREDICATE
            construction = _ScopeConstruction(self, scope_id, row, shares=False, sharing=False)
        construction.place(predicate)
        return self._seal(construction, predicate), form

    def partitions(
        self,
        predicate: TemporallyResolvedPredicate,
        entity: EntityMetadata,
        order_terms: Sequence[ResolvedOrderTerm],
    ) -> bool:
        """Whether a table-per-hierarchy read of ``entity`` reads, at its root
        row, a document member some concrete of the whole root family lacks.

        Only the root row's own reads count: its predicate occurrences at the
        current object and its ordering terms, which order, cursor capture, and
        seek all read. A relationship candidate's reads belong to another row,
        and broad projection reads none.
        """
        facet = self.facet
        layout = _table_layout(self.storage, facet, entity.identity)
        root = _entity_view(facet, entity.identity).root
        exposed = set(_entity_view(facet, root).concrete_subtypes)
        applicability = _RootApplicability(facet, layout)
        owners = (
            *applicability.predicate(predicate.predicate),
            *(owner for term in order_terms if (owner := applicability.attribute(term.member))),
        )
        return any(
            not exposed <= set(_entity_view(facet, owner).concrete_subtypes) for owner in owners
        )

    def sealed(
        self,
        predicate: TemporallyResolvedPredicate,
        roots: dict[EntityIdentity | None, LexicalScopeId],
        requires_tph_partition: bool,
        write_filter_form: WriteFilterForm | None,
    ) -> StatementPlan:
        scopes: list[LexicalScopePlan] = []
        for scope in self._scopes:
            if scope is None:  # pragma: no cover - every reserved scope is planned
                raise SqlGenError("a reserved lexical scope was never planned")
            scopes.append(scope)
        return StatementPlan(
            predicate,
            tuple(scopes),
            MappingProxyType(roots),
            requires_tph_partition,
            write_filter_form,
        )

    def _reserve(self) -> LexicalScopeId:
        self._scopes.append(None)
        return len(self._scopes) - 1

    def _seal(
        self, construction: _ScopeConstruction, predicate: ResolvedPredicate
    ) -> LexicalScopeId:
        plan = construction.sealed(predicate)
        self._scopes[plan.scope_id] = plan
        return plan.scope_id


@dataclass(frozen=True, slots=True)
class _Joined:
    source: int


@dataclass(frozen=True, slots=True)
class _Confined:
    source: int
    hops: tuple[ResolvedRelationship, ...]


@dataclass(frozen=True, slots=True)
class _Collected:
    results: int
    cell: int


@dataclass(frozen=True, slots=True)
class _Reused:
    target: int


type _Shared = _Joined | _Confined | _Collected | _Reused

type _Operation = (
    ResolvedComparison
    | ResolvedRange
    | ResolvedMembership
    | ResolvedStringMatch
    | ResolvedNullCheck
)


class _OpenResults:
    __slots__ = ("owner", "paths", "scopes")

    def __init__(self, owner: int) -> None:
        self.owner = owner
        self.paths: list[PredicatePath] = []
        self.scopes: list[LexicalScopeId | None] = []


class _ScopeConstruction:
    """One lexical plan under construction.

    :meth:`place` gives every rendered occurrence its placement, planning the
    nested lexical plans of the evaluations it selects. Where ``shares``, it
    first decides, in first-use order, whether each occurrence reads shared
    sources at this row; presences are placed last, once every
    source-producing occurrence is known, so one can reuse a target a later
    sibling shares. :meth:`decide` instead takes every sharing decision before
    anything is placed.
    """

    __slots__ = (
        "_placements",
        "_planner",
        "_presences",
        "_results",
        "_results_refs",
        "_reuses",
        "_row",
        "_scope_id",
        "_shared",
        "_shares",
        "_sharing",
        "_source_refs",
        "_sources",
    )

    def __init__(
        self,
        planner: _StatementPlanner,
        scope_id: LexicalScopeId,
        row: _Row,
        *,
        shares: bool,
        sharing: bool,
    ) -> None:
        self._planner = planner
        self._scope_id = scope_id
        self._row = row
        self._shares = shares
        self._sharing = sharing
        self._sources: list[SharedSourcePlan] = []
        self._source_refs: list[SharedSourceRef] = []
        self._results: list[_OpenResults] = []
        self._results_refs: list[OwnerResultsRef] = []
        self._shared: dict[PredicatePath, _Shared] = {}
        self._reuses: list[tuple[ResolvedPresence, PredicatePath, int | None]] = []
        self._presences: list[tuple[ResolvedPresence, PredicatePath]] = []
        self._placements: dict[PredicatePath, PredicatePlacement] = {}

    def shares(self) -> bool:
        """Whether any occurrence reads through a shared source."""
        return bool(self._sources)

    def sealed(self, predicate: ResolvedPredicate) -> LexicalScopePlan:
        results: list[OwnerResultsPlan] = []
        for open_results in self._results:
            cells: list[OwnerResultCell] = []
            for path, scope_id in zip(open_results.paths, open_results.scopes, strict=True):
                if scope_id is None:  # pragma: no cover - every collected occurrence is placed
                    raise SqlGenError("an owner-result cell was never planned")
                cells.append(OwnerResultCell(path, scope_id))
            results.append(OwnerResultsPlan(self._source_refs[open_results.owner], tuple(cells)))
        return LexicalScopePlan(
            self._scope_id,
            predicate,
            MappingProxyType(self._placements),
            tuple(self._sources),
            tuple(results),
        )

    # ----------------------------------------------------------------------- #
    # Shared sources                                                           #
    # ----------------------------------------------------------------------- #

    def decide(self, predicate: ResolvedPredicate) -> None:
        """Decide every shared source ``predicate`` reads through at this row
        before anything is placed.

        Scalar operations, presence tests, target narrowings, and collection
        quantifiers reached through to-one hops, and those in the operand of a
        narrowing of the row itself, can share (:meth:`_share_reached`); an
        operand evaluated in a subquery plans its own. A presence whose target
        another occurrence shares reads that target's join.
        """
        self._share(predicate, ())
        self._resolve_reuse()
        self._shares = False

    def _resolve_reuse(self) -> None:
        for presence, path, reached in self._reuses:
            self._reuse(presence, path, reached)
        self._reuses.clear()

    def _share(self, predicate: ResolvedPredicate, path: PredicatePath) -> None:
        match predicate:
            case ResolvedAnd(operands=operands) | ResolvedOr(operands=operands):
                for index, operand in enumerate(operands):
                    self._share(operand, (*path, index))
            case ResolvedNot(operand=operand) | ResolvedGroup(operand=operand):
                self._share(operand, (*path, 0))
            case (
                ResolvedComparison(position=RelatedObject() as position)
                | ResolvedRange(position=RelatedObject() as position)
                | ResolvedMembership(position=RelatedObject() as position)
                | ResolvedStringMatch(position=RelatedObject() as position)
                | ResolvedNullCheck(position=RelatedObject() as position)
                | ResolvedNarrow(target=RelatedObject() as position)
            ):
                self._share_reached(predicate, path, _hops(position))
            case ResolvedQuantifier():
                self._share_collection(predicate, path)
            case ResolvedPresence():
                self._share_presence(predicate, path)
            case ResolvedNarrow(target=CurrentObject(), operand=operand) if (
                operand is not None and self._renders_branch_operand(predicate)
            ):
                self._share(operand, (*path, 0))
            case _:
                pass

    def _renders_branch_operand(self, narrow: ResolvedNarrow) -> bool:
        """Whether a narrowing of this row renders its operand here: a concrete
        branch outside the selection answers false without it."""
        concrete = self._row.branch_concrete
        return concrete is None or concrete in narrow.selection

    def _share_presence(self, presence: ResolvedPresence, path: PredicatePath) -> None:
        """Share ``presence``'s hops, and note a relationship presence whose own
        target a shared source might already join."""
        position = presence.position
        reached: int | None = None
        if isinstance(position, RelatedObject):
            decision = self._share_reached(presence, path, _hops(position))
            if not isinstance(decision, _Joined):
                return
            reached = decision.source
        if isinstance(presence.target, ResolvedRelationship):
            self._reuses.append((presence, path, reached))

    def _share_collection(self, quantifier: ResolvedQuantifier, path: PredicatePath) -> None:
        """Share a quantifier over a collection its shared owner holds.

        A related Entity collection is quantified at the owner's joined row, its
        correlated `exists` one a database can evaluate set-wise. A document
        collection — a scalar collection or a ``many`` Value Object — reads the
        owner's results instead: its elements come from the owner row itself, so
        the quantifier is evaluated once per owner row the result relation reads
        rather than once per row of the scope. A relationship with no candidate
        answers inside its hops.
        """
        position = quantifier.position
        if not isinstance(position, RelatedObject):
            return
        collection = quantifier.collection
        related = isinstance(collection, ResolvedRelationship)
        if isinstance(collection, ResolvedRelationship) and self._reaches_nothing(collection):
            return
        decision = self._share_reached(quantifier, path, _hops(position))
        if isinstance(decision, _Joined) and not related:
            self._shared[path] = self._collect(decision.source, path)

    def _share_reached(
        self,
        occurrence: ResolvedPredicate,
        path: PredicatePath,
        hops: tuple[ResolvedRelationship, ...],
    ) -> _Joined | _Confined | None:
        """Share the leading proven ``hops`` of ``occurrence``.

        Where every hop is proven and the occurrence is safe over the last
        target's joined row, it reads that row. Otherwise the proven prefix —
        every hop but the last where all are proven — is shared, and the
        occurrence continues through its own scalar subqueries confined to that
        prefix: the first repeats the join terms of every shared source it is
        reached through, so it yields, and asserts the cardinality of, only the
        candidates of the joined row the evaluating row reaches, evaluating
        exactly what the unshared form would wherever the database tests the
        term. With no shared prefix, or past a target with no concrete
        subtype, it stays unshared.
        """
        if any(self._reaches_nothing(hop) for hop in hops):
            return None
        branches = self._proven_prefix(hops)
        if len(branches) == len(hops) and self._joined_row_is_safe(
            occurrence,
            _table_layout(self._planner.storage, self._planner.facet, branches[-1].entity.identity),
        ):
            shared = len(hops)
        else:
            shared = min(len(branches), len(hops) - 1)
            if not shared:
                return None
        reached: int | None = None
        for hop, branch in zip(hops[:shared], branches, strict=False):
            reached = self._adopt(reached, hop, branch)
        assert reached is not None
        decision = _Joined(reached) if shared == len(hops) else _Confined(reached, hops[shared:])
        self._shared[path] = decision
        return decision

    def _reuse(self, presence: ResolvedPresence, path: PredicatePath, reached: int | None) -> None:
        """Let ``presence`` read its target's join where another occurrence
        shares that target; matching alone opens no join."""
        target = presence.target
        if not isinstance(target, ResolvedRelationship):  # pragma: no cover - planned relationships
            return
        shared = self._find(reached, target)
        if shared is None:
            return
        where = presence.where
        layout = _table_layout(
            self._planner.storage,
            self._planner.facet,
            self._sources[shared].candidate.entity.identity,
        )
        if where is None or _operand_is_safe(where, layout):
            self._shared[path] = _Reused(shared)

    def _proven_prefix(
        self, hops: tuple[ResolvedRelationship, ...]
    ) -> list[RelationshipCandidateBranch]:
        """The one candidate branch of each leading hop proven unique."""
        proven: list[RelationshipCandidateBranch] = []
        planner = self._planner
        for hop in hops:
            candidates = self._candidates(hop)
            if not shared_relationship_is_eligible(
                hop, candidates, facet=planner.facet, storage=planner.storage
            ):
                break
            proven.append(candidates.branches[0])
        return proven

    def _find(self, parent: int | None, relationship: ResolvedRelationship) -> int | None:
        """The source already reaching ``relationship``'s occurrence from ``parent``."""
        parent_ref = None if parent is None else self._source_refs[parent]
        return next(
            (
                index
                for index, source in enumerate(self._sources)
                if source.parent is parent_ref
                and _same_occurrence(source.relationship, relationship)
            ),
            None,
        )

    def _adopt(
        self,
        parent: int | None,
        relationship: ResolvedRelationship,
        candidate: RelationshipCandidateBranch,
    ) -> int:
        """The source reaching ``relationship`` from ``parent``, opened if new,
        so a source always follows the source it is reached from."""
        found = self._find(parent, relationship)
        if found is not None:
            return found
        parent_ref = None if parent is None else self._source_refs[parent]
        self._sources.append(SharedSourcePlan(relationship, candidate, parent_ref))
        self._source_refs.append(SharedSourceRef(self._scope_id, len(self._source_refs)))
        return len(self._sources) - 1

    def _collect(self, owner: int, path: PredicatePath) -> _Collected:
        """A new cell of ``owner``'s results, opened if new, for the occurrence
        at ``path``."""
        index = next(
            (index for index, results in enumerate(self._results) if results.owner == owner),
            None,
        )
        if index is None:
            index = len(self._results)
            self._results.append(_OpenResults(owner))
            self._results_refs.append(OwnerResultsRef(self._scope_id, index))
        results = self._results[index]
        results.paths.append(path)
        results.scopes.append(None)
        return _Collected(index, len(results.paths) - 1)

    def _joined_row_is_safe(self, occurrence: ResolvedPredicate, target: TableLayout) -> bool:
        """Whether evaluating ``occurrence`` over ``target``'s joined row
        evaluates nothing that can fail where its unshared form would not have.

        Uniqueness says how many rows a target has, not what an occurrence
        evaluates over them; this is the one place that second question is
        answered. An unshared occurrence reads its target inside a correlated
        subquery, over only the candidates that subquery admitted.

        A joined-row term is a filter a database may test against any target
        row it scans — including rows no source row reaches, which neither a
        presence guard nor a `case` excludes. A collection quantifier there, or
        in the owner results that read every row of ``target``'s table they are
        joined to, has its operand tested against every element of any such
        row. So a projection that can fail on stored data stays unshared there:
        a document-resident member converted to its declared type, a scalar
        element projected to a type its comparison casts to, and a presence's,
        match's, narrowing's, or quantifier's operand that evaluates anything
        :func:`_operand_is_safe` cannot establish. A direct Column, extracted
        text, and a presence or null test cannot fail.
        """
        match occurrence:
            case ResolvedComparison(member=member) | ResolvedRange(member=member):
                return not _converts(member, target)
            case ResolvedMembership(member=member):
                return not _converts(member, target)
            case ResolvedPresence(target=ResolvedRelationship() as relationship, where=where) if (
                where is not None
            ):
                return self._operand_is_safe_at_every_candidate(where, relationship)
            case ResolvedNarrow(operand=operand) if operand is not None:
                return _operand_is_safe(operand, target)
            case ResolvedQuantifier(
                collection=ResolvedRelationship() as collection, where=where
            ) if where is not None:
                return self._operand_is_safe_at_every_candidate(where, collection)
            case ResolvedQuantifier(where=where) if where is not None:
                return _operand_is_safe(where, target)
            case _:
                return True

    def _operand_is_safe_at_every_candidate(
        self, operand: ResolvedPredicate, relationship: ResolvedRelationship
    ) -> bool:
        planner = self._planner
        return all(
            _operand_is_safe(
                operand, _table_layout(planner.storage, planner.facet, branch.entity.identity)
            )
            for branch in self._candidates(relationship).branches
        )

    # ----------------------------------------------------------------------- #
    # Placements                                                               #
    # ----------------------------------------------------------------------- #

    def place(self, predicate: ResolvedPredicate) -> None:
        """Place every occurrence of the plan's root ``predicate`` that renders."""
        self._place(predicate, ())
        self._place_presences()

    def place_at_row(self, quantifier: ResolvedQuantifier) -> None:
        """Place ``quantifier`` as evaluated at this row, at the plan's root."""
        terminal = self._collection_terminal(quantifier, sharing=False)
        self._placements[()] = _here(terminal)
        self._place_body(quantifier, (), terminal)
        self._place_presences()

    def _place(self, predicate: ResolvedPredicate, path: PredicatePath) -> None:
        match predicate:
            case ResolvedAnd(operands=operands) | ResolvedOr(operands=operands):
                for index, operand in enumerate(operands):
                    self._place(operand, (*path, index))
            case ResolvedNot(operand=operand) | ResolvedGroup(operand=operand):
                self._place(operand, (*path, 0))
            case (
                ResolvedComparison()
                | ResolvedRange()
                | ResolvedMembership()
                | ResolvedStringMatch()
                | ResolvedNullCheck()
            ):
                self._placements[path] = self._operation(predicate, path)
            case ResolvedQuantifier():
                self._quantifier(predicate, path)
            case ResolvedPresence():
                if self._shares:
                    self._share_presence(predicate, path)
                self._presences.append((predicate, path))
            case ResolvedNarrow():
                self._narrow(predicate, path)
            case ResolvedConstant():
                pass

    def _place_presences(self) -> None:
        """Place presences once every occurrence that can open a source has."""
        self._resolve_reuse()
        for presence, path in self._presences:
            self._placements[path] = self._presence(presence, path)

    def _operation(self, operation: _Operation, path: PredicatePath) -> PredicatePlacement:
        position = operation.position
        if not isinstance(position, RelatedObject):
            return _AT_ROW
        hops = _hops(position)
        if self._shares:
            self._share_reached(operation, path, hops)
        match self._shared.get(path) if self._shared else None:
            case _Joined(source=source):
                return SharedRowEvaluation(self._source_refs[source], REACHED_ROW)
            case _Confined(source=source, hops=remaining):
                return ConfinedScalarEvaluation(
                    self._source_refs[source], self._uniform(remaining, REACHED_ROW)
                )
            case _:
                return UnsharedEvaluation(self._reached(hops, lambda: REACHED_ROW))

    def _quantifier(self, quantifier: ResolvedQuantifier, path: PredicatePath) -> None:
        if self._shares:
            self._share_collection(quantifier, path)
        decision = self._shared.get(path)
        terminal: Terminal
        match decision:
            case _Collected(results=results, cell=cell):
                open_results = self._results[results]
                owner = self._source_row(open_results.owner)
                open_results.scopes[cell] = self._planner.cell(quantifier, owner)
                self._placements[path] = OwnerResultEvaluation(self._results_refs[results], cell)
                return
            case _Joined(source=source):
                terminal = self._collection_terminal(quantifier, sharing=self._sharing)
                placement: PredicatePlacement = SharedRowEvaluation(
                    self._source_refs[source], terminal
                )
            case _Confined(source=source, hops=hops):
                terminal = self._collection_terminal(quantifier, sharing=False)
                placement = ConfinedScalarEvaluation(
                    self._source_refs[source], self._uniform(hops, terminal)
                )
            case _:
                position = quantifier.position
                if isinstance(position, RelatedObject):
                    continuation = self._reached(
                        _hops(position),
                        lambda: self._collection_terminal(quantifier, sharing=False),
                    )
                    terminal = continuation.terminals[0]
                    placement = UnsharedEvaluation(continuation)
                else:
                    terminal = self._collection_terminal(quantifier, sharing=self._sharing)
                    placement = _here(terminal)
        self._placements[path] = placement
        self._place_body(quantifier, path, terminal)

    def _place_body(
        self, quantifier: ResolvedQuantifier, path: PredicatePath, terminal: Terminal
    ) -> None:
        """Place a document collection's element body, which renders in this
        lexical plan wherever the collection is reached."""
        where = quantifier.where
        if isinstance(terminal, ReachedRow) and where is not None:
            self._place(where, (*path, 0))

    def _presence(self, presence: ResolvedPresence, path: PredicatePath) -> PredicatePlacement:
        match self._shared.get(path):
            case _Reused(target=target):
                where = presence.where
                operand = (
                    None
                    if where is None
                    else self._planner.scope(
                        where, self._source_row(target), shares=False, sharing=self._sharing
                    )
                )
                return SharedRowEvaluation(self._source_refs[target], JoinedTargetMatch(operand))
            case _Joined(source=source):
                return SharedRowEvaluation(
                    self._source_refs[source],
                    self._presence_terminal(presence, sharing=self._sharing),
                )
            case _Confined(source=source, hops=hops):
                return ConfinedScalarEvaluation(
                    self._source_refs[source],
                    self._uniform(hops, self._presence_terminal(presence, sharing=False)),
                )
            case _:
                position = presence.position
                if not isinstance(position, RelatedObject):
                    return _here(self._presence_terminal(presence, sharing=self._sharing))
                return UnsharedEvaluation(
                    self._reached(
                        _hops(position), lambda: self._presence_terminal(presence, sharing=False)
                    )
                )

    def _narrow(self, narrow: ResolvedNarrow, path: PredicatePath) -> None:
        target = narrow.target
        if self._shares and isinstance(target, RelatedObject):
            self._share_reached(narrow, path, _hops(target))
        if isinstance(target, CurrentObject):
            selection = self._branch_selection(narrow)
            self._placements[path] = UnsharedEvaluation(
                Continuation((), (BranchSelection(selection),))
            )
            if selection is not False and narrow.operand is not None:
                self._place(narrow.operand, (*path, 0))
            return
        placement: PredicatePlacement
        match self._shared.get(path):
            case _Joined(source=source):
                selection = self._target_selection(
                    narrow, self._source_row(source), sharing=self._sharing, joined=True
                )
                placement = SharedRowEvaluation(self._source_refs[source], selection)
            case _Confined(source=source, hops=hops):
                placement = ConfinedScalarEvaluation(
                    self._source_refs[source], self._per_branch(hops, narrow)
                )
            case _:
                hops = _hops(target)
                empty = self._first_empty(hops)
                continuation = (
                    self._per_branch(hops, narrow)
                    if empty is None
                    else self._uniform(hops[:empty], NO_CANDIDATE)
                )
                placement = UnsharedEvaluation(continuation)
        self._placements[path] = placement

    # ----------------------------------------------------------------------- #
    # Navigation and terminals                                                 #
    # ----------------------------------------------------------------------- #

    def _reached(
        self, hops: tuple[ResolvedRelationship, ...], terminal: Callable[[], Terminal]
    ) -> Continuation:
        """The unshared continuation through ``hops``: up to the first target
        with no candidate, or to ``terminal`` past every hop."""
        empty = self._first_empty(hops)
        if empty is not None:
            return self._uniform(hops[:empty], NO_CANDIDATE)
        return self._uniform(hops, terminal())

    def _uniform(self, hops: tuple[ResolvedRelationship, ...], terminal: Terminal) -> Continuation:
        """``hops`` with the same ``terminal`` at every candidate of the last."""
        planned = self._planned_hops(hops)
        count = len(planned[-1].candidates.branches) if planned else 1
        return Continuation(planned, (terminal,) * count)

    def _per_branch(
        self, hops: tuple[ResolvedRelationship, ...], narrow: ResolvedNarrow
    ) -> Continuation:
        """``hops`` to ``narrow``'s target, its selection decided at each
        candidate of the last, inside a correlated subquery."""
        planned = self._planned_hops(hops)
        last = planned[-1]
        terminals = tuple(
            self._target_selection(
                narrow,
                self._candidate_row(last.relationship, branch),
                sharing=False,
                joined=False,
            )
            for branch in last.candidates.branches
        )
        return Continuation(planned, terminals)

    def _planned_hops(self, hops: tuple[ResolvedRelationship, ...]) -> tuple[PlannedHop, ...]:
        return tuple(PlannedHop(hop, self._candidates(hop)) for hop in hops)

    def _first_empty(self, hops: tuple[ResolvedRelationship, ...]) -> int | None:
        """The first hop whose target has no concrete subtype."""
        return next((index for index, hop in enumerate(hops) if self._reaches_nothing(hop)), None)

    def _collection_terminal(self, quantifier: ResolvedQuantifier, *, sharing: bool) -> Terminal:
        """A quantifier's evaluation at the row holding its collection.

        An ``any`` or ``none`` whose ``where`` is itself a narrowing of the
        bound element selects the related branches it plans rather than
        lowering a guard in each: an element outside the selection makes that
        narrowing false, so it can neither match ``any`` nor spoil ``none``. A
        universal keeps every branch, because such an element is its
        counterexample.
        """
        collection = quantifier.collection
        if not isinstance(collection, ResolvedRelationship):
            return REACHED_ROW
        where = quantifier.where
        narrowed = (
            where
            if quantifier.kind != "all"
            and isinstance(where, ResolvedNarrow)
            and isinstance(where.target, CurrentObject)
            else None
        )
        if narrowed is None:
            return self._existence(collection, where, None, sharing=sharing)
        return self._existence(collection, narrowed.operand, narrowed.selection, sharing=sharing)

    def _presence_terminal(self, presence: ResolvedPresence, *, sharing: bool) -> Terminal:
        target = presence.target
        if isinstance(target, ResolvedRelationship):
            return self._existence(target, presence.where, None, sharing=sharing)
        return REACHED_ROW

    def _existence(
        self,
        relationship: ResolvedRelationship,
        operand: ResolvedPredicate | None,
        position: tuple[EntityIdentity, ...] | None,
        *,
        sharing: bool,
    ) -> CandidateExistence:
        """One `exists` per candidate branch, each operand its own lexical plan
        at that candidate's row."""
        if self._reaches_nothing(relationship):
            return CandidateExistence(())
        return CandidateExistence(
            tuple(
                CandidateOperand(
                    branch,
                    None
                    if operand is None
                    else self._planner.scope(
                        operand,
                        self._candidate_row(relationship, branch),
                        shares=sharing,
                        sharing=sharing,
                    ),
                )
                for branch in self._candidates(relationship, position=position).branches
            )
        )

    def _target_selection(
        self, narrow: ResolvedNarrow, row: _Row, *, sharing: bool, joined: bool
    ) -> TargetSelection:
        """``narrow``'s selection at one ``row`` of its target: a tag guard in a
        hierarchy table, the branch's own answer in a concrete table. A joined
        target's operand stands beside its guard; a candidate outside the
        selection answers false without one."""
        relationship = _narrowed_relationship(narrow)
        target = relationship.target
        selection: SubtypeSelection
        if target.inheritance is None:
            selection = True
        elif row.branch_concrete is not None:
            selection = row.branch_concrete in narrow.selection
        else:
            planner = self._planner
            root = _entity_view(planner.facet, target.identity).root
            layout = _table_layout(planner.storage, planner.facet, root)
            selection = _TagPredicate(_tag_column(layout, root), narrow.selection)
        operand = narrow.operand
        scope = (
            None
            if operand is None or (selection is False and not joined)
            else self._planner.scope(operand, row, shares=False, sharing=sharing)
        )
        return TargetSelection(selection, scope)

    def _branch_selection(self, narrow: ResolvedNarrow) -> SubtypeSelection:
        """A narrowing of this row: decided where its branch fixes a concrete,
        else its grouped branch predicate's tag guard."""
        concrete = self._row.branch_concrete
        if concrete is not None:
            return concrete in narrow.selection
        planner = self._planner
        tag = _plan_resolved_branch_narrow(
            planner.facet, planner.storage, self._row.entity, narrow.selection
        ).tag
        if tag is None:  # pragma: no cover - TPCS union branches always fix a concrete
            raise SqlGenError("a TPCS branch narrow requires a concrete branch scope")
        return tag

    def _candidates(
        self,
        relationship: ResolvedRelationship,
        *,
        position: tuple[EntityIdentity, ...] | None = None,
    ) -> RelationshipCandidatePlan:
        planner = self._planner
        return plan_relationship_candidates(
            relationship,
            position=position,
            meta=planner.meta,
            facet=planner.facet,
            storage=planner.storage,
        )

    def _candidate_row(
        self, relationship: ResolvedRelationship, branch: RelationshipCandidateBranch
    ) -> _Row:
        """A candidate's row; a concrete table of a table-per-concrete-subtype
        target fixes its own concrete."""
        planner = self._planner
        identity = branch.entity.identity
        target = relationship.target
        tpcs = target.inheritance is not None and not isinstance(
            _entity_view(planner.facet, target.identity).strategy, TablePerHierarchy
        )
        return _Row(
            branch.entity,
            _table_layout(planner.storage, planner.facet, identity),
            identity if tpcs else None,
        )

    def _source_row(self, source: int) -> _Row:
        planned = self._sources[source]
        return self._candidate_row(planned.relationship, planned.candidate)

    def _reaches_nothing(self, relationship: ResolvedRelationship) -> bool:
        target = relationship.target
        if target.inheritance is None:
            return False
        return not _entity_view(self._planner.facet, target.identity).concrete_subtypes


def _here(terminal: Terminal) -> UnsharedEvaluation:
    """An unshared evaluation at the current row itself."""
    if isinstance(terminal, ReachedRow):
        return _AT_ROW
    return UnsharedEvaluation(Continuation((), (terminal,)))


def _narrowed_relationship(narrow: ResolvedNarrow) -> ResolvedRelationship:
    target = narrow.target
    if not isinstance(target, RelatedObject):  # pragma: no cover - a reached target narrows here
        raise SqlGenError("a narrowing of the current row reaches no relationship")
    return target.relationship


def _hops(position: RelatedObject) -> tuple[ResolvedRelationship, ...]:
    hops: list[ResolvedRelationship] = []
    current: ObjectPosition = position
    while isinstance(current, RelatedObject):
        hops.append(current.relationship)
        current = current.source
    hops.reverse()
    return tuple(hops)


def _same_occurrence(first: ResolvedRelationship, second: ResolvedRelationship) -> bool:
    """One direction, endpoints, target family, and temporal visibility."""
    return (
        first.identity == second.identity
        and first.source.identity == second.source.identity
        and first.related.identity == second.related.identity
        and first.target.identity == second.target.identity
        and first.temporal_visibility == second.temporal_visibility
    )


def _operand_is_safe(operand: ResolvedPredicate, target: TableLayout) -> bool:
    """Whether a match's, narrowing's, or quantifier's ``operand``, resolved at
    ``target`` or at an element of a collection it holds, reads only that row
    or element without a projection that can fail.

    A further hop's scalar subquery asserts its cardinality and a quantifier,
    narrowing, or match evaluates an operand of its own over other rows, so an
    operand reaching any of them stays unshared.
    """
    match operand:
        case ResolvedAnd(operands=operands) | ResolvedOr(operands=operands):
            return all(_operand_is_safe(inner, target) for inner in operands)
        case ResolvedNot(operand=inner) | ResolvedGroup(operand=inner):
            return _operand_is_safe(inner, target)
        case (
            ResolvedComparison(member=member, position=CurrentObject())
            | ResolvedRange(member=member, position=CurrentObject())
            | ResolvedMembership(member=member, position=CurrentObject())
        ):
            return not _converts(member, target)
        case (
            ResolvedComparison(member=member, position=ScalarElement())
            | ResolvedRange(member=member, position=ScalarElement())
            | ResolvedMembership(member=member, position=ScalarElement())
        ):
            return is_text_compared(member.type)
        case (
            ResolvedConstant()
            | ResolvedStringMatch(position=CurrentObject() | ScalarElement())
            | ResolvedNullCheck(position=CurrentObject() | ScalarElement())
            | ResolvedPresence(position=CurrentObject(), where=None)
            | ResolvedNarrow(target=CurrentObject(), operand=None)
        ):
            return True
        case _:
            return False


def _converts(member: ResolvedPredicateMember, layout: TableLayout) -> bool:
    """Whether comparing ``member`` read from a row of ``layout``, or from a
    Value Object element, converts extracted document text to its type."""
    if is_text_compared(member.type):
        return False
    if isinstance(member, AttributeMetadata):
        return isinstance(layout.placement(member.identity), DocumentPath)
    return True


class _RootApplicability:
    """The owners of the document members a root row reads, at its layout."""

    __slots__ = ("_facet", "_layout")

    def __init__(self, facet: InheritanceFacet, layout: TableLayout) -> None:
        self._facet = facet
        self._layout = layout

    def predicate(self, predicate: ResolvedPredicate) -> Iterator[EntityIdentity]:
        """The predicate's reads at the root row itself; a narrowing of that
        row renders its operand there."""
        match predicate:
            case ResolvedAnd(operands=operands) | ResolvedOr(operands=operands):
                for operand in operands:
                    yield from self.predicate(operand)
            case ResolvedNot(operand=operand) | ResolvedGroup(operand=operand):
                yield from self.predicate(operand)
            case (
                ResolvedComparison(position=CurrentObject())
                | ResolvedRange(position=CurrentObject())
                | ResolvedMembership(position=CurrentObject())
                | ResolvedStringMatch(position=CurrentObject())
                | ResolvedNullCheck(position=CurrentObject())
            ):
                yield from self._member(predicate.member)
            case ResolvedQuantifier(position=CurrentObject(), collection=collection):
                if isinstance(collection, ScalarCollection):
                    yield from self._member(collection.member)
                elif not isinstance(collection, ResolvedRelationship):
                    yield from self._occurrence(collection)
            case ResolvedPresence(position=CurrentObject(), target=target) if not isinstance(
                target, ResolvedRelationship
            ):
                yield from self._occurrence(target)
            case ResolvedNarrow(target=CurrentObject(), operand=operand) if operand is not None:
                yield from self.predicate(operand)
            case _:
                pass

    def attribute(self, attribute: AttributeMetadata) -> EntityIdentity | None:
        placement = self._layout.placement(attribute.identity)
        return attribute.identity.entity if isinstance(placement, DocumentPath) else None

    def _member(self, member: ResolvedPredicateMember) -> Iterator[EntityIdentity]:
        if isinstance(member, AttributeMetadata):
            if owner := self.attribute(member):
                yield owner
            return
        yield from self._value_object_leaf(member)

    def _value_object_leaf(self, leaf: ValueObjectAttributeMetadata) -> Iterator[EntityIdentity]:
        identity = leaf.identity.value_object
        vo = _entity_view(self._facet, identity.entity).applicable_value_object(identity.path[0])
        if vo is not None and isinstance(self._layout.placement(vo.identity), DocumentPath):
            yield vo.identity.entity

    def _occurrence(self, occurrence: OccurrenceMetadata) -> Iterator[EntityIdentity]:
        identity = occurrence.identity
        vo = _entity_view(self._facet, identity.entity).applicable_value_object(identity.path[0])
        if vo is not None and isinstance(self._layout.placement(vo.identity), DocumentPath):
            yield vo.identity.entity
