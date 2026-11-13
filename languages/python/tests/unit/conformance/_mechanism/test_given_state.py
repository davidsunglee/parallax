"""The conformance engine's given-state seeding: ``given.corrupt`` realized as
whole-document replacements over a read case's loaded fixtures.

Docker-free, over ports that answer one stored document and record what was
written back.
"""

from __future__ import annotations

import copy
import dataclasses
from collections.abc import Callable, Mapping, Sequence
from typing import Any, cast

import pytest

from parallax.conformance import case_format, models
from parallax.conformance._mechanism.envelope import UnclassifiedEngineError
from parallax.conformance._mechanism.given_state import (
    apply_given_corrupt,
)
from parallax.conformance._mechanism.model_facts import (
    load_case_domain_model,
    load_case_metamodel,
    load_case_setup_metamodel,
)
from parallax.core.internal.db_port import (
    DatabaseConnection,
    OrderedWriteTransport,
    PipelineStatement,
    Row,
    StructuredDocument,
    TransactionOutcome,
)
from parallax.core.internal.dialect import POSTGRES, Dialect
from tests._support.case_corpus import case as corpus_case
from tests._support.db_port import body_outcome


def _load_case(case_id: str) -> case_format.Case:
    return corpus_case(case_id)


class _CorruptionPort:
    """A port answering one stored document and recording what was written back."""

    dialect: Dialect = POSTGRES
    ordered_write_transport: OrderedWriteTransport | None = None

    def __init__(self, stored: object) -> None:
        self._stored = stored
        self.reads: list[tuple[str, list[object]]] = []
        self.writes: list[tuple[str, list[object]]] = []

    def execute(
        self,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[tuple[int, int]] = (),
        *,
        read_only: bool = False,
    ) -> list[Row]:
        self.reads.append((sql, list(binds)))
        return [(copy.deepcopy(self._stored),)]

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        self.writes.append((sql, list(binds)))
        return 1

    def execute_pipeline(
        self, statements: Sequence[PipelineStatement], *, read_only: bool = False
    ) -> list[list[Row]]:
        return [
            self.execute(
                statement.sql, statement.binds, statement.document_reads, read_only=read_only
            )
            for statement in statements
        ]

    def transaction[T](
        self,
        body: Callable[[DatabaseConnection], T],
        *,
        isolation: str | None = None,
        access_mode: str | None = None,
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


def test_given_corrupt_reads_a_document_its_provider_returned_as_text() -> None:
    port = _corrupting(
        "m-snapshot-read-049",
        '{"day": "2026-01-15", "clock": "09:30:00", "token": "old"}',
    )
    written = cast("dict[str, object]", cast("StructuredDocument", port.writes[0][1][0]).document)
    assert written["token"] == "NOT-A-UUID"


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
    assert "from px.publication_book where id = ?" in port.reads[0][0]
    assert cast("StructuredDocument", port.writes[0][1][0]).document == {
        "title": 7,
        "detail": "hardback",
        "pages": 412,
    }


def test_given_corrupt_refuses_a_member_kept_in_a_column_of_its_own() -> None:
    with pytest.raises(UnclassifiedEngineError, match="does not place inside a Structured Column"):
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
    case = _load_case("m-temporal-write-017")
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
    with pytest.raises(UnclassifiedEngineError, match="a temporal Entity: its model primary key"):
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
    with pytest.raises(UnclassifiedEngineError, match="a temporal Entity: its model primary key"):
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
            self,
            sql: str,
            binds: Sequence[object],
            document_reads: Sequence[tuple[int, int]] = (),
            *,
            read_only: bool = False,
        ) -> list[Row]:
            return []

    case = _load_case("m-snapshot-read-049")
    with pytest.raises(UnclassifiedEngineError, match="answer with 0 row\\(s\\) rather than one"):
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
    written = cast("dict[str, Any]", cast("StructuredDocument", port.writes[0][1][0]).document)
    assert written["address"] == {"city": "Oslo", "geo": {"country": 7}}


def test_given_corrupt_addresses_a_row_only_the_provisioning_model_declares() -> None:
    # The read lanes hand corruption the model that provisioned the rows, so an
    # Entity the reader omits is still addressable.
    case = _load_case("m-inheritance-151")
    document = dict(case.document)
    document["given"] = {
        **cast("Mapping[str, object]", document["given"]),
        "corrupt": [
            {"entity": "parallax.compatibility.Den", "key": 1, "member": ["name"], "value": 7}
        ],
    }
    case = dataclasses.replace(case, document=document)
    port = _CorruptionPort({"name": "Council Rock"})

    apply_given_corrupt(case, load_case_setup_metamodel(case), port)

    assert [cast("StructuredDocument", binds[0]).document for _sql, binds in port.writes] == [
        {"name": 7}
    ]
    assert port.writes[0][0] == "update px.den_document set payload = ? where id = ?"
    with pytest.raises(KeyError, match="Den"):
        apply_given_corrupt(case, load_case_metamodel(case), _CorruptionPort({}))
