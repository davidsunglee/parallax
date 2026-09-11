"""The stored state a case declares before its action runs: ``given.corrupt``,
the fixture rows a Temporal Shadow is seeded from, and ``given.apply``.

Three seeders rather than one, because the lanes do work between them: every
compile path seeds the shadow alone, the read lanes corrupt stored state alone,
and the run lanes that apply out-of-band statements seed the shadow first and
apply after work of their own. Each seeder is applied where its lane already
stands — after provisioning, before the action — so a case states its stored
state once and every lane observes the same storage.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any, cast

from parallax.conformance import _case_ingress, case_format, provision
from parallax.conformance._mechanism.envelope import EngineError, driver_binds
from parallax.conformance._mechanism.model_facts import case_entity, family_declarer
from parallax.conformance.temporal_state import TemporalShadow
from parallax.core import inheritance, storage_layout
from parallax.core.base import INFINITY_LITERAL
from parallax.core.db_port import DatabaseConnection, JsonDocument
from parallax.core.metamodel import EntityMetadata, PrimaryKey, ValueObjectIdentity
from parallax.core.metamodel import Metamodel as AcceptedMetamodel
from parallax.core.storage_layout import DirectColumn, DocumentPath
from parallax.core.unit_work import KeyedWrite
from parallax.core.unit_work.instructions import PreparedKeyedWrite
from parallax.core.wire import WireValue, decode_wire

__all__ = ["apply_given_apply", "apply_given_corrupt", "seed_shadow_from_fixtures"]


def apply_given_corrupt(
    case: case_format.Case, model: AcceptedMetamodel, port: DatabaseConnection
) -> None:
    """Write a read case's ``given.corrupt`` entries over its loaded fixtures.

    Applied where every read lane already stands — after provisioning, before the
    action — so a case states the stored value once and every read form observes
    the same storage. Each entry addresses a Structured Column and a path inside
    it, and the value is stored exactly as authored: it is what the model
    contradicts, so passing it back through the codec that spells a conforming
    one would refuse it.

    Every entry's Entity is judged for temporality before any entry applies, as
    the reference harness judges it before any row lands: that refusal is about
    the CASE, so a legal entry standing before a temporal one must not have
    written a row by the time the list is refused. A refusal only one entry's own
    address resolution reaches leaves earlier entries' writes standing, which the
    case's ungradeability makes harmless.
    """
    given = case.document.get("given")
    if not isinstance(given, Mapping):
        return
    entries = cast("Mapping[str, object]", given).get("corrupt")
    if not isinstance(entries, list):
        return
    corruptions = cast("list[Mapping[str, object]]", entries)
    _refuse_temporal_corruptions(case, model, corruptions)
    for entry in corruptions:
        _corrupt_stored_state(case, model, port, entry)


def _refuse_temporal_corruptions(
    case: case_format.Case, model: AcceptedMetamodel, entries: Sequence[Mapping[str, object]]
) -> None:
    """Refuse every entry addressing a temporal Entity, before any entry applies.

    A temporal Entity's rows are keyed by the model key plus each axis's end
    instant, so one ``key`` value there addresses a milestone chain and names no
    row in it (`m-case-format` *Corrupting stored state*).
    """
    for entry in entries:
        entity = case_entity(model, cast("str", entry["entity"]))
        if _is_temporal(model, entity):
            raise EngineError(f"{case.path.name}: {_temporal_corruption_refusal(entity)}")


def _corrupt_stored_state(
    case: case_format.Case,
    model: AcceptedMetamodel,
    port: DatabaseConnection,
    entry: Mapping[str, object],
) -> None:
    """Realize one corruption as a whole-document replacement of one row's cell.

    Read, mutate, write: a document holds the value at an authored path, and
    replacing the whole document reaches it without a per-dialect document
    mutation expression — the corrupt value is the subject of the case's own
    assertion, so it must mean the same thing on every provider.
    """
    entity = case_entity(model, cast("str", entry["entity"]))
    view = storage_layout.view(model).entity(entity.identity)
    if view is None:  # pragma: no cover - a corrupted Entity owns rows
        raise EngineError(f"{case.path.name}: {entity.identity.canonical} owns no table")
    member = tuple(cast("list[object]", entry["member"]))
    column, path = _corruption_target(case, model, entity, member)
    key_column, key = _corruption_key(case, model, entity, entry["key"])
    dialect = port.dialect
    table = dialect.quote(view.layout.table.name)
    where = f"where {dialect.quote(key_column)} = ?"
    rows = port.execute(
        dialect.to_driver_sql(f"select {dialect.quote(column)} from {table} {where}"), [key]
    )
    if len(rows) != 1:
        raise EngineError(
            f"{case.path.name}: given.corrupt addresses {entity.identity.canonical} "
            f"{entry['key']!r}, which the loaded fixtures answer with {len(rows)} row(s) "
            "rather than one"
        )
    document = _replaced_at(_stored_value(rows[0][column]), path, entry["value"])
    port.execute_write(
        dialect.to_driver_sql(f"update {table} set {dialect.quote(column)} = ? {where}"),
        [JsonDocument(document), key],
    )


def _is_temporal(model: AcceptedMetamodel, entity: EntityMetadata) -> bool:
    """Whether ``entity``'s family declares an As-Of Axis.

    Temporality is family-wide and root-owned, so the question is asked of the
    family root's own declaration; a descendant declares none of its own.
    """
    position = inheritance.view(model).entity(entity.identity)
    root = entity if position is None else model.entity(position.root)
    return root is not None and bool(root.declared_as_of_axes)


def _temporal_corruption_refusal(entity: EntityMetadata) -> str:
    """Why a corruption addressing ``entity`` is refused.

    Spelled exactly as the corpus's own static validation and the reference
    harness spell it, so a case reaching for a temporal Entity is told the same
    thing wherever it is refused: its rows are keyed by the model key plus each
    axis's end instant, so one ``key`` value addresses a milestone chain and
    names no row in it (`m-case-format` *Corrupting stored state*).
    """
    return (
        f"given.corrupt addresses {entity.identity.canonical}, a temporal Entity: its "
        "model primary key addresses a milestone chain rather than one row "
        "(m-case-format *Corrupting stored state*)"
    )


def _stored_value(cell: object) -> object:
    """One Structured Column as the mutable JSON value its provider returned.

    The root is whatever the column carries rather than an object in every case:
    a shared document and a top-level `One` occurrence are objects, and a
    top-level `Many` occurrence is an array.
    """
    return json.loads(cell) if isinstance(cell, str) else cell


def _replaced_at(document: object, path: tuple[object, ...], value: object) -> object:
    """``document`` with ``value`` stored at ``path``, walking its own containers.

    A path segment is a member name or an array position, and the container it
    indexes is whatever the stored document holds there, so the walk is untyped
    for the same reason the stored state is: it is not the model's. The empty
    path addresses the Structured Column's whole stored value, which is what an
    address naming a top-level occurrence itself resolves to.
    """
    if not path:
        return value
    current: Any = document
    for segment in path[:-1]:
        current = current[segment]
    current[path[-1]] = value
    return document


def _corruption_target(
    case: case_format.Case,
    model: AcceptedMetamodel,
    entity: EntityMetadata,
    member: tuple[object, ...],
) -> tuple[str, tuple[object, ...]]:
    """The Structured Column and in-document path one addressed member resolves to.

    The addressed top-level member answers it through the DECLARING member the
    name resolves to, because a placement stays keyed by declaration identity
    across every Entity that inherits it (`m-storage-layout`): a document-resident
    member contributes its own Document Path, a top-level Value Object occurrence
    under `Columns` contributes its own Structured Column, and the nested names
    and array positions the address carries follow — an address stopping at the
    occurrence itself leaving the whole stored value as the target. A member the
    layout keeps in a Column of its own is refused — only a Structured Column can
    hold a value its own declaration contradicts.
    """
    view = storage_layout.view(model).entity(entity.identity)
    family = inheritance.view(model).entity(entity.identity)
    name = member[0]
    declared = (
        None
        if not isinstance(name, str) or family is None
        else family.applicable_attribute(name) or family.applicable_value_object(name)
    )
    placement = (
        None if declared is None or view is None else view.layout.placement(declared.identity)
    )
    if isinstance(placement, DocumentPath):
        return placement.slot.column.name, (*placement.path, *member[1:])
    if isinstance(placement, DirectColumn) and isinstance(
        placement.slot.contributor, ValueObjectIdentity
    ):
        return placement.slot.column.name, member[1:]
    raise EngineError(
        f"{case.path.name}: given.corrupt addresses {entity.identity.canonical}."
        f"{'.'.join(str(segment) for segment in member)}, which this model does not place "
        "inside a Structured Column"
    )


def _corruption_key(
    case: case_format.Case, model: AcceptedMetamodel, entity: EntityMetadata, key: object
) -> tuple[str, object]:
    """The primary-key Column one corruption addresses its row by, and the managed
    value it binds.

    `m-metamodel` admits no composite primary key, and the addressed Entity is
    non-temporal by then, so this one Column IS the row's physical key.
    """
    view = storage_layout.view(model).entity(entity.identity)
    family = inheritance.view(model).entity(entity.identity)
    attributes = () if family is None else family.applicable_attributes
    declared = next(
        (attribute for attribute in attributes if isinstance(attribute.primary_key, PrimaryKey)),
        None,
    )
    placement = (
        None if declared is None or view is None else view.layout.placement(declared.identity)
    )
    # Defensive: every accepted Entity declares one primary key and every Storage
    # Layout keeps it in a Column of its own.
    if declared is None or not isinstance(placement, DirectColumn):  # pragma: no cover
        raise EngineError(
            f"{case.path.name}: {entity.identity.canonical} declares no primary key a "
            "corruption can address a row by"
        )
    return placement.slot.column.name, decode_wire(declared.type, cast("WireValue", key))


def seed_shadow_from_fixtures(
    case: case_format.Case, model: AcceptedMetamodel, shadow: TemporalShadow
) -> None:
    """Seed ``shadow`` from the case's OWN fixture-loading rule (`m-case-format`):
    a writeSequence starts EMPTY unless it opts in with ``given.fixtures: true``;
    every other shape (scenario, conflict) loads the model's default fixtures —
    mirrored from ``tests/_support/corpus.py``'s ``case_fixtures`` rule, kept independent
    (production/adapter code never imports the test suite)."""
    given = case.document.get("given")
    fixtures_flag = (
        isinstance(given, Mapping) and cast("Mapping[str, object]", given).get("fixtures") is True
    )
    if case.shape == "writeSequence" and not fixtures_flag:
        return
    fixtures = provision.load_fixtures(cast("str", case.document["model"]))
    for entity_name, rows in fixtures.items():
        entity = case_entity(model, entity_name)
        if not family_declarer(model, entity).declared_as_of_axes:
            shadow.seed_fixtures(
                model,
                entity,
                cast("list[Mapping[str, object]]", rows),
            )
            continue
        managed_rows: list[Mapping[str, object]] = []
        for row in cast("list[Mapping[str, object]]", rows):
            open_bounds = {name: value for name, value in row.items() if value == INFINITY_LITERAL}
            instruction = KeyedWrite(
                "insert",
                entity.identity.canonical,
                ({name: value for name, value in row.items() if name not in open_bounds},),
            )
            prepared = _case_ingress.prepare_case_write(instruction, model)
            assert isinstance(prepared, PreparedKeyedWrite)
            managed_rows.append({**prepared.rows[0], **open_bounds})
        shadow.seed_fixtures(model, entity, managed_rows)


def apply_given_apply(
    case: case_format.Case, port: DatabaseConnection, shadow: TemporalShadow
) -> None:
    """Apply a case's out-of-band ``given.apply`` naive statements VERBATIM,
    immediately (never inside our own transaction), and tell ``shadow`` they ran.

    They stand for a writer this unit of work is not: a CONCURRENT transaction
    that already committed, so its effect must survive our own eventual rollback
    (a stale-version conflict), or a newer application version that stored state
    no authored member of this model could produce (a Structured Column key the
    model declares nowhere).

    Marking the tracker here rather than at each lane is what makes the mark
    unforgettable: every executor of a shape ``given.apply`` is admitted on —
    conflict, writeSequence, and each of the three scenario executors — runs the
    statements through this one function, so no lane can leave a tracker claiming
    a whole account of a row one of them may since have overtaken."""
    given = case.document.get("given")
    if not isinstance(given, Mapping):
        return
    entries = cast("Mapping[str, object]", given).get("apply")
    if not isinstance(entries, list):
        return
    shadow.note_out_of_band_write()
    for entry in cast("list[Mapping[str, object]]", entries):
        sql = cast("str", entry["sql"])
        binds = cast("list[object]", entry.get("binds", []))
        port.execute_write(port.dialect.to_driver_sql(sql), driver_binds(binds))
