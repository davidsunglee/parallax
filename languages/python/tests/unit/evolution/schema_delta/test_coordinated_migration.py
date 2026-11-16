"""`coordinated_migration` over the input spaces its steps and causes vary by.

The corpus witnesses each sequence statement once; this module walks the
combinations a corpus case would spell row by row: which allocator changes ask
for a drain, a creation, an alteration, a positioning, or a drop; which causes
each step names; and how combined changes order.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence

import pytest

from parallax.core.internal.database_binding import (
    ResolvedBinding,
    SequenceRelocated,
)
from parallax.core.internal.dialect import POSTGRES, Dialect, SequenceDdl, Unsupported
from parallax.core.internal.entity import model_of
from parallax.core.internal.metamodel import Metamodel
from parallax.descriptor import domain_model_from_yaml
from parallax.evolution import (
    CoordinatedEvolution,
    CoordinatedMigration,
    ManualAction,
    ManualStep,
    MigrationStatement,
    SchemaTarget,
    UnilateralEvolution,
    UnsupportedSchemaEvolutionError,
    coordinated_migration,
)
from parallax.evolution.internal.model_evolution import (
    AttributeAdded,
    AttributeAltered,
    AttributeRemoved,
    EntityAltered,
    EntityRemoved,
    EvolutionOperation,
    evolve_resolved,
)
from parallax.postgres import PostgresBinding
from tests._support.bindings import binding_for, bound_model


def _generation(allocator: str | None, settings: str = "") -> str:
    if allocator is None:
        return ""
    return f", pkGeneration: {{ strategy: key-sequence, name: {allocator}{settings} }}"


def _model(*entities: tuple[str, str | None, str], extra: str = "") -> Metamodel:
    """One standalone Entity per ``(name, allocator, settings)``, each with a
    key drawing from ``allocator`` (application-assigned where it is ``None``)
    and a required label."""
    body = "".join(
        f"""
  - name: {name}
    table: {name.lower()}
    attributes:
      - {{ name: id, type: int64, primaryKey: true{_generation(allocator, settings)} }}
      - {{ name: label, type: string, maxLength: 16 }}
"""
        for name, allocator, settings in entities
    )
    return model_of(domain_model_from_yaml(f"entities:{body}{extra}"))


def _migration(
    earlier: Metamodel,
    later: Metamodel,
    *,
    earlier_binding: ResolvedBinding | None = None,
    later_binding: ResolvedBinding | None = None,
) -> tuple[CoordinatedEvolution, CoordinatedMigration]:
    evolution = evolve_resolved(
        earlier_binding or bound_model(earlier), later_binding or bound_model(later)
    )
    assert isinstance(evolution, CoordinatedEvolution)
    return evolution, coordinated_migration(evolution)


def _shape(migration: CoordinatedMigration) -> list[str]:
    """Each step as its manual action or its statement's leading words."""
    return [
        step.action.value if isinstance(step, ManualStep) else " ".join(step.sql.split()[:2])
        for step in migration.steps
    ]


def _statement(migration: CoordinatedMigration, prefix: str) -> MigrationStatement:
    (found,) = (
        step
        for step in migration.steps
        if isinstance(step, MigrationStatement) and step.sql.startswith(prefix)
    )
    return found


def _named(causes: Sequence[EvolutionOperation]) -> set[str]:
    return {
        cause.attribute.entity.name
        if isinstance(cause, AttributeAltered | AttributeAdded)
        else type(cause).__name__
        for cause in causes
    }


def test_a_unilateral_evolution_is_refused_naming_schema_delta() -> None:
    model = _model(("Badge", "ids", ""))
    evolution = evolve_resolved(bound_model(model), bound_model(model))
    assert isinstance(evolution, UnilateralEvolution)
    with pytest.raises(TypeError, match="use schema_delta"):
        coordinated_migration(evolution)  # pyright: ignore[reportArgumentType] - the refused input


# --- allocation settings -------------------------------------------------------


def test_a_shrunken_step_is_altered_then_positioned_past_the_earlier_step_s_block() -> None:
    _, migration = _migration(
        _model(("Badge", "ids", ", batchSize: 50")), _model(("Badge", "ids", ", batchSize: 20"))
    )
    assert _shape(migration) == ["DrainEarlierRoots", "alter sequence", "select case"]
    assert _statement(migration, "alter").sql == "alter sequence px.ids increment by 20"
    position = _statement(migration, "select").sql
    assert "cast(t1.last_value as numeric) + 50 else" in position
    assert "(select cast(max(t2.id) as numeric) + 1 from px.badge t2)" in position


