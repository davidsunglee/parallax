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

from parallax.conformance import animal_owner, read_models
from parallax.core import Attr, Concrete, Entity, EntityConfig, FamilyRoot, Field, Rel, Relationship
from parallax.core.db_port import DbPort, Row
from parallax.core.entity import metamodel
from parallax.core.entity.base import (
    EntityRegistry,
    ModelCopyError,
    ScopedMetamodel,
    default_registry,
    entity_record_of,
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
def _declare_duplicate_default_probe(table: str):
    """Declare (and thereby register) the probe in the process-default
    registry. One class statement per call, in its own function scope, so
    calling this twice IS the duplicate registration under test -- with no
    redeclared binding for Pyright to flag (each canonical name is declared
    once per Python scope; the registry, not the scope, sees the collision)."""

    class DuplicateRegistrationDefaultProbe(Entity, frozen=True):
        __parallax__ = EntityConfig(table=table, mutability="transactional")

        id: Attr[int] = Field(primary_key=True, pk_generator="none")

    return DuplicateRegistrationDefaultProbe


def test_duplicate_registration_in_the_default_registry_raises() -> None:
    _declare_duplicate_default_probe("dup_default_probe_1")
    with pytest.raises(RegistryCollisionError, match="DuplicateRegistrationDefaultProbe"):
        _declare_duplicate_default_probe("dup_default_probe_2")


def _declare_duplicate_scoped_probe(table: str, registry: EntityRegistry):
    class DuplicateRegistrationScopedProbe(Entity, frozen=True, registry=registry):
        __parallax__ = EntityConfig(table=table, mutability="transactional")

        id: Attr[int] = Field(primary_key=True, pk_generator="none")

    return DuplicateRegistrationScopedProbe


def test_duplicate_registration_in_a_scoped_registry_raises() -> None:
    scoped = EntityRegistry()
    _declare_duplicate_scoped_probe("dup_scoped_probe_1", scoped)
    with pytest.raises(RegistryCollisionError, match="DuplicateRegistrationScopedProbe"):
        _declare_duplicate_scoped_probe("dup_scoped_probe_2", scoped)


# --------------------------------------------------------------------------- #
# The SAME canonical name coexists across TWO DIFFERENT registries.           #
# --------------------------------------------------------------------------- #
def _declare_coexisting_probe(table: str, registry: EntityRegistry, marker_default: str):
    class CoexistingProbe(Entity, frozen=True, registry=registry):
        __parallax__ = EntityConfig(table=table, mutability="transactional")

        id: Attr[int] = Field(primary_key=True, pk_generator="none")
        marker: Attr[str] = Field(default=marker_default)

    return CoexistingProbe


def test_same_name_in_two_registries_coexists() -> None:
    registry_a = EntityRegistry()
    registry_b = EntityRegistry()
    class_a = _declare_coexisting_probe("coexist_probe_a", registry_a, "a")
    class_b = _declare_coexisting_probe("coexist_probe_b", registry_b, "b")

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


def _declare_bare_spoke(registry: EntityRegistry):
    """A relationship-free "Spoke" -- the same canonical name as
    `_build_hub_family`'s, declared in a FOREIGN registry purely for its
    registration side effect."""

    class Spoke(Entity, frozen=True, registry=registry):
        __parallax__ = EntityConfig(table="spoke_y", mutability="transactional")

        id: Attr[int] = Field(primary_key=True, pk_generator="none")

    return Spoke


def test_dynamic_relationship_hop_resolves_within_the_declaring_registry() -> None:
    registry_x = EntityRegistry()
    registry_y = EntityRegistry()
    hub_x, _spoke_x, _detail_x = _build_hub_family(registry_x)

    # `registry_y`'s own "Spoke" shares the exact same canonical name as
    # `registry_x`'s, but declares NO relationship at all -- a same-named
    # foreign class registered elsewhere must be INVISIBLE to the dynamic hop
    # resolving `Hub.spokes.extra` inside `registry_x`'s own scope.
    _declare_bare_spoke(registry_y)

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
def _declare_sample_probe(table: str, registry: EntityRegistry, flavor_default: str):
    class Sample(Entity, frozen=True, registry=registry):
        __parallax__ = EntityConfig(table=table, mutability="transactional")

        id: Attr[int] = Field(primary_key=True, pk_generator="none")
        flavor: Attr[str] = Field(default=flavor_default)

    return Sample


def test_db_find_instantiates_the_connected_registrys_own_class() -> None:
    registry_a = EntityRegistry()
    registry_b = EntityRegistry()
    sample_a = _declare_sample_probe("sample_a", registry_a, "a")
    _declare_sample_probe("sample_b", registry_b, "b")

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

    def declare_mismatched_leaf(registry: EntityRegistry):
        """Declare a concrete leaf under the root with an EXPLICIT
        (mismatched) ``registry=`` -- the class-definition-time rejection
        under test."""

        class FamilyLeafProbe(FamilyRootProbe, frozen=True, registry=registry):
            __parallax__ = EntityConfig(
                mutability="transactional", inheritance=Concrete(tag_value="leaf")
            )

        return FamilyLeafProbe

    other = EntityRegistry()
    with pytest.raises(EntityDefinitionError, match="registry"):
        declare_mismatched_leaf(other)


# --------------------------------------------------------------------------- #
# S1 (BLOCKING, COR-3 Phase 7 increment 7 round-2): two-registry TPH          #
# regression -- a table-per-hierarchy family's SHARED-TABLE default must      #
# never cross a registry boundary, even for two SAME-NAMED roots.            #
# --------------------------------------------------------------------------- #
def _declare_tph_animal_root(table: str, registry: EntityRegistry):
    class Animal(Entity, frozen=True, registry=registry):
        __parallax__ = EntityConfig(
            table=table,
            mutability="transactional",
            inheritance=FamilyRoot(strategy="table-per-hierarchy", tag="kind"),
        )

        id: Attr[int] = Field(primary_key=True, pk_generator="none")

    return Animal


def test_family_shared_table_does_not_leak_across_registries() -> None:
    """Reproduces the reviewer's defect verbatim: a bare-canonical-name-keyed
    shared-table cache let a SECOND registry's same-named TPH root overwrite
    the FIRST's entry, so a concrete-subtype descendant compiled afterward
    silently inherited the WRONG registry's table. Re-keyed by the root's own
    CLASS object (never the bare name) -- collision-proof like
    `_ENTITY_BY_CLASS` -- so this can never happen regardless of compile
    order."""
    registry_a = EntityRegistry()
    registry_b = EntityRegistry()
    animal_a = _declare_tph_animal_root("animals_a", registry_a)

    # A SAME-NAMED root in a DIFFERENT registry, compiled AFTER `animal_a` but
    # BEFORE its own concrete subtype below -- exactly the interleaving that
    # let the bare-name-keyed bookkeeping overwrite registry A's entry pre-fix.
    _declare_tph_animal_root("animals_b", registry_b)

    class Dog(animal_a, frozen=True):
        __parallax__ = EntityConfig(
            mutability="transactional", inheritance=Concrete(tag_value="dog")
        )

    record = entity_record_of(Dog)
    assert record is not None
    assert record.table == "animals_a"  # registry A's own root table, never B's


# --------------------------------------------------------------------------- #
# Shadowing precedence (S1's scrutiny-item-1 pin): a child registry declaring #
# a name that ALSO exists in its own `parent` chain is never a collision --   #
# the child's own entry shadows the parent's, the parent itself unaffected.   #
# --------------------------------------------------------------------------- #
def _declare_shadow_probe(table: str, registry: EntityRegistry):
    class ShadowProbe(Entity, frozen=True, registry=registry):
        __parallax__ = EntityConfig(table=table, mutability="transactional")

        id: Attr[int] = Field(primary_key=True, pk_generator="none")

    return ShadowProbe


def test_child_registry_entry_shadows_a_same_named_parent_entry() -> None:
    parent = EntityRegistry(parent=None)
    parent_class = _declare_shadow_probe("shadow_probe_parent", parent)
    child = EntityRegistry(parent=parent)

    # Declaring the SAME name in the CHILD raises no `RegistryCollisionError`
    # at all -- `__parallax_register__`'s own collision check looks only at
    # the registering registry's OWN scope, never its `parent` chain.
    child_class = _declare_shadow_probe("shadow_probe_child", child)

    # The child's own entry shadows the parent's from here on...
    assert child.resolve("ShadowProbe") is child_class
    assert child.records()["ShadowProbe"] is entity_record_of(child_class)
    # ... while the parent registry itself is entirely unaffected.
    assert parent.resolve("ShadowProbe") is parent_class
    assert parent.records()["ShadowProbe"] is entity_record_of(parent_class)


# --------------------------------------------------------------------------- #
# S2 (BLOCKING, COR-3 Phase 7 increment 7 round-2): class-authored metamodel  #
# assembly (the bare `metamodel(classes)` helper, never only                 #
# `EntityRegistry.metamodel()`) auto-scopes from the classes it is given, so  #
# `db.find` resolves through the assembled classes' own registry -- never    #
# the process default -- even when a same-named foreign class is ALSO        #
# imported in the same process.                                              #
# --------------------------------------------------------------------------- #
def test_bare_metamodel_auto_scopes_from_a_single_registrys_classes() -> None:
    meta = metamodel([animal_owner.Person])
    assert isinstance(meta, ScopedMetamodel)
    assert meta.registry is animal_owner.ANIMAL_OWNER_REGISTRY


def test_bare_metamodel_over_a_mixed_registry_set_scopes_to_the_narrower_child() -> None:
    # `animal_owner.Person`'s own `ANIMAL_OWNER_REGISTRY` already resolves
    # everything its `parent` (the process default, where `Animal`/`Pet` are
    # registered) does -- so mixing the owner class with its related
    # default-registry siblings scopes to the NARROWER, `Person`-owning
    # registry: the identical tag `ANIMAL_OWNER_REGISTRY.metamodel()` itself
    # would produce, never a guess.
    meta = metamodel([animal_owner.Person, read_models.Animal, read_models.Pet])
    assert isinstance(meta, ScopedMetamodel)
    assert meta.registry is animal_owner.ANIMAL_OWNER_REGISTRY


def test_bare_metamodel_over_an_incompatible_mixed_set_raises() -> None:
    registry_a = EntityRegistry(parent=None)
    registry_b = EntityRegistry(parent=None)

    class IncompatibleProbeA(Entity, frozen=True, registry=registry_a):
        __parallax__ = EntityConfig(table="incompatible_probe_a", mutability="transactional")

        id: Attr[int] = Field(primary_key=True, pk_generator="none")

    class IncompatibleProbeB(Entity, frozen=True, registry=registry_b):
        __parallax__ = EntityConfig(table="incompatible_probe_b", mutability="transactional")

        id: Attr[int] = Field(primary_key=True, pk_generator="none")

    with pytest.raises(ValueError, match="incompatible EntityRegistry"):
        metamodel([IncompatibleProbeA, IncompatibleProbeB])


def test_db_find_over_a_bare_metamodel_resolves_the_assembled_classs_own_registry() -> None:
    # Reproduces the reviewer's defect verbatim: pre-fix, `metamodel(...)`
    # produced a bare, UNTAGGED `Metamodel`, so `resolve_entity_class` fell
    # back to the process default registry -- landing on that registry's OWN,
    # unrelated `read_models.Person` (`models/person.yaml`) instead of the
    # assembled `animal_owner.Person` (`models/animal.yaml`'s real polymorphic
    # owner), the moment both happened to be imported in the same process.
    meta = metamodel([animal_owner.Person])
    port = _CannedPort([{"id": 1, "name": "Alice"}])
    db = Database.connect(port, meta)
    snapshot = db.find(animal_owner.Person.where(animal_owner.Person.id == 1))
    result = snapshot.result()

    assert type(result) is animal_owner.Person
    assert type(result) is not read_models.Person
    assert result.name == "Alice"


# --------------------------------------------------------------------------- #
# R1 (BLOCKING, COR-3 Phase 7 increment 7 round-2): S2's original mixed-      #
# registry check confirmed only that the candidate REACHES every other       #
# distinct registry, never that it actually RESOLVES every supplied class     #
# back to itself -- a conflicting same-name pair across registries (or       #
# shadowed within one registry chain) must reject loudly, never silently     #
# emit two divergent records for one canonical name.                         #
# --------------------------------------------------------------------------- #
def test_bare_metamodel_over_conflicting_same_name_classes_rejects_loudly() -> None:
    # Reproduces the reviewer's exact call verbatim: `animal_owner.Person`
    # (`models/animal.yaml`'s polymorphic owner) and `read_models.Person`
    # (`models/person.yaml`'s unrelated one-to-one Passport owner) share the
    # literal canonical name "Person" but are UNRELATED classes with
    # divergent descriptors (maxLength, relationships) -- pre-fix, S2's
    # reachability-only check silently picked ANIMAL_OWNER_REGISTRY (it
    # reaches the default registry `read_models.Person` lives in) without
    # confirming that registry resolves EVERY supplied class back to itself,
    # so the assembled Metamodel's own `entities` carried BOTH divergent
    # "Person" records while class resolution silently returned only
    # `animal_owner.Person` -- descriptor and class resolution selecting
    # different definitions. Must reject loudly instead.
    with pytest.raises(ValueError, match="conflicting same-name classes"):
        metamodel([animal_owner.Person, read_models.Person])


def test_bare_metamodel_over_a_same_name_pair_shadowed_within_one_registry_chain_rejects() -> None:
    # A same-name pair rejects even when both classes' own registries form a
    # SINGLE parent chain via shadowing (never only when the registries are
    # genuinely incomparable) -- supplying BOTH the shadowing CHILD class and
    # the shadowed PARENT class is the SAME conflict as the cross-registry
    # reproduction above, just one level removed.
    parent = EntityRegistry(parent=None)
    parent_class = _declare_shadow_conflict_probe("shadow_conflict_parent", parent)
    child = EntityRegistry(parent=parent)
    child_class = _declare_shadow_conflict_probe("shadow_conflict_child", child)

    with pytest.raises(ValueError, match="conflicting same-name classes"):
        metamodel([parent_class, child_class])


def _declare_shadow_conflict_probe(table: str, registry: EntityRegistry):
    class ShadowConflictProbe(Entity, frozen=True, registry=registry):
        __parallax__ = EntityConfig(table=table, mutability="transactional")

        id: Attr[int] = Field(primary_key=True, pk_generator="none")

    return ShadowConflictProbe


# --------------------------------------------------------------------------- #
# P1 (BLOCKING, COR-3 Phase 7 increment 7 round-3): the IDENTICAL class object #
# repeated in `classes` is harmless repetition, never a conflict -- prompt 89 #
# requires `metamodel()` "must never emit two records for one canonical       #
# name," and pre-fix it silently did (`entities` carried the SAME class's     #
# record twice). The distinct-same-name rejection above (R1) is unaffected:  #
# TWO DIFFERENT classes sharing a name still raises loudly; only the SAME     #
# class object repeated dedupes.                                             #
# --------------------------------------------------------------------------- #
def test_bare_metamodel_over_an_identical_class_repeated_dedupes_to_one_record() -> None:
    meta = metamodel([read_models.Person, read_models.Person])
    assert len(meta.entities) == 1
    assert meta.entities[0].name == "Person"


def test_bare_metamodel_over_an_identical_class_repeated_round_trips_normally() -> None:
    # The assembled (deduped) Metamodel is still a well-formed, correctly
    # SCOPED `ScopedMetamodel` -- `db.find` resolves `animal_owner.Person`
    # exactly as it would from a single, non-repeated supply.
    meta = metamodel([animal_owner.Person, animal_owner.Person])
    assert isinstance(meta, ScopedMetamodel)
    assert meta.registry is animal_owner.ANIMAL_OWNER_REGISTRY
    assert len(meta.entities) == 1

    port = _CannedPort([{"id": 1, "name": "Alice"}])
    db = Database.connect(port, meta)
    snapshot = db.find(animal_owner.Person.where(animal_owner.Person.id == 1))
    result = snapshot.result()

    assert type(result) is animal_owner.Person
    assert result.name == "Alice"


def test_bare_metamodel_over_a_mixed_set_with_a_repeated_class_dedupes_only_the_repeat() -> None:
    # A legitimate mixed set (COR-3 Phase 7 increment 7 round-2's own
    # reproduction, `animal_owner.Person` + its related default-registry
    # siblings) still dedupes an identical repetition within it, preserving
    # FIRST-occurrence order for the surviving, non-repeated members.
    meta = metamodel([animal_owner.Person, read_models.Animal, read_models.Animal])
    assert [entity.name for entity in meta.entities] == ["Person", "Animal"]
