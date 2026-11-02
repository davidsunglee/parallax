# AWS test environment

This package defines the two stacks the Aurora cloud suite depends on:

- `ParallaxCiEnvironmentStack`, the private environment the suite runs
  against: a VPC whose private subnets reach the internet through one NAT
  instance, an Aurora PostgreSQL Serverless v2 cluster with one writer and one
  reader, and an ephemeral CodeBuild runner for GitHub Actions jobs. Protected
  CI deploys it.
- `ParallaxCiAccessStack`, the trust path CI deploys through: the
  `parallax-ci-deploy` role, the bounded policy CloudFormation executes the
  environment stack with, and the permissions boundary every role the
  environment creates carries. A maintainer deploys it; CI never can.

[`cdk.json`](cdk.json) holds the deployment's account, Region, zones, NAT
instance type, and Aurora capacity under `parallax:environment`, and the
approved rollout inputs under `parallax:rollout`: the repository and its
protected environment, the existing GitHub OIDC provider and CodeConnections
connection the stacks reuse, the bootstrap qualifier, and who owns the
spending guardrail. Both stacks refuse a configuration that cannot describe a
deployable environment.

## Trust path

```text
aws-deploy environment (main only, required reviewer)
└── GitHub OIDC token, subject repo:davidsunglee/parallax:environment:aws-deploy
    └── parallax-ci-deploy                        assumes nothing else; changes nothing itself
        └── cdk-parallaxci-deploy / file-publishing roles
            └── ParallaxCiEnvironmentStack only   never the access or bootstrap stack
                └── cdk-parallaxci-cfn-exec-role  bounded policy + parallax-ci-boundary
```

The `ParallaxCiBootstrap` stack is the CDK bootstrap with its template
narrowed by [`tools/bootstrap-template.ts`](tools/bootstrap-template.ts) from
the pinned CLI's own: only `parallax-ci-deploy` may assume its roles, its
deploy role may change and never delete the environment stack alone, and its
execution role always holds the bounded policy and boundary rather than
administrator access. Its file assets are encrypted with the AWS managed S3
key, which every bootstrap passes explicitly so a re-bootstrap never creates a
customer key; any other key is drift. A CLI upgrade that changes the default
template fails that narrowing until it is reviewed again.

The runner connects to the cluster only as `parallax_conformance_login`
through IAM, and reads only the published record: it holds no master secret,
no Data API, and no deploy access.

## Role bootstrap

The conformance login and its roles are converged by
[`src/role-bootstrap-handler/index.mts`](src/role-bootstrap-handler/index.mts),
a Lambda function in the VPC's private subnets serving the stack's
role-bootstrap custom resource on a pinned Node.js runtime. On every deployment
it signs in to the writer as the cluster's master user over certificate-verified
TLS and runs the statement in [`src/role-bootstrap.ts`](src/role-bootstrap.ts),
waiting out an unreachable or resuming cluster within its timeout and failing
at once on any other error. It then reads the converged roles, memberships,
default role, and control-database owner back and fails unless they are the
expected ones. Deleting the resource changes nothing in the database.

The master user signs in with an IAM token, which the handler signs itself.
The first run makes the master a member of the IAM-authenticated login, and so
of `rds_iam`, after which PostgreSQL routes every master sign-in to IAM
authentication; only that first run can still use the master password from its
secret. A maintainer who needs the master reaches it the same way, with an IAM
token from inside the VPC. The cluster has no Data API, which would offer only
the password.

The build compiles the handler to `index.mjs` and synthesis copies beside it the
parts of the dependency-free postgres.js driver the runtime loads; that is the
only form a deployment ships, and the assembly check refuses an asset that
carries TypeScript instead.

## What it publishes

After the conformance roles are bootstrapped, the environment stack publishes
one `TestEnvironment` record as the SSM parameter
`/parallax/ci/aws/test-environment`.
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
Amazon Linux 2023 arm64 image ID committed as `natInstanceImage` in
[`deploy-inputs.json`](deploy-inputs.json). A deploy refuses to run until one
is committed; the preflight names the newest image to review. The instance is
replaced, and patched, only when a reviewed change names a new image.

Each deploy also supplies the commit it deploys as the `DeployedRevision`
parameter. A new revision runs the role bootstrap again, so every deployment
re-proves that the roles converge. Synthesis looks nothing up: everything else
it needs is committed.

## Setting up and checking the rollout

[`tools/rollout.ts`](tools/rollout.ts) checks and sets up the rollout. No
verification gate runs it. With no command it is a read-only preflight that
reports every check as verified, pending (with the step that supplies it),
drift, unchecked, or for a human to confirm, then lists what only the
protected deployment and the cloud run can prove:

```bash
node aws/tools/rollout.ts preflight
```

Run it from `infra/`, as a maintainer in a human-controlled session such as
CloudShell, with `gh` authenticated as a repository administrator. Each setup
step changes something, so each needs its own authorization and the reviewed,
unmodified `main` revision, refuses on drift, and verifies its result:

```bash
git fetch origin
node aws/tools/rollout.ts apply access-stack    --authorize access-stack    --revision "$(git rev-parse HEAD)"
node aws/tools/rollout.ts apply bootstrap       --authorize bootstrap       --revision "$(git rev-parse HEAD)"
node aws/tools/rollout.ts apply github-settings --authorize github-settings --revision "$(git rev-parse HEAD)"
node aws/tools/rollout.ts apply settings-token  --authorize settings-token  --revision "$(git rev-parse HEAD)" < token
```

`access-stack` comes first, because the bootstrap trusts the role it creates
and attaches the policies it defines. `settings-token` places a fine-grained
token limited to this repository, with read access to Administration and
Actions alone, into `aws-deploy`, the one environment whose jobs can read it;
its value passes from the terminal or a pipe straight to `gh`.
`github-settings` never removes a branch rule it did not add.

## Spending guardrail

With `budget.ownership` `manual`, the account's existing monthly cost budget is
the guardrail, and the preflight requires exactly one, unfiltered, with actual
and forecast email alerts that fire by the time spending reaches its limit.
Moving to a stack-owned budget is a reviewed change to `stack` ownership with a
new name: the access stack creates it only beside a manual guardrail still in
force, so spending stays guarded, and a maintainer retires the manual budget
only after the new one's recipients are verified. A budget of the
configured name outside the stack is drift, never something to import.
Budgets alert; nothing caps spending.

## Deploying

[`infra-deploy.yml`](../../.github/workflows/infra-deploy.yml) deploys the
environment stack from `main`, on a push touching its inputs or on dispatch,
after the `aws-deploy` reviewer approves. It verifies the repository's
protections, synthesizes without credentials, verifies the account and the
Aurora offering as the deploy role, deploys, and records the deployed
revision, stack, role bootstrap, record, and runner in the run summary. The
record fails unless the role bootstrap ran for this revision and read back the
converged roles.
A deployment never rolls back on failure: the stack keeps what it created, in
`CREATE_FAILED` or `UPDATE_FAILED`, and the next deployment resumes at the
failed resource. A rollback could not delete the deletion-protected cluster.
A change that replaces a resource still deploys with rollback, which the CLI
requires; if a stack is already failed when such a change arrives, the CLI
rolls it back first, and a failed first creation then leaves it in
`ROLLBACK_FAILED` for a maintainer to delete.

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
