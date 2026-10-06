"""Capture and compare runtime readings of the Valid-Time interval workloads.

``capture`` measures selected cells of
``tests/unit/_time_interval_runtime_support.py`` — a flow cell by flow,
interface, layout, and mode, an algorithm cell by algorithm and size, or every
cell — each in a child interpreter of its own (the ``read`` subcommand), and
writes one ``capture.json`` into an output directory that must be new or
empty. A capture keeps every raw sample beside its median, the warm-up and
sample counts, what each window contains and what is composed outside it, the
outcome every run reported, the production subject (commit, a digest of every
production source and the lock, and whether those match the commit), the
measurement-support digest, the environment, the execution seam, and every
flow combination no public lifecycle supports, with its reason. A cell whose
child fails is recorded as failed and the command exits 3.

``compare`` judges a candidate capture against a baseline capture, cell by
cell, and writes ``comparison.json`` into a new or empty output directory.
Before judging any timing it requires the two captures to share the
measurement-support digest, the sampling, the execution seam, and the
environment's implementation, Python version, system, machine, and host — a
capture missing any of these facts, or its production digest, is refused
rather than read — and it requires every cell either capture selected
to be measured in both, its record stating the outcome of a complete run and
its timed windows. Each cell
answers exactly one result:

* ``missing-or-incompatible-evidence`` — the captures are incompatible, the
  cell is absent or failed in either, or a repetition failed or answered a
  capture that does not match the original's support, sampling, environment,
  or production subject;
* ``reproducible-regression`` — repetition established a slowdown;
* ``inconclusive`` — the cell needed repetition that was not requested, or
  repetition reached its round limit without a conclusion;
* ``no-detected-regression`` — the screen raised no suspicion, or repetition
  established that the change stays within baseline-to-baseline variation.

The comparison's own result is the most severe cell result in that order, and
the command exits 0 only when it is ``no-detected-regression``.

The rule
--------
*Screen.* For each cell, with ``r`` the candidate median over the baseline
median, the cell is suspect when ``r`` lies outside ``1 ± INVESTIGATION_TRIGGER``
(a change beyond 5% either way); when either capture's interquartile range
exceeds ``DISPERSION_LIMIT`` of its median (excessive variability); or when the
probability that a candidate sample exceeds a baseline sample (ties counting
half) reaches ``SUPERIORITY_LIMIT`` or falls to ``1 - SUPERIORITY_LIMIT`` (a
smaller shift that is consistent across samples). Two captures are rarely
taken together, and the host's conditions between them shift every cell alike:
a candidate that merely looks faster may be concealing a slowdown, so a shift
in either direction is repeated. Only a cell whose two captures are
indistinguishable raises none of these and is ``no-detected-regression``. The
trigger is a reason to repeat, never an allowance a slowdown may consume.

*Repetition.* A suspect cell is captured again on both supplied worktrees, in
rounds of three captures: odd rounds take baseline, candidate, baseline, and
even rounds candidate, baseline, baseline, so the subject measured first
alternates and every round carries a baseline-to-baseline control. Each
repetition is kept as a capture of its own under the comparison's ``rounds``
directory. For round ``k``, with ``b`` the median of its first baseline
capture, ``c`` its candidate median, and ``b'`` its control median, the change
is ``L_k = ln(c / b)`` and the baseline variation is ``N_k = ln(b' / b)``.

*Conclusion.* Only repeated rounds are judged: the original captures may have
been taken far apart in time, and a host's conditions can spike within
seconds. After at least ``MIN_ROUNDS`` rounds, let ``p`` be the rounds'
sampling resolution, the largest of twice the combined standard error of the
two medians a round's change compares (each the normal approximation
``1.2533 * (IQR / 1.349) / sqrt(n)``, relative to its median). The cell is a
``reproducible-regression`` when every ``L_k`` exceeds both the largest
``|N_k|`` and ``p``: every round's candidate is slower than the largest
baseline-to-baseline change, and by more than the medians can resolve. It is
``no-detected-regression`` when the median ``L_k`` is no larger than the
smallest ``|N_k|``: round for round, the candidate is typically slower than
its baseline by no more than the baseline differs from itself, so one spiked
capture can neither conclude a regression nor excuse one. Otherwise another round is
taken, and a cell still undecided after ``--max-repeat-rounds`` rounds is
``inconclusive``. Repetition never turns uncertainty into success.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import statistics
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal, cast

from interpreter_matrix import CURRENT_MINOR, HASH_SEED, child_command, child_environment

WORKSPACE: Final = Path(__file__).resolve().parents[1]
REPOSITORY: Final = WORKSPACE.parents[1]
SCRIPT: Final = Path(__file__).resolve()
SUPPORT_MODULE: Final = WORKSPACE / "tests" / "unit" / "_time_interval_runtime_support.py"
sys.path.insert(0, str(WORKSPACE))

# `sys.path` gains the workspace above, so this import cannot precede it; that is
# what the E402 suppression records.
from tests.unit import _time_interval_runtime_support as support  # noqa: E402

if Path(support.__file__ or "").resolve() != SUPPORT_MODULE:
    raise ImportError(f"this tool measures over {SUPPORT_MODULE}, but resolved {support.__file__}")

SCHEMA_VERSION: Final = 1
CAPTURE_KIND: Final = "time-interval-runtime-capture"
COMPARISON_KIND: Final = "time-interval-runtime-comparison"
CAPTURE_FILE: Final = "capture.json"
COMPARISON_FILE: Final = "comparison.json"
WARMUPS: Final = 3
MEASURED: Final = 9
NAMESPACE: Final = "time-interval-runtime"
SUPPORT_SOURCES: Final = (
    "tools/time_interval_runtime.py",
    "tools/interpreter_matrix.py",
    "tests/_support/db_port.py",
)
"""The measurement sources beyond the workload module's own digest."""
PRODUCTION_PATHS: Final = ("languages/python/packages", "languages/python/uv.lock")
"""What the production subject consists of, relative to the repository."""
ENVIRONMENT_KEYS: Final = ("implementation", "pythonVersion", "system", "machine", "node")
"""The environment facts two comparable captures must share."""

