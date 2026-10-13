"""Evidence bundles for the to-one traversal performance driver.

A bundle is one JSON manifest plus the statement and sample files it names by
relative path and SHA-256 digest. A compiler-only inventory freezes statements
and provenance and makes no execution claim; a capture adds live server
provenance, seeded counts, every ordinary execution timing, and every raw
``EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)`` sample. Validation only reads.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import statistics
import subprocess
import sys
from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Final, Literal, cast

from parallax.core.base import INFINITY
from parallax.core.dialect import POSTGRES

MANIFEST_VERSION: Final = 1
ENVIRONMENT_PREFIX: Final = "PARALLAX_TO_ONE_PERFORMANCE_"
SUITES: Final = ("reads", "mixed", "collections", "writes")
PRODUCTION_VARIANTS: Final = ("baseline", "current")

type Mode = Literal["inventory", "list", "compare", "validate"]
type Suite = Literal["reads", "mixed", "collections", "writes"]
type Pairing = Literal["paired", "current-only"]
type Kind = Literal["read", "update", "delete"]
type Observation = Literal["multiset", "ordered", "affected"]
type Campaign = Literal["focused", "final"]

_MODES: Final[frozenset[str]] = frozenset({"inventory", "list", "compare", "validate"})
_SHA: Final = re.compile(r"^[0-9a-f]{40}$")
_DIGEST: Final = re.compile(r"^[0-9a-f]{64}$")
_SAFE_NAME: Final = re.compile(r"^[a-z0-9][a-z0-9.-]*$")


class EvidenceError(ValueError):
    """A refused selection, overwrite, or malformed evidence input."""


def environment(name: str, environ: Mapping[str, str] | None = None) -> str | None:
    value = (os.environ if environ is None else environ).get(ENVIRONMENT_PREFIX + name)
    return value.strip() if value is not None and value.strip() else None


def selected_mode(environ: Mapping[str, str] | None = None) -> Mode | None:
    value = environment("MODE", environ)
    if value is None:
        return None
    if value not in _MODES:
        raise EvidenceError(f"{ENVIRONMENT_PREFIX}MODE={value!r} is not one of {sorted(_MODES)}")
    return cast("Mode", value)


def required_path(name: str, environ: Mapping[str, str] | None = None) -> Path:
    value = environment(name, environ)
    if value is None:
        raise EvidenceError(f"{ENVIRONMENT_PREFIX}{name} names no path")
    return Path(value)


# --------------------------------------------------------------------------- #
# Workload classification and selection                                        #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class Classification:
    """What the executable manifest says one workload is."""

    id: str
    suite: Suite
    pairing: Pairing
    kind: Kind
    observation: Observation
    variants: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Selection:
    suite: Suite | Literal["all"]
    workloads: tuple[str, ...]
    variants: tuple[str, ...]
    campaign: Campaign
    scale: str
    warmups: int
    samples: int
    explains: int


def _listed(value: str | None) -> tuple[str, ...]:
    if value is None:
        return ()
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _count(name: str, default: int, environ: Mapping[str, str] | None, *, minimum: int) -> int:
    raw = environment(name, environ)
    if raw is None:
        return default
    if not raw.isdigit() or int(raw) < minimum:
        raise EvidenceError(f"{ENVIRONMENT_PREFIX}{name}={raw!r} is not an integer >= {minimum}")
    return int(raw)


def select(  # noqa: C901 - one refusal per selection rule
    manifest: Sequence[Classification],
    scales: Sequence[str],
    environ: Mapping[str, str] | None = None,
    *,
    default_scale: str,
) -> Selection:
    """The capture a compare run requests, refusing anything not stated exactly.

    A focused capture names its workloads; an absent, empty, or unknown name is
    an error rather than a fallback to the whole suite. Only the final campaign
    may take every workload of its suite.
    """
    suite = environment("SUITE", environ) or ""
    if suite not in (*SUITES, "all"):
        raise EvidenceError(f"{ENVIRONMENT_PREFIX}SUITE={suite!r} is not one of {[*SUITES, 'all']}")
    campaign_value = environment("CAMPAIGN", environ) or "focused"
    if campaign_value not in ("focused", "final"):
        raise EvidenceError(f"{ENVIRONMENT_PREFIX}CAMPAIGN={campaign_value!r} is not 'final'")
    campaign: Campaign = campaign_value
    in_suite = [entry for entry in manifest if suite in ("all", entry.suite)]
    known = {entry.id: entry for entry in in_suite}
    requested = _listed(environment("WORKLOADS", environ))
    if not requested:
        if campaign != "final":
            raise EvidenceError(
                f"a focused capture names exact workloads in {ENVIRONMENT_PREFIX}WORKLOADS"
            )
        requested = tuple(known)
    unknown = [name for name in requested if name not in known]
    if unknown:
        raise EvidenceError(f"workloads {unknown} are not {suite!r} workloads of the manifest")
    if len(set(requested)) != len(requested):
        raise EvidenceError(f"workloads {list(requested)} repeat an id")
    variants = _listed(environment("VARIANTS", environ)) or PRODUCTION_VARIANTS
    for name in requested:
        allowed = known[name].variants
        if not set(variants) & set(allowed):
            raise EvidenceError(f"{name} declares none of the variants {list(variants)}")
    declared = {variant for entry in in_suite for variant in entry.variants}
    stray = sorted(set(variants) - declared)
    if stray:
        raise EvidenceError(f"variants {stray} are declared by no selected workload")
    scale = environment("SCALE", environ) or default_scale
    if scale not in scales:
        raise EvidenceError(f"{ENVIRONMENT_PREFIX}SCALE={scale!r} is not one of {list(scales)}")
    return Selection(
        suite=suite,
        workloads=requested,
        variants=tuple(variants),
        campaign=campaign,
        scale=scale,
        warmups=_count("WARMUPS", 2, environ, minimum=0),
        samples=_count("SAMPLES", 7, environ, minimum=1),
        explains=_count("EXPLAINS", 3, environ, minimum=1),
    )


def variants_for(entry: Classification, selection: Selection) -> tuple[str, ...]:
    """The variants a selected workload runs, in declaration order: a
    current-only workload has no baseline to run."""
    return tuple(variant for variant in entry.variants if variant in selection.variants)


# --------------------------------------------------------------------------- #
# Lossless bind codec                                                          #
# --------------------------------------------------------------------------- #


def encode_bind(value: object) -> dict[str, object]:  # noqa: C901 - one arm per carrier
    match value:
        case None:
            return {"t": "null"}
        case bool():
            return {"t": "bool", "v": value}
        case int():
            return {"t": "int", "v": value}
        case float():
            return {"t": "float", "v": repr(value)}
        case Decimal():
            return {"t": "decimal", "v": str(value)}
        case str():
            return {"t": "str", "v": value}
        case dt.datetime():
            if value.tzinfo is None:
                raise EvidenceError(f"a naive timestamp bind {value!r} has no lossless spelling")
            return {"t": "datetime", "v": value.isoformat()}
        case dt.date():
            return {"t": "date", "v": value.isoformat()}
        case _ if value is INFINITY:
            return {"t": "infinity"}
        case tuple() | list():
            items = cast("Sequence[object]", value)
            return {"t": type(items).__name__, "v": [encode_bind(item) for item in items]}
        case _:
            raise EvidenceError(f"a bind of {type(value).__name__} has no lossless spelling")


def decode_bind(document: Mapping[str, object]) -> object:  # noqa: C901 - one arm per carrier
    tag, raw = document.get("t"), document.get("v")
    match tag:
        case "null":
            return None
        case "bool" if isinstance(raw, bool):
            return raw
        case "int" if isinstance(raw, int) and not isinstance(raw, bool):
            return raw
        case "float" if isinstance(raw, str):
            return float(raw)
        case "decimal" if isinstance(raw, str):
            return Decimal(raw)
        case "str" if isinstance(raw, str):
            return raw
        case "datetime" if isinstance(raw, str):
            return dt.datetime.fromisoformat(raw)
        case "date" if isinstance(raw, str):
            return dt.date.fromisoformat(raw)
        case "infinity":
            return INFINITY
        case "tuple" | "list" if isinstance(raw, list):
            items = [
                decode_bind(cast("Mapping[str, object]", item))
                for item in cast("list[object]", raw)
            ]
            return tuple(items) if tag == "tuple" else items
        case _:
            raise EvidenceError(f"{document!r} is not an encoded bind")


def encode_binds(binds: Sequence[object]) -> list[dict[str, object]]:
    encoded = [encode_bind(bind) for bind in binds]
    replayed = decode_binds(encoded)
    if [(type(a), a) for a in replayed] != [(type(b), b) for b in binds]:
        raise EvidenceError(f"binds {binds!r} do not survive their own encoding")
    return encoded


def decode_binds(encoded: Sequence[Mapping[str, object]]) -> tuple[object, ...]:
    return tuple(decode_bind(item) for item in encoded)


# --------------------------------------------------------------------------- #
# Digests and provenance                                                       #
# --------------------------------------------------------------------------- #


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def file_digests(paths: Sequence[Path], root: Path) -> dict[str, str]:
    return {path.relative_to(root).as_posix(): sha256_bytes(path.read_bytes()) for path in paths}


def _git(root: Path, *arguments: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        capture_output=True,
    ).stdout


def compiler_state(root: Path) -> dict[str, object]:
    """The checkout the statements were compiled from: its commit, and whether
    and how its working tree differs, tracked and untracked alike."""
    untracked = sorted(
        name
        for name in _git(root, "ls-files", "--others", "--exclude-standard", "-z")
        .decode()
        .split("\0")
        if name
    )
    diff = hashlib.sha256(_git(root, "diff", "HEAD", "--binary"))
    for name in untracked:
        diff.update(name.encode() + b"\0" + (root / name).read_bytes())
    status = _git(root, "status", "--porcelain").decode()
    return {
        "branch": _git(root, "rev-parse", "--abbrev-ref", "HEAD").decode().strip(),
        "sha": _git(root, "rev-parse", "HEAD").decode().strip(),
        "dirty": bool(status.strip()),
        "diffDigest": diff.hexdigest(),
        "changedPaths": sorted(line[3:] for line in status.splitlines() if line),
    }


def command_record(environ: Mapping[str, str] | None = None) -> dict[str, object]:
    source = os.environ if environ is None else environ
    return {
        "argv": list(sys.argv),
        "environment": {
            name: value for name, value in sorted(source.items()) if name.startswith("PARALLAX_")
        },
    }


def now() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


# --------------------------------------------------------------------------- #
# Bundle writing                                                               #
# --------------------------------------------------------------------------- #


def dumps(document: object) -> str:
    return json.dumps(document, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


class BundleWriter:
    """Files of one capture identity, written once into a fresh output directory."""

    def __init__(self, directory: Path, prefix: str) -> None:
        if not _SAFE_NAME.match(prefix):
            raise EvidenceError(f"{prefix!r} is not a capture identity")
        if not directory.is_dir():
            raise EvidenceError(f"{directory} is not an existing output directory")
        existing = sorted(path.name for path in directory.glob(f"{prefix}-*"))
        if existing:
            raise EvidenceError(
                f"{directory} already holds capture {prefix!r} ({existing[0]}); choose a fresh "
                "output directory rather than overwrite earlier evidence"
            )
        self.directory = directory
        self.prefix = prefix
        self._files: dict[str, str] = {}

    def write(self, suffix: str, document: object) -> str:
        name = f"{self.prefix}-{suffix}.json"
        if not _SAFE_NAME.match(name) or name in self._files:
            raise EvidenceError(f"{name!r} is not a fresh file name of this capture")
        text = dumps(document)
        (self.directory / name).write_text(text, encoding="utf-8")
        self._files[name] = sha256_text(text)
        return name

    def finish(self, manifest: Mapping[str, object]) -> Path:
        files = [{"path": name, "sha256": digest} for name, digest in sorted(self._files.items())]
        path = self.directory / f"{self.prefix}-manifest.json"
        path.write_text(dumps({**manifest, "files": files}), encoding="utf-8")
        return path


def load(path: Path) -> dict[str, Any]:
    return cast("dict[str, Any]", json.loads(path.read_text(encoding="utf-8")))


# --------------------------------------------------------------------------- #
# Plan extraction                                                              #
# --------------------------------------------------------------------------- #

_NODE_FIELDS: Final = (
    ("Relation Name", "relation"),
    ("Alias", "alias"),
    ("Function Name", "function"),
    ("Subplan Name", "subplan"),
    ("Parent Relationship", "parent"),
    ("Index Name", "index"),
)


def plan_nodes(plan: Mapping[str, Any]) -> list[dict[str, object]]:
    """Every node of one executed plan, depth first, with its actual work."""

    def walk(node: Mapping[str, Any], depth: int) -> Iterator[dict[str, object]]:
        entry: dict[str, object] = {"depth": depth, "node": node["Node Type"]}
        for source, name in _NODE_FIELDS:
            if source in node:
                entry[name] = node[source]
        entry["loops"] = node.get("Actual Loops")
        entry["rows"] = node.get("Actual Rows")
        entry["sharedHit"] = node.get("Shared Hit Blocks")
        entry["sharedRead"] = node.get("Shared Read Blocks")
        yield entry
        for child in cast("Sequence[Mapping[str, Any]]", node.get("Plans", ())):
            yield from walk(child, depth + 1)

    return list(walk(cast("Mapping[str, Any]", plan["Plan"]), 0))


def plan_summary(plans: Sequence[Mapping[str, Any]]) -> dict[str, object]:
    """Server timings over every sample, and the last sample's per-relation work."""
    executed = [float(plan["Execution Time"]) for plan in plans]
    planned = [float(plan["Planning Time"]) for plan in plans]
    nodes = plan_nodes(plans[-1])
    relations: dict[str, dict[str, int]] = {}
    for node in nodes:
        name = str(node.get("relation") or node.get("function") or node.get("subplan") or "")
        if not name:
            continue
        totals = relations.setdefault(name, {"nodes": 0, "loops": 0, "rows": 0, "sharedHit": 0})
        loops = int(cast("int", node["loops"] or 0))
        totals["nodes"] += 1
        totals["loops"] += loops
        totals["rows"] += int(cast("int", node["rows"] or 0)) * max(loops, 1)
        totals["sharedHit"] += int(cast("int", node["sharedHit"] or 0))
    root = cast("Mapping[str, Any]", plans[-1]["Plan"])
    return {
        "executionMs": _spread(executed),
        "planningMs": _spread(planned),
        "rootSharedHit": root.get("Shared Hit Blocks"),
        "rootSharedRead": root.get("Shared Read Blocks"),
        "topology": [
            "  " * cast("int", node["depth"])
            + str(node["node"])
            + "".join(
                f" [{node[key]}]" for key in ("relation", "function", "subplan") if key in node
            )
            for node in nodes
        ],
        "relations": relations,
    }


