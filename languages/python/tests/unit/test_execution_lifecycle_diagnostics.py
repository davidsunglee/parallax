"""Failure Diagnostic unit tests (m-execution-lifecycle, Docker-free).

Construction is TOTAL: the diagnostic projects an arbitrary exception, so every
field is read off code this module does not own and none of those reads may
replace the failure the caller needs to see. Each field is guarded on its own,
which is what a hostile ``code`` costing only ``code`` proves — a diagnostic that
collapsed to one fallback would still be total and would still be useless.

Bounds are byte bounds over encoded UTF-8, so the two interesting inputs are a
message longer than its ceiling and a cut that lands inside a multi-byte code
point. Detachment is the last claim: nothing here holds the exception, its
traceback, or its cause graph — including through a ``str`` subclass, which is
how a reference walks back in wearing a string's shape.
"""

from __future__ import annotations

import gc
import weakref

from parallax.core.db_error import Category, DatabaseError
from parallax.core.execution_lifecycle import (
    MESSAGE_LIMIT_BYTES,
    STACK_LIMIT_BYTES,
    FailureDiagnostic,
)
from parallax.core.execution_lifecycle._diagnostics import (
    database_diagnostic_for,
    diagnostic_for,
)


class _Coded(RuntimeError):
    code = "a-stable-code"


class _HostileMessage(RuntimeError):
    def __str__(self) -> str:
        raise ValueError("this exception refuses to render")


class _HostileCode(RuntimeError):
    @property
    def code(self) -> str:
        raise ValueError("this exception refuses to publish a code")


class _FatalCode(RuntimeError):
    @property
    def code(self) -> str:
        raise KeyboardInterrupt


class _Smuggled(str):
    """A ``str`` subclass carrying a reference and refusing to be encoded."""

    __slots__ = ("owner",)

    def __new__(cls, value: str, owner: object) -> _Smuggled:
        text = super().__new__(cls, value)
        text.owner = owner
        return text

    def encode(self, encoding: str = "utf-8", errors: str = "strict") -> bytes:
        raise KeyboardInterrupt


class _SmugglingMessage(RuntimeError):
    def __str__(self) -> str:
        return _Smuggled("legible but hostile", self)


class _SmugglingCode(RuntimeError):
    @property
    def code(self) -> str:
        return _Smuggled("a-stable-code", self)


class _ShadowedDatabaseError(DatabaseError):
    """A port error whose two neutral facts refuse to be read."""

    def __init__(self) -> None:
        Exception.__init__(self, "this error shadows its own classification")

    @property
    def category(self) -> Category:  # pyright: ignore[reportIncompatibleVariableOverride]
        raise KeyboardInterrupt

    @property
    def native_code(self) -> str:  # pyright: ignore[reportIncompatibleVariableOverride]
        raise ValueError("this error refuses to publish a native code")


def _raised(error: BaseException) -> BaseException:
    """``error`` with a real traceback, which is what a rendered stack needs."""
    try:
        raise error
    except BaseException as caught:
        return caught


def test_a_diagnostic_names_the_fully_qualified_runtime_type() -> None:
    # Spelled the same way for every exception, builtins included, so a reader
    # never has to know which rule produced it.
    assert diagnostic_for(_raised(ValueError("bad"))).qualified_type == "builtins.ValueError"
    assert diagnostic_for(_Coded()).qualified_type == f"{__name__}._Coded"


def test_a_diagnostic_carries_the_message_the_stack_and_no_truncation_flags() -> None:
    diagnostic = diagnostic_for(_raised(ValueError("bad")))
    assert diagnostic.message == "bad"
    assert not diagnostic.message_truncated
    assert not diagnostic.stack_truncated
    assert "ValueError: bad" in diagnostic.stack
    # A rendered frame, so the stack locates the failure rather than naming it.
    assert "in _raised" in diagnostic.stack


def test_a_rendered_stack_follows_the_declared_cause_chain() -> None:
    def failing() -> BaseException:
        try:
            try:
                raise ValueError("the original")
            except ValueError as cause:
                raise RuntimeError("the wrapper") from cause
        except RuntimeError as caught:
            return caught

    stack = diagnostic_for(failing()).stack
    assert "ValueError: the original" in stack
    assert "RuntimeError: the wrapper" in stack
    assert "direct cause" in stack


def test_a_stable_code_is_carried_and_its_absence_is_absence() -> None:
    assert diagnostic_for(_Coded()).code == "a-stable-code"
    assert diagnostic_for(ValueError("bad")).code is None
    # A `code` of some other shape is no more usable than a missing one.
    weird = ValueError("bad")
    weird.code = 7  # pyright: ignore[reportAttributeAccessIssue] - deliberately the wrong shape
    assert diagnostic_for(weird).code is None


def test_each_field_degrades_on_its_own() -> None:
    # A message that cannot render costs the message and nothing else: the
    # qualified type, the code, and the whole stack still arrive.
    message_failure = diagnostic_for(_raised(_HostileMessage()))
    assert message_failure.message == "<unavailable>"
    assert message_failure.qualified_type.endswith("._HostileMessage")
    assert "_HostileMessage" in message_failure.stack

    # And a code that cannot be read costs the code and nothing else.
    code_failure = diagnostic_for(_raised(_HostileCode("still legible")))
    assert code_failure.code is None
    assert code_failure.message == "still legible"


