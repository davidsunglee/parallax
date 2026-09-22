"""The credential seam: one kind, one protocol, one declaration (m-db-port). Docker-free.

What a secret's one home is, that the declaration beside the protocol is not a
source and never could be mistaken for one, and that the credential alias stays
the single member every provider constructs.
"""

from __future__ import annotations

import dataclasses
from typing import get_args

import pytest

from parallax.core.db_port import (
    DRIVER_MANAGED,
    Credential,
    CredentialResolutionError,
    CredentialSource,
    DriverManaged,
    Password,
)


def test_a_password_keeps_its_secret_out_of_its_representation() -> None:
    # A repr is a place values get logged, and this value exists to hold the one
    # thing that must not be.
    credential = Password("hunter2")

    assert "hunter2" not in repr(credential)
    assert credential.secret == "hunter2"


def test_a_password_is_frozen_and_equal_by_value() -> None:
    credential = Password("hunter2")
    with pytest.raises(dataclasses.FrozenInstanceError):
        credential.secret = "other"  # pyright: ignore[reportAttributeAccessIssue] - the frozen record's refusal at runtime is what this proves
    assert credential == Password("hunter2")
    assert credential != Password("other")


def test_a_constant_credential_is_its_own_source() -> None:
    # There is no `StaticPassword` wrapper: an application writes
    # `credentials=Password(...)` and a dynamic source returns `Password(...)`,
    # so both ends of the seam name one type.
    credential = Password("hunter2")

    assert isinstance(credential, CredentialSource)
    assert credential.resolve() is credential


def test_the_credential_alias_has_exactly_the_one_member_today() -> None:
    # A later bearer-token or client-certificate kind widens this alias without
    # renaming anything a provider already constructs, so what is pinned is the
    # alias rather than each use of it.
    assert get_args(Credential.__value__) == ()
    assert Credential.__value__ is Password


def test_the_driver_managed_declaration_is_not_a_source() -> None:
    # It resolves nothing, which is what keeps it out of `Credential` and out of
    # every provider's `resolve`. An adapter recognizes it beside the protocol
    # rather than through it.
    assert not isinstance(DRIVER_MANAGED, CredentialSource)
    assert not hasattr(DRIVER_MANAGED, "resolve")


def test_the_driver_managed_declaration_admits_one_instance() -> None:
    # An adapter recognizes it by identity, so a second construction must be the
    # same object rather than an equal one.
    assert DriverManaged() is DRIVER_MANAGED

    with pytest.raises(TypeError, match="one instance"):
        type("Narrower", (DriverManaged,), {})


def test_a_resolution_refusal_is_an_ordinary_exception_a_provider_can_raise() -> None:
    # Providers live in other distributions, so the type they refuse with is
    # part of this seam rather than of any adapter.
    refusal = CredentialResolutionError("the credential source could not produce a password")

    assert isinstance(refusal, Exception)
    assert str(refusal) == "the credential source could not produce a password"


def test_any_object_that_resolves_is_a_source_without_registering_anything() -> None:
    # Structural recognition is what lets a provider's token source and a test's
    # fake cross the seam with no registration and no base class.
    class Minted:
        def resolve(self) -> Password:
            return Password("minted")

    assert isinstance(Minted(), CredentialSource)
