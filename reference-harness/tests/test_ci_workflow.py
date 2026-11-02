"""The workflow reader reduces YAML to the facts the CI contract judges."""

from __future__ import annotations

from pathlib import Path

from reference_harness import ci_workflow


def _read(tmp_path: Path, text: str) -> ci_workflow.Workflow:
    path = tmp_path / "ci.yml"
    path.write_text(text, encoding="utf-8")
    workflow = ci_workflow.read(path)
    assert workflow is not None
    return workflow


def test_a_bare_on_key_still_names_the_triggers(tmp_path: Path) -> None:
    workflow = _read(tmp_path, "on:\n  push:\n  schedule:\n    - cron: '0 7 * * 1'\njobs: {}\n")
    assert workflow.triggers == frozenset({"push", "schedule"})
    assert workflow.jobs == ()


def test_triggers_spelled_as_a_list_or_a_word_are_read(tmp_path: Path) -> None:
    assert _read(tmp_path, "on: [push, pull_request]\n").triggers == {"push", "pull_request"}
    assert _read(tmp_path, "on: workflow_dispatch\n").triggers == {"workflow_dispatch"}
    assert _read(tmp_path, "name: none\n").triggers == frozenset()


def test_dependencies_conditions_outputs_and_the_matrix_are_read(tmp_path: Path) -> None:
    workflow = _read(
        tmp_path,
        "jobs:\n"
        "  relevance:\n"
        "    outputs:\n"
        "      relevant: ${{ steps.r.outputs.relevant }}\n"
        "  cells:\n"
        "    name: cells (${{ matrix.provider }})\n"
        "    needs: relevance\n"
        "    if: ${{ needs.relevance.outputs.relevant == 'true' }}\n"
        "    runs-on: ${{ matrix.runner }}\n"
        "    strategy:\n"
        "      matrix:\n"
        "        include: [{provider: aws, runner: r}]\n"
        "    steps:\n"
        "      - run: just python-check-cloud\n"
        "  verdict:\n"
        "    needs: [relevance]\n"
        "    if: always()\n",
    )
    relevance, cells, verdict = workflow.jobs
    assert relevance.outputs == ("relevant",)
    assert cells.needs == ("relevance",)
    assert cells.condition == "needs.relevance.outputs.relevant == 'true'"
    assert cells.name == "cells (${{ matrix.provider }})"
    assert cells.runs_on == "${{ matrix.runner }}"
    assert cells.matrix == {"include": [{"provider": "aws", "runner": "r"}]}
    assert cells.invoked == ("python-check-cloud",)
    assert (verdict.needs, verdict.condition) == (("relevance",), "always()")
    assert relevance.matrix is None and relevance.condition is None


def test_a_document_that_is_no_mapping_has_no_jobs(tmp_path: Path) -> None:
    assert _read(tmp_path, "- just a list\n") == ci_workflow.Workflow(frozenset(), ())
    assert ci_workflow.read(tmp_path / "absent.yml") is None
    assert ci_workflow.jobs(tmp_path / "absent.yml") is None
