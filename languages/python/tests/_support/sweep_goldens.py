"""The corpus cases the compile and run sweeps grade against authored goldens.

Membership of a set here is the claim that the named cases' emitted SQL and binds
equal the case's own ``postgres`` golden byte for byte; the two readers below are
how both sweeps read that golden. Both sweeps grade the same claim, so the sets
and the readers are surface-neutral rather than owned by either.
"""

from __future__ import annotations

from typing import Any, Final, cast

from parallax.conformance import case_format
from parallax.core.metamodel import Metamodel
from tests._support.bind_positions import assert_zero_signs, statement_bind_positions
from tests._support.corpus import case_document, wire_value_deep

_SCALAR_READS: Final[frozenset[str]] = frozenset({"m-core-001", "m-descriptor-001"})
_VALUE_OBJECT_PREDICATE_READS: Final[frozenset[str]] = frozenset(
    f"m-value-object-{n:03d}" for n in (1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 48, 49, 54, 55)
)
_VALUE_OBJECT_TO_MANY_READS: Final[frozenset[str]] = frozenset(
    f"m-value-object-{n:03d}" for n in (*range(15, 23), *range(50, 54), *range(56, 66), 68)
)
_ORDERS_PREDICATE_READS: Final[frozenset[str]] = frozenset(
    f"m-predicate-{n:03d}" for n in (*range(1, 26), 29, 30, 31, 33, 34)
)
_ORDERS_OBJECT_QUERY_READS: Final[frozenset[str]] = frozenset(
    f"m-object-query-{n:03d}" for n in range(1, 8)
)
_VALUE_OBJECT_MATERIALIZATION_READS: Final[frozenset[str]] = frozenset(
    {"m-value-object-023", "m-value-object-024"}
)
_TEMPORAL_READ_ROW_FORM: Final[frozenset[str]] = frozenset(
    f"m-temporal-read-{n:03d}" for n in (*range(1, 9), 13, 14, 15, 16, 17)
)
_TEMPORAL_VALUE_OBJECT_READS: Final[frozenset[str]] = frozenset(
    f"m-value-object-{n:03d}" for n in (28, 29, 30, 31)
)
_INHERITANCE_READS: Final[frozenset[str]] = frozenset(
    f"m-inheritance-{n:03d}" for n in (*range(1, 7), *range(11, 18), 50, 51, 52, 53, 134, 135)
)
_INHERITANCE_TEMPORAL_READS: Final[frozenset[str]] = frozenset(
    {"m-inheritance-092", "m-inheritance-093"}
)
_INHERITANCE_CONCRETE_TARGET_TEMPORAL_READS: Final[frozenset[str]] = frozenset(
    {"m-inheritance-100", "m-inheritance-101"}
)
_NAVIGATE_READS: Final[frozenset[str]] = frozenset(
    {f"m-navigate-{n:03d}" for n in (*range(1, 12), 18, 23)}
)
_NAVIGATE_INHERITANCE_READS: Final[frozenset[str]] = frozenset(
    {"m-inheritance-060", "m-inheritance-061", "m-inheritance-062", "m-inheritance-063"}
    | {"m-inheritance-070", "m-inheritance-071", "m-inheritance-110"}
)
_SNAPSHOT_READ_MILESTONE_SET_READS: Final[frozenset[str]] = frozenset(
    {"m-snapshot-read-013", "m-snapshot-read-014"}
)
_INHERITANCE_INSTANCE_FORM_GRAPH_READS: Final[frozenset[str]] = frozenset(
    {"m-inheritance-106", "m-inheritance-107", "m-inheritance-108", "m-inheritance-109"}
    | {"m-inheritance-137"}
)
_READ_LOCK_READS: Final[frozenset[str]] = frozenset(
    {
        "m-read-lock-001",
        "m-read-lock-002",
        "m-read-lock-005",
        "m-read-lock-010",
        "m-read-lock-019",
        "m-read-lock-020",
    }
)
_DESCRIPTOR_DEFAULT_COLUMN_READS: Final[frozenset[str]] = frozenset({"m-descriptor-002"})
_MATERIALIZATION_KEY_COMPATIBILITY_READS: Final[frozenset[str]] = frozenset(
    {"m-inheritance-119", "m-inheritance-120"}
)
_STORAGE_LAYOUT_READS: Final[frozenset[str]] = frozenset(
    {"m-storage-layout-009", "m-storage-layout-010"}
)
_DOCUMENT_CODEC_READS: Final[frozenset[str]] = frozenset(
    f"m-document-codec-{n:03d}" for n in range(3, 14)
)
_STORAGE_LAYOUT_DOCUMENT_AND_TWIN_READS: Final[frozenset[str]] = frozenset(
    {f"m-storage-layout-{n:03d}" for n in (*range(17, 22), 25, 26)}
    | {
        "m-inheritance-123",
        "m-inheritance-124",
        "m-inheritance-126",
        "m-inheritance-127",
        "m-inheritance-136",
        "m-navigate-025",
    }
)
_CANONICAL_ENTITY_SPELLING_READS: Final[frozenset[str]] = frozenset({"m-predicate-051"})
_EXECUTION_LIFECYCLE_READS: Final[frozenset[str]] = frozenset({"m-execution-lifecycle-001"})
_CORRUPT_STORED_STATE_READS: Final[frozenset[str]] = frozenset({"m-snapshot-read-049"})
COMPILE_EXERCISED: Final[frozenset[str]] = (
    _SCALAR_READS
    | _DOCUMENT_CODEC_READS
    | _VALUE_OBJECT_PREDICATE_READS
    | _VALUE_OBJECT_TO_MANY_READS
    | _ORDERS_PREDICATE_READS
    | _ORDERS_OBJECT_QUERY_READS
    | _VALUE_OBJECT_MATERIALIZATION_READS
    | _TEMPORAL_READ_ROW_FORM
    | _TEMPORAL_VALUE_OBJECT_READS
    | _INHERITANCE_READS
    | _INHERITANCE_TEMPORAL_READS
    | _INHERITANCE_CONCRETE_TARGET_TEMPORAL_READS
    | _NAVIGATE_READS
    | _NAVIGATE_INHERITANCE_READS
    | _SNAPSHOT_READ_MILESTONE_SET_READS
    | _INHERITANCE_INSTANCE_FORM_GRAPH_READS
    | _READ_LOCK_READS
    | _DESCRIPTOR_DEFAULT_COLUMN_READS
    | _MATERIALIZATION_KEY_COMPATIBILITY_READS
    | _STORAGE_LAYOUT_READS
    | _STORAGE_LAYOUT_DOCUMENT_AND_TWIN_READS
    | _CANONICAL_ENTITY_SPELLING_READS
    | _EXECUTION_LIFECYCLE_READS
    | _CORRUPT_STORED_STATE_READS
)

