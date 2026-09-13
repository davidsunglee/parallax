"""The conformance engine's given-state seeding: ``given.corrupt`` realized as
whole-document replacements over a read case's loaded fixtures, and
``given.apply`` applied verbatim before a run lane's first step.

Docker-free, over ports that answer one stored document and record what was
written back.
"""

from __future__ import annotations

import copy
import dataclasses
import functools
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, cast

import pytest

from parallax.conformance import case_format, models
from parallax.conformance._mechanism.envelope import EngineError
from parallax.conformance._mechanism.given_state import apply_given_apply, apply_given_corrupt
from parallax.conformance._mechanism.model_facts import (
    case_entity,
    load_case_domain_model,
    load_case_metamodel,
)
from parallax.conformance.temporal_state import TemporalShadow
from parallax.core.db_port import (
    DatabaseConnection,
    JsonDocument,
    PipelineStatement,
    Row,
    TransactionOutcome,
)
from parallax.core.dialect import POSTGRES, Dialect
from tests._support.db_port import body_outcome
from tests.unit.conformance._recording_ports import FakeWritePort


@functools.cache
def _corpus_by_id() -> Mapping[str, case_format.Case]:
    return {case.case_id: case for case in case_format.load_cases()}


def _load_case(case_id: str) -> case_format.Case:
    return _corpus_by_id()[case_id]


class _CorruptionPort:
    """A port answering one stored document and recording what was written back."""

    dialect: Dialect = POSTGRES

    def __init__(self, stored: object) -> None:
        self._stored = stored
        self.reads: list[tuple[str, list[object]]] = []
        self.writes: list[tuple[str, list[object]]] = []

    def execute(
        self, sql: str, binds: Sequence[object], document_reads: Sequence[tuple[int, int]] = ()
    ) -> list[Row]:
        self.reads.append((sql, list(binds)))
        return [(copy.deepcopy(self._stored),)]

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        self.writes.append((sql, list(binds)))
        return 1

    def execute_pipeline(self, statements: Sequence[PipelineStatement]) -> list[list[Row]]:
        return [
            self.execute(statement.sql, statement.binds, statement.document_reads)
            for statement in statements
        ]

    def transaction[T](
        self, body: Callable[[DatabaseConnection], T], *, isolation: str | None = None
    ) -> TransactionOutcome[T]:  # pragma: no cover - a corruption runs outside one
        return body_outcome(self, body)


def _corrupting(case_id: str, stored: object, *entries: Mapping[str, object]) -> _CorruptionPort:
    """Apply *entries* over ``case_id``'s model against a port holding *stored*."""
    case = _load_case(case_id)
    if entries:
        document = dict(case.document)
        document["given"] = {"corrupt": list(entries)}
        case = dataclasses.replace(case, document=document)
    port = _CorruptionPort(stored)
    apply_given_corrupt(case, models.accepted_model_of(load_case_domain_model(case)), port)
    return port


def test_given_corrupt_writes_the_authored_value_into_the_stored_document() -> None:
    port = _corrupting(
        "m-snapshot-read-049", {"day": "2026-01-15", "clock": "09:30:00", "token": "old"}
    )
    assert [binds for _sql, binds in port.reads] == [[101], [102]]
    assert all("from stream_coordinate where id = %s" in sql for sql, _ in port.reads)
    written = [cast("JsonDocument", binds[0]).value for _sql, binds in port.writes]
    assert written == [
        {"day": "2026-01-15", "clock": "09:30:00", "token": "NOT-A-UUID"},
        {"day": "2026-01-15", "clock": None, "token": "old"},
    ]
    assert all(
        sql == "update stream_coordinate set coordinates = %s where id = %s"
        for sql, _binds in port.writes
    )


def test_given_corrupt_reads_a_document_its_provider_returned_as_text() -> None:
    port = _corrupting(
        "m-snapshot-read-049",
        '{"day": "2026-01-15", "clock": "09:30:00", "token": "old"}',
    )
    written = cast("dict[str, object]", cast("JsonDocument", port.writes[0][1][0]).value)
    assert written["token"] == "NOT-A-UUID"


