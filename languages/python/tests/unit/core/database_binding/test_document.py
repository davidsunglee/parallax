"""m-database-binding: the generic binding document codec over a backend's values."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import pytest

from parallax.core.internal.database_binding import (
    BindingError,
    LocationCodec,
    binding_document,
    binding_from_document,
)
from parallax.core.internal.metamodel import EntityIdentity


@dataclass(frozen=True, slots=True)
class _Place:
    """A two-component location, so an entry can carry some components and not others."""

    store: str
    database: str

    @property
    def qualifier(self) -> tuple[str, ...]:
        return (self.store, self.database)


@dataclass(frozen=True, slots=True)
class _Entry:
    location: _Place | None
    name: str | None


_CODEC = LocationCodec(
    backend="twopart",
    keys=("store", "database"),
    location_type=_Place,
    table_type=_Entry,
    sequence_type=_Entry,
    load=lambda components: _Place(components["store"], components["database"]),
    dump=lambda place: {"store": place.store, "database": place.database},
    table=_Entry,
    sequence=_Entry,
)


def _issues(document: object) -> list[tuple[str, tuple[str, ...]]]:
    with pytest.raises(BindingError) as raised:
        binding_from_document(document, _CODEC)
    return [(issue.code, issue.path) for issue in raised.value.issues]


def _document(**sections: object) -> dict[str, object]:
    return {"format_version": 1, "backend": "twopart", **sections}


def test_an_entry_carries_every_location_component_or_none() -> None:
    parts = binding_from_document(
        _document(entities={"Order": {"store": "s", "database": "d"}, "Line": {"table": "l"}}),
        _CODEC,
    )
    assert parts.entities == {
        EntityIdentity(None, "Line"): _Entry(None, "l"),
        EntityIdentity(None, "Order"): _Entry(_Place("s", "d"), None),
    }
    assert _issues(_document(entities={"Order": {"store": "s", "table": "o"}})) == [
        ("binding-field-missing", ("entities", "Order", "database"))
    ]


def test_normalized_maps_are_frozen_in_canonical_key_order() -> None:
    place = {"store": "s", "database": "d"}
    parts = binding_from_document(
        _document(
            namespaces={"b": place, "a": place},
            entities={"z.Order": {}, "Order": {}, "a.Order": {}},
            sequences={"b": {}, "B": {}},
        ),
        _CODEC,
    )
    assert list(parts.namespaces) == ["a", "b"]
    assert [identity.canonical for identity in parts.entities] == ["Order", "a.Order", "z.Order"]
    assert list(parts.sequences) == ["B", "b"]
    with pytest.raises(TypeError):
        parts.namespaces["c"] = _Place("s", "d")  # pyright: ignore[reportIndexIssue]


def test_a_key_that_is_not_text_is_refused_at_its_spelling() -> None:
    assert _issues(_document(namespaces={1: {"store": "s", "database": "d"}})) == [
        ("binding-namespace-key-invalid", ("namespaces", "1"))
    ]
    assert _issues(_document(sequences={None: {}})) == [
        ("binding-sequence-key-invalid", ("sequences", "None"))
    ]


@pytest.mark.parametrize("version", [True, 1.0, "1", 2])
def test_only_the_integer_format_version_one_is_read(version: object) -> None:
    assert _issues({"format_version": version, "backend": "twopart", "default": "x"}) == [
        ("binding-version-unsupported", ("format_version",))
    ]


def test_typed_values_of_the_wrong_type_project_to_refused_document_values() -> None:
    document = binding_document(
        _CODEC,
        default={"store": "s", "database": "d"},
        namespaces=["a"],
        entities={"Order": _Place("s", "d"), "Line": _Entry(_Place("s", ""), None)},
    )
    assert _issues(document) == [
        ("binding-value-invalid", ("default",)),
        ("binding-identifier-invalid", ("entities", "Line", "database")),
        ("binding-value-invalid", ("entities", "Order")),
        ("binding-value-invalid", ("namespaces",)),
    ]


def test_projection_spells_canonical_values_as_their_document() -> None:
    parts = binding_from_document(
        _document(
            default={"store": "s", "database": "d"},
            entities={"x.Order": {"table": "orders"}},
            sequences={},
        ),
        _CODEC,
    )
    document: Mapping[str, object] = binding_document(
        _CODEC,
        default=parts.default,
        namespaces=parts.namespaces,
        entities=parts.entities,
        sequences=parts.sequences,
    )
    assert document == _document(
        default={"store": "s", "database": "d"}, entities={"x.Order": {"table": "orders"}}
    )