def test_a_grown_step_is_altered_without_positioning() -> None:
    # The next block under the larger step already starts past the last one
    # the earlier step reserved.
    _, migration = _migration(
        _model(("Badge", "ids", ", batchSize: 20")), _model(("Badge", "ids", ", batchSize: 50"))
    )
    assert _shape(migration) == ["DrainEarlierRoots", "alter sequence"]


def test_settings_keeping_the_physical_step_need_a_drain_and_no_statement() -> None:
    evolution, migration = _migration(
        _model(("Badge", "ids", ", batchSize: 10, incrementSize: 2")),
        _model(("Badge", "ids", ", batchSize: 20, incrementSize: 1")),
    )
    assert _shape(migration) == ["DrainEarlierRoots"]
    (requirement,) = evolution.coordination_requirements
    assert migration.steps[0].caused_by == (requirement.operation,)


def test_a_key_type_change_restates_the_sequence_type_and_bounds() -> None:
    alter = _statement(_migration(_model(("Badge", "ids", "")), _int32_badge())[1], "alter")
    assert alter.sql == (
        "alter sequence px.ids as integer minvalue -2147483648 maxvalue 2147483647"
    )


def _int32_badge() -> Metamodel:
    return model_of(
        domain_model_from_yaml(
            """
entities:
  - name: Badge
    table: badge
    attributes:
      - name: id
        type: int32
        primaryKey: true
        pkGeneration: { strategy: key-sequence, name: ids }
      - { name: label, type: string, maxLength: 16 }
"""
        )
    )


# --- consumers joining and leaving allocators -----------------------------------


def test_a_populated_join_onto_a_new_allocator_creates_then_positions_it() -> None:
    evolution, migration = _migration(
        _model(("Badge", None, ""), ("Pass", None, "")),
        _model(("Badge", "ids", ""), ("Pass", "ids", "")),
    )
    assert _shape(migration) == ["DrainEarlierRoots", "create sequence", "select case"]
    joins = tuple(requirement.operation for requirement in evolution.coordination_requirements)
    assert all(step.caused_by == joins for step in migration.steps)
    position = _statement(migration, "select").sql
    assert "from px.badge t2" in position and "from px.pass t3" in position


def test_a_join_onto_a_surviving_allocator_positions_without_creating_it() -> None:
    _, migration = _migration(
        _model(("Badge", "ids", ""), ("Pass", None, "")),
        _model(("Badge", "ids", ""), ("Pass", "ids", "")),
    )
    assert _shape(migration) == ["DrainEarlierRoots", "select case"]
    assert _named(migration.steps[1].caused_by) == {"Pass"}


def test_a_move_between_allocators_positions_the_new_one_and_drops_the_abandoned_one() -> None:
    _, migration = _migration(_model(("Badge", "old", "")), _model(("Badge", "new", "")))
    assert _shape(migration) == [
        "DrainEarlierRoots",
        "create sequence",
        "select case",
        "drop sequence",
    ]
    assert _statement(migration, "drop").sql == "drop sequence px.old"
    assert "px.new" in _statement(migration, "create").sql


def test_a_move_off_a_shared_allocator_keeps_its_sequence() -> None:
    _, migration = _migration(
        _model(("Badge", "old", ""), ("Pass", "old", "")),
        _model(("Badge", "old", ""), ("Pass", "new", "")),
    )
    assert "drop sequence" not in _shape(migration)


def test_leaving_a_surviving_allocator_updates_the_authoring_surface_alone() -> None:
    evolution, migration = _migration(
        _model(("Badge", "ids", ""), ("Pass", "ids", "")),
        _model(("Badge", "ids", ""), ("Pass", None, "")),
    )
    (requirement,) = evolution.coordination_requirements
    assert migration.steps == (
        ManualStep(ManualAction.UPDATE_AUTHORING_SURFACE, (requirement.operation,)),
    )


def test_leaving_an_allocator_s_final_reference_drains_then_drops_it() -> None:
    evolution, migration = _migration(_model(("Badge", "ids", "")), _model(("Badge", None, "")))
    (requirement,) = evolution.coordination_requirements
    assert _shape(migration) == ["DrainEarlierRoots", "UpdateAuthoringSurface", "drop sequence"]
    assert all(step.caused_by == (requirement.operation,) for step in migration.steps)


def test_removing_an_allocator_s_last_consumer_drops_it_for_that_removal() -> None:
    _, migration = _migration(
        _model(("Badge", "ids", ""), ("Pass", None, "")), _model(("Pass", None, ""))
    )
    assert _shape(migration) == ["DrainEarlierRoots", "UpdateAuthoringSurface", "drop sequence"]
    assert all(
        isinstance(cause, EntityRemoved) for step in migration.steps for cause in step.caused_by
    )


def _badge(*attributes: str) -> Metamodel:
    body = "".join(f"\n      - {attribute}" for attribute in attributes)
    return model_of(
        domain_model_from_yaml(
            f"entities:\n  - name: Badge\n    table: badge\n    attributes:{body}"
        )
    )


