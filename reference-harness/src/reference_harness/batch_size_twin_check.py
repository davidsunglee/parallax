"""Validate the compatibility corpus's batch-size twin proofs.

A streamed read's page size is a performance dial: it changes what the delivery
costs and nothing about which roots arrive, their order, or what each carries.
The corpus proves that by authoring the same read once per page size, because
the corpus executes authored goldens rather than compiling them and a second
page size therefore needs goldens of its own.

Two such cases pass independently whatever they say, so the claim they jointly
make survives only while they still describe one read. This checker is what
keeps that true: a coherent edit to one arm's query and graph together would
otherwise leave two cases passing and the invariance quietly evaporated.

The arms are named ``<module>-NNN-<proof>-batch-size-twin-<batchSize>.yaml`` and
paired by ``<module>-<proof>``. Each arm declares its own ``batchSize``, its own
statements, and its own round-trip count; on everything else — the model, the
Object Query, the delivered graph, the compile-eligibility declaration — they
must be equal.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from reference_harness.case_twins import (
    case_twin_arms,
    is_physical_case_member,
    logical_case,
    mapping_document,
    module_ids,
    yaml_paths,
)

__all__ = ["batch_size_twin_errors", "main", "run"]

_CASE_TWIN_RE = re.compile(r"^(?P<prefix>.+)-batch-size-twin-(?P<arm>[0-9]+)\.ya?ml$")


def _is_page_size_member(path: tuple[str, ...], key: str) -> bool:
    """Every member a page size legitimately changes, on top of the physical ones.

    ``when.stream.batchSize`` is the dial itself, and ``then.roundTrips`` is the
    statement count it moves — the same physical observation ``then.statements``
    already is, stated as a number.
    """
    if path == ("when", "stream"):
        return key == "batchSize"
    if path == ("then",):
        return key == "roundTrips" or is_physical_case_member(path, key)
    return is_physical_case_member(path, key)


def _declared_batch_size(document: Mapping[str, Any]) -> object:
    stream = document.get("when", {})
    stream = stream.get("stream") if isinstance(stream, Mapping) else None
    return stream.get("batchSize") if isinstance(stream, Mapping) else None


def batch_size_twin_errors(compatibility_root: Path) -> list[str]:
    """Return every batch-size twin inconsistency under *compatibility_root*."""
    errors: list[str] = []
    if not compatibility_root.is_dir():
        return [f"not a directory: {compatibility_root}"]

    modules = module_ids(compatibility_root, errors)
    candidates = case_twin_arms(
        yaml_paths(compatibility_root / "cases"), _CASE_TWIN_RE, modules, "batch-size", errors
    )
    for pair, arms in sorted(candidates.items()):
        if len(arms) < 2:
            (only,) = arms.values()
            errors.append(
                f"batch-size twin {pair!r} has one member ({only.name}); the proof is that a "
                "page size changes nothing, which one page size cannot state"
            )
            continue
        documents: dict[str, dict[str, Any]] = {}
        for arm, path in sorted(arms.items()):
            document = mapping_document(path, "compatibility case", errors)
            if document is None:
                continue
            declared = _declared_batch_size(document)
            if declared != int(arm):
                errors.append(
                    f"{path.name}: filename declares batch size {arm} but "
                    f"when.stream.batchSize is {declared!r}"
                )
            documents[arm] = document
        if len(documents) != len(arms):
            continue
        baseline_arm, baseline = sorted(documents.items())[0]
        reduced = logical_case(baseline, physical=_is_page_size_member)
        for arm, document in sorted(documents.items())[1:]:
            if logical_case(document, physical=_is_page_size_member) != reduced:
                errors.append(
                    f"batch-size twin {pair!r} arms {baseline_arm} and {arm} differ in "
                    "page-size-invariant authored behavior"
                )
    return errors


def run(compatibility_root: Path) -> int:
    """Run the batch-size twin gate and print a concise verdict."""
    errors = batch_size_twin_errors(compatibility_root)
    if errors:
        print(f"batch-size twin gate FAILED ({len(errors)} problem(s)):", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print("batch-size twin gate OK: every streamed twin states one read at every page size")
    return 0


def main(argv: list[str]) -> int:
    """CLI entry point for ``python -m reference_harness.batch_size_twin_check``."""
    if len(argv) != 1:
        print(
            "usage: python -m reference_harness.batch_size_twin_check <compatibility-dir>",
            file=sys.stderr,
        )
        return 2
    return run(Path(argv[0]))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
