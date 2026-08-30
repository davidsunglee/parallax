"""What a Scenario's own document must say about the dialect being executed.

Three cross-checks, none of which touches a database: the golden SQL each step
lists is canonical, the round trips it declares are the calls it makes, and a
write settling against a grouped find binds the state that find recorded. All
three are dialect-keyed, so they run only where the executing dialect carries a
golden — the structural rules that must hold on every run are
:mod:`.compile`'s.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, NamedTuple

from ..case import Case, Entity
from ..case_assertions import CaseFailure, write_value_equal
from ..ddl_builder import quote_identifier
from ..inheritance import STRATEGY_TPCS, Family, query_position
from ..keyed_write_validate import validate_keyed_write
from ..sql_normalize import normalize
from ..temporality import temporal_axes
from ..value_object_resolve import RejectionError
from ..write_plan import (
    ObjectAddress,
    assert_inheritance_write_routing,
    assert_write_values,
    classify_write_row,
    close_address_binds,
    is_existing_row_statement,
    parse_set_columns,
    statement_object,
    tag,
    unit_resolving_reads,
    version_column,
)
from .compile import CompiledScenario, _GroupedWrite, _SettledOn, _UngroupedWrite
from .report import reported_against

# The projected output column that carries the table-per-concrete-subtype
# `familyVariant` literal per `union all` branch (the settled TPCS asymmetry,
# m-sql): unlike table-per-hierarchy — which projects the RAW tag column and
# derives `familyVariant` at materialization — TPCS has no tag column, so each
# branch projects a subtype-name literal aliased to this column. A settled write's
# find observed its rows under that spelling, so matching one back to its variant
# reads it here.
_TPCS_VARIANT_COLUMN = "family_variant"


def judge_document(scenario: CompiledScenario, dialect: str) -> None:
    """Grade the Scenario's own document for *dialect*, before any database call."""
    _assert_normalization(scenario, dialect)
    _assert_count_consistency(scenario, dialect)
    _assert_settled_write(scenario, dialect)


def _assert_normalization(scenario: CompiledScenario, dialect: str) -> None:
    case = scenario.case
    for step in scenario.steps:
        for sql in step.statements.sql(dialect):
            canonical = normalize(sql, dialect)
            if canonical != sql:
                raise CaseFailure(
                    f"{case.path.name}: when.scenario[{step.index}].statements ({dialect}) is "
                    f"not canonical.\n"
                    f"  stored:     {sql!r}\n"
                    f"  normalized: {canonical!r}"
                )


def _assert_count_consistency(scenario: CompiledScenario, dialect: str) -> None:
    """Each step's declared roundTrips MUST equal its golden SQL statement count
    plus the resolving reads it owes.

    A cache HIT lists no golden SQL and declares ``roundTrips: 0``; a cache MISS
    that executes one statement declares ``roundTrips: 1``. An ungrouped write
    step declares its DML beside the read its keyed verbs' sources require, which
    it lists no SQL for — the framework composes that read from the model rather
    than from the case. The steps' total MUST equal the case-level
    ``roundTrips``. This is the round-trip contract proven from the fixture's own
    declared counts — the harness never compiles a query to SQL.
    """
    case = scenario.case
    total = 0
    for step in scenario.steps:
        declared = step.round_trips
        statements = step.statements.sql(dialect)
        reads = _resolving_reads(case, step)
        if len(statements) + reads != declared:
            raise CaseFailure(
                f"{case.path.name}: scenario[{step.index}] declares roundTrips "
                f"{declared} but lists {len(statements)} golden SQL statement(s) "
                f"for {dialect} and owes {reads} resolving read(s). A step's declared "
                f"round trips MUST equal the number of calls it makes (a cache hit = 0)."
            )
        total += declared
    if total != case.round_trips:
        raise CaseFailure(
            f"{case.path.name}: scenario steps total {total} round trip(s) but "
            f"roundTrips is {case.round_trips}. The case-level roundTrips MUST "
            f"equal the sum of the per-step round trips."
        )


def _resolving_reads(case: Case, step: Any) -> int:
    """The resolving reads ONE scenario step owes beside the SQL it lists.

    An UNGROUPED write step is its own choreography unit, so it owes what any unit
    owes (:func:`write_plan.unit_resolving_reads`). A GROUPED one owes none of its
    own: its group's find steps are what publish the values it settles against,
    and those finds already declare their own round trips (`m-case-format`
    *Resolving reads a write owes*). A find step owes none either — a read IS
    the SQL it lists.
    """
    if not isinstance(step, _UngroupedWrite):
        return 0
    return unit_resolving_reads(case, list(step.entries))


