"""Write no-drift guard (m-api-conformance, M4 increment 5).

The registered write stories (``parallax.conformance.stories`` — the single
source the Usage Guide renders and the real-Postgres suite executes) are driven
here against a recording fake port as the supplementary wire-golden proof.
Commit stories must emit the mirrored corpus case's golden DML (and
participating reads) byte-exact through the **public** developer surface — the
documented spelling cannot drift from the graded wire protocol. Abort stories
prove the m-unit-work abort contract instead: the discarded buffer emits
nothing, the deliberate failure surfaces (or is suppressed by the story itself),
and the surrounding reads still match their goldens — their rolled-back round
trips are graded by the conformance run lane, which executes-then-aborts; the
developer surface discards the buffer before it ever reaches the wire.

Marked ``unit`` as well as ``api_conformance`` (the compile-sweep precedent): it
is pure, Docker-free, in-process behaviour, so the story executions contribute
to the unit-lane branch-coverage gate — the story bodies' only DB-free driver.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Sequence
from decimal import Decimal
from typing import Any, Final, cast

import pytest

from conftest import case_document, compare_binds
from parallax.conformance import case_format, models
from parallax.conformance.read_models import Payment
from parallax.conformance.stories import WRITE_STORIES, WriteStory
from parallax.conformance.vo_models import (
    Contact,
    ContactAddress,
    ContactGeo,
    ContactPoint,
    Shipment,
)
from parallax.core.base import INFINITY, TemporalBound
from parallax.core.db_port import Bind, DbPort, Row
from parallax.core.dialect import POSTGRES
from parallax.core.unit_work import WriteRejectedError
from parallax.snapshot.handle import Database, Transaction

pytestmark = [pytest.mark.unit, pytest.mark.api_conformance]

_MODELS = models.load_models()
_CASES = {c.case_id: c for c in case_format.load_cases()}
_STORIES = {story.case_id: story for story in WRITE_STORIES}

# The driver-native infinity sentinel (`m-core`/`m-dialect`): a real Postgres
# open upper bound renders through `engine.wire_value` as the literal
# `"infinity"` string every golden binds/asserts — a plain far-future
# `datetime` (as `test_transact.py`'s own gate-focused pins use, which never
# compare THIS column) would instead render as an ordinary ISO instant and
# fail the byte-exact DML compare here.
_INFINITY: Final[TemporalBound] = INFINITY

# Per-model seed rows every registered story's own finds may need, COLUMN-keyed
# (the real driver-row convention `parallax.snapshot.handle._wrap` decodes) — one small
# fixed row set per model, keyed by `story.model` (D-29/D-30 completion round:
# the temporal stories' own observing finds need model-shaped seed data too,
# not just Account's). Id 2 (Linus, balance 250.00) joins ids 1/3 here for
# `m-opt-lock-002` (the versioned, locking-mode keyed update) — the SAME triple
# `core/compatibility/fixtures/account.yaml` seeds.
_ACCOUNT_SEED_ROWS: Final[list[Row]] = [
    {"id": 1, "owner": "Ada", "balance": 100.00, "version": 1},
    {"id": 2, "owner": "Linus", "balance": 250.00, "version": 1},
    {"id": 3, "owner": "Grace", "balance": 10.00, "version": 1},
]
_BALANCE_SEED_ROWS: Final[list[Row]] = [
    {
        "bal_id": 1,
        "acct_num": "A",
        "val": Decimal("100.00"),
        "in_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        "out_z": _INFINITY,
    }
]
_POSITION_SEED_ROWS: Final[list[Row]] = [
    {
        "pos_id": 1,
        "acct_num": "A",
        "val": Decimal("100.00"),
        "from_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        "thru_z": _INFINITY,
        "in_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        "out_z": _INFINITY,
    }
]
_SUPPLIER_D1_ADDRESS: Final[dict[str, Any]] = {
    "street": "1 Old Street",
    "city": "Oslo",
    "geo": {"country": "NO"},
    "phones": [{"type": "home", "number": "555-0100"}],
}
_SUPPLIER_SEED_ROWS: Final[list[Row]] = [
    {
        "sup_id": 1,
        "name": "Nordic Foods",
        "in_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        "out_z": _INFINITY,
        "address": _SUPPLIER_D1_ADDRESS,
    }
]
_BRANCH_D1_ADDRESS: Final[dict[str, Any]] = {
    "street": "10 Old Road",
    "city": "Helsinki",
    "geo": {"country": "FI"},
    "phones": [{"type": "main", "number": "555-1000"}],
}
_BRANCH_SEED_ROWS: Final[list[Row]] = [
    {
        "br_id": 1,
        "name": "Central Branch",
        "from_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        "thru_z": _INFINITY,
        "in_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        "out_z": _INFINITY,
        "address": _BRANCH_D1_ADDRESS,
    }
]
_SEED_ROWS_BY_MODEL: Final[dict[str, list[Row]]] = {
    "account": _ACCOUNT_SEED_ROWS,
    "balance": _BALANCE_SEED_ROWS,
    "position": _POSITION_SEED_ROWS,
    "supplier": _SUPPLIER_SEED_ROWS,
    "branch": _BRANCH_SEED_ROWS,
}

# `m-audit-write-005` starts from EXISTING history (`given.fixtures: true`),
# never its own fresh insert: id 1's CURRENT milestone is already value 150.00
# at in_z 2024-06-01 (a superseded 100.00 prior on record too, per the fixture
# — irrelevant to this port double, which serves only the ONE row the story's
# own find actually needs) — a per-CASE override, since the shared per-MODEL
# `_BALANCE_SEED_ROWS` above instead represents "immediately after this OTHER
# story's own fresh insert" (100.00 at 2024-01-01).
_SEED_ROWS_BY_CASE: Final[dict[str, list[Row]]] = {
    "m-audit-write-005": [
        {
            "bal_id": 1,
            "acct_num": "A",
            "val": Decimal("150.00"),
            "in_z": dt.datetime(2024, 6, 1, tzinfo=dt.UTC),
            "out_z": _INFINITY,
        }
    ],
    # `m-value-object-026`/`-027` (D-33, Phase-9 sweep): each story's own
    # SECOND `db.transact` observes its Customer row before replacing/nulling
    # the address out — a per-CASE seed (never per-model: the two stories use
    # different ids AND different original address documents).
    "m-value-object-026": [
        {
            "id": 200,
            "name": "Ingrid",
            "address": {
                "street": "3 Old Road",
                "city": "Bergen",
                "geo": {"country": "NO"},
                "phones": [{"type": "home", "number": "555-1111"}],
            },
        }
    ],
    "m-value-object-027": [
        {
            "id": 300,
            "name": "Bjorn",
            "address": {"street": "7 Fjord Vei", "city": "Alesund", "geo": {"country": "NO"}},
        }
    ],
}


def _seed_rows_for(story: WriteStory) -> list[Row]:
    if story.case_id in _SEED_ROWS_BY_CASE:
        return _SEED_ROWS_BY_CASE[story.case_id]
    return _SEED_ROWS_BY_MODEL.get(story.model, [])


class _RecordingPort:
    """An in-memory ``m-db-port`` recording every call in order (no Docker).

    ``rows`` seeds a small keyed row set, each row's OWN PRIMARY-KEY value
    ordered FIRST in its dict (every seed row below follows this convention);
    each ``execute`` filters it by whether that FIRST value appears among the
    query's bind values (a pk-bind-aware selection, model-agnostic — every
    registered story's own primary-key python name is ``id``, but its
    PHYSICAL column varies, e.g. ``bal_id``/``pos_id``, so matching on a
    literal ``"id"`` key would only ever work by Account's own coincidence;
    matching on EVERY value would falsely multi-match rows sharing an
    unrelated column value, e.g. two Accounts both carrying ``version: 1``) so
    a story finding id 1 vs id 3 — or both, in the SAME transaction — gets the
    matching seeded row, not a fixed stand-in (the graded binds/versions
    depend on it: m-unit-work-006/009/012's own delete gates bind the
    OBSERVED version, which must come from the RIGHT seeded row). A query
    whose binds match no seeded row (an insert-then-find on a fresh id, or a
    non-id predicate) falls back to the FIRST seeded row — a type-correct
    stand-in whose own content the calling story never checks.
    """

    def __init__(self, *, rows: Sequence[Row] = ()) -> None:
        self.ops: list[tuple[object, ...]] = []
        self._rows = [dict(row) for row in rows]

    def execute(self, sql: str, binds: Sequence[Bind]) -> list[Row]:
        self.ops.append(("read", sql, tuple(binds)))
        matched = [row for row in self._rows if next(iter(row.values())) in binds]
        return [dict(row) for row in (matched or self._rows[:1])]

    def execute_write(self, sql: str, binds: Sequence[Bind]) -> int:
        self.ops.append(("write", sql, tuple(binds)))
        return 1

    def transaction[T](self, body: Callable[[DbPort], T]) -> T:
        self.ops.append(("begin",))
        try:
            result = body(self)
        except BaseException:
            self.ops.append(("rollback",))
            raise
        self.ops.append(("commit",))
        return result

    def statements(self) -> list[tuple[str, tuple[object, ...]]]:
        """The executed statements (reads and writes) in wire order."""
        return [
            (cast("str", op[1]), cast("tuple[object, ...]", op[2]))
            for op in self.ops
            if op[0] in ("read", "write")
        ]

    def writes(self) -> list[tuple[str, tuple[object, ...]]]:
        """The executed WRITE statements alone, in wire order (D-29's own
        writeSequence-story grading rule, below)."""
        return [
            (cast("str", op[1]), cast("tuple[object, ...]", op[2]))
            for op in self.ops
            if op[0] == "write"
        ]

    def reads(self) -> list[tuple[str, tuple[object, ...]]]:
        """The executed READ statements alone, in wire order (D-29's own
        writeSequence-story grading rule, below)."""
        return [
            (cast("str", op[1]), cast("tuple[object, ...]", op[2]))
            for op in self.ops
            if op[0] == "read"
        ]

    @property
    def wrote(self) -> bool:
        return any(op[0] == "write" for op in self.ops)


def _driver_goldens(entries: list[dict[str, Any]]) -> list[tuple[str, list[object]]]:
    out: list[tuple[str, list[object]]] = []
    for entry in entries:
        sql: Any = entry["sql"]
        text = cast("dict[str, str]", sql)["postgres"] if isinstance(sql, dict) else sql
        out.append((POSTGRES.to_driver_sql(cast("str", text)), list(entry.get("binds", []))))
    return out


def _scenario_goldens(
    case_id: str, *, skip_rollback: bool = False
) -> list[tuple[str, list[object]]]:
    """The case's flattened per-step golden statements in driver form."""
    doc = case_document(_CASES[case_id])
    if _CASES[case_id].shape == "writeSequence":
        return _driver_goldens(cast("list[dict[str, Any]]", doc["then"]["statements"]))
    out: list[tuple[str, list[object]]] = []
    for step in cast("list[dict[str, Any]]", doc["when"]["scenario"]):
        if skip_rollback and step.get("rollback") is True:
            continue
        out.extend(_driver_goldens(cast("list[dict[str, Any]]", step["statements"])))
    return out


