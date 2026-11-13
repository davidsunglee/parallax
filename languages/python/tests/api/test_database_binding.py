"""Authoring a PostgreSQL database binding in code, JSON, and YAML."""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping

import pytest

from parallax.core import BindingError, BindingIssue, UsageError
from parallax.core.introspection import EntityIdentity
from parallax.postgres import PostgresBinding, PostgresLocation, PostgresSequence, PostgresTable


def _binding() -> PostgresBinding:
    return PostgresBinding(
        default=PostgresLocation(schema="app"),
        namespaces={"audit": PostgresLocation(schema="audit")},
        entities={"commerce.Customer": PostgresTable(schema="crm", name="customer_master")},
        sequences={"documentNumbers": PostgresSequence(schema="shared", name="document_numbers")},
    )


_YAML = """\
format_version: 1
backend: postgres
default:
  schema: app
namespaces:
  audit:
    schema: audit
entities:
  commerce.Customer:
    schema: crm
    table: customer_master
sequences:
  documentNumbers:
    schema: shared
    sequence: document_numbers
"""


def test_typed_json_and_yaml_bindings_round_trip_to_one_value() -> None:
    binding = _binding()
    assert binding == PostgresBinding.from_yaml(binding.to_yaml())
    assert binding == PostgresBinding.from_json(binding.to_json())
    assert binding == PostgresBinding.from_document(binding.to_document())
    assert binding == PostgresBinding.from_yaml(_YAML)
    assert hash(binding) == hash(PostgresBinding.from_yaml(_YAML))
    assert binding.dialect.name == "postgres"


def test_serialization_is_canonical_whatever_the_authoring_order() -> None:
    reordered = PostgresBinding(
        sequences={"documentNumbers": PostgresSequence(schema="shared", name="document_numbers")},
        entities={"commerce.Customer": PostgresTable(name="customer_master", schema="crm")},
        namespaces={"audit": PostgresLocation(schema="audit")},
        default=PostgresLocation(schema="app"),
    )
    assert reordered.to_yaml() == _binding().to_yaml() == _YAML
    assert reordered.to_json() == _binding().to_json()


def test_a_binding_presents_its_locations_as_qualifier_components() -> None:
    binding = _binding()
    assert binding.default is not None
    assert binding.default.qualifier == ("app",)
    customer = binding.entities[EntityIdentity("commerce", "Customer")]
    assert customer.location == PostgresLocation(schema="crm")
    assert PostgresTable(name="orders").location is None
    assert binding.sequences["documentNumbers"].location == PostgresLocation(schema="shared")
    assert repr(binding) == (
        "PostgresBinding(default=PostgresLocation(schema='app'), "
        "namespaces={'audit': PostgresLocation(schema='audit')}, "
        "entities={EntityIdentity(namespace='commerce', name='Customer'): "
        "PostgresTable(schema='crm', name='customer_master')}, "
        "sequences={'documentNumbers': "
        "PostgresSequence(schema='shared', name='document_numbers')})"
    )


def test_owner_keys_normalize_to_entity_identities() -> None:
    binding = _binding()
    customer = EntityIdentity("commerce", "Customer")
    assert list(binding.entities) == [customer]
    assert binding.entities[customer] == PostgresTable(schema="crm", name="customer_master")
    assert PostgresBinding(entities=binding.entities) == PostgresBinding(
        entities={"commerce.Customer": PostgresTable(schema="crm", name="customer_master")}
    )


def test_a_binding_owns_copies_of_the_maps_it_was_given() -> None:
    namespaces = {"audit": PostgresLocation(schema="audit")}
    entities: dict[str, PostgresTable] = {
        "commerce.Customer": PostgresTable(name="customer_master")
    }
    binding = PostgresBinding(namespaces=namespaces, entities=entities)
    namespaces["billing"] = PostgresLocation(schema="billing")
    entities["commerce.Order"] = PostgresTable(name="orders")
    assert list(binding.namespaces) == ["audit"]
    assert list(binding.entities) == [EntityIdentity("commerce", "Customer")]


