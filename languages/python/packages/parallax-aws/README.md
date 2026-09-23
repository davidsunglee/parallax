# parallax-aws

Parallax's AWS credential providers: the sole declarer of `botocore`. See
`languages/python/spec/python.md`.

## Authenticating an RDS Postgres login with IAM

Install the `postgres` extra — `pip install parallax-aws[postgres]` — and the
whole story is one call:

```python
from parallax.aws.postgres import rds_postgres
from parallax.postgres import PoolOptions
from parallax.snapshot import connect

adapter = rds_postgres(
    host="orders.cluster-abc.us-east-1.rds.amazonaws.com",
    user="orders_service",
    database="orders",
    region="us-east-1",
    pool=PoolOptions(min_size=2, max_size=20),
)
with connect(adapter, model) as root:
    ...
```

What comes back is the ordinary `PostgresAdapter`, configured — nothing sits
between the application and the adapter at runtime, and nothing was resolved or
opened to build it. The factory is where three things are stated once, so no
deployment has to remember them: the connection is encrypted, the token is
signed for the host, port and user the connection then uses, and the endpoint to
sign for is the one the application connects through.

`params` keeps the rest of libpq's grammar open — `application_name`,
`options`, `connect_timeout`, and `sslrootcert` with an `sslmode` of
`verify-ca` or `verify-full`, which is what AWS's own certificate bundle is for.
It may strengthen the TLS requirement and may not weaken it, it may not ask for
the GSS encryption libpq would carry the login over in TLS's place, and it may
not restate `host`, `port`, `user`, `dbname` or `password`: a value the token
was not signed for authenticates nothing. `host` names one endpoint for the same
reason — libpq reads a comma-separated list of them, and a token signed for the
list authenticates at none of its members. Every refusal is fixed text, because
`params` is a place other secrets live.

## The source on its own

`RdsIamCredentials` is a `CredentialSource`, and the part of this package that
imports no adapter. An application assembling its own connection string uses it
directly, and a deployment on another engine installs this package without the
`postgres` extra and gets no database driver with it.

```python
from parallax.aws import RdsIamCredentials
from parallax.postgres import PostgresAdapter

endpoint = "orders.cluster-abc.us-east-1.rds.amazonaws.com"
adapter = PostgresAdapter(
    f"postgresql://orders_service@{endpoint}:5432/orders?sslmode=require",
    credentials=RdsIamCredentials(
        host=endpoint, port=5432, user="orders_service", region="us-east-1"
    ),
)
```

IAM database authentication is identical on RDS Postgres and Aurora Postgres.
For a cluster, the endpoint above is the one the application connects through:
a token proves nothing at an endpoint it was not signed for. Written this way,
the TLS requirement the factory would have stated is the caller's to spell.

## What has to agree outside Parallax

- the database login exists and holds the IAM role —
  `CREATE USER orders_service; GRANT rds_iam TO orders_service;`;
- the AWS identity the process runs as is allowed `rds-db:connect` on
  `arn:aws:rds-db:<region>:<account>:dbuser:<resource-id>/orders_service`;
- the connection is encrypted. An IAM token is a password, so it travels over
  TLS: `sslmode=require` at least, and `verify-full` with AWS's certificate
  bundle where the deployment can supply one.

## What resolving a token costs

Signing is local — no AWS endpoint is reached to produce a token. What can block
is botocore finding or refreshing the AWS credentials it signs with: the
environment, a profile, an ECS task role, IMDSv2, IRSA, or SSO. The record
bounds that I/O, because the seam requires a source to, and it creates its RDS
client on first use rather than at construction, so composing an adapter stays
free of I/O. A profile's `credential_process` is bounded too, by the record
rather than by botocore, which waits on that command without a timeout: a helper
that has not answered within a few seconds is killed and the attempt fails as a
refusal. A helper that legitimately needs longer — one waiting on a person —
belongs behind a session of your own, which is used exactly as given.

There is no token cache and no refresh thread. A connection the server has
already accepted is never disturbed by its token ageing out, and when a source
is asked for a new one is the port's rule rather than this package's — see
`core/spec/m-db-port.md`, "Configuration carries where, and a Credential Source
carries how".

```python
# a session of your own — a profile, static keys, a test double; used as given
RdsIamCredentials(host=endpoint, port=5432, user="app", region="us-east-1", session=session)
```

## When a token cannot be produced

Every botocore or signing failure surfaces as
`CredentialResolutionError: RDS IAM token could not be generated`, with the
native error chained beneath it. The message is fixed text so that nothing a
provider says can leak through it; what the adapter then reports — a startup
that fails naming the refusal, or an acquisition failing with
`reason="credentials_refused"` — is in
[PostgreSQL connection lifecycle](https://github.com/davidsunglee/parallax/blob/main/languages/python/docs/postgresql-lifecycle.md)
under "Where the password lives".