def compare_summaries(baseline: Mapping[str, Any], current: Mapping[str, Any]) -> dict[str, object]:
    """Per-relation work of a paired capture, side by side."""
    names = sorted(set(baseline["relations"]) | set(current["relations"]))
    empty = {"nodes": 0, "loops": 0, "rows": 0, "sharedHit": 0}
    return {
        "executionMedianMs": {
            "baseline": baseline["executionMs"]["median"],
            "current": current["executionMs"]["median"],
        },
        "relations": {
            name: {
                "baseline": baseline["relations"].get(name, empty),
                "current": current["relations"].get(name, empty),
            }
            for name in names
        },
    }


def _spread(samples: Sequence[float]) -> dict[str, float]:
    return {
        "median": statistics.median(samples),
        "min": min(samples),
        "max": max(samples),
    }


def timing_summary(samples_ns: Sequence[int]) -> dict[str, float]:
    return _spread([sample / 1e6 for sample in samples_ns])


# --------------------------------------------------------------------------- #
# Semantic observations                                                        #
# --------------------------------------------------------------------------- #


def observed(values: Sequence[int], observation: Observation) -> dict[str, object]:
    """One execution's roots in a comparable, multiplicity-preserving form."""
    if observation == "ordered":
        return {"ordered": list(values), "digest": sha256_text(json.dumps(list(values)))}
    counts = sorted(Counter(values).items())
    return {
        "count": len(values),
        "distinct": len(counts),
        "digest": sha256_text(json.dumps(counts)),
    }


