"""Parallax AWS credential providers (``parallax-aws``).

The sole botocore declarer, and a leaf beside the adapters rather than a layer
above them: it produces a :class:`~parallax.core.db_port.CredentialSource` a
composition root hands to whichever adapter it selected, and imports no adapter
itself. Exports :class:`RdsIamCredentials`, which authenticates an RDS or Aurora
Postgres login with an IAM token.
"""

from __future__ import annotations

from parallax.aws._rds import RdsIamCredentials

__all__ = ["RdsIamCredentials"]
