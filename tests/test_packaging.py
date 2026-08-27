"""Guard against shipping an image that is missing a module.

The adapters import extraction and rules *by name*. If a package is left out
of the image, nothing fails at build time - the adapter just falls back and
the container serves a healthy /health while producing no verdicts. That is
the worst kind of break, so it is checked here.
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = REPO_ROOT / "Dockerfile"

#: Packages the backend reaches through an adapter at runtime.
ADAPTER_PACKAGES = ("backend", "extraction", "rules")


def _active_copy_targets() -> set[str]:
    """Packages copied by a live (non-commented) COPY instruction."""
    targets: set[str] = set()
    for raw in DOCKERFILE.read_text().splitlines():
        line = raw.strip()
        if line.startswith("#") or not line.upper().startswith("COPY "):
            continue
        source = line.split()[1]
        targets.add(source.rstrip("/"))
    return targets


@pytest.mark.parametrize("package", ADAPTER_PACKAGES)
def test_dockerfile_copies_every_adapter_package(package: str) -> None:
    assert package in _active_copy_targets(), (
        f"Dockerfile does not COPY {package}/. The image would build and run, "
        f"but its adapter would silently fall back."
    )


@pytest.mark.parametrize("package", ADAPTER_PACKAGES)
def test_adapter_packages_exist(package: str) -> None:
    assert (REPO_ROOT / package).is_dir()


def test_dockerignore_does_not_exclude_adapter_packages() -> None:
    ignored = {
        line.strip().rstrip("/")
        for line in (REPO_ROOT / ".dockerignore").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }
    assert not ignored.intersection(ADAPTER_PACKAGES)