_IDS = "pkGeneration: { strategy: key-sequence, name: ids }"


def test_removing_an_allocator_s_last_key_drains_then_drops_it_for_that_removal() -> None:
    _, migration = _migration(
        _badge(
            f"{{ name: id, type: int64, primaryKey: true, {_IDS} }}", "{ name: code, type: int64 }"
        ),
        _badge("{ name: code, type: int64, primaryKey: true }"),
    )
    drain, *_, drop = migration.steps
    assert drain == ManualStep(ManualAction.DRAIN_EARLIER_ROOTS, drain.caused_by)
    assert drop == MigrationStatement(sql="drop sequence px.ids", caused_by=drain.caused_by)
    (removal,) = drop.caused_by
    assert isinstance(removal, AttributeRemoved) and removal.attribute.name == "id"


@pytest.mark.parametrize(
    "later_key",
    [
        pytest.param(
            (
                "{ name: id, type: int64 }",
                f"{{ name: code, type: int64, primaryKey: true, {_IDS} }}",
            ),
            id="promoted",
        ),
        pytest.param((f"{{ name: code, type: int64, primaryKey: true, {_IDS} }}",), id="replacing"),
    ],
)
def test_a_populated_entity_gaining_a_generated_key_creates_then_positions_its_allocator(
    later_key: tuple[str, ...],
) -> None:
    _, migration = _migration(
        _badge("{ name: id, type: int64, primaryKey: true }", "{ name: code, type: int64 }"),
        _badge(*later_key),
    )
    drain = migration.steps[0]
    create, position = migration.steps[-2:]
    assert drain == ManualStep(ManualAction.DRAIN_EARLIER_ROOTS, drain.caused_by)
    assert isinstance(create, MigrationStatement) and create.sql.startswith(
        "create sequence px.ids"
    )
    assert isinstance(position, MigrationStatement) and "from px.badge t2" in position.sql
    (cause,) = create.caused_by
    assert isinstance(cause, AttributeAltered | AttributeAdded) and cause.attribute.name == "code"
    assert drain.caused_by == position.caused_by == create.caused_by


def _fleet(van_parent: str) -> Metamodel:
    def family(root: str, allocator: str, *leaves: str) -> str:
        members = "".join(
            f"""
  - name: {leaf}
    table: {leaf.lower()}
    inheritance: {{ role: concrete-subtype, parent: {root} }}
    attributes: [{{ name: note, type: string, maxLength: 8, nullable: true }}]
"""
            for leaf in leaves
        )
        return f"""
  - name: {root}
    inheritance: {{ role: root, strategy: table-per-concrete-subtype }}
    attributes:
      - {{ name: id, type: int64, primaryKey: true{_generation(allocator)} }}
{members}"""

    leaves: dict[str, tuple[str, ...]] = {"Fleet": ("Truck",), "Other": ("Car",)}
    leaves[van_parent] = (*leaves[van_parent], "Van")
    return model_of(
        domain_model_from_yaml(
            "entities:"
            + family("Fleet", "fleet_ids", *leaves["Fleet"])
            + family("Other", "other_ids", *leaves["Other"])
        )
    )


def test_a_leaf_moved_into_another_allocator_s_family_positions_that_allocator() -> None:
    _, migration = _migration(_fleet("Fleet"), _fleet("Other"))
    assert _shape(migration) == ["DrainEarlierRoots", "TransformStoredData", "select case"]
    position = _statement(migration, "select")
    assert "px.other_ids" in position.sql and "from px.van" in position.sql
    (move,) = position.caused_by
    assert isinstance(move, EntityAltered) and move.entity.name == "Van"
    assert migration.steps[0].caused_by == (move,)


# --- combined changes and ordinary statements ------------------------------------


def _placed(model: Metamodel, *, badge: str = "px", sequence: str | None = None) -> ResolvedBinding:
    document: dict[str, object] = {
        "format_version": 1,
        "backend": "postgres",
        "default": {"schema": "px"},
        "entities": {"Badge": {"schema": badge}},
    }
    if sequence is not None:
        document["sequences"] = {"ids": {"schema": sequence}}
    return ResolvedBinding(model, PostgresBinding.from_document(document))


