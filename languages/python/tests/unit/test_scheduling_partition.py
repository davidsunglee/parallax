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
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from check_resource_access import RESOURCE_CLASSES
from tests._support import committed_evidence, shards
from tests._support.repo import PY_ROOT, REPO_ROOT
from tests.unit._session_selection_support import WHOLE_CLASS, selection
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


def _deployed_cells(job: str) -> list[str]:
    workflow: Any = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    return [str(cell) for cell in workflow["jobs"][job]["strategy"]["matrix"]["shard"]]


def test_the_deployed_cells_partition_each_class_and_leave_the_rest_whole() -> None:
    variants = (
        ("cost", _deployed_cells(COST_JOB), "--shard", shards.COST_DURATIONS),
        ("db", _deployed_cells("python-check-db"), "--db-shard", shards.DB_DURATIONS),
    )
    with ThreadPoolExecutor(max_workers=3) as sessions:
        unsharded = sessions.submit(selection, None, WHOLE_CLASS)
        narrowed = {
            scheduling_class: sessions.submit(
                selection, None, cells[len(cells) // 2], option=option
            )
            for scheduling_class, cells, option, _path in variants
        }
        whole = unsharded.result()
        selected = {name: future.result().selected for name, future in narrowed.items()}
    for scheduling_class, cells, option, path in variants:
        parsed = [shards.index_and_count(cell, option=option) for cell in cells]
        assert sorted(parsed) == [(index, len(cells)) for index in range(1, len(cells) + 1)]
        members = [item for item in whole.selected if whole.classes[item] == scheduling_class]
        known = shards.known(path)
        if scheduling_class == "db":
            assignment = shards.shard_of_groups(members, whole.groups, known, len(cells))
        else:
            assignment = shards.shard_of_each(shards.weights(members, known), len(cells))
        predicted = {
            cell: [item for item, shard in zip(members, assignment, strict=True) if shard == index]
            for cell, (index, _) in zip(cells, parsed, strict=True)
        }
        assert all(predicted.values())
        assert sorted(item for part in predicted.values() for item in part) == sorted(members)
        spot_checked = cells[len(cells) // 2]
        actual = selected[scheduling_class]
        assert [item for item in actual if whole.classes[item] == scheduling_class] == predicted[
            spot_checked
        ]
        assert [item for item in actual if whole.classes[item] != scheduling_class] == [
            item for item in whole.selected if whole.classes[item] != scheduling_class
        ]
        if scheduling_class == "db":
            placement = dict(zip(members, assignment, strict=True))
            for group in set(whole.groups.values()):
                assert (
                    len({placement[item] for item in members if whole.groups.get(item) == group})
                    <= 1
                )


def test_database_groups_are_indivisible_and_use_unsuffixed_weights() -> None:
    nodeids = ["a::first", "b::second", "c::heavy", "d::small"]
    groups = {"a::first": "shared", "b::second": "shared"}
    known = dict(zip(nodeids, (4.0, 4.0, 7.0, 1.0), strict=True))
    assert shards.shard_of_groups(nodeids, groups, known, 2) == [1, 1, 2, 2]
    suffixed = [f"{nodeid}@shared" if nodeid in groups else nodeid for nodeid in nodeids]
    assert shards.shard_of_groups(
        suffixed, {f"{nodeid}@shared": group for nodeid, group in groups.items()}, known, 2
    ) == [1, 1, 2, 2]
    assert shards.shard_of_groups([*nodeids, "e::unknown"], groups, known, 2) == [1, 1, 2, 1, 2]


def test_database_group_names_follow_xdist_composite_marker_rules() -> None:
    class Item:
        def iter_markers(self, name: str) -> list[pytest.Mark]:
            assert name == "xdist_group"
            return [
                pytest.mark.xdist_group("z").mark,
                pytest.mark.xdist_group(name="a").mark,
                pytest.mark.xdist_group("z").mark,
                pytest.mark.xdist_group().mark,
            ]

    assert shards.group_of(cast("pytest.Item", Item())) == "a_default_z"


@pytest.mark.parametrize("option", ["--shard", "--db-shard"])
@pytest.mark.parametrize("shard", ["", "1", "1/", "0/4", "5/4", "a/4"])
def test_a_malformed_shard_is_the_options_usage_error(shard: str, option: str) -> None:
    with pytest.raises(pytest.UsageError, match=f"{option} expects I/N"):
        shards.index_and_count(shard, option=option)


@pytest.mark.parametrize("option", ["--shard", "--db-shard"])
def test_a_session_given_a_malformed_shard_stops_with_the_usage_error(option: str) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(Path(__file__)),
            option,
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
    assert f"{option} expects I/N" in completed.stderr


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
    known = shards.known()
    stored = sorted(known)
    shard_of = shards.shard_of_each(shards.weights(stored, known), 2)
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
    assert shards.weights(["a::heavy", "a::light", "a::unstored"], known) == [4.0, 1.0, 3.0]


def test_the_stored_durations_are_the_contract_the_shards_read_them_under() -> None:
    # The tracked file is an input to every sharded session, so what it holds is
    # graded here rather than only where a malformed entry would silently skew a
    # shard.
    assert shards.known()
    assert shards.known(shards.DB_DURATIONS)


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
            shards.known(path)


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
        shards.known(path)


def _stored_over_two_entries(path: Path, *, replace: bool) -> dict[str, float]:
    """A file holding a renamed and a kept item after a store of one observation
    of the kept one over it."""
    path.write_text('{"a::renamed": 5.0, "a::kept": 2.0}\n', encoding="utf-8")
    shards.store({"a::kept": 3.04}, replace=replace, path=path)
    return shards.known(path)


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
    match = re.search(r'^python-test-db shard="1/1":\n((?:    .*\n)+)', justfile, re.MULTILINE)
    assert match is not None
    (invocation,) = match.group(1).strip().splitlines()
    assert invocation.endswith("uv run pytest -m db -n 4 --dist loadgroup --db-shard {{shard}}")


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
