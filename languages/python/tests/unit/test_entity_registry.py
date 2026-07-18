"""D-20 explicit scoped entity registries: unit pins (COR-3 Phase 8 increment 7
Part A, design doc 37 DQ7a Option A).

Every entity class registers into an explicit :class:`EntityRegistry` scope
(``registry=`` at class-definition time; omitted -> the process
:func:`default_registry`). These pins prove: duplicate registration is a loud
error EVERYWHERE (default registry too, not only a scoped one); the SAME
canonical name coexists across TWO DIFFERENT registries; name resolution
(``where``/``include``/dynamic relationship hops/``AttributeExpr.set``) stays
scoped to the declaring class's own registry -- a same-named foreign class
registered elsewhere is invisible; and ``db.find`` instantiates the connected
metamodel's own class even when an unrelated registry holds a same-named
class (the design-doc reproduction, inverted into a regression pin).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import pytest

from parallax.core import Attr, Concrete, Entity, EntityConfig, FamilyRoot, Field, Rel, Relationship
from parallax.core.db_port import DbPort, Row
from parallax.core.entity.base import (
    EntityRegistry,
    ModelCopyError,
    default_registry,
    entity_records,
    entity_registry,
)
from parallax.core.entity.errors import EntityDefinitionError, RegistryCollisionError
from parallax.snapshot.handle import Database

pytestmark = pytest.mark.unit


class _CannedPort:
    """A fake ``m-db-port`` returning ONE canned row set for the single
    root-level query a flat (relationship-free) entity's ``db.find`` issues."""

    def __init__(self, rows: Sequence[Row]) -> None:
        self._rows = list(rows)
        self.executed: list[tuple[str, list[object]]] = []

    def execute(self, sql: str, binds: Sequence[object]) -> list[Row]:
        self.executed.append((sql, list(binds)))
        return list(self._rows)

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:  # pragma: no cover
        raise NotImplementedError

    def transaction[T](self, body: Callable[[DbPort], T]) -> T:  # pragma: no cover
        raise NotImplementedError


# --------------------------------------------------------------------------- #
# Duplicate registration is a loud error EVERYWHERE (default registry too).   #
# --------------------------------------------------------------------------- #
def test_duplicate_registration_in_the_default_registry_raises() -> None:
    class DuplicateRegistrationDefaultProbe(  # pyright: ignore[reportUnusedClass, reportRedeclaration]
        Entity, frozen=True
    ):
        __parallax__ = EntityConfig(table="dup_default_probe_1", mutability="transactional")

        id: Attr[int] = Field(primary_key=True, pk_generator="none")

    with pytest.raises(RegistryCollisionError, match="DuplicateRegistrationDefaultProbe"):

        class DuplicateRegistrationDefaultProbe(  # pyright: ignore[reportUnusedClass]
            Entity, frozen=True
        ):
            __parallax__ = EntityConfig(table="dup_default_probe_2", mutability="transactional")

            id: Attr[int] = Field(primary_key=True, pk_generator="none")


def test_duplicate_registration_in_a_scoped_registry_raises() -> None:
    scoped = EntityRegistry()

    class DuplicateRegistrationScopedProbe(  # pyright: ignore[reportUnusedClass, reportRedeclaration]
        Entity, frozen=True, registry=scoped
    ):
        __parallax__ = EntityConfig(table="dup_scoped_probe_1", mutability="transactional")

        id: Attr[int] = Field(primary_key=True, pk_generator="none")

    with pytest.raises(RegistryCollisionError, match="DuplicateRegistrationScopedProbe"):

        class DuplicateRegistrationScopedProbe(  # pyright: ignore[reportUnusedClass]
            Entity, frozen=True, registry=scoped
        ):
            __parallax__ = EntityConfig(table="dup_scoped_probe_2", mutability="transactional")

            id: Attr[int] = Field(primary_key=True, pk_generator="none")