def test_a_binding_cannot_be_mutated() -> None:
    binding = _binding()
    with pytest.raises(TypeError):
        binding.namespaces["billing"] = PostgresLocation(schema="billing")  # pyright: ignore[reportIndexIssue]
    with pytest.raises(dataclasses.FrozenInstanceError):
        binding.default = None  # pyright: ignore[reportAttributeAccessIssue]


def _issues(raised: pytest.ExceptionInfo[BindingError]) -> list[tuple[str, tuple[str, ...]]]:
    return [(issue.code, issue.path) for issue in raised.value.issues]


@pytest.mark.parametrize(
    ("typed", "document"),
    [
        (
            lambda: PostgresBinding(entities={"commerce.Customer": PostgresTable(name="")}),
            {"entities": {"commerce.Customer": {"table": ""}}},
        ),
        (
            lambda: PostgresBinding(entities={"commerce.customer": PostgresTable(name="c")}),
            {"entities": {"commerce.customer": {"table": "c"}}},
        ),
        (
            lambda: PostgresBinding(namespaces={"Audit": PostgresLocation(schema="")}),
            {"namespaces": {"Audit": {"schema": ""}}},
        ),
        (
            lambda: PostgresBinding(sequences={"": PostgresSequence(schema="")}),
            {"sequences": {"": {"schema": ""}}},
        ),
    ],
    ids=["empty-table", "malformed-owner", "namespace-and-schema", "empty-allocator"],
)
def test_typed_and_document_bindings_report_equal_issues(
    typed: Callable[[], PostgresBinding], document: Mapping[str, object]
) -> None:
    with pytest.raises(BindingError) as from_code:
        typed()
    with pytest.raises(BindingError) as from_document:
        PostgresBinding.from_document({"format_version": 1, "backend": "postgres", **document})
    assert _issues(from_code) == _issues(from_document)


def test_every_problem_is_reported_at_its_artifact_path() -> None:
    with pytest.raises(BindingError) as raised:
        PostgresBinding(
            default="app",  # pyright: ignore[reportArgumentType]
            entities={
                "commerce.Order": PostgresTable(schema=5, name=""),  # pyright: ignore[reportArgumentType]
                "commerce.Customer": PostgresLocation(schema="crm"),
            },
        )
    assert isinstance(raised.value, UsageError)
    assert raised.value.code == "binding-definition-rejected"
    assert _issues(raised) == [
        ("binding-value-invalid", ("default",)),
        ("binding-value-invalid", ("entities", "commerce.Customer")),
        ("binding-value-invalid", ("entities", "commerce.Order", "schema")),
        ("binding-identifier-invalid", ("entities", "commerce.Order", "table")),
    ]


def test_an_omitted_part_is_not_an_invalid_one() -> None:
    assert PostgresBinding(entities={"commerce.Order": PostgresTable()}).to_document() == {
        "format_version": 1,
        "backend": "postgres",
        "entities": {"commerce.Order": {}},
    }
    with pytest.raises(BindingError) as raised:
        PostgresBinding.from_yaml("format_version: 1\nbackend: postgres\ndefault: null\n")
    assert _issues(raised) == [("binding-value-invalid", ("default",))]


@pytest.mark.parametrize(
    ("door", "text"),
    [(PostgresBinding.from_json, '{"format_version": 1,'), (PostgresBinding.from_yaml, "a: [")],
    ids=["json", "yaml"],
)
def test_malformed_text_is_a_definition_refusal(
    door: Callable[[str], PostgresBinding], text: str
) -> None:
    with pytest.raises(BindingError) as raised:
        door(text)
    assert raised.value.issues == (BindingIssue("binding-syntax-invalid", ()),)
    assert raised.value.__cause__ is not None
