"""Apply and verify the repository-owned release environment configuration."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

CONFIG = Path(__file__).resolve().parents[3] / ".github/release/configuration.json"


def gh_api(path: str, payload: dict[str, Any] | None = None, method: str = "GET") -> Any:
    command = ["gh", "api", path, "--method", method]
    if payload is not None:
        command += ["--input", "-"]
    result = subprocess.run(
        command,
        input=json.dumps(payload) if payload is not None else None,
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(result.stdout) if result.stdout.strip() else None


def verify_environment(actual: dict[str, Any], expected: dict[str, Any]) -> None:
    if actual.get("deployment_branch_policy") != expected["deployment_branch_policy"]:
        raise ValueError("release environment branch restrictions differ from configuration")
    rules = actual.get("protection_rules", [])
    reviewer_rules = [rule for rule in rules if rule["type"] == "required_reviewers"]
    wanted = {(r["type"], r["id"]) for r in expected["reviewers"]}
    if wanted:
        if len(reviewer_rules) != 1:
            raise ValueError("production requires exactly one reviewer rule")
        rule = reviewer_rules[0]
        found = {(r["type"], r["reviewer"]["id"]) for r in rule["reviewers"]}
        if found != wanted or rule.get("prevent_self_review") is not False:
            raise ValueError("production must require Dave and allow his self approval")
        if actual.get("can_admins_bypass") is not False:
            raise ValueError("production administrator approval bypass must be disabled")
    elif reviewer_rules:
        raise ValueError("unexpected rehearsal approval requirement")


def _branches(path: str) -> list[dict[str, Any]]:
    policies: list[dict[str, Any]] = []
    page = 1
    while True:
        found = gh_api(f"{path}/deployment-branch-policies?per_page=100&page={page}")[
            "branch_policies"
        ]
        policies.extend(found)
        if len(found) < 100:
            return policies
        page += 1


def configure(*, apply: bool = False) -> dict[str, Any]:
    config = json.loads(CONFIG.read_text())
    prefix = f"repos/{config['repository']}"
    repository = gh_api(prefix)
    if repository["visibility"] != "public":
        raise ValueError("review release environment capability before using a private repository")
    result: dict[str, Any] = {"repository": config["repository"], "environments": {}}
    for name, expected in config["environments"].items():
        path = f"{prefix}/environments/{name}"
        if apply:
            gh_api(path, expected, "PUT")
            found = _branches(path)
            if any(
                (policy["name"], policy["type"])
                not in {(branch, "branch") for branch in config["branches"][name]}
                for policy in found
            ):
                raise ValueError(f"{name}: remove unexpected branch policies explicitly")
            for branch in config["branches"][name]:
                if not any(
                    policy["name"] == branch and policy["type"] == "branch" for policy in found
                ):
                    gh_api(
                        f"{path}/deployment-branch-policies",
                        {"name": branch, "type": "branch"},
                        "POST",
                    )
        actual = gh_api(path)
        verify_environment(actual, expected)
        branches = _branches(path)
        if {(policy["name"], policy["type"]) for policy in branches} != {
            (branch, "branch") for branch in config["branches"][name]
        }:
            raise ValueError(f"{name}: release branches differ from configuration")
        result["environments"][name] = {**actual, "observed_branch_policies": branches}
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = configure(apply=args.apply)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n")
    print("Release environments verified; production approval remains required.")


if __name__ == "__main__":
    main()
