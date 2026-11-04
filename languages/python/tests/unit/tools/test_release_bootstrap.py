from __future__ import annotations

import json
import urllib.error
import urllib.request
from email.message import Message
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

import release_bootstrap as bootstrap

_ENDPOINT = "https://vstoken.actions.githubusercontent.com/token?api-version=2.0"
_PROJECT = "parallax-core"
_BASE = "https://test.pypi.org"
_EMPTY: dict[str, Any] = {"name": _PROJECT, "files": []}
_SECRETS = ("github-request-secret", "github-jwt-secret", "minted-upload-secret")
type Reply = tuple[int, dict[str, Any]]


@pytest.fixture(autouse=True)
def runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    values = {
        "GITHUB_ACTIONS": "true",
        "GITHUB_REPOSITORY": "davidsunglee/parallax",
        "GITHUB_WORKFLOW_REF": (
            "davidsunglee/parallax/.github/workflows/release.yml@refs/heads/main"
        ),
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_SHA": "a" * 40,
        "GITHUB_RUN_ID": "1234",
        "GITHUB_RUN_ATTEMPT": "1",
        "ACTIONS_ID_TOKEN_REQUEST_URL": _ENDPOINT,
        "ACTIONS_ID_TOKEN_REQUEST_TOKEN": _SECRETS[0],
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def _replies(after: Reply = (200, _EMPTY)) -> list[Reply]:
    return [
        (404, {}),
        (200, {"audience": "testpypi"}),
        (200, {"value": _SECRETS[1]}),
        (200, {"success": True, "token": _SECRETS[2], "expires": 123456}),
        after,
    ]


def _transport(
    monkeypatch: pytest.MonkeyPatch, replies: list[Reply]
) -> list[urllib.request.Request]:
    requests: list[urllib.request.Request] = []

    def request_json(request: urllib.request.Request) -> Reply:
        requests.append(request)
        assert replies, "unexpected request"
        return replies.pop(0)

    def no_sleep(seconds: float) -> None:
        assert seconds == 10

    monkeypatch.setattr(bootstrap, "request_json", request_json)
    monkeypatch.setattr(bootstrap.time, "sleep", no_sleep)
    return requests


def _run(tmp_path: Path) -> dict[str, Any]:
    output = tmp_path / "nested/evidence.json"
    result = bootstrap.bootstrap("testpypi", _PROJECT, output)
    evidence = output.read_text()
    assert json.loads(evidence) == result
    for secret in _SECRETS:
        assert secret not in evidence
    return result


def test_bootstrap_exchanges_once_without_uploading_and_retains_safe_evidence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    requests = _transport(monkeypatch, _replies())
    result = _run(tmp_path)
    assert result["status"] == "created-owner-check-required"
    assert result["source"]["sha"] == "a" * 40
    assert result["expires"] == 123456
    assert result["before"]["status"] == "absent"
    assert result["after"] == {"status": "empty-project", "http_status": 200, **_EMPTY}
    assert [(request.get_method(), request.full_url) for request in requests] == [
        ("GET", f"{_BASE}/simple/{_PROJECT}/"),
        ("GET", f"{_BASE}/_/oidc/audience"),
        ("GET", _ENDPOINT + "&audience=testpypi"),
        ("POST", f"{_BASE}/_/oidc/mint-token"),
        ("GET", f"{_BASE}/simple/{_PROJECT}/"),
    ]
    assert requests[2].get_header("Authorization") == f"Bearer {_SECRETS[0]}"
    assert requests[3].data == json.dumps({"token": _SECRETS[1]}).encode()
    assert all(request.get_header("Authorization") is None for request in requests[:2])
    assert all(request.get_header("Authorization") is None for request in requests[3:])


def test_existing_project_requires_owner_confirmation_without_exchange(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    requests = _transport(monkeypatch, [(200, _EMPTY)])
    assert _run(tmp_path)["status"] == "owner-confirmation-needed"
    assert len(requests) == 1


@pytest.mark.parametrize("project", ["parallax-conformance", "unconfigured"])
def test_refuses_unconfigured_projects_before_network(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, project: str
) -> None:
    requests = _transport(monkeypatch, [])
    result = bootstrap.bootstrap("testpypi", project, tmp_path / "evidence.json")
    assert result["error"] == "unconfigured-index-or-project"
    assert not requests


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("GITHUB_ACTIONS", "false"),
        ("GITHUB_REPOSITORY", "other/repo"),
        (
            "GITHUB_WORKFLOW_REF",
            "davidsunglee/parallax/.github/workflows/other.yml@refs/heads/main",
        ),
        ("GITHUB_SHA", "bad-sha"),
        ("GITHUB_RUN_ID", ""),
        ("GITHUB_RUN_ATTEMPT", ""),
        ("GITHUB_REF", ""),
        ("ACTIONS_ID_TOKEN_REQUEST_TOKEN", ""),
        ("ACTIONS_ID_TOKEN_REQUEST_URL", ""),
        ("ACTIONS_ID_TOKEN_REQUEST_URL", "http://vstoken.actions.githubusercontent.com/token"),
        ("ACTIONS_ID_TOKEN_REQUEST_URL", "https://evil.example/token"),
        (
            "ACTIONS_ID_TOKEN_REQUEST_URL",
            "https://secret@vstoken.actions.githubusercontent.com/token",
        ),
    ],
)
def test_runtime_failures_never_contact_network(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, key: str, value: str
) -> None:
    monkeypatch.setenv(key, value)
    requests = _transport(monkeypatch, [])
    assert _run(tmp_path)["status"] == "failed"
    assert not requests


