from __future__ import annotations

import json
import time
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest


def configure(config: pytest.Config) -> None:
    """Register timing capture only when ``--timing-report`` selects a directory."""
    directory = config.getoption("--timing-report")
    if directory is not None:
        worker_input = cast("dict[str, str]", getattr(config, "workerinput", {}))
        worker = worker_input.get("workerid", "controller")
        config.pluginmanager.register(_SessionTimings(Path(directory), worker))


class _SessionTimings:
    def __init__(self, directory: Path, worker: str) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        self._stream = (directory / f"{worker}.jsonl").open("w", encoding="utf-8")
        self._controller = worker == "controller"
        self._write("configured")

    def _write(self, event: str, **fields: object) -> None:
        self._stream.write(json.dumps({"event": event, "time": time.time(), **fields}) + "\n")
        self._stream.flush()

    def pytest_sessionstart(self) -> None:
        self._write("session-start")

    @pytest.hookimpl(hookwrapper=True)
    def pytest_collection(self, session: pytest.Session) -> Iterator[None]:
        self._write("collection-start")
        try:
            yield
        finally:
            self._write("collection-finish", selected=len(session.items))

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        if self._controller:
            self._write(
                "test-report",
                worker=getattr(report, "worker_id", "controller"),
                nodeid=report.nodeid,
                phase=report.when,
                outcome=report.outcome,
                duration=report.duration,
                start=report.start,
                stop=report.stop,
            )

    def pytest_sessionfinish(self, exitstatus: int) -> None:
        self._write("session-finish", exitstatus=int(exitstatus))

    def pytest_unconfigure(self) -> None:
        self._stream.close()
