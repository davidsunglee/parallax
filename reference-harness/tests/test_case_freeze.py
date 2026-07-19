"""The parsed compatibility corpus is deeply immutable and safely shared.

``discover_cases``/``load_case``/``load_model`` hand every caller the *same*
parsed graph. That is only sound because the graph rejects writes: before the
freeze, per-call re-parsing was the sole thing isolating the corruption tests
from one another, an implicit contract that nothing stated and nothing enforced.

These tests pin the contract itself — that a write raises, that the freeze
reaches aliased inner nodes, and that ``copy.deepcopy`` remains the sanctioned
way out. They are the guard rail that makes sharing one parsed graph between
callers safe rather than merely fast.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from reference_harness.case import discover_cases, load_model
from reference_harness.inheritance import resolve_effective_definition

COMPATIBILITY_ROOT = Path(__file__).resolve().parents[2] / "core" / "compatibility"


def _any_case():
    """One arbitrary parsed case — the contract is graph-wide, not case-specific."""
    return discover_cases(COMPATIBILITY_ROOT)[0]


def test_case_raw_rejects_item_assignment() -> None:
    case = _any_case()
    with pytest.raises(TypeError):
        case.raw["model"] = "models/hacked.yaml"


def test_case_raw_rejects_key_deletion() -> None:
    case = _any_case()
    with pytest.raises(TypeError):
        del case.raw["model"]


def test_nested_case_document_rejects_item_assignment() -> None:
    """The freeze is recursive — an inner node is as immutable as the root."""
    case = next(c for c in discover_cases(COMPATIBILITY_ROOT) if c.when)
    with pytest.raises(TypeError):
        case.when["injected"] = True


def test_model_descriptor_attribute_list_rejects_append() -> None:
    """Sequence nodes reject in-place growth, not just mapping nodes."""
    model = load_model(COMPATIBILITY_ROOT, "models/payment.yaml")
    attributes = model.descriptor["entities"][0]["attributes"]
    with pytest.raises(TypeError):
        attributes.append({"name": "injected", "type": "string", "column": "injected"})


def test_model_fixtures_reject_mutation() -> None:
    model = load_model(COMPATIBILITY_ROOT, "models/payment.yaml")
    with pytest.raises(TypeError):
        model.fixtures["injected"] = []


def test_inheritance_effective_definition_alias_stays_frozen() -> None:
    """The alias `_merge_ancestry_attributes` splices in must not be a side door.

    That helper appends the *original* ancestor attribute dicts into the list it
    returns rather than copies of them, so a shallow freeze would leave an
    inheritance participant's inherited attributes writable through the flattened
    definition — corrupting the ancestor for every later reader of the shared
    graph. The returned list is itself a fresh, mutable list; it is the elements
    that must stay frozen.
    """
    model = load_model(COMPATIBILITY_ROOT, "models/payment.yaml")
    resolved = resolve_effective_definition(list(model.descriptor["entities"]), "CardPayment")
    inherited = next(a for a in resolved["attributes"] if a["name"] == "amount")
    with pytest.raises(TypeError):
        inherited["column"] = "hijacked"


def test_deepcopy_yields_a_fully_mutable_graph() -> None:
    """The sanctioned escape hatch: negative tests build malformed input this way."""
    case = copy.deepcopy(_any_case())
    case.raw["model"] = "models/damaged.yaml"
    assert case.raw["model"] == "models/damaged.yaml"


def test_deepcopy_does_not_disturb_the_shared_original() -> None:
    original = _any_case()
    before = original.raw["model"]
    damaged = copy.deepcopy(original)
    damaged.raw["model"] = "models/damaged.yaml"
    assert _any_case().raw["model"] == before


def test_frozen_nodes_are_still_dict_and_list_instances() -> None:
    """Load-bearing: ~176 `isinstance(x, dict)`/`isinstance(x, list)` shape checks
    across the harness (schema_validate, sql_lint, inheritance, case_runner, …)
    must keep seeing corpus documents as the builtins they are. Freezing to
    `MappingProxyType`/`tuple` would fail every one of them silently, turning an
    immutability change into a behavior change.
    """
    model = load_model(COMPATIBILITY_ROOT, "models/payment.yaml")
    assert isinstance(model.descriptor, dict)
    assert isinstance(model.descriptor["entities"], list)
    assert isinstance(model.descriptor["entities"][0], dict)
    assert isinstance(model.descriptor["entities"][0]["attributes"], list)


def test_frozen_nodes_compare_equal_to_plain_literals() -> None:
    """Equality against plain `dict`/`list` literals is what the assertions in the
    existing suite are written against; the freeze must not disturb it."""
    model = load_model(COMPATIBILITY_ROOT, "models/payment.yaml")
    entity = model.descriptor["entities"][0]
    assert entity["inheritance"] == dict(entity["inheritance"])
    assert entity["attributes"] == list(entity["attributes"])
