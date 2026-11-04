# Validated adapter wheels

The reusable [wheel workflow](../../../.github/workflows/wheels.yml) builds the
[declared native targets](../tools/wheel_targets.json) for the Python minors
selected from workspace metadata by `interpreter_matrix.supported_minors`.
The ordinary CI workflow calls it for relevant pull requests and main pushes;
[wheel relevance](../tools/wheel_relevance.py) owns the exact input paths.
It covers build metadata, Python and psycopg constraints and lockfiles, native
loader sources and conversion/loading dependencies, wheel validation tests and
tooling, and their workflows. Unrelated Python source changes do not run it.
An unknown comparison base runs the matrix. The
[refresh workflow](../../../.github/workflows/wheel-refresh.yml) calls the same
path weekly and on demand. Each run resolves the newest stable PostgreSQL 18.x
from PostgreSQL's release feed, checks the required floor, and verifies the exact
server version. Driver installation resolves the newest psycopg allowed by the
candidate wheel's dependency metadata.

## Build and validation

Run on the native target runner with its CPython minor, Docker on Linux,
Homebrew on ARM macOS, a C compiler on Intel macOS, and the Windows C build
toolchain on Windows. Intel macOS provisions PostgreSQL from the exact release
source with its published checksum; Windows uses the published EDB archive.
For example, from the repository root on native Linux ARM:

```bash
python languages/python/tools/wheel_build.py --target manylinux_2_28-aarch64 \
  --python 3.15 --postgres-version 18.6 \
  --output languages/python/reports/wheel-cell
```

Use `--newest-postgres` to select the version for a new run, rather than copying
an old invocation's version. `--matrix` emits the workflow matrix. The workflow
builds shared companion wheels and the six production sdists once, supplying
them through `--companions` and `--sdists`; standalone builds prepare both. Build and repair
run through cibuildwheel. Linux validation runs in the same policy image on the
native host; macOS and Windows validate on the native runner.

Validation can also consume an existing repaired wheel, without rebuilding it:

```bash
PARALLAX_WHEEL_DSN=postgresql://postgres@127.0.0.1:55432/postgres \
python languages/python/tools/validate_wheel.py \
  --wheel /absolute/path/to/candidate.whl --companions /absolute/path/to/companions \
  --postgres-version 18.6 --output languages/python/reports/wheel-validation
```

The server must be disposable and the login must be an administrator: the
existing tests create conformance roles and reset tables. Validation installs
explicit wheel paths into two fresh environments. Each run checks installed
bytes and loaded module origins against the supplied wheels, selects the
driver explicitly, builds psycopg-c from source against system libpq, and runs
the existing compiled-loader differential, refusal, timestamp-delivery and
open-bound tests. Missing database infrastructure, wrong server versions,
skips, and empty test results fail. The normal workspace test fixture and its
timing instrumentation remain in use. Every cell also builds all six production
wheels from the exact shared sdists with isolated builds and no wheel cache,
then installs those wheels in fresh environments and runs the same two-driver
validation. Each supplied distribution is imported and its installed package
files are checked against its candidate wheel. Source builds run inside the
same native policy environment; they need a C compiler and Cython (resolved from
the sdist build requirements). Their wheels are proof artifacts, not publication
replacements.

## Artifact handoff

A release workflow can call `wheels.yml` with `source-ref` fixed to its source
commit and read the workflow's `artifact` output. Download that artifact from
the same run: it contains the exact validated adapter wheels, companion wheels
under `companions/`, the six production sdists under `sdists/`, and `manifest.json` with source/run/attempt identities,
filenames, SHA-256 hashes, driver observations and results. Each target
additionally binds its `source_install` proof to the retained sdist identities,
source-built wheel identities, both driver results and build/validation timing. The companion
`parallax-conformance` wheel is development tooling used by the tests and must
never be published. This path performs no publication.

Verify the manifest and hashes before consuming artifacts. Rebuilt or changed
bytes need validation again. Artifacts expire under the workflow's retention
settings; a release owner must retain the validated set as release evidence.
Per-target artifacts retain available build, database, installation and test
logs, JUnit, and test timing streams on both success and failure. The aggregate
verdict fails if any declared target or driver proof is absent or unsuccessful.

## Timings

Each target records setup (tool installation, PostgreSQL provisioning and
companion preparation), cibuildwheel build/repair, and each driver's clean
installation and validation. Setup excludes checkout and tool setup actions;
the GitHub job's runner time includes those actions and artifact transfer.
The separate source-install stage records source build duration and each
driver installation/validation duration in addition to its total elapsed time.
Linux setup includes building system libpq; its log is retained separately.
The manifest also retains GitHub job queue and execution times. Queue delay is
unknown if the API supplies no job creation timestamp; workflow creation is
not substituted for dependent-job admission.

The in-workflow summary labels elapsed and aggregate runner time as observed,
since its own job and other jobs may still be running. After completion, refresh
the same summary with the tool's `--jobs` and `--run` JSON inputs, using GitHub's
exact attempt records. Completed workflow elapsed is creation to completion;
execution elapsed starts at `run_started_at`. Aggregate runner time sums job
execution durations, which overlap and cannot be read as workflow wall time.
Keep full coverage when comparing timings; scope changes require a separate
decision.
