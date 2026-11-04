# Release account setup

[`configuration.json`](configuration.json) owns the repository, workflow,
environment protections and six project names used by the setup/preflight tool.
Apply GitHub configuration with:

```sh
python languages/python/tools/release_setup.py --apply
```

The authenticated GitHub user needs repository administration. Production requires
Dave as its sole required reviewer, allows him to approve his own runs, disables
administrator bypass, and accepts only `main`. TestPyPI permits candidate branches
under `release/` as well as `main`. A preflight verifies these rules before any
publication. This setup command never approves deployments or publishes packages.

## Index owner action

Sign in as Dave independently on [PyPI](https://pypi.org/manage/projects/) and
[TestPyPI](https://test.pypi.org/manage/projects/). For each project named in the
configuration, verify Dave has the **Owner** role if it exists, then add its
GitHub trusted publisher under **Manage → Publishing**. If it does not exist,
add a pending publisher in
[PyPI publishing settings](https://pypi.org/manage/account/publishing/) or
[TestPyPI publishing settings](https://test.pypi.org/manage/account/publishing/).
Use these exact values:

| Field | Value |
|---|---|
| Owner | `davidsunglee` |
| Repository | `parallax` |
| Workflow filename | `release.yml` |
| Environment on PyPI | `pypi` |
| Environment on TestPyPI | `testpypi` |
| Project name | Each of the six configured names |

Report the account username and confirm the six publishers on each index.
A 404 or pending publisher establishes neither ownership nor a name reservation.
The first successful trusted upload creates the project under the pending
publisher's account; verify Dave's Owner role afterward. If another account owns
a name, stop and resolve ownership; do not rename the distribution.

No API token is needed. Do not send credentials in chat. Production setup is
separate from approval to publish; every production publication still waits for
Dave's protected-environment approval after the complete TestPyPI rehearsal.

See [the release guide](../../languages/python/docs/releases.md) for the release
and recovery procedure. Trusted publisher configuration follows
[PyPI's documentation](https://docs.pypi.org/trusted-publishers/adding-a-publisher/);
GitHub [environment protections](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments)
provide the approval gate.
