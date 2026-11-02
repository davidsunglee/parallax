# AWS test environment

This package defines `ParallaxCiEnvironmentStack`, the private environment the
Aurora cloud suite runs against: a VPC whose private subnets reach the internet
through one NAT instance, and an Aurora PostgreSQL Serverless v2 cluster with one
writer and one reader. [`cdk.json`](cdk.json) holds the deployment's account,
Region, zones, NAT instance type, and Aurora capacity, and the stack refuses a
configuration that cannot describe a deployable environment.

## What it publishes

After the conformance roles are bootstrapped, the stack publishes one
`TestEnvironment` record as the SSM parameter `/parallax/ci/aws/test-environment`.
[`test-environment.schema.json`](test-environment.schema.json) is its authored
contract; the TypeScript type in `src/generated/` is derived from it, and the
Python suite validates a deployed record against the schema version the record
names.

A change to the record's shape bumps its `schema` version by one. The previous
version's schema stays beside the new one, as `test-environment.v<N>.schema.json`,
until the new version is deployed, so the suite reads both while a rollout is in
flight.

## Deploy inputs

The NAT instance's image is the `NatInstanceImage` deployment parameter, an
Amazon Linux 2023 arm64 image ID. CloudFormation keeps the previous value on a
deploy that supplies none, so the instance is replaced, and patched, only when a
reviewed deploy names a new image. Synthesis looks nothing up: everything else it
needs is committed.

## Working on it

From the repository root, after `pnpm install`:

```bash
just infra-check    # every infrastructure gate
just infra-build    # compile, then synthesize into infra/aws/cdk.out
just infra-format   # apply formatting
```

Every infrastructure command runs with AWS credentials, profiles, and the
instance metadata service out of reach, so none of them can reach an account.
After editing the schema, regenerate its type from `infra/`:

```bash
node tools/check-generated.ts --write
```
