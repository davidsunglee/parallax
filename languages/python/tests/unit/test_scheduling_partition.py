"""The scheduling partition, and the layout it is orthogonal to.

Every collected item's class is derived from what it requires by the collection
hook in ``tests/conftest.py`` — its fixture closure for a database, the boundary
its function carries for an interpreter of its own — so neither zero nor two
classes is representable, provided the derivation stays the only source, which is
what the authored-marker check below pins. The remaining assertions grade the real
session rather than a synthetic one: whichever selection is running, every item
it holds is graded.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
import tomllib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
import yaml
from memory_instruments import takes_its_own_interpreter

from _support import cost_durations
from _support.repo import PY_ROOT, REPO_ROOT
from check_database_access import ENTRY_POINT_FIXTURE

SCHEDULING_CLASSES = frozenset({"dbfree", "db", "cost"})
DATABASE_FIXTURES = frozenset({ENTRY_POINT_FIXTURE})
ORTHOGONAL_SELECTORS = frozenset({"compile_sweep", "adapter_smoke"})

CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
COST_JOB = "python-check-cost"
COST_JOB_STEP = "just python-check-cost ${{ matrix.shard }}"
UNGATING_KEYS = frozenset({"if", "continue-on-error"})
WHOLE_CLASS = "1/1"

# The primary semantic surfaces, each one directory under `tests/`.
SURFACES = frozenset(
    {"api", "compatibility", "dialect", "distribution", "provider_contract", "unit"}
)

TESTS_ROOT = PY_ROOT / "tests"


def _test_modules() -> list[Path]:
    return sorted(p for p in TESTS_ROOT.rglob("*.py") if "__pycache__" not in p.parts)


def _authored_marks(source: str) -> set[str]:
    """Every ``pytest.mark.<name>`` spelled in *source*."""
    marks: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Attribute) or not isinstance(node.value, ast.Attribute):
            continue
        namespace = node.value
        if (
            isinstance(namespace.value, ast.Name)
            and namespace.value.id == "pytest"
            and namespace.attr == "mark"
        ):
            marks.add(node.attr)
    return marks


def _classes_of(item: pytest.Item) -> set[str]:
    return {mark.name for mark in item.iter_markers()} & SCHEDULING_CLASSES


# --------------------------------------------------------------------------
# The partition
# --------------------------------------------------------------------------
def test_every_collected_item_carries_exactly_one_scheduling_class(
    request: pytest.FixtureRequest,
) -> None:
    offenders = {
        item.nodeid: sorted(_classes_of(item))
        for item in request.session.items
        if len(_classes_of(item)) != 1
    }
    assert offenders == {}


def test_an_items_class_agrees_with_what_it_requires(
    request: pytest.FixtureRequest,
) -> None:
    for item in request.session.items:
        function = item if isinstance(item, pytest.Function) else None
        closure = function.fixturenames if function else ()
        needs_database = bool(DATABASE_FIXTURES.intersection(closure))
        needs_interpreter = takes_its_own_interpreter(function.obj) if function else False
        assert not (needs_database and needs_interpreter), item.nodeid
        if needs_database:
            expected = {"db"}
        elif needs_interpreter:
            expected = {"cost"}
        else:
            expected = {"dbfree"}
        assert _classes_of(item) == expected, item.nodeid


def test_only_the_derivation_names_a_scheduling_class() -> None:
    # A module authoring a class would restore the second source of truth the
    # derivation exists to remove, and could give one item two classes.
    offenders = {
        path.relative_to(TESTS_ROOT).as_posix(): sorted(
            _authored_marks(path.read_text(encoding="utf-8")) & SCHEDULING_CLASSES
        )
        for path in _test_modules()
        if path.name != "conftest.py"
        and _authored_marks(path.read_text(encoding="utf-8")) & SCHEDULING_CLASSES
    }
    assert offenders == {}


def _cost_job() -> Any:
    """The `python-check-cost` job as the CI workflow declares it."""
    workflow: Any = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    return workflow["jobs"][COST_JOB]


def _deployed_cells() -> list[str]:
    """The shard each cell of that job runs, in the order the matrix names them."""
    return [str(cell) for cell in _cost_job()["strategy"]["matrix"]["shard"]]


def _cost_job_step() -> Any:
    """The step of that job which invokes the class command."""
    (step,) = [step for step in _cost_job()["steps"] if COST_JOB in str(step.get("run", ""))]
    return step


def _index_and_count(cell: str) -> tuple[int, int]:
    index, _, count = cell.partition("/")
    return int(index), int(count)


def _selection(expression: str, shard: str) -> list[str]:
    """The items one session selects under ``-m expression --shard shard``, in
    collection order.

    A shard is a property of a whole session, so it is read off sessions of its
    own rather than off the one grading it.
    """
    collected = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-m",
            expression,
            "--shard",
            shard,
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
        ],
        cwd=PY_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in collected.stdout.splitlines() if "::" in line]


def test_the_cost_jobs_matrix_is_the_shard_vector_alone() -> None:
    # The shard vector is the whole expansion only while it is the matrix's only
    # key: a second dimension would multiply the cells, and `include` or
    # `exclude` would add or drop cells the vector never names. Every assertion
    # below reads that vector, so this is what makes them assertions about the
    # cells GitHub Actions runs.
    assert set(_cost_job()["strategy"]["matrix"]) == {"shard"}


def test_the_cost_jobs_cells_are_every_shard_of_one_count() -> None:
    # The cells are the workflow's, not a copy of it: N of them, each naming N,
    # together naming every index of it once. A deleted, duplicated, or
    # renumbered cell fails here rather than silently dropping class members.
    cells = [_index_and_count(cell) for cell in _deployed_cells()]
    assert {count for _, count in cells} == {len(cells)}
    assert sorted(index for index, _ in cells) == list(range(1, len(cells) + 1))


def test_the_cost_job_runs_the_shard_its_cell_names() -> None:
    # A cell is its own shard only if the step passes it through; a shard spelled
    # into the step would run one part of the class in every cell.
    runs = [str(step["run"]).strip() for step in _cost_job()["steps"] if "run" in step]
    assert [run for run in runs if COST_JOB in run] == [COST_JOB_STEP]


def test_every_cost_cell_runs_unconditionally_and_gates_on_its_verdict() -> None:
    # A cell gates the shard it names only while it always runs and its failure
    # is the job's: an `if` on the job or on the invoking step would skip part of
    # the class, and `continue-on-error` on either would run that part ungated.
    assert UNGATING_KEYS.isdisjoint(_cost_job())
    assert UNGATING_KEYS.isdisjoint(_cost_job_step())


def test_the_deployed_cells_partition_the_cost_class() -> None:
    # The cells' selections together hold every cost item exactly once and none
    # of them is empty; with the expansion and the gating pinned above, that is
    # what lets CI run the class as one cell per shard and still own it once
    # (§9). The whole-class selection is the reference, so a shard mechanism that
    # dropped or doubled an item is caught here.
    whole = _selection("cost", WHOLE_CLASS)
    shards = [_selection("cost", cell) for cell in _deployed_cells()]
    assert all(shards)
    assert sorted(item for shard in shards for item in shard) == sorted(whole)


def test_a_shard_leaves_every_other_class_whole() -> None:
    # The partition above is graded within `-m cost`, where no other class is
    # present; that a sharded session still holds the whole of the rest of the
    # suite is what confines `--shard` to the class CI splits.
    assert _selection("not cost", "2/4") == _selection("not cost", WHOLE_CLASS)


def _malformed_shard_session(shard: str) -> subprocess.CompletedProcess[str]:
    """The outcome of a session given a ``--shard`` value, collecting this module
    alone so what it reports is the option's answer rather than the suite's."""
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(Path(__file__)),
            "--shard",
            shard,
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
        ],
        cwd=PY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(
    "shard",
    [
        "",
        "1",
        "1/",
        "0/4",
        "5/4",
        "²/4",
        pytest.param("9" * 5000 + "/4", id="more-digits-than-int-converts"),
    ],
)
def test_a_malformed_shard_is_the_options_usage_error(shard: str) -> None:
    # `str.isdigit` is wider than Python's integer parser, so a value it accepts
    # can still be one `int` refuses; the option answers every spelling with its
    # own diagnostic rather than an exception raised partway through a session.
    completed = _malformed_shard_session(shard)
    assert completed.returncode == pytest.ExitCode.USAGE_ERROR
    assert "--shard expects I/N" in completed.stderr


# --------------------------------------------------------------------------
# The durations the shards are balanced over
# --------------------------------------------------------------------------
def _load_of_each(halves: Sequence[Sequence[str]], known: Mapping[str, float]) -> list[float]:
    unknown = sum(known.values()) / len(known)
    return [sum(known.get(item, unknown) for item in half) for half in halves]


def test_the_shards_are_balanced_by_the_stored_durations() -> None:
    # Two shards make the claim sharpest. The class's items span two orders of
    # magnitude, so halves drawn by position are hundreds of seconds apart while
    # halves drawn by what each item last cost are a fraction of a second apart:
    # a mechanism that stopped reading the file would still partition the class
    # and would fail here.
    known = cost_durations.known()
    halves = [_selection("cost", f"{index}/2") for index in (1, 2)]
    balanced = _load_of_each(halves, known)
    positional = _load_of_each([sorted(known)[::2], sorted(known)[1::2]], known)
    assert abs(balanced[0] - balanced[1]) <= max(known.values())
    assert abs(balanced[0] - balanced[1]) <= abs(positional[0] - positional[1])


def test_the_stored_durations_are_the_contract_the_shards_read_them_under() -> None:
    # The tracked file is an input to every sharded session, so what it holds is
    # graded here rather than only where a malformed entry would silently skew a
    # shard.
    assert cost_durations.known()


def test_a_missing_durations_file_is_a_usage_error(tmp_path: Path) -> None:
    # Absent, the shards would fall back to equal weights, still partition the
    # class, and balance it by nothing — green, and no longer doing the one thing
    # the file exists for.
    with pytest.raises(pytest.UsageError, match=r"never-stored\.json"):
        cost_durations.known(tmp_path / "never-stored.json")


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param("[1.0, 2.0]", id="not-an-object"),
        pytest.param('{"a::b": ', id="truncated"),
        pytest.param('{"a::b": "1.0"}', id="string"),
        pytest.param('{"a::b": true}', id="boolean"),
        pytest.param('{"a::b": -1.0}', id="negative"),
        pytest.param('{"a::b": NaN}', id="nan"),
        pytest.param('{"a::b": Infinity}', id="infinite"),
    ],
)
def test_a_duration_that_is_not_a_finite_non_negative_number_is_a_usage_error(
    payload: str, tmp_path: Path
) -> None:
    # `float` accepts every one of these, and a `NaN` among them would poison the
    # mean an unknown item weighs and collapse the choice of lightest shard,
    # leaving the balance decided by nothing while the partition stayed intact.
    path = tmp_path / "cost_durations.json"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(pytest.UsageError, match=re.escape(str(path))):
        cost_durations.known(path)


def test_a_whole_class_store_replaces_and_a_shard_merges(tmp_path: Path) -> None:
    # A whole-class run measured every item there is, so an entry it did not
    # observe names an item that no longer exists; a shard measured its own part
    # of the class, so the entries it did not observe are the only record of the
    # items the other shards run.
    path = tmp_path / "cost_durations.json"
    path.write_text('{"a::renamed": 5.0, "a::kept": 2.0}\n', encoding="utf-8")
    cost_durations.store({"a::kept": 3.04}, whole_class=False, path=path)
    assert cost_durations.known(path) == {"a::renamed": 5.0, "a::kept": 3.0}
    cost_durations.store({"a::kept": 3.04}, whole_class=True, path=path)
    assert cost_durations.known(path) == {"a::kept": 3.0}


def test_the_marker_catalog_is_the_partition_plus_the_orthogonal_selectors() -> None:
    config = tomllib.loads((PY_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    catalog = config["tool"]["pytest"]["ini_options"]["markers"]
    names = {entry.split(":", 1)[0] for entry in catalog}
    assert names == SCHEDULING_CLASSES | ORTHOGONAL_SELECTORS


# --------------------------------------------------------------------------
# The semantic surfaces the partition cuts across
# --------------------------------------------------------------------------
def test_the_test_root_holds_only_surfaces_support_and_runner_required_files() -> None:
    entries = {p.name for p in TESTS_ROOT.iterdir() if p.name != "__pycache__"}
    assert entries == SURFACES | {"_support", "conftest.py"}


def test_every_collected_item_sits_under_a_primary_surface(
    request: pytest.FixtureRequest,
) -> None:
    surfaces = {
        Path(str(item.path)).relative_to(TESTS_ROOT).parts[0] for item in request.session.items
    }
    assert surfaces <= SURFACES


def test_each_focused_surface_recipe_selects_its_own_directory() -> None:
    justfile = (REPO_ROOT / "justfile").read_text(encoding="utf-8")
    for surface in sorted(SURFACES):
        recipe = f"python-test-{surface.replace('_', '-')}"
        match = re.search(rf"^{re.escape(recipe)}:\n((?:    .*\n)+)", justfile, re.MULTILINE)
        assert match is not None, f"no recipe `{recipe}`"
        (invocation,) = match.group(1).strip().splitlines()
        assert invocation.endswith(f"uv run pytest tests/{surface}")
