from __future__ import annotations

import re
from collections.abc import Mapping
from types import MappingProxyType
from typing import Final, cast

__all__ = [
    "ConflictError",
    "InternalError",
    "InvalidValueError",
    "NoResultFound",
    "ParallaxError",
    "TooManyResultsFound",
    "UnsupportedError",
    "UsageError",
]

_CODE_SPELLING: Final = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")


def _require_code_spelling(code: str) -> None:
    """Refuse a ``code`` that is not lowercase words joined by single hyphens.

    Only the spelling is checked here: each owner keeps its own vocabulary
    beside the code that raises it.
    """
    if _CODE_SPELLING.fullmatch(code) is None:
        raise ValueError(f"{code!r} is not an error code: lowercase words joined by hyphens")


class ParallaxError(Exception):
    """The root of every exception Parallax raises.

    ``code`` is a stable, hyphenated name for what went wrong, owned by the
    module that raises it; a class whose reason another field carries has one
    constant code. ``args`` is exactly ``(code, message)``, and the rendered
    text is ``"{code}: {message}"``.

    ``is_transient`` answers whether a later attempt of the same work may
    succeed once Parallax's own retries are spent.
    """

    def __init__(self, code: str, message: str) -> None:
        _require_code_spelling(code)
        super().__init__(code, message)

    @property
    def code(self) -> str:
        return cast("str", self.args[0])

    @property
    def is_transient(self) -> bool:
        return False

    def __str__(self) -> str:
        return f"{self.args[0]}: {self.args[1]}"

    def __reduce__(self) -> tuple[object, ...]:
        # Rebuilding from the instance state rather than re-running a
        # subclass's constructor keeps every subclass picklable whatever its
        # signature, including the hand-frozen ones.
        return (_restored, (type(self), self.args, dict(self.__dict__)))


def _restored(
    kind: type[ParallaxError], args: tuple[object, ...], state: dict[str, object]
) -> ParallaxError:
    error = kind.__new__(kind, *args)
    error.__dict__.update(state)
    return error


class UsageError(ParallaxError):
    """The request contradicts Parallax's rules; fix the code, declaration or input."""


class InvalidValueError(UsageError):
    """A value you supplied does not fit its member's type, value space or requiredness.

    A reference to a member the model does not declare, and any other
    structural mistake, is a plain :class:`UsageError`.
    """


class UnsupportedError(ParallaxError):
    """A reasonable request this version of Parallax, or the selected Dialect,
    cannot serve yet.

    Serving it would not change what the request means, so the calling code is
    not wrong; it waits for the capability or avoids the gap another way. A
    request that contradicts the semantics is a :class:`UsageError` instead.
    """


class InternalError(ParallaxError):
    """A Parallax invariant failed; no change to the calling code avoids it."""


class ConflictError(ParallaxError):
    """The work collided with stored state another writer changed.

    ``entity`` is the canonical Entity name and ``key`` the primary key, by
    declared attribute name, of the row the conflict hit, where there is one.
    ``is_transient`` is what the raise site stated: whether re-running the work
    may succeed, which is also whether the retry loop replays it.
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        entity: str | None = None,
        key: Mapping[str, object] | None = None,
        transient: bool = False,
    ) -> None:
        super().__init__(code, message)
        self._entity = entity
        self._key = None if key is None else dict(key)
        self._transient = transient

    @property
    def entity(self) -> str | None:
        return self._entity

    @property
    def key(self) -> Mapping[str, object] | None:
        return None if self._key is None else MappingProxyType(self._key)

    @property
    def is_transient(self) -> bool:
        return self._transient


class NoResultFound(ParallaxError):
    """A single-result accessor found no result."""

    def __init__(self, message: str) -> None:
        super().__init__("no-result-found", message)


class TooManyResultsFound(ParallaxError):
    """A single-result accessor found more than one result."""

    def __init__(self, message: str) -> None:
        super().__init__("too-many-results-found", message)