def _assert_settled_write(scenario: CompiledScenario, dialect: str) -> None:
    """Cross-check each settled write step's golden against the observed state the
    find it names recorded (`m-case-format` *Settling against a grouped find*).

    The observed state is resolved INDEPENDENTLY of the golden, from the named
    find step's own ``expectRows`` — the rows that read returned, which is exactly
    the evidence the store it filled holds — and by each entry's OWN object
    (:func:`_settled_observed_row`), so a find that observed no row of that object
    names evidence that does not exist.
    What the resolution then reaches is the target's PROFILE's answer: a temporal
    write's close address (on a Bitemporal target, its Valid-Time exclusive upper
    bound) and its optimistic gate, and a versioned Non-Temporal write's own gate
    and framework-computed version advance. Either way the corpus states which
    state the write settled against in two independent places — here and in
    execution.

    Which bind a misresolution moves differs the same way: a Bitemporal key's
    current rectangles are disjoint on Valid Time, so a close binding the OTHER
    current rectangle fails on the address, while a Transaction-Time-Only close
    addresses the key plus the invariant open bound and a versioned write its key
    alone, so on both of those the whole difference lands on what the observation
    derives.

    An entry is aligned with its golden by the OBJECT each statement itself
    addresses (:func:`write_plan.statement_object`), never by the order the buffer
    names objects in: a flush dependency-orders its surviving writes so a parent is
    inserted before and deleted after the children referencing it (`m-unit-work`
    *the planning pipeline*, `m-case-format` *foreign-key-ordered at flush*), so
    the statement order a legal buffer produces is the graph's, not the author's.
    Entries settling against one state of one object coalesce into ONE statement
    (`m-unit-work` *Observed-State Coalescing*) — what distinguishes them is the
    assignments they contribute to it, while what this cross-check reads, the
    state they settled against, is the one thing they share — and the same buffer
    equally expresses a mixed multi-object flush, whose objects emit one statement
    each. The settling statement is the EXISTING-ROW one; a temporal successor's
    chained INSERT settles nothing and is passed over.

    An address names the object but not which concrete subtype of it a golden
    claims, because a table-per-hierarchy family shares one table, so the aligned
    statement is also required to ROUTE to the entry's own subtype — the tag guard
    binding that subtype's ``tagValue``, or, under table-per-concrete-subtype, its
    own table (`m-inheritance`). The writeSequence lane asks the same of its
    goldens; a scenario write carries no writeSequence, so this is where a settled
    one is asked.
    """
    case = scenario.case
    for step in scenario.steps:
        if not isinstance(step, _GroupedWrite) or step.settles_on is None:
            continue
        # The write-grading operations this delegates to speak of the statement
        # they were handed rather than of the Scenario position that handed it
        # over, so the position is added here, at the boundary that knows it.
        with reported_against(case, step.index):
            _assert_settled_step(case, step, step.settles_on, dialect)


def _assert_settled_step(case: Case, step: _GroupedWrite, origin: _SettledOn, dialect: str) -> None:
    """Grade one settled write step's golden against its named find's own rows."""
    index = step.index
    settling = [
        (_statement_address(case, index, statement, binds, dialect), statement, binds)
        for statement, binds in step.statements.pairs(dialect)
        if is_existing_row_statement(statement)
    ]
    aligned: set[int] = set()
    for entry in step.entries:
        entity = case.model.entity(entry["entity"])
        row = _sole_settled_row(case, index, entity, entry)
        temporal = bool(temporal_axes(entity.runtime_facts))
        _, pk, _set_cols, _observed = classify_write_row(
            case, entity, row, mutation=entry["mutation"], opening=temporal
        )
        statement, binds = _settled_statement(case, index, entity, pk, settling, aligned)
        assert_inheritance_write_routing(case, entity, [statement], [binds], dialect)
        if not temporal:
            _assert_settled_version_binds(
                case, entity, index, origin, pk, binds, statement, dialect
            )
            continue
        observed = _settled_milestone(case, entity, index, origin, pk)
        expected = [
            entry.get("at"),
            *close_address_binds(case, entity, pk, observed.valid_end),
        ]
        if case.concurrency_mode == "optimistic":
            expected.append(observed.tx_start)
        assert_write_values(case, expected, binds, statement)
    if len(aligned) != len(settling):
        raise CaseFailure(
            f"{case.path.name}: scenario[{index}] carries {len(settling) - len(aligned)} "
            f"existing-row statement(s) for {dialect} addressing an object no entry of its "
            f"buffer writes — every statement a settled flush emits belongs to one of the "
            f"objects written, and entries settling against one state coalesce into one."
        )


