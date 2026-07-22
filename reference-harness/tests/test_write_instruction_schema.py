"""DB-free tests for the canonical write-instruction schema (m-unit-work).

`write-instruction.schema.json` is the write-side analogue of
`operation.schema.json`: the canonical, axis-explicit vocabulary a unit of work
buffers. These tests pin the two instruction shapes (keyed + predicate), the
axis-explicit Valid-Time bounds, the absence of a Transaction-Time-instant field, and the
verb / bound conditionals.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from reference_harness import serde

_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2] / "core" / "schemas" / "write-instruction.schema.json"
)


def _validator() -> Draft202012Validator:
    return Draft202012Validator(json.loads(_SCHEMA_PATH.read_text(encoding="utf-8")))


def _valid(doc: dict[str, Any]) -> bool:
    return next(_validator().iter_errors(doc), None) is None


def test_schema_is_meta_valid() -> None:
    Draft202012Validator.check_schema(json.loads(_SCHEMA_PATH.read_text(encoding="utf-8")))


# --- keyed instructions -------------------------------------------------------


def test_keyed_plain_insert_is_valid() -> None:
    assert _valid({"mutation": "insert", "entity": "Balance", "rows": [{"id": 1, "value": 100.0}]})


def test_keyed_plain_temporal_carries_valid_from_only() -> None:
    assert _valid(
        {
            "mutation": "update",
            "entity": "Balance",
            "rows": [{"id": 1, "value": 150.0}],
            "validFrom": "2024-06-01T00:00:00+00:00",
        }
    )


def test_keyed_until_requires_both_valid_time_bounds() -> None:
    # Every bounded `*Until` operation is over `[validFrom, until)`
    # (m-bitemp-write), so BOTH bounds are required — dropping either rejects it.
    doc = {
        "mutation": "updateUntil",
        "entity": "Position",
        "rows": [{"id": 1, "value": 9}],
        "validFrom": "2024-01-01T00:00:00+00:00",
        "until": "2024-06-01T00:00:00+00:00",
    }
    assert _valid(doc)
    assert not _valid({key: value for key, value in doc.items() if key != "until"})
    assert not _valid({key: value for key, value in doc.items() if key != "validFrom"})


def test_keyed_plain_mutation_rejects_a_window_end() -> None:
    assert not _valid(
        {"mutation": "insert", "entity": "Balance", "rows": [{"id": 1}], "until": "x"}
    )


def test_keyed_rejects_a_transaction_instant_field() -> None:
    # The Transaction-Time instant is Clock-supplied context, never an instruction field.
    assert not _valid(
        {"mutation": "insert", "entity": "Balance", "rows": [{"id": 1}], "at": "2024-01-01"}
    )


# --- the framework-owned observation is NOT durable instruction state (m-unit-work) --


def test_keyed_instruction_row_rejects_observed_version() -> None:
    # The optimistic-lock version is attached per materialized row at FLUSH (ADR 0013),
    # never carried on the durable instruction, so it cannot ride in a keyed write row.
    assert not _valid(
        {
            "mutation": "update",
            "entity": "Balance",
            "rows": [{"id": 1, "value": 150.0, "observedVersion": 3}],
        }
    )


def test_keyed_instruction_row_rejects_observed_tx_start() -> None:
    # The observed Transaction-Time start (`in_z`) is the temporal analogue of the version;
    # like it, the observation is flush context, never an instruction field.
    assert not _valid(
        {
            "mutation": "terminate",
            "entity": "Balance",
            "rows": [{"id": 1, "observedTxStart": "2024-01-01T00:00:00+00:00"}],
        }
    )


def test_observation_cannot_round_trip_as_instruction_state() -> None:
    """An observation attached to an instruction row cannot survive as instruction state.

    Serde round-trips the canonical form losslessly, but the SCHEMA is the gate: an
    instruction that carries the framework-owned `observedVersion` is invalid, so an
    implementation cannot serialize an observation-bearing row, round-trip it, and have
    it validate back as a durable instruction — the observation has no home here.
    """
    clean = {"mutation": "update", "entity": "Balance", "rows": [{"id": 1, "value": 150.0}]}
    assert _valid(clean)
    # Round-trip fidelity holds for the clean instruction (write-side serde contract).
    assert serde.roundtrip(clean, serde.JSON) == clean
    assert serde.roundtrip(clean, serde.YAML) == clean
    # Attaching the framework-owned observation makes it NOT a valid instruction, and it
    # still fails to validate after a lossless serde round-trip — the observation cannot
    # round-trip INTO instruction state on either axis.
    smuggled_version = {
        "mutation": "update",
        "entity": "Balance",
        "rows": [{"id": 1, "value": 150.0, "observedVersion": 3}],
    }
    smuggled_in_z = {
        "mutation": "terminate",
        "entity": "Balance",
        "rows": [{"id": 1, "observedTxStart": "2024-01-01T00:00:00+00:00"}],
    }
    for smuggled in (smuggled_version, smuggled_in_z):
        assert not _valid(smuggled)
        assert not _valid(serde.roundtrip(smuggled, serde.JSON))
        assert not _valid(serde.roundtrip(smuggled, serde.YAML))


def test_keyed_value_object_document_and_pk_marker_rows() -> None:
    assert _valid(
        {
            "mutation": "insert",
            "entity": "Customer",
            "rows": [{"id": {"computed": "maxPlusOne"}, "address": {"city": "Oslo"}}],
        }
    )


# --- predicate instructions ---------------------------------------------------


def test_predicate_update_requires_assignments() -> None:
    doc = {
        "mutation": "update",
        "target": {
            "entity": "Account",
            "predicate": {"lessThan": {"attr": "Account.balance", "value": 200}},
        },
        "assignments": [{"attr": "Account.balance", "value": 0}],
    }
    assert _valid(doc)
    del doc["assignments"]
    assert not _valid(doc)


def test_predicate_delete_rejects_assignments() -> None:
    assert not _valid(
        {
            "mutation": "delete",
            "target": {
                "entity": "Account",
                "predicate": {"eq": {"attr": "Account.id", "value": 1}},
            },
            "assignments": [{"attr": "Account.balance", "value": 0}],
        }
    )


def test_predicate_until_requires_both_valid_time_bounds() -> None:
    # A bounded `*Until` predicate write is over `[validFrom, until)`
    # (m-bitemp-write); both bounds are required.
    doc = {
        "mutation": "terminateUntil",
        "target": {"entity": "Position", "predicate": {"eq": {"attr": "Position.id", "value": 1}}},
        "validFrom": "2024-01-01T00:00:00+00:00",
        "until": "2024-06-01T00:00:00+00:00",
    }
    assert _valid(doc)
    assert not _valid({key: value for key, value in doc.items() if key != "until"})
    assert not _valid({key: value for key, value in doc.items() if key != "validFrom"})


def test_instruction_rejects_unknown_top_level_key() -> None:
    assert not _valid(
        {"mutation": "insert", "entity": "Balance", "rows": [{"id": 1}], "bogus": True}
    )
