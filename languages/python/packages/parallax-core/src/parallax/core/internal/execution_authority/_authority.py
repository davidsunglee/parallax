from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Protocol

from parallax.core._execution._unit_work.strategy import DatabaseLoginActor, SubjectActor
from parallax.core.internal.base import UsageError
from parallax.core.internal.db_port import (
    AUTHORIZATION_INVALID,
    ConnectionContextSource,
    DatabaseRuntime,
)

__all__ = [
    "PRINCIPAL_INVALID",
    "ExecutionAuthority",
    "Principal",
    "capture_database_login",
    "capture_principal",
    "same_authority",
]


class Principal[Authorization](Protocol):
    """Application-supplied subject and database authorization."""

    @property
    def subject(self) -> str: ...

    @property
    def database_authorization(self) -> Authorization: ...


PRINCIPAL_INVALID: Final = "principal-invalid"
"""A Principal cannot be captured for the selected database runtime: its subject
is no Subject Actor, or the runtime refused its authorization's shape, which is
the refusal's ``__cause__``."""


@dataclass(frozen=True, slots=True, eq=False)
class PrincipalAuthority:
    actor: SubjectActor
    authorization: object
    source: ConnectionContextSource


@dataclass(frozen=True, slots=True, eq=False)
class LoginAuthority:
    actor: DatabaseLoginActor
    source: ConnectionContextSource


type ExecutionAuthority = PrincipalAuthority | LoginAuthority


def capture_principal[Authorization](
    runtime: DatabaseRuntime[Authorization], principal: Principal[Authorization]
) -> PrincipalAuthority:
    subject = principal.subject
    try:
        actor = SubjectActor(subject)
    except ValueError as error:
        raise UsageError(PRINCIPAL_INVALID, str(error)) from error

    authorization = principal.database_authorization
    try:
        source = runtime.principal_source(authorization)
    except UsageError as error:
        if error.code != AUTHORIZATION_INVALID:
            raise
        raise UsageError(PRINCIPAL_INVALID, error.args[1]) from error
    return PrincipalAuthority(actor, authorization, source)


def capture_database_login[Authorization](
    runtime: DatabaseRuntime[Authorization],
) -> LoginAuthority:
    return LoginAuthority(DatabaseLoginActor(runtime.login_identity), runtime.login_source())


def same_authority(left: ExecutionAuthority, right: ExecutionAuthority) -> bool:
    match left, right:
        case LoginAuthority(), LoginAuthority():
            return True
        case PrincipalAuthority(), PrincipalAuthority():
            return left.actor == right.actor and left.authorization == right.authorization
        case _:
            return False