# --------------------------------------------------------------------------- #
# The SAME canonical name coexists across TWO DIFFERENT registries.           #
# --------------------------------------------------------------------------- #
def test_same_name_in_two_registries_coexists() -> None:
    registry_a = EntityRegistry()
    registry_b = EntityRegistry()

    class CoexistingProbe(  # pyright: ignore[reportRedeclaration]
        Entity, frozen=True, registry=registry_a
    ):
        __parallax__ = EntityConfig(table="coexist_probe_a", mutability="transactional")

        id: Attr[int] = Field(primary_key=True, pk_generator="none")
        marker: Attr[str] = Field(default="a")

    class_a = CoexistingProbe

    class CoexistingProbe(Entity, frozen=True, registry=registry_b):
        __parallax__ = EntityConfig(table="coexist_probe_b", mutability="transactional")

        id: Attr[int] = Field(primary_key=True, pk_generator="none")
        marker: Attr[str] = Field(default="b")

    class_b = CoexistingProbe

    assert class_a is not class_b
    assert registry_a.resolve("CoexistingProbe") is class_a
    assert registry_b.resolve("CoexistingProbe") is class_b
    assert registry_a.records()["CoexistingProbe"] is not registry_b.records()["CoexistingProbe"]


# --------------------------------------------------------------------------- #
# Scoped resolution: a same-named foreign class in another registry is        #
# invisible to `.where`/`.include`/dynamic hops/`AttributeExpr.set`/wrap.     #
# --------------------------------------------------------------------------- #
def _build_hub_family(registry: EntityRegistry) -> tuple[Any, Any, Any]:
    class Detail(Entity, frozen=True, registry=registry):
        __parallax__ = EntityConfig(table="detail", mutability="transactional")

        id: Attr[int] = Field(primary_key=True, pk_generator="none")

    class Spoke(Entity, frozen=True, registry=registry):
        __parallax__ = EntityConfig(table="spoke", mutability="transactional")

        id: Attr[int] = Field(primary_key=True, pk_generator="none")
        hub_id: Attr[int] = Field(type="int64")
        detail_id: Attr[int] = Field(type="int64")
        extra: Rel[Detail] = Relationship(
            cardinality="one-to-one",
            join="this.detailId = Detail.id",
            related_entity="Detail",
            foreign_key="detail_id",
        )

    class Hub(Entity, frozen=True, registry=registry):
        __parallax__ = EntityConfig(table="hub", mutability="transactional")

        id: Attr[int] = Field(primary_key=True, pk_generator="none")
        spokes: Rel[tuple[Spoke, ...]] = Relationship(
            cardinality="one-to-many",
            join="this.id = Spoke.hubId",
            related_entity="Spoke",
            foreign_key="hub_id",
        )

    return Hub, Spoke, Detail


def test_dynamic_relationship_hop_resolves_within_the_declaring_registry() -> None:
    registry_x = EntityRegistry()
    registry_y = EntityRegistry()
    hub_x, _spoke_x, _detail_x = _build_hub_family(registry_x)

    # `registry_y`'s own "Spoke" shares the exact same canonical name as
    # `registry_x`'s, but declares NO relationship at all -- a same-named
    # foreign class registered elsewhere must be INVISIBLE to the dynamic hop
    # resolving `Hub.spokes.extra` inside `registry_x`'s own scope.
    class Spoke(Entity, frozen=True, registry=registry_y):  # pyright: ignore[reportUnusedClass]
        __parallax__ = EntityConfig(table="spoke_y", mutability="transactional")

        id: Attr[int] = Field(primary_key=True, pk_generator="none")

    path = hub_x.spokes.extra  # first hop typed (Rel[T]); second hop dynamic (__getattr__)
    assert path.target == "Detail"


def test_where_and_include_validate_within_the_declaring_registry() -> None:
    registry_x = EntityRegistry()
    hub_x, spoke_x, _detail_x = _build_hub_family(registry_x)

    statement = hub_x.where(hub_x.id == 1).include(hub_x.spokes.extra)
    assert statement.target == "Hub"

    # An undeclared hop still raises (never silently resolves against a
    # foreign, same-named registry elsewhere).
    with pytest.raises(AttributeError, match="declares no relationship"):
        _ = spoke_x.extra.bogus_hop  # type: ignore[attr-defined]