def test_every_drain_precedes_every_relocation_transformation_and_statement() -> None:
    earlier = _model(("Badge", "ids", ", batchSize: 50"), ("Pass", None, ""))
    later = _model(
        ("Badge", "ids", ", batchSize: 20"),
        ("Pass", "ids", ", batchSize: 20"),
        extra="""
  - name: Ledger
    table: ledger
    attributes:
      - { name: id, type: int64, primaryKey: true }
""",
    )
    evolution, migration = _migration(
        earlier,
        later,
        earlier_binding=_placed(earlier, sequence="px"),
        later_binding=_placed(later, badge="px_archive", sequence="px_keys"),
    )
    assert _shape(migration) == [
        "DrainEarlierRoots",
        "Relocate",
        "Relocate",
        "create table",
        "alter sequence",
        "select case",
    ]
    relocations = [
        operation
        for operation in evolution.operations
        if type(operation).__name__ in {"TableRelocated", "SequenceRelocated"}
    ]
    assert set(relocations) <= set(migration.steps[0].caused_by)
    assert [step.caused_by for step in migration.steps[1:3]] == [(r,) for r in relocations]
    sequence = next(r for r in relocations if isinstance(r, SequenceRelocated))
    assert _statement(migration, "alter").sql.startswith("alter sequence px_keys.ids")
    assert sequence.later.qualifier == ("px_keys",)


def test_an_operation_needing_no_database_change_still_gets_its_ordinary_statement() -> None:
    # A nullable member arrives unilaterally beside a required one the
    # deployment must backfill: the first is generated, the second withheld.
    earlier = _model(("Badge", None, ""))
    later = model_of(
        domain_model_from_yaml(
            """
entities:
  - name: Badge
    table: badge
    attributes:
      - { name: id, type: int64, primaryKey: true }
      - { name: label, type: string, maxLength: 16 }
      - { name: note, type: string, maxLength: 16, nullable: true }
      - { name: code, type: string, maxLength: 16 }
"""
        )
    )
    _, migration = _migration(earlier, later)
    assert _shape(migration) == ["TransformStoredData", "alter table"]
    assert migration.steps[1] == MigrationStatement(
        sql="alter table px.badge add column note varchar(16)",
        caused_by=migration.steps[1].caused_by,
    )
    (backfilled,) = migration.steps[0].caused_by
    assert isinstance(backfilled, AttributeAdded)
    assert backfilled.attribute.name == "code"


# --- refusals --------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class _SequencelessMigrations(Dialect):
    """A Dialect that holds native sequences but cannot alter or position one."""

    def alter_sequence(
        self, sequence: str, earlier: SequenceDdl, later: SequenceDdl
    ) -> str | Unsupported:
        del sequence, earlier, later
        return Unsupported("no alteration")

    def position_sequence(
        self,
        sequence: str,
        ddl: SequenceDdl,
        key_columns: Sequence[tuple[str, str]],
        *,
        reserved_increment: int,
    ) -> str | Unsupported:
        del sequence, ddl, key_columns, reserved_increment
        return Unsupported("no positioning")


def test_every_sequence_operation_a_dialect_refuses_is_reported_at_once() -> None:
    dialect = _SequencelessMigrations(
        name="sequenceless",
        reserved=POSTGRES.reserved,
        quote_char=POSTGRES.quote_char,
        error_codes=POSTGRES.error_codes,
        max_identifier_bytes=POSTGRES.max_identifier_bytes,
        max_bind_parameters=POSTGRES.max_bind_parameters,
        sequence_bounds=POSTGRES.sequence_bounds,
    )
    binding = binding_for(dialect)
    evolution = evolve_resolved(
        ResolvedBinding(_model(("Badge", "ids", ", batchSize: 50")), binding),
        ResolvedBinding(_model(("Badge", "ids", ", batchSize: 20")), binding),
    )
    assert isinstance(evolution, CoordinatedEvolution)
    with pytest.raises(UnsupportedSchemaEvolutionError) as raised:
        coordinated_migration(evolution)
    assert [(refusal.kind, refusal.reason) for refusal in raised.value.operations] == [
        ("AlterSequence", "no alteration"),
        ("PositionSequence", "no positioning"),
    ]
    assert {refusal.location for refusal in raised.value.operations} == {
        SchemaTarget(sequence=evolution.later.sequences["ids"].physical)
    }


def test_an_index_dropped_from_a_relocated_table_is_dropped_where_the_table_moved() -> None:
    def badge(indexed: bool) -> Metamodel:
        index = "\n    indices: [{ name: badge_label, attributes: [label] }]" if indexed else ""
        return model_of(
            domain_model_from_yaml(
                f"""
entities:
  - name: Badge
    table: badge
    attributes:
      - {{ name: id, type: int64, primaryKey: true }}
      - {{ name: label, type: string, maxLength: 16 }}{index}
"""
            )
        )

    earlier, later = badge(indexed=True), badge(indexed=False)
    _, migration = _migration(
        earlier,
        later,
        earlier_binding=_placed(earlier),
        later_binding=_placed(later, badge="px_archive"),
    )
    assert _shape(migration) == ["DrainEarlierRoots", "Relocate", "drop index"]
    assert _statement(migration, "drop index").sql.startswith("drop index px_archive.pxi_badge_")
