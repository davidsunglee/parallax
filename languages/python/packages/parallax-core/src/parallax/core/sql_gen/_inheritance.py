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
carries its family read's `inner` operation as an un-lowered node, and the tag
guard as a fragment plus its bind VALUES. `_compile` constructs the statement's
:class:`~parallax.core.sql_gen._context.Ctx`, lowers `inner` through it, and only
then appends the guard's binds. That split is what keeps the m-sql "Grouped
branch predicates" ordering (binds read branch-predicate-first, then tag)
structural rather than contingent.

Two rules make it checkable by reading this file alone. **Nothing here lowers a
predicate**: the module imports no predicate lowering, and contains no `match`
over the node union — the one operation node it inspects is a TOP-LEVEL `narrow`,
and only to resolve the read's position, never to descend into it. **Nothing here
binds**: `Ctx` appears in exactly one signature, :func:`tag_guard`, which reads it
(`own_column`) and returns the fragment plus its bind VALUES; no function in this
module touches `ctx.binds`, `ctx.bind`, or `ctx.next_alias`.

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
from typing import cast

from parallax.core import inheritance
from parallax.core.descriptor import Attribute, Entity, Metamodel, ValueObject
from parallax.core.dialect import Dialect, LockMode
from parallax.core.op_algebra import Narrow, Operation, OrderKey
from parallax.core.sql_gen._context import Ctx as _Ctx
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


def tag_guard(
    ctx: _Ctx, meta: Metamodel, tag_col: str, tag_kind: str, position: Sequence[str]
) -> tuple[str, tuple[object, ...]]:
    """PLAN the tag-predicate guard for ``position`` (m-sql *Tag-predicate
    selection*): `t0.<tag> = ?` for one concrete, `t0.<tag> in (?, …)` for several
    — the `in` list in ``position``'s already-canonical alphabetical order, so its
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

    The tag column is THIS context's own column, so it renders through
    :meth:`Ctx.own_column` like every other one: the framework-owned tag is no
    more alias-qualified than a declared attribute is. In every read context
    ``unaliased`` is ``False`` and this is exactly ``qualified(alias, tag_col)``,
    so no emitted read SQL depends on the distinction — it exists so the leak
    cannot reopen from a caller that arrives with an unaliased context, rather
    than resting on every such caller being rejected upstream first.
    """
    col = ctx.own_column(tag_col)
    tag_values = [tag_value(meta, name) for name in position]
    if tag_kind == "eq":
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
class TphPlan:
    """Table-per-hierarchy: one shared single-table SELECT (m-sql "Inheritance —
    table-per-hierarchy lowering").

    The tag PREDICATE (`tag_kind`: none / `=` / `in`) is keyed purely to the
    resolved position's SIZE — one concrete lowers to `=` whether reached by a
    direct concrete `targetEntity` or a narrow, several lower to `in`, and only an
    untouched abstract-**root** `targetEntity` (no top-level narrow at all) gets no
    tag predicate at all. The raw tag column PROJECTION (`project_tag`, slot 2) is
    instead keyed to whether `targetEntity` itself is abstract — independent of the
    narrow's resolved cardinality (`m-inheritance-012`: `Animal` narrowed to the
    single concrete `Dog` still projects `t0.kind` and still carries
    `familyVariant`, because the caller queried the polymorphic `Animal` position).
    These are deliberately two different conditions.
    """

    table: str
    columns: tuple[tuple[Attribute, str], ...]
    tag_column: str
    project_tag: bool
    value_objects: tuple[ValueObject, ...]
    inner: Operation
    tag_kind: str
    position: tuple[str, ...]
    transform: RowTransform

    def projection(self, dialect: Dialect, alias: str) -> tuple[str, tuple[object, ...]]:
        """The select list and its ordered projection binds, against ``alias``."""
        exprs: list[str] = []
        binds: list[object] = []
        for attribute, _owner in self.columns:
            expr, extra = dialect.project(alias, attribute.column, attribute.type)
            exprs.append(expr)
            binds.extend(extra)
        if self.project_tag:
            # Slot 2 (m-sql resolved Q6): the raw tag column, projected iff the
            # read's OWN targetEntity is abstract — never derived from the
            # resolved position.
            exprs.append(dialect.qualified(alias, self.tag_column))
        exprs.extend(dialect.qualified(alias, vo.column) for vo in self.value_objects)
        return ", ".join(exprs), tuple(binds)


@dataclass(frozen=True, slots=True)
class TpcsSinglePlan:
    """A table-per-concrete-subtype read resolving to exactly one concrete: an
    ordinary single-table read of that subtype's own table, no tag, no union, no
    `familyVariant` — attribute resolution still widens across the family (the
    lowering context's entity stays the read's own `targetEntity`, e.g. an abstract
    position narrowed down to this one concrete), matching the
    table-per-hierarchy concrete-target form.
    """

    table: str
    columns: tuple[tuple[Attribute, str], ...]
    value_objects: tuple[ValueObject, ...]
    inner: Operation
    transform: RowTransform

    def projection(self, dialect: Dialect, alias: str) -> tuple[str, tuple[object, ...]]:
        exprs: list[str] = []
        binds: list[object] = []
        for attribute, _owner in self.columns:
            expr, extra = dialect.project(alias, attribute.column, attribute.type)
            exprs.append(expr)
            binds.extend(extra)
        exprs.extend(dialect.qualified(alias, vo.column) for vo in self.value_objects)
        return ", ".join(exprs), tuple(binds)


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
    tag_column: str
    tag_kind: str
    position: tuple[str, ...]


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
        tag_kind = "eq" if len(position) == 1 else "in"
    else:
        position = tuple(inheritance.effective_concrete_subtypes(meta, target))
        inner = predicate
        is_bare_root = entity.inheritance is not None and entity.inheritance.role == "root"
        tag_kind = "none" if is_bare_root else ("eq" if len(position) == 1 else "in")

    table = meta.entity(position[0]).table
    if table is None:  # pragma: no cover - a validated TPH concrete always declares one
        raise SqlGenError(f"{position[0]}: table-per-hierarchy concrete subtype declares no table")

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
        tag_column=tag_col,
        project_tag=abstract_target,
        value_objects=tuple(superset_value_objects(meta, position)) if instance_form else (),
        inner=inner,
        tag_kind=tag_kind,
        position=position,
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
    tag_col = tph_tag_column(root)
    position = narrow_effective_set(meta, narrow.to)
    return BranchNarrowPlan(
        operand=narrow.operand,
        tag_column=tag_col,
        tag_kind="eq" if len(position) == 1 else "in",
        position=position,
    )