def test_narrow_resolves_subtype_names_regardless_of_registry() -> None:
    # `Entity.narrow`'s subtype resolution (`entity_record_of`) is CLASS-keyed
    # (never name-keyed), so it needs no registry scoping at all -- confirmed
    # here as a structural pin alongside the scoped `where`/`include` proof
    # above: a scoped family's own root still narrows to its own subtypes.
    registry_x = EntityRegistry()

    class NarrowRootProbe(Entity, frozen=True, registry=registry_x):
        __parallax__ = EntityConfig(
            table="narrow_root_probe",
            mutability="transactional",
            inheritance=FamilyRoot(strategy="table-per-hierarchy", tag="kind"),
        )

        id: Attr[int] = Field(primary_key=True, pk_generator="none")

    class NarrowLeafProbe(NarrowRootProbe, frozen=True):
        __parallax__ = EntityConfig(
            mutability="transactional", inheritance=Concrete(tag_value="leaf")
        )

        detail: Attr[str] = Field(nullable=True, default=None)

    predicate = NarrowRootProbe.narrow(NarrowLeafProbe)
    narrow_node = predicate.op
    assert narrow_node.to == ("NarrowLeafProbe",)  # type: ignore[attr-defined]


def test_attribute_expr_set_validates_within_the_declaring_registry() -> None:
    scoped = EntityRegistry()

    class SetProbe(Entity, frozen=True, registry=scoped):
        __parallax__ = EntityConfig(table="set_probe", mutability="transactional")

        id: Attr[int] = Field(primary_key=True, pk_generator="none")
        name: Attr[str] = Field(max_length=32)

    assignment = SetProbe.name.set("Ada")
    assert assignment.value == "Ada"
    with pytest.raises(ModelCopyError):
        SetProbe.id.set(2)  # a primary-key member is never assignable


# --------------------------------------------------------------------------- #
# The regression pin: `db.find` instantiates the CONNECTED metamodel's own    #
# class even with a same-named class registered elsewhere.                    #
# --------------------------------------------------------------------------- #
def test_db_find_instantiates_the_connected_registrys_own_class() -> None:
    registry_a = EntityRegistry()
    registry_b = EntityRegistry()

    class Sample(  # pyright: ignore[reportRedeclaration]
        Entity, frozen=True, registry=registry_a
    ):
        __parallax__ = EntityConfig(table="sample_a", mutability="transactional")

        id: Attr[int] = Field(primary_key=True, pk_generator="none")
        flavor: Attr[str] = Field(default="a")

    sample_a = Sample

    class Sample(Entity, frozen=True, registry=registry_b):
        __parallax__ = EntityConfig(table="sample_b", mutability="transactional")

        id: Attr[int] = Field(primary_key=True, pk_generator="none")
        flavor: Attr[str] = Field(default="b")

    port = _CannedPort([{"id": 1, "flavor": "a"}])
    db = Database.connect(port, registry_a.metamodel())
    snapshot = db.find(sample_a.where(sample_a.id == 1))
    result = snapshot.result()

    assert type(result) is sample_a
    assert result.flavor == "a"


# --------------------------------------------------------------------------- #
# Default-registry behavior is unchanged for a single-registry app.          #
# --------------------------------------------------------------------------- #
def test_default_registry_behavior_unchanged_for_a_single_registry_app() -> None:
    class DefaultRegistryProbe(Entity, frozen=True):
        __parallax__ = EntityConfig(table="default_probe", mutability="transactional")

        id: Attr[int] = Field(primary_key=True, pk_generator="none")

    assert default_registry().resolve("DefaultRegistryProbe") is DefaultRegistryProbe
    assert entity_registry()["DefaultRegistryProbe"] is DefaultRegistryProbe
    assert "DefaultRegistryProbe" in entity_records()


# --------------------------------------------------------------------------- #
# An inheritance-family subclass always shares its root's registry; an        #
# explicit `registry=` naming a DIFFERENT one raises at class-definition time #
# (never a silent split-family bug).                                         #
# --------------------------------------------------------------------------- #
def test_family_subclass_registry_mismatch_raises() -> None:
    scoped = EntityRegistry()

    class FamilyRootProbe(Entity, frozen=True, registry=scoped):
        __parallax__ = EntityConfig(
            table="family_root_probe",
            mutability="transactional",
            inheritance=FamilyRoot(strategy="table-per-hierarchy", tag="kind"),
        )

        id: Attr[int] = Field(primary_key=True, pk_generator="none")

    other = EntityRegistry()
    with pytest.raises(EntityDefinitionError, match="registry"):

        class FamilyLeafProbe(  # pyright: ignore[reportUnusedClass]
            FamilyRootProbe, frozen=True, registry=other
        ):
            __parallax__ = EntityConfig(
                mutability="transactional", inheritance=Concrete(tag_value="leaf")
            )
