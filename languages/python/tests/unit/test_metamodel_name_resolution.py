"""Bare-or-canonical Entity name resolution over a bare accepted model.

Pins the ambiguity-rejecting contract shared by every seam that resolves an
authored Entity spelling against an accepted ``Metamodel``: an exact canonical
spelling matches, a bare name matches only when a single Entity carries it, and a
bare name two namespaces share is a miss rather than a silent first match. The
``predicate.validate``, snapshot materialize, unit-of-work, and write-lowering
seams resolve through the same ``entity_by_name`` helper, and so — the second
suite below — do the three lowering seams an accepted query reaches next:
``m-sql``'s family reads and hops, ``m-deep-fetch``'s levels, and
``m-navigate``'s hop canonicalization. One rule across validation and lowering is
what makes "preflight accepted this reference" imply "lowering resolves it".
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast

import pytest

from _support.sql import compile_read
from parallax.core import deep_fetch, navigate
from parallax.core import predicate as oa
from parallax.core._formation_profile import form_metamodel
from parallax.core.db_port import DbPort
from parallax.core.dialect import POSTGRES, Dialect
from parallax.core.entity._layout import CatalogedModel
from parallax.core.metamodel import EntityIdentity, EntityMetadata, Metamodel, entity_by_name
from parallax.core.object_query import (
    IncludePath,
    IncludeSegment,
    ObjectQueryNode,
    validate_object_query,
)
from parallax.core.predicate import All, ModelRejectedError, Narrow, validate_predicate
from parallax.core.unit_work import instructions
from parallax.descriptor import _records as records
from parallax.descriptor._adapter import unresolved_metamodel
from parallax.snapshot import handle
from parallax.snapshot.handle import QueryTargetError


def _entity(name: str, namespace: str) -> records.Entity:
    key = records.Attribute(name="id", type="int64", column="id", primary_key=True)
    table = f"{namespace}_{name}".lower()
    return records.Entity(name=name, namespace=namespace, table=table, attributes=(key,))


def _model() -> Metamodel:
    """An accepted model with two same-named Entities in distinct namespaces
    (``a.Person`` / ``b.Person``) plus one uniquely-named ``c.Account``.

    Each Entity maps its own physical Table: name ambiguity is a resolution
    concern, while two independent owners of one Table is a rejected model.
    """
    return form_metamodel(
        unresolved_metamodel(
            records.Metamodel(
                (
                    _entity("Person", "a"),
                    _entity("Person", "b"),
                    _entity("Account", "c"),
                )
            )
        )
    )


def test_shared_helper_rejects_an_ambiguous_bare_name() -> None:
    model = _model()
    assert entity_by_name(model, "Person") is None
    person_a = entity_by_name(model, "a.Person")
    assert person_a is not None
    assert person_a.identity.canonical == "a.Person"
    account = entity_by_name(model, "Account")
    assert account is not None
    assert account.identity.canonical == "c.Account"
    assert entity_by_name(model, "Nope") is None


def test_predicate_resolver_rejects_an_ambiguous_bare_name() -> None:
    model = _model()
    root = entity_by_name(model, "a.Person")
    assert root is not None
    # A selection whose alternative is the ambiguous bare "Person" must not silently
    # resolve to whichever namespace's Person appears first. The miss is named as
    # the resolution failure it is, not as the empty resolved set it would
    # otherwise collapse into: a narrow rule would invite narrowing differently,
    # while the spelling itself is what names no position.
    op = Narrow(to=("Person",), operand=All())
    with pytest.raises(ModelRejectedError) as excinfo:
        validate_predicate(root, op, model)
    assert excinfo.value.rule == "reference-ambiguous-entity-name"


def test_the_write_boundary_classifies_an_ambiguous_bare_name_by_the_same_rule() -> None:
    # The write side of the same thesis: a deserialized instruction's target
    # resolves through the SAME helper, and its miss is classified with the SAME
    # normative rule name the predicate resolver uses — a different package and
    # a different exception class, one rule.
    model = _model()
    keyed = instructions.deserialize(
        {"mutation": "delete", "entity": "Person", "rows": [{"id": 1}]}
    )
    with pytest.raises(instructions.InstructionRejectedError) as excinfo:
        instructions.validate_instruction(keyed, model)
    assert excinfo.value.rule == "reference-ambiguous-entity-name"

    canonical = instructions.deserialize(
        {"mutation": "delete", "entity": "a.Person", "rows": [{"id": 1}]}
    )
    instructions.validate_instruction(canonical, model)


def _query(target: str, includes: tuple[IncludePath, ...] = ()) -> ObjectQueryNode:
    """A find-all Object Query against the authored spelling ``target``."""
    namespace, _, name = target.rpartition(".")
    return ObjectQueryNode(
        target=EntityIdentity(namespace or None, name), predicate=All(), includes=includes
    )


class _RefusingPort:
    """Every adapter call is a failure — a read refused for its spelling reaches
    none of them."""

    dialect: Dialect = POSTGRES

    def execute(
        self, sql: str, binds: object, document_reads: Sequence[tuple[int, int]] = ()
    ) -> list[dict[str, object]]:
        raise AssertionError(f"the read reached the adapter: {sql!r}")

    def execute_write(self, sql: str, binds: object) -> int:
        raise AssertionError(f"the read reached the adapter: {sql!r}")

    def transaction(self, body: object) -> object:
        raise AssertionError("the read opened a transaction")


def test_the_read_executor_classifies_an_ambiguous_bare_name_by_the_same_rule() -> None:
    # The read side: the find executor resolves its target spelling through the
    # same helper, and reports the same rule through `predicate`'s own rejected
    # carrier — so one rule and one class answer an ambiguous spelling whether
    # preflight or lowering resolves it.
    with pytest.raises(ModelRejectedError) as excinfo:
        model = _model()
        handle.find(
            _query("Person"),
            CatalogedModel(model),
            cast("DbPort", _RefusingPort()),
        )
    assert excinfo.value.rule == "reference-ambiguous-entity-name"


def test_the_read_executor_refuses_a_target_the_model_does_not_declare() -> None:
    # The other half of the executor's own classification: `find` / `find_history`
    # are exported and take a bare target spelling, so an undeclared one reaches
    # this seam and earns the same `query-target-not-in-model` refusal the read
    # preflight answers with — never a bare `KeyError` from a lookup miss.
    with pytest.raises(QueryTargetError) as excinfo:
        model = _model()
        handle.find(
            _query("Nope"),
            CatalogedModel(model),
            cast("DbPort", _RefusingPort()),
        )
    assert excinfo.value.code == "query-target-not-in-model"


def test_a_canonical_spelling_names_one_of_two_twins_at_every_reference_position() -> None:
    # The counterpart to the refusal above: the SAME two-namespace model, addressed
    # canonically. Each position that resolves an Entity spelling — a narrow's
    # `to` entries and an attribute's Entity prefix — names exactly one
    # twin, and the twin it names is the one the namespace segment selects.
    model = _model()
    root = _named(model, "a.Person")

    narrow = Narrow(to=("a.Person",), operand=All())
    validate_predicate(root, narrow, model)

    predicate = oa.Comparison(op="eq", attr="a.Person.id", value=1)
    validate_predicate(root, predicate, model)

    # The other twin is a different Entity, so its attribute is outside this
    # position rather than merely ambiguous.
    with pytest.raises(ModelRejectedError) as excinfo:
        validate_predicate(root, oa.Comparison(op="eq", attr="b.Person.id", value=1), model)
    assert excinfo.value.rule == "attribute-outside-active-position"


def test_sql_lowering_reaches_the_table_the_canonical_spelling_names() -> None:
    # The whole point of the widened grammar: two Entities sharing a local name are
    # separately addressable, and the SQL proves WHICH one a spelling reached.
    model = _model()

    for namespace in ("a", "b"):
        root = _named(model, f"{namespace}.Person")
        op = oa.Comparison(op="eq", attr=f"{namespace}.Person.id", value=1)
        validate_predicate(root, op, model)
        compiled = compile_read(op, model, POSTGRES, root)
        assert compiled.statement.sql == (
            f"select t0.id from {namespace}_person t0 where t0.id = ?"
        )


# --------------------------------------------------------------------------- #
# The same rule at the LOWERING seams.                                         #
#                                                                              #
# A namespace is declared per class and never inherited, so a family root and   #
# its own concrete subtypes may sit in different namespaces — and a reference   #
# position spells them all bare. Resolving such a spelling into the REFERRING   #
# Entity's namespace (the declaration rule) answers a different Entity than     #
# `validate_predicate` resolved it to, so the read preflight accepted           #
# failed to lower. Nothing in the shipped corpus exhibits it: every corpus      #
# family restates one namespace on every member.                                #
# --------------------------------------------------------------------------- #
def _cross_namespace_model() -> Metamodel:
    """An accepted model whose family root, concrete subtypes, and relationship
    peer each sit in a DIFFERENT namespace, every local name unique model-wide.

    ``zoo.Beast`` is the table-per-hierarchy root over the ownerless ``Wolf`` and
    ``Bear``; ``den.Den`` owns them through ``denId``. Every query reference
    below therefore names an Entity outside the namespace of the position it is
    written against, which is exactly the case the two resolution rules answer
    differently.
    """
    beast = records.Entity(
        name="Beast",
        namespace="zoo",
        table="beast",
        inheritance=records.Inheritance(
            role="root", strategy="table-per-hierarchy", tag_column="kind"
        ),
        attributes=(
            records.Attribute(name="id", type="int64", column="id", primary_key=True),
            records.Attribute(name="denId", type="int64", column="den_id", nullable=True),
        ),
        relationships=(records.ReverseRelationship(name="den", reverse_of="den.Den.beasts"),),
    )
    wolf = records.Entity(
        name="Wolf",
        inheritance=records.Inheritance(
            role="concrete-subtype", parent="zoo.Beast", tag_value="wolf"
        ),
        attributes=(records.Attribute(name="howl", type="string", column="howl", nullable=True),),
    )
    bear = records.Entity(
        name="Bear",
        inheritance=records.Inheritance(
            role="concrete-subtype", parent="zoo.Beast", tag_value="bear"
        ),
        attributes=(
            records.Attribute(
                name="hibernates", type="boolean", column="hibernates", nullable=True
            ),
        ),
    )
    den = records.Entity(
        name="Den",
        namespace="den",
        table="den",
        attributes=(records.Attribute(name="id", type="int64", column="id", primary_key=True),),
        relationships=(
            records.DefiningRelationship(
                name="beasts",
                cardinality="one-to-many",
                join=records.RelationshipJoin(
                    source="id",
                    target=records.RelationshipTarget(entity="zoo.Beast", attribute="denId"),
                ),
            ),
        ),
    )
    return form_metamodel(unresolved_metamodel(records.Metamodel((beast, wolf, bear, den))))


def _named(model: Metamodel, name: str) -> EntityMetadata:
    entity = entity_by_name(model, name)
    assert entity is not None
    return entity


def test_sql_lowering_resolves_a_narrow_across_namespaces() -> None:
    # The top-level narrow and the mid-predicate branch narrow both resolve `Wolf`
    # against the model, not against `zoo.Beast`'s namespace, so each lowers to the
    # tag guard the accepted query asked for.
    model = _cross_namespace_model()
    root = _named(model, "zoo.Beast")

    top_level = Narrow(to=("Wolf",), operand=All())
    validate_predicate(root, top_level, model)
    assert compile_read(top_level, model, POSTGRES, root).statement.binds == ("wolf",)

    branches = oa.Or(
        operands=(
            Narrow(to=("Wolf",), operand=All()),
            Narrow(to=("Bear",), operand=All()),
        )
    )
    validate_predicate(root, branches, model)
    assert compile_read(branches, model, POSTGRES, root).statement.binds == ("wolf", "bear")


def test_sql_lowering_resolves_a_hop_and_its_narrow_across_namespaces() -> None:
    # Two references in one query: the hop's own `Den.beasts` (resolved from a
    # position in the `den` namespace to a relationship whose target is in `zoo`)
    # and the narrow inside it (`Wolf`, resolved from `zoo.Beast`).
    model = _cross_namespace_model()
    den = _named(model, "den.Den")

    op = oa.Exists(rel="Den.beasts", op=Narrow(to=("Wolf",), operand=All()))
    validate_predicate(den, op, model)
    compiled = compile_read(op, model, POSTGRES, den)
    assert compiled.statement.sql == (
        "select t0.id from den t0 where exists (select 1 from beast t1 "
        "where t1.den_id = t0.id and t1.kind = ?)"
    )
    assert compiled.statement.binds == ("wolf",)


def test_deep_fetch_planning_resolves_every_reference_across_namespaces() -> None:
    # A segment narrow, a path-root guard, and a segment whose `Class` prefix names
    # the family root from a path rooted at an ownerless concrete subtype — the
    # three deep-fetch reference positions, each pointing outside its own namespace.
    model = _cross_namespace_model()
    den = _named(model, "den.Den")
    beast = _named(model, "zoo.Beast")
    wolf = _named(model, "Wolf")

    segment_narrow = _query(
        "den.Den",
        includes=(IncludePath(segments=(IncludeSegment(rel="Den.beasts", narrow_to=("Wolf",)),)),),
    )
    validate_object_query(den, segment_narrow, model)
    assert [level.attach_key for level in deep_fetch.plan(den, segment_narrow, model).levels] == [
        "beasts[Wolf]"
    ]

    root_guard = _query(
        "zoo.Beast",
        includes=(IncludePath(applies_to=("Wolf",), segments=(IncludeSegment(rel="Beast.den"),)),),
    )
    validate_object_query(beast, root_guard, model)
    guarded = deep_fetch.plan(beast, root_guard, model).levels
    assert [level.source_position for level in guarded] == [(wolf.identity,)]

    from_subtype = _query("Wolf", (IncludePath(segments=(IncludeSegment(rel="Beast.den"),)),))
    validate_object_query(wolf, from_subtype, model)
    assert [level.attach_key for level in deep_fetch.plan(wolf, from_subtype, model).levels] == [
        "den"
    ]


def test_navigation_canonicalization_resolves_a_hop_from_another_namespace() -> None:
    # The hop's `Class` prefix names the family ROOT while the queried position is
    # the ownerless concrete subtype, so the owner-relative rule looked for a
    # `Beast` that does not exist. There is no as-of term to inject on this model,
    # so canonicalization returning the query unchanged is the whole proof that
    # the reference resolved.
    model = _cross_namespace_model()
    wolf = _named(model, "Wolf")

    op = oa.Exists(rel="Beast.den")
    validate_predicate(wolf, op, model)
    assert navigate.canonicalize(op, model, wolf) == op


def test_every_lowering_seam_resolves_a_canonically_spelled_reference() -> None:
    # The same three seams, asked with the canonical spelling of each reference
    # rather than the bare one. `zoo.Beast` and `den.Den` are namespaced while the
    # concrete subtypes are ownerless, so a canonical spelling and a bare one
    # coincide for `Wolf` — which is what makes the namespaced positions the
    # load-bearing half of each assertion.
    model = _cross_namespace_model()
    den = _named(model, "den.Den")
    beast = _named(model, "zoo.Beast")
    wolf = _named(model, "Wolf")

    hop = oa.Exists(rel="den.Den.beasts", op=Narrow(to=("Wolf",), operand=All()))
    validate_predicate(den, hop, model)
    compiled = compile_read(hop, model, POSTGRES, den)
    assert compiled.statement.sql == (
        "select t0.id from den t0 where exists (select 1 from beast t1 "
        "where t1.den_id = t0.id and t1.kind = ?)"
    )
    assert compiled.statement.binds == ("wolf",)

    root_guard = _query(
        "zoo.Beast",
        (IncludePath(applies_to=("Wolf",), segments=(IncludeSegment(rel="zoo.Beast.den"),)),),
    )
    validate_object_query(beast, root_guard, model)
    guarded = deep_fetch.plan(beast, root_guard, model).levels
    assert [level.source_position for level in guarded] == [(wolf.identity,)]

    navigation = oa.Exists(rel="zoo.Beast.den")
    validate_predicate(wolf, navigation, model)
    assert navigate.canonicalize(navigation, model, wolf) == navigation
