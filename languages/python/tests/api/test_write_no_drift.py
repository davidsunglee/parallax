"""Write no-drift guard (m-api-conformance).

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

Pure, Docker-free, in-process behaviour, so it classifies ``dbfree`` and the
story executions contribute to the database-free branch-coverage gate — the
story bodies' only database-free driver.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Mapping, Sequence
from decimal import Decimal
from typing import Any, Final, cast

import pytest
from pydantic import ValidationError

from _support.corpus import case_document, compare_binds
from _support.db_port import body_outcome
from _support.document_reads import fold_mapping_rows
from parallax.conformance import case_format
from parallax.conformance.class_models import MODELS
from parallax.conformance.engine import decode_write_row
from parallax.conformance.read_models import Payment
from parallax.conformance.stories import WRITE_STORIES, WriteStory
from parallax.conformance.vo_models import (
    ContactAddress,
    ContactGeo,
    ContactPoint,
    Destination,
    Shipment,
)
from parallax.core.base import INFINITY, TemporalBound
from parallax.core.db_port import Bind, Committed, DbPort, Row, TransactionOutcome
from parallax.core.dialect import POSTGRES
from parallax.core.entity import DomainModel
from parallax.core.entity._model import model_of
from parallax.core.metamodel import EntityMetadata
from parallax.core.unit_work import WriteRejectedError, validate_write
from parallax.snapshot.handle import Database, Transaction

_CASES = {c.case_id: c for c in case_format.load_cases()}
_STORIES = {story.case_id: story for story in WRITE_STORIES}

# The driver-native infinity sentinel (`m-core`/`m-dialect`): a real Postgres
# open upper bound renders through `engine.wire_value` as the literal
# `"infinity"` string every golden binds/asserts — a plain far-future
# `datetime` (as `test_transaction_writes.py`'s own gate-focused pins use, which never
# compare THIS column) would instead render as an ordinary ISO instant and
# fail the byte-exact DML compare here.
_INFINITY: Final[TemporalBound] = INFINITY

# Per-model seed rows every registered story's own finds may need, COLUMN-keyed
# (the real driver-row convention `parallax.snapshot.handle` decodes) — one small
# fixed row set per model, keyed by `story.model` (the temporal stories'
# own observing finds need model-shaped seed data too,
# not just Account's). Id 2 (Linus, balance 250.00) joins ids 1/3 here for
# `m-opt-lock-002` (the versioned, locking-mode keyed update) — the SAME triple
# `core/compatibility/fixtures/account.yaml` seeds.
_ACCOUNT_SEED_ROWS: Final[list[Row]] = [
    {"id": 1, "owner": "Ada", "balance": Decimal("100.00"), "version": 1},
    {"id": 2, "owner": "Linus", "balance": Decimal("250.00"), "version": 1},
    {"id": 3, "owner": "Grace", "balance": Decimal("10.00"), "version": 1},
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

# `m-txtime-write-005` starts from EXISTING history (`given.fixtures: true`),
# never its own fresh insert: id 1's CURRENT milestone is already value 150.00
# at in_z 2024-06-01 (a superseded 100.00 prior on record too, per the fixture
# — irrelevant to this port double, which serves only the ONE row the story's
# own find actually needs) — a per-CASE override, since the shared per-MODEL
# `_BALANCE_SEED_ROWS` above instead represents "immediately after this OTHER
# story's own fresh insert" (100.00 at 2024-01-01).
_SEED_ROWS_BY_CASE: Final[dict[str, list[Row]]] = {
    "m-txtime-write-005": [
        {
            "bal_id": 1,
            "acct_num": "A",
            "val": Decimal("150.00"),
            "in_z": dt.datetime(2024, 6, 1, tzinfo=dt.UTC),
            "out_z": _INFINITY,
        }
    ],
    # `m-value-object-026`/`-027`: each story's own
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
    # `m-unit-work-028`: the fixture row whose stored `geo` is a SCALAR where a
    # `one` occurrence is declared. Its story's find delivers the classification
    # in band, so this seed has to carry the invalid document verbatim — a
    # conforming stand-in would take the story down the ordinary branch and grade
    # nothing the case is about.
    "m-unit-work-028": [
        {
            "id": 6,
            "name": "Rin",
            "address": {"street": "6 Kastanien Allee", "city": "Berlin", "geo": "unknown"},
        }
    ],
}


# A read SCRIPT: one row set per read, consumed in the order the story issues
# them. The keyed seed sets above select by primary-key bind, which is exactly
# what a story reading one key at two AS-OF coordinates cannot be served by — the
# coordinate is what distinguishes the two answers, and resolving one needs a
# temporal query engine this double is deliberately not. A story whose reads
# differ only by coordinate therefore states its own answers here, in order.
_READ_ROWS_BY_CASE: Final[dict[str, list[list[Row]]]] = {
    # `m-unit-work-015`: Position id 1 holds two rectangles current on
    # Transaction Time. The story's first find pins Valid Time 2024-03-01 and
    # observes the split HEAD; its second pins 2024-09-01 and observes the
    # corrected TAIL. Both are the fixture rows `fixtures/position.yaml` seeds.
    "m-unit-work-015": [
        [
            {
                "pos_id": 1,
                "acct_num": "A",
                "val": Decimal("100.00"),
                "from_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
                "thru_z": dt.datetime(2024, 6, 1, tzinfo=dt.UTC),
                "in_z": dt.datetime(2024, 4, 1, tzinfo=dt.UTC),
                "out_z": _INFINITY,
            }
        ],
        [
            {
                "pos_id": 1,
                "acct_num": "A",
                "val": Decimal("200.00"),
                "from_z": dt.datetime(2024, 6, 1, tzinfo=dt.UTC),
                "thru_z": _INFINITY,
                "in_z": dt.datetime(2024, 4, 1, tzinfo=dt.UTC),
                "out_z": _INFINITY,
            }
        ],
    ]
}


def _seed_rows_for(story: WriteStory) -> list[Row]:
    if story.case_id in _SEED_ROWS_BY_CASE:
        return _SEED_ROWS_BY_CASE[story.case_id]
    return _SEED_ROWS_BY_MODEL.get(story.model, [])


def _port_for(story: WriteStory) -> _RecordingPort:
    return _RecordingPort(
        rows=_seed_rows_for(story), reads=_READ_ROWS_BY_CASE.get(story.case_id, [])
    )


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

    ``reads`` overrides that selection with a SCRIPT: one row set per read, in
    issue order, for a story whose reads a keyed selection cannot tell apart —
    two finds of one key at different as-of coordinates return different
    milestones, and deciding which is a temporal query this double does not
    answer. A read past the script's end falls back to the keyed selection.
    """

    def __init__(self, *, rows: Sequence[Row] = (), reads: Sequence[Sequence[Row]] = ()) -> None:
        self.ops: list[tuple[object, ...]] = []
        self._rows = [dict(row) for row in rows]
        self._scripted = [[dict(row) for row in answer] for answer in reads]

    def execute(
        self, sql: str, binds: Sequence[Bind], document_reads: Sequence[tuple[int, int]] = ()
    ) -> list[Row]:
        self.ops.append(("read", sql, tuple(binds)))
        if self._scripted:
            return fold_mapping_rows(self._scripted.pop(0), document_reads)
        matched = [row for row in self._rows if next(iter(row.values())) in binds]
        return fold_mapping_rows(matched or self._rows[:1], document_reads)

    def execute_write(self, sql: str, binds: Sequence[Bind]) -> int:
        self.ops.append(("write", sql, tuple(binds)))
        return 1

    def transaction[T](
        self, body: Callable[[DbPort], T], *, isolation: str | None = None
    ) -> TransactionOutcome[T]:
        self.ops.append(("begin",))
        outcome = body_outcome(self, body)
        self.ops.append(("commit",) if isinstance(outcome, Committed) else ("rollback",))
        return outcome

    def statements(self) -> list[tuple[str, tuple[object, ...]]]:
        """The executed statements (reads and writes) in wire order."""
        return [
            (cast("str", op[1]), cast("tuple[object, ...]", op[2]))
            for op in self.ops
            if op[0] in ("read", "write")
        ]

    def writes(self) -> list[tuple[str, tuple[object, ...]]]:
        """The executed WRITE statements alone, in wire order (the
        writeSequence-story grading rule, below)."""
        return [
            (cast("str", op[1]), cast("tuple[object, ...]", op[2]))
            for op in self.ops
            if op[0] == "write"
        ]

    def reads(self) -> list[tuple[str, tuple[object, ...]]]:
        """The executed READ statements alone, in wire order (the
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
    the structural half of the writeSequence-story grading rule, so a
    story's own observation reads (a genuine ``tx.find`` before a temporal
    ``tx.update``/``tx.terminate``, needed for the merge to have a real
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
    grades against: a ``writeSequence`` case's own golden vocabulary is
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
    # A story's own scripted-clock FACTORY (never a shared instance) —
    # this consumer's fresh clock, independent of `test_story_run.py`'s own.
    clock = story.clock() if story.clock is not None else None
    return Database.connect(port, MODELS[story.model], clock=clock)


# The no-drift guard grades every EXERCISED story (`m-api-conformance.md`);
# every write story here is the plain graded idiom.
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
    port = _port_for(story)
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
    port = _port_for(story)
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
    port = _port_for(story)
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
    port = _port_for(story)
    with pytest.raises(RuntimeError, match="abort"):
        story.run(_db(port, story))
    kinds = [op[0] for op in port.ops]
    assert kinds == ["begin", "read", "write", "read", "rollback"], port.ops


def _case_model_stem(case_id: str) -> str:
    """The `MODELS` key the case's own `model` reference names."""
    model_ref = str(case_document(_CASES[case_id])["model"])
    return model_ref.removeprefix("models/").removesuffix(".yaml")