def _assert_reads_are_proper_selects(port: _RecordingPort) -> None:
    """The read/write partition :func:`_observed_statements` relies on is
    exhaustive and correctly classified: every op the port recorded as a READ
    genuinely is one (a ``select``), never a write emission miscategorized —
    the structural half of D-29's own writeSequence-story grading rule, so a
    story's own observation reads (a genuine ``tx.find`` before a temporal
    ``tx.update``/``tx.terminate``, needed for the D-30 merge to have a real
    payload to merge onto) are PROVEN to have executed, even though they are
    graded separately from the byte-exact DML compare below (a writeSequence
    case's own `then.statements` vocabulary is WRITE-ONLY — the corpus format
    never authors a read step there, contrast a `scenario` shape's own
    per-step statements, which DO include find goldens)."""
    for sql, _binds in port.reads():
        assert sql.strip().lower().startswith("select"), sql


def _observed_statements(
    port: _RecordingPort, case_id: str
) -> list[tuple[str, tuple[object, ...]]]:
    """The statements this case's golden ``then.statements``/``statements``
    grades against (D-29): a ``writeSequence`` case's own golden vocabulary is
    WRITE-ONLY, so a writeSequence STORY's own observation reads are excluded
    here (and proven separately, :func:`_assert_reads_are_proper_selects`) —
    never folded into the byte-exact DML compare. A ``scenario`` case's own
    per-step goldens already include find steps, so nothing changes there."""
    _assert_reads_are_proper_selects(port)
    if _CASES[case_id].shape == "writeSequence":
        return port.writes()
    return port.statements()


