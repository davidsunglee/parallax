"""The full collection and actual selection from an independent pytest session."""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from tests._support.repo import PY_ROOT

WHOLE_CLASS = "1/1"


@dataclass(frozen=True)
class SessionSelection:
    collected: list[str]
    selected: list[str]


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--selection-snapshot", type=Path)


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> Iterator[None]:
    collected = list(items)
    yield
    path = config.getoption("--selection-snapshot")
    if path is not None:
        path.write_text(
            json.dumps(
                {
                    "collected": [item.nodeid for item in collected],
                    "selected": [item.nodeid for item in items],
                }
            ),
            encoding="utf-8",
        )


def selection(expression: str | None, shard: str) -> SessionSelection:
    """Collect the real tree and record its selection under the given options."""
    narrowing = [] if expression is None else ["-m", expression]
    with TemporaryDirectory(prefix="parallax-selection-") as temporary:
        snapshot = Path(temporary) / "selection.json"
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                *narrowing,
                "--shard",
                shard,
                "--collect-only",
                "-q",
                "-p",
                "no:cacheprovider",
                "-p",
                __name__,
                "--selection-snapshot",
                str(snapshot),
            ],
            cwd=PY_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        document = json.loads(snapshot.read_text(encoding="utf-8"))
    return SessionSelection(collected=document["collected"], selected=document["selected"])


def selections(requests: Sequence[tuple[str | None, str]]) -> list[SessionSelection]:
    expressions = [expression for expression, _ in requests]
    shards = [shard for _, shard in requests]
    with ThreadPoolExecutor(max_workers=len(requests)) as sessions:
        return list(sessions.map(selection, expressions, shards))