@pytest.mark.parametrize(
    ("position", "replacement"),
    [
        (1, (200, {"audience": "pypi"})),
        (1, (500, {"secret": _SECRETS[0]})),
        (2, (200, {"value": ""})),
        (2, (403, {"value": _SECRETS[1]})),
        (3, (403, {"token": _SECRETS[2], "errors": [_SECRETS[1]]})),
        (3, (200, {"success": False, "token": _SECRETS[2], "expires": 123})),
        (3, (200, {"success": True, "token": "", "expires": 123})),
        (3, (200, {"success": True, "token": _SECRETS[2], "expires": _SECRETS[1]})),
        (4, (200, dict[str, Any](name="wrong-project", files=[]))),
        (4, (200, {"name": _PROJECT, "files": [{"filename": "published.whl"}]})),
    ],
)
def test_failed_exchanges_and_wrong_observations_retain_sanitized_evidence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, position: int, replacement: Reply
) -> None:
    replies = _replies()
    replies[position] = replacement
    requests = _transport(monkeypatch, replies)
    assert _run(tmp_path)["status"] == "failed"
    assert len(requests) == position + 1


def test_preexisting_name_collision_does_not_request_identity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    requests = _transport(monkeypatch, [(200, {"name": "other", "files": []})])
    assert _run(tmp_path)["error"] == "simple-index-name-or-files-mismatch"
    assert len(requests) == 1


@pytest.mark.parametrize("visible", [True, False])
def test_visibility_retries_only_public_gets_with_one_mint(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, visible: bool
) -> None:
    replies = _replies((404, {})) + [(404, {})] * 11
    replies.append((200, _EMPTY) if visible else (404, {}))
    requests = _transport(monkeypatch, replies)
    result = _run(tmp_path)
    assert result["visibility_attempts"] == 13
    assert result["status"] == ("created-owner-check-required" if visible else "failed")
    assert sum(request.get_method() == "POST" for request in requests) == 1
    assert all(request.get_method() == "GET" for request in requests[4:])


@pytest.mark.parametrize("failure", [OSError(_SECRETS[0]), ValueError(_SECRETS[1])])
def test_transport_failure_never_persists_exception_text(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, failure: Exception
) -> None:
    def request_json(request: urllib.request.Request) -> Reply:
        raise failure

    monkeypatch.setattr(bootstrap, "request_json", request_json)
    assert _run(tmp_path)["status"] == "failed"