def _settled_statement(
    case: Case,
    index: int,
    entity: Entity,
    pk: Any,
    settling: list[tuple[ObjectAddress, str, list[Any]]],
    aligned: set[int],
) -> tuple[str, list[Any]]:
    """The golden statement one settled entry's OBJECT survives as, with the binds
    authored on it.

    Alignment is by OBJECT IDENTITY — the entry's own table and Object Key against
    the ones each statement addresses — so it holds however the flush ordered
    those statements, and every entry of one object reaches the one statement they
    coalesce into. Two statements addressing one object are refused as firmly as
    none: coalescing leaves an object at most one surviving existing-row write per
    observed state, and the second would be graded against evidence the first
    already consumed.

    ``aligned`` collects the statements entries reached, which is what lets the
    caller name a golden addressing an object the buffer never writes.
    """
    matches = [
        position
        for position, (address, _statement, _binds) in enumerate(settling)
        if address.names_table(entity.table)
        and address.names_key_column(entity.identity_column)
        and write_value_equal(address.key, pk)
    ]
    if not matches:
        raise CaseFailure(
            f"{case.path.name}: scenario[{index}] settles a write of {entity.name} pk {pk!r} "
            f"against a find but its golden carries no existing-row statement addressing that "
            f"object — a settled write emits one."
        )
    if len(matches) > 1:
        raise CaseFailure(
            f"{case.path.name}: scenario[{index}] carries {len(matches)} existing-row "
            f"statements addressing {entity.name} pk {pk!r} — writes settling against one "
            f"observed state of one object coalesce into ONE statement."
        )
    (position,) = matches
    aligned.add(position)
    _address, statement, binds = settling[position]
    return statement, binds


def _statement_address(
    case: Case, index: int, statement: str, binds: list[Any], dialect: str
) -> ObjectAddress:
    """The object a settled scenario step's *statement* addresses.

    A settled write addresses the ONE object it survives as, so a golden here that
    renders no bound key address is a defect of the case rather than a statement
    with nothing to say — which is why the address is required at this step and
    optional to :func:`write_plan.statement_object`.
    """
    address = statement_object(statement, binds, dialect)
    if address is None:
        raise CaseFailure(
            f"{case.path.name}: scenario[{index}] carries an existing-row golden whose "
            f"predicate does not open with a bound key equality for {dialect}: "
            f"{statement!r} — a settled write addresses the ONE object it survives as, "
            f"and its key leads that address."
        )
    return address


def _assert_settled_version_binds(
    case: Case,
    entity: Entity,
    index: int,
    origin: _SettledOn,
    pk: Any,
    binds: list[Any],
    statement: str,
    dialect: str,
) -> None:
    """Cross-check a settled VERSIONED Non-Temporal write's golden against the
    generation the find it names observed OF ITS OWN KEY.

    A versioned write is addressed by its key alone, so the whole difference
    between one observed generation and another lands on what the observation
    derives, and both halves are graded: the optimistic gate, which is the
    golden's LAST bind and is the observed version itself, and the
    framework-computed advance, which is one more than it and is assigned in
    BOTH concurrency modes. A locking UPDATE therefore still states its observed
    generation; a DELETE assigns nothing, so a locking one states none and there
    is nothing here to cross-check.

    Which of the two the statement carries is read off the STATEMENT rather than
    off the entry's own verb, because coalescing decides what survives: a
    destructive intent supersedes the assignments buffered before it, so an
    entry spelling `update` may reach a golden DELETE that advances nothing.

    The generation is read off the named find step's own ``expectRows`` by the
    write's own key, exactly as the temporal arm reads its milestone
    (:func:`_settled_milestone`), so the corpus states which generation the write
    settled against in two independent places.

    The version column is located in the SET clause by the spelling the golden
    renders it with (:func:`quote_identifier`) rather than by its model name: a
    physical column may be reserved or otherwise non-simple, and the golden then
    quotes it exactly as the generated DML does (`m-dialect`).
    """
    version_col = version_column(entity)
    if version_col is None:
        return
    observed = _settled_generation(case, entity, index, origin, pk, version_col)
    if case.concurrency_mode == "optimistic" and (
        not binds or not write_value_equal(binds[-1], observed)
    ):
        raise CaseFailure(
            f"{case.path.name}: scenario[{index}] settles {entity.name} against a find that "
            f"observed version {observed!r}, but its golden gate binds "
            f"{binds[-1] if binds else None!r}."
        )
    assigned = parse_set_columns(statement)
    if assigned is None:
        return
    spelling = quote_identifier(version_col, dialect)
    if spelling not in assigned:
        raise CaseFailure(
            f"{case.path.name}: scenario[{index}] settles a versioned {entity.name} update "
            f"whose golden SET clause {assigned} assigns no {spelling!r} — a versioned "
            f"update advances the framework-owned version under either concurrency strategy."
        )
    position = assigned.index(spelling)
    advanced = binds[position] if position < len(binds) else None
    if not write_value_equal(advanced, observed + 1):
        raise CaseFailure(
            f"{case.path.name}: scenario[{index}] settles {entity.name} against a find that "
            f"observed version {observed!r}, but its golden advances the version to "
            f"{advanced!r} rather than {observed + 1!r}."
        )