# --------------------------------------------------------------------------- #
# Validation                                                                   #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class _Check:
    problems: list[str]

    def expect(self, condition: bool, problem: str) -> bool:
        if not condition:
            self.problems.append(problem)
        return condition


def _record(value: object) -> Mapping[str, Any]:
    return cast("Mapping[str, Any]", value) if isinstance(value, Mapping) else {}


def _filled(value: object, kind: type) -> bool:
    return isinstance(value, kind) and bool(value)


def _number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _check_files(manifest: Mapping[str, Any], root: Path, check: _Check) -> dict[str, Any]:
    loaded: dict[str, Any] = {}
    entries = manifest.get("files")
    if not check.expect(bool(entries) and isinstance(entries, list), "the manifest lists no files"):
        return loaded
    prefix = str(manifest.get("captureId", ""))
    for entry in cast("list[Mapping[str, Any]]", entries):
        name, digest = str(entry.get("path")), entry.get("sha256")
        path = root / name
        if not check.expect(
            name.startswith(f"evidence-{prefix}-") and "/" not in name,
            f"{name} is not a file of capture {prefix!r}",
        ):
            continue
        if not check.expect(path.is_file(), f"{name} is missing"):
            continue
        data = path.read_bytes()
        if check.expect(sha256_bytes(data) == digest, f"{name} does not match its digest"):
            loaded[name] = json.loads(data)
    return loaded