_WRITE_SCENARIOS: Final[frozenset[str]] = frozenset(f"m-unit-work-{n:03d}" for n in (1, 8, 10, 11))
_READLESS_PREDICATE_WRITE_SCENARIOS: Final[frozenset[str]] = frozenset(
    {"m-batch-write-005", "m-batch-write-006", "m-batch-write-007"}
)
_READLESS_BARRIER_SCENARIOS: Final[frozenset[str]] = frozenset({"m-batch-write-011"})
_LOCKING_FALLBACK_SCENARIOS: Final[frozenset[str]] = frozenset({"m-opt-lock-023"})
_OBJECT_CLAIM_COALESCING_SCENARIOS: Final[frozenset[str]] = frozenset(
    {"m-unit-work-026", "m-unit-work-027"}
)
_OPT_LOCK_AND_PK_GEN_WRITE_SEQUENCES: Final[frozenset[str]] = frozenset(
    {
        "m-opt-lock-002",
        "m-opt-lock-026",
        "m-opt-lock-027",
        "m-opt-lock-028",
        "m-opt-lock-029",
        "m-unit-work-043",
        "m-unit-work-044",
        "m-inheritance-007",
        "m-inheritance-008",
        "m-inheritance-009",
        "m-inheritance-010",
        "m-inheritance-080",
        "m-inheritance-081",
        "m-inheritance-082",
        "m-inheritance-083",
        "m-inheritance-084",
        "m-inheritance-085",
        "m-inheritance-104",
        "m-pk-gen-001",
        "m-pk-gen-002",
        "m-pk-gen-003",
        "m-pk-gen-013",
        "m-batch-write-004",
    }
)
_BATCH_COLLAPSE_WRITE_SEQUENCES: Final[frozenset[str]] = frozenset(
    {"m-batch-write-001", "m-batch-write-003", "m-value-object-045"}
)
_DECIMAL_PRECISION_WRITE_SEQUENCES: Final[frozenset[str]] = frozenset({"m-core-007"})
_STORAGE_LAYOUT_WRITE_SEQUENCES: Final[frozenset[str]] = frozenset(
    {
        "m-storage-layout-006",
        "m-storage-layout-007",
        "m-storage-layout-008",
        "m-storage-layout-011",
    }
)
_DOCUMENT_LAYOUT_WRITE_SEQUENCES: Final[frozenset[str]] = frozenset(
    {
        "m-storage-layout-022",
        "m-storage-layout-023",
        "m-value-object-067",
        "m-document-codec-001",
        "m-document-codec-002",
        "m-opt-lock-018",
        "m-inheritance-125",
        "m-inheritance-128",
    }
)
_LAYOUT_TWIN_WRITES: Final[frozenset[str]] = frozenset(
    {f"m-storage-layout-{n:03d}" for n in range(29, 35)}
    | {"m-txtime-write-013", "m-txtime-write-014"}
)
_FLOAT_WRITE_SEQUENCES: Final[frozenset[str]] = frozenset(
    {
        "m-document-codec-014",
        "m-document-codec-015",
        "m-document-codec-016",
        "m-document-codec-017",
        "m-core-009",
        "m-core-010",
    }
)
_WRITE_SEQUENCES: Final[frozenset[str]] = (
    frozenset({"m-unit-work-003", "m-unit-work-007", "m-batch-write-002"})
    | _OPT_LOCK_AND_PK_GEN_WRITE_SEQUENCES
    | _BATCH_COLLAPSE_WRITE_SEQUENCES
    | _DECIMAL_PRECISION_WRITE_SEQUENCES
    | _STORAGE_LAYOUT_WRITE_SEQUENCES
    | _DOCUMENT_LAYOUT_WRITE_SEQUENCES
    | _FLOAT_WRITE_SEQUENCES
)
_SNAPSHOT_MUTATE_SCENARIOS: Final[frozenset[str]] = frozenset({"m-snapshot-read-010"})
_TEMPORAL_WRITE_SEQUENCES: Final[frozenset[str]] = frozenset(
    {
        "m-txtime-write-001",
        "m-txtime-write-002",
        "m-txtime-write-003",
        "m-txtime-write-004",
        "m-txtime-write-005",
        "m-txtime-write-015",
        "m-bitemp-write-001",
        "m-bitemp-write-002",
        "m-bitemp-write-003",
        "m-bitemp-write-006",
        "m-bitemp-write-007",
        "m-bitemp-write-008",
        "m-bitemp-write-009",
        "m-inheritance-090",
        "m-inheritance-091",
        "m-inheritance-094",
        "m-inheritance-095",
        "m-inheritance-096",
        "m-inheritance-097",
        "m-value-object-032",
        "m-value-object-033",
        "m-txtime-write-010",
        "m-bitemp-write-019",
    }
)
_TEMPORAL_COALESCING_SCENARIOS: Final[frozenset[str]] = frozenset(
    {"m-txtime-write-008", "m-bitemp-write-014", "m-bitemp-write-024", "m-bitemp-write-025"}
)
_PIN_CONTRAST_SCENARIOS: Final[frozenset[str]] = frozenset(
    {"m-bitemp-write-015", "m-bitemp-write-016"}
)
_PER_VIEW_PIN_SCENARIOS: Final[frozenset[str]] = frozenset({"m-bitemp-write-023"})
_EXECUTION_LIFECYCLE_SCENARIOS: Final[frozenset[str]] = frozenset(
    {"m-execution-lifecycle-002", "m-execution-lifecycle-003"}
)

