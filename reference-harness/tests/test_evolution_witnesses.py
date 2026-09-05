"""The corpus witnesses every name a descriptor pair can reach — DB-free.

ADR 0063 fixes closed algebras, and `compatibility-case.schema.json` spells them
as enums. A closed vocabulary with an unwitnessed name is a portability claim no
implementation is measured against, so these tests read the enums back out of the
schema and require each name to appear in some case's `then.evolution`, together
with both directions of the boundaries the specification calls directional.

Three names are exempt, and the exemption is the one place this falls short of
the portable proof ADR 0063 asks for: no pair of model descriptors can reach
them, for the structural reason `_UNREACHABLE_FROM_A_DESCRIPTOR` states and
`test_a_surviving_axis_cannot_change_its_endpoints` proves.

The property is the CORPUS's, not one implementation's, which is why it lives in
the harness: it fails when a name is added to the vocabulary and no case is
authored for it, whoever wrote the implementation.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any, Final

import pytest

from reference_harness.case import Case, discover_cases, load_model
from reference_harness.temporality import TEMPORAL_MEMBERS, temporal_axes

_REPO_ROOT = Path(__file__).resolve().parents[2]
_COMPATIBILITY_ROOT = _REPO_ROOT / "core" / "compatibility"
_CASE_SCHEMA = _REPO_ROOT / "core" / "schemas" / "compatibility-case.schema.json"

# A surviving As-Of Axis cannot report changed endpoints in a corpus case: a
# descriptor spells one Temporality Profile and the profile derives each axis's
# endpoint Attributes from its dimension alone, so two endpoints agreeing on
# (Entity, Temporal Dimension) agree on the endpoints too. The vocabulary keeps
# the names because an accepted Metamodel reaching `m-metamodel` directly may
# carry other endpoints; the Python unit suite witnesses them there.
# `test_a_surviving_axis_cannot_change_its_endpoints` proves the exemption.
_UNREACHABLE_FROM_A_DESCRIPTOR: Final[frozenset[str]] = frozenset(
    {"AsOfAxisAltered", "StartAttributeChanged", "EndAttributeChanged"}
)


def _schema_enum(name: str) -> frozenset[str]:
    definitions = json.loads(_CASE_SCHEMA.read_text(encoding="utf-8"))["$defs"]
    return frozenset(definitions[name]["enum"])


def _evolution_cases() -> list[Case]:
    return [case for case in discover_cases(_COMPATIBILITY_ROOT) if case.is_evolution]


_CASES: Final[list[Case]] = _evolution_cases()


def _operations() -> Iterator[Mapping[str, Any]]:
    for case in _CASES:
        evolution = case.expected_evolution or {}
        for operation in evolution.get("operations") or []:
            if isinstance(operation, Mapping):
                yield operation


def _deltas() -> Iterator[Mapping[str, Any]]:
    for operation in _operations():
        for delta in operation.get("deltas") or []:
            if isinstance(delta, Mapping):
                yield delta


def _requirements() -> Iterator[Mapping[str, Any]]:
    for case in _CASES:
        evolution = case.expected_evolution or {}
        for requirement in evolution.get("coordinationRequirements") or []:
            if isinstance(requirement, Mapping):
                yield requirement


def _impacts() -> Iterator[Mapping[str, Any]]:
    for case in _CASES:
        evolution = case.expected_evolution or {}
        for impact in evolution.get("behavioralImpacts") or []:
            if isinstance(impact, Mapping):
                yield impact


def _directions(kind: str) -> set[tuple[Any, Any]]:
    return {
        (_hashable(delta.get("earlier")), _hashable(delta.get("later")))
        for delta in _deltas()
        if delta.get("kind") == kind
    }


def _hashable(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(_hashable(item) for item in value)  # pyright: ignore[reportUnknownVariableType] - parsed YAML hands its items over as unknowns
    if isinstance(value, dict):
        return tuple(sorted((key, _hashable(item)) for key, item in value.items()))  # pyright: ignore[reportUnknownVariableType] - parsed YAML hands its items over as unknowns
    return value


def test_the_corpus_has_evolution_cases() -> None:
    assert _CASES, "no evolution cases discovered under core/compatibility/cases"


def test_every_evolution_operation_kind_has_a_witness() -> None:
    witnessed = {str(operation.get("kind")) for operation in _operations()}
    expected = _schema_enum("evolutionOperationKind") - _UNREACHABLE_FROM_A_DESCRIPTOR
    assert expected - witnessed == set()


def test_every_field_delta_kind_has_a_witness() -> None:
    witnessed = {str(delta.get("kind")) for delta in _deltas()}
    expected = _schema_enum("evolutionFieldDeltaKind") - _UNREACHABLE_FROM_A_DESCRIPTOR
    assert expected - witnessed == set()


def test_every_behavioral_impact_kind_has_a_witness() -> None:
    witnessed = {str(impact.get("kind")) for impact in _impacts()}
    assert _schema_enum("behavioralImpactKind") - witnessed == set()


def test_every_coordination_reason_has_a_witness() -> None:
    witnessed = {
        str(reason)
        for requirement in _requirements()
        for reason in requirement.get("reasons") or []
    }
    assert _schema_enum("coordinationReason") - witnessed == set()


def test_every_declaration_collection_has_a_witness() -> None:
    witnessed = {
        str(operation.get("collection"))
        for operation in _operations()
        if operation.get("kind") == "DeclarationOrderChanged"
    }
    assert _schema_enum("declarationCollection") - witnessed == set()


def test_one_operation_is_witnessed_carrying_both_coordination_reasons() -> None:
    # An operation needing both appears ONCE with both reasons in fixed order,
    # so consumers never regroup duplicate entries.
    assert any(
        list(requirement.get("reasons") or [])
        == ["AuthoringSurfaceChangeRequired", "DatabaseMigrationRequired"]
        for requirement in _requirements()
    )


_BOOLEAN_DELTAS: Final[tuple[str, ...]] = (
    "NullabilityChanged",
    "ReadOnlyChanged",
    "OptimisticLockingChanged",
    "DependencyChanged",
    "UniquenessChanged",
)


@pytest.mark.parametrize("kind", _BOOLEAN_DELTAS)
def test_a_boolean_delta_is_witnessed_in_both_directions(kind: str) -> None:
    # Every boolean fact has exactly two moves, and a corpus witnessing one is a
    # corpus that never grades the other.
    assert _directions(kind) == {(False, True), (True, False)}


def test_a_string_bound_is_witnessed_relaxed_and_contracted() -> None:
    moves = _directions("MaximumLengthChanged")
    relaxed = {
        (earlier, later)
        for earlier, later in moves
        if later is None or (earlier is not None and earlier < later)
    }
    assert relaxed and moves - relaxed


def test_persistence_is_witnessed_withdrawn_and_granted() -> None:
    moves = _directions("PersistenceChanged")
    assert any(later == "read-only" for _, later in moves)
    assert any(earlier == "read-only" for earlier, _ in moves)


def test_multiplicity_is_witnessed_in_both_directions() -> None:
    assert _directions("MultiplicityChanged") == {("one", "many"), ("many", "one")}


_ADDITIONS: Final[tuple[str, ...]] = (
    "AttributeAdded",
    "ValueObjectOccurrenceAdded",
    "ValueObjectAttributeAdded",
)


@pytest.mark.parametrize("kind", _ADDITIONS)
def test_a_member_addition_is_witnessed_unilateral_and_coordinated(kind: str) -> None:
    # The addition boundary is the member's own nullability, so both verdicts
    # need a witness at every kind of member that can carry one.
    coordinated = {
        _hashable(requirement.get("operation"))
        for requirement in _requirements()
        if isinstance(operation := requirement.get("operation"), Mapping)
        and operation.get("kind") == kind
    }
    described = {
        _hashable(operation) for operation in _operations() if operation.get("kind") == kind
    }
    assert coordinated, f"no coordinated {kind} witness"
    assert described - coordinated, f"no unilateral {kind} witness"


def test_a_surviving_axis_cannot_change_its_endpoints() -> None:
    # The exemption above, proven rather than asserted: every corpus model's
    # As-Of Axis endpoints are the framework-fixed ones its Temporal Dimension
    # derives, so no two endpoints can agree on an axis position and disagree on
    # its endpoint Attributes.
    named = {*_earlier_models(), *(case.evolve_later for case in _CASES)}
    assert named
    for relative in sorted(path for path in named if path is not None):
        model = load_model(_COMPATIBILITY_ROOT, relative)
        for definition in model.entity_defs:
            for axis in temporal_axes(definition):
                start, end = TEMPORAL_MEMBERS[axis.dimension]
                assert (axis.start.name, axis.end.name) == (start.name, end.name), relative


def _earlier_models() -> Sequence[str]:
    return [case.evolve_earlier for case in _CASES if case.evolve_earlier is not None]
