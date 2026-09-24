"""The memory gates the cost class owns."""

from __future__ import annotations

from typing import Any

import yaml

import snapshot_delivery_overhead as snapshot_report
import write_lowering_overhead as write_report
from interpreter_matrix import supported_minors
from parallax.conformance.budget import BYTE_UNITS, GATED_WINDOWS, BudgetContract, MemoryGates
from tests.unit import _delivery_control_support as control_support
from tests.unit import _memory_gate_support as gate_support
from tests.unit._session_selection_support import WHOLE_CLASS, selections


def test_every_memory_gate_is_owned_by_one_collected_cost_item() -> None:
    # A ceiling in `spec/memory-gates.yaml` blocks only through an item CI runs
    # in the cost class. The ownership table names each gate's item by module
    # and function, so ownership is graded here against the class as a real
    # session collects it — never inferred from a report member's registration
    # — and the table is a partition: every gate claimed, none twice.
    (cost_class,) = selections([("cost", WHOLE_CLASS)])
    collected = set(cost_class)
    for owner in gate_support.OWNERS:
        assert owner.nodeid in collected, owner.nodeid
        assert owner.gates(), owner.nodeid
    assert gate_support.unowned_gates() == ()


def _gated_by_the_instruments() -> dict[tuple[str, str, str], str]:
    """Every address the instruments read in a gated window, with the unit it is
    read in: the static matrices every capture is validated against, so the set
    is known without measuring anything."""
    contract = BudgetContract.load()
    predicted = {
        (snapshot_report.SUBJECT, workload, cell): snapshot_report.unit(cell)
        for _runtime, workload, cell in snapshot_report.addresses(contract, supported_minors())
        if snapshot_report.is_memory_cell(cell)
        and snapshot_report.window_of(cell, workload) in GATED_WINDOWS
    }
    predicted.update(
        ((write_report.SUBJECT, case, metric), write_report.unit_of(window, metric))
        for case, window in write_report.WINDOWS.items()
        if window in GATED_WINDOWS
        for metric in write_report.METRICS
        if write_report.unit_of(window, metric) in BYTE_UNITS
    )
    return predicted


def test_the_owners_partition_every_address_the_instruments_gate() -> None:
    # The gates are a capture's output, so an address the instruments gained
    # since the basis was taken carries no gate yet and the partition above
    # cannot see it: it would fail first at the next rebaseline, where no
    # implementation may land. Grading the table against the addresses the
    # instruments read instead of the ones the file names moves that failure to
    # the change that widens the matrix. Measuring nothing is what keeps this
    # database-free and inside the merge gate.
    predicted = _gated_by_the_instruments()
    authored = MemoryGates.load()
    assert set(authored.addresses) <= set(predicted)
    document: Any = yaml.safe_load(authored.path.read_text(encoding="utf-8"))
    for (subject, workload, cell), unit in sorted(predicted.items()):
        document["gates"].setdefault(subject, {}).setdefault(workload, {}).setdefault(
            cell, {"unit": unit, "maxBytes": 1}
        )
    over_predicted = MemoryGates.from_bytes(authored.path, yaml.safe_dump(document).encode("utf-8"))
    assert set(over_predicted.addresses) == set(predicted)
    assert gate_support.unowned_gates(over_predicted) == ()


def test_every_claimed_control_address_is_a_cold_plan_reading() -> None:
    # A claim is only as good as the reading behind it, and the sole control
    # reading any owner's child takes is a cold read-plan compilation. The
    # cold-plan owner claims the guarded include workloads by workload, so
    # gating a warm-plan or delivery window would hand it addresses it cannot
    # read while the partition above still reports every gate claimed.
    arms = BudgetContract.load().memory_scaling_arms
    claimed = [
        (workload, cell)
        for subject, workload, cell in _gated_by_the_instruments()
        if workload.startswith(control_support.CONTROL_PREFIX)
        and any(
            owner.subject == subject and owner.selects(workload) for owner in gate_support.OWNERS
        )
    ]
    assert claimed
    for workload, cell in claimed:
        control = control_support.control_address(workload, cell, arms)
        assert isinstance(control, control_support.GuardedPlanControl), (workload, cell)
        assert control.phase == "cold", (workload, cell)
