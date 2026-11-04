from __future__ import annotations

import copy
import json
from typing import Any
from unittest.mock import patch

import pytest

import release_setup as setup


def _configuration() -> dict[str, Any]:
    return json.loads(setup.CONFIG.read_text())


def _environment(expected: dict[str, Any]) -> dict[str, Any]:
    rules: list[dict[str, Any]] = []
    if expected["reviewers"]:
        rules.append(
            {
                "type": "required_reviewers",
                "prevent_self_review": False,
                "reviewers": [
                    {"type": item["type"], "reviewer": {"id": item["id"]}}
                    for item in expected["reviewers"]
                ],
            }
        )
    return {
        "can_admins_bypass": False,
        "deployment_branch_policy": expected["deployment_branch_policy"],
        "protection_rules": rules,
    }


@pytest.mark.parametrize(
    "mutation", ["absent", "other-owner", "extra-reviewer", "self-review", "admin", "branches"]
)
def test_production_requires_dave_approval_without_bypass(mutation: str) -> None:
    expected = _configuration()["environments"]["pypi"]
    actual = copy.deepcopy(_environment(expected))
    if mutation == "absent":
        actual["protection_rules"] = []
    elif mutation == "other-owner":
        actual["protection_rules"][0]["reviewers"][0]["reviewer"]["id"] += 1
    elif mutation == "extra-reviewer":
        actual["protection_rules"][0]["reviewers"].append({"type": "User", "reviewer": {"id": 1}})
    elif mutation == "self-review":
        actual["protection_rules"][0]["prevent_self_review"] = True
    elif mutation == "admin":
        actual["can_admins_bypass"] = True
    else:
        actual["deployment_branch_policy"]["custom_branch_policies"] = False
    with pytest.raises(ValueError):
        setup.verify_environment(actual, expected)


def test_dave_can_approve_his_own_production_release() -> None:
    expected = _configuration()["environments"]["pypi"]
    setup.verify_environment(_environment(expected), expected)


def test_readback_detects_unexpected_branch_on_later_policy_page() -> None:
    config = _configuration()

    def api(path: str, payload: dict[str, Any] | None = None, method: str = "GET") -> Any:
        assert payload is None and method == "GET"
        if path == f"repos/{config['repository']}":
            return {"visibility": "public"}
        if "deployment-branch-policies" in path:
            if path.endswith("&page=1"):
                return {"branch_policies": [{"name": "main", "type": "branch"}] * 100}
            return {"branch_policies": [{"name": "unexpected", "type": "tag"}]}
        return _environment(config["environments"][path.rsplit("/", 1)[1]])

    with patch.object(setup, "gh_api", api), pytest.raises(ValueError, match="branches differ"):
        setup.configure()


def test_apply_refuses_to_remove_or_silently_allow_unexpected_policies() -> None:
    config = _configuration()
    mutations: list[str] = []

    def api(path: str, payload: dict[str, Any] | None = None, method: str = "GET") -> Any:
        if method != "GET":
            mutations.append(method)
            return {}
        if path == f"repos/{config['repository']}":
            return {"visibility": "public"}
        return {"branch_policies": [{"name": "release/**", "type": "tag"}]}

    with patch.object(setup, "gh_api", api), pytest.raises(ValueError, match="unexpected branch"):
        setup.configure(apply=True)
    assert mutations == ["PUT"]
