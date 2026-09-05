"""A Dialect that cannot spell an operation (m-schema-delta), Docker-free.

Only two DDL primitives can refuse, and no shipped Dialect refuses either, so a
synthetic one is the only way to reach the aggregation at all. What these tests
pin is the whole answer under refusal: every operation the Dialect cannot render
arrives at once, in the order the statements would have run, each naming where it
acts and the Evolution Operations that asked for it — and no statement escapes
beside them.

The causal attribution the refusals expose is the same attribution every physical
operation carries; a refusal is simply the one place a caller can read it.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence

import pytest
from _corpus_model_support import formed
from _inheritance_family_support import entity_with_two_indices_over_one_column

from parallax.core.dialect import (
    POSTGRES,
    ColumnDdl,
    Dialect,
    IndexColumnDdl,
    PhysicalIndexName,
    Unsupported,
)
from parallax.core.metamodel import Metamodel as AcceptedMetamodel
from parallax.descriptor._records import Attribute, Entity, Index, Metamodel
from parallax.evolution.model_evolution import ABSENT, UnilateralEvolution, evolve
from parallax.evolution.schema_delta import UnsupportedSchemaEvolutionError, schema_delta

_INDEX_REFUSAL = "this dialect indexes nothing"
_WIDENING_REFUSAL = "this dialect widens nothing"


@dataclasses.dataclass(frozen=True, slots=True)
class _RefusingDialect(Dialect):
    """A Dialect that creates and alters Tables and refuses the other two primitives."""

    def expand_column(self, table: str, earlier: ColumnDdl, later: ColumnDdl) -> str | Unsupported:
        del table, earlier, later
        return Unsupported(_WIDENING_REFUSAL)

    def create_index(
        self,
        table: str,
        name: PhysicalIndexName,
        columns: Sequence[IndexColumnDdl],
        *,
        unique: bool,
    ) -> str | Unsupported:
        del table, name, columns, unique
        return Unsupported(_INDEX_REFUSAL)


def _refusing() -> Dialect:
    return _RefusingDialect(
        name="refusing",
        reserved=POSTGRES.reserved,
        quote_char=POSTGRES.quote_char,
        error_codes=POSTGRES.error_codes,
        max_identifier_bytes=POSTGRES.max_identifier_bytes,
    )


def _widget(*, bound: int, indexed: bool) -> AcceptedMetamodel:
    """One Entity whose `code` bound and authored access path both vary."""
    return formed(
        Metamodel(
            entities=(
                Entity(
                    name="Widget",
                    table="widget",
                    attributes=(
                        Attribute(name="id", type="int64", column="id", primary_key=True),
                        Attribute(name="code", type="string", column="code", max_length=bound),
                    ),
                    indices=((Index(name="widget_code", attributes=("code",)),) if indexed else ()),
                ),
            )
        )
    )


def _widened_and_indexed() -> UnilateralEvolution:
    """One evolution widening a Column and putting an access path over it."""
    evolution = evolve(_widget(bound=8, indexed=False), _widget(bound=64, indexed=True))
    assert isinstance(evolution, UnilateralEvolution)
    return evolution


def test_every_operation_a_dialect_refuses_is_reported_at_once() -> None:
    # No partial delta escapes: the whole plan is rendered and inspected before
    # anything is returned, so both refusals arrive in one error rather than the
    # first one arriving alone.
    with pytest.raises(UnsupportedSchemaEvolutionError) as raised:
        schema_delta(evolve(ABSENT, entity_with_two_indices_over_one_column()), _refusing())
    error = raised.value
    assert error.dialect_identity == "refusing"
    assert [operation.kind for operation in error.operations] == ["CreateIndex", "CreateIndex"]
    assert {operation.location.table.name for operation in error.operations} == {"widget"}
    assert all(operation.reason == _INDEX_REFUSAL for operation in error.operations)
    for operation in error.operations:
        assert operation.caused_by
        assert operation.location.index is not None


def test_refusals_from_two_primitives_arrive_in_statement_order() -> None:
    # A widened Column and a new access path in one evolution: the refusals are
    # ordered as the statements would have been — the Column before the Index
    # over it — rather than grouped by which primitive refused.
    evolution = _widened_and_indexed()
    with pytest.raises(UnsupportedSchemaEvolutionError) as raised:
        schema_delta(evolution, _refusing())
    error = raised.value
    assert [operation.kind for operation in error.operations] == [
        "ExpandColumnDomain",
        "CreateIndex",
    ]
    assert [operation.reason for operation in error.operations] == [
        _WIDENING_REFUSAL,
        _INDEX_REFUSAL,
    ]


def test_each_refusal_names_the_operations_that_asked_for_it() -> None:
    # Causal attribution is per physical operation, not per delta: the widening
    # is asked for by the member alteration and the Index by its own addition.
    evolution = _widened_and_indexed()
    with pytest.raises(UnsupportedSchemaEvolutionError) as raised:
        schema_delta(evolution, _refusing())
    widened, indexed = raised.value.operations
    assert [type(cause).__name__ for cause in widened.caused_by] == ["AttributeAltered"]
    assert [type(cause).__name__ for cause in indexed.caused_by] == ["IndexAdded"]
    assert widened.location.column is not None
    assert widened.location.column.name == "code"


def test_a_refusing_dialect_returns_no_statement_at_all() -> None:
    # A Schema Delta is applied statement by statement, so half of one is worse
    # than none: an operation the Dialect cannot spell means no delta is
    # returned, not a delta missing that statement.
    evolution = _widened_and_indexed()
    with pytest.raises(UnsupportedSchemaEvolutionError):
        schema_delta(evolution, _refusing())
    supported = schema_delta(evolution, POSTGRES)
    (created,) = supported.created_indices
    assert supported.statements == (
        "alter table widget alter column code type varchar(64)",
        f"create index {created.physical_index_name.value} on widget (code)",
    )
