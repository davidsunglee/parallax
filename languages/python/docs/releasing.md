# Releasing Parallax

The [release workflow](../../../.github/workflows/release.yml) owns preparation,
TestPyPI rehearsal and production publication. It reuses the
[validated wheel workflow](../../../.github/workflows/wheels.yml) and its full
native platform matrix. The [release setup](../../../.github/release/README.md)
contains the exact index publisher and GitHub environment configuration.

## Compatibility and maintenance

All production distributions release together. Their metadata requires exact
matching first-party versions, including optional first-party dependencies.
Applications install the distributions they need and their dependencies; they
need not install every production distribution. Mixed first-party release
versions are unsupported. Conformance remains development-only and unpublished.

`0.1.0` is a normal production install candidate, with no alpha or beta packaging
suffix. Patch releases within a minor line remain backward-compatible.
Subsequent pre-1.0 minor releases may introduce explicitly documented breaking
changes, accompanied by migration guidance. Before 1.0, only the newest minor
line is maintained: after `0.2.0`, ongoing fixes normally ship as `0.2.x`.
An older-line backport requires an explicit case-by-case decision.

The initial public surface is the implemented binding: public signatures and
exports, [error contracts](../spec/execution.md#transactions-and-failure-boundaries)
and [temporal spelling](../spec/queries-and-results.md), with their
[API snapshot](../tests/api/public_api.json) and executable examples. A future
release must preserve that contract within a minor line. A changed public
contract belongs in its binding owner and release notes with migration guidance.

Python and dependency support belong to package metadata; platform support
belongs to the [wheel targets](../tools/wheel_targets.json). PostgreSQL support
belongs to the [binding contract](../spec/execution.md#supported-postgresql),
which links its package configuration. The main database suite tests the floor
and newest supported release, collapsing identical versions; scheduled checks
resolve newer supported PostgreSQL releases and retain exact tested versions.
The wheel matrix uses the newest tested version without multiplying platform
cells by database versions. A new PostgreSQL major needs a separate support
decision.

## Prepare, rehearse and approve

1. Choose a source revision whose required CI checks pass. Prepare one complete
   artifact set through the shared build and validation path. It contains the
   production wheels and sdists; conformance companions are test evidence only.
   Source-install proof builds from the retained sdists on every declared target.
2. Retain the artifact manifest, filenames and SHA-256 hashes tied to that source,
   successful validation results, logs, provenance and timing summaries. Wheel
   timings distinguish setup, build/repair and both driver checks; queue delay,
   workflow elapsed time and aggregate runner time have different meanings, as
   [wheel validation](wheel-validation.md#timings) explains.
3. Rehearse the complete set on TestPyPI for every release. Download the uploaded
   files, compare their identities against the manifest, and smoke-test an
   installation using those downloads. A successful upload alone is insufficient.
4. Present Dave with the concrete source revision, manifest and validation and
   rehearsal evidence. Dave must explicitly approve every production publication,
   including one he initiated. The protected `pypi` environment is the approval
   gate; preparation is not approval.
5. Publish exactly the validated and rehearsed bytes to PyPI, without rebuilding
   or changing versions. Download and reconcile the complete production set
   against the manifest before announcing it or marking the release published.

GitHub trusted publishing supplies short-lived index credentials and publication
attestations bind publisher identity to artifact hashes. Attestations do not
replace test evidence. Retain the release artifact set and provenance durably;
ordinary workflow artifacts expire. Any changed or rebuilt file requires renewed
validation, rehearsal and production approval.

Index names are the distribution names from
[ADR 0006](adr/0006-distributions-share-the-parallax-namespace.md). Neither a
missing index listing nor a pending trusted publisher proves ownership or
reserves a name. Confirm Dave's ownership through the index account and publisher
setup before publication. Do not rename a distribution to bypass an ownership
problem. The shared `parallax` import namespace collides with the unrelated
PyPI distribution `parallax`; do not co-install it.

## Interrupted uploads

Publication is not atomic across files or distributions. Keep the original
validated set and manifest. Reconcile the target index against that manifest:
verify the hashes of every present file and upload only missing identical files.
A conflicting hash or unexpected file requires investigation; do not overwrite a
published file or reuse a filename for different bytes. Re-run the download and
installation verification after the set is complete. A production recovery still
requires Dave's explicit approval through the protected environment.

## Defective releases

Obtain Dave's explicit approval before yanking. Yank the defective version across
all production distributions that were published, using one clear reason that
identifies the affected version and its replacement. Preserve the original
artifacts, hashes and provenance. Yanking discourages ordinary installation but
does not block explicit exact-version installs, so communicate the affected
version and correction to users.

Publish the correction as a new coordinated version through the same validation,
complete TestPyPI rehearsal and production approval process. Do not rebuild or
replace the defective version's files. The newest-minor maintenance policy still
applies when choosing the correction's version.

## Release notes and licences

Update [release notes](releases.md) for each coordinated release, including
breaking changes and migration guidance when applicable. Mark publication only
after index verification succeeds. Each production distribution carries the
Apache-2.0 licence and its attribution notice in both wheel and sdist. Third-party
dependencies retain their own licences in their separate distributions.

## Workflow commands and retained evidence

For a new release, dispatch `release.yml` on `main` without a candidate run ID.
Preparation builds once, waits for successful source CI and checks retained
PostgreSQL observations. The complete TestPyPI upload and download/install proof
then precede the protected production job. A push under `release/` can rehearse
a candidate before merge; it never enters the production job. Production requires
its original source revision to be an ancestor of `main`, or its entire repository
tree to match a commit reachable from `main` after a squash or rebase merge. The
workflow fetches that original commit by SHA, so branch deletion does not remove
the local proof input. This preserves recovery after later commits advance
`main`. The original source
revision, manifest and rehearsed artifact bytes remain unchanged in either case.

Each candidate has a durable draft GitHub release named
`release-candidate-RUN_ID-ATTEMPT`. Its `candidate.tar.gz` retains the original
25 production files, release and wheel manifests, source CI and database proof,
native validation records and timing evidence. The archive has a GitHub build
provenance attestation and retained signature bundle. TestPyPI and production
verification archives are added as those stages succeed. Keep these evidence
drafts after the public release; workflow artifact expiration must not erase
release evidence.

To recover an interrupted upload, dispatch the same `release.yml` on `main`,
setting `candidate-run-id` and `candidate-attempt` to the **original build run**
that archived the candidate. The workflow verifies the archive's attestation,
its equality to that build run's source SHA, its manifest and retained source
CI. Recovery rechecks the captured run/check results and the hashes and complete
PostgreSQL observations in the archived evidence; it does not download expiring
CI artifacts again. It rehearses the exact bytes again, then requests Dave's
production approval.
It does not rebuild. Always reference the original build run when recovering,
including after a recovery run itself is interrupted. Recovery works after
workflow artifacts expire because it downloads the durable draft release asset.
Use this recovery path rather than rerunning individual failed jobs with a new
attempt number.

For read-only local inspection of a recovered `candidate/` directory:

```sh
python languages/python/tools/release_artifacts.py verify --bundle candidate
python languages/python/tools/release_artifacts.py reconcile \
  --bundle candidate --index pypi --output reconciliation
```

Reconciliation downloads and hashes every already published file. The generated
`missing/` directory contains only the exact retained files still absent.
Conflicting, unexpected or already yanked files stop the process. Uploads use
trusted publishing with attestations and never blindly skip an existing file.

Prepare a coordinated yank plan without changing the index:

```sh
python languages/python/tools/release_yank.py --bundle candidate \
  --reason 'Defective VERSION; use REPLACEMENT: reason' --output yank-plan.json
```

Present the plan to Dave for explicit approval. Once approved, Dave uses each
published project's owner URL in the plan to yank that version with the same
reason. Do not delete the release or its files. Verify the coordinated result
and retain it with the candidate evidence:

```sh
python languages/python/tools/release_yank.py --bundle candidate \
  --reason 'Defective VERSION; use REPLACEMENT: reason' \
  --verify --output yank-result.json
```

This owner action is separate from trusted uploads. The tooling prepares all
six projects together and fails verification until every published file is
yanked with the approved reason; unpublished projects need no action.