def _assert_statements(
    port: _RecordingPort, goldens: list[tuple[str, list[object]]], case_id: str
) -> None:
    observed = _observed_statements(port, case_id)
    assert len(observed) == len(goldens), (case_id, observed, goldens)
    for (sql, binds), (golden_sql, golden_binds) in zip(observed, goldens, strict=True):
        assert sql == golden_sql, (case_id, sql, golden_sql)
        # A graduated verb's bind is a REAL typed value (e.g. `Decimal("5.00")`
        # from an idiomatic entity instance), while the case's own authored
        # golden is a plain YAML literal (`5.00`, a float) — `compare_binds`
        # reconciles the two in exact-Decimal space, same as row grading.
        compare_binds(binds, golden_binds)


def _db(port: _RecordingPort, story: WriteStory) -> Database:
    # D-29: a story's own scripted-clock FACTORY (never a shared instance) —
    # this consumer's fresh clock, independent of `test_story_run.py`'s own.
    clock = story.clock() if story.clock is not None else None
    # D-33: a story compiled under its OWN `registry` (the Customer/Location/
    # Depot mirror's `CUSTOMER_REGISTRY`, ledger D-20) connects through THAT
    # registry's metamodel, never the bare ingested corpus descriptor
    # (`_MODELS`) — the same `resolve_entity_class` scoping
    # `test_story_run.py`'s own `_reset_for_registry` observes.
    meta = story.registry.metamodel() if story.registry is not None else _MODELS[story.model]
    return Database.connect(port, meta, clock=clock)