def _check_provenance(manifest: Mapping[str, Any], check: _Check) -> None:
    check.expect(manifest.get("manifestVersion") == MANIFEST_VERSION, "unknown manifest version")
    created = manifest.get("createdAt")
    try:
        dt.datetime.fromisoformat(cast("str", created))
    except (TypeError, ValueError):
        check.expect(False, f"createdAt {created!r} is not a timestamp")
    command = _record(manifest.get("command"))
    check.expect(_filled(command.get("argv"), list), "the command is not recorded")
    check.expect(
        isinstance(command.get("environment"), Mapping), "the command environment is not recorded"
    )
    compiler = _record(manifest.get("compiler"))
    check.expect(bool(compiler.get("branch")), "the compiler branch is not recorded")
    check.expect(bool(_SHA.match(str(compiler.get("sha")))), "the compiler SHA is not recorded")
    check.expect(isinstance(compiler.get("dirty"), bool), "the dirty state is not recorded")
    check.expect(
        bool(_DIGEST.match(str(compiler.get("diffDigest")))), "the diff digest is not recorded"
    )
    driver_files = _record(_record(manifest.get("driver")).get("files"))
    check.expect(
        bool(driver_files) and all(_DIGEST.match(str(digest)) for digest in driver_files.values()),
        "the driver files are not recorded",
    )
    for owner in ("driver", "schema", "seed"):
        record = _record(manifest.get(owner))
        check.expect(
            bool(_DIGEST.match(str(record.get("digest")))), f"the {owner} digest is not recorded"
        )