def _settled_observed_row(
    case: Case, entity: Entity, index: int, origin: _SettledOn, pk: Any, state: str
) -> Mapping[str, Any]:
    """The ONE row of *pk* a settled write's named find declares it observed.

    Read off that find step's own ``expectRows`` — the rows the case declares that
    read returned, which is exactly the evidence the store it filled holds — so
    this derivation consults the case's READ result rather than the tracked
    current state every other write shape resolves from. That is the whole point
    of the reference: a unit of work may hold more than one piece of evidence
    about a key, so tracked state answers for at most one of them and only the
    read the write named says which it was handed.

    One resolver for both profiles, because the rule they share is the whole of
    it — the write's own object, exactly one match — and what differs is only the
    state each then projects out of the row (:func:`_settled_generation`,
    :func:`_settled_milestone`). *state* is that profile's own noun, so the
    refusal names what the write would have settled against.

    A POLYMORPHIC find needs the write's own concrete subtype beside the key
    (:func:`_row_is_variant_of`): a primary key names one object per TABLE, and only a
    table-per-hierarchy family shares one, so a discriminated-union read over
    table-per-concrete-subtype legitimately returns sibling rows of one key from
    different tables. Two rows the write's own subtype claims are two observed states,
    which is what the write would have to choose between. Which of a row's fields
    STATES a variant is the ORIGIN read's own question, so it is asked of that read
    once (:func:`_origin_variant_columns`) rather than guessed per row.
    """
    key_column = entity.identity_column
    variant_columns = _origin_variant_columns(case, origin)
    matched = [
        row
        for row in origin.observed_rows
        if write_value_equal(row.get(key_column), pk)
        and _row_is_variant_of(case, entity, row, variant_columns)
    ]
    if len(matched) != 1:
        raise CaseFailure(
            f"{case.path.name}: scenario[{index}] settles against a find that observed "
            f"{len(matched)} row(s) of {entity.name} pk {pk!r} — a keyed write settles "
            f"against the ONE {state} the value it was handed came from."
        )
    return matched[0]


def _origin_variant_columns(case: Case, origin: _SettledOn) -> tuple[str, ...]:
    """The fields of *origin*'s observed rows that state a row's variant SPELLING, in
    precedence order — empty when that read states no variant at all.

    Only a read whose queried position is ABSTRACT is discriminated: it resolves over
    more than one concrete subtype, so `m-sql` gives its result a variant tag —
    materialized as ``familyVariant`` in the compatibility rows (`m-case-format`),
    and, under table-per-concrete-subtype before that materialization, carried by the
    projected per-branch ``family_variant`` literal. The materialized spelling leads,
    because a materialized row carries BOTH: alias remapping restores an authored
    physical column its own spelling, so `family_variant` beside `familyVariant` is
    the model's own column beside the read's answer.

    A **concrete-target** read carries no variant tag whatsoever (`m-sql`: the caller
    already queried a known variant), so neither spelling means anything there. Both
    are legal physical spellings a model may author — the compatibility corpus maps
    `catalog.Record.variantMarker` to the column ``family_variant`` and
    `compatibility.overlap.VariantRecord`'s value-object document to the column
    ``familyVariant`` — and reading one of those as a discriminator would refuse a
    settled write whose find observed exactly the row it names.

    Which position is abstract is asked of the same classifier materialization asks
    (:func:`~reference_harness.inheritance.query_position`), so one rule in this
    harness decides whether a read's rows carry a variant — of *origin*'s own query,
    because that is the read whose rows are being interrogated.
    """
    position = query_position(origin.object_query, case.model.entity_defs)
    if position is None:
        return ()
    if position.strategy == STRATEGY_TPCS:
        return ("familyVariant", _TPCS_VARIANT_COLUMN)
    return ("familyVariant",)