def test_given_corrupt_descends_into_a_value_object_document() -> None:
    port = _corrupting(
        "m-storage-layout-027",
        {"street": "4 Main", "city": "Boston"},
        {
            "entity": "parallax.compatibility.ClassificationTwinItem",
            "key": 4,
            "member": ["profile", "street"],
            "value": 7,
        },
    )
    assert cast("JsonDocument", port.writes[0][1][0]).value == {"street": 7, "city": "Boston"}


def test_given_corrupt_replaces_a_whole_occurrence_under_columns() -> None:
    # `[profile]` addresses the occurrence itself, whose Structured Column holds
    # the whole stored value — which is how a case authors the wrong-KIND verdict
    # for a top-level Value Object under either layout.
    port = _corrupting(
        "m-storage-layout-027",
        {"street": "4 Main", "city": "Boston"},
        {
            "entity": "parallax.compatibility.ClassificationTwinItem",
            "key": 4,
            "member": ["profile"],
            "value": "not-an-object",
        },
    )
    assert cast("JsonDocument", port.writes[0][1][0]).value == "not-an-object"


def test_given_corrupt_indexes_an_array_backed_structured_column() -> None:
    # A top-level `many` occurrence under `Columns` stores an ARRAY at the root of
    # its own Structured Column, so the address's first position indexes the
    # column's whole value rather than a member of a document.
    port = _corrupting(
        "m-storage-layout-029",
        [{"code": "A"}, {"code": "B"}],
        {
            "entity": "parallax.compatibility.WriteTwinItem",
            "key": 1,
            "member": ["marks", 0, "code"],
            "value": 7,
        },
    )
    assert cast("JsonDocument", port.writes[0][1][0]).value == [{"code": 7}, {"code": "B"}]


def test_given_corrupt_addresses_an_inherited_member_by_its_declaration() -> None:
    # `Book` inherits `Publication.title`, whose placement stays keyed by the
    # declaring identity, so a corruption addressing the concrete row Entity has
    # to resolve the declaration rather than an identity that Entity would own.
    port = _corrupting(
        "m-inheritance-126",
        {"title": "Dune", "detail": "hardback", "pages": 412},
        {
            "entity": "parallax.compatibility.Book",
            "key": 1,
            "member": ["title"],
            "value": 7,
        },
    )
    assert "from publication_book where id = %s" in port.reads[0][0]
    assert cast("JsonDocument", port.writes[0][1][0]).value == {
        "title": 7,
        "detail": "hardback",
        "pages": 412,
    }


def test_given_corrupt_refuses_a_member_kept_in_a_column_of_its_own() -> None:
    with pytest.raises(EngineError, match="does not place inside a Structured Column"):
        _corrupting(
            "m-snapshot-read-049",
            {},
            {
                "entity": "parallax.compatibility.StreamCoordinate",
                "key": 101,
                "member": ["id"],
                "value": None,
            },
        )


def test_given_corrupt_refuses_a_temporal_entity_before_reading_anything() -> None:
    # A temporal Entity's rows are keyed by the model key plus each axis's end
    # instant, so one `key` value addresses a milestone CHAIN. The address is
    # refused rather than resolved to whichever milestone a select happened to
    # answer with, and refused before any statement is issued.
    port = _CorruptionPort({})
    case = _load_case("m-bitemp-write-001")
    document = dict(case.document)
    document["given"] = {
        "corrupt": [
            {
                "entity": "parallax.compatibility.Position",
                "key": 1,
                "member": ["val"],
                "value": "not-a-decimal",
            }
        ]
    }
    with pytest.raises(EngineError, match="a temporal Entity: its model primary key"):
        apply_given_corrupt(
            dataclasses.replace(case, document=document),
            models.accepted_model_of(load_case_domain_model(case)),
            port,
        )
    assert port.reads == [] and port.writes == []


