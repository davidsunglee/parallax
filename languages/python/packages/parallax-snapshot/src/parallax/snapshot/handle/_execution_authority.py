from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from parallax.core.db_port import (
    ConnectionContextSource,
    DatabaseRuntime,
    InvalidAuthorizationError,
)
from parallax.core.unit_work import DatabaseLoginActor, SubjectActor

__all__ = [
    "ExecutionCapture",
    "InvalidPrincipalError",
    "LoginExecution",
    "Principal",
    "PrincipalExecution",
    "capture_database_login",
    "capture_principal",
    "same_execution",
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
class PrincipalExecution:
    actor: SubjectActor
    authorization: object
    source: ConnectionContextSource


@dataclass(frozen=True, slots=True, eq=False)
class LoginExecution:
    actor: DatabaseLoginActor
    source: ConnectionContextSource


type ExecutionCapture = PrincipalExecution | LoginExecution


def capture_principal[Authorization](
    runtime: DatabaseRuntime[Authorization], principal: Principal[Authorization]
) -> PrincipalExecution:
    subject = principal.subject
    try:
        actor = SubjectActor(subject)
    except ValueError as error:
        raise InvalidPrincipalError(str(error)) from error

    authorization = principal.database_authorization
    try:
        source = runtime.principal_execution(authorization)
    except InvalidAuthorizationError as error:
        raise InvalidPrincipalError(str(error)) from error
    return PrincipalExecution(actor, authorization, source)


def capture_database_login[Authorization](
    runtime: DatabaseRuntime[Authorization],
) -> LoginExecution:
    return LoginExecution(DatabaseLoginActor(runtime.login_identity), runtime.login_execution())


def same_execution(left: ExecutionCapture, right: ExecutionCapture) -> bool:
    match left, right:
        case LoginExecution(), LoginExecution():
            return True
        case PrincipalExecution(), PrincipalExecution():
            return left.actor == right.actor and left.authorization == right.authorization
        case _:
            return False
