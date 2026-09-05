"""Deriving a Physical Index Name (m-schema-delta), Docker-free.

A name is the one generated identifier this system produces, and it has to be
readable, stable, and short enough for the database that holds it. These are the
rules a corpus case can only witness one instance of: what the readable half
keeps, what an empty readable input becomes, what the fingerprint is a function
of, and what truncation is allowed to touch.
"""

from __future__ import annotations

import dataclasses

from parallax.core.base import STRING
from parallax.core.dialect import POSTGRES, Dialect
from parallax.core.metamodel import AttributeIdentity, Column, EntityIdentity, IndexIdentity, Table
from parallax.evolution.schema_delta._naming import physical_index_name, readable_prefix
from parallax.evolution.schema_delta._physical import IndexDefinition, PhysicalColumn

_ENTITY = EntityIdentity(namespace="parallax.test", name="Widget")

_MARIADB: Dialect = dataclasses.replace(POSTGRES, name="mariadb", max_identifier_bytes=64)


def _definition(
    *,
    table: str = "widget",
    index: str = "widget_code",
    components: tuple[str, ...] = ("code",),
    unique: bool = False,
) -> IndexDefinition:
    return IndexDefinition(
        table=Table(name=table),
        index=IndexIdentity(_ENTITY, index),
        components=tuple(AttributeIdentity(_ENTITY, name) for name in components),
        columns=tuple(
            PhysicalColumn(Column(name=name), STRING, 8, nullable=True) for name in components
        ),
        unique=unique,
    )


# --- the readable half ---------------------------------------------------------


def test_the_readable_prefix_lowercases_letters_and_keeps_digits() -> None:
    assert readable_prefix(("Widget2", "taxID")) == "widget2_taxid"


def test_every_run_of_anything_else_becomes_exactly_one_underscore() -> None:
    # Field boundaries, dots, and existing underscores are all separators, so no
    # name ever carries a doubled or trailing underscore.
    assert readable_prefix(("widget__code", "parallax.test.Widget", "non-unique")) == (
        "widget_code_parallax_test_widget_non_unique"
    )
    assert readable_prefix(("__widget__",)) == "widget"


def test_a_readable_input_with_nothing_to_keep_becomes_index() -> None:
    # Unreachable from an accepted model — a Table name carries letters — but the
    # rule is what keeps the derivation total rather than producing `pxi__<hex>`.
    assert readable_prefix(("", "...", "---")) == "index"


# --- the fingerprint -----------------------------------------------------------


def _fingerprint_of(definition: IndexDefinition) -> str:
    return physical_index_name(definition, POSTGRES).value.rsplit("_", 1)[1]


def test_the_fingerprint_is_32_lowercase_hexadecimal_characters() -> None:
    fingerprint = _fingerprint_of(_definition())
    assert len(fingerprint) == 32
    assert all(character in "0123456789abcdef" for character in fingerprint)


def test_the_same_definition_always_derives_the_same_name() -> None:
    assert physical_index_name(_definition(), POSTGRES) == physical_index_name(
        _definition(), POSTGRES
    )


def test_every_structural_fact_moves_the_fingerprint() -> None:
    # The fingerprint is what makes the name unique, so each fact the definition
    # is identified by has to reach it — including component ORDER, which changes
    # the physical access path.
    base = _fingerprint_of(_definition())
    assert _fingerprint_of(_definition(table="gadget")) != base
    assert _fingerprint_of(_definition(index="widget_code_2")) != base
    assert _fingerprint_of(_definition(unique=True)) != base
    forward = _fingerprint_of(_definition(components=("code", "label")))
    reversed_components = _fingerprint_of(_definition(components=("label", "code")))
    assert forward != reversed_components


def test_the_declaring_entity_reaches_the_fingerprint_through_its_whole_identity() -> None:
    other_namespace = dataclasses.replace(
        _definition(),
        index=IndexIdentity(
            EntityIdentity(namespace="parallax.other", name="Widget"), "widget_code"
        ),
    )
    assert _fingerprint_of(other_namespace) != _fingerprint_of(_definition())


# --- fitting the dialect's limit -----------------------------------------------


def _short() -> IndexDefinition:
    """A definition whose whole readable input already fits every limit."""
    entity = EntityIdentity(namespace=None, name="W")
    return dataclasses.replace(
        _definition(table="t"),
        index=IndexIdentity(entity, "i"),
        components=(AttributeIdentity(entity, "code"),),
    )


def test_a_short_name_keeps_its_whole_readable_input() -> None:
    name = physical_index_name(_short(), POSTGRES)
    assert name.value == f"pxi_t_w_i_non_unique_{_fingerprint_of(_short())}"
    assert len(name.value) < POSTGRES.max_identifier_bytes


def test_a_long_readable_input_truncates_without_touching_the_fingerprint() -> None:
    long = _definition(table="x" * 40)
    name = physical_index_name(long, POSTGRES)
    assert len(name.value) == POSTGRES.max_identifier_bytes
    assert name.value.endswith(_fingerprint_of(long))
    assert name.value.startswith("pxi_" + "x" * 26)


def test_truncation_never_leaves_the_separator_it_landed_on() -> None:
    # The cut can fall inside a separator run, and a name ending in `_` before the
    # fingerprint would read as a doubled underscore rather than as a shortening.
    cut_on_a_boundary = _definition(table="a_very_long_physical_table_name_for_one_widget")
    name = physical_index_name(cut_on_a_boundary, POSTGRES)
    assert "__" not in name.value
    assert name.value == f"pxi_a_very_long_physical_table_{_fingerprint_of(cut_on_a_boundary)}"


def test_each_dialect_gets_the_prefix_its_own_limit_allows() -> None:
    # The fingerprint is identical because it is the definition's; only the
    # readable half differs, because MariaDB allows one more byte than Postgres.
    long = _definition(table="x" * 40)
    postgres = physical_index_name(long, POSTGRES)
    mariadb = physical_index_name(long, _MARIADB)
    assert len(postgres.value) == 63
    assert len(mariadb.value) == 64
    assert postgres.value.rsplit("_", 1)[1] == mariadb.value.rsplit("_", 1)[1]
    assert mariadb.value == f"pxi_{'x' * 27}_{postgres.value.rsplit('_', 1)[1]}"
