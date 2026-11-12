"""Durable child results, reused only with identical measurement inputs."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from production_origins import source_roots


def journal_root(workspace: Path) -> Path:
    return Path(os.environ.get("PARALLAX_CAPTURE_JOURNAL", workspace / "reports" / "checkpoints"))


def _encoded(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def capture_identity(
    workspace: Path,
    sources: Sequence[Path],
    runtime_metadata: Mapping[str, object],
) -> dict[str, object]:
    paths = set(sources)
    paths.add(workspace / "uv.lock")
    for root in source_roots(workspace):
        paths.update(
            path
            for path in root.rglob("*")
            if path.is_file() and path.suffix in {".py", ".pyi", ".pyx", ".pxd", ".so", ".pyd"}
        )
    return {
        "sources": {
            path.relative_to(workspace).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(paths)
        },
        "runtime": dict(runtime_metadata),
        "host": {
            "node": platform.node(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "cores": os.cpu_count(),
        },
    }


class CaptureJournal:
    """Keep successful payloads immutable; incomplete or corrupt entries are refused."""

    def __init__(self, root: Path, subject: str, identity: Mapping[str, object]) -> None:
        self._identity = cast("dict[str, object]", json.loads(_encoded(identity)))
        self._root = root / subject / hashlib.sha256(_encoded(identity)).hexdigest()

    def _path(self, key: Mapping[str, object]) -> Path:
        return self._root / f"{hashlib.sha256(_encoded(key)).hexdigest()}.json"

    def load(self, key: Mapping[str, object]) -> dict[str, object] | None:
        path = self._path(key)
        try:
            document: object = json.loads(path.read_bytes())
        except FileNotFoundError:
            return None
        except (ValueError, UnicodeError) as error:
            raise ValueError(f"invalid capture checkpoint {path}: {error}") from error
        if not isinstance(document, dict):
            raise ValueError(f"invalid capture checkpoint {path}: expected an object")
        record = cast("dict[str, object]", document)
        payload = record.get("payload")
        if (
            record.get("schemaVersion") != 1
            or record.get("identity") != self._identity
            or record.get("key") != dict(key)
            or not isinstance(payload, dict)
            or record.get("payloadSha256")
            != hashlib.sha256(_encoded(cast("dict[str, object]", payload))).hexdigest()
        ):
            raise ValueError(f"invalid capture checkpoint {path}: identity or payload mismatch")
        return cast("dict[str, object]", payload)

    def store(self, key: Mapping[str, object], payload: Mapping[str, object]) -> None:
        path = self._path(key)
        document = {
            "schemaVersion": 1,
            "identity": self._identity,
            "key": dict(key),
            "payload": dict(payload),
            "payloadSha256": hashlib.sha256(_encoded(payload)).hexdigest(),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=".pending-", delete=False
        ) as stream:
            temporary = Path(stream.name)
            try:
                stream.write(_encoded(document) + b"\n")
                stream.flush()
                os.fsync(stream.fileno())
            except BaseException:
                temporary.unlink(missing_ok=True)
                raise
        try:
            try:
                os.link(temporary, path)
            except FileExistsError:
                if _encoded(self.load(key)) != _encoded(payload):
                    raise ValueError(
                        f"capture checkpoint {path} already holds another result"
                    ) from None
            if os.name == "posix":
                descriptor = os.open(path.parent, os.O_RDONLY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
        finally:
            temporary.unlink(missing_ok=True)
