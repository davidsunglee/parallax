"""The full collection and actual selection from an independent pytest session."""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from tests._support import shards
from tests._support.repo import PY_ROOT


@dataclass(frozen=True)
class SessionSelection:
    collected: list[str]
    selected: list[str]
    classes: dict[str, str]
    groups: dict[str, str]


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
                    "classes": {
                        item.nodeid: next(
                            mark.name
                            for mark in item.iter_markers()
                            if mark.name in {"cost", "db", "dbfree", "cloud"}
                        )
                        for item in collected
                    },
                    "groups": {
                        item.nodeid: group
                        for item in collected
                        if (group := shards.group_of(item)) is not None
                    },
                }
            ),
            encoding="utf-8",
        )


def selection(*arguments: str) -> SessionSelection:
    """Collect the real tree and record its selection under the given options."""
    with TemporaryDirectory(prefix="parallax-selection-") as temporary:
        snapshot = Path(temporary) / "selection.json"
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                *arguments,
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
    return SessionSelection(**document)