def validate_inventory(path: Path, manifest: Sequence[Classification]) -> list[str]:
    """Every problem the compiler-only inventory at ``path`` has; none when valid."""
    check = _Check([])
    document = load(path)
    _check_provenance(document, check)
    check.expect(document.get("kind") == "inventory", "not an inventory manifest")
    check.expect(document.get("captureId") == "baseline", "not the baseline capture identity")
    check.expect("server" not in document, "an inventory claims a server")
    loaded = _check_files(document, path.parent, check)
    statements: dict[str, Mapping[str, Any]] = {}
    parameters: dict[str, object] = {}
    for content in loaded.values():
        statements.update(cast("Mapping[str, Mapping[str, Any]]", content.get("statements", {})))
        parameters.update(cast("Mapping[str, object]", content.get("parameters", {})))
    expected = {entry.id: entry for entry in manifest}
    entries = {
        str(entry.get("id")): entry
        for entry in cast("list[Mapping[str, Any]]", document.get("workloads", []))
    }
    for name, entry in entries.items():
        known = expected.get(name)
        if not check.expect(known is not None, f"{name} is not a workload of the manifest"):
            continue
        assert known is not None
        check.expect(entry.get("suite") == known.suite, f"{name} changed suite")
        check.expect(entry.get("pairing") == known.pairing, f"{name} changed pairing")
        check.expect(entry.get("kind") == known.kind, f"{name} changed kind")
        recorded = _record(parameters.get(name))
        check.expect(
            _filled(recorded.get("objectQuery"), Mapping)
            and _filled(recorded.get("reference"), str)
            and isinstance(recorded.get("finalScales"), list),
            f"{name} has no complete parameters",
        )
        check.expect(entry.get("observation") == known.observation, f"{name} changed observation")
        statement = statements.get(name)
        if known.pairing == "current-only":
            check.expect(statement is None, f"{name} is current-only but froze a statement")
            continue
        if not check.expect(statement is not None, f"{name} froze no statement"):
            continue
        assert statement is not None
        _check_statement(name, statement, check)
    paired = {entry.id for entry in manifest if entry.pairing == "paired"}
    check.expect(
        paired <= set(entries),
        f"paired workloads {sorted(paired - set(entries))} have no inventory entry",
    )
    check.expect(not set(statements) - set(entries), "a statement file names an unlisted workload")
    return check.problems