# The no-drift guard grades every EXERCISED story (`m-api-conformance.md`) —
# the core amendment bundle (COR-3 Phase 8) closed the corpus gap that once
# kept m-unit-work-005/006/009/012 guide-only, so every write story here is
# the plain graded idiom now.
_COMMIT_IDS = sorted(s.case_id for s in WRITE_STORIES if s.kind == "commit")
_ABORT_IDS = sorted(s.case_id for s in WRITE_STORIES if s.kind == "abort")

# Abort stories split into two wire shapes. A PLAIN discard's buffered write
# never reaches the wire at all (m-unit-work-002/011): the guard asserts
# `not port.wrote` plus the reads-only goldens. `m-unit-work-012`'s mirrored
# story instead FORCE-FLUSHES its versioned delete for real (a second find
# inside the doomed transaction, mirroring `callback_value_withheld_on_
# abort`'s own force-flush-then-abort pattern) before the deliberate abort
# rolls it back — the delete DOES reach the wire, so it needs the DIFFERENT
# graded treatment `test_force_flushed_abort_story_reaches_the_wire_then_
# rolls_back` below gives it, named here rather than special-cased inline.
_FORCE_FLUSHED_ABORT_IDS: Final[frozenset[str]] = frozenset({"m-unit-work-012"})
_PLAIN_DISCARD_ABORT_IDS = sorted(set(_ABORT_IDS) - _FORCE_FLUSHED_ABORT_IDS)


@pytest.mark.parametrize("case_id", _COMMIT_IDS, ids=_COMMIT_IDS)
def test_commit_story_emits_the_golden_dml(case_id: str) -> None:
    story = _STORIES[case_id]
    port = _RecordingPort(rows=_seed_rows_for(story))
    story.run(_db(port, story))
    _assert_statements(port, _scenario_goldens(case_id), case_id)
    assert port.ops[0] == ("begin",)
    assert port.ops[-1] == ("commit",)
    assert ("rollback",) not in port.ops


@pytest.mark.parametrize("case_id", _PLAIN_DISCARD_ABORT_IDS, ids=_PLAIN_DISCARD_ABORT_IDS)
def test_abort_story_discards_the_buffer_and_keeps_the_reads_golden(case_id: str) -> None:
    # The rolled-back step's DML round trip is graded by the conformance run
    # lane (which executes then aborts); through the developer surface the
    # buffered write is discarded before it reaches the wire, so the guard here
    # is the abort CONTRACT: nothing written, the abort rolled back, reads golden.
    story = _STORIES[case_id]
    port = _RecordingPort(rows=_seed_rows_for(story))
    story.run(_db(port, story))
    assert not port.wrote, (case_id, port.ops)
    _assert_statements(port, _scenario_goldens(case_id, skip_rollback=True), case_id)
    assert ("rollback",) in port.ops


@pytest.mark.parametrize(
    "case_id", sorted(_FORCE_FLUSHED_ABORT_IDS), ids=sorted(_FORCE_FLUSHED_ABORT_IDS)
)
def test_force_flushed_abort_story_reaches_the_wire_then_rolls_back(case_id: str) -> None:
    """`m-unit-work-012`'s mirrored story force-flushes its versioned delete for
    real before the deliberate abort rolls it back, so — unlike a plain
    discard — the delete DOES reach the wire. This compares the FULL
    statement sequence (`skip_rollback=False`: the amended 4-step corpus
    goldens — observe select, delete, forced-flush select, post-abort select
    — match the story's own wire order exactly) plus the structural abort
    contract (the rollback fired, something was written, the trailing
    post-abort find still committed).
    """
    story = _STORIES[case_id]
    port = _RecordingPort(rows=_seed_rows_for(story))
    story.run(_db(port, story))
    _assert_statements(port, _scenario_goldens(case_id, skip_rollback=False), case_id)
    assert ("rollback",) in port.ops
    assert port.wrote
    assert port.ops[-1] == ("commit",)


