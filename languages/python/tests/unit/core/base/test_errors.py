"""The root every Parallax error stands on: construction, rendering, pickling."""

from __future__ import annotations

import pickle
import traceback

import pytest

from parallax.core import (
    ConflictError,
    ConnectionAcquisitionError,
    CredentialResolutionError,
    DatabaseError,
    DatabaseStartupError,
    EditError,
    EditViolation,
    InternalError,
    MetamodelValidationError,
    NoResultFound,
    ParallaxError,
    TooManyResultsFound,
    TransactionRollbackError,
    UnloadedRelationshipError,
    UsageError,
    WritePreconditionError,
)
from parallax.core.metamodel import EntityIdentity, EntityLocation, MetamodelIssue
from parallax.core.read_delivery import InvalidData, InvalidDataError, StoredDataIssue
from parallax.core.read_delivery._page import CONTINUATION_ORDER_NOT_TOTAL, invalid_result_refusal
from parallax.core.write_plan import ObjectKey
from parallax.descriptor import DescriptorError, DescriptorViolation

_ORDER = EntityIdentity("shop", "Order")


def _invalid_root() -> InvalidData[object]:
    return InvalidData(
        issues=frozenset(
            {StoredDataIssue("stored-data-attribute-null", _ORDER, path=(), stored_value=None)}
        ),
        data=None,
        object_key=ObjectKey(_ORDER, (("id", 42),)),
        version=None,
        edge=None,
        ordinal=0,
    )


_KEPT: tuple[tuple[ParallaxError, type[ParallaxError], str], ...] = (
    (UsageError("query-clause-invalid", "m"), UsageError, "query-clause-invalid"),
    (InternalError("sql-generation-failed", "m"), InternalError, "sql-generation-failed"),
    (
        EditError((EditViolation("edit-read-only", EntityLocation(_ORDER), "total"),)),
        UsageError,
        "edit-rejected",
    ),
    (
        MetamodelValidationError(
            (MetamodelIssue("metamodel-entity-unknown", EntityLocation(_ORDER)),)
        ),
        UsageError,
        "model-formation-rejected",
    ),
    (UnloadedRelationshipError("lines"), UsageError, "relationship-unloaded"),
    (
        DescriptorError("descriptor-invalid-syntax", "m", format="json", line=1, column=2),
        UsageError,
        "descriptor-invalid-syntax",
    ),
    (NoResultFound("m"), ParallaxError, "no-result-found"),
    (TooManyResultsFound("m"), ParallaxError, "too-many-results-found"),
    (
        invalid_result_refusal((_invalid_root(),), edition="2026-09-a"),
        ParallaxError,
        "result-data-invalid",
    ),
    (ConflictError("optimistic-lock-conflict", "m"), ParallaxError, "optimistic-lock-conflict"),
    (
        WritePreconditionError(_ORDER, {"id": 42}, 3),
        ConflictError,
        "write-precondition-failed",
    ),
    (
        DatabaseError(category="deadlock", native_code="40P01", message="m"),
        ParallaxError,
        "database-statement-failed",
    ),
    (
        ConnectionAcquisitionError("m", reason="timeout"),
        ParallaxError,
        "connection-acquisition-failed",
    ),
    (
        DatabaseStartupError("m", route="writer", phase="probe"),
        ParallaxError,
        "database-startup-failed",
    ),
    (CredentialResolutionError("m"), ParallaxError, "credential-resolution-failed"),
    (
        TransactionRollbackError(ValueError("trigger"), RuntimeError("rollback")),
        ParallaxError,
        "transaction-rollback-failed",
    ),
)


@pytest.mark.parametrize(("error", "parent", "code"), _KEPT, ids=lambda v: type(v).__name__)
def test_every_kept_class_stands_on_its_parent_with_its_code(
    error: ParallaxError, parent: type[ParallaxError], code: str
) -> None:
    assert isinstance(error, parent)
    assert error.code == code
    assert error.args[0] == code
    assert str(error) == f"{code}: {error.args[1]}"
    assert not isinstance(error, ValueError | TypeError | RuntimeError | LookupError)


@pytest.mark.parametrize(
    "code", ["", "Upper-case", "under_score", "double--hyphen", "-leading", "trailing-", "a b"]
)
def test_a_code_that_is_not_lowercase_hyphenated_words_is_refused(code: str) -> None:
    with pytest.raises(ValueError, match="is not an error code"):
        UsageError(code, "m")


def test_the_root_has_no_writable_code() -> None:
    error = UsageError("query-clause-invalid", "m")
    with pytest.raises(AttributeError):
        error.code = "other"  # pyright: ignore[reportAttributeAccessIssue] - the refusal under test