def test_every_write_story_mirrors_an_active_case_exactly_once() -> None:
    # The registry is reconciled against the corpus: one story per mirrored
    # case, every mirrored case real, and each story's model is its case's.
    assert len(_STORIES) == len(WRITE_STORIES)
    for story in WRITE_STORIES:
        assert story.case_id in _CASES, story.case_id
        assert story.model == _case_model_stem(story.case_id), story.case_id


# --------------------------------------------------------------------------- #
# Rejected-case build/buffer-time proofs (m-inheritance/m-value-object): the   #
# write-side counterpart of                                                   #
# `test_object_query_no_drift.test_idiomatic_statement_build_rejects_the_corpus_rule` #
# — `tx.insert` refuses the SAME invalid write the corpus's own rejected      #
# lane grades (`engine.run_rejected_case`), through the SAME model-aware      #
# `validate_write` (`Transaction._buffer`), naming the SAME classified rule.  #
# No golden DML: a rejected write never reaches the port (`api_suite.EXAMPLES`'#
# own entries are these exact snippets).                                      #
# --------------------------------------------------------------------------- #
REJECTED_WRITE_BUILDERS: dict[str, Callable[[Transaction], None]] = {
    "m-inheritance-088": lambda tx: tx.insert(Payment(id=10, amount=Decimal("200.00"))),
}

