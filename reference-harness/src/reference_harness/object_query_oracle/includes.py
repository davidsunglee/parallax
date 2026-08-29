"""The Include Paths a read eager-fetches, and the one statement each hop costs.

An Object Query's ``includes`` are authored as paths; what a read executes is the
de-duplicated set of relationship HOPS those paths traverse, one golden statement
each after the root. This module resolves the paths into hops, executes each hop
once keyed by the parent keys the previous level gathered, and buckets the rows it
returned by parent so the assembly can fan them back out in memory.

The contract it proves is N+1 elimination, and it proves it against derivations of
its own rather than against the database's answer: a level's authored binds are
the gathered parent keys, then the effective set's table-per-hierarchy tag values,
then the propagated as-of coordinates, and a declared relationship ordering is
graded on the rows the golden returned. A level whose parents gathered no keys
issues no SQL at all, so the statement a case lists for it is dead SQL the case is
refused for.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass
from typing import Any, NamedTuple

from ..case import Case, Entity, Model
from ..case_assertions import CaseFailure
from ..inheritance import (
    STRATEGY_TPH,
    Family,
    inheritance_of,
    narrowed_view_key,
    resolve_hop_effective_set,
    resolve_root_source_set,
    tag_value_to_subtype,
)
from . import execute, materialize
from .executor import ReadExecutor

# --- reading the authored paths ---------------------------------------------


def query_has_includes(query: dict[str, Any]) -> bool:
    """Whether an Object Query eager-fetches anything at all."""
    return bool(query.get("includes"))


def deepfetch_paths(query: dict[str, Any]) -> list[list[str]]:
    """One Object Query's Include Paths as ordered lists of ``Class.relationship`` refs.

    A path is a closed object ``{appliesTo?, segments}`` whose entries are closed
    ``{rel, narrowTo?}`` segments (m-object-query); this projection keeps only the
    ``rel`` and is used where narrowing is irrelevant (root-entity resolution).
    Narrow-aware hop identity is built from :func:`deepfetch_paths_raw`.

    Every reader here takes the QUERY rather than the case, because a read case's
    top-level ``when.objectQuery`` and a Scenario read step's own ``objectQuery``
    are the same document in two positions and both carry includes.
    """
    return [[segment["rel"] for segment in path["segments"]] for path in query["includes"]]


def deepfetch_paths_raw(query: dict[str, Any]) -> list[dict[str, Any]]:
    """The Include Paths as authored: closed ``{appliesTo?, segments}`` objects.

    Preserves both selection positions — the SOURCE guard and each hop's own
    ``narrowTo`` — so the fetch machinery can derive the narrowed view key, the
    root participation filter, and the dedup identity built from both.
    """
    return list(query["includes"])


def deepfetch_root_position(query: dict[str, Any]) -> str | None:
    """The polymorphic position a deep fetch's paths are rooted at.

    The query's own ``target`` when it names an entity of the model, which is what
    a source guard clamps against.
    """
    target = query.get("target")
    return target if isinstance(target, str) else None


def deepfetch_root_entity(model: Model, query: dict[str, Any]) -> Entity:
    """The entity the deep-fetch root query targets.

    It is the owning class of the first relationship in the first declared path
    (every path starts at the queried entity), so a deep fetch may be rooted at
    any entity in a multi-entity model, not just the descriptor's first one.
    """
    first_rel = deepfetch_paths(query)[0][0]
    root_class = first_rel.rpartition(".")[0]
    return model.entity(root_class)


def column_of(entity: Entity, attr_name: str) -> str:
    """The physical Column *entity* holds its named Attribute in."""
    return entity.attribute_by_name(attr_name)["column"]


def _join_endpoints(relationship: dict[str, Any]) -> tuple[str, str]:
    """``(source_attr, target_attr)`` of a compiled structured join."""
    join = relationship["join"]
    return join["source"]["attribute"], join["target"]["attribute"]


def _resolve_rel_ref(model: Model, rel_ref: str) -> tuple[Entity, dict[str, Any]]:
    """Resolve ``Class.relationship`` to its owning entity + relationship def."""
    class_name, _, rel_name = rel_ref.rpartition(".")
    entity = model.entity(class_name)
    return entity, entity.relationship_metadata_by_name(rel_name)


# --- resolving the paths into hops ------------------------------------------


class HopKey(NamedTuple):
    """The dedup identity of one deep-fetch hop (m-deep-fetch).

    ``parent`` is the key of the hop this one descends from, absent at a path's
    first segment: it is what keeps two branches that reach the same relationship
    from different parents apart, so every hop names exactly one set of parent rows.
    ``root_source`` is the path's resolved ROOT SOURCE SET, carried at that first
    segment alone — deeper hops inherit the guard through ``parent``.
    ``narrowed_set`` is the hop's own effective concrete set, carried only when a
    narrow was AUTHORED.

    The two narrow positions key on deliberately different things. ``narrowed_set``
    keys on whether a narrow was authored, because a narrowed hop populates its own
    view key even when it resolves to the target's entire set. ``root_source`` keys
    on the resolved set alone, because a root guard creates no view: a guard
    admitting every root object is observationally the broad path and collapses onto
    it, while every proper guard resolves to a strict subset and differs
    automatically.
    """

    parent: HopKey | None
    root_source: tuple[str, ...] | None
    rel_ref: str
    narrowed_set: tuple[str, ...] | None


class ResolvedHop(NamedTuple):
    """One authored path segment resolved against the family.

    The single derivation both passes over a deep fetch share — the execution pass
    that issues each level's statement and the assembly pass that walks the authored
    paths again — so a hop cannot be identified one way while executing and another
    way while attaching. ``effective_set`` is the hop's canonically-ordered effective
    concrete set, or ``None`` for a non-polymorphic target; ``target`` is the
    relationship's declared target class, carried alongside it because the
    table-per-hierarchy tag predicate is derived from the family it belongs to.
    """

    key: HopKey
    target: str | None
    effective_set: list[str] | None
    is_narrowed: bool


def resolve_hop(
    family: Family,
    segment: dict[str, Any],
    *,
    parent: HopKey | None,
    root_source: tuple[str, ...] | None,
) -> ResolvedHop:
    """Resolve one authored segment into its effective set and its dedup identity.

    *root_source* is the path's resolved root source set at a path's FIRST segment
    and ``None`` at every deeper one, because a deeper hop descends from parents the
    guard already selected and is separated by *parent* instead.
    """
    rel_ref = segment["rel"]
    narrow_to = segment.get("narrowTo") if isinstance(segment.get("narrowTo"), list) else None
    target = family.relationship_target(rel_ref)
    if target is not None and inheritance_of(family.defs.get(target, {})) is not None:
        effective_set, is_narrowed = resolve_hop_effective_set(family, rel_ref, narrow_to)
    else:
        effective_set, is_narrowed = None, False
    key = HopKey(
        parent=parent,
        root_source=root_source,
        rel_ref=rel_ref,
        narrowed_set=tuple(effective_set) if (is_narrowed and effective_set is not None) else None,
    )
    return ResolvedHop(key=key, target=target, effective_set=effective_set, is_narrowed=is_narrowed)


class FetchStep:
    """One relationship hop = one golden statement (after the root).

    A hop is identified by :attr:`hop_key`, so a BROAD hop and a NARROWED hop over
    the same relationship, two narrowed hops with different effective sets, two
    paths guarded to different root sources, and two branches reaching one
    relationship from different parents are all DISTINCT levels (each counts toward
    ``L`` in ``1 + L``), while equivalent authored narrowings that resolve to the
    same set DEDUPLICATE (m-deep-fetch). :attr:`parent_hop` names the hop whose
    fetched rows this one gathers its parent keys from, absent when those are the
    root query's own rows. Its graph attach key is :attr:`view_key` — the ordinary
    relationship name for a broad hop, the derived ``<rel>[<Concrete>,<Concrete>]``
    for a narrowed one; a root guard contributes NO view key at all.
    :attr:`root_guard` is the source set a PROPER root guard restricts this hop's
    parent objects to, carried only on the hop a guarded path starts with (a deeper
    hop's parents are already the guarded ones) and only when the guard admits fewer
    than every root object.
    """

    def __init__(
        self,
        rel_ref: str,
        parent_entity: Entity,
        child_entity: Entity,
        parent_attr: str,
        child_attr: str,
        cardinality: str,
        order_by: list[dict[str, Any]] | None = None,
        *,
        hop_key: HopKey,
        view_key: str,
        effective_set: list[str] | None,
        is_narrowed: bool,
        root_guard: tuple[str, ...] | None,
        tag_column: str | None,
        tag_binds: list[Any],
        polymorphic: bool,
        variant_map: dict[Any, str],
    ) -> None:
        self.rel_ref = rel_ref
        self.rel_name = rel_ref.rpartition(".")[2]
        self.parent_entity = parent_entity
        self.child_entity = child_entity
        self.parent_attr = parent_attr
        self.child_attr = child_attr
        self.cardinality = cardinality
        self.order_by = order_by or []
        self.hop_key = hop_key
        self.view_key = view_key
        self.effective_set = effective_set
        self.is_narrowed = is_narrowed
        self.root_guard = root_guard
        self.tag_column = tag_column
        self.tag_binds = tag_binds
        self.polymorphic = polymorphic
        self.variant_map = variant_map

    @property
    def parent_hop(self) -> HopKey | None:
        return self.hop_key.parent

    @property
    def to_many(self) -> bool:
        return self.cardinality == "one-to-many"


def fetch_steps(model: Model, query: dict[str, Any]) -> list[FetchStep]:
    """Ordered, de-duplicated relationship hops for a deep fetch.

    Each distinct hop across all paths is exactly one statement (one query per level
    — the N+1-eliminating contract). Dedup identity is :class:`HopKey`: paths
    sharing a segment prefix (``{segments: [{rel: Order.items}]}`` /
    ``{segments: [{rel: Order.items}, {rel: OrderItem.statuses}]}``) fetch
    ``Order.items`` once; a broad and a narrowed hop over the same relationship, or
    two differently-narrowed hops, are DISTINCT; equivalent authored narrowings
    (``[Pet]`` vs ``[Cat, Dog]``) converge — at the segment position and at the root
    position alike.
    """
    family = Family(model.entity_defs)
    variant_map = tag_value_to_subtype(model.entity_defs)
    root_position = deepfetch_root_position(query)
    root_full_set = resolve_root_source_set(family, root_position, {})
    steps: list[FetchStep] = []
    seen: set[HopKey] = set()
    for path in deepfetch_paths_raw(query):
        root_source = resolve_root_source_set(family, root_position, path)
        # A guard admitting every root object restricts nothing, so only a PROPER
        # guard is carried as a participation filter.
        guard = root_source if root_source != root_full_set else None
        parent_hop: HopKey | None = None
        for index, segment in enumerate(path["segments"]):
            hop = resolve_hop(
                family, segment, parent=parent_hop, root_source=root_source if index == 0 else None
            )
            if hop.key not in seen:
                seen.add(hop.key)
                steps.append(
                    _step_of(
                        model,
                        family,
                        hop,
                        variant_map,
                        root_guard=guard if index == 0 else None,
                    )
                )
            parent_hop = hop.key
    return steps


def _step_of(
    model: Model,
    family: Family,
    hop: ResolvedHop,
    variant_map: dict[Any, str],
    *,
    root_guard: tuple[str, ...] | None,
) -> FetchStep:
    """The executable step one resolved hop denotes: its endpoints, its graph attach
    key, and the table-per-hierarchy tag binds its shared-table read carries."""
    rel_ref = hop.key.rel_ref
    parent_entity, relationship = _resolve_rel_ref(model, rel_ref)
    child_entity = model.entity(relationship["join"]["target"]["entity"])
    this_attr, other_attr = _join_endpoints(relationship)
    rel_name = rel_ref.rpartition(".")[2]

    if hop.effective_set is not None and hop.target is not None:
        # The shared table holds the WHOLE family's concretes (the root's
        # descendants), not just the relationship target's — so a hop targeting an
        # abstract SUBTYPE still needs a tag predicate to exclude sibling branches in
        # the same table. No tag predicate when the hop spans the whole shared table;
        # otherwise a tag `=`/`in` over the effective set's tagValues.
        root = family.root_of(hop.target)
        whole = family.effective_concrete_set(root) if root is not None else hop.effective_set
        tag_column = family.tag_column_of(hop.target)
        tag_binds: list[Any] = (
            []
            if set(hop.effective_set) == set(whole)
            else _hop_tag_binds(family, hop.effective_set)
        )
        view_key = (
            narrowed_view_key(family, rel_ref, hop.effective_set) if hop.is_narrowed else rel_name
        )
        polymorphic = len(hop.effective_set) > 1 and family.strategy_of(hop.target) == STRATEGY_TPH
    else:
        tag_column, tag_binds, polymorphic = None, [], False
        view_key = rel_name

    return FetchStep(
        rel_ref=rel_ref,
        parent_entity=parent_entity,
        child_entity=child_entity,
        parent_attr=this_attr,
        child_attr=other_attr,
        cardinality=relationship["cardinality"],
        order_by=relationship.get("orderBy"),
        hop_key=hop.key,
        view_key=view_key,
        effective_set=hop.effective_set,
        is_narrowed=hop.is_narrowed,
        root_guard=root_guard,
        tag_column=tag_column,
        tag_binds=tag_binds,
        polymorphic=bool(polymorphic),
        variant_map=variant_map,
    )


def _hop_tag_binds(family: Family, effective_set: list[str]) -> list[Any]:
    """The ``tagValue`` list for a table-per-hierarchy hop's effective set.

    A single concrete lowers to ``kind = ?`` (one bind); several to ``kind in (?, …)``
    (one bind per concrete). *effective_set* is already in the family's canonical
    sibling-set order (ALPHABETICAL by entity name, m-inheritance), so the binds follow
    that order. Mirrors the top-level TPH tag-selection rule (m-sql), applied to a
    deep-fetch child level.
    """
    binds: list[Any] = []
    for name in effective_set:
        block = inheritance_of(family.defs.get(name, {}))
        if block is not None and block.get("tagValue") is not None:
            binds.append(block["tagValue"])
    return binds


# --- which parents a hop starts from ----------------------------------------


def guarded_parents(
    case: Case, step: FetchStep, parents: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """The parent rows a path-root guard admits into *step* (m-deep-fetch).

    A root guard changes no statement of its own and populates no view of its own:
    it selects which already-fetched ROOT objects the hop starts from, so the hop's
    child statement is keyed by exactly those objects' gathered keys. Selection is
    by the root row's own concrete subtype, which an abstract-target read carries as
    ``familyVariant`` — a guard can only ever be a proper subset of a POLYMORPHIC
    position, so a root read that projects no variant cannot be guarded at all.
    """
    if step.root_guard is None:
        return parents
    admitted = set(step.root_guard)
    for row in parents:
        if "familyVariant" not in row:
            raise CaseFailure(
                f"{case.path.name}: the path-root guard {list(step.root_guard)!r} on "
                f"{step.rel_ref} cannot select root objects — the root read carries no "
                f"`familyVariant`, so its own position is not polymorphic "
                f"(m-inheritance / m-deep-fetch)."
            )
    return [row for row in parents if row["familyVariant"] in admitted]


# --- the order a to-many level must have returned ---------------------------


def _sorted_by_order_keys(
    rows: list[dict[str, Any]],
    sort_spec: list[tuple[str, bool, bool]],
) -> list[dict[str, Any]]:
    """Return *rows* sorted by *sort_spec* — a list of
    ``(column, descending, nulls_first)`` triples evaluated left to right. Stable:
    rows tied on every key keep input order. A key's Null Placement is
    independent of its direction (m-deep-fetch), so ``nulls_first`` is not derived
    from ``descending``; an authored placement is what the caller passes and an
    omitted one arrives already defaulted to nulls-last.
    """

    def compare(row_a: dict[str, Any], row_b: dict[str, Any]) -> int:
        for column, descending, nulls_first in sort_spec:
            left, right = row_a[column], row_b[column]
            if left == right:
                continue
            if left is None:
                return -1 if nulls_first else 1
            if right is None:
                return 1 if nulls_first else -1
            ordered = -1 if left < right else 1
            return -ordered if descending else ordered
        return 0

    return sorted(rows, key=functools.cmp_to_key(compare))


def assert_child_ordering(
    case: Case,
    steps: list[FetchStep],
    children_by_step: dict[HopKey, dict[Any, list[dict[str, Any]]]],
) -> None:
    """Assert each ordered to-many level returned its children in the declared order.

    A to-many relationship that declares ``orderBy`` requires the per-level child
    query to emit ``ORDER BY`` over the declared keys (m-navigate), so the rows the DB
    returned — preserved in SQL order inside each parent's bucket — must already
    equal those rows sorted by the declared keys/directions. The oracle derives
    the expected order from the model (an independent oracle) rather than trusting
    the authored ``then.graph`` order. A relationship with no ``orderBy`` is
    skipped (its order is unspecified). NULL values sort where the key's authored
    ``nulls`` asks, and where it is omitted they sort LAST — the canonical
    placement in either direction (m-deep-fetch); two NULLs are equal and fall
    through to the next key. Residual ties beyond the declared keys keep
    their DB order (the sort is stable), which the contract permits. Every
    declared ``orderBy`` key MUST be present in the child query's projection; a
    key absent from the returned rows raises a clean ``CaseFailure`` (the order
    cannot be verified without the key).
    """
    for step in steps:
        if not step.to_many or not step.order_by:
            continue
        sort_spec = [
            (
                column_of(step.child_entity, key["attribute"]),
                key.get("direction", "asc") == "desc",
                key.get("nulls", "last") == "first",
            )
            for key in step.order_by
        ]
        bucket = children_by_step.get(step.hop_key, {})
        for parent_key, rows in bucket.items():
            if not rows:
                continue
            missing = [column for column, _, _ in sort_spec if column not in rows[0]]
            if missing:
                raise CaseFailure(
                    f"{case.path.name}: {step.rel_ref} orderBy column(s) {missing!r} are "
                    f"not in the child query's projection, so the order cannot be "
                    f"verified; project them in the child SELECT."
                )
            expected = _sorted_by_order_keys(rows, sort_spec)
            if rows != expected:
                cols = [column for column, _, _ in sort_spec]
                got = [[row[c] for c in cols] for row in rows]
                want = [[row[c] for c in cols] for row in expected]
                raise CaseFailure(
                    f"{case.path.name}: {step.rel_ref} children for parent "
                    f"{parent_key!r} are not in declared orderBy order "
                    f"(keys {cols!r}). got {got!r}, expected {want!r}."
                )


# --- executing the levels ----------------------------------------------------


@dataclass(frozen=True, slots=True)
class ExecutedLevels:
    """What one run of a query's child levels produced, and how much SQL it used.

    ``consumed`` is the count rather than a slice because the levels a run
    executes are a PREFIX of the statements it was handed: a streamed read's
    pages share one flat ``then.statements`` list, so each page reads the tail
    left by the pages before it and hands the rest back.
    """

    children_by_hop: dict[HopKey, dict[Any, list[dict[str, Any]]]]
    consumed: int


def refuse_unused_levels(
    case: Case, source: str, dialect: str, executed: ExecutedLevels, listed: int
) -> None:
    """Refuse a case listing child SQL its own levels never reached.

    Enforced by the callers that hand over their WHOLE statement list, because
    only they know that nothing follows: a streamed page is handed the tail of a
    list later pages still consume, so an unused statement there is the next
    page's root rather than dead SQL.
    """
    if executed.consumed != listed:
        raise CaseFailure(
            f"{case.path.name}: {source} ({dialect}) lists "
            f"{listed - executed.consumed} unused deep-fetch child "
            f"statement(s). Child SQL MUST be omitted after a level gathers no "
            f"parent keys."
        )


def execute_fetch_levels(
    case: Case,
    reader: ReadExecutor,
    source: str,
    query: dict[str, Any],
    steps: list[FetchStep],
    root_rows: list[dict[str, Any]],
    levels: list[tuple[str, list[Any]]],
) -> ExecutedLevels:
    """Execute one Object Query's child levels and bucket each hop's rows by parent key.

    The N+1-elimination contract, executed once for both positions an Include
    Path is authored at — a read case's own ``then.statements`` and a Scenario
    read step's own ``statements``, named by *source* in every diagnostic. A
    child level runs only when the previous level produced parent keys; an empty
    parent key set elides that child SQL entirely, and a level the golden lists
    but no parent reaches is unused SQL the case is refused for. Each executed
    level's authored binds are cross-checked against the keys, tag values, and
    propagated as-of coordinates the oracle derives independently, so a dropped
    IN list, a missing table-per-hierarchy tag filter, or a lost as-of
    propagation fails the case rather than passing on the DB's own answer. Rows
    are held per HOP rather than per entity, because two branches may reach one
    entity through different guards or different parents and a deeper hop
    descends from exactly one of them.
    """
    dialect = reader.dialect
    root_pins = execute.root_asof_pins(query)

    # rows_by_hop[hop key] -> the result-rows that hop fetched.
    rows_by_hop: dict[HopKey, list[dict[str, Any]]] = {}

    # Execute each hop once, keyed by gathered parent keys, bucketed by hop identity.
    children_by_step: dict[HopKey, dict[Any, list[dict[str, Any]]]] = {}
    statement_index = 0
    for step in steps:
        source_rows = root_rows if step.parent_hop is None else rows_by_hop[step.parent_hop]
        parents = guarded_parents(case, step, source_rows)
        parent_col = column_of(step.parent_entity, step.parent_attr)
        parent_keys = sorted(
            {
                materialize.coerce_identity_key(parent[parent_col])
                for parent in parents
                if parent.get(parent_col) is not None
            }
        )

        if not parent_keys:
            rows_by_hop[step.hop_key] = []
            children_by_step[step.hop_key] = {}
            continue

        if statement_index >= len(levels):
            raise CaseFailure(
                f"{case.path.name}: {source} ({dialect}) has no child statement "
                f"for {step.view_key}, but the previous level gathered parent "
                f"keys {parent_keys!r}."
            )

        # Bind layout per child level: the IN-list of gathered parent keys, then the
        # polymorphic hop's tag binds (table-per-hierarchy `kind = ?` / `in (?, …)`
        # over the effective set, alphabetical order), then the propagated as-of binds.
        level_sql, raw_authored = levels[statement_index]
        in_slice = raw_authored[: len(parent_keys)]
        rest = list(raw_authored[len(parent_keys) :])
        tag_slice = rest[: len(step.tag_binds)]
        asof_suffix = rest[len(step.tag_binds) :]
        if sorted(materialize.coerce_identity_key(bind) for bind in in_slice) != parent_keys:
            raise CaseFailure(
                f"{case.path.name}: {source} ({dialect}) level {statement_index + 1} "
                f"({step.view_key}) IN-list binds {in_slice!r} != gathered parent "
                f"keys {parent_keys!r}. The child level MUST be keyed by exactly "
                f"the parents from the previous level (the N+1-eliminating IN list)."
            )
        if list(tag_slice) != list(step.tag_binds):
            raise CaseFailure(
                f"{case.path.name}: {source} ({dialect}) level {statement_index + 1} "
                f"({step.view_key}) tag binds {tag_slice!r} != the effective-set tag "
                f"values {step.tag_binds!r}. A polymorphic table-per-hierarchy hop over a "
                f"proper subset MUST filter its shared-table read by the effective set's "
                f"tag values (m-navigate / m-inheritance)."
            )

        # As-of propagation oracle: the root pin propagates per-hop, matched by
        # axis, to each temporal child level. The oracle derives the child's
        # as-of binds independently and asserts the authored suffix matches, so a
        # dropped/wrong propagated as-of fails the case. A non-temporal child has
        # an empty suffix (no as-of term).
        expected_suffix = (
            execute.expected_pin_suffix(step.child_entity, root_pins)
            if step.child_entity.is_temporal
            else []
        )
        if list(asof_suffix) != expected_suffix:
            raise CaseFailure(
                f"{case.path.name}: {source} ({dialect}) level {statement_index + 1} "
                f"({step.view_key}) as-of suffix {asof_suffix!r} != the propagated "
                f"as-of binds {expected_suffix!r}. The root pin MUST propagate to "
                f"this temporal child (matched by axis), appended after the IN list."
            )

        child_rows = execute.query_rows(
            case,
            reader,
            level_sql,
            list(parent_keys) + list(step.tag_binds) + expected_suffix,
        )
        # A polymorphic (multi-concrete, table-per-hierarchy) hop projects the raw tag
        # column; materialize each row's `familyVariant` from the tag map (never a
        # projected SQL column), exactly as an abstract-target flat read does.
        if step.polymorphic and step.tag_column is not None:
            child_rows = [
                materialize.materialize_hop_variant(
                    case,
                    row,
                    view_key=step.view_key,
                    tag_column=step.tag_column,
                    variant_map=step.variant_map,
                )
                for row in child_rows
            ]
            child_rows = [
                materialize.materialize_document_layout(
                    case,
                    case.model.entity(row["familyVariant"]),
                    [row],
                    include_value_objects=True,
                )[0]
                for row in child_rows
            ]
        else:
            child_rows = materialize.materialize_document_layout(
                case,
                step.child_entity,
                child_rows,
                include_value_objects=True,
            )
        rows_by_hop[step.hop_key] = child_rows

        child_col = column_of(step.child_entity, step.child_attr)
        bucket: dict[Any, list[dict[str, Any]]] = {}
        for row in child_rows:
            bucket.setdefault(materialize.coerce_identity_key(row[child_col]), []).append(row)
        children_by_step[step.hop_key] = bucket
        statement_index += 1

    assert_child_ordering(case, steps, children_by_step)

    return ExecutedLevels(children_by_hop=children_by_step, consumed=statement_index)