def test_an_unhandled_error_renders_its_class_code_and_message() -> None:
    error = ConflictError("optimistic-lock-conflict", "shop.Order: a concurrent write won")
    (line,) = traceback.format_exception_only(error)
    assert line.endswith(
        "ConflictError: optimistic-lock-conflict: shop.Order: a concurrent write won\n"
    )


def test_only_a_conflict_its_raise_site_called_transient_is_transient() -> None:
    assert not UsageError("query-clause-invalid", "m").is_transient
    assert not InternalError("sql-generation-failed", "m").is_transient
    assert not ConflictError("missing-target", "m").is_transient
    assert ConflictError("optimistic-lock-conflict", "m", transient=True).is_transient
    assert not WritePreconditionError(_ORDER, {"id": 42}, 3).is_transient


def test_a_conflict_names_the_row_it_hit_read_only() -> None:
    key = {"id": 42}
    conflict = ConflictError("stale-write", "m", entity="shop.Order", key=key)
    key["id"] = 7
    assert (conflict.entity, conflict.key) == ("shop.Order", {"id": 42})
    assert conflict.key is not None
    with pytest.raises(TypeError):
        conflict.key["id"] = 7  # pyright: ignore[reportIndexIssue] - the refusal under test
    assert (ConflictError("stale-write", "m").entity, ConflictError("stale-write", "m").key) == (
        None,
        None,
    )


def test_a_precondition_failure_names_its_row_by_canonical_entity_name() -> None:
    failure = WritePreconditionError(_ORDER, {"id": 42}, 3)
    assert (failure.entity, failure.key, failure.expected) == ("shop.Order", {"id": 42}, 3)


def _round_trip[E: ParallaxError](error: E) -> E:
    error.add_note("a note travels with it")
    restored = pickle.loads(pickle.dumps(error))
    assert type(restored) is type(error)
    assert restored.args == error.args
    assert restored.__notes__ == ["a note travels with it"]
    return restored


def test_a_conflict_survives_pickling_with_its_fields() -> None:
    restored = _round_trip(
        ConflictError(
            "optimistic-lock-conflict", "m", entity="shop.Order", key={"id": 42}, transient=True
        )
    )
    assert (restored.entity, restored.key, restored.is_transient) == (
        "shop.Order",
        {"id": 42},
        True,
    )


def test_a_precondition_failure_survives_pickling_with_its_fields() -> None:
    restored = _round_trip(WritePreconditionError(_ORDER, {"id": 42}, 3))
    assert (restored.entity, restored.key, restored.expected) == ("shop.Order", {"id": 42}, 3)


def test_an_invalid_data_refusal_survives_pickling_still_frozen() -> None:
    restored = _round_trip(invalid_result_refusal((_invalid_root(),), edition="2026-09-a"))
    assert restored.invalid_data == (_invalid_root(),)
    assert restored.edition == "2026-09-a"
    with pytest.raises(AttributeError):
        restored._edition = "other"  # pyright: ignore[reportPrivateUsage] - the refusal under test


def test_a_continuation_tie_refusal_survives_pickling_with_its_coordinate() -> None:
    restored = _round_trip(
        InvalidDataError(CONTINUATION_ORDER_NOT_TOTAL, "m", coordinate=(2, b"\x00"))
    )
    assert restored.coordinate == (2, b"\x00")
    assert (restored.invalid_data, restored.edition) == ((), None)


def test_a_descriptor_error_survives_pickling_with_its_phase_fields() -> None:
    syntax = _round_trip(
        DescriptorError("descriptor-invalid-syntax", "m", format="yaml", line=3, column=4)
    )
    assert (syntax.format, syntax.line, syntax.column, syntax.violations) == ("yaml", 3, 4, ())
    violation = DescriptorViolation(path=("entities", 0), rule="required", message="m")
    schema = _round_trip(DescriptorError("descriptor-schema-invalid", "m", violations=(violation,)))
    assert schema.violations == (violation,)
    bare = _round_trip(DescriptorError("descriptor-value-invalid", "m"))
    assert (bare.format, bare.violations) == (None, ())


def test_an_unloaded_relationship_is_absent_to_hasattr_and_getattr() -> None:
    class Node:
        @property
        def lines(self) -> object:
            raise UnloadedRelationshipError("lines")

    node = Node()
    assert not hasattr(node, "lines")
    assert getattr(node, "lines", "absent") == "absent"
    with pytest.raises(UsageError) as unloaded:
        _ = node.lines
    assert isinstance(unloaded.value, AttributeError)
    assert isinstance(unloaded.value, UnloadedRelationshipError)
    assert unloaded.value.path == "lines"
