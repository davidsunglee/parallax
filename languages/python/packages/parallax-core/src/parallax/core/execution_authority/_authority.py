from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from parallax.core._execution._unit_work.strategy import DatabaseLoginActor, SubjectActor
from parallax.core.db_port import (
    ConnectionContextSource,
    DatabaseRuntime,
    InvalidAuthorizationError,
)

__all__ = [
    "ExecutionAuthority",
    "InvalidPrincipalError",
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


class InvalidPrincipalError(ValueError):
    """A Principal cannot be captured for the selected database runtime."""


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
        raise InvalidPrincipalError(str(error)) from error

    authorization = principal.database_authorization
    try:
        source = runtime.principal_source(authorization)
    except InvalidAuthorizationError as error:
        raise InvalidPrincipalError(str(error)) from error
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
