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

from collections.abc import Callable, Sequence
from decimal import Decimal
from typing import Any, cast

import pytest

from conftest import case_document, compare_binds
from parallax.conformance import api_suite, case_format, models
from parallax.conformance.read_models import Payment
from parallax.conformance.stories import WRITE_STORIES, WriteStory
from parallax.core.db_port import Bind, DbPort, Row
from parallax.core.dialect import POSTGRES
from parallax.core.unit_work import WriteRejectedError
from parallax.snapshot.handle import Database

pytestmark = [pytest.mark.unit, pytest.mark.api_conformance]

_MODELS = models.load_models()
_CASES = {c.case_id: c for c in case_format.load_cases()}
_STORIES = {story.case_id: story for story in WRITE_STORIES}


class _RecordingPort:
    """An in-memory ``m-db-port`` recording every call in order (no Docker)."""

    def __init__(self, *, rows: Sequence[Row] = ()) -> None:
        self.ops: list[tuple[object, ...]] = []
        self.rows = list(rows)

    def execute(self, sql: str, binds: Sequence[Bind]) -> list[Row]:
        self.ops.append(("read", sql, tuple(binds)))
        return [dict(row) for row in self.rows]

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


def _assert_statements(
    port: _RecordingPort, goldens: list[tuple[str, list[object]]], case_id: str
) -> None:
    observed = port.statements()
    assert len(observed) == len(goldens), (case_id, observed, goldens)
    for (sql, binds), (golden_sql, golden_binds) in zip(observed, goldens, strict=True):
        assert sql == golden_sql, (case_id, sql, golden_sql)
        # A graduated verb's bind is a REAL typed value (e.g. `Decimal("5.00")`
        # from an idiomatic entity instance), while the case's own authored
        # golden is a plain YAML literal (`5.00`, a float) — `compare_binds`
        # reconciles the two in exact-Decimal space, same as row grading.
        compare_binds(binds, golden_binds)


def _db(port: _RecordingPort, story: WriteStory) -> Database:
    return Database.connect(port, _MODELS[story.model])


# The no-drift guard grades only EXERCISED stories (`m-api-conformance.md`):
# `GUIDE_ONLY_WRITE_STORY_IDS` (m-unit-work-005/006/009) add a leading
# observing read their mirrored corpus case does not author (the m-opt-lock
# prior-observation rule postdates those cases), so their wire shape cannot
# reproduce the case's own golden DML byte-exact — they are reasoned-skipped
# in the coverage partition instead (`api_suite.CASE_SKIP_REASONS`) and stay
# out of this guard's parametrize sets. `test_story_run.py` still executes
# them for real, proving the (corrected) idiom itself works.
_COMMIT_IDS = sorted(
    s.case_id
    for s in WRITE_STORIES
    if s.kind == "commit" and s.case_id not in api_suite.GUIDE_ONLY_WRITE_STORY_IDS
)
_ABORT_IDS = sorted(s.case_id for s in WRITE_STORIES if s.kind == "abort")


@pytest.mark.parametrize("case_id", _COMMIT_IDS, ids=_COMMIT_IDS)
def test_commit_story_emits_the_golden_dml(case_id: str) -> None:
    story = _STORIES[case_id]
    port = _RecordingPort(rows=[{"id": 1, "owner": "Ada", "balance": 100.00, "version": 1}])
    story.run(_db(port, story))
    _assert_statements(port, _scenario_goldens(case_id), case_id)
    assert port.ops[0] == ("begin",)
    assert port.ops[-1] == ("commit",)
    assert ("rollback",) not in port.ops


@pytest.mark.parametrize("case_id", _ABORT_IDS, ids=_ABORT_IDS)
def test_abort_story_discards_the_buffer_and_keeps_the_reads_golden(case_id: str) -> None:
    # The rolled-back step's DML round trip is graded by the conformance run
    # lane (which executes then aborts); through the developer surface the
    # buffered write is discarded before it reaches the wire, so the guard here
    # is the abort CONTRACT: nothing written, the abort rolled back, reads golden.
    story = _STORIES[case_id]
    port = _RecordingPort(rows=[{"id": 1, "owner": "Ada", "balance": 100.00, "version": 1}])
    story.run(_db(port, story))
    assert not port.wrote, (case_id, port.ops)
    _assert_statements(port, _scenario_goldens(case_id, skip_rollback=True), case_id)
    assert ("rollback",) in port.ops


_GUIDE_ONLY_COMMIT_IDS = sorted(api_suite.GUIDE_ONLY_WRITE_STORY_IDS)


@pytest.mark.parametrize("case_id", _GUIDE_ONLY_COMMIT_IDS, ids=_GUIDE_ONLY_COMMIT_IDS)
def test_guide_only_story_runs_docker_free_without_grading_against_the_corpus_golden(
    case_id: str,
) -> None:
    """`GUIDE_ONLY_WRITE_STORY_IDS` (m-unit-work-005/006/009) add a leading
    observing read their mirrored corpus case does not author — the no-drift
    guard grades only EXERCISED stories (`_COMMIT_IDS` above excludes these
    three), so this asserts only that the corrected idiom runs cleanly
    through the fake port, never a golden-DML comparison. This is deliberately
    still this module's job: `test_write_no_drift.py` is "the story bodies'
    only DB-free driver" (module docstring), and these three guide-only
    stories are still real, executable Usage-Guide examples that must not
    silently break.
    """
    story = _STORIES[case_id]
    port = _RecordingPort(rows=[{"id": 1, "owner": "Ada", "balance": 100.00, "version": 1}])
    story.run(_db(port, story))
    assert port.ops[0] == ("begin",)
    assert port.ops[-1] == ("commit",)
    assert ("rollback",) not in port.ops


def test_boundary_story_withholds_the_callback_value() -> None:
    # m-unit-work-004 (boundary, api-conformance lane): read -> buffered update
    # -> a dependent read force-flushes it inside the still-open scope -> the
    # closure throws. The abort discards even the force-flushed write (the
    # port rolls back) and `transact` raises instead of returning the value.
    story = _STORIES["m-unit-work-004"]
    port = _RecordingPort(rows=[{"id": 1, "owner": "Ada", "balance": 100.00, "version": 1}])
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
# Rejected-case build/buffer-time proof (m-inheritance, COR-3 Phase 8         #
# increment 2): the write-side counterpart of                                 #
# `test_operation_no_drift.test_idiomatic_statement_build_rejects_the_corpus_rule` #
# — `tx.insert` refuses the SAME invalid write the corpus's own rejected      #
# lane grades (`engine.run_rejected_case`), through the SAME model-aware      #
# `validate_write` (`Transaction._buffer`), naming the SAME classified rule.  #
# No golden DML: a rejected write never reaches the port (`api_suite.EXAMPLES`'#
# own `m-inheritance-088` entry is this exact snippet).                       #
# --------------------------------------------------------------------------- #
def test_idiomatic_write_build_rejects_the_corpus_rule() -> None:
    case = _CASES["m-inheritance-088"]
    expected_rule = case_document(case)["then"]["rejectedRule"]
    port = _RecordingPort()
    db = Database.connect(port, _MODELS["payment"])
    with pytest.raises(WriteRejectedError) as exc_info:
        db.transact(lambda tx: tx.insert(Payment(id=10, amount=Decimal("200.00"))))
    assert exc_info.value.rule == expected_rule
    assert not port.wrote