def _placeholders(sql: str) -> int:
    """The binds ``sql`` takes, counted as the PostgreSQL driver reads it."""
    return POSTGRES.to_driver_sql(sql).replace("%%", "").count("%s")


def _check_statement(name: str, statement: Mapping[str, Any], check: _Check) -> None:
    sql = statement.get("sql")
    if not check.expect(_filled(sql, str), f"{name} has no SQL"):
        return
    binds = statement.get("binds")
    try:
        decoded = decode_binds(cast("Sequence[Mapping[str, object]]", binds))
        lossless = encode_binds(decoded) == binds
    except (EvidenceError, TypeError, ValueError, AttributeError):
        decoded, lossless = (), False
    if check.expect(lossless, f"{name}'s binds are not losslessly replayable"):
        placeholders = _placeholders(cast("str", sql))
        check.expect(
            placeholders == len(decoded),
            f"{name} binds {len(decoded)} values to {placeholders} placeholders",
        )


def validate_capture(
    path: Path, manifest: Sequence[Classification], final_matrix: Sequence[tuple[str, str]]
) -> list[str]:
    """Every problem the measured capture at ``path`` has; none when valid.

    A selected paired point needs both production variants and a referenced
    baseline; a selected current-only point needs complete current samples, and
    a capture selecting no paired point never reads its baseline. Every point's
    observations must agree with its independent reference. Unselected
    workloads need nothing, except that a final campaign must cover the whole
    final matrix of its suite.
    """
    check = _Check([])
    document = load(path)
    _check_provenance(document, check)
    check.expect(document.get("kind") == "capture", "not a capture manifest")
    server = _record(document.get("server"))
    for name, kind in (("image", str), ("version", str), ("settings", Mapping), ("container", str)):
        check.expect(_filled(server.get(name), kind), f"the server {name} is not recorded")
    protocol = _record(document.get("protocol"))
    samples, explains = protocol.get("samples"), protocol.get("explains")
    check.expect(isinstance(samples, int) and samples > 0, "the sample count is not recorded")
    check.expect(isinstance(explains, int) and explains > 0, "the EXPLAIN count is not recorded")
    warmups = protocol.get("warmups")
    check.expect(isinstance(warmups, int) and warmups >= 0, "the warmup count is not recorded")
    for name in ("order", "ordinaryTiming", "explainTiming"):
        check.expect(_filled(protocol.get(name), str), f"the protocol {name} is not recorded")
    expected = {entry.id: entry for entry in manifest}
    selection = _record(document.get("selection"))
    points = {
        (str(point[0]), str(point[1]))
        for point in cast("list[list[str]]", selection.get("points", []))
    }
    check.expect(bool(points), "the capture selects no point")
    _check_selection(selection, points, expected, final_matrix, check)
    scales = _record(_record(document.get("seed")).get("scales"))
    for scale in {scale for _, scale in points}:
        record = _record(scales.get(scale))
        check.expect(
            all(
                _filled(record.get(name), Mapping)
                for name in ("counts", "distributions", "parameters")
            ),
            f"scale {scale} records no seeded counts, distributions, and parameters",
        )
    loaded = _check_files(document, path.parent, check)
    baseline = cast("Mapping[str, Any] | None", document.get("baseline"))
    replays = any(expected[name].pairing == "paired" for name, _ in points if name in expected)
    frozen = _frozen(baseline, check) if baseline is not None and replays else {}
    selected_variants = set(cast("list[str]", selection.get("variants") or []))
    entries = {
        (str(entry.get("id")), str(entry.get("scale"))): entry
        for entry in cast("list[Mapping[str, Any]]", document.get("workloads", []))
    }
    check.expect(set(entries) == points, "captured points differ from the selection")
    for point, entry in entries.items():
        known = expected.get(point[0])
        label = "/".join(point)
        if not check.expect(known is not None, f"{label} is not a workload of the manifest"):
            continue
        assert known is not None
        check.expect(entry.get("pairing") == known.pairing, f"{label} changed pairing")
        variants = {
            str(variant.get("variant")): variant
            for variant in cast("list[Mapping[str, Any]]", entry.get("variants", []))
        }
        check.expect(
            set(variants) == {name for name in known.variants if name in selected_variants},
            f"{label} measures variants other than its selected ones",
        )
        if known.pairing == "current-only":
            check.expect(set(variants) == {"current"}, f"{label} is current-only")
        else:
            check.expect(baseline is not None, f"{label} is paired but references no baseline")
            check.expect(
                set(PRODUCTION_VARIANTS) <= set(variants), f"{label} lacks a production variant"
            )
            check.expect(bool(entry.get("comparison")), f"{label} has no paired summary")
            replayed = loaded.get(str(variants.get("baseline", {}).get("statement")))
            check.expect(
                replayed is not None and replayed == frozen.get(point[0]),
                f"{label} did not replay its frozen baseline statement",
            )
        for name, variant in variants.items():
            _check_variant(f"{label}/{name}", variant, loaded, samples, explains, check)
        _check_observations(label, known.kind, set(variants), entry, check)
    return check.problems