def test_boundary_story_withholds_the_callback_value() -> None:
    # m-unit-work-004 (boundary, api-conformance lane): read -> buffered update
    # -> a dependent read force-flushes it inside the still-open scope -> the
    # closure throws. The abort discards even the force-flushed write (the
    # port rolls back) and `transact` raises instead of returning the value.
    story = _STORIES["m-unit-work-004"]
    port = _RecordingPort(rows=_seed_rows_for(story))
    with pytest.raises(RuntimeError, match="abort"):
        story.run(_db(port, story))
    kinds = [op[0] for op in port.ops]
    assert kinds == ["begin", "read", "write", "read", "rollback"], port.ops


def test_every_write_story_mirrors_an_active_case_exactly_once() -> None:
    # The registry is reconciled against the corpus: one story per mirrored
    # case, every mirrored case real, and each story's model is its case's.
    assert len(_STORIES) == len(WRITE_STORIES)
    for story in WRITE_STORIES:
        assert story.case_id in _CASES, story.case_id
        model_ref = str(case_document(_CASES[story.case_id])["model"])
        assert story.model == model_ref.removeprefix("models/").removesuffix(".yaml"), story.case_id


# --------------------------------------------------------------------------- #
# Rejected-case build/buffer-time proofs (m-inheritance/m-value-object): the   #
# write-side counterpart of                                                   #
# `test_operation_no_drift.test_idiomatic_statement_build_rejects_the_corpus_rule` #
# — `tx.insert` refuses the SAME invalid write the corpus's own rejected      #
# lane grades (`engine.run_rejected_case`), through the SAME model-aware      #
# `validate_write` (`Transaction._buffer`), naming the SAME classified rule.  #
# No golden DML: a rejected write never reaches the port (`api_suite.EXAMPLES`'#
# own entries are these exact snippets). The Contact/Shipment value-object    #
# write-input rejects (`m-value-object-039..042/044`) construct a            #
# STRUCTURALLY-incomplete instance directly (every inner VO field stays      #
# Python-optional even though its DECLARED descriptor is non-nullable, see   #
# `vo_models.ContactPoint`'s own docstring) — `validate_write`, never         #
# Pydantic's own required-field enforcement, is what refuses it.             #
# --------------------------------------------------------------------------- #
REJECTED_WRITE_BUILDERS: dict[str, Callable[[Transaction], None]] = {
    "m-inheritance-088": lambda tx: tx.insert(Payment(id=10, amount=Decimal("200.00"))),
    "m-value-object-039": lambda tx: tx.insert(
        Contact(
            id=1,
            name="Acme",
            address=ContactAddress(
                city="Oslo",
                geo=ContactGeo(country="NO", point=ContactPoint(lat=59.9, lon=10.7)),
            ),
        )
    ),
    "m-value-object-040": lambda tx: tx.insert(
        Contact(
            id=2,
            name="Beacon",
            address=ContactAddress(
                street="1 Main St",
                city="Oslo",
                geo=ContactGeo(point=ContactPoint(lat=59.9, lon=10.7)),
            ),
        )
    ),
    "m-value-object-041": lambda tx: tx.insert(
        Contact(
            id=3,
            name="Cairn",
            address=ContactAddress(
                street="2 Fjord Vei",
                city="Bergen",
                geo=ContactGeo(country="NO", point=ContactPoint(lon=5.3)),
            ),
        )
    ),
    "m-value-object-042": lambda tx: tx.insert(
        Contact(id=4, name="Delta", address=ContactAddress(street="3 Harbour Rd", city="Oslo"))
    ),
    "m-value-object-044": lambda tx: tx.insert(Shipment(id=5, name="Express")),
}

# case id -> the model `_RecordingPort` connects against.
REJECTED_WRITE_MODELS: dict[str, str] = {
    "m-inheritance-088": "payment",
    "m-value-object-039": "contact",
    "m-value-object-040": "contact",
    "m-value-object-041": "contact",
    "m-value-object-042": "contact",
    "m-value-object-044": "shipment",
}


@pytest.mark.parametrize(
    "case_id", sorted(REJECTED_WRITE_BUILDERS), ids=sorted(REJECTED_WRITE_BUILDERS)
)
def test_idiomatic_write_build_rejects_the_corpus_rule(case_id: str) -> None:
    case = _CASES[case_id]
    expected_rule = case_document(case)["then"]["rejectedRule"]
    port = _RecordingPort()
    db = Database.connect(port, _MODELS[REJECTED_WRITE_MODELS[case_id]])
    with pytest.raises(WriteRejectedError) as exc_info:
        db.transact(REJECTED_WRITE_BUILDERS[case_id])
    assert exc_info.value.rule == expected_rule
    assert not port.wrote
