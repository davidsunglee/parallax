"""``parallax.snapshot.handle._publication`` — prepared Model Selections and the
Serving Model that publishes them.

A Model Selection is the prepared execution form of one Domain Model under one
Model Edition: every finite, fallible model-only derivation has already run, and
the products are retained on the selection itself. It is process-local and
carries no transaction, connection, Clock, or Execution Lifecycle Provider,
which is what this scope's grant row states structurally: it is SEALED
(`spec/python.md` §7) to ``parallax.core.entity`` and ``m-unit-work`` alone, so
nothing here can name an attempt, a port, or an activity. What the row cannot
say — that ``m-unit-work``'s ``Clock`` is not held either — is a promise the
record types keep by having no such field.

The selection is opaque from outside: ``model`` and ``edition`` are its only
public properties, and its two projections are reached through
:func:`read_projection` and :func:`write_projection`, defined here beside the
class so the reach needs no private-usage suppression anywhere. A read entry
receives the read projection and a write entry the write projection, so each
verb holds only the capability it needs. The two projections carry the same
edition and share the exact same :class:`~parallax.core.entity._layout.CatalogedModel`,
by construction rather than by check.

Preparation itself — :func:`~parallax.snapshot.handle._database.prepare_model`
— lives in the composition root, because building a Write Planner reaches the
SQL-lowering group this scope may not; this module owns the one constructor it
calls. A :class:`ServingModel` then holds the current selection for executions
to adopt and replaces it by identity compare-and-replace under one lock, so a
reader observes a complete selection or another complete one and never a
partial state, and a stale publisher is refused rather than reordered.

Names crossing a module boundary are spelled bare; privacy is carried by this
MODULE's leading underscore and by the package's frozen ``__all__``.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from parallax.core.entity import DomainModel, EntityGraphConstruction, EntityRowCodec
from parallax.core.entity._layout import CatalogedModel
from parallax.core.unit_work import WritePlanner

__all__ = [
    "ModelSelection",
    "PublicationConflictError",
    "SelectedReadModel",
    "SelectedWriteModel",
    "ServingModel",
    "check_edition",
    "read_projection",
    "write_projection",
]


def check_edition(edition: str, /) -> str:
    """``edition`` itself, refusing anything but a nonempty string.

    An edition is an opaque token compared only for equality: never parsed,
    ordered, or read for chronology, so the one thing to check is that there is
    a token at all.
    """
    if not isinstance(edition, str):  # pyright: ignore[reportUnnecessaryIsInstance] - the runtime half of the annotation, so an untyped caller is named
        raise ValueError(f"a Model Edition is a nonempty string, not {edition!r}")
    if not edition:
        raise ValueError("a Model Edition is a nonempty string; the empty string names nothing")
    return edition


@dataclass(frozen=True, slots=True)
class SelectedReadModel:
    """The read projection of one Model Selection: the edition it was prepared
    under, the cataloged model a read resolves, plans, and converts against,
    and — for a class-backed model — the Entity Graph Construction that
    materializes its rows into instances.

    A property of the operation rather than of the Handle: the scope above takes
    the record its execution policy hands back for THIS operation, and a stream
    keeps the one it opened under through all of its pages.

    The write codec is deliberately absent. A read never derives a row, so a
    record carrying one would offer the write half to every read composition
    that holds it. The construction is the only half that can be missing at
    all: a member layout and a row are both derived from accepted metadata, so
    a descriptor-backed model prepares a fully functional catalog while
    preparing no materializer, and a Typed read is refused on that absence
    before any I/O.
    """

    edition: str
    model: CatalogedModel
    construction: EntityGraphConstruction | None


@dataclass(frozen=True, slots=True)
class SelectedWriteModel:
    """The write projection of one Model Selection: the same edition and the
    exact same cataloged model as its read projection, with the Entity Row
    Codec every write derives its rows through and the Write Planner every
    flush plans through.
    """

    edition: str
    model: CatalogedModel
    codec: EntityRowCodec
    planner: WritePlanner


class ModelSelection:
    """One Domain Model prepared under one Model Edition, complete.

    Opaque by construction: ``prepare_model`` answers a complete selection or
    raises, and no partially prepared value exists. ``model`` is the exact
    original Domain Model and ``edition`` the token it was prepared under; the
    projections behind them are reached through :func:`read_projection` and
    :func:`write_projection`. Equality is identity, which is what a Serving
    Model compares when it publishes.
    """

    __slots__ = ("_edition", "_model", "_read", "_write")

    def __init__(
        self,
        edition: str,
        model: DomainModel,
        read: SelectedReadModel,
        write: SelectedWriteModel,
    ) -> None:
        self._edition = check_edition(edition)
        self._model = model
        self._read = read
        self._write = write

    def __init_subclass__(cls) -> None:
        raise TypeError("ModelSelection is the prepared form itself and admits no subclass")

    @property
    def model(self) -> DomainModel:
        """The exact Domain Model this selection prepared."""
        return self._model

    @property
    def edition(self) -> str:
        """The opaque Model Edition this selection was prepared under."""
        return self._edition

    def __repr__(self) -> str:
        return f"ModelSelection(edition={self._edition!r})"


def read_projection(selection: ModelSelection, /) -> SelectedReadModel:
    """The read projection ``selection`` prepared."""
    return selection._read  # pyright: ignore[reportPrivateUsage] - the same-module accessor the opaque selection is read through


def write_projection(selection: ModelSelection, /) -> SelectedWriteModel:
    """The write projection ``selection`` prepared."""
    return selection._write  # pyright: ignore[reportPrivateUsage] - the same-module accessor the opaque selection is read through


class PublicationConflictError(RuntimeError):
    """A publication was refused because the Serving Model did not hold the
    selection the publisher expected.

    Refused rather than retried or reordered: editions are never ordered to
    pick a winner. :attr:`expected` is what the publisher believed was held and
    :attr:`held` is what actually was, so the loser of a race can rebase on the
    selection it lost to without a second ``current()`` that may already
    observe a third.
    """

    def __init__(self, *, expected: ModelSelection, held: ModelSelection) -> None:
        super().__init__(
            f"publication refused: expected {expected!r} to be serving, but {held!r} is"
        )
        self.expected = expected
        self.held = held


class ServingModel:
    """The one holder of the Model Selection new executions adopt.

    Always holds a complete selection, from the initial one on. ``current()``
    is one reference read — no lock, no callback, no I/O, no preparation — so
    an adopting execution never waits on a publisher. ``publish`` compares the
    held selection with ``expected`` by identity and replaces it, as one step
    under one lock, so two publishers cannot both succeed against the same
    expectation and a reader observes either selection whole.

    A static model is this same holder with no later publication. It is a
    separate object rather than a verb on a Database so that holding a handle
    confers no authority to change the model it serves; two handles connected
    over one Serving Model flip together.
    """

    __slots__ = ("_lock", "_selection")

    def __init__(self, initial: ModelSelection) -> None:
        if not isinstance(initial, ModelSelection):  # pyright: ignore[reportUnnecessaryIsInstance] - the runtime half of the annotation, so an untyped caller is named
            raise TypeError(f"a ServingModel holds a prepared ModelSelection, not {initial!r}")
        self._lock = threading.Lock()
        self._selection = initial

    def __init_subclass__(cls) -> None:
        raise TypeError("ServingModel is the single concrete holder and admits no subclass")

    def current(self) -> ModelSelection:
        """The exact selection currently serving."""
        return self._selection

    def publish(self, candidate: ModelSelection, *, expected: ModelSelection) -> None:
        """Replace ``expected`` with ``candidate``, or refuse without changing
        anything.

        Raises :class:`PublicationConflictError` when the held selection is not
        ``expected`` by identity; the error carries what was actually held.
        """
        if not isinstance(candidate, ModelSelection):  # pyright: ignore[reportUnnecessaryIsInstance] - the runtime half of the annotation, so an untyped caller is named
            raise TypeError(
                f"a ServingModel publishes a prepared ModelSelection, not {candidate!r}"
            )
        with self._lock:
            held = self._selection
            if held is not expected:
                raise PublicationConflictError(expected=expected, held=held)
            self._selection = candidate

    def __repr__(self) -> str:
        return f"ServingModel(current={self._selection!r})"