def test_cli_never_prints_tokens(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _transport(monkeypatch, _replies())
    monkeypatch.setattr(
        "sys.argv",
        [
            "release_bootstrap.py",
            "--index",
            "testpypi",
            "--project",
            _PROJECT,
            "--output",
            str(tmp_path / "evidence.json"),
        ],
    )
    bootstrap.main()
    captured = capsys.readouterr()
    assert "Owner role" in captured.out
    for secret in _SECRETS:
        assert secret not in captured.out + captured.err


def test_no_redirect_handler_refuses_credential_forwarding() -> None:
    handler = bootstrap.NoRedirect()
    request = urllib.request.Request("https://pypi.org/_/oidc/mint-token")
    assert (
        handler.redirect_request(request, None, 307, "redirect", {}, "https://evil.example") is None
    )


def test_production_index_uses_its_own_audience_and_endpoints(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    replies = _replies()
    replies[1] = (200, {"audience": "pypi"})
    requests = _transport(monkeypatch, replies)
    result = bootstrap.bootstrap("pypi", _PROJECT, tmp_path / "evidence.json")
    assert result["status"] == "created-owner-check-required"
    assert requests[0].full_url == "https://pypi.org/simple/parallax-core/"
    assert requests[2].full_url == _ENDPOINT + "&audience=pypi"
    assert requests[3].full_url == "https://pypi.org/_/oidc/mint-token"


def test_network_transport_never_exposes_remote_error_body() -> None:
    request = urllib.request.Request("https://pypi.org/_/oidc/mint-token")
    error = urllib.error.HTTPError(request.full_url, 403, _SECRETS[2], Message(), None)
    with patch.object(urllib.request, "build_opener") as opener:
        opener.return_value.open.side_effect = error
        assert bootstrap.request_json(request) == (403, {})
        assert isinstance(opener.call_args.args[0], bootstrap.NoRedirect)
        opener.return_value.open.assert_called_once_with(request, timeout=30)


@pytest.mark.parametrize("content", [b"not json", b"[]", b"null"])
def test_network_transport_rejects_malformed_json(content: bytes) -> None:
    request = urllib.request.Request("https://pypi.org/_/oidc/audience")
    with patch.object(urllib.request, "build_opener") as opener:
        opener.return_value.open.return_value.__enter__.return_value.read.return_value = content
        with pytest.raises(bootstrap.BootstrapError):
            bootstrap.request_json(request)


def test_readiness_checks_all_configured_names_without_oidc_or_owner_inference(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS")
    monkeypatch.delenv("ACTIONS_ID_TOKEN_REQUEST_TOKEN")
    monkeypatch.delenv("ACTIONS_ID_TOKEN_REQUEST_URL")
    projects: list[str] = json.loads(bootstrap.CONFIG.read_text())["projects"]
    replies: list[Reply] = [
        (200, {"name": project, "files": [] if index % 2 else [{"filename": "release.whl"}]})
        for index, project in enumerate(projects)
    ]
    requests = _transport(monkeypatch, replies)
    output = tmp_path / "readiness.json"
    result = bootstrap.check_projects("pypi", output)
    assert result["status"] == "projects-present"
    assert result["owner_role_verified"] is False
    assert list(result["projects"]) == projects
    assert [observation["file_count"] for observation in result["projects"].values()] == [
        int(index % 2 == 0) for index in range(len(projects))
    ]
    assert [(request.get_method(), request.full_url) for request in requests] == [
        ("GET", f"https://pypi.org/simple/{project}/") for project in projects
    ]
    assert all(request.get_header("Authorization") is None for request in requests)
    assert json.loads(output.read_text()) == result
    for secret in _SECRETS:
        assert secret not in output.read_text()


@pytest.mark.parametrize(
    "reply",
    [
        (404, {}),
        (500, {"error": _SECRETS[0]}),
        (200, {"name": "wrong-name", "files": []}),
        (200, {"name": _PROJECT, "files": None}),
    ],
)
def test_readiness_refuses_missing_or_invalid_public_project(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, reply: Reply
) -> None:
    requests = _transport(monkeypatch, [reply])
    output = tmp_path / "readiness.json"
    result = bootstrap.check_projects("testpypi", output)
    assert result["status"] == "setup-incomplete"
    assert result["checking_project"] == _PROJECT
    assert result["owner_role_verified"] is False
    assert len(requests) == 1
    assert "error" in result
    assert json.loads(output.read_text()) == result
    for secret in _SECRETS:
        assert secret not in output.read_text()


def test_readiness_cli_succeeds_without_github_runtime(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    projects: list[str] = json.loads(bootstrap.CONFIG.read_text())["projects"]
    _transport(monkeypatch, [(200, {"name": project, "files": []}) for project in projects])
    monkeypatch.delenv("GITHUB_ACTIONS")
    monkeypatch.setattr(
        "sys.argv",
        [
            "release_bootstrap.py",
            "--index",
            "testpypi",
            "--check-projects",
            "--output",
            str(tmp_path / "readiness.json"),
        ],
    )
    bootstrap.main()
    assert "Owner roles were not verified" in capsys.readouterr().out


def test_cli_requires_exactly_one_bootstrap_or_readiness_operation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "release_bootstrap.py",
            "--index",
            "testpypi",
            "--check-projects",
            "--project",
            _PROJECT,
            "--output",
            str(tmp_path / "readiness.json"),
        ],
    )
    with pytest.raises(SystemExit) as error:
        bootstrap.main()
    assert error.value.code == 2
