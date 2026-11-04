from __future__ import annotations

import platform

import pytest

import wheel_build


def test_every_supported_runtime_has_the_complete_native_platform_matrix() -> None:
    cells = wheel_build.matrix()
    expected = {
        "manylinux2014-x86_64",
        "manylinux_2_28-aarch64",
        "musllinux-x86_64",
        "musllinux-aarch64",
        "macos-arm64",
        "macos-x86_64",
        "windows-amd64",
    }
    assert len(cells) == 14
    for runtime in ("3.14", "3.15"):
        assert {cell["id"] for cell in cells if cell["python"] == runtime} == expected
    arm_linux = [
        cell for cell in cells if cell["platform"] == "linux" and cell["arch"] == "aarch64"
    ]
    assert all(cell["runner"] == "ubuntu-24.04-arm" for cell in arm_linux)


def test_an_emulated_linux_arm_build_is_refused_before_building(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setattr(platform, "machine", lambda: "x86_64")
    target = next(target for target in wheel_build.targets() if target["id"] == "musllinux-aarch64")
    with pytest.raises(ValueError, match="native aarch64 runner required"):
        wheel_build._native(target, "3.15")
