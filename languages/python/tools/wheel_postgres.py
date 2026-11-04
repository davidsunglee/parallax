from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import zipfile
from collections.abc import Generator, Sequence
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_PORT = 55432
_EDB_DOWNLOADS = "https://www.enterprisedb.com/download-postgresql-binaries"


@dataclass(frozen=True)
class PostgresSetup:
    env: dict[str, str]
    observations: dict[str, Any]


def _supported_version(version: str) -> int:
    match = re.fullmatch(r"18\.(\d+)", version)
    if match is None or int(match[1]) < 6:
        raise ValueError(f"PostgreSQL {version!r} is outside the required >=18.6,<19 policy")
    return 180000 + int(match[1])


class _WindowsDownloads(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.text: list[str] = []
        self.links: dict[str, str] = {}
        self.anchor: str | None = None

    def handle_data(self, data: str) -> None:
        self.text.append(data)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "a":
            self.anchor = attributes.get("href")
        if tag == "img" and attributes.get("alt") == "Windows x86-64" and self.anchor:
            versions = re.findall(r"Version\s+(\d+\.\d+)", "".join(self.text))
            if versions:
                self.links[versions[-1]] = self.anchor

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            self.anchor = None


def windows_download(page: str, version: str) -> str:
    parser = _WindowsDownloads()
    parser.feed(page)
    link = parser.links.get(version)
    if link is None or urlparse(link).netloc != "sbp.enterprisedb.com":
        raise ValueError(f"EDB does not advertise Windows x86-64 binaries for PostgreSQL {version}")
    return link


class _Commands:
    def __init__(self, output: Path) -> None:
        self.output = output
        self.env = dict(os.environ)

    def run(self, arguments: Sequence[str], *, check: bool = True) -> str:
        with (self.output / "setup.log").open("a", encoding="utf-8") as log:
            log.write(f"$ {subprocess.list2cmdline(arguments)}\n")
            log.flush()
            result = subprocess.run(
                arguments,
                env=self.env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            log.write(result.stdout)
            log.flush()
        print(result.stdout, end="", flush=True)
        if check and result.returncode:
            raise subprocess.CalledProcessError(result.returncode, arguments, result.stdout)
        return result.stdout.strip()


def _stop_container(commands: _Commands, container: str) -> None:
    failures: list[Exception] = []
    for arguments in (["docker", "logs", container], ["docker", "rm", "-f", container]):
        try:
            captured = commands.run(arguments)
            if arguments[1] == "logs":
                (commands.output / "server.log").write_text(captured, encoding="utf-8")
        except Exception as error:
            failures.append(error)
    if failures:
        raise ExceptionGroup("PostgreSQL container evidence/cleanup failed", failures)


def _docker(
    version: str, commands: _Commands, lifetime: ExitStack
) -> tuple[list[str], dict[str, Any]]:
    image = f"postgres:{version}"
    commands.run(["docker", "pull", image])
    inspected = json.loads(commands.run(["docker", "image", "inspect", image]))[0]
    container = commands.run(
        [
            "docker",
            "run",
            "--detach",
            "--publish",
            f"127.0.0.1:{_PORT}:5432",
            "--env",
            "POSTGRES_HOST_AUTH_METHOD=trust",
            image,
        ]
    )
    lifetime.callback(_stop_container, commands, container)
    ready = ["docker", "exec", container, "pg_isready", "-h", "127.0.0.1", "-U", "postgres"]
    deadline = time.monotonic() + 90
    while True:
        try:
            commands.run(ready)
            break
        except subprocess.CalledProcessError:
            if time.monotonic() >= deadline:
                raise TimeoutError("PostgreSQL container did not become ready") from None
            time.sleep(1)
    return ["docker", "exec", container, "psql"], {
        "image": image,
        "image_id": inspected["Id"],
        "image_digests": inspected.get("RepoDigests", []),
        "image_architecture": inspected["Architecture"],
    }


def _windows(version: str, commands: _Commands) -> tuple[Path, dict[str, Any]]:
    with urllib.request.urlopen(_EDB_DOWNLOADS, timeout=60) as response:
        link = windows_download(response.read().decode("utf-8"), version)
    archive = commands.output / "postgresql-windows.zip"
    digest = hashlib.sha256()
    with urllib.request.urlopen(link, timeout=120) as response, archive.open("wb") as destination:
        downloaded_url = str(response.geturl())
        parsed = urlparse(downloaded_url)
        if parsed.netloc != "get.enterprisedb.com" or not re.fullmatch(
            rf"/postgresql/postgresql-{re.escape(version)}-\d+-windows-x64-binaries\.zip",
            parsed.path,
        ):
            raise ValueError(f"EDB binary download did not resolve to PostgreSQL {version} x64")
        while chunk := response.read(1024 * 1024):
            destination.write(chunk)
            digest.update(chunk)
    extracted = commands.output / "postgresql"
    with zipfile.ZipFile(archive) as contents:
        contents.extractall(extracted)
    archive.unlink()
    return extracted / "pgsql" / "bin", {
        "download_url": downloaded_url,
        "download_sha256": digest.hexdigest(),
    }


def _native(
    version: str, commands: _Commands, lifetime: ExitStack
) -> tuple[list[str], dict[str, Any]]:
    observations: dict[str, Any] = {}
    if sys.platform == "win32":
        binary, observations = _windows(version, commands)
    elif sys.platform == "darwin":
        commands.run(["brew", "update"])
        formula = "postgresql@18"
        commands.run(["brew", "install", formula])
        commands.run(["brew", "upgrade", formula])
        binary = Path(commands.run(["brew", "--prefix", formula])) / "bin"
    else:
        raise ValueError(f"unsupported native PostgreSQL host: {sys.platform}")
    commands.env["PATH"] = f"{binary}{os.pathsep}{commands.env.get('PATH', '')}"
    commands.env["PG_CONFIG"] = str(binary / "pg_config")
    data = commands.output / "data"
    server_log = commands.output / "server.log"
    commands.run(
        [
            str(binary / "initdb"),
            "-D",
            str(data),
            "-U",
            "postgres",
            "-A",
            "trust",
            "--locale=C",
            "--encoding=UTF8",
        ]
    )
    stop = [str(binary / "pg_ctl"), "-D", str(data), "-m", "immediate", "-w", "stop"]
    lifetime.callback(commands.run, stop)
    commands.run(
        [
            str(binary / "pg_ctl"),
            "-D",
            str(data),
            "-l",
            str(server_log),
            "-o",
            f"-p {_PORT} -h 127.0.0.1",
            "-w",
            "start",
        ]
    )
    observations["pg_config"] = commands.run([str(binary / "pg_config"), "--version"])
    return [str(binary / "psql")], observations


@contextmanager
def provision(version: str, output_path: Path) -> Generator[PostgresSetup]:
    expected = _supported_version(version)
    output_path.mkdir(parents=True, exist_ok=True)
    commands = _Commands(output_path.resolve())
    lifetime = ExitStack()
    try:
        start = _docker if sys.platform.startswith("linux") else _native
        psql, observations = start(version, commands, lifetime)
        query = [*psql, "-h", "127.0.0.1", "-U", "postgres", "-d", "postgres", "-Atc"]
        if not sys.platform.startswith("linux"):
            query[1:1] = ["-p", str(_PORT)]
        actual = commands.run([*query, "show server_version_num"])
        if actual != str(expected):
            raise ValueError(
                f"PostgreSQL server is {actual}, expected exact {version} ({expected})"
            )
        observations.update(
            server_version_num=int(actual),
            server_version=commands.run([*query, "show server_version"]),
        )
        env = {
            "PATH": commands.env["PATH"],
            "PARALLAX_WHEEL_DSN": f"postgresql://postgres@127.0.0.1:{_PORT}/postgres",
        }
        if "PG_CONFIG" in commands.env:
            env["PG_CONFIG"] = commands.env["PG_CONFIG"]
        yield PostgresSetup(env, observations)
    except BaseException as error:
        try:
            lifetime.close()
        except BaseException as cleanup:
            raise BaseExceptionGroup(
                "PostgreSQL operation and cleanup failed", [error, cleanup]
            ) from None
        raise
    else:
        lifetime.close()
