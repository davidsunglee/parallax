"""Minimal local stub for the Testcontainers network the replication pair joins."""

from typing import Self

class Network:
    name: str

    def __init__(self) -> None: ...
    def create(self) -> Self: ...
    def remove(self) -> None: ...
