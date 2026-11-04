# Release account setup

[`configuration.json`](configuration.json) owns the repository, workflow,
environment protections and production project names used by setup/preflight.
Apply GitHub configuration with:

```sh
python languages/python/tools/release_setup.py --apply
```

The authenticated GitHub user needs repository administration. Production requires
Dave as its sole required reviewer, allows him to approve his own runs, disables
administrator bypass, and accepts only `main`. TestPyPI permits candidate branches
under `release/` as well as `main`. Preflight verifies these rules before use.
This configuration command never approves deployments or publishes packages.

## New-project ownership bootstrap

Sign in as Dave independently on [PyPI](https://pypi.org/manage/projects/) and
[TestPyPI](https://test.pypi.org/manage/projects/), verify email and configure 2FA.
For an existing project, verify Dave's **Owner** role and register its normal
trusted publisher under **Manage → Publishing**. Raise an ownership conflict;
do not rename a distribution or assume a public name listing proves ownership.

For new projects, use one pending publisher at a time. PyPI's pending-publisher
identity is unique on the GitHub owner, repository, workflow and environment;
registering the same identity for a second pending project is rejected. This
restriction differs from normal publishers, which can serve several projects.
See the [upstream explanation](https://github.com/pypi/warehouse/issues/20006#issuecomment-4424570615).

1. Add one pending publisher in
   [PyPI publishing settings](https://pypi.org/manage/account/publishing/) or
   [TestPyPI publishing settings](https://test.pypi.org/manage/account/publishing/).
   Begin with `parallax-core` and use the following fields.
2. Dispatch `release.yml` with operation `bootstrap`, the selected index and that
   project name. The setup-only job exchanges GitHub OIDC credentials, discards
   the temporary upload token, and uploads **no distribution files**. Warehouse
   creates the project and converts its pending publisher during this exchange,
   before any upload. The job verifies the expected empty project appears.
3. Check the project in your index account and confirm Dave has the **Owner**
   role and the expected trusted publisher. A public listing alone is not proof.
4. Once the pending entry is consumed, register the next configured project with
   the same GitHub fields and repeat. Finish every configured production project
   on both indexes. No dummy releases or changed version numbers are needed.

| Field | Value |
|---|---|
| GitHub owner | `davidsunglee` |
| Repository | `parallax` |
| Workflow filename | `release.yml` |
| Environment on PyPI | `pypi` |
| Environment on TestPyPI | `testpypi` |
| Project name | The one project being bootstrapped |

For example, after adding the TestPyPI pending entry:

```sh
gh workflow run release.yml --ref release/your-candidate \
  -f operation=bootstrap -f bootstrap-index=testpypi \
  -f bootstrap-project=parallax-core
```

The PyPI environment accepts only `main`, so the reviewed release infrastructure
must land before PyPI bootstrap runs. Its protected-environment approval grants
access for the setup-only job, which uploads no files; it is separate from
approval of production publication. Use `--ref main` and `bootstrap-index=pypi`
for that setup. The later release operation still requires Dave's explicit
approval after complete validation and TestPyPI rehearsal.

A missing listing or pending publisher establishes neither ownership nor a name
reservation. If the expected project already exists, the bootstrap tool stops
for owner/publisher verification instead of assuming it owns the name. Retain the
non-secret bootstrap evidence and confirm the actual Owner role in the account.
No API token or password is needed in chat or repository configuration.

The setup-only path follows
[Warehouse's pending conversion](https://github.com/pypi/warehouse/blob/main/warehouse/oidc/views.py)
and [OIDC exchange](https://docs.pypi.org/trusted-publishers/internals/).
See [the release guide](../../languages/python/docs/releasing.md) for publication
and recovery. GitHub
[environment protections](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments)
provide the approval gate.