def _check_selection(
    selection: Mapping[str, Any],
    points: set[tuple[str, str]],
    expected: Mapping[str, Classification],
    final_matrix: Sequence[tuple[str, str]],
    check: _Check,
) -> None:
    """The recorded selection is one ``select`` could make, and its points are
    exactly those its workloads and scale or campaign produce."""
    suite, campaign = selection.get("suite"), selection.get("campaign")
    check.expect(suite in (*SUITES, "all"), f"the selected suite {suite!r} is unknown")
    check.expect(campaign in ("focused", "final"), f"the selected campaign {campaign!r} is unknown")
    members = {name for name, entry in expected.items() if suite in ("all", entry.suite)}
    workloads = [str(name) for name in cast("list[object]", selection.get("workloads") or [])]
    check.expect(
        bool(workloads) and set(workloads) <= members and len(set(workloads)) == len(workloads),
        f"the selected workloads {workloads} are not distinct {suite!r} workloads",
    )
    declared = {variant for name in members for variant in expected[name].variants}
    variants = cast("list[object]", selection.get("variants") or [])
    check.expect(
        bool(variants) and set(variants) <= declared,
        f"the selected variants {variants} are not declared by the {suite!r} workloads",
    )
    if campaign == "final":
        required = {point for point in final_matrix if point[0] in members}
        check.expect(required <= points, f"the final campaign omits {sorted(required - points)}")
        produced = {point for point in final_matrix if point[0] in workloads}
    else:
        produced = {(name, str(selection.get("scale"))) for name in workloads}
    check.expect(points == produced, "the selected points are not those of its workloads")