def test_a_control_flow_exception_from_a_field_never_escapes() -> None:
    # Observing a failure must never replace the failure the caller needs to
    # see, so even a `BaseException` raised while projecting one field is
    # swallowed — the one place in the system where that is the contract.
    diagnostic = diagnostic_for(_raised(_FatalCode("legible")))
    assert diagnostic.code is None
    assert diagnostic.message == "legible"


def test_a_hostile_encoding_never_reaches_the_bound() -> None:
    # `__str__` may legally answer a `str` SUBCLASS, and the bound is a byte
    # count — so a subclass whose `encode` raises `KeyboardInterrupt` would abort
    # the query being observed if the bound called its method. The bound calls
    # `str`'s own, so the message survives whole and the field costs nothing.
    diagnostic = diagnostic_for(_raised(_SmugglingMessage()))
    assert diagnostic.message == "legible but hostile"
    assert not diagnostic.message_truncated
    assert diagnostic.qualified_type.endswith("._SmugglingMessage")


def test_every_projected_string_is_an_exact_str() -> None:
    # A `str` subclass is a reference back into the failure wearing a string's
    # shape: this one pins the exception, its traceback, and its frames for as
    # long as the diagnostic lives, and overrides the methods a consumer calls.
    # A projection that retains nothing may keep neither.
    diagnostic = diagnostic_for(_raised(_SmugglingCode("legible")))
    assert diagnostic.code == "a-stable-code"
    assert type(diagnostic.code) is str
    assert type(diagnostic.message) is str
    assert type(diagnostic.stack) is str

    smuggling = DatabaseError(category="deadlock", native_code="40P01", message="dup")
    smuggling.native_code = _Smuggled("40P01", smuggling)
    database = database_diagnostic_for(smuggling)
    assert database.native_code == "40P01"
    assert type(database.native_code) is str


def test_a_database_error_shadowing_its_own_facts_costs_those_facts_alone() -> None:
    # The port raises whatever it raises, and a subclass may shadow either
    # neutral field. Each is read behind its own guard, so the diagnostic still
    # arrives and the failure the caller came for is still the one propagating.
    diagnostic = database_diagnostic_for(_raised(_ShadowedDatabaseError()))
    assert (diagnostic.category, diagnostic.native_code) == (None, None)
    assert diagnostic.failure.qualified_type.endswith("._ShadowedDatabaseError")
    assert "shadows its own classification" in diagnostic.failure.message


def test_a_message_beyond_its_ceiling_is_cut_and_flagged() -> None:
    diagnostic = diagnostic_for(ValueError("x" * (MESSAGE_LIMIT_BYTES + 10)))
    assert diagnostic.message_truncated
    assert len(diagnostic.message.encode("utf-8")) == MESSAGE_LIMIT_BYTES


def test_truncation_discards_a_code_point_the_cut_split() -> None:
    # The bound is a BYTE bound, and the last code point admitted by it is three
    # bytes wide, so the cut lands inside one: the split half is discarded
    # rather than surfacing as a replacement character the original never had.
    text = "a" * (MESSAGE_LIMIT_BYTES - 1) + "€" + "tail"
    diagnostic = diagnostic_for(ValueError(text))
    assert diagnostic.message_truncated
    assert diagnostic.message == "a" * (MESSAGE_LIMIT_BYTES - 1)
    assert "�" not in diagnostic.message


def test_a_message_carrying_lone_surrogates_is_still_projected() -> None:
    # A `str` Python admits and UTF-8 does not. Encoding replaces it rather than
    # refusing, because a diagnostic that raised while projecting a message
    # would replace the failure the caller came for.
    diagnostic = diagnostic_for(ValueError("before\ud800after"))
    assert not diagnostic.message_truncated
    assert "before" in diagnostic.message


def test_a_stack_beyond_its_ceiling_is_cut_and_flagged() -> None:
    diagnostic = diagnostic_for(_raised(ValueError("x" * (STACK_LIMIT_BYTES + 1000))))
    assert diagnostic.stack_truncated
    assert len(diagnostic.stack.encode("utf-8")) <= STACK_LIMIT_BYTES


def test_a_database_failure_copies_the_category_and_native_code_unchanged() -> None:
    error = DatabaseError(category="deadlock", native_code="40P01", message="deadlock detected")
    diagnostic = database_diagnostic_for(_raised(error))
    assert (diagnostic.category, diagnostic.native_code) == ("deadlock", "40P01")
    assert diagnostic.failure.message == str(error)


def test_a_non_database_failure_escaping_the_port_classifies_as_neither() -> None:
    # No classification of it exists to copy, and inventing one would put a
    # category on a failure `m-db-error` never judged.
    diagnostic = database_diagnostic_for(_raised(ValueError("driver blew up")))
    assert (diagnostic.category, diagnostic.native_code) == (None, None)


def test_a_diagnostic_holds_no_reference_to_the_exception_it_projected() -> None:
    # A built-in exception supports no weak reference, so liveness is proven
    # against a subclass that does — the projection is the same either way.
    error = _raised(_Coded("bad"))
    diagnostic = diagnostic_for(error)
    reference = weakref.ref(error)
    del error
    gc.collect()
    assert reference() is None
    assert isinstance(diagnostic, FailureDiagnostic)
    assert diagnostic.message == "bad"
    assert "_Coded: bad" in diagnostic.stack
