"""The corpus witnesses every name a descriptor pair can reach — DB-free.

ADR 0063 fixes closed algebras, and `compatibility-case.schema.json` spells them
as enums. A closed vocabulary with an unwitnessed name is a portability claim no
implementation is measured against, so these tests read the enums back out of the
schema and require each name to appear in some case's `then.evolution`, together
with both directions of the boundaries the specification calls directional.

Three names are exempt, and ADR 0063's portable-proof obligation is written to
admit exactly them: it covers every name a pair of model descriptors can
express, while a name only an accepted Metamodel can produce is witnessed by the
implementation's own suite and proved unreachable here rather than asserted. The
proof reads the descriptor language itself — the closed temporal vocabulary
`m-descriptor.md` fixes and the corpus's own rejection fixtures — rather than
the models the evolution cases happen to name, so a language that grew a way to
spell a disagreeing endpoint would fail it.

The property is the CORPUS's, not one implementation's, which is why it lives in
the harness: it fails when a name is added to the vocabulary and no case is
authored for it, whoever wrote the implementation.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any, Final

import pytest

from reference_harness.case import Case, discover_cases
from reference_harness.corpus_yaml import read_corpus_yaml
from reference_harness.temporality import (
    TEMPORAL_MEMBERS,
    TEMPORALITY_PROFILES,
    Endpoint,
    temporal_axes,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_COMPATIBILITY_ROOT = _REPO_ROOT / "core" / "compatibility"
_CASE_SCHEMA = _REPO_ROOT / "core" / "schemas" / "compatibility-case.schema.json"
_DESCRIPTOR_SPEC = _REPO_ROOT / "core" / "spec" / "m-descriptor.md"

# The two normative tables `m-descriptor.md` fixes the temporal language with:
# the closed profile vocabulary, and the endpoint Attribute and column each
# Temporal Dimension derives.
_PROFILE_TABLE_HEADER = "| Profile | Derived As-Of Axes |"
_ENDPOINT_TABLE_HEADER = "| Dimension | Start Attribute / column | End Attribute / column |"

# A surviving As-Of Axis cannot report changed endpoints from any descriptor
# pair: a descriptor spells one Temporality Profile out of a closed vocabulary
# and the profile derives each axis's endpoint Attributes from its dimension
# alone, so two descriptors agreeing on (Entity, Temporal Dimension) agree on
# the endpoints too. The vocabulary keeps the names because an accepted
# Metamodel reaching `m-metamodel` directly may carry other endpoints, and ADR
# 0063 names this exemption where it states the portable-proof obligation: such
# a name is witnessed by the implementation's own suite, and the corpus proves
# it unreachable. The three tests below are that proof — the temporal alphabet
# is the language's own, one endpoint pair is derived per dimension across every
# descriptor the language spells, and an authored endpoint is rejected.
_UNREACHABLE_FROM_A_DESCRIPTOR: Final[frozenset[str]] = frozenset(
    {"AsOfAxisAltered", "StartAttributeChanged", "EndAttributeChanged"}
)


def _schema_enum(name: str) -> frozenset[str]:
    definitions = json.loads(_CASE_SCHEMA.read_text(encoding="utf-8"))["$defs"]
    return frozenset(definitions[name]["enum"])


def _physical_operation_kinds() -> frozenset[str]:
    """The closed physical-operation algebra, as the case schema spells it.

    The algebra is private to a generator, and the one place the corpus names it
    is the refusal an `unsupported` cell carries — which is why this enum, not a
    `$defs` of its own, is where the vocabulary is read back from.
    """
    definitions = json.loads(_CASE_SCHEMA.read_text(encoding="utf-8"))["$defs"]
    return frozenset(definitions["unsupportedSchemaOperation"]["properties"]["kind"]["enum"])


# What each physical operation looks like once it is a statement. A `delta` cell
# carries plain SQL and no operation kind — the algebra never crosses the
# generator's boundary — so a kind is witnessed either by a statement of its own
# shape or by an `unsupported` cell naming it. The shapes are the ones both
# dialects share; a widening is the one that diverges, and the alternation is
# that divergence rather than a second grammar.
_PHYSICAL_OPERATION_STATEMENTS: Final[Mapping[str, str]] = {
    "CreateTable": r"^create table\b",
    "AddColumn": r"^alter table \S+ add column\b",
    "ExpandColumnDomain": r"^alter table \S+ (alter column|modify)\b",
    "CreateIndex": r"^create (unique )?index\b",
    "DropIndex": r"^drop index\b",
}


def _authored_statements() -> Iterator[str]:
    for case in _CASES:
        for cell in (case.then.get("schema") or {}).values():
            delta = cell.get("delta") if isinstance(cell, Mapping) else None
            if isinstance(delta, Mapping):
                yield from (str(statement) for statement in delta.get("statements") or [])


def _refused_kinds() -> Iterator[str]:
    for case in _CASES:
        for cell in (case.then.get("schema") or {}).values():
            unsupported = cell.get("unsupported") if isinstance(cell, Mapping) else None
            if isinstance(unsupported, Mapping):
                yield from (
                    str(operation.get("kind"))
                    for operation in unsupported.get("operations") or []
                    if isinstance(operation, Mapping)
                )


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


def test_every_physical_operation_kind_has_a_witness() -> None:
    # A physical operation kind no case reaches is a lowering rule no
    # implementation is measured against, exactly as an unwitnessed Evolution
    # Operation is.
    statements = list(_authored_statements())
    witnessed = {
        kind
        for kind, shape in _PHYSICAL_OPERATION_STATEMENTS.items()
        if any(re.match(shape, statement) for statement in statements)
    } | set(_refused_kinds())
    assert _physical_operation_kinds() - witnessed == set()


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


def test_the_temporal_alphabet_is_the_one_the_descriptor_language_spells() -> None:
    # First half of the exemption's proof, and what makes the second half
    # exhaustive rather than a sample: `m-descriptor.md` fixes the closed
    # profile vocabulary and the normative dimension-to-endpoint table, so both
    # are read back out of the specification. A profile or endpoint the language
    # gains without the derivation following fails here.
    assert _spelled_profiles() == dict(TEMPORALITY_PROFILES)
    assert _spelled_endpoints() == dict(TEMPORAL_MEMBERS)


def test_no_two_descriptors_can_disagree_on_a_surviving_axis_endpoint() -> None:
    # Second half: every axis any pair of descriptors can put at one position,
    # derived from every profile the language spells and from definitions
    # differing in everything else a descriptor may carry. One endpoint pair per
    # Temporal Dimension means two descriptors agreeing on (Entity, Temporal
    # Dimension) agree on the endpoints too, so `AsOfAxisAltered` and its two
    # deltas have no descriptor pair that can emit them.
    spelled = _spelled_endpoints()
    derived: dict[str, set[tuple[Endpoint, Endpoint]]] = {}
    for definition in _every_definition_the_language_spells():
        for axis in temporal_axes(definition):
            derived.setdefault(axis.dimension, set()).add((axis.start, axis.end))
    assert set(derived) == set(spelled)
    assert all(pairs == {spelled[dimension]} for dimension, pairs in derived.items())


def test_no_descriptor_can_author_an_axis_endpoint() -> None:
    # The remaining route to a disagreeing endpoint is an authored one, and the
    # corpus's own rejection fixtures close it: an Attribute bearing a derived
    # endpoint's canonical name is a phase-3 value violation, and the retired
    # container that once spelled axes and endpoint references is rejected at
    # the entity's closed key set.
    authored = _rejection("value-temporal-attribute-declared")
    assert {violation["rule"] for violation in authored["violations"]} == {
        "temporal-attribute-declared"
    }
    container = _rejection("schema-retired-as-of-axes")
    assert container["code"] == "descriptor-schema-invalid"


def _every_definition_the_language_spells() -> Iterator[Mapping[str, Any]]:
    """Every temporal shape a descriptor entity can present to the derivation.

    One definition per profile the language spells plus the omitted profile,
    each also carried by a definition spelling everything else that could name
    an endpoint — an Attribute bearing an endpoint's canonical name over a
    different column, an inheritance parent, a layout, a Persistence Mode — so
    the derivation is shown to read the profile and nothing else.
    """
    yield {}
    for profile in _spelled_profiles():
        yield {"temporality": profile}
        yield {
            "name": "Anything",
            "temporality": profile,
            "attributes": [
                {"name": "validStart", "type": "timestamp", "column": "authored_from"},
                {"name": "txEnd", "type": "timestamp", "column": "authored_out"},
            ],
            "extends": "Root",
            "layout": "relational-document",
            "persistence": "read-only",
        }


def _spelled_profiles() -> dict[str, tuple[str, ...]]:
    return {row[0][0]: tuple(row[1]) for row in _spec_table(_PROFILE_TABLE_HEADER)}


def _spelled_endpoints() -> dict[str, tuple[Endpoint, Endpoint]]:
    return {
        row[0][0]: (Endpoint(*row[1]), Endpoint(*row[2]))
        for row in _spec_table(_ENDPOINT_TABLE_HEADER)
    }


def _spec_table(header: str) -> list[list[list[str]]]:
    """Each row under *header* in ``m-descriptor.md``, cell by cell.

    A cell answers with the backticked tokens it spells in order, which is how
    the normative tables mark the vocabulary they fix: prose around a token
    ("(default)", "none", "then") carries no name.
    """
    lines = _DESCRIPTOR_SPEC.read_text(encoding="utf-8").splitlines()
    rows: list[list[list[str]]] = []
    for line in lines[lines.index(header) + 2 :]:
        if not line.startswith("|"):
            break
        rows.append([re.findall(r"`([^`]+)`", cell) for cell in line.strip("|").split("|")])
    return rows


def _rejection(name: str) -> Mapping[str, Any]:
    return read_corpus_yaml(_COMPATIBILITY_ROOT / "descriptor-errors" / f"{name}.expected.yaml")