def _row_is_variant_of(
    case: Case, entity: Entity, row: Mapping[str, Any], variant_columns: tuple[str, ...]
) -> bool:
    """Whether an observed row is a row of *entity*'s own concrete subtype.

    A discriminated-union read tags every returned row with the concrete variant it
    resolved to (`m-inheritance` *Abstract-position reads*), and that tag is what
    separates two sibling rows a key alone cannot: the raw tag column under
    table-per-hierarchy, and otherwise whichever field the ORIGIN read states its
    variant in (*variant_columns*, from :func:`_origin_variant_columns`). The tag
    column is read first and needs no such licence: it is a real column of the shared
    table carrying that row's own ``tagValue``, so it says the same thing wherever it
    appears.

    A row stating no variant answers for its key alone — a concrete-target read
    projects no discriminator, because every row it returns is already the queried
    subtype's.
    """
    discriminator = tag(entity)
    if discriminator is not None and discriminator[0] in row:
        return write_value_equal(row[discriminator[0]], discriminator[1])
    for column in variant_columns:
        if column in row:
            return row[column] == Family(case.model.entity_defs).variant_spelling(
                entity.canonical_name
            )
    return True


def _settled_generation(
    case: Case, entity: Entity, index: int, origin: _SettledOn, pk: Any, version_col: str
) -> Any:
    """The version a settled versioned write's named find observed, of *pk*.

    The versioned peer of :func:`_settled_milestone`: a versioned key holds one
    ROW but one observed GENERATION per read of it, so the resolved row must carry
    the version that read saw, and a row carrying none states no generation for
    the write to have settled against.
    """
    row = _settled_observed_row(case, entity, index, origin, pk, "generation")
    if version_col not in row:
        raise CaseFailure(
            f"{case.path.name}: scenario[{index}] settles against a find whose observed "
            f"{entity.name} pk {pk!r} carries no {version_col!r} — a keyed write settles "
            f"against the ONE generation the value it was handed came from."
        )
    return row[version_col]


def _sole_settled_row(
    case: Case, index: int, entity: Entity, entry: dict[str, Any]
) -> dict[str, Any]:
    """The ONE row a settled write entry authors.

    The plural half is `m-unit-work`'s own singleton — a temporal entry chains
    one milestone, and an observed write of any profile is evidence about one row
    — and it is asked of the SAME
    :func:`~reference_harness.keyed_write_validate.validate_keyed_write` every
    other lane asks it of, so this lane cannot refuse a different set of entries;
    what is local here is only the consequence — a settled entry must hand over
    exactly one row, because the named find handed over exactly one value.
    """
    try:
        validate_keyed_write(entity, entry)
    except RejectionError as exc:
        raise CaseFailure(f"{case.path.name}: scenario[{index}]: {exc.detail}") from exc
    rows = entry.get("rows")
    if not isinstance(rows, list) or len(rows) != 1:
        raise CaseFailure(
            f"{case.path.name}: scenario[{index}] settles a write entry carrying "
            f"{len(rows) if isinstance(rows, list) else 0} rows against a find — a settled "
            f"entry carries ONE row, which is the one value that find handed over."
        )
    return rows[0]


class _ObservedMilestone(NamedTuple):
    """The two coordinates of the milestone a settled close was handed.

    Not a whole rectangle: what a close derives from its observation is the
    Valid-Time bound it addresses and, under optimistic concurrency, the
    Transaction-Time start it gates on. The milestone's Valid-Time start is the
    predecessor's own edge, which the close neither addresses nor gates on.
    """

    valid_end: Any
    tx_start: Any


def _settled_milestone(
    case: Case, entity: Entity, index: int, origin: _SettledOn, pk: Any
) -> _ObservedMilestone:
    """The milestone a settled write's named find observed, of *pk*.

    A milestone chain holds several rows per key, so the resolved row's own
    coordinates are what the close derives from.

    A Transaction-Time-Only target has no Valid-Time half to read, and its close
    addresses the key plus the invariant open Transaction-Time bound, so there the
    milestone the find observed reaches the golden through the optimistic gate
    alone.
    """
    axes = {axis.dimension: axis for axis in temporal_axes(entity.runtime_facts)}
    valid_axis, tx_axis = axes.get("valid-time"), axes["transaction-time"]
    row = _settled_observed_row(case, entity, index, origin, pk, "milestone")
    return _ObservedMilestone(
        row.get(valid_axis.end.column) if valid_axis is not None else None,
        row.get(tx_axis.start.column),
    )
