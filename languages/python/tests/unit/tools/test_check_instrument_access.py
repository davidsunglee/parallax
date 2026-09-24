"""Unit tests for the whole-interpreter instrument access guard.

The reader's name is taken from the guard's own declared set rather than written
out, which keeps this module free of the calls it plants and pins the plants to
the set the guard actually enforces.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import check_instrument_access as guard

READER = sorted(guard.WHOLE_INTERPRETER_READERS)[0]


def _findings(root: Path, source: str) -> list[guard.Finding]:
    (root / "test_probe.py").write_text(source)
    return guard.audit(root)


def test_a_test_carrying_the_boundary_calls_its_reader_legally(tmp_path: Path) -> None:
    source = (
        f"from memory_instruments import {READER}, {guard.BOUNDARY}, {guard.SERVER}\n\n\n"
        f"@{guard.BOUNDARY}\ndef test_probe():\n    {READER}(seam)\n\n\n"
        f'if __name__ == "__main__":\n    {guard.SERVER}()\n'
    )
    assert _findings(tmp_path, source) == []


@pytest.mark.parametrize(
    "entry",
    ["", f'\n\nif __name__ == "main":\n    {guard.SERVER}()\n'],
    ids=["no-server", "misspelled-main-guard"],
)
def test_a_module_holding_a_boundary_but_serving_nothing_is_a_finding(
    entry: str, tmp_path: Path
) -> None:
    source = (
        f"from memory_instruments import {READER}, {guard.BOUNDARY}, {guard.SERVER}\n\n\n"
        f"@{guard.BOUNDARY}\ndef test_probe():\n    {READER}(seam)\n{entry}"
    )
    (finding,) = _findings(tmp_path, source)
    assert guard.SERVER in finding.message


def test_the_real_test_tree_confines_whole_interpreter_readings() -> None:
    assert guard.main([]) == 0
    assert guard.main(["--check"]) == 0


@pytest.mark.parametrize(
    "planted",
    [
        f"from memory_instruments import {READER}\n\n\ndef test_rogue():\n    {READER}(seam)\n",
        (
            "from tests.unit import memory_instruments as m\n\n\n"
            f"def test_rogue():\n    m.{READER}(seam)\n"
        ),
    ],
    ids=["imported-name", "module-attribute"],
)
def test_a_planted_reading_fails_the_gate(
    planted: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The plant goes into a scratch tree the audited root is pointed at, never
    into the real one: a canary interrupted mid-run would otherwise leave an
    untracked module behind and fail a sibling gate."""
    monkeypatch.setattr(guard, "TESTS_ROOT", tmp_path)
    assert guard.main([]) == 0

    (tmp_path / "test_rogue.py").write_text(planted)
    assert guard.main([]) == 1
