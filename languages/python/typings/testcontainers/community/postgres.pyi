"""Minimal local stub for the untyped Testcontainers Postgres package.

Covers only the surface the self-managed provisioners use; a stub keeps the
Docker-only provisioners strict-Pyright clean without suppressing type errors.
"""

from typing import Self

from testcontainers.core.container import DockerContainer

class PostgresContainer(DockerContainer):
    port: int
    username: str
    password: str
    dbname: str

    def __init__(
        self,
        image: str,
        *,
        username: str | None = None,
        password: str | None = None,
        dbname: str | None = None,
        driver: str | None = "psycopg2",
    ) -> None: ...
    def start(self) -> Self: ...
    def get_connection_url(self) -> str: ...
