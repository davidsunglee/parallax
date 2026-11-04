"""Create one pending-publisher project through OIDC without publishing files."""

from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, cast

from release_artifacts import CONFIG, INDEXES

_VISIBILITY_ATTEMPTS = 13


class BootstrapError(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


def request_json(request: urllib.request.Request) -> tuple[int, dict[str, Any]]:
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=30) as response:
            document = json.loads(response.read())
            if not isinstance(document, dict):
                raise BootstrapError("invalid-json-object")
            return response.status, cast(dict[str, Any], document)
    except urllib.error.HTTPError as error:
        # Remote error bodies and exception text can contain credentials.
        return error.code, {}
    except OSError, ValueError:
        raise BootstrapError("network-or-json-failure") from None


def _https_url(url: str) -> urllib.parse.SplitResult:
    parsed = urllib.parse.urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in (None, 443)
        or parsed.fragment
    ):
        raise BootstrapError("unsafe-endpoint")
    return parsed


def _runtime(config: dict[str, Any]) -> dict[str, str]:
    values = {
        key: os.environ.get(f"GITHUB_{key}", "")
        for key in ("REPOSITORY", "WORKFLOW_REF", "SHA", "REF", "RUN_ID", "RUN_ATTEMPT")
    }
    workflow_prefix = f"{config['repository']}/.github/workflows/{config['workflow']}@"
    if (
        os.environ.get("GITHUB_ACTIONS") != "true"
        or values["REPOSITORY"] != config["repository"]
        or values["WORKFLOW_REF"] != workflow_prefix + values["REF"]
        or not values["REF"].startswith("refs/heads/")
        or not re.fullmatch(r"[0-9a-f]{40}", values["SHA"])
        or not values["RUN_ID"].isdigit()
        or not values["RUN_ATTEMPT"].isdigit()
    ):
        raise BootstrapError("invalid-github-runtime")
    endpoint = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL", "")
    hostname = _https_url(endpoint).hostname
    if not hostname or not hostname.endswith(".actions.githubusercontent.com"):
        raise BootstrapError("invalid-github-oidc-endpoint")
    if not os.environ.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN"):
        raise BootstrapError("missing-github-oidc-credential")
    return {key.lower(): value for key, value in values.items()}


def _observe(base: str, project: str, *, require_empty: bool = True) -> dict[str, Any]:
    status, document = request_json(
        urllib.request.Request(
            f"{base}/simple/{project}/",
            headers={"Accept": "application/vnd.pypi.simple.v1+json", "Cache-Control": "no-cache"},
        )
    )
    if status == 404:
        return {"status": "absent", "http_status": status}
    if status != 200:
        raise BootstrapError(f"simple-index-http-{status}")
    files = document.get("files")
    if document.get("name") != project or not isinstance(files, list):
        raise BootstrapError("simple-index-name-or-files-mismatch")
    if not require_empty:
        return {
            "status": "project-present",
            "http_status": status,
            "name": project,
            "file_count": len(cast(list[Any], files)),
        }
    if files:
        raise BootstrapError("simple-index-name-or-files-mismatch")
    return {"status": "empty-project", "http_status": status, "name": project, "files": []}


def _mint(base: str, index: str) -> int:
    status, audience = request_json(urllib.request.Request(f"{base}/_/oidc/audience"))
    if status != 200 or audience.get("audience") != index:
        raise BootstrapError(f"invalid-audience-response-http-{status}")
    parsed = _https_url(os.environ["ACTIONS_ID_TOKEN_REQUEST_URL"])
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query = [(key, value) for key, value in query if key != "audience"]
    endpoint = parsed._replace(query=urllib.parse.urlencode([*query, ("audience", index)])).geturl()
    status, identity = request_json(
        urllib.request.Request(
            endpoint,
            headers={"Authorization": f"Bearer {os.environ['ACTIONS_ID_TOKEN_REQUEST_TOKEN']}"},
        )
    )
    if status != 200 or not isinstance(identity.get("value"), str) or not identity["value"]:
        raise BootstrapError(f"invalid-github-oidc-response-http-{status}")
    request = urllib.request.Request(
        f"{base}/_/oidc/mint-token",
        data=json.dumps({"token": identity.pop("value")}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    status, minted = request_json(request)
    token = minted.pop("token", None)
    valid_token = isinstance(token, str) and bool(token)
    del token
    expires = minted.get("expires")
    if (
        status != 200
        or minted.get("success") is not True
        or not valid_token
        or type(expires) is not int
        or expires <= 0
    ):
        raise BootstrapError(f"invalid-mint-response-http-{status}")
    return expires


def bootstrap(index: str, project: str, output: Path) -> dict[str, Any]:
    """Always retain nonsecret evidence; an existing project requires owner confirmation."""
    evidence: dict[str, Any] = {"index": index, "project": project, "status": "failed"}
    try:
        config = json.loads(CONFIG.read_text())
        if index not in INDEXES or project not in config["projects"]:
            raise BootstrapError("unconfigured-index-or-project")
        base = INDEXES[index]
        _https_url(base)
        evidence["source"] = _runtime(config)
        evidence["before"] = _observe(base, project)
        if evidence["before"]["status"] != "absent":
            evidence["status"] = "owner-confirmation-needed"
            return evidence
        evidence["expires"] = _mint(base, index)
        for attempt in range(_VISIBILITY_ATTEMPTS):
            evidence["after"] = _observe(base, project)
            evidence["visibility_attempts"] = attempt + 1
            if evidence["after"]["status"] == "empty-project":
                evidence["status"] = "created-owner-check-required"
                return evidence
            if attempt + 1 < _VISIBILITY_ATTEMPTS:
                time.sleep(10)
        raise BootstrapError("project-not-visible-after-mint")
    except BootstrapError as error:
        evidence["error"] = str(error)
        return evidence
    except Exception:
        evidence["error"] = "unexpected-bootstrap-failure"
        return evidence
    finally:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(evidence, indent=2) + "\n")


def check_projects(index: str, output: Path) -> dict[str, Any]:
    """Check public project presence only; this cannot establish an Owner role."""
    evidence: dict[str, Any] = {
        "index": index,
        "status": "setup-incomplete",
        "owner_role_verified": False,
        "projects": {},
    }
    try:
        if index not in INDEXES:
            raise BootstrapError("unconfigured-index")
        config = json.loads(CONFIG.read_text())
        base = INDEXES[index]
        _https_url(base)
        for project in config["projects"]:
            evidence["checking_project"] = project
            observation = _observe(base, project, require_empty=False)
            evidence["projects"][project] = observation
            if observation["status"] == "absent":
                raise BootstrapError("configured-project-absent")
        del evidence["checking_project"]
        evidence["status"] = "projects-present"
    except BootstrapError as error:
        evidence["error"] = str(error)
    except Exception:
        evidence["error"] = "unexpected-project-check-failure"
    finally:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(evidence, indent=2) + "\n")
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", choices=INDEXES, required=True)
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument("--project")
    operation.add_argument("--check-projects", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.check_projects:
        evidence = check_projects(args.index, args.output)
        print(f"Project presence: {evidence['status']}. Owner roles were not verified.")
        if evidence["status"] != "projects-present":
            raise SystemExit(1)
        return
    evidence = bootstrap(args.index, args.project, args.output)
    print(f"Bootstrap: {evidence['status']}. Check the actual Owner role in the index UI.")
    if evidence["status"] != "created-owner-check-required":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
