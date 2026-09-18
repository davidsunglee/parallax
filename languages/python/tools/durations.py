"""Wall-clock spans around the report harness's own work, for the report tools.

A span brackets harness work outside every measured window: a member
subprocess, a provisioning call, a workload loop, one child's lifetime. It is
telemetry, never evidence: a span explains where a capture's elapsed time went
and no reading depends on one. Spans nest, and a parent includes its children,
so a critical path is read off the outermost span and never summed from the
spans inside it. A span is recorded even when the work it brackets fails, so a
failed operation still has attribution.
"""

from __future__ import annotations

import json
import math
import sys
import time
from collections.abc import Callable, Generator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, cast

SCHEMA_VERSION: Final = 1
SCOPES: Final = frozenset({"collection", "member", "setup", "workload", "case", "scenario"})


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class Span:
    scope: str
    name: str
    labels: Mapping[str, str]
    started_at: datetime
    seconds: float

    def document(self) -> dict[str, object]:
        return {
            "scope": self.scope,
            "name": self.name,
            "labels": dict(self.labels),
            "startedAt": self.started_at.isoformat(),
            "seconds": self.seconds,
        }


@dataclass(frozen=True, slots=True)
class Unavailable:
    """Telemetry that was expected and never arrived, with the reason."""

    scope: str
    name: str
    reason: str

    def document(self) -> dict[str, object]:
        return {"scope": self.scope, "name": self.name, "reason": self.reason}


class Spans:
    """A recorder of spans and of the telemetry it could not obtain.

    ``clock`` supplies elapsed time and ``now`` the wall-clock start; both are
    injectable so a test records deterministic spans.
    """

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._clock = clock
        self._now = now
        self._spans: list[Span] = []
        self._unavailable: list[Unavailable] = []

    @property
    def spans(self) -> tuple[Span, ...]:
        return tuple(self._spans)

    @property
    def unavailable(self) -> tuple[Unavailable, ...]:
        return tuple(self._unavailable)

    @contextmanager
    def span(self, scope: str, name: str, **labels: str) -> Generator[None]:
        _scope(scope)
        started_at = self._now()
        started = self._clock()
        try:
            yield
        finally:
            self._spans.append(Span(scope, name, labels, started_at, self._clock() - started))

    def add(self, span: Span) -> None:
        self._spans.append(span)

    def extend(self, other: Spans) -> None:
        self._spans.extend(other.spans)
        self._unavailable.extend(other.unavailable)

    def missing(self, scope: str, name: str, reason: str) -> None:
        self._unavailable.append(Unavailable(_scope(scope), name, reason))

    def document(self) -> dict[str, object]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "spans": [span.document() for span in self._spans],
            "unavailable": [entry.document() for entry in self._unavailable],
        }

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.document(), indent=2) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> Spans:
        """The recorder a sidecar was written from; ``ValueError`` names the
        first way the document is not one."""
        document = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(document, Mapping):
            raise ValueError(f"{path} does not hold a durations document")
        loaded = cast("Mapping[str, object]", document)
        if loaded.get("schemaVersion") != SCHEMA_VERSION:
            raise ValueError(
                f"{path} has schemaVersion {loaded.get('schemaVersion')!r}, "
                f"expected {SCHEMA_VERSION}"
            )
        spans = cls()
        for entry in _entries(loaded, "spans", path):
            spans.add(_span(entry))
        for entry in _entries(loaded, "unavailable", path):
            spans.missing(_string(entry, "scope"), _string(entry, "name"), _string(entry, "reason"))
        return spans


def write_sidecar(path: Path, write: Callable[[Path], None]) -> None:
    """Write one telemetry sidecar with ``write``, reporting an I/O failure on
    stderr instead of raising it: telemetry a member cannot record is
    unavailable, and never changes the member's envelope or exit status."""
    try:
        write(path)
    except OSError as error:
        print(f"telemetry sidecar {path} was not written: {error}", file=sys.stderr)


def _scope(scope: str) -> str:
    if scope not in SCOPES:
        raise ValueError(f"span scope {scope!r} is not one of {sorted(SCOPES)}")
    return scope


def _entries(document: Mapping[str, object], key: str, path: Path) -> list[Mapping[str, object]]:
    listed = document.get(key, [])
    if not isinstance(listed, Sequence) or isinstance(listed, str):
        raise ValueError(f"{path} {key} is not a list")
    entries: list[Mapping[str, object]] = []
    for entry in cast("Sequence[object]", listed):
        if not isinstance(entry, Mapping):
            raise ValueError(f"{path} {key} entry {entry!r} is not an object")
        entries.append(cast("Mapping[str, object]", entry))
    return entries


def _string(entry: Mapping[str, object], key: str) -> str:
    value = entry.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"span {key} {value!r} is not a non-empty string")
    return value


def _span(entry: Mapping[str, object]) -> Span:
    labels = entry.get("labels", {})
    if not isinstance(labels, Mapping):
        raise ValueError(f"span labels {labels!r} are not an object")
    typed_labels = cast("Mapping[object, object]", labels)
    if not all(
        isinstance(key, str) and isinstance(value, str) for key, value in typed_labels.items()
    ):
        raise ValueError(f"span labels {labels!r} are not all strings")
    started = datetime.fromisoformat(_string(entry, "startedAt"))
    if started.tzinfo is None:
        raise ValueError(f"span startedAt {started.isoformat()!r} carries no timezone")
    seconds = entry.get("seconds")
    if isinstance(seconds, bool) or not isinstance(seconds, int | float):
        raise ValueError(f"span seconds {seconds!r} is not a number")
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError(f"span seconds {seconds!r} is not a non-negative finite number")
    return Span(
        _scope(_string(entry, "scope")),
        _string(entry, "name"),
        cast("Mapping[str, str]", dict(typed_labels)),
        started,
        float(seconds),
    )


def render(spans: Spans) -> str:
    """The recorded spans as a Markdown section, outermost first."""
    lines = ["## Durations", ""]
    ordered = sorted(spans.spans, key=lambda span: (span.started_at, -span.seconds))
    if not ordered:
        lines.append("No durations were recorded.")
    for span in ordered:
        if span.scope == "collection":
            lines.append(
                f"Critical path: {span.seconds:.3f} s, the `{span.name}` collection span. "
                "Nested spans are included in their parents and are never summed."
            )
    if ordered:
        lines += [
            "",
            "| Scope | Name | Labels | Started | Seconds |",
            "|---|---|---|---|---:|",
        ]
        lines += [
            f"| {span.scope} | {span.name} | {_labels(span.labels)} | "
            f"{span.started_at.isoformat()} | {span.seconds:.3f} |"
            for span in ordered
        ]
    if spans.unavailable:
        lines += ["", "Durations unavailable:", ""]
        lines += [f"- {entry.scope} `{entry.name}`: {entry.reason}" for entry in spans.unavailable]
    return "\n".join(lines) + "\n"


def _labels(labels: Mapping[str, str]) -> str:
    return ", ".join(f"{key}={labels[key]}" for key in sorted(labels)) or "-"