INVESTIGATION_TRIGGER: Final = 0.05
DISPERSION_LIMIT: Final = 0.10
SUPERIORITY_LIMIT: Final = 0.8
MIN_ROUNDS: Final = 3
DEFAULT_MAX_ROUNDS: Final = 3

type Result = Literal[
    "missing-or-incompatible-evidence",
    "reproducible-regression",
    "inconclusive",
    "no-detected-regression",
]
RESULTS: Final[tuple[Result, ...]] = (
    "missing-or-incompatible-evidence",
    "reproducible-regression",
    "inconclusive",
    "no-detected-regression",
)
"""Every result, most severe first."""
type Subject = Literal["baseline", "candidate"]


class CaptureError(ValueError):
    """A capture or comparison cannot be read or written as asked."""


class SelectionError(ValueError):
    """A selection names no supported cell."""


# --------------------------------------------------------------------------- #
# Identities                                                                    #
# --------------------------------------------------------------------------- #
def _git(repository: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repository), *arguments],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def files_digest(root: Path, paths: Sequence[str]) -> str:
    """One SHA-256 digest over each of ``paths`` — relative to ``root`` — and
    its contents, independent of the order they are named in."""
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256((root / path).read_bytes()).hexdigest().encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def production_identity(repository: Path = REPOSITORY) -> dict[str, object]:
    """The production subject ``repository``'s working tree holds: its commit,
    a digest of every tracked or unignored production file, and whether those
    files match the commit."""
    listed = _git(
        repository,
        "ls-files",
        "-z",
        "--cached",
        "--others",
        "--exclude-standard",
        "--",
        *PRODUCTION_PATHS,
    ).split("\0")
    present = sorted({path for path in listed if path and (repository / path).is_file()})
    status = _git(repository, "status", "--porcelain", "--", *PRODUCTION_PATHS)
    return {
        "repository": str(repository),
        "commit": _git(repository, "rev-parse", "HEAD").strip(),
        "productionDigest": files_digest(repository, present),
        "productionFiles": len(present),
        "productionMatchesCommit": status == "",
    }


