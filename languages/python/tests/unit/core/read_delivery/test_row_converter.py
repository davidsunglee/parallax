"""A bound converter's flat-row publisher: prepared once on first request,
shared by every later caller of that converter, and never by another."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest

from parallax.core import predicate as oa
from parallax.core.dialect import POSTGRES
from parallax.core.entity._layout import CatalogedModel
from parallax.core.metamodel import EntityIdentity
from parallax.core.read_delivery import _row_converter
from parallax.core.read_delivery._page import (
    ROOT_LEVEL,
    PageBuilder,
    ViewSchema,
    page_rows,
    state_for,
)
from parallax.core.read_delivery._row_converter import ReadRowConverter, RowPublisher, bind
from parallax.core.sql_gen._compile import CompiledRead
from parallax.core.temporal_read import Pin
from tests._support.document_reads import folded_names
from tests._support.sql import compile_read
from tests.unit._corpus_model_support import model, target
from tests.unit._prepared_read_support import result_row

ANIMAL = model("animal")
_NAMESPACE = "parallax.compatibility"
_CALLERS = 8


def _animal_read() -> tuple[CompiledRead, ReadRowConverter]:
    compiled = compile_read(
        oa.TrueNode(), ANIMAL, POSTGRES, target(ANIMAL, "Animal"), result_form="row"
    )
    return compiled, bind(CatalogedModel(ANIMAL), compiled.result_contract, compiled.projection)


def _published(compiled: CompiledRead, converter: ReadRowConverter, kind: str) -> dict[str, Any]:
    selected = folded_names(compiled.statement.sql, compiled.document_reads)
    cells = dict.fromkeys(selected) | {"id": 1, "name": "Rex", "kind": kind}
    builder = PageBuilder(ViewSchema.of())
    index, resolved, _document, variant = converter.convert_row(
        result_row(compiled, cells), builder, source=ROOT_LEVEL
    )
    rows = page_rows(builder.finish((index,), Pin()))
    (root,) = rows.roots
    return converter.row_publisher().publish(resolved, state_for(rows, root).member_row, variant)


def _counting_preparations(patched: pytest.MonkeyPatch) -> list[RowPublisher]:
    prepared: list[RowPublisher] = []
    prepare = vars(_row_converter)["_prepare_row_publisher"]

    def counting(*args: Any) -> RowPublisher:
        publisher = prepare(*args)
        prepared.append(publisher)
        return publisher

    patched.setattr(_row_converter, "_prepare_row_publisher", counting)
    return prepared


def test_one_converter_reuses_one_publisher_and_another_prepares_its_own(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _counting_preparations(monkeypatch)
    compiled, converter = _animal_read()
    _, other = _animal_read()

    first = converter.row_publisher()
    assert converter.row_publisher() is first
    assert prepared == [first]

    assert other.row_publisher() is not first
    assert len(prepared) == 2
    assert _published(compiled, converter, "dog") == _published(compiled, other, "dog")


def test_concurrent_first_requests_wait_for_one_complete_publisher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepare = vars(_row_converter)["_prepare_row_publisher"]
    started = threading.Event()
    release = threading.Event()
    callers = threading.Barrier(_CALLERS)
    prepared: list[RowPublisher] = []

    def delayed(*args: Any) -> RowPublisher:
        started.set()
        assert release.wait(timeout=2)
        publisher = prepare(*args)
        prepared.append(publisher)
        return publisher

    monkeypatch.setattr(_row_converter, "_prepare_row_publisher", delayed)
    _, converter = _animal_read()

    def request(_index: int) -> RowPublisher:
        callers.wait()
        return converter.row_publisher()

    with ThreadPoolExecutor(max_workers=_CALLERS) as pool:
        futures = tuple(pool.submit(request, index) for index in range(_CALLERS))
        assert started.wait(timeout=2)
        time.sleep(0.05)
        assert not any(future.done() for future in futures)
        release.set()
        publishers = tuple(future.result() for future in futures)

    assert prepared == [publishers[0]]
    assert all(publisher is publishers[0] for publisher in publishers)


def test_a_failed_preparation_leaves_none_and_a_later_request_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepare = vars(_row_converter)["_prepare_row_publisher"]
    attempts: list[int] = []

    def failing_once(*args: Any) -> RowPublisher:
        attempts.append(len(attempts))
        if len(attempts) == 1:
            raise RuntimeError("preparation failed")
        return prepare(*args)

    monkeypatch.setattr(_row_converter, "_prepare_row_publisher", failing_once)
    compiled, converter = _animal_read()
    _, fresh = _animal_read()

    with pytest.raises(RuntimeError, match="preparation failed"):
        converter.row_publisher()
    retried = converter.row_publisher()

    assert attempts == [0, 1]
    assert converter.row_publisher() is retried
    assert _published(compiled, converter, "cat") == _published(compiled, fresh, "cat")


def test_a_publisher_serves_only_the_pairs_a_row_can_resolve_to() -> None:
    compiled, converter = _animal_read()
    publisher = converter.row_publisher()
    root = EntityIdentity(_NAMESPACE, "Animal")
    dog = EntityIdentity(_NAMESPACE, "Dog")

    assert _published(compiled, converter, "dog")["familyVariant"] == "Dog"
    assert "familyVariant" not in _published(compiled, converter, "zebra")
    member_row = (None,) * len(CatalogedModel(ANIMAL).layouts.entity(dog).members)
    for concrete, variant in ((dog, "Cat"), (dog, None), (root, "Dog")):
        with pytest.raises(KeyError):
            publisher.publish(concrete, member_row, variant)
    assert converter.row_publisher() is publisher