def _check_observations(
    label: str, kind: Kind, variants: set[str], entry: Mapping[str, Any], check: _Check
) -> None:
    """Parity recomputed from the recorded observations: every variant
    statement and the public execution read the reference's roots with their
    multiplicity, and every mutation affected as many rows."""
    observations = _record(entry.get("observations"))
    reference = _record(observations.get("reference"))
    if not check.expect(
        bool(_DIGEST.match(str(reference.get("digest"))))
        and isinstance(reference.get("count"), int),
        f"{label} has no reference reading",
    ):
        return
    statements = _record(observations.get("statements"))
    public = _record(observations.get("public"))
    affected = _record(observations.get("affectedRows"))
    check.expect(bool(public), f"{label} has no public execution")
    check.expect(set(statements) == variants, f"{label} does not observe every variant")
    check.expect(
        set(affected) == (set() if kind == "read" else variants),
        f"{label} does not count every mutation's affected rows",
    )
    check.expect(
        all(
            record.get("digest") == reference["digest"]
            and record.get("count", reference["count"]) == reference["count"]
            for record in (*map(_record, statements.values()), public)
        )
        and all(count == reference["count"] for count in affected.values()),
        f"{label} lacks semantic parity",
    )


def _frozen(baseline: Mapping[str, Any], check: _Check) -> dict[str, Any]:
    """The statements of the inventory a capture says it replayed."""
    path = Path(str(baseline.get("manifest")))
    if not check.expect(path.is_file(), f"the replayed baseline {path} is unavailable"):
        return {}
    check.expect(
        sha256_bytes(path.read_bytes()) == baseline.get("digest"),
        "the replayed baseline does not match its digest",
    )
    statements: dict[str, Any] = {}
    for content in _check_files(load(path), path.parent, check).values():
        statements.update(cast("Mapping[str, Any]", content.get("statements", {})))
    return statements


_ACTUAL_WORK: Final = (
    "Actual Loops",
    "Actual Rows",
    "Actual Total Time",
    "Shared Hit Blocks",
    "Shared Read Blocks",
)


def _executed_node(node: object) -> bool:
    record = _record(node)
    children = record.get("Plans", [])
    return (
        _filled(record.get("Node Type"), str)
        and all(_number(record.get(name)) for name in _ACTUAL_WORK)
        and isinstance(children, list)
        and all(_executed_node(child) for child in cast("list[object]", children))
    )


def _executed_plan(plan: object) -> bool:
    """An ``EXPLAIN (ANALYZE, BUFFERS)`` sample: server timings, and actual
    loops, rows, time, and buffer work at every node."""
    record = _record(plan)
    return (
        _number(record.get("Execution Time"))
        and _number(record.get("Planning Time"))
        and _executed_node(record.get("Plan"))
    )


def _check_variant(
    label: str,
    variant: Mapping[str, Any],
    loaded: Mapping[str, Any],
    samples: object,
    explains: object,
    check: _Check,
) -> None:
    statement = loaded.get(str(variant.get("statement")))
    measured = loaded.get(str(variant.get("samples")))
    if check.expect(statement is not None, f"{label} has no statement file"):
        _check_statement(label, cast("Mapping[str, Any]", statement), check)
    if not check.expect(measured is not None, f"{label} has no samples file"):
        return
    measured = _record(measured)
    ordinary = measured.get("ordinaryNs")
    check.expect(
        isinstance(ordinary, list)
        and len(cast("list[object]", ordinary)) == samples
        and all(
            isinstance(sample, int) and not isinstance(sample, bool) and sample > 0
            for sample in cast("list[object]", ordinary)
        ),
        f"{label} lacks ordinary samples",
    )
    plans = measured.get("explain")
    if check.expect(
        isinstance(plans, list) and len(cast("list[object]", plans)) == explains,
        f"{label} lacks EXPLAIN samples",
    ):
        check.expect(
            all(_executed_plan(plan) for plan in cast("list[object]", plans)),
            f"{label} holds a sample that is not an executed plan",
        )


def assert_valid(problems: Sequence[str]) -> None:
    assert not problems, "\n".join(problems)
