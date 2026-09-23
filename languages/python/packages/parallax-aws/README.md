# parallax-aws

Parallax's AWS credential providers: the sole declarer of `botocore`. See
`languages/python/spec/python.md`.

## Authenticating an RDS login with IAM

`RdsIamCredentials` is a `CredentialSource`. It produces the IAM token that
authenticates a database login, and an adapter consumes it — this package
imports no adapter of its own, so it installs beside whichever one a deployment
selected. Install `parallax-postgres` alongside it for the Postgres one.

```python
from parallax.aws import RdsIamCredentials
from parallax.postgres import PoolOptions, PostgresAdapter
from parallax.snapshot import connect

endpoint = "orders.cluster-abc.us-east-1.rds.amazonaws.com"
adapter = PostgresAdapter(
    f"postgresql://orders_service@{endpoint}:5432/orders?sslmode=require",
    credentials=RdsIamCredentials(
        host=endpoint, port=5432, user="orders_service", region="us-east-1"
    ),
    pool=PoolOptions(min_size=2, max_size=20),
)
with connect(adapter, model) as root:
    ...
```

IAM database authentication is identical on RDS Postgres and Aurora Postgres.
For a cluster, the endpoint above is the one the application connects through:
a token proves nothing at an endpoint it was not signed for.

Three things outside Parallax have to agree with that line:

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
free of I/O.

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