# case id -> the model `_RecordingPort` connects against.
REJECTED_WRITE_MODELS: dict[str, str] = {"m-inheritance-088": "payment"}

# The Contact/Shipment value-object write-input rejects the corpus grades
# through `validate_write` over a raw document. The class grammar carries
# nullability on the annotation alone, so a declared-non-nullable member is a
# required Python field and the same defect is refused one step earlier, at
# construction — the representation-specific rejection spec §2 sanctions for a
# shape only one grammar can spell. Each entry names the member the corpus case
# omits, so the two stay pinned to the same defect.
#
# Both halves of that sentence are graded, because they discharge DIFFERENT
# obligations and a regression in either must fail:
#
#   `test_the_class_grammar_refuses_the_corpus_incomplete_document` discharges
#   python.md §2's "grammar-level failures stay representation-specific — the
#   descriptor rejects through its ingestion phases, Python through class
#   creation — so a shape only one grammar can spell, or can reject before the
#   shared seam, carries no equivalence obligation": it pins WHERE the Python
#   representation refuses (class creation) and that the refusal names the very
#   member the corpus omits, which is the only reason this file may stop short
#   of driving `tx.insert` for these five.
#
#   `test_the_declared_structure_classifies_the_corpus_rule` discharges
#   m-case-format.md "Rejected cases": "The harness (and every language
#   implementation) resolves the input against the queried entity's DECLARED
#   value-object structure and asserts the refusal happens pre-SQL with EXACTLY
#   the named rule; a run that accepts the input, or rejects it with a different
#   rule, fails." Reaching that seam needs a raw document, which is what the
#   corpus's own `when.write` is — so the case's document is walked against the
#   declared structure the ENTITY CLASSES compose (never the corpus descriptor,
#   whose own walk `tests/compatibility/test_rejected_sweep.py` already grades),
#   and the classified rule is compared to `then.rejectedRule` exactly.
INCOMPLETE_DOCUMENT_BUILDERS: dict[str, tuple[str, Callable[[], object]]] = {
    "m-value-object-039": (
        "street",
        lambda: ContactAddress(
            city="Oslo", geo=ContactGeo(country="NO", point=ContactPoint(lat=59.9, lon=10.7))
        ),
    ),
    "m-value-object-040": ("country", lambda: ContactGeo(point=ContactPoint(lat=59.9, lon=10.7))),
    "m-value-object-041": ("lat", lambda: ContactPoint(lon=5.3)),
    "m-value-object-042": (
        "geo",
        lambda: ContactAddress(street="3 Harbour Rd", city="Oslo"),
    ),
    "m-value-object-044": ("destination", lambda: Shipment(id=5, name="Express")),
}


