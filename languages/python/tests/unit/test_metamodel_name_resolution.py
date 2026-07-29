"""Bare-or-canonical Entity name resolution over a bare accepted model.

Pins the ambiguity-rejecting contract shared by every frontend seam that
resolves an authored Entity spelling against an accepted ``Metamodel``: an exact
canonical spelling matches, a bare name matches only when a single Entity
carries it, and a bare name two namespaces share is a miss rather than a silent
first match. The ``op_algebra.validate``, snapshot
materialize, unit-of-work, and write-lowering seams all resolve through the same
``entity_by_name`` helper, so its rule governs each of them.
"""

from __future__ import annotations

import pytest

from parallax.core._formation_profile import form_metamodel
from parallax.core.metamodel import Metamodel, entity_by_name
from parallax.core.op_algebra import All, Narrow, OperationRejectedError, validate_operation
from parallax.descriptor import _records as records
from parallax.descriptor._adapter import unresolved_metamodel


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


def test_op_algebra_resolver_rejects_an_ambiguous_bare_name() -> None:
    model = _model()
    root = entity_by_name(model, "a.Person")
    assert root is not None
    # A narrow whose `entity` is the ambiguous bare "Person" must not silently
    # resolve to whichever namespace's Person appears first; the miss collapses
    # the resolved set, so the narrow is rejected rather than validated against
    # an arbitrarily chosen Entity.
    op = Narrow(entity="Person", to=("Person",), operand=All())
    with pytest.raises(OperationRejectedError) as excinfo:
        validate_operation(root, op, model)
    assert excinfo.value.rule == "narrow-empty-effective-set"
