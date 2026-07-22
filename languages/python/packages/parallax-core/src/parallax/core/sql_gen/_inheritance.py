"""Inheritance-family read PLANNING (m-sql "Metamodel-extension lowering").

Two `inheritance` names meet in this file, and they are not the same thing:

* ``parallax.core.inheritance`` — the METAMODEL module (`m-inheritance`), imported
  below as plain ``inheritance``. It answers model questions: a family's root, its
  effective concrete subtypes, its ancestry chain, its value-object superset.
* ``parallax.core.sql_gen._inheritance`` — THIS module, the family lane of the SQL
  compiler. It answers lowering questions: what a family read projects, which tag
  predicate it carries, how a table-per-concrete-subtype union splits into
  branches, and how a row's `familyVariant` is materialized. Siblings import it
  by its dotted path and alias each name down (`plan_inheritance_read as
  _plan_inheritance_read`), so ``inheritance.`` at a use site always means the
  metamodel module.

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

from parallax.core import inheritance
from parallax.core.descriptor import Attribute, Entity, Metamodel, ValueObject
from parallax.core.dialect import Dialect, LockMode
from parallax.core.op_algebra import Narrow, Operation, OrderKey
from parallax.core.sql_gen._context import ColumnScope as _ColumnScope
from parallax.core.sql_gen._context import SqlGenError


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

    ``tag_pairs`` is the WHOLE family's `(tagValue, concreteName)` mapping in
    `inheritance.effective_concrete_subtypes`' canonical alphabetical order —
    never the read's own resolved position, since a narrowed abstract read
    still projects the shared table's tag column and may observe any of them.
    A tuple of pairs rather than a `Mapping` is what keeps `CompiledRead`
    hashable and its `repr` stable.
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
# Position and superset resolution.                                            #
# --------------------------------------------------------------------------- #
def narrow_effective_set(meta: Metamodel, to: Sequence[str]) -> tuple[str, ...]:
    """A narrow's resolved, canonically alphabetical effective concrete set.

    `validate_operation` runs upstream and guarantees the resolved set is
    non-empty and a subset of the active position (`m-op-algebra` "the four-step
    validation rule") before this compiler ever sees the operation, so this need
    only resolve and canonicalize — never re-validate.
    """
    resolved: set[str] = set()
    for name in to:
        resolved.update(inheritance.effective_concrete_subtypes(meta, name))
    return tuple(sorted(resolved))


def superset_columns(meta: Metamodel, position: Sequence[str]) -> list[tuple[Attribute, str]]:
    """The stable superset column list for a read over ``position`` (m-sql
    *Abstract-read projection* / *union-all lowering*): each ancestor's own
    attributes in ancestry order, then each position concrete's own attributes in
    canonical alphabetical order — paired with the declaring entity's name so a
    table-per-concrete-subtype branch can tell which columns it physically owns.
    """
    columns: list[tuple[Attribute, str]] = []
    for ancestor in inheritance.ancestor_chain(meta, position):
        columns.extend((attribute, ancestor.name) for attribute in ancestor.attributes)
    for name in sorted(position):
        entity = meta.entity(name)
        columns.extend((attribute, entity.name) for attribute in entity.attributes)
    return columns


def superset_value_objects(meta: Metamodel, position: Sequence[str]) -> list[ValueObject]:
    """The value objects reachable from ``position``, same ordering rule as
    :func:`superset_columns` (ancestry prefix, then alphabetical own blocks) —
    the shared `inheritance.superset_value_objects` resolution (also used by
    `m-snapshot-read`'s row-decoding superset)."""
    return inheritance.superset_value_objects(meta, position)


# --------------------------------------------------------------------------- #
# Tag values and the DEFERRED tag guard.                                       #
# --------------------------------------------------------------------------- #
def tag_value(meta: Metamodel, concrete_name: str) -> str:
    concrete = meta.entity(concrete_name)
    if concrete.inheritance is None or concrete.inheritance.tag_value is None:
        raise SqlGenError(  # pragma: no cover - a validated TPH concrete always declares one
            f"{concrete_name}: table-per-hierarchy concrete subtype declares no tagValue"
        )
    return concrete.inheritance.tag_value


def tph_tag_column(root: Entity) -> str:
    """A table-per-hierarchy root's declared tag column."""
    assert root.inheritance is not None  # a family root always carries its own block
    tag_col = root.inheritance.tag_column
    if tag_col is None:  # pragma: no cover - a validated TPH root always declares one
        raise SqlGenError(f"{root.name}: table-per-hierarchy root declares no tag column")
    return tag_col


def family_tag_pairs(meta: Metamodel, root: Entity) -> tuple[tuple[str, str], ...]:
    """The WHOLE family's `(tagValue, concreteName)` pairs, in
    `effective_concrete_subtypes`' canonical alphabetical order.

    Deliberately the family's set, not the read's resolved position: a narrowed
    abstract read still projects the shared table's raw tag column, and the
    mapping that interprets it is a property of the family, not of the narrow
    (`m-inheritance-012`).
    """
    return tuple(
        (tag_value(meta, name), name)
        for name in inheritance.effective_concrete_subtypes(meta, root.name)
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
    position: tuple[str, ...]

    @property
    def kind(self) -> TagKind:
        """`=` for a single concrete, `in` for several (m-sql *Tag-predicate
        selection*)."""
        return "eq" if len(self.position) == 1 else "in"


def tag_guard(
    scope: _ColumnScope, meta: Metamodel, tag: TagPredicate
) -> tuple[str, tuple[object, ...]]:
    """PLAN the tag-predicate guard for ``tag`` (m-sql *Tag-predicate
    selection*): `t0.<tag> = ?` for one concrete, `t0.<tag> in (?, …)` for several
    — the `in` list in the position's already-canonical alphabetical order, so its
    tag values follow suit.

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
    tag_values = [tag_value(meta, name) for name in tag.position]
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
    columns: Sequence[tuple[Attribute, str]],
    tag_column: str | None,
    value_objects: Sequence[ValueObject],
) -> tuple[str, tuple[object, ...]]:
    """The m-sql projection SLOT ORDER for a single-table family read, once.

    * **Slot 1** — the resolved position's stable superset columns, each through
      the dialect's own select-list expression (a `bytes` column projects
      `encode(col, ?)`, which is where a projection BIND comes from and why
      projection binds lead the statement's bind tuple).
    * **Slot 2** (m-sql resolved Q6) — the raw tag column, projected iff the
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
    for attribute, _owner in columns:
        expr, extra = dialect.project(alias, attribute.column, attribute.type)
        exprs.append(expr)
        binds.extend(extra)
    if tag_column is not None:
        exprs.append(dialect.qualified(alias, tag_column))
    exprs.extend(dialect.qualified(alias, vo.storage_column) for vo in value_objects)
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
    columns: tuple[tuple[Attribute, str], ...]
    projected_tag_column: str | None
    value_objects: tuple[ValueObject, ...]
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
    spans :func:`parallax.core.inheritance.family_attributes` rather than only
    that entity's own declared attributes), matching the table-per-hierarchy
    concrete-target form.
    """

    table: str
    columns: tuple[tuple[Attribute, str], ...]
    value_objects: tuple[ValueObject, ...]
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
    columns: tuple[tuple[Attribute, bool], ...]

    def projection(self, dialect: Dialect, alias: str) -> tuple[str, tuple[object, ...]]:
        exprs: list[str] = []
        binds: list[object] = []
        for attribute, owned in self.columns:
            if owned:
                expr, extra = dialect.project(alias, attribute.column, attribute.type)
                exprs.append(expr)
                binds.extend(extra)
            else:
                cast_type = dialect.null_cast(attribute.type, attribute.max_length)
                exprs.append(f"cast(null as {cast_type}) {attribute.column}")
        # Slot 3 (the settled TPH/TPCS asymmetry): TPCS projects the variant NAME
        # literal per branch directly — there is no tag column to derive it from.
        exprs.append(f"'{self.name}' family_variant")
        return ", ".join(exprs), tuple(binds)


@dataclass(frozen=True, slots=True)
class TpcsUnionPlan:
    """A position resolving to two or more concretes: canonical `union all`, one
    branch per concrete in alphabetical order, every branch restarting its own
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
    entity: Entity,
    predicate: Operation,
    distinct: bool,
    order_keys: tuple[OrderKey, ...],
    limit: int | None,
    meta: Metamodel,
    target: str,
    instance_form: bool,
    lock: LockMode | None,
) -> TphPlan | TpcsSinglePlan | TpcsUnionPlan:
    """Plan an inheritance-family read for its declared strategy (m-inheritance
    admits exactly two; a third is rejected long before SQL, by the model-aware
    descriptor validator).

    ``instance_form`` is the object lane (`result_form == "instance"`), the only
    thing about the read's consumption lane the family projection depends on. The
    clause-tail arguments are here rather than at the assembly site because the
    union lane must REFUSE them, and its two refusals have a fixed relative order
    that a caller-side check would silently reorder.
    """
    root = inheritance.family_root(meta, entity)
    assert root.inheritance is not None  # a family root always carries its own block
    strategy = root.inheritance.strategy
    if strategy == "table-per-hierarchy":
        return _plan_tph_read(entity, root, predicate, meta, target, instance_form)
    if strategy == "table-per-concrete-subtype":
        return _plan_tpcs_read(
            predicate, distinct, order_keys, limit, meta, target, instance_form, lock
        )
    # m-inheritance admits only the two strategies above; a descriptor failing to
    # declare one is refused by the model-aware validator long before a read
    # reaches this compiler.
    raise SqlGenError(
        f"{root.name}: unrecognized inheritance strategy {strategy!r}"
    )  # pragma: no cover


def _plan_tph_read(
    entity: Entity,
    root: Entity,
    predicate: Operation,
    meta: Metamodel,
    target: str,
    instance_form: bool,
) -> TphPlan:
    tag_col = tph_tag_column(root)
    abstract_target = entity.inheritance is not None and entity.inheritance.role in (
        "root",
        "abstract-subtype",
    )

    if isinstance(predicate, Narrow):
        position = narrow_effective_set(meta, predicate.to)
        inner = predicate.operand
        guarded = True
    else:
        position = tuple(inheritance.effective_concrete_subtypes(meta, target))
        inner = predicate
        # Only an UNTOUCHED abstract root queries the whole family, so only it
        # carries no tag predicate at all.
        guarded = not (entity.inheritance is not None and entity.inheritance.role == "root")

    table = inheritance.effective_table(meta, root)
    if table is None:  # pragma: no cover - validated TPH roots always declare one
        raise SqlGenError(f"{root.name}: table-per-hierarchy root declares no table")

    # `familyVariant` rides the SAME condition as the slot-2 tag projection: the
    # transform reads the column this read projects, or there is no column to read
    # and nothing to materialize.
    transform: RowTransform = (
        _TagTransform(tag_col, family_tag_pairs(meta, root))
        if abstract_target
        else IDENTITY_TRANSFORM
    )
    return TphPlan(
        table=table,
        columns=tuple(superset_columns(meta, position)),
        projected_tag_column=tag_col if abstract_target else None,
        value_objects=tuple(superset_value_objects(meta, position)) if instance_form else (),
        inner=inner,
        tag=TagPredicate(tag_col, position) if guarded else None,
        transform=transform,
    )


def _plan_tpcs_read(
    predicate: Operation,
    distinct: bool,
    order_keys: tuple[OrderKey, ...],
    limit: int | None,
    meta: Metamodel,
    target: str,
    instance_form: bool,
    lock: LockMode | None,
) -> TpcsSinglePlan | TpcsUnionPlan:
    """Table-per-concrete-subtype (m-sql "Inheritance — table-per-concrete-subtype
    lowering"). Unlike table-per-hierarchy, the single-vs-several split is the ONLY
    thing that decides `familyVariant` here — there is no table-per-concrete-subtype
    analogue of the abstract-`targetEntity` slot-2 rule, because a resolved single
    concrete has no shared table to discriminate and no sibling branch to
    distinguish it from (m-sql, explicit).
    """
    if isinstance(predicate, Narrow):
        position = narrow_effective_set(meta, predicate.to)
        inner = predicate.operand
    else:
        position = tuple(inheritance.effective_concrete_subtypes(meta, target))
        inner = predicate

    if len(position) == 1:
        concrete = meta.entity(position[0])
        if concrete.table is None:  # pragma: no cover - a validated TPCS concrete always has one
            raise SqlGenError(
                f"{concrete.name}: table-per-concrete-subtype subtype declares no table"
            )
        return TpcsSinglePlan(
            table=concrete.table,
            columns=tuple(superset_columns(meta, position)),
            value_objects=tuple(superset_value_objects(meta, position)) if instance_form else (),
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
    # Instance-form (ledger D-22, COR-3 Phase 8 part C): a VO-FREE family's
    # union-all lowering is BYTE-IDENTICAL to its row-form sibling (no slot-4
    # value-object columns to add either way — m-inheritance-109 witnesses
    # this exact shape, verified against m-inheritance-052's own golden). A
    # VO-BEARING family's union-all instance-form projection remains
    # genuinely unwitnessed (no corpus golden authors what a value-object
    # document column looks like split across `union all` branches whose
    # owning concrete may not even declare it) — narrowed refusal, never a
    # blanket one, and never a guessed lowering with no witness to check it
    # against.
    if instance_form and superset_value_objects(meta, position):
        raise SqlGenError(
            "instance-form (value-object document) projection over a table-per-concrete-"
            "subtype union-all read has no goldened lowering yet for a VALUE-OBJECT-"
            "BEARING family (the VO-free shape is witnessed, m-inheritance-109)"
        )

    columns = superset_columns(meta, position)
    branches: list[TpcsBranchPlan] = []
    for name in position:
        concrete = meta.entity(name)
        if concrete.table is None:  # pragma: no cover - a validated TPCS concrete always has one
            raise SqlGenError(f"{name}: table-per-concrete-subtype subtype declares no table")
        owned = {ancestor.name for ancestor in inheritance.ancestor_chain(meta, (name,))} | {name}
        branches.append(
            TpcsBranchPlan(
                name=name,
                table=concrete.table,
                columns=tuple((attribute, owner in owned) for attribute, owner in columns),
            )
        )
    # Every branch projects its own `family_variant` literal, so the transform is
    # a plain rename — no tag map, no metamodel lookup.
    return TpcsUnionPlan(
        branches=tuple(branches), inner=inner, transform=_LiteralTransform("family_variant")
    )


def plan_branch_narrow(meta: Metamodel, entity: Entity, narrow: Narrow) -> BranchNarrowPlan:
    """Plan a mid-predicate `narrow` (m-sql "Grouped branch predicates").

    The branch's own operand composes with its own tag guard via `and` at the
    caller, which lowers the operand first so its binds precede the guard's.
    """
    root = inheritance.family_root(meta, entity)
    if root.inheritance is None or root.inheritance.strategy != "table-per-hierarchy":
        raise SqlGenError(
            "a narrow nested inside and/or/not/group over a table-per-concrete-subtype "
            "family has no goldened lowering yet"
        )
    return BranchNarrowPlan(
        operand=narrow.operand,
        tag=TagPredicate(tph_tag_column(root), narrow_effective_set(meta, narrow.to)),
    )
