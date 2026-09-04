"""The case oracle and the adapter envelope are one algebra, MIRRORED not shared.

`compatibility-case.schema.json` states what a case ASSERTS about the execution
lifecycle; `conformance-adapter.schema.json` states what an adapter REPORTS. A
runner grades one against the other, so the two must admit exactly the same
documents — a constraint present on one side alone makes the comparison reject
pairs the other side could have produced.

The write vocabulary solves this by single-sourcing across files
(`test_write_schema_sharing`). The adapter contract deliberately does not: it is
the schema an external language implementation reads to learn what envelope to
emit, and it stays consumable as one document. That buys self-containment and
costs a mirror that can drift, which is what these tests hold shut.

The covered set is derived from the files rather than listed here — every `$defs`
name defined in BOTH must agree, so a definition shared later is covered the day
it appears. `description` is the one licensed difference: each side describes its
own context, and the statement index in particular points at different things.
:data:`MIRRORED_DEFS` is a floor beneath that derivation, not the scope itself;
it fails when a rename on one side silently shrinks the intersection.

Name-derivation reaches every mirrored pair the two files spell alike. The
oracle wrapper is the one they do not: the case authors it INLINE at
`then.executionLifecycle` and the adapter names it
`$defs.executionLifecycleObservation`, so :data:`RENAMED_MIRRORS` registers that
pair explicitly and it is compared the same way.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from reference_harness.schemas import load_schemas

_CORE = Path(__file__).resolve().parents[2] / "core"
_SCHEMAS = load_schemas(_CORE)

_CASE_SCHEMA: dict[str, Any] = _SCHEMAS["compatibility-case.schema.json"]
_CASE_DEFS: dict[str, Any] = _CASE_SCHEMA["$defs"]
_ADAPTER_DEFS: dict[str, Any] = _SCHEMAS["conformance-adapter.schema.json"]["$defs"]

MIRRORED_DEFS = frozenset(
    {
        "behavioralImpact",
        "behavioralImpactKind",
        "coordinationReason",
        "coordinationRequirement",
        "declarationCollection",
        "evolutionFieldDelta",
        "evolutionFieldDeltaKind",
        "evolutionOperation",
        "evolutionOperationKind",
        "evolutionResult",
        "evolutionScope",
        "lifecycleRoot",
        "lifecycleEvent",
        "lifecycleNoFields",
        "lifecycleTarget",
        "lifecycleReadStarted",
        "lifecycleWriteBatchStarted",
        "lifecycleDatabaseCallStarted",
        "lifecycleDatabaseCallFinished",
        "lifecycleInvocationStarted",
        "lifecycleInvocationFinished",
        "lifecycleActivityOutcome",
        "lifecycleAttemptFinished",
        "lifecycleStreamStarted",
        "lifecycleStreamFinished",
        "lifecycleFailure",
    }
)

RENAMED_MIRRORS: dict[str, Any] = {
    "executionLifecycleObservation": _CASE_SCHEMA["properties"]["then"]["properties"][
        "executionLifecycle"
    ],
}


def _shared_def_names() -> list[str]:
    return sorted(set(_CASE_DEFS) & set(_ADAPTER_DEFS))


def _without_descriptions(node: Any) -> Any:
    if isinstance(node, dict):
        return {k: _without_descriptions(v) for k, v in node.items() if k != "description"}
    if isinstance(node, list):
        return [_without_descriptions(item) for item in node]
    return node


# --- the mirror itself ---------------------------------------------------------


def test_the_known_mirrored_definitions_are_still_defined_on_both_sides() -> None:
    """A rename on one side would shrink the intersection instead of failing."""
    assert MIRRORED_DEFS <= set(_shared_def_names())


def test_every_definition_the_two_schemas_share_is_structurally_identical() -> None:
    for name in _shared_def_names():
        assert _without_descriptions(_CASE_DEFS[name]) == _without_descriptions(
            _ADAPTER_DEFS[name]
        ), f"{name} has drifted between the case oracle and the adapter envelope"


def test_the_wrapper_the_two_files_name_differently_still_mirrors() -> None:
    """The union itself is the one pair name derivation cannot see."""
    for adapter_name, case_node in RENAMED_MIRRORS.items():
        assert _without_descriptions(case_node) == _without_descriptions(
            _ADAPTER_DEFS[adapter_name]
        ), f"{adapter_name} has drifted from the case oracle's own wrapper"


# --- what the comparison is blind to, and what it is not ------------------------


def test_each_side_keeps_its_own_statement_index_description() -> None:
    """The one difference the mirror licenses is real, not a formality.

    A Database Call's `statement` indexes the case's flattened authored golden
    order on the oracle side and the envelope's own `emissions` on the observed
    side. The prose says so per file; the structure is identical regardless.
    """
    case_call = _CASE_DEFS["lifecycleDatabaseCallStarted"]["description"]
    adapter_call = _ADAPTER_DEFS["lifecycleDatabaseCallStarted"]["description"]
    assert "golden" in case_call and "emissions" not in case_call
    assert "emissions" in adapter_call


def test_the_comparison_detects_a_constraint_present_on_one_side_alone() -> None:
    """The gate's own proof: a dropped conditional is drift, not a description."""
    weakened = copy.deepcopy(_ADAPTER_DEFS["lifecycleDatabaseCallFinished"])
    del weakened["allOf"]
    assert _without_descriptions(
        _CASE_DEFS["lifecycleDatabaseCallFinished"]
    ) != _without_descriptions(weakened)
