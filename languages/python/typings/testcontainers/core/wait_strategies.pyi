"""Minimal local stub for the Testcontainers readiness strategies Parallax uses."""

from typing import Self

class WaitStrategy:
    def with_startup_timeout(self, timeout: int) -> Self: ...

class ExecWaitStrategy(WaitStrategy):
    def __init__(self, command: list[str]) -> None: ...
