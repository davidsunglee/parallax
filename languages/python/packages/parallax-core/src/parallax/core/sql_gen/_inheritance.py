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
carries its read's own operation as an un-lowered node, and the tag guard as its
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
over the node union — the one operation node it inspects is a TOP-LEVEL `narrow`,
and only to resolve the read's position, never to descend into it. **Nothing here
binds**, and that is now checked rather than asserted: lowering state reaches
this module through exactly one signature, :func:`tag_guard`, and it arrives as a
:class:`~parallax.core.sql_gen._context.ColumnScope` — a protocol carrying
`own_column` and nothing else, so `bind`, `binds`, and `next_alias` are not
merely unused here, they are unreachable.

The read's queried **position** is the resolved effective concrete-subtype set
the whole read targets: a top-level `narrow` (the read's ENTIRE predicate after
peeling result-shaping directives) replaces `targetEntity`'s own position with
its resolved `to` set; a `narrow` reached anywhere else (nested inside
and/or/not/group) is a local BRANCH guard and never changes the read's own
position (`m-inheritance-015`'s `or` of two narrowed branches is the corpus
witness — the projection and the whole-family "no tag" rule stay keyed to
`targetEntity`, only each branch's own tag guard is injected).

Named without a leading underscore because the MODULE carries the privacy, the
package convention `_context` already established: importers alias to the
module-private spelling.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, cast

from parallax.core.dialect import Dialect, LockMode
from parallax.core.inheritance import (
    InheritanceEntityView,
    InheritanceFacet,
    InheritancePositionView,
)
from parallax.core.metamodel import (
    AbstractRoot,
    AbstractSubtype,
    AttributeMetadata,
    EntityIdentity,
    EntityMetadata,
    RelativeEntityReference,
    TablePerHierarchy,
    ValueObjectMetadata,
    resolve_entity_reference,
)
from parallax.core.op_algebra import Narrow, Operation, OrderKey
from parallax.core.sql_gen._context import ColumnScope as _ColumnScope
from parallax.core.sql_gen._context import SqlGenError


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


def position_table(facet: InheritanceFacet, entity: EntityIdentity) -> str:
    """The one physical table a read of ``entity``'s own rows selects from.

    Row-bearing by construction at every call site: a table-per-hierarchy
    position reads the root's shared table and a concrete subtype reads its own,
    so only a table-per-concrete-subtype abstract position has none — and that
    position never reaches a single-table read, it fans out to its concretes.
    """
    container = entity_view(facet, entity).container
    if container is None:  # pragma: no cover - an abstract position never reads one table
        raise SqlGenError(f"{entity.canonical}: this inheritance position declares no table")
    return container.name


def tag_column(view: InheritanceEntityView) -> str:
    """The table-per-hierarchy tag column ``view``'s family discriminates by."""
    column = view.tag_column
    if column is None:  # pragma: no cover - every table-per-hierarchy view carries one
        raise SqlGenError(f"{view.entity.canonical}: this family declares no tag column")
    return column


def tag_value(facet: InheritanceFacet, concrete: EntityIdentity) -> str:
    """The value ``concrete``'s rows carry in its family's shared tag column."""
    value = entity_view(facet, concrete).tag_value
    if value is None:  # pragma: no cover - a validated TPH concrete always declares one
        raise SqlGenError(
            f"{concrete.canonical}: table-per-hierarchy concrete subtype declares no tagValue"
        )
    return value


# --------------------------------------------------------------------------- #
# Row transforms: how a read's own `familyVariant` is materialized onto each   #
# observed row (m-case-format / m-conformance-adapter). Table-per-hierarchy    #
# derives it from the projected raw tag column, table-per-concrete-subtype     #
# reads it straight from the projected literal column, and every other read    #
# carries none.                                                               #
#                                                                              #
# A UNION of three frozen forms rather than one class with a `kind` tag and    #
# optional fields: every field of every form is required, so there is no       #
# illegal state to assert against at apply time, and each form's `apply` is    #
# total — which is what lets `CompiledRead.transform_row` be a single          #
# structural delegation with no dispatch. This is the module's own documented  #
# style (the `m-op-algebra` node union), and each form pickles, compares, and  #
# reprs as a plain dataclass with no `__reduce__` and no stored callable.      #
#                                                                              #
# The three forms keep their module-private spelling: no sibling names them —  #
# `_compile` reaches them only through :data:`RowTransform` (the declared type #
# of `CompiledRead._transform`) and :data:`IDENTITY_TRANSFORM`. Those two are  #
# this module's published surface for the family; the forms themselves are     #
# construction details of the planners below.                                  #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class _IdentityTransform:
    """No `familyVariant` to materialize: a non-family read, a concrete-target
    table-per-hierarchy read, or a table-per-concrete-subtype read whose
    position resolved to a single concrete. Still returns a FRESH dict, so
    every caller may mutate the result regardless of which form it got."""

    def apply(self, row: Mapping[str, object]) -> dict[str, object]:
        return dict(row)


@dataclass(frozen=True, slots=True)
class _TagTransform:
    """Table-per-hierarchy: pop the framework-owned raw tag column (it never
    reaches the caller) and map its value to the declaring concrete's name.

    ``tag_pairs`` is the WHOLE family's `(tagValue, concreteName)` mapping in the
    facet's canonical concrete-subtype order — never the read's own resolved
    position, since a narrowed abstract read still projects the shared table's
    tag column and may observe any of them. A tuple of pairs rather than a
    `Mapping` is what keeps `CompiledRead` hashable and its `repr` stable.
    """

    column: str
    tag_pairs: tuple[tuple[str, str], ...]

    def apply(self, row: Mapping[str, object]) -> dict[str, object]:
        materialized = dict(row)
        raw = materialized.pop(self.column)
        materialized["familyVariant"] = dict(self.tag_pairs)[cast("str", raw)]
        return materialized


@dataclass(frozen=True, slots=True)
class _LiteralTransform:
    """Table-per-concrete-subtype `union all`: rename the per-branch projected
    subtype-name literal column — there is no tag column to derive it from."""

    column: str

    def apply(self, row: Mapping[str, object]) -> dict[str, object]:
        materialized = dict(row)
        materialized["familyVariant"] = materialized.pop(self.column)
        return materialized


RowTransform = _IdentityTransform | _TagTransform | _LiteralTransform

# The identity form is stateless, so one shared instance serves every read that
# carries no `familyVariant`; equality is structural, so a copied/unpickled
# `CompiledRead` still compares equal to one holding this very object.
IDENTITY_TRANSFORM = _IdentityTransform()


# --------------------------------------------------------------------------- #
# Position resolution.                                                         #
# --------------------------------------------------------------------------- #
def narrow_position(
    facet: InheritanceFacet, owner: EntityIdentity, to: Sequence[str]
) -> InheritancePositionView:
    """The projection a `narrow`'s authored ``to`` list denotes.

    Each authored name is resolved relative to the queried Entity's own
    namespace, exactly as any other bare model reference is, and the facet
    resolves the members' union to the position's canonical effective
    concrete-subtype set and its projection supersets.

    `validate_operation` runs upstream and guarantees the resolved set is
    non-empty and a subset of the active position (`m-op-algebra` "the four-step
    validation rule") before this compiler ever sees the operation, so this need
    only resolve — never re-validate.
    """
    members = tuple(resolve_entity_reference(owner, RelativeEntityReference(name)) for name in to)
    position = facet.position(members)
    if position is None:
        raise SqlGenError(
            f"narrow to {sorted(identity.canonical for identity in members)} names an entity "
            "the model does not declare, or spans more than one inheritance family"
        )
    return position


# --------------------------------------------------------------------------- #
# The DEFERRED tag guard.                                                      #
# --------------------------------------------------------------------------- #
def family_tag_pairs(facet: InheritanceFacet, root: EntityIdentity) -> tuple[tuple[str, str], ...]:
    """The WHOLE family's `(tagValue, concreteName)` pairs, in the facet's
    canonical concrete-subtype order.

    Deliberately the family's set, not the read's resolved position: a narrowed
    abstract read still projects the shared table's raw tag column, and the
    mapping that interprets it is a property of the family, not of the narrow
    (`m-inheritance-012`).
    """
    return tuple(
        (tag_value(facet, concrete), concrete.name)
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
def _single_table_projection(
    dialect: Dialect,
    alias: str,
    columns: Sequence[AttributeMetadata],
    projected_tag_column: str | None,
    value_objects: Sequence[ValueObjectMetadata],
) -> tuple[str, tuple[object, ...]]:
    """The m-sql projection SLOT ORDER for a single-table family read, once.

    * **Slot 1** — the resolved position's stable superset columns, each through
      the dialect's own select-list expression (a `bytes` column projects
      `encode(col, ?)`, which is where a projection BIND comes from and why
      projection binds lead the statement's bind tuple).
    * **Slot 2** — the raw tag column, projected iff the
      read's OWN `targetEntity` is abstract, NEVER derived from the resolved
      position. ``None`` is "this read projects no tag": a table-per-hierarchy
      read whose own `targetEntity` is concrete, and every
      table-per-concrete-subtype single-concrete read, which reads a table that
      carries no tag column at all.
    * **Slot 4** — the value-object document columns, LAST among all columns, in
      declared order.

    Both single-table family plans render through here instead of each spelling
    the order out. That order is contractual, so two copies means a future
    slot-order correction can be applied to one and missed in the other — the
    duplication's real cost, well before its size. :class:`TpcsBranchPlan`
    deliberately does NOT share it: a `union all` branch projects `cast(null as
    …)` placeholders for the superset columns it does not own plus a slot-3
    variant-name literal, which is a genuinely different list rather than this
    one minus a slot.
    """
    exprs: list[str] = []
    binds: list[object] = []
    for attribute in columns:
        expr, extra = dialect.project(alias, attribute.storage.name, attribute.type)
        exprs.append(expr)
        binds.extend(extra)
    if projected_tag_column is not None:
        exprs.append(dialect.qualified(alias, projected_tag_column))
    exprs.extend(dialect.qualified(alias, member.storage.name) for member in value_objects)
    return ", ".join(exprs), tuple(binds)


@dataclass(frozen=True, slots=True)
class TphPlan:
    """Table-per-hierarchy: one shared single-table SELECT (m-sql "Inheritance —
    table-per-hierarchy lowering").

    The tag PREDICATE (:attr:`tag`) is keyed purely to the resolved position's
    SIZE — one concrete lowers to `=` whether reached by a direct concrete
    `targetEntity` or a narrow, several lower to `in`, and only an untouched
    abstract-**root** `targetEntity` (no top-level narrow at all) carries no tag
    predicate at all, which is ``None``. The raw tag column PROJECTION
    (:attr:`projected_tag_column`, slot 2) is instead keyed to whether
    `targetEntity` itself is abstract — independent of the narrow's resolved
    cardinality (`m-inheritance-012`: `Animal` narrowed to the single concrete
    `Dog` still projects `t0.kind` and still carries `familyVariant`, because the
    caller queried the polymorphic `Animal` position). These are deliberately two
    different conditions, and each is spelled as its OWN optional so neither can
    be read off the other: a bare abstract root projects the tag it does not
    guard on, and a concrete target guards on the tag it does not project.
    """

    table: str
    columns: tuple[AttributeMetadata, ...]
    projected_tag_column: str | None
    value_objects: tuple[ValueObjectMetadata, ...]
    inner: Operation
    tag: TagPredicate | None
    transform: RowTransform

    def projection(self, dialect: Dialect, alias: str) -> tuple[str, tuple[object, ...]]:
        """The select list and its ordered projection binds, against ``alias``."""
        return _single_table_projection(
            dialect, alias, self.columns, self.projected_tag_column, self.value_objects
        )


@dataclass(frozen=True, slots=True)
class TpcsSinglePlan:
    """A table-per-concrete-subtype read resolving to exactly one concrete: an
    ordinary single-table read of that subtype's own table, no tag, no union, no
    `familyVariant` — attribute resolution still widens across the family (the
    RESOLUTION SCOPE's entity stays the read's own `targetEntity`, e.g. an
    abstract position narrowed down to this one concrete, so its attribute search
    spans the family's superset rather than only that entity's own declared
    attributes), matching the table-per-hierarchy concrete-target form.
    """

    table: str
    columns: tuple[AttributeMetadata, ...]
    value_objects: tuple[ValueObjectMetadata, ...]
    inner: Operation
    transform: RowTransform

    def projection(self, dialect: Dialect, alias: str) -> tuple[str, tuple[object, ...]]:
        """The select list and its ordered projection binds, against ``alias``.

        Slot 2 is always absent: this reads the resolved concrete's OWN table,
        which declares no tag column to project.
        """
        return _single_table_projection(dialect, alias, self.columns, None, self.value_objects)


@dataclass(frozen=True, slots=True)
class TpcsBranchPlan:
    """One `union all` branch: its own table, and the shared superset column list
    paired with whether THIS branch physically owns each column."""

    name: str
    table: str
    columns: tuple[tuple[AttributeMetadata, bool], ...]

    def projection(self, dialect: Dialect, alias: str) -> tuple[str, tuple[object, ...]]:
        exprs: list[str] = []
        binds: list[object] = []
        for attribute, owned in self.columns:
            if owned:
                expr, extra = dialect.project(alias, attribute.storage.name, attribute.type)
                exprs.append(expr)
                binds.extend(extra)
            else:
                cast_type = dialect.null_cast(attribute.type, attribute.max_length)
                exprs.append(f"cast(null as {cast_type}) {attribute.storage.name}")
        # Slot 3 (the settled TPH/TPCS asymmetry): TPCS projects the variant NAME
        # literal per branch directly — there is no tag column to derive it from.
        exprs.append(f"'{self.name}' family_variant")
        return ", ".join(exprs), tuple(binds)


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
    """

    branches: tuple[TpcsBranchPlan, ...]
    inner: Operation
    transform: RowTransform


@dataclass(frozen=True, slots=True)
class BranchNarrowPlan:
    """A `narrow` reached MID-predicate (nested inside and/or/not/group) — a
    **grouped branch predicate** (m-sql "Grouped branch predicates"). Carries the
    branch's own un-lowered ``operand`` and the inputs its tag guard needs; the
    caller lowers the operand FIRST, then guards.
    """

    operand: Operation
    tag: TagPredicate


# --------------------------------------------------------------------------- #
# Planning.                                                                    #
# --------------------------------------------------------------------------- #
def plan_inheritance_read(
    entity: EntityMetadata,
    predicate: Operation,
    distinct: bool,
    order_keys: tuple[OrderKey, ...],
    limit: int | None,
    facet: InheritanceFacet,
    instance_form: bool,
    lock: LockMode | None,
) -> TphPlan | TpcsSinglePlan | TpcsUnionPlan:
    """Plan an inheritance-family read for its family's declared strategy.

    Only an inheritance participant reaches here, and m-inheritance admits
    exactly two strategies, so the table-per-hierarchy test decides between them
    outright.

    ``instance_form`` is the object lane (`result_form == "instance"`), the only
    thing about the read's consumption lane the family projection depends on. The
    clause-tail arguments are here rather than at the assembly site because the
    union lane must REFUSE them, and its two refusals have a fixed relative order
    that a caller-side check would silently reorder.
    """
    view = entity_view(facet, entity.identity)
    position, inner, narrowed = _read_position(view, predicate, facet)
    if isinstance(view.strategy, TablePerHierarchy):
        return _plan_tph_read(entity, view, position, inner, facet, instance_form, narrowed)
    return _plan_tpcs_read(position, inner, distinct, order_keys, limit, facet, instance_form, lock)


def _read_position(
    view: InheritanceEntityView, predicate: Operation, facet: InheritanceFacet
) -> tuple[InheritancePositionView, Operation, bool]:
    """The read's queried position, the predicate left to lower under it, and
    whether a top-level `narrow` produced it.

    A TOP-LEVEL `narrow` — the read's entire predicate once result-shaping
    directives are peeled — replaces `targetEntity`'s own position with its
    resolved `to` set and contributes its operand; anything else leaves the
    Entity's own position standing and is lowered whole.
    """
    if isinstance(predicate, Narrow):
        return narrow_position(facet, view.entity, predicate.to), predicate.operand, True
    return view, predicate, False


def _plan_tph_read(
    entity: EntityMetadata,
    view: InheritanceEntityView,
    position: InheritancePositionView,
    inner: Operation,
    facet: InheritanceFacet,
    instance_form: bool,
    narrowed: bool,
) -> TphPlan:
    tag_col = tag_column(view)
    abstract_target = isinstance(entity.inheritance, (AbstractRoot, AbstractSubtype))
    # Only an UNTOUCHED abstract root queries the whole family, so only it carries
    # no tag predicate at all.
    guarded = narrowed or not isinstance(entity.inheritance, AbstractRoot)

    # `familyVariant` rides the SAME condition as the slot-2 tag projection: the
    # transform reads the column this read projects, or there is no column to read
    # and nothing to materialize.
    transform: RowTransform = (
        _TagTransform(tag_col, family_tag_pairs(facet, view.root))
        if abstract_target
        else IDENTITY_TRANSFORM
    )
    return TphPlan(
        table=position_table(facet, view.entity),
        columns=tuple(position.superset_attributes),
        projected_tag_column=tag_col if abstract_target else None,
        value_objects=tuple(position.superset_value_objects) if instance_form else (),
        inner=inner,
        tag=TagPredicate(tag_col, tuple(position.concrete_subtypes)) if guarded else None,
        transform=transform,
    )


def _plan_tpcs_read(
    position: InheritancePositionView,
    inner: Operation,
    distinct: bool,
    order_keys: tuple[OrderKey, ...],
    limit: int | None,
    facet: InheritanceFacet,
    instance_form: bool,
    lock: LockMode | None,
) -> TpcsSinglePlan | TpcsUnionPlan:
    """Table-per-concrete-subtype (m-sql "Inheritance — table-per-concrete-subtype
    lowering"). Unlike table-per-hierarchy, the single-vs-several split is the ONLY
    thing that decides `familyVariant` here — there is no table-per-concrete-subtype
    analogue of the abstract-`targetEntity` slot-2 rule, because a resolved single
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
        return TpcsSinglePlan(
            table=position_table(facet, concretes[0]),
            columns=tuple(position.superset_attributes),
            value_objects=tuple(position.superset_value_objects) if instance_form else (),
            inner=inner,
            # A single resolved concrete projects neither a tag column nor a
            # variant literal — the settled asymmetry with table-per-hierarchy,
            # whose abstract target keeps its tag however narrow the position
            # resolves.
            transform=IDENTITY_TRANSFORM,
        )

    if distinct or order_keys or limit is not None or lock is not None:
        raise SqlGenError(
            "distinct / orderBy / limit / a read-lock suffix over a table-per-concrete-"
            "subtype union-all read (2+ effective concretes) has no goldened lowering yet"
        )
    # Instance-form: a VO-FREE family's
    # union-all lowering is BYTE-IDENTICAL to its row-form sibling (no slot-4
    # value-object columns to add either way — m-inheritance-109 witnesses
    # this exact shape, verified against m-inheritance-052's own golden). A
    # VO-BEARING family's union-all instance-form projection remains
    # genuinely unwitnessed (no corpus golden authors what a value-object
    # document column looks like split across `union all` branches whose
    # owning concrete may not even declare it) — narrowed refusal, never a
    # blanket one, and never a guessed lowering with no witness to check it
    # against.
    if instance_form and position.superset_value_objects:
        raise SqlGenError(
            "instance-form (value-object document) projection over a table-per-concrete-"
            "subtype union-all read has no goldened lowering yet for a VALUE-OBJECT-"
            "BEARING family (the VO-free shape is witnessed, m-inheritance-109)"
        )

    columns = position.superset_attributes
    branches: list[TpcsBranchPlan] = []
    for concrete in concretes:
        owned = frozenset(entity_view(facet, concrete).ancestry)
        branches.append(
            TpcsBranchPlan(
                name=concrete.name,
                table=position_table(facet, concrete),
                # A superset Attribute names its DECLARING position, and a branch
                # physically owns exactly the columns its own ancestry declares —
                # which the facet's chain already ends with the concrete itself.
                columns=tuple(
                    (attribute, attribute.identity.entity in owned) for attribute in columns
                ),
            )
        )
    # Every branch projects its own `family_variant` literal, so the transform is
    # a plain rename — no tag map, no metamodel lookup.
    return TpcsUnionPlan(
        branches=tuple(branches), inner=inner, transform=_LiteralTransform("family_variant")
    )


def plan_branch_narrow(
    facet: InheritanceFacet, entity: EntityMetadata, narrow: Narrow
) -> BranchNarrowPlan:
    """Plan a mid-predicate `narrow` (m-sql "Grouped branch predicates").

    The branch's own operand composes with its own tag guard via `and` at the
    caller, which lowers the operand first so its binds precede the guard's.
    """
    view = entity_view(facet, entity.identity)
    if not isinstance(view.strategy, TablePerHierarchy):
        raise SqlGenError(
            "a narrow nested inside and/or/not/group over a table-per-concrete-subtype "
            "family has no goldened lowering yet"
        )
    position = narrow_position(facet, entity.identity, narrow.to)
    return BranchNarrowPlan(
        operand=narrow.operand,
        tag=TagPredicate(tag_column(view), tuple(position.concrete_subtypes)),
    )