def support_identity() -> dict[str, object]:
    """The measurement support this tool runs: its own sources and the
    workload module's digest of everything it measures over."""
    sources = {
        path: hashlib.sha256((WORKSPACE / path).read_bytes()).hexdigest()
        for path in SUPPORT_SOURCES
    }
    workloads = support.support_digest()
    combined = hashlib.sha256(
        json.dumps({"sources": sources, "workloads": workloads}, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return {"digest": combined, "sources": sources, "workloadDigest": workloads}


def environment() -> dict[str, object]:
    return {
        "implementation": platform.python_implementation(),
        "pythonVersion": platform.python_version(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "node": platform.node(),
        "cpuCount": os.cpu_count(),
        "loadAverage": list(os.getloadavg()),
        "executable": sys.executable,
        "childMinor": CURRENT_MINOR,
        "childHashSeed": HASH_SEED,
    }


def sampling() -> dict[str, object]:
    return {
        "warmups": WARMUPS,
        "measured": MEASURED,
        "unit": "us",
        "collectBeforeEachRun": True,
        "interpreterPerCell": True,
    }


# --------------------------------------------------------------------------- #
# Selection                                                                     #
# --------------------------------------------------------------------------- #
def _not_applicable_reason(flow: str, interface: str | None, mode: str | None) -> str | None:
    for entry in support.NOT_APPLICABLE:
        if (
            entry.flow == flow
            and interface in (None, entry.interface)
            and mode in (None, entry.mode)
        ):
            return entry.reason
    return None


def select_flow(
    flow: str, interface: str | None, layout: str | None, mode: str | None
) -> tuple[support.Cell, ...]:
    """The supported flow cells ``flow`` names, narrowed by any axis given."""
    cells = tuple(
        cell
        for cell in support.CELLS
        if isinstance(cell, support.FlowCell)
        and cell.flow == flow
        and interface in (None, cell.interface)
        and layout in (None, cell.layout)
        and mode in (None, cell.mode)
    )
    if not cells:
        reason = _not_applicable_reason(flow, interface, mode)
        detail = f": {reason}" if reason is not None else ""
        raise SelectionError(
            f"{flow} supports no {interface or 'any'} {layout or 'any'} {mode or 'any'} cell"
            f"{detail}"
        )
    return cells


def select_algorithm(algorithm: str, size: int | None) -> tuple[support.Cell, ...]:
    cells = tuple(
        cell
        for cell in support.CELLS
        if isinstance(cell, support.AlgorithmCell)
        and cell.algorithm == algorithm
        and size in (None, cell.size)
    )
    if not cells:
        raise SelectionError(f"{algorithm} has no cell of size {size}; sizes are {support.SIZES}")
    return cells


def selection_arguments(cell: support.Cell) -> list[str]:
    """The ``capture`` arguments selecting exactly ``cell``."""
    if isinstance(cell, support.FlowCell):
        return [
            "--flow",
            cell.flow,
            "--interface",
            cell.interface,
            "--layout",
            cell.layout,
            "--mode",
            cell.mode,
        ]
    return ["--algorithm", cell.algorithm, "--size", str(cell.size)]


# --------------------------------------------------------------------------- #
# Capture                                                                       #
# --------------------------------------------------------------------------- #
type Reader = Callable[[support.Cell], Mapping[str, object] | str]
"""Takes one cell's reading and answers the reading document, or why it is
unavailable."""


def reading_document(cell_id: str, *, warmups: int, measured: int) -> dict[str, object]:
    """One cell measured in this interpreter: what the ``read`` child prints."""
    reading = support.measure(support.cell_named(cell_id), warmups=warmups, measured=measured)
    return {
        "cell": cell_id,
        "samplesUs": list(reading.samples_us),
        "windows": reading.windows,
        "outcome": reading.outcome.document(),
    }


def child_reader(cell: support.Cell) -> Mapping[str, object] | str:
    """``cell``'s reading taken by a child interpreter of its own."""
    arguments = ["read", cell.id, "--warmups", str(WARMUPS), "--measured", str(MEASURED)]
    try:
        completed = subprocess.run(
            child_command(CURRENT_MINOR, SCRIPT, arguments),
            cwd=WORKSPACE,
            env=child_environment(CURRENT_MINOR, NAMESPACE),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as error:
        return f"the child could not be started: {error}"
    if completed.returncode != 0:
        return f"the child exited {completed.returncode}\n{completed.stdout}{completed.stderr}"
    lines = completed.stdout.strip().splitlines()
    try:
        document = json.loads(lines[-1]) if lines else None
    except json.JSONDecodeError as error:
        return f"the child's reading did not decode: {error}"
    if not isinstance(document, Mapping):
        return "the child printed no reading"
    return cast("Mapping[str, object]", document)


def _positive_samples(value: object) -> list[float] | None:
    if not isinstance(value, list):
        return None
    samples = cast("list[object]", value)
    if len(samples) != MEASURED or not all(
        isinstance(sample, int | float)
        and not isinstance(sample, bool)
        and math.isfinite(sample)
        and sample > 0
        for sample in samples
    ):
        return None
    return [float(cast("float", sample)) for sample in samples]


def _selection_fields(cell: support.Cell) -> dict[str, object]:
    if isinstance(cell, support.FlowCell):
        return {
            "kind": "flow",
            "flow": cell.flow,
            "interface": cell.interface,
            "layout": cell.layout,
            "mode": cell.mode,
        }
    return {"kind": "algorithm", "algorithm": cell.algorithm, "size": cell.size}


def cell_record(cell: support.Cell, document: Mapping[str, object] | str) -> dict[str, object]:
    """The capture's record of ``cell``: its measured samples and their
    window, or why the reading was refused."""
    if isinstance(document, str):
        return {"status": "failed", "reason": document}
    expected = support.expected_outcome(cell).document()
    samples = _positive_samples(document.get("samplesUs"))
    windows = document.get("windows")
    problems = [
        message
        for failed, message in (
            (document.get("cell") != cell.id, f"the reading answered {document.get('cell')!r}"),
            (samples is None, f"the reading carries no {MEASURED} positive samples"),
            (not isinstance(windows, int) or windows <= 0, "the reading timed no window"),
            (document.get("outcome") != expected, f"the outcome is not {expected}"),
        )
        if failed
    ]
    if problems or samples is None:
        return {"status": "failed", "reason": "; ".join(problems)}
    described = support.description(cell)
    return {
        "status": "measured",
        **_selection_fields(cell),
        "unit": "us",
        "samplesUs": samples,
        "medianUs": statistics.median(samples),
        "warmups": WARMUPS,
        "measured": MEASURED,
        "windows": windows,
        "units": described.units,
        "outcome": expected,
        "stages": described.stages,
        "setup": described.setup,
    }


def _not_applicable() -> list[dict[str, object]]:
    return [
        {
            "flow": entry.flow,
            "interface": entry.interface,
            "mode": entry.mode,
            "reason": entry.reason,
        }
        for entry in support.NOT_APPLICABLE
    ]


def capture_document(
    cells: Sequence[support.Cell],
    reader: Reader,
    subject: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Every selected cell read through ``reader``, with the identities and
    conditions the readings were taken under. The environment's load average
    is the host's as the first cell is read, and ``loadAverageAfter`` its load
    once the last one has been."""
    document: dict[str, object] = {
        "schemaVersion": SCHEMA_VERSION,
        "kind": CAPTURE_KIND,
        "subject": dict(production_identity() if subject is None else subject),
        "support": support_identity(),
        "environment": environment(),
        "sampling": sampling(),
        "executionSeam": support.EXECUTION_SEAM,
        "selections": [cell.id for cell in cells],
        "notApplicable": _not_applicable(),
    }
    document["cells"] = {cell.id: cell_record(cell, reader(cell)) for cell in cells}
    document["loadAverageAfter"] = list(os.getloadavg())
    return document


def _fresh_directory(output: Path) -> None:
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise CaptureError(f"{output} already holds a record; recorded evidence is immutable")
    output.mkdir(parents=True, exist_ok=True)


def _write(path: Path, document: Mapping[str, object]) -> None:
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def capture(
    cells: Sequence[support.Cell],
    output: Path,
    reader: Reader = child_reader,
    subject: Mapping[str, object] | None = None,
) -> int:
    """Write ``cells``' capture into ``output``; 0 when every cell was
    measured, 3 when any failed."""
    _fresh_directory(output)
    document = capture_document(cells, reader, subject)
    _write(output / CAPTURE_FILE, document)
    records = cast("Mapping[str, Mapping[str, object]]", document["cells"])
    return 0 if all(record["status"] == "measured" for record in records.values()) else 3


# --------------------------------------------------------------------------- #
# Captures as evidence                                                          #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class Capture:
    path: Path
    document: Mapping[str, Any]

    @property
    def support_digest(self) -> object:
        return self.document["support"].get("digest")

    @property
    def production_digest(self) -> object:
        return self.document["subject"].get("productionDigest")

    @property
    def selections(self) -> tuple[str, ...]:
        return tuple(str(name) for name in self.document["selections"])

    def environment_facts(self) -> dict[str, object]:
        facts = self.document["environment"]
        return {key: facts.get(key) for key in ENVIRONMENT_KEYS}

    def samples(self, cell_id: str) -> tuple[float, ...] | None:
        """``cell_id``'s measured samples, or ``None`` where it is absent,
        failed, malformed, or not recorded as a complete run of a supported
        cell."""
        record = self.document["cells"].get(cell_id)
        if not isinstance(record, Mapping):
            return None
        fields = cast("Mapping[str, object]", record)
        try:
            expected = support.expected_outcome(support.cell_named(cell_id)).document()
        except KeyError:
            return None
        windows = fields.get("windows")
        if (
            fields.get("status") != "measured"
            or fields.get("outcome") != expected
            or not isinstance(windows, int)
            or windows <= 0
        ):
            return None
        samples = _positive_samples(fields.get("samplesUs"))
        return None if samples is None else tuple(samples)


def load_capture(path: Path) -> Capture:
    """The capture at ``path`` — its directory or its file."""
    file = path / CAPTURE_FILE if path.is_dir() else path
    try:
        document = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CaptureError(f"{file} holds no readable capture: {error}") from error
    if not isinstance(document, Mapping):
        raise CaptureError(f"{file} holds no capture document")
    fields = cast("Mapping[str, Any]", document)
    if fields.get("kind") != CAPTURE_KIND or fields.get("schemaVersion") != SCHEMA_VERSION:
        raise CaptureError(f"{file} is not a version {SCHEMA_VERSION} {CAPTURE_KIND}")
    for key in ("subject", "support", "environment", "sampling", "cells"):
        if not isinstance(fields.get(key), Mapping):
            raise CaptureError(f"{file} carries no {key} object")
    if not isinstance(fields.get("selections"), list):
        raise CaptureError(f"{file} carries no selections")
    missing = _missing_provenance(fields)
    if missing:
        raise CaptureError(f"{file} records no {', '.join(missing)}")
    return Capture(file, fields)


def _missing_provenance(fields: Mapping[str, Any]) -> list[str]:
    """The provenance facts compatibility is judged by that ``fields`` lacks,
    so two captures lacking the same fact never compare as compatible."""
    stated = {
        "production digest": fields["subject"].get("productionDigest"),
        "measurement-support digest": fields["support"].get("digest"),
        "execution seam": fields.get("executionSeam"),
        **{f"environment {key}": fields["environment"].get(key) for key in ENVIRONMENT_KEYS},
    }
    missing = [name for name, value in stated.items() if not isinstance(value, str) or not value]
    recorded = fields["sampling"]
    missing.extend(f"sampling {key}" for key in sampling() if key not in recorded)
    return missing


def incompatibilities(baseline: Capture, candidate: Capture) -> list[str]:
    """Every way ``candidate`` was not taken under ``baseline``'s conditions."""
    problems: list[str] = []
    if baseline.support_digest != candidate.support_digest:
        problems.append("the measurement-support digests differ")
    if baseline.document["sampling"] != candidate.document["sampling"]:
        problems.append("the sampling differs")
    if baseline.document.get("executionSeam") != candidate.document.get("executionSeam"):
        problems.append("the execution seams differ")
    before, after = baseline.environment_facts(), candidate.environment_facts()
    problems.extend(
        f"the environment's {key} differs: {before[key]!r} against {after[key]!r}"
        for key in ENVIRONMENT_KEYS
        if before[key] != after[key]
    )
    return problems


def _repetition_problem(original: Capture, repeated: Capture, cell_id: str) -> str | None:
    problems = incompatibilities(original, repeated)
    if repeated.production_digest != original.production_digest:
        problems.append("the worktree's production subject is not the original capture's")
    if repeated.samples(cell_id) is None:
        problems.append(f"{cell_id} was not measured")
    return "; ".join(problems) if problems else None


# --------------------------------------------------------------------------- #
# The rule                                                                      #
# --------------------------------------------------------------------------- #
def dispersion(samples: Sequence[float]) -> float:
    """The interquartile range relative to the median."""
    lower, _, upper = statistics.quantiles(samples, n=4, method="inclusive")
    return (upper - lower) / statistics.median(samples)


def median_error(samples: Sequence[float]) -> float:
    """The standard error of the median relative to it, by the normal
    approximation with the deviation estimated from the interquartile range."""
    return 1.2533 * dispersion(samples) / 1.349 / math.sqrt(len(samples))


def superiority(candidate: Sequence[float], baseline: Sequence[float]) -> float:
    """The probability that a candidate sample exceeds a baseline sample, ties
    counting half."""
    wins = sum(
        1.0 if later > earlier else 0.5 if later == earlier else 0.0
        for later in candidate
        for earlier in baseline
    )
    return wins / (len(candidate) * len(baseline))


@dataclass(frozen=True, slots=True)
class Screen:
    ratio: float
    baseline_dispersion: float
    candidate_dispersion: float
    superiority: float

    @property
    def reasons(self) -> tuple[str, ...]:
        """Why the cell is suspect; empty when it is not."""
        reasons: list[str] = []
        if abs(self.ratio - 1) > INVESTIGATION_TRIGGER:
            reasons.append("beyond-investigation-trigger")
        if max(self.baseline_dispersion, self.candidate_dispersion) > DISPERSION_LIMIT:
            reasons.append("excessive-variability")
        if not 1 - SUPERIORITY_LIMIT < self.superiority < SUPERIORITY_LIMIT:
            reasons.append("consistent-shift")
        return tuple(reasons)

    def document(self) -> dict[str, object]:
        return {
            "ratio": self.ratio,
            "baselineDispersion": self.baseline_dispersion,
            "candidateDispersion": self.candidate_dispersion,
            "superiority": self.superiority,
            "suspect": list(self.reasons),
        }


def screen(baseline: Sequence[float], candidate: Sequence[float]) -> Screen:
    return Screen(
        statistics.median(candidate) / statistics.median(baseline),
        dispersion(baseline),
        dispersion(candidate),
        superiority(candidate, baseline),
    )


def round_order(index: int) -> tuple[Subject, Subject, Subject]:
    """The subjects round ``index`` (from one) captures, in order: the first
    baseline is the candidate's pair, the last baseline its control."""
    return (
        ("baseline", "candidate", "baseline")
        if index % 2
        else ("candidate", "baseline", "baseline")
    )


@dataclass(frozen=True, slots=True)
class Round:
    """One repeated round: its candidate's median and its first and control
    baseline medians, and the resolution of its change — twice the combined
    standard error of the candidate and first baseline medians."""

    index: int
    baseline_us: float
    candidate_us: float
    control_us: float
    resolution: float
    captures: tuple[str, ...]

    @property
    def change(self) -> float:
        return math.log(self.candidate_us / self.baseline_us)

    @property
    def variation(self) -> float:
        return math.log(self.control_us / self.baseline_us)

    def document(self) -> dict[str, object]:
        return {
            "round": self.index,
            "order": list(round_order(self.index)),
            "baselineMedianUs": self.baseline_us,
            "candidateMedianUs": self.candidate_us,
            "controlMedianUs": self.control_us,
            "change": self.change,
            "baselineVariation": self.variation,
            "resolution": self.resolution,
            "captures": list(self.captures),
        }


@dataclass(frozen=True, slots=True)
class Bands:
    """What the rounds' changes are judged against."""

    largest_variation: float
    smallest_variation: float
    resolution: float

    @classmethod
    def of(cls, rounds: Sequence[Round]) -> Bands:
        variations = [abs(taken.variation) for taken in rounds]
        return cls(max(variations), min(variations), max(taken.resolution for taken in rounds))

    def document(self) -> dict[str, float]:
        return {
            "largestBaselineVariation": self.largest_variation,
            "smallestBaselineVariation": self.smallest_variation,
            "resolution": self.resolution,
        }


def judge(rounds: Sequence[Round]) -> Result | None:
    """The conclusion ``rounds`` establish, or ``None`` while they establish
    none."""
    if len(rounds) < MIN_ROUNDS:
        return None
    bands = Bands.of(rounds)
    changes = [taken.change for taken in rounds]
    if min(changes) > max(bands.largest_variation, bands.resolution):
        return "reproducible-regression"
    if statistics.median(changes) <= bands.smallest_variation:
        return "no-detected-regression"
    return None


# --------------------------------------------------------------------------- #
# Comparison                                                                    #
# --------------------------------------------------------------------------- #
type Repeater = Callable[[Subject, support.Cell, Path], Path | str]
"""Captures one cell of one subject into a destination directory and answers
that directory, or why it could not."""


def _repetition_environment() -> dict[str, str]:
    removed = ("VIRTUAL_ENV", "PYTHONPATH", "PYTHONHOME", "UV_PROJECT_ENVIRONMENT")
    return {name: value for name, value in os.environ.items() if name not in removed}


def repetition_command(cell: support.Cell, destination: Path) -> list[str]:
    """What captures ``cell`` alone into ``destination`` from a worktree's
    Python workspace, through that worktree's own environment."""
    return [
        "uv",
        "run",
        "--frozen",
        "python",
        "tools/time_interval_runtime.py",
        "capture",
        *selection_arguments(cell),
        "--output",
        str(destination),
    ]


@dataclass(frozen=True, slots=True)
class WorktreeRepeater:
    """Repeats captures in the baseline and candidate repository worktrees."""

    baseline: Path
    candidate: Path

    def __call__(self, subject: Subject, cell: support.Cell, destination: Path) -> Path | str:
        worktree = self.baseline if subject == "baseline" else self.candidate
        # The child runs in the worktree, so a relative destination would name
        # a directory there rather than the one the comparison reads back.
        destination = destination.resolve()
        try:
            completed = subprocess.run(
                repetition_command(cell, destination),
                cwd=worktree / "languages" / "python",
                env=_repetition_environment(),
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as error:
            return f"the {subject} capture could not be started: {error}"
        if completed.returncode != 0:
            return (
                f"the {subject} capture exited {completed.returncode}\n"
                f"{completed.stdout}{completed.stderr}"
            )
        return destination


@dataclass(frozen=True, slots=True)
class _Pair:
    baseline: Capture
    candidate: Capture

    def of(self, subject: Subject) -> Capture:
        return self.baseline if subject == "baseline" else self.candidate


def _safe(cell_id: str) -> str:
    return cell_id.replace("/", "__")


@dataclass(frozen=True, slots=True)
class _Repetition:
    pair: _Pair
    repeater: Repeater
    rounds_root: Path

    def round(self, cell: support.Cell, index: int) -> Round | str:
        """Round ``index`` of ``cell``, or why it could not be taken."""
        taken_samples: list[tuple[float, ...]] = []
        paths: list[str] = []
        for position, subject in enumerate(round_order(index)):
            destination = self.rounds_root / _safe(cell.id) / f"round-{index}-{position}-{subject}"
            taken = self.repeater(subject, cell, destination)
            if isinstance(taken, str):
                return taken
            try:
                repeated = load_capture(taken)
            except CaptureError as error:
                return str(error)
            problem = _repetition_problem(self.pair.of(subject), repeated, cell.id)
            if problem is not None:
                return f"the round {index} {subject} capture is not comparable: {problem}"
            taken_samples.append(cast("tuple[float, ...]", repeated.samples(cell.id)))
            paths.append(str(repeated.path))
        first, second, control = taken_samples
        baseline, candidate = (first, second) if index % 2 else (second, first)
        return Round(
            index,
            statistics.median(baseline),
            statistics.median(candidate),
            statistics.median(control),
            2 * math.hypot(median_error(baseline), median_error(candidate)),
            tuple(paths),
        )


def _cell_result(result: Result, basis: str, **details: object) -> dict[str, object]:
    return {"result": result, "basis": basis, **details}


def _repeated_result(
    cell: support.Cell, repetition: _Repetition, max_rounds: int, initial: Screen
) -> dict[str, object]:
    rounds: list[Round] = []
    for index in range(1, max_rounds + 1):
        taken = repetition.round(cell, index)
        if isinstance(taken, str):
            return _cell_result(
                "missing-or-incompatible-evidence",
                taken,
                initial=initial.document(),
                rounds=[done.document() for done in rounds],
            )
        rounds.append(taken)
        verdict = judge(rounds)
        if verdict is not None:
            return _cell_result(
                verdict,
                "repetition",
                initial=initial.document(),
                rounds=[done.document() for done in rounds],
                bands=Bands.of(rounds).document(),
            )
    return _cell_result(
        "inconclusive",
        f"undecided after {len(rounds)} of at most {max_rounds} rounds",
        initial=initial.document(),
        rounds=[done.document() for done in rounds],
        bands=Bands.of(rounds).document() if rounds else None,
    )


def compare_cell(
    cell_id: str, pair: _Pair, repetition: _Repetition | None, max_rounds: int
) -> dict[str, object]:
    """``cell_id``'s result: screened, then repeated where it is suspect."""
    before, after = pair.baseline.samples(cell_id), pair.candidate.samples(cell_id)
    if before is None or after is None:
        absent = [
            name
            for name, samples in (("baseline", before), ("candidate", after))
            if samples is None
        ]
        return _cell_result(
            "missing-or-incompatible-evidence", f"not measured in the {' and '.join(absent)}"
        )
    initial = screen(before, after)
    if not initial.reasons:
        return _cell_result("no-detected-regression", "screen", initial=initial.document())
    if repetition is None:
        return _cell_result(
            "inconclusive", "suspect, and repetition was not requested", initial=initial.document()
        )
    try:
        cell = support.cell_named(cell_id)
    except KeyError as error:
        return _cell_result("missing-or-incompatible-evidence", str(error))
    return _repeated_result(cell, repetition, max_rounds, initial)


def _required(pair: _Pair) -> list[str]:
    selected = set(pair.baseline.selections) | set(pair.candidate.selections)
    known = [cell.id for cell in support.CELLS if cell.id in selected]
    return known + sorted(selected.difference(known))


def overall(results: Sequence[Result]) -> Result:
    """The most severe of ``results``; no result at all is missing evidence."""
    if not results:
        return "missing-or-incompatible-evidence"
    return min(results, key=RESULTS.index)


def comparison_document(
    baseline: Capture,
    candidate: Capture,
    *,
    repeater: Repeater | None,
    max_rounds: int,
    rounds_root: Path,
) -> dict[str, object]:
    """Every required cell of ``candidate`` judged against ``baseline``."""
    pair = _Pair(baseline, candidate)
    problems = incompatibilities(baseline, candidate)
    repetition = None if repeater is None else _Repetition(pair, repeater, rounds_root)
    cells: list[dict[str, object]] = []
    for cell_id in _required(pair):
        judged = (
            _cell_result("missing-or-incompatible-evidence", "; ".join(problems))
            if problems
            else compare_cell(cell_id, pair, repetition, max_rounds)
        )
        cells.append({"cell": cell_id, **judged})
    results: list[Result] = [cast("Result", cell["result"]) for cell in cells]
    return {
        "schemaVersion": SCHEMA_VERSION,
        "kind": COMPARISON_KIND,
        "baseline": {"path": str(baseline.path), "subject": baseline.document["subject"]},
        "candidate": {"path": str(candidate.path), "subject": candidate.document["subject"]},
        "rule": {
            "investigationTrigger": INVESTIGATION_TRIGGER,
            "dispersionLimit": DISPERSION_LIMIT,
            "superiorityLimit": SUPERIORITY_LIMIT,
            "minRounds": MIN_ROUNDS,
            "maxRounds": max_rounds,
            "repetition": repeater is not None,
        },
        "compatibility": problems,
        "complete": {cell.id for cell in support.CELLS} <= {cell["cell"] for cell in cells},
        "notApplicable": baseline.document.get("notApplicable", []),
        "counts": {result: results.count(result) for result in RESULTS},
        "result": overall(results),
        "cells": cells,
    }


def compare(
    baseline: Path,
    candidate: Path,
    output: Path,
    *,
    repeater: Repeater | None = None,
    max_rounds: int = DEFAULT_MAX_ROUNDS,
) -> Result:
    """Write the comparison of two captures into ``output`` and answer its result."""
    loaded = load_capture(baseline), load_capture(candidate)
    _fresh_directory(output)
    document = comparison_document(
        *loaded,
        repeater=repeater,
        max_rounds=max_rounds,
        rounds_root=output / "rounds",
    )
    _write(output / COMPARISON_FILE, document)
    return cast("Result", document["result"])


# --------------------------------------------------------------------------- #
# Command line                                                                  #
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    commands = parser.add_subparsers(dest="command", required=True)
    taken = commands.add_parser("capture", help="measure selected cells into a new directory")
    chosen = taken.add_mutually_exclusive_group(required=True)
    chosen.add_argument("--flow", choices=support.FLOWS)
    chosen.add_argument("--algorithm", choices=support.ALGORITHMS)
    chosen.add_argument("--all", action="store_true")
    taken.add_argument("--interface", choices=support.INTERFACES)
    taken.add_argument("--layout", choices=support.LAYOUTS)
    taken.add_argument("--mode", choices=support.MODES)
    taken.add_argument("--size", type=int)
    taken.add_argument("--output", type=Path, required=True)
    judged = commands.add_parser("compare", help="judge a candidate capture against a baseline")
    judged.add_argument("--baseline", type=Path, required=True)
    judged.add_argument("--candidate", type=Path, required=True)
    judged.add_argument("--baseline-worktree", type=Path)
    judged.add_argument("--candidate-worktree", type=Path)
    judged.add_argument("--repeat", action="store_true")
    judged.add_argument("--max-repeat-rounds", type=int, default=DEFAULT_MAX_ROUNDS)
    judged.add_argument("--output", type=Path, required=True)
    child = commands.add_parser("read", help="measure one cell in this interpreter (internal)")
    child.add_argument("cell")
    child.add_argument("--warmups", type=int, required=True)
    child.add_argument("--measured", type=int, required=True)
    return parser


def selected_cells(args: argparse.Namespace) -> tuple[support.Cell, ...]:
    flow_axes = (args.interface, args.layout, args.mode)
    if args.all:
        if any(axis is not None for axis in (*flow_axes, args.size)):
            raise SelectionError("--all takes no narrowing axis")
        return support.CELLS
    if args.flow is not None:
        if args.size is not None:
            raise SelectionError("a flow selection takes no --size")
        return select_flow(args.flow, *flow_axes)
    if any(axis is not None for axis in flow_axes):
        raise SelectionError("an algorithm selection takes only --size")
    return select_algorithm(args.algorithm, args.size)


def _repeater(args: argparse.Namespace) -> Repeater | None:
    worktrees = (args.baseline_worktree, args.candidate_worktree)
    if not args.repeat:
        if any(worktree is not None for worktree in worktrees):
            raise SelectionError("worktrees are used only with --repeat")
        return None
    if None in worktrees:
        raise SelectionError("--repeat requires --baseline-worktree and --candidate-worktree")
    if args.max_repeat_rounds < 0:
        raise SelectionError("--max-repeat-rounds must be non-negative")
    return WorktreeRepeater(args.baseline_worktree.resolve(), args.candidate_worktree.resolve())


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "read":
            document = reading_document(args.cell, warmups=args.warmups, measured=args.measured)
            print(json.dumps(document, sort_keys=True))
            return 0
        if args.command == "capture":
            return capture(selected_cells(args), args.output)
        result = compare(
            args.baseline,
            args.candidate,
            args.output,
            repeater=_repeater(args),
            max_rounds=args.max_repeat_rounds,
        )
    except (SelectionError, CaptureError, KeyError) as error:
        print(f"{parser.prog}: {error}", file=sys.stderr)
        return 2
    print(json.dumps({"result": result, "comparison": str(args.output / COMPARISON_FILE)}))
    return 0 if result == "no-detected-regression" else 1


if __name__ == "__main__":
    raise SystemExit(main())
