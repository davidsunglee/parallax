"""The scheduling partition, and the layout it is orthogonal to.

Every collected item's class is derived from what it requires by the collection
hook in ``tests/conftest.py`` — its fixture closure for a database, for a
provider-hosted environment, or for the committed cost evidence, the boundary its
function carries for an interpreter of its own — so neither zero nor two classes
is representable, provided the
derivation stays the only source, which is what the authored-marker check below
pins. The remaining assertions grade the real session rather than a synthetic
one: whichever selection is running, every item it holds is graded.
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
import tomllib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
import yaml

from check_resource_access import RESOURCE_CLASSES
from tests._support import committed_evidence, cost_durations
from tests._support.repo import PY_ROOT, REPO_ROOT
from tests.unit._session_selection_support import WHOLE_CLASS, selections
from tests.unit.memory_instruments import takes_its_own_interpreter

SCHEDULING_CLASSES = frozenset({"dbfree", "db", "cloud", "cost"})
RESOURCE_FIXTURES = {entry.fixture: name for name, entry in RESOURCE_CLASSES.items()}
EVIDENCE_FIXTURES = frozenset({committed_evidence.FIXTURE})
ORTHOGONAL_SELECTORS = frozenset({"compile_sweep", "adapter_smoke"})

CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
COST_JOB = "python-test-cost"

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
        resources = {RESOURCE_FIXTURES[name] for name in closure if name in RESOURCE_FIXTURES}
        needs_cost = bool(EVIDENCE_FIXTURES.intersection(closure)) or (
            takes_its_own_interpreter(function.obj) if function else False
        )
        assert len(resources) <= 1, item.nodeid
        assert not (resources and needs_cost), item.nodeid
        if resources:
            expected = resources
        elif needs_cost:
            expected = {"cost"}
        else:
            expected = {"dbfree"}
        assert _classes_of(item) == expected, item.nodeid


def test_the_committed_evidence_is_every_retained_capture_and_the_derived_gates() -> None:
    evidence = [
        PY_ROOT / committed_evidence.GATES,
        PY_ROOT / "evidence/cost/current/portfolio.json",
        PY_ROOT / "evidence/cost/structural-metadata-after/portfolio.json",
        PY_ROOT / "evidence/cost/structural-metadata-before/portfolio.json",
    ]
    beside = [
        PY_ROOT / "spec/budget-contract.yaml",
        PY_ROOT / "evidence/cost/README.md",
        PY_ROOT / "evidence/cost/current/summary.md",
        PY_ROOT / "tests/_support/cost_durations.json",
        REPO_ROOT / "core/schemas/conformance-adapter.schema.json",
    ]
    assert [committed_evidence.is_committed(str(path)) for path in evidence] == [True] * 4
    assert [committed_evidence.is_committed(str(path)) for path in beside] == [False] * 5


def test_an_item_that_did_not_request_the_committed_evidence_cannot_open_it() -> None:
    # The refusal is not an `Exception`, so an opener suppressing its own errors
    # cannot turn it into a pass; every spelling of the open is the same event.
    gates = PY_ROOT / committed_evidence.GATES
    with pytest.raises(committed_evidence.EvidenceRefused, match="committed_cost_evidence"):
        gates.read_bytes()
    with pytest.raises(committed_evidence.EvidenceRefused):
        open(os.path.relpath(gates), "rb")  # noqa: SIM115 - the refusal precedes any handle
    with pytest.raises(committed_evidence.EvidenceRefused):
        os.open(gates, os.O_RDONLY)
    assert (PY_ROOT / "spec/budget-contract.yaml").read_bytes()


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
    """The `python-test-cost` job as the CI workflow declares it."""
    workflow: Any = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    return workflow["jobs"][COST_JOB]


def _deployed_cells() -> list[str]:
    """The shard each cell of that job runs, in the order the matrix names them."""
    return [str(cell) for cell in _cost_job()["strategy"]["matrix"]["shard"]]


def test_the_deployed_cells_partition_the_cost_class_and_leave_the_rest_whole() -> None:
    # The cells are every index of one count, parsed as the hook parses `--shard`.
    # Their parts, computed in process from what the hook computes them from — the
    # whole class in collection order, the stored durations, and the cell count —
    # hold every cost item exactly once and none is empty (§9). One real sharded
    # session pins the prediction: its cost items are its cell's part, and its
    # other items are exactly an unsharded session's, which is what confines
    # `--shard` to the class CI splits.
    cells = _deployed_cells()
    parsed = [cost_durations.index_and_count(cell) for cell in cells]
    assert sorted(parsed) == [(index, len(cells)) for index in range(1, len(cells) + 1)]

    # Halfway along the vector: neither the first nor the last cell, so a hook
    # that ran one end of the vector whatever cell it was given fails here.
    spot_checked = cells[len(cells) // 2]
    cost_session, sharded_session, unsharded_session = selections(
        [("cost", WHOLE_CLASS), (None, spot_checked), (None, WHOLE_CLASS)]
    )
    cost_class = cost_session.selected
    whole = cost_session.collected
    under_one_cell = sharded_session.selected
    shard_of = cost_durations.shard_of_each(
        cost_durations.weights(cost_class, cost_durations.known()), len(cells)
    )
    predicted = {
        cell: [item for item, shard in zip(cost_class, shard_of, strict=True) if shard == index]
        for cell, (index, _) in zip(cells, parsed, strict=True)
    }
    assert all(predicted.values())
    assert sorted(item for part in predicted.values() for item in part) == sorted(cost_class)

    in_class = set(cost_class)
    assert [item for item in under_one_cell if item in in_class] == predicted[spot_checked]
    assert [item for item in under_one_cell if item not in in_class] == [
        item for item in unsharded_session.selected if item not in in_class
    ]
    assert [item for item in whole if item in in_class] == list(cost_class)


@pytest.mark.parametrize("shard", ["", "1", "1/", "0/4", "5/4", "a/4"])
def test_a_malformed_shard_is_the_options_usage_error(shard: str) -> None:
    with pytest.raises(pytest.UsageError, match="--shard expects I/N"):
        cost_durations.index_and_count(shard)


def test_a_session_given_a_malformed_shard_stops_with_the_usage_error() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(Path(__file__)),
            "--shard",
            "0/4",
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
    # halves drawn by what each item last cost are a fraction of a second apart.
    # Graded over the stored items through the assignment the hook calls; that
    # the hook reads the file at all is what the partition test's real session
    # pins, since a hook weighing everything alike would predict other cells.
    known = cost_durations.known()
    stored = sorted(known)
    shard_of = cost_durations.shard_of_each(cost_durations.weights(stored, known), 2)
    halves = [
        [item for item, shard in zip(stored, shard_of, strict=True) if shard == index]
        for index in (1, 2)
    ]
    balanced = _load_of_each(halves, known)
    positional = _load_of_each([sorted(known)[::2], sorted(known)[1::2]], known)
    assert abs(balanced[0] - balanced[1]) <= max(known.values())
    assert abs(balanced[0] - balanced[1]) <= abs(positional[0] - positional[1])


def test_an_item_weighs_its_stored_duration_and_an_unknown_one_the_mean() -> None:
    # The assignment sees these numbers and nothing else, so this is where the
    # balance is claimed: weights that regressed to one value for every item
    # would still partition the class, and still leave every cell's predicted
    # part matching what the hook produced from the same regression.
    known = {"a::light": 1.0, "a::heavy": 4.0, "a::middling": 4.0}
    assert cost_durations.weights(["a::heavy", "a::light", "a::unstored"], known) == [4.0, 1.0, 3.0]


def test_the_stored_durations_are_the_contract_the_shards_read_them_under() -> None:
    # The tracked file is an input to every sharded session, so what it holds is
    # graded here rather than only where a malformed entry would silently skew a
    # shard.
    assert cost_durations.known()


def test_durations_that_do_not_arrive_at_all_are_a_usage_error(tmp_path: Path) -> None:
    # Without them the shards would weigh every item the same, still partition
    # the class, and balance it by nothing — green, and no longer doing the one
    # thing the file exists for. A session cannot tell the ways of not arriving
    # apart, so a file that is absent, one whose bytes are not text, and a path
    # that is not a readable file are one answer.
    undecodable = tmp_path / "undecodable.json"
    undecodable.write_bytes(b'{"a::b": 1.0}\xff')
    for path in (tmp_path / "never-stored.json", undecodable, tmp_path):
        with pytest.raises(pytest.UsageError, match=re.escape(str(path))):
            cost_durations.known(path)


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param("[1.0, 2.0]", id="not-an-object"),
        pytest.param("{}", id="no-durations"),
        pytest.param('{"a::b": ', id="truncated"),
        pytest.param('{"a::b": "1.0"}', id="string"),
        pytest.param('{"a::b": true}', id="boolean"),
        pytest.param('{"a::b": -1.0}', id="negative"),
        pytest.param('{"a::b": NaN}', id="nan"),
        pytest.param('{"a::b": Infinity}', id="infinite"),
    ],
)
def test_a_payload_that_is_not_a_mapping_of_durations_is_a_usage_error(
    payload: str, tmp_path: Path
) -> None:
    # A payload can arrive and still be no durations: a list, an object naming
    # none, a document that stops. A `NaN` would poison the mean an unknown item
    # weighs and collapse the choice of lightest shard, leaving the balance
    # decided by nothing while the partition stayed intact.
    path = tmp_path / "cost_durations.json"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(pytest.UsageError, match=re.escape(str(path))):
        cost_durations.known(path)


def _stored_over_two_entries(path: Path, *, replace: bool) -> dict[str, float]:
    """A file holding a renamed and a kept item after a store of one observation
    of the kept one over it."""
    path.write_text('{"a::renamed": 5.0, "a::kept": 2.0}\n', encoding="utf-8")
    cost_durations.store({"a::kept": 3.04}, replace=replace, path=path)
    return cost_durations.known(path)


def test_a_replacing_store_drops_every_item_it_did_not_observe(tmp_path: Path) -> None:
    stored = _stored_over_two_entries(tmp_path / "cost_durations.json", replace=True)
    assert stored == {"a::kept": 3.0}


def test_a_merging_store_keeps_every_item_it_did_not_observe(tmp_path: Path) -> None:
    stored = _stored_over_two_entries(tmp_path / "cost_durations.json", replace=False)
    assert stored == {"a::renamed": 5.0, "a::kept": 3.0}


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
    assert entries == SURFACES | {"_support", "__init__.py", "conftest.py"}


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


def _module_group(module: Path) -> str | None:
    """The ``xdist_group`` a test module assigns to every item through ``pytestmark``."""
    for node in ast.parse(module.read_text(encoding="utf-8")).body:
        if not (
            isinstance(node, ast.Assign)
            and [target.id for target in node.targets if isinstance(target, ast.Name)]
            == ["pytestmark"]
            and isinstance(node.value, ast.Call)
            and ast.unparse(node.value.func) == "pytest.mark.xdist_group"
        ):
            continue
        (name,) = node.value.args
        return (
            name.value if isinstance(name, ast.Constant) and isinstance(name.value, str) else None
        )
    return None


def test_the_replication_proofs_share_one_worker_and_so_one_standby_pair() -> None:
    # Each worker opens its own pair on first use, so the whole database lane
    # adds one pair only while every proof needing it is grouped onto one
    # worker and the class owner distributes by group.
    proofs = sorted((TESTS_ROOT / "provider_contract" / "replication").glob("test_*.py"))
    assert proofs
    assert {proof.name: _module_group(proof) for proof in proofs} == {
        proof.name: "replication" for proof in proofs
    }
    justfile = (REPO_ROOT / "justfile").read_text(encoding="utf-8")
    match = re.search(r"^python-test-db:\n((?:    .*\n)+)", justfile, re.MULTILINE)
    assert match is not None
    (invocation,) = match.group(1).strip().splitlines()
    assert invocation.endswith("uv run pytest -m db -n 4 --dist loadgroup")


# --------------------------------------------------------------------------
# The provider-hosted class: collected everywhere, run only where selected
# --------------------------------------------------------------------------
CLOUD_SUITE = "tests/provider_contract/aws"


def _collect(*arguments: str, providers: str | None = None) -> subprocess.CompletedProcess[str]:
    environment = {
        key: value for key, value in os.environ.items() if key != "PARALLAX_CLOUD_PROVIDERS"
    }
    if providers is not None:
        environment["PARALLAX_CLOUD_PROVIDERS"] = providers
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            *arguments,
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
        ],
        cwd=PY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def test_a_cloud_run_naming_no_provider_selects_nothing_and_fails() -> None:
    # Unset is the state of every local run, so no selection there can reach
    # the provider; a CI cell that forgot to name its provider collects nothing,
    # and pytest's own no-tests status fails it rather than passing it.
    completed = _collect("-m", "cloud", CLOUD_SUITE)
    assert completed.returncode == pytest.ExitCode.NO_TESTS_COLLECTED
    assert "deselected" in completed.stdout


def test_a_cloud_run_naming_its_provider_selects_the_providers_suite() -> None:
    completed = _collect("-m", "cloud", CLOUD_SUITE, providers="aws")
    assert completed.returncode == pytest.ExitCode.OK
    assert "test_topology.py::" in completed.stdout
    assert "deselected" not in completed.stdout


def test_the_cloud_suite_is_never_part_of_another_class() -> None:
    for scheduling_class in ("dbfree", "db", "cost"):
        completed = _collect("-m", scheduling_class, CLOUD_SUITE, providers="aws")
        assert completed.returncode == pytest.ExitCode.NO_TESTS_COLLECTED, scheduling_class


def test_an_unknown_provider_is_a_usage_error() -> None:
    completed = _collect("-m", "cloud", CLOUD_SUITE, providers="aws,gcp")
    assert completed.returncode == pytest.ExitCode.USAGE_ERROR
    assert "PARALLAX_CLOUD_PROVIDERS names gcp" in completed.stderr


@pytest.mark.parametrize(
    ("fixtures", "refusal"),
    [
        ("profile_run, aws_run", "a provider-hosted environment"),
        ("aws_run, committed_cost_evidence", "cloud resources and a cost resource"),
    ],
)
def test_a_closure_reaching_two_classes_resources_fails_collection(
    tmp_path: Path, fixtures: str, refusal: str
) -> None:
    # The plant lives outside the test root, with the runner's hooks loaded as a
    # plugin, so an interrupted run leaves no stray module in the tree.
    planted = tmp_path / "test_planted.py"
    planted.write_text(f"def test_planted({fixtures}):\n    pass\n", encoding="utf-8")
    completed = _collect(str(planted), "-p", "tests.conftest", "--rootdir", ".")
    assert completed.returncode == pytest.ExitCode.USAGE_ERROR
    assert refusal in completed.stdout + completed.stderr
