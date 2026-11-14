"""Prepared document patches applied in memory against the same patches applied
by a provider's own mutation SQL (`m-document-codec` *applyPreparedPatches*,
`m-dialect` *Document mutation-expression form*), through the profile's live
provider.

Each object-root case prepares one temporal revision's assignments through the
production preparer once, applies those prepared patches to the stored document
in memory, executes the production statement compiled from that same payload,
and compares the complete persisted document either way. Outside an object root,
which only a table without its generated root-object check can hold, the
provider's actual behavior is recorded per dialect instead, never asserted
equal: a provider without recorded behavior fails rather than inheriting another
provider's. A table adopting the check without validating its rows refuses a
write that would keep such a root.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Final

import pytest

from parallax.core import Attr, Document, DomainModel, TxTemporal, ValueObject, attr
from parallax.core._execution._planning import build_write_planner
from parallax.core.internal.base import SQL_NULL, StructuredDocument
from parallax.core.internal.db_error import DatabaseError
from parallax.core.internal.document_codec import apply_prepared_patches, persisted_document_equal
from parallax.core.internal.entity._model import model_of
from parallax.core.internal.metamodel import AttributeIdentity, EntityIdentity, ValueObjectIdentity
from parallax.core.internal.sql_gen._write import compile_write_step
from parallax.core.internal.write_plan.payload import AssignmentPayload, DocumentPatches
from parallax.core.internal.write_plan.steps import (
    INFINITY,
    STALE_WRITE,
    UNGATED,
    ExactCount,
    MilestoneTarget,
    PlannedAssignments,
    PlannedTemporalRevision,
)
from tests._support.bindings import TEST_BINDING, bound_model

_NAMESPACE = "provider.document_patch"
_TABLE = "patch_voyage"
_STORED_AT: Final = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)


class PatchStop(ValueObject):
    port: Attr[str]
    note: Attr[str | None]


class PatchVoyage(TxTemporal, table=_TABLE, namespace=_NAMESPACE, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    title: Attr[str | None] = attr(max_length=32)
    crew: Attr[int | None]
    fare: Attr[Decimal | None] = attr(precision=18, scale=2)
    ratio: Attr[float | None]
    active: Attr[bool | None]
    sailed: Attr[dt.date | None]
    departed: Attr[dt.datetime | None]
    marks: Attr[tuple[int, ...]]
    route: Attr[PatchStop | None]
    stops: Attr[tuple[PatchStop, ...]]


_MODEL: Final = DomainModel(PatchVoyage)
_META: Final = model_of(_MODEL)
_ENTITY: Final = EntityIdentity(_NAMESPACE, "PatchVoyage")

_STORED: Final[Mapping[str, object]] = {
    "title": "Northbound",
    "crew": 12,
    "fare": "10.50",
    "active": True,
    "marks": [1, 2],
    "route": {"port": "Oslo", "note": "pier 4", "dock": "undeclared inside"},
    "stops": [{"port": "Bergen", "note": None}],
    "legacy": {"kept": [1, "x", None], "flag": False},
    "newerKey": "written by a newer application",
}


@dataclass(frozen=True, slots=True)
class _Patch:
    id: str
    attributes: Mapping[str, object]
    value_objects: Mapping[str, object]


_OBJECT_ROOT_PATCHES: Final = (
    _Patch("string", {"title": "Southbound"}, {}),
    _Patch("integer", {"crew": 13}, {}),
    _Patch("decimal", {"fare": Decimal("11.25")}, {}),
    _Patch("float", {"ratio": 0.125}, {}),
    _Patch("boolean", {"active": False}, {}),
    _Patch("date", {"sailed": dt.date(2024, 2, 29)}, {}),
    _Patch("timestamp", {"departed": dt.datetime(2024, 3, 1, 6, 30, 15, 120, tzinfo=dt.UTC)}, {}),
    _Patch("null-over-present", {"title": None}, {}),
    _Patch("null-over-absent", {"ratio": None}, {}),
    _Patch("present-over-absent", {"sailed": dt.date(2024, 1, 2)}, {}),
    _Patch("array-member", {"marks": (3, 1, 3)}, {}),
    _Patch("empty-array-member", {"marks": ()}, {}),
    _Patch("one-occurrence-replaced-whole", {}, {"route": {"port": "Tromso", "note": None}}),
    _Patch("one-occurrence-nulled", {}, {"route": None}),
    _Patch(
        "many-occurrence-replaced-whole",
        {},
        {"stops": ({"port": "Alesund", "note": "late"}, {"port": "Molde", "note": None})},
    ),
    _Patch("many-occurrence-emptied", {}, {"stops": ()}),
    _Patch(
        "several-in-canonical-order",
        {"crew": 0, "title": "Both", "marks": (9,), "active": None},
        {"stops": ({"port": "Kiel", "note": None},), "route": {"port": "Riga", "note": "x"}},
    ),
)


def _revision(assignments: PlannedAssignments) -> PlannedTemporalRevision:
    return PlannedTemporalRevision(
        entity=_ENTITY,
        target=MilestoneTarget(
            key_attributes=(AttributeIdentity(_ENTITY, "id"),),
            key_values=(1,),
            end_attributes=(AttributeIdentity(_ENTITY, "txEnd"),),
            end_values=(INFINITY,),
        ),
        assignments=assignments,
        concurrency=UNGATED,
        affected_rows=ExactCount(expected=1, on_shortfall=STALE_WRITE),
        predecessor_document_is_object=True,
    )


def _assignments(patch: _Patch) -> PlannedAssignments:
    return PlannedAssignments(
        attributes={
            AttributeIdentity(_ENTITY, name): value for name, value in patch.attributes.items()
        },
        value_objects={
            ValueObjectIdentity(_ENTITY, (name,)): value
            for name, value in patch.value_objects.items()
        },
    )


def _prepared(assignments: PlannedAssignments) -> tuple[AssignmentPayload, DocumentPatches]:
    payload = build_write_planner(bound_model(_META)).payloads.assignments(_ENTITY, assignments)
    (patched,) = (value for value in payload.values if isinstance(value, DocumentPatches))
    return payload, patched


def _root_check_name() -> str:
    root = bound_model(_META).table(_ENTITY).document_root_constraint
    assert root is not None
    return root.check_name


def _seed(profile_run: Any, document: str | None, *, unmanaged: bool = False) -> None:
    """One current row of the entity holding ``document``'s JSON text, or SQL
    NULL where ``document`` is ``None``.

    An ``unmanaged`` table has lost its generated root-object check, as one
    created before the check existed has; only the SQL NULL root also drops the
    column's ``not null``.
    """
    profile_run.reset(_META, {}, TEST_BINDING)
    port = profile_run.port
    if unmanaged:
        port.execute_write(f"alter table px.{_TABLE} drop constraint {_root_check_name()}", [])
    if document is None:
        port.execute_write(f"alter table px.{_TABLE} alter column payload drop not null", [])
    port.execute_write(
        f"insert into px.{_TABLE}(id, in_z, out_z, payload) values (?, ?, 'infinity', ?::jsonb)",
        [1, _STORED_AT, document],
    )


def _execute(profile_run: Any, step: PlannedTemporalRevision, payload: AssignmentPayload) -> int:
    port = profile_run.port
    dialect = port.dialect
    statement = compile_write_step(step, payload, bound_model(_META), dialect)
    return port.execute_write(statement.sql, list(statement.binds))


def _persisted(profile_run: Any) -> object:
    """The row's complete stored document as the provider's document-read seam
    answers it."""
    port = profile_run.port
    dialect = port.dialect
    presence, document = dialect.render_document_pair("t0.payload")
    ((present, raw),) = port.execute(
        f"select {presence}, {document} from px.{_TABLE} t0 where t0.id = ?", [1]
    )
    return dialect.parse_owned_document_read(present, raw)


@pytest.mark.parametrize("patch", _OBJECT_ROOT_PATCHES, ids=lambda patch: patch.id)
def test_prepared_patches_persist_what_applying_them_in_memory_predicts(
    profile_run: Any, patch: _Patch
) -> None:
    _seed(profile_run, json.dumps(_STORED))
    before = _persisted(profile_run)
    assert isinstance(before, StructuredDocument)
    payload, patched = _prepared(_assignments(patch))
    predicted = apply_prepared_patches(before.document, patched.patches)

    assert _execute(profile_run, _revision(payload.assignments), payload) == 1

    persisted = _persisted(profile_run)
    assert isinstance(persisted, StructuredDocument)
    assert persisted_document_equal(predicted, persisted.document), (predicted, persisted.document)
    for undeclared in ("legacy", "newerKey"):
        assert persisted_document_equal(predicted[undeclared], _STORED[undeclared])


# --------------------------------------------------------------------------- #
# Outside an object root, each executable provider's own stored result.       #
# --------------------------------------------------------------------------- #
_EXTERNAL_ROOTS: Final[Mapping[str, str | None]] = {
    "json-null": "null",
    "scalar": '"legacy"',
    "array": '["legacy", "old"]',
    "sql-null": None,
}
_EXTERNAL_ROOT_OUTCOMES: Final[Mapping[str, Mapping[str, object]]] = {
    "postgres": {
        "json-null": [None, {"crew": 5}],
        "scalar": ["legacy", {"crew": 5}],
        "array": ["legacy", "old", {"crew": 5}],
        "sql-null": SQL_NULL,
    },
}


def _recorded[T](table: Mapping[str, Mapping[str, T]], profile_run: Any) -> Mapping[str, T]:
    name = profile_run.port.dialect.name
    recorded = table.get(name)
    if recorded is None:
        pytest.fail(f"no document mutation behavior outside an object root is recorded for {name}")
    return recorded


def _crew_revision() -> tuple[PlannedTemporalRevision, AssignmentPayload]:
    payload, _patched = _prepared(_assignments(_Patch("crew", {"crew": 5}, {})))
    return _revision(payload.assignments), payload


@pytest.mark.parametrize("root", _EXTERNAL_ROOTS, ids=str)
def test_a_patch_outside_an_object_root_does_what_its_provider_does(
    profile_run: Any, root: str
) -> None:
    expected = _recorded(_EXTERNAL_ROOT_OUTCOMES, profile_run)[root]
    _seed(profile_run, _EXTERNAL_ROOTS[root], unmanaged=True)
    step, payload = _crew_revision()
    assert _execute(profile_run, step, payload) == 1
    persisted = _persisted(profile_run)
    if expected is SQL_NULL:
        assert persisted == SQL_NULL
    else:
        assert isinstance(persisted, StructuredDocument)
        assert persisted_document_equal(expected, persisted.document), persisted.document


@pytest.mark.parametrize("root", ["json-null", "scalar", "array"])
def test_a_patch_keeping_a_legacy_non_object_root_is_refused_by_an_unvalidated_check(
    profile_run: Any, root: str
) -> None:
    _seed(profile_run, _EXTERNAL_ROOTS[root], unmanaged=True)
    name = _root_check_name()
    port = profile_run.port
    port.execute_write(
        f"alter table px.{_TABLE} add constraint {name} "
        "check (jsonb_typeof(payload) = 'object') not valid",
        [],
    )
    before = _persisted(profile_run)
    step, payload = _crew_revision()
    with pytest.raises(DatabaseError) as refused:
        _execute(profile_run, step, payload)
    assert (refused.value.category, refused.value.native_code) == ("constraintViolation", "23514")
    assert refused.value.constraint_name == name
    assert _persisted(profile_run) == before