WRITE_EXERCISED: Final[frozenset[str]] = (
    _WRITE_SCENARIOS
    | _EXECUTION_LIFECYCLE_SCENARIOS
    | _LAYOUT_TWIN_WRITES
    | _WRITE_SEQUENCES
    | _SNAPSHOT_MUTATE_SCENARIOS
    | _TEMPORAL_WRITE_SEQUENCES
    | _TEMPORAL_COALESCING_SCENARIOS
    | _READLESS_PREDICATE_WRITE_SCENARIOS
    | _READLESS_BARRIER_SCENARIOS
    | _LOCKING_FALLBACK_SCENARIOS
    | _OBJECT_CLAIM_COALESCING_SCENARIOS
    | _PIN_CONTRAST_SCENARIOS
    | _PER_VIEW_PIN_SCENARIOS
)


def wire_binds(binds: list[object]) -> list[object]:
    """Test-authored bind carriers in Wire-like form, outside production."""
    return [wire_value_deep(bind) for bind in binds]


def assert_wire_binds(
    model: Metamodel, golden_sql: str, golden_binds: list[object], observed_binds: list[object]
) -> None:
    """Emitted binds equal the golden's in Wire form, and carry its zero sign at
    every declared float position (`m-case-format` *Canonical literal oracles*)."""
    observed, expected = wire_binds(observed_binds), wire_binds(golden_binds)
    assert observed == expected, (golden_sql, observed, expected)
    assert_zero_signs(observed, expected, statement_bind_positions(model, golden_sql, golden_binds))


