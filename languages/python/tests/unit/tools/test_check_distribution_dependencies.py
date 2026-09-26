"""The internal-distribution dependency check, on the real workspace and on
scratch workspaces planted with each finding it exists to report."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path

import pytest

import check_distribution_dependencies as check_module
from check_distribution_dependencies import check
from python_workspace import load_workspace
from tests._support.repo import PY_ROOT
from tests.unit.tools._workspace_support import write_member, write_root

_CORE = {"parallax/core/__init__.py": "", "parallax/core/model.py": "VALUE = 1\n"}
_POSTGRES = {"parallax/postgres/__init__.py": "from parallax.core.model import VALUE\n"}


def _findings(
    repo: Path,
    members: Mapping[str, tuple[Mapping[str, str], Iterable[str], Mapping[str, Iterable[str]]]],
    *,
    workspace_members: Iterable[str] = ("packages/*",),
    sources: Iterable[str] | None = None,
) -> list[str]:
    root = write_root(
        repo,
        sources=members.keys() if sources is None else sources,
        members=workspace_members,
    )
    for name, (modules, dependencies, extras) in members.items():
        write_member(repo, name, modules, dependencies=dependencies, extras=extras)
    return check(load_workspace(root))


def _siblings(
    snapshot: Mapping[str, str], dependencies: Iterable[str] = ("parallax-core",)
) -> dict[str, tuple[Mapping[str, str], Iterable[str], Mapping[str, Iterable[str]]]]:
    return {
        "parallax-core": (_CORE, (), {}),
        "parallax-postgres": (_POSTGRES, ("parallax-core", "psycopg>=3"), {}),
        "parallax-snapshot": (snapshot, dependencies, {}),
    }


def test_the_real_workspace_declares_exactly_the_siblings_it_imports() -> None:
    assert check(load_workspace(PY_ROOT)) == []


def test_main_exits_zero_on_the_real_workspace() -> None:
    assert check_module.main([]) == 0


def test_a_consistent_scratch_workspace_passes(tmp_path: Path) -> None:
    snapshot = {"parallax/snapshot/__init__.py": "from parallax.core import model\n"}
    assert _findings(tmp_path, _siblings(snapshot)) == []


def test_an_undeclared_sibling_import_fails(tmp_path: Path) -> None:
    snapshot = {"parallax/snapshot/__init__.py": "import parallax.core.model\n"}
    assert _findings(tmp_path, _siblings(snapshot, dependencies=())) == [
        "parallax-snapshot: imports parallax-core (src/parallax/snapshot/__init__.py:1) "
        "but [project].dependencies does not declare it"
    ]


def test_an_unused_sibling_declaration_fails(tmp_path: Path) -> None:
    snapshot = {"parallax/snapshot/__init__.py": "from parallax.core import model\n"}
    findings = _findings(
        tmp_path, _siblings(snapshot, dependencies=("parallax-core", "parallax-postgres"))
    )
    assert findings == [
        "parallax-snapshot: [project].dependencies declares parallax-postgres, "
        "which nothing it gates imports"
    ]


def test_a_member_declaring_itself_fails(tmp_path: Path) -> None:
    snapshot = {"parallax/snapshot/__init__.py": "from parallax.core import model\n"}
    findings = _findings(
        tmp_path, _siblings(snapshot, dependencies=("parallax-core", "parallax-snapshot"))
    )
    assert findings == [
        "parallax-snapshot: [project].dependencies declares parallax-snapshot, "
        "which is the member itself"
    ]


@pytest.mark.parametrize(
    "source",
    [
        "from __future__ import annotations\nfrom typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n    from parallax.core.model import VALUE\n",
        "def load():\n    import parallax.core\n",
        "from parallax import core\n",
    ],
    ids=["type-checking", "function-body", "namespace-from"],
)
def test_every_static_import_spelling_needs_its_sibling(tmp_path: Path, source: str) -> None:
    snapshot = {"parallax/snapshot/__init__.py": source}
    [finding] = _findings(tmp_path, _siblings(snapshot, dependencies=()))
    assert finding.startswith("parallax-snapshot: imports parallax-core ")


def test_imports_resolve_to_the_member_owning_each_namespace_scope(tmp_path: Path) -> None:
    # Relative and absolute imports of the member's own scope are not sibling
    # imports, and each `parallax.<scope>` reaches exactly the member owning it
    # although every member ships beneath the same `parallax` namespace.
    snapshot = {
        "parallax/snapshot/__init__.py": "from . import handle\nfrom .handle import read\n",
        "parallax/snapshot/handle/__init__.py": "from .. import handle as again\n",
        "parallax/snapshot/handle/read.py": (
            "import parallax.snapshot.handle\nfrom ...postgres import adapter\n"
        ),
    }
    findings = _findings(tmp_path, _siblings(snapshot, dependencies=("parallax-postgres",)))
    assert findings == []
    missing = _findings(tmp_path / "missing", _siblings(snapshot, dependencies=()))
    assert missing == [
        "parallax-snapshot: imports parallax-postgres "
        "(src/parallax/snapshot/handle/read.py:2) but [project].dependencies does not declare it"
    ]


def test_an_import_of_a_scope_no_member_owns_fails(tmp_path: Path) -> None:
    snapshot = {"parallax/snapshot/__init__.py": "import parallax.nowhere\n"}
    assert _findings(tmp_path, _siblings(snapshot, dependencies=())) == [
        "parallax-snapshot: src/parallax/snapshot/__init__.py:1 imports parallax.nowhere, "
        "which no workspace member owns"
    ]


def test_a_parallax_requirement_naming_no_member_fails(tmp_path: Path) -> None:
    snapshot = {"parallax/snapshot/__init__.py": "from parallax.core import model\n"}
    findings = _findings(
        tmp_path, _siblings(snapshot, dependencies=("parallax-core", "parallax-gone>=1"))
    )
    assert findings == [
        "parallax-snapshot: [project].dependencies declares parallax-gone, "
        "which is no workspace member"
    ]


_AWS_BASE = "from parallax.core.model import VALUE\n"
_AWS_SLICE = "from parallax.postgres import VALUE\nfrom parallax.core import model\n"


def _aws(
    repo: Path,
    *,
    base: Iterable[str],
    extras: Mapping[str, Iterable[str]],
    modules: Mapping[str, str] | None = None,
) -> list[str]:
    aws = modules or {
        "parallax/aws/__init__.py": _AWS_BASE,
        "parallax/aws/postgres.py": _AWS_SLICE,
    }
    members = _siblings({"parallax/snapshot/__init__.py": ""}, dependencies=())
    members["parallax-aws"] = (aws, base, extras)
    return _findings(repo, members)


def test_an_extra_satisfies_the_imports_of_the_slice_it_names(tmp_path: Path) -> None:
    findings = _aws(
        tmp_path,
        base=("parallax-core", "botocore"),
        extras={"postgres": ("parallax-postgres", "psycopg>=3")},
    )
    assert findings == []


def test_an_extra_can_gate_a_slice_package(tmp_path: Path) -> None:
    modules = {
        "parallax/aws/__init__.py": _AWS_BASE,
        "parallax/aws/postgres/__init__.py": "",
        "parallax/aws/postgres/factory.py": _AWS_SLICE,
    }
    findings = _aws(
        tmp_path,
        base=("parallax-core",),
        extras={"postgres": ("parallax-postgres",)},
        modules=modules,
    )
    assert findings == []


def test_a_slice_import_missing_from_its_extra_fails(tmp_path: Path) -> None:
    assert _aws(tmp_path, base=("parallax-core",), extras={"postgres": ()}) == [
        "parallax-aws: imports parallax-postgres (src/parallax/aws/postgres.py:1) "
        "but [project.optional-dependencies].postgres does not declare it"
    ]


def test_a_slice_import_declared_in_the_base_belongs_in_its_extra(tmp_path: Path) -> None:
    findings = _aws(tmp_path, base=("parallax-core", "parallax-postgres"), extras={"postgres": ()})
    assert findings == [
        "parallax-aws: [project].dependencies declares parallax-postgres, "
        "which nothing it gates imports",
        "parallax-aws: imports parallax-postgres (src/parallax/aws/postgres.py:1) "
        "but [project.optional-dependencies].postgres does not declare it",
    ]


def test_a_base_import_is_not_satisfied_by_an_extra(tmp_path: Path) -> None:
    modules = {
        "parallax/aws/__init__.py": _AWS_BASE + "from parallax.postgres import VALUE as V\n",
        "parallax/aws/postgres.py": _AWS_SLICE,
    }
    findings = _aws(
        tmp_path,
        base=("parallax-core",),
        extras={"postgres": ("parallax-postgres",)},
        modules=modules,
    )
    assert findings == [
        "parallax-aws: imports parallax-postgres (src/parallax/aws/__init__.py:2) "
        "but [project].dependencies does not declare it",
        "parallax-aws: [project.optional-dependencies].postgres declares parallax-postgres, "
        "which nothing it gates imports",
    ]


def test_an_extra_gating_no_slice_fails(tmp_path: Path) -> None:
    findings = _aws(
        tmp_path,
        base=("parallax-core",),
        extras={"postgres": ("parallax-postgres",), "mysql": ("parallax-core",)},
    )
    assert findings == [
        "parallax-aws: extra 'mysql' gates no parallax.aws.mysql slice, "
        "so the check cannot tell which imports it satisfies"
    ]


def test_a_member_the_workspace_globs_miss_fails(tmp_path: Path) -> None:
    snapshot = {"parallax/snapshot/__init__.py": "from parallax.core import model\n"}
    findings = _findings(
        tmp_path,
        _siblings(snapshot),
        workspace_members=("packages/parallax-core", "packages/parallax-postgres"),
    )
    assert findings[0] == (
        "packages/parallax-snapshot: not matched by [tool.uv.workspace].members, "
        "so no workspace check analyzes it"
    )


def test_a_member_missing_from_the_workspace_sources_fails(tmp_path: Path) -> None:
    snapshot = {"parallax/snapshot/__init__.py": "from parallax.core import model\n"}
    findings = _findings(
        tmp_path, _siblings(snapshot), sources=("parallax-core", "parallax-postgres")
    )
    assert findings == [
        "parallax-snapshot: missing from [tool.uv.sources] as a workspace source, so a sibling "
        "requirement on it would not resolve to the workspace"
    ]


def test_a_new_member_is_analyzed_like_every_other(tmp_path: Path) -> None:
    members = _siblings({"parallax/snapshot/__init__.py": "from parallax.core import model\n"})
    members["parallax-mysql"] = ({"parallax/mysql/__init__.py": "import parallax.core\n"}, (), {})
    assert _findings(tmp_path, members) == [
        "parallax-mysql: imports parallax-core (src/parallax/mysql/__init__.py:1) "
        "but [project].dependencies does not declare it"
    ]


@pytest.mark.parametrize(
    ("modules", "expected"),
    [
        ({"parallax/README": ""}, "owns no scope packages under src/parallax/"),
        (
            {"parallax/mysql/__init__.py": "", "parallax/maria/__init__.py": ""},
            "owns ['maria', 'mysql'] scope packages under src/parallax/",
        ),
        ({"parallax/core/__init__.py": ""}, "parallax.core: owned by several members"),
        (
            {"parallax/__init__.py": "", "parallax/mysql/__init__.py": ""},
            "src/parallax/ holds modules ['__init__.py']",
        ),
    ],
    ids=["no-scope", "several-scopes", "shared-scope", "regular-namespace-package"],
)
def test_a_member_without_one_owned_scope_fails(
    tmp_path: Path, modules: dict[str, str], expected: str
) -> None:
    members = _siblings({"parallax/snapshot/__init__.py": "from parallax.core import model\n"})
    members["parallax-mysql"] = (modules, (), {})
    findings = _findings(tmp_path, members)
    assert any(expected in finding for finding in findings), findings


def test_main_exits_non_zero_on_a_finding(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    snapshot = {"parallax/snapshot/__init__.py": "import parallax.core\n"}
    root = write_root(tmp_path, sources=_siblings(snapshot).keys())
    for name, (modules, _, extras) in _siblings(snapshot).items():
        write_member(tmp_path, name, modules, extras=extras)
    monkeypatch.setattr(check_module, "PY_ROOT", root)
    assert check_module.main([]) == 1
