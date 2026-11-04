from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests._support import shards
from tests._support.repo import PY_ROOT


@pytest.mark.parametrize(
    ("count", "workers", "max_chunk"),
    [(0, 4, None), (5, 4, None), (26, 4, None), (48, 3, None), (48, 3, 2), (48, 3, 1)],
)
def test_cost_dispatch_preserves_each_item_and_starts_heavy_work_on_separate_workers(
    count: int, workers: int, max_chunk: int | None
) -> None:
    weights = [float(position) for position in range(count)]
    ordered = shards.order_for_workers(weights, workers, max_chunk)
    assert sorted(ordered) == list(range(count))
    if count < 2 * workers:
        assert ordered == list(reversed(range(count)))
    else:
        chunk = max(2, min(count // workers // 4, count if max_chunk is None else max_chunk))
        batches = [ordered[i * chunk : (i + 1) * chunk] for i in range(workers)]
        assert [batch[0] for batch in batches] == list(range(count - 1, count - workers - 1, -1))
        assert sorted(item for batch in batches for item in batch[1:]) == list(
            range(workers * (chunk - 1))
        )
        remainder = ordered[workers * chunk :]
        assert remainder == sorted(remainder, reverse=True)


@pytest.mark.parametrize("workers", [0, 1])
def test_serial_cost_order_is_unchanged(workers: int) -> None:
    assert shards.order_for_workers([2.0, 8.0, 1.0, 9.0], workers) == [0, 1, 2, 3]


def test_equal_cost_weights_have_a_repeatable_order() -> None:
    assert shards.order_for_workers([1.0] * 8, 2) == [0, 7, 1, 6, 2, 3, 4, 5]


@pytest.mark.parametrize(
    ("workers", "distribution", "expression", "max_chunk"),
    [
        (2, "load", "cost", None),
        ("auto", "load", "cost", None),
        (3, "load", "cost", 2),
        (2, "loadgroup", "cost", None),
        (0, "no", "cost", None),
        (2, "load", "", None),
    ],
)
def test_real_cost_sessions_dispatch_heavy_items_without_reordering_other_sessions(
    tmp_path: Path, workers: int | str, distribution: str, expression: str, max_chunk: int | None
) -> None:
    (tmp_path / "pytest.ini").write_text(
        "[pytest]\nmarkers =\n    cost: synthetic cost resource\n    dbfree: no resource\n",
        encoding="utf-8",
    )
    (tmp_path / "conftest.py").write_text(
        "from pathlib import Path\n"
        "from tests.conftest import (\n"
        "    pytest_addoption, pytest_collection_modifyitems, pytest_configure_node)\n"
        "from tests._support import shards\n"
        "shards.known = lambda *args: {\n"
        "    f'test_sample.py::test_case_{i:02}': float(i) for i in range(48)}\n"
        "def pytest_xdist_auto_num_workers(config):\n"
        "    return 2\n"
        "def pytest_collection_finish(session):\n"
        "    worker = getattr(session.config, 'workerinput', {}).get('workerid', 'controller')\n"
        "    Path(__file__).with_name(worker + '-collection').write_text('\\n'.join(\n"
        "        item.name for item in session.items))\n",
        encoding="utf-8",
    )
    functions = [
        "from pathlib import Path\n",
        "def record(name, worker):\n"
        "    with Path(__file__).with_name(worker + '-executed').open('a') as output:\n"
        "        output.write(name + '\\n')\n",
        "def test_ordinary(worker_id):\n    record('test_ordinary', worker_id)\n",
    ]
    for position in range(48):
        name = f"test_case_{position:02}"
        functions.append(
            f"def {name}(worker_id):\n    record('{name}', worker_id)\n"
            f"{name}.__parallax_own_interpreter__ = True\n"
        )
    (tmp_path / "test_sample.py").write_text("".join(functions), encoding="utf-8")
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-c",
        str(tmp_path / "pytest.ini"),
        "--confcutdir",
        str(tmp_path),
        "-n",
        str(workers),
        "--dist",
        distribution,
        str(tmp_path / "test_sample.py"),
    ]
    if expression:
        command.extend(["-m", expression])
    if max_chunk is not None:
        command.extend(["--maxschedchunk", str(max_chunk)])
    completed = subprocess.run(
        command,
        cwd=PY_ROOT,
        env={**os.environ, "PYTEST_ADDOPTS": ""},
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    collections = [path.read_text().splitlines() for path in tmp_path.glob("*-collection")]
    assert collections
    assert all(collection == collections[0] for collection in collections)
    original = [f"test_case_{position:02}" for position in range(48)]
    worker_count = 2 if workers == "auto" else int(workers)
    if worker_count > 1 and distribution == "load" and expression == "cost":
        starts = sorted(path.read_text().splitlines()[0] for path in tmp_path.glob("*-executed"))
        assert starts == original[-worker_count:]
        assert sorted(collections[0]) == original
    else:
        assert collections[0] == (["test_ordinary"] if not expression else []) + original
    executed = [
        name for path in tmp_path.glob("*-executed") for name in path.read_text().splitlines()
    ]
    assert sorted(executed) == sorted(collections[0])