def _rejected_write_target(domain_model: DomainModel) -> EntityMetadata:
    """The Entity a rejected `when.write` resolves against (`engine._rejected_target`'s
    own convention): these models declare no family, so it is the model's one Entity —
    unpacking fails loudly if that ever stops holding."""
    (entity,) = domain_model.entities
    return entity


@pytest.mark.parametrize(
    "case_id", sorted(INCOMPLETE_DOCUMENT_BUILDERS), ids=sorted(INCOMPLETE_DOCUMENT_BUILDERS)
)
def test_the_class_grammar_refuses_the_corpus_incomplete_document(case_id: str) -> None:
    member, build = INCOMPLETE_DOCUMENT_BUILDERS[case_id]
    with pytest.raises(ValidationError, match=member):
        build()


@pytest.mark.parametrize(
    "case_id", sorted(INCOMPLETE_DOCUMENT_BUILDERS), ids=sorted(INCOMPLETE_DOCUMENT_BUILDERS)
)
def test_the_declared_structure_classifies_the_corpus_rule(case_id: str) -> None:
    case = _CASES[case_id]
    expected_rule = case_document(case)["then"]["rejectedRule"]
    domain_model = MODELS[_case_model_stem(case_id)]
    model = model_of(domain_model)
    target = _rejected_write_target(domain_model)
    # The case authors its row in the wire spellings a read golden uses, so it
    # decodes to native carriers first — exactly as `engine.run_rejected_case`
    # does — or a type mismatch, not the omission, would be what gets classified.
    authored = cast("Mapping[str, object]", case_document(case)["when"]["write"])
    row = decode_write_row(target, authored, model)
    with pytest.raises(WriteRejectedError) as exc_info:
        validate_write(target, row, model)
    assert exc_info.value.rule == expected_rule


def test_a_complete_document_still_constructs() -> None:
    # The counterpart of the refusals above: every required member supplied is
    # accepted, so the rejections are about absence and nothing else.
    assert (
        Shipment(
            id=5, name="Express", destination=Destination(street="1 Main St", city="Oslo")
        ).destination.city
        == "Oslo"
    )


@pytest.mark.parametrize(
    "case_id", sorted(REJECTED_WRITE_BUILDERS), ids=sorted(REJECTED_WRITE_BUILDERS)
)
def test_idiomatic_write_build_rejects_the_corpus_rule(case_id: str) -> None:
    case = _CASES[case_id]
    expected_rule = case_document(case)["then"]["rejectedRule"]
    port = _RecordingPort()
    db = Database.connect(port, MODELS[REJECTED_WRITE_MODELS[case_id]])
    with pytest.raises(WriteRejectedError) as exc_info:
        db.transact(REJECTED_WRITE_BUILDERS[case_id])
    assert exc_info.value.rule == expected_rule
    assert not port.wrote