def write_golden_statements(case: case_format.Case) -> list[tuple[str, list[object]]]:
    """The ordered golden DML for a write case: a writeSequence's flat `then.statements`,
    or a scenario's per-step `when.scenario[i].statements` flattened in step order.

    A lifecycle **action** step (m-case-format) carries no `statements` key at
    all when it emits no SQL (a snapshot-read `mutate`'s in-memory-only change);
    it contributes an empty group rather than a missing-key error.
    """
    doc = case_document(case)
    if case.shape == "writeSequence":
        groups = [cast("list[dict[str, Any]]", doc["then"]["statements"])]
    else:
        steps = cast("list[dict[str, Any]]", doc["when"]["scenario"])
        groups = [cast("list[dict[str, Any]]", step.get("statements", [])) for step in steps]
    out: list[tuple[str, list[object]]] = []
    for group in groups:
        for entry in group:
            sql: Any = entry["sql"]
            text = cast("dict[str, str]", sql)["postgres"] if isinstance(sql, dict) else sql
            out.append((cast("str", text), _entry_binds(entry)))
    return out


def _entry_binds(entry: dict[str, Any]) -> list[object]:
    """One statement entry's Postgres binds.

    A bind list follows the same flat-or-dialect-keyed polymorphism ``sql`` does
    (`m-case-format`): flat where the hole structure is shared across dialects, and
    keyed per dialect where it diverges — a document mutation's path bind is one
    Postgres text-array path and one MariaDB JSON-path string, so those two cannot
    be one authored list.
    """
    binds: Any = entry.get("binds", [])
    if isinstance(binds, dict):
        binds = cast("dict[str, list[object]]", binds)["postgres"]
    return list(cast("list[object]", binds))
