"""Unit tests for the whole-interpreter instrument access guard.

The guard is what makes the derived `cost` classification trustworthy, so what
matters is not that it fires but that it fires on the routes a reading can
actually take. Its rule is that a module holds a reader only where it imported
one, and that mentioning such a name anywhere reaches it — so the routes worth
planting are the ones that mention a reader without calling it, and the shapes a
name-based rule is tempted to exclude. Each is planted here against a scratch
tree, and the canary at the end holds the real one.

The reader's name is taken from the guard's own declared set rather than written
out, which keeps this module free of the strings it plants and pins the plants to
the set the guard actually enforces.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import check_instrument_access as guard

READER = sorted(guard.WHOLE_INTERPRETER_READERS)[0]
IMPORTED = f"from memory_instruments import {READER}\n"


def _findings(root: Path, source: str) -> list[guard.Finding]:
    (root / "test_probe.py").write_text(source)
    return guard.audit(root)


def _messages(root: Path, source: str) -> str:
    return "\n".join(str(finding) for finding in _findings(root, source))


# --------------------------------------------------------------------------
# Import-time code: the one place no boundary can be written
# --------------------------------------------------------------------------
def test_a_module_level_reading_is_a_finding_no_decorator_could_cover(tmp_path: Path) -> None:
    (finding,) = _findings(tmp_path, f"{IMPORTED}\n{READER}(seam)\n")
    assert finding.line == 3
    assert "imported" in finding.message


def test_a_class_body_reading_is_import_time_too(tmp_path: Path) -> None:
    assert len(_findings(tmp_path, f"{IMPORTED}\n\nclass Probe:\n    held = {READER}(seam)\n")) == 1


def test_the_main_block_is_the_one_import_time_exclusion(tmp_path: Path) -> None:
    source = f'{IMPORTED}\n\nif __name__ == "__main__":\n    {READER}(seam)\n'
    assert _findings(tmp_path, source) == []


def test_a_name_comparison_that_is_not_the_main_block_runs_during_collection(
    tmp_path: Path,
) -> None:
    """``!=`` runs the branch in every process but the child the boundary starts,
    which is the opposite of what the exclusion is for."""
    source = f'{IMPORTED}\n\nif __name__ != "__main__":\n    {READER}(seam)\n'
    assert len(_findings(tmp_path, source)) == 1


def test_a_return_annotation_is_evaluated_when_the_module_is_imported(tmp_path: Path) -> None:
    source = f"{IMPORTED}\n\ndef probe() -> {READER}(seam):\n    return None\n"
    assert len(_findings(tmp_path, source)) == 1


def test_a_parameter_default_is_evaluated_when_the_module_is_imported(tmp_path: Path) -> None:
    source = f"{IMPORTED}\n\ndef probe(held={READER}(seam)):\n    return held\n"
    assert len(_findings(tmp_path, source)) == 1


def test_a_lambda_default_is_evaluated_where_the_lambda_is_created(tmp_path: Path) -> None:
    source = f"{IMPORTED}\n\nprobe = lambda held={READER}(seam): held\n"
    assert len(_findings(tmp_path, source)) == 1


def test_a_function_body_is_not_import_time_and_is_answered_by_reachability(
    tmp_path: Path,
) -> None:
    source = f"{IMPORTED}\n\ndef helper():\n    return {READER}(seam)\n"
    assert _findings(tmp_path, source) == []


# --------------------------------------------------------------------------
# Reachability: a reader is what a test reaches, not what it spells
# --------------------------------------------------------------------------
def test_an_undecorated_test_reaching_a_reader_through_a_helper_is_a_finding(
    tmp_path: Path,
) -> None:
    source = (
        f"{IMPORTED}\n\ndef helper():\n    return {READER}(seam)\n\n\n"
        "def test_probe():\n    helper()\n"
    )
    (finding,) = _findings(tmp_path, source)
    assert "test_probe" in finding.message
    assert guard.BOUNDARY in finding.message


def test_a_reader_handed_to_a_wrapper_is_reached_without_being_called_there(
    tmp_path: Path,
) -> None:
    """``partial(reader)`` names no call site the rule could match, which is the
    shape an enumeration of call spellings never finishes."""
    source = (
        f"from functools import partial\n{IMPORTED}\n\n"
        f"def test_probe():\n    reader = partial({READER})\n    reader(seam)\n"
    )
    assert len(_findings(tmp_path, source)) == 1


def test_a_reader_named_by_a_variable_holding_its_name_is_reached(tmp_path: Path) -> None:
    source = (
        "import memory_instruments\n\n\n"
        f'def test_probe():\n    name = "{READER}"\n'
        "    getattr(memory_instruments, name)(seam)\n"
    )
    assert len(_findings(tmp_path, source)) == 1


def test_a_module_that_imported_no_reader_holds_none_whatever_it_spells(
    tmp_path: Path,
) -> None:
    """Reader names are ordinary English words and the suites are full of locals
    spelled like them. A module that never imported the instruments cannot hold
    one, which is what lets the rule read every mention in a module that did."""
    source = f"def test_probe():\n    {READER} = Observation()\n    record({READER})\n"
    assert _findings(tmp_path, source) == []


def test_a_reader_handed_as_an_attribute_of_the_module_it_lives_in_is_reached(
    tmp_path: Path,
) -> None:
    """``import memory_instruments`` puts every reader one dot away, so the module
    name itself stands for a reader wherever it is mentioned."""
    source = (
        f"import memory_instruments\n\n\ndef test_probe():\n"
        f"    register(memory_instruments.{READER})\n"
    )
    assert len(_findings(tmp_path, source)) == 1


def test_a_reader_packed_into_a_container_is_reached(tmp_path: Path) -> None:
    """The name is in no call position at all: it is an element of a tuple that a
    call happens to receive."""
    source = f"{IMPORTED}\n\ndef test_probe():\n    register(({READER},))\n"
    assert len(_findings(tmp_path, source)) == 1


def test_a_reader_returned_by_a_helper_is_reached_by_whoever_calls_it(
    tmp_path: Path,
) -> None:
    """The helper hands the reader back rather than calling it, and the caller
    calls what it got — so no site names a reader beside a call."""
    source = (
        f"{IMPORTED}\n\ndef helper():\n    return {READER}\n\n\n"
        "def test_probe():\n    helper()(seam)\n"
    )
    assert len(_findings(tmp_path, source)) == 1


def test_a_nested_binding_does_not_excuse_the_reader_beside_it(tmp_path: Path) -> None:
    """A parameter of an inner function shadows the reader inside that function
    and nowhere else, so the outer mention is still a read."""
    source = (
        f"{IMPORTED}\n\ndef test_probe():\n"
        f"    def inner({READER}):\n        return {READER}\n"
        f"    register(partial({READER}))\n"
    )
    assert len(_findings(tmp_path, source)) == 1


def test_a_reader_reached_through_an_imported_helper_module_is_a_finding(
    tmp_path: Path,
) -> None:
    """The audited tree resolves its own imports, so a test reaching a reader
    through a module beside it is planted rather than argued about."""
    (tmp_path / "probe_helpers.py").write_text(
        f"{IMPORTED}\n\ndef reading(seam):\n    return {READER}(seam)\n"
    )
    source = "from probe_helpers import reading\n\n\ndef test_probe():\n    reading(seam)\n"
    assert len(_findings(tmp_path, source)) == 1


def test_a_test_carrying_the_boundary_reaches_its_reader_legally(tmp_path: Path) -> None:
    source = (
        f"from memory_instruments import {READER}, {guard.BOUNDARY}, {guard.SERVER}\n\n\n"
        f"@{guard.BOUNDARY}\ndef test_probe():\n    {READER}(seam)\n\n\n"
        f'if __name__ == "__main__":\n    {guard.SERVER}()\n'
    )
    assert _findings(tmp_path, source) == []


def test_a_module_holding_a_boundary_but_serving_nothing_is_a_finding(tmp_path: Path) -> None:
    source = (
        f"from memory_instruments import {READER}, {guard.BOUNDARY}\n\n\n"
        f"@{guard.BOUNDARY}\ndef test_probe():\n    {READER}(seam)\n"
    )
    assert guard.SERVER in _messages(tmp_path, source)


# --------------------------------------------------------------------------
# Canary: the real tree passes, a planted reading blocks
# --------------------------------------------------------------------------
def test_the_real_test_tree_confines_whole_interpreter_readings() -> None:
    assert guard.main([]) == 0
    assert guard.main(["--check"]) == 0


def test_a_planted_reading_fails_the_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The plant goes into a scratch tree the audited root is pointed at, never
    into the real one: a canary interrupted mid-run would otherwise leave an
    untracked module behind and fail a sibling gate."""
    monkeypatch.setattr(guard, "TESTS_ROOT", tmp_path)
    assert guard.main([]) == 0

    (tmp_path / "test_rogue.py").write_text(
        f"{IMPORTED}\n\ndef test_rogue():\n    {READER}(seam)\n"
    )
    assert guard.main([]) == 1
