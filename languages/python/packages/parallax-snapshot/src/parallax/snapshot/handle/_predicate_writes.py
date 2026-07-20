"""``parallax.snapshot.handle._predicate_writes`` — the predicate-selected (``_where``) write lane.

The set-based half of the spec §5 write surface (COR-3 Phase 8 increment 5), as
free functions rather than :class:`~parallax.snapshot.handle.Transaction`
methods: bare-statement and business-window validation into a canonical
:class:`~parallax.core.unit_work.PredicateWrite`, the readless-vs-materialize
dispatch, the minimal resolving read, per-row no-op elimination, observation
recording, and atomic keyed-unit buffering.

Every entry point threads ``(uow, meta, conn, dialect)`` — the four pieces of
transaction state this lane actually reads — mirroring
:func:`~parallax.snapshot.handle._write_inputs.record_observations`'s own shape.
``Transaction`` keeps five thin ``_where`` delegates plus the frozen
``_buffer_predicate_instruction`` seam the conformance engine calls, so this
module buffers through ``uow.buffer`` directly and never reaches back into
``Transaction``.

Depends on :mod:`parallax.snapshot.handle._family` (the version attribute and
the member-to-column map) and :mod:`parallax.snapshot.handle._write_inputs`
(window validation and the per-row materialization).

Names crossing a module boundary are spelled bare; a helper whose every caller
lives here keeps its underscore. Privacy is carried by this MODULE's leading
underscore and by the package's frozen ``__all__``, never by per-name
underscores.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence

from parallax.core import deep_fetch, inheritance, op_algebra, read_lock
from parallax.core.db_port import DbPort, Row
from parallax.core.descriptor import Attribute, Entity, Metamodel
from parallax.core.dialect import Dialect, LockMode
from parallax.core.entity import Statement as EntityStatement
from parallax.core.entity.expressions import AttributeAssignment
from parallax.core.sql_gen import Statement, compile_read
from parallax.core.unit_work import (
    AtomicUnit,
    KeyedWrite,
    ObjectKey,
    Observation,
    PredicateMutation,
    PredicateWrite,
    UnitOfWork,
    instructions,
)
from parallax.snapshot.handle._family import assignment_member, members, version_attribute
from parallax.snapshot.handle._write_inputs import (
    materialize_row,
    validate_business_from,
    validate_until,
)


def buffer_predicate(
    uow: UnitOfWork,
    meta: Metamodel,
    conn: DbPort,
    dialect: Dialect,
    mutation: PredicateMutation,
    statement: EntityStatement,
    assignments: Sequence[AttributeAssignment],
    *,
    business_from: dt.datetime | None,
    until: dt.datetime | None = None,
) -> None:
    """The neutral seam every ``_where`` verb shares — the SAME seam the
    conformance engine's predicate-write translation drives (COR-3 Phase 8
    increment 5), so the developer-facing verbs and the corpus-driven
    engine path can never diverge in behavior.

    1. **Bare-statement guard** (`python.md` §5 "A statement becomes a
       write target only as a bare statement") — one carrying nothing but
       a predicate; every other clause is rejected (`EntityStatement.
       is_bare`, subsuming ``.distinct()``).
    2. **Inheritance rejection** (`m-inheritance` "Per-object writes are
       keyed; set-based inheritance writes are out of scope") — BEFORE any
       SQL, the SAME ``subtype-write-set-based-unsupported`` classification
       a keyless keyed write raises.
    3. **Business-bound validation** — a bitemporal target REQUIRES
       ``business_from`` (its own business instant); an audit-only or
       non-temporal target takes none (no business axis to bound); the
       ``*Until`` forms additionally require ``until``, with
       ``business_from < until`` — an equal or reversed window rejects
       HERE, at build, before any buffering (:func:`validate_until`, S4
       COR-3 Phase 8 increment 7 remediation).
    4. **Build + validate the canonical instruction** (the SAME
       deserialize/`validate_instruction` round trip a keyed write buys in
       ``Transaction._buffer`` — non-empty/no-duplicate assignments are the
       schema's own check).
    5. **Dispatch**: an unversioned, non-temporal target buffers READLESS
       (one statement, `m-batch-write`); a versioned or temporal one
       MATERIALIZES (``_materialize_predicate_write``, ADR 0014).
    """
    if not statement.is_bare():
        raise ValueError(
            f"{statement.target}: a set-based write target must be a bare statement "
            "(nothing but a predicate) — order_by / limit / distinct / as_of / history / "
            "as_of_range / narrow / include are all rejected on a write target (python.md §5)"
        )
    entity = meta.entity(statement.target)
    inheritance.reject_predicate_write(entity)
    declaring = inheritance.declaring_entity(meta, entity)
    business_from_literal = validate_business_from(declaring, mutation, business_from)
    until_literal: str | None = None
    if until is not None:
        assert business_from is not None  # `*_until_where` verbs require both together
        until_literal = validate_until(declaring, mutation, business_from, until)

    doc: dict[str, object] = {
        "mutation": mutation,
        "target": {
            "entity": statement.target,
            "predicate": op_algebra.serialize(statement.predicate),
        },
    }
    if assignments:
        doc["assignments"] = [{"attr": str(a.attr), "value": a.value} for a in assignments]
    if business_from_literal is not None:
        doc["businessFrom"] = business_from_literal
    if until_literal is not None:
        doc["businessTo"] = until_literal
    instruction = instructions.deserialize(doc)
    assert isinstance(instruction, PredicateWrite)  # this seam always builds the predicate shape
    instructions.validate_instruction(instruction, meta)
    buffer_predicate_instruction(uow, meta, conn, dialect, instruction)


def buffer_predicate_instruction(
    uow: UnitOfWork,
    meta: Metamodel,
    conn: DbPort,
    dialect: Dialect,
    instruction: PredicateWrite,
) -> None:
    """The neutral seam UNDERLYING every ``_where`` verb and the
    conformance engine's own predicate-write translation (COR-3 Phase 8
    increment 5; `m-case-format` "predicate-shaped case entries deserialize
    to PredicateWrite through the existing serde and buffer through
    Transaction's own seam"): given an ALREADY-BUILT, already-validated
    :class:`~parallax.core.unit_work.PredicateWrite` instruction, reject an
    inheritance-family target (`m-inheritance`), then dispatch READLESS
    (`m-batch-write`) or MATERIALIZE (`m-opt-lock`, ADR 0014). The typed
    ``_where`` verbs (:func:`buffer_predicate`) build ``instruction`` from
    a bare :class:`~parallax.core.entity.Statement` plus typed
    ``Attr.set(...)`` assignments first; the engine builds it directly
    from the case's own canonical write-instruction document — both
    converge HERE, so the two callers can never diverge in behavior.

    ``Transaction._buffer_predicate_instruction`` is the thin method that
    delegates here. It keeps its leading underscore and its exact signature
    because the conformance engine calls it directly (`parallax.conformance.
    engine`), making it a frozen external seam rather than an ordinary
    cross-module helper.
    """
    entity = meta.entity(instruction.target.entity)
    inheritance.reject_predicate_write(entity)
    declaring = inheritance.declaring_entity(meta, entity)
    version_attr = version_attribute(declaring)
    if not declaring.is_temporal and version_attr is None:
        # Readless (`m-batch-write.md` "Predicate-selected readless forms"):
        # one statement, no materialization, no equality-elimination pass.
        uow.buffer(instruction)
        return
    _materialize_predicate_write(
        uow, meta, conn, dialect, instruction, entity, declaring, version_attr
    )


def _materialize_predicate_write(
    uow: UnitOfWork,
    meta: Metamodel,
    conn: DbPort,
    dialect: Dialect,
    instruction: PredicateWrite,
    entity: Entity,
    declaring: Entity,
    version_attr: Attribute | None,
) -> None:
    """Materialize a predicate write on a VERSIONED or TEMPORAL target
    (`m-opt-lock` "Predicate-selected writes materialize when observations
    are needed"; ADR 0014): resolve the predicate through a MINIMAL
    row-form read on THIS transaction's own connection (never instance-form
    — the resolve constructs no object, `m-value-object-047`), record each
    matched row's observation through ``uow.observe`` (the SAME
    transaction-scoped seam a real
    :meth:`~parallax.snapshot.handle.Transaction.find` uses — never an
    engine-side map), then buffer one keyed per-row write per row the verb
    WRITES (the per-row no-op elimination below) as an ORDERED ATOMIC PLANNED
    UNIT (`m-unit-work`, :class:`AtomicUnit`) at the call position. Zero
    resolved rows -> zero keyed writes, success (no unit buffered at all).
    The lock suffix on the resolve derives from the transaction's own
    concurrency mode (``locking`` ⇒ the shared read lock, ``optimistic`` ⇒
    none) — the SAME rule a real ``Transaction.find`` applies.

    A TEMPORAL target's raw predicate carries no as-of wrapper (a bare
    statement forbids ``.as_of()``/``.history()``, python.md §5) — exactly
    like an ordinary find's omitted axis, it must still default every
    declared axis to its CURRENT milestone (`m-temporal-read` "default-
    latest"), so the resolve routes through the SAME
    :func:`~parallax.core.deep_fetch.plan` root-canonicalization every
    other read uses (:func:`~parallax.snapshot.handle.find`) rather than
    compiling the raw predicate directly — otherwise a temporal target's
    resolve would match every historical milestone too, not just the open
    one(s).
    """
    lock: LockMode | None = read_lock.mode_for(uow.settings.concurrency)
    plan_ = deep_fetch.plan(instruction.target.entity, instruction.target.predicate, meta)
    assignments = {
        assignment_member(assignment.attr): assignment.value
        for assignment in instruction.assignments
    }
    # Need-sensitive projection (`m-case-format.md:727`): the resolving
    # read projects the resolved row's own value-object document(s) for
    # TWO independent needs, on EVERY target class — never gated on
    # temporality alone (confirmation-pass residual A, completing P2).
    #
    # CHAIN need: the verb's OWN milestone plan writes a CHAINED row
    # from the resolved one. A BITEMPORAL target's rectangle split
    # (`bitemp_write.plan`) chains on EVERY close-bearing mutation —
    # update, updateUntil, terminate, AND terminateUntil alike, since
    # head (and tail, for the `*Until` forms) always carry the OLD
    # payload forward, not just an assignment-bearing one
    # (`m-bitemp-write` "head/tail old values come from the observed
    # prior rectangle"). An AUDIT-ONLY target's plan (`audit_write.
    # plan`) chains ONLY an ASSIGNMENT-BEARING `update`
    # (`materialize_row`'s own `assignment_bearing` set) — its
    # `terminate` is close-only, no chained row, so it stays
    # document-free (`m-value-object-047`'s own row-form-omits-slot-4
    # witness stays byte-identical); audit-only never reaches the
    # `*Until` forms (bitemporal-only, `validate_business_from`). The
    # chain need projects EVERY declared document, never just the
    # assigned ones — a chained row must carry forward whichever
    # documents the assignments do NOT themselves reassign. Either way,
    # an AUDIT-ONLY target's own `full_row` merge (`materialize_row`)
    # reads this read's row directly, while a BITEMPORAL target's split
    # reads it indirectly, through `_temporal_observation`'s payload,
    # which keeps a value-object document whenever THIS read actually
    # projected it (`m-value-object` "the document rides every
    # chained/split row whole").
    #
    # COMPARISON need: an assignment-bearing verb's per-row no-op
    # elimination (below, `materialize_row` -> `_apply_assignments`)
    # compares each assigned member's new value against the resolved
    # row's own — a value-object member's comparison can only ever see
    # the STORED document when this read actually projected its column
    # (`m-opt-lock.md:92-95` "when all assignments already equal that
    # row's values, it issues no DML, advances no version"). A TEMPORAL
    # target's chain need above already projects every document
    # whenever it is assignment-bearing, so this need is a strict no-op
    # there; a VERSIONED NON-TEMPORAL target never chains (no milestone
    # to carry a payload across — `m-opt-lock`/`m-descriptor`: versioned
    # and temporal are mutually exclusive), so it reaches this need
    # ALONE. Minimal-read discipline (`m-sql`) then projects the
    # ASSIGNED value-object document(s) only — never every declared
    # one, matching an ordinary read's own need-driven projection.
    assignment_bearing = instruction.mutation in ("update", "updateUntil")
    chain_need = (
        version_attr is None
        and declaring.is_temporal
        and (declaring.temporal == "bitemporal" or instruction.mutation == "update")
    )
    needs_documents: bool | frozenset[str]
    if chain_need:
        needs_documents = True
    elif assignment_bearing:
        member_columns = members(meta, entity)
        needs_documents = frozenset(member for member in assignments if member_columns[member][1])
    else:
        needs_documents = False
    statement = compile_read(
        plan_.root_operation,
        meta,
        dialect,
        instruction.target.entity,
        result_form="row",
        lock=lock,
        include_value_objects=needs_documents,
    )
    rows = uow.read(lambda: _resolve_rows(conn, dialect, statement))
    writes: list[KeyedWrite] = []
    pending: list[tuple[ObjectKey, Observation | None]] = []
    for row in rows:
        key, observation, new_row = materialize_row(
            meta, entity, declaring, version_attr, instruction.mutation, assignments, row
        )
        if new_row is None:
            continue  # per-row no-op elimination (assignment-bearing verbs only)
        writes.append(
            KeyedWrite(
                mutation=instruction.mutation,
                entity=instruction.target.entity,
                rows=(new_row,),
                business_from=instruction.business_from,
                business_to=instruction.business_to,
            )
        )
        pending.append((key, observation))
    if not writes:
        return
    for key, observation in pending:
        if observation is not None:
            uow.observe(key, observation)
    uow.buffer(AtomicUnit(writes=tuple(writes)))


def _resolve_rows(conn: DbPort, dialect: Dialect, statement: Statement) -> list[Row]:
    return conn.execute(dialect.to_driver_sql(statement.sql), list(statement.binds))