def test_given_corrupt_refuses_a_temporal_entry_before_an_earlier_legal_one_applies() -> None:
    # The temporal refusal is about the CASE rather than about one entry, so a
    # legal entry standing before a temporal one must not have written a row by
    # the time the list is refused — which is where the reference harness stands
    # too: it judges every entry's Entity before any row lands.
    port = _CorruptionPort({"title": "Dune", "detail": "hardback", "pages": 412})
    case = _load_case("m-inheritance-126")
    document = dict(case.document)
    document["given"] = {
        "corrupt": [
            {
                "entity": "parallax.compatibility.Book",
                "key": 1,
                "member": ["title"],
                "value": 7,
            },
            {
                "entity": "parallax.compatibility.Charter",
                "key": 1,
                "member": ["terms", "clause"],
                "value": 7,
            },
        ]
    }
    with pytest.raises(EngineError, match="a temporal Entity: its model primary key"):
        apply_given_corrupt(
            dataclasses.replace(case, document=document),
            models.accepted_model_of(load_case_domain_model(case)),
            port,
        )
    assert port.reads == [] and port.writes == []


def test_given_corrupt_reports_how_many_rows_its_key_answered_with() -> None:
    # The count is reported rather than assumed to be zero: a key that selected
    # too many rows is a different fault from one that selected none, and reading
    # "the fixtures do not hold it" for either would misdescribe one of them.
    class _Empty(_CorruptionPort):
        def execute(
            self, sql: str, binds: Sequence[object], document_reads: Sequence[tuple[int, int]] = ()
        ) -> list[Row]:
            return []

    case = _load_case("m-snapshot-read-049")
    with pytest.raises(EngineError, match="answer with 0 row\\(s\\) rather than one"):
        apply_given_corrupt(
            case, models.accepted_model_of(load_case_domain_model(case)), _Empty({})
        )


def test_given_corrupt_descends_a_nested_occurrence_path() -> None:
    port = _corrupting(
        "m-storage-layout-018",
        {"displayName": "Ada", "address": {"city": "Oslo", "geo": {"country": "NO"}}},
        {
            "entity": "parallax.compatibility.Traveler",
            "key": 1,
            "member": ["address", "geo", "country"],
            "value": 7,
        },
    )
    written = cast("dict[str, Any]", cast("JsonDocument", port.writes[0][1][0]).value)
    assert written["address"] == {"city": "Oslo", "geo": {"country": 7}}


def test_a_case_declaring_no_corruption_writes_nothing() -> None:
    case = _load_case("m-snapshot-read-049")
    document = dict(case.document)
    document["given"] = {"fixtures": True}
    port = _CorruptionPort({})
    apply_given_corrupt(
        dataclasses.replace(case, document=document),
        models.accepted_model_of(load_case_domain_model(case)),
        port,
    )
    assert port.reads == [] and port.writes == []


def test_apply_given_apply_is_a_no_op_when_given_carries_no_apply_list() -> None:
    case = case_format.Case(
        path=Path("m-unit-work-999-synthetic.yaml"),
        case_id="m-unit-work-999",
        shape="conflict",
        tags=("m-unit-work", "slice-snapshot-1"),
        model="models/account.yaml",
        document={"model": "models/account.yaml", "given": {"fixtures": True}},
    )
    port = FakeWritePort()
    shadow = TemporalShadow()
    meta = load_case_metamodel(_load_case("m-txtime-write-002"))
    model = meta
    apply_given_apply(case, port, shadow)
    assert port.writes == []
    # A case that applies nothing leaves the tracker's account of the stored rows
    # whole — including for a key it tracks no milestone of — which is what a keyed
    # temporal write over a document-mapped target depends on.
    assert shadow.accounts_for(
        model, case_entity(model, "parallax.compatibility.Balance"), {"id": 1}
    )
