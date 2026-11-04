"""Every direct pin in requirements*.txt is pinned identically in its lock file."""

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def pins(path: Path) -> dict[str, str]:
    found = {}
    for raw in path.read_text().splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        name, sep, version = line.partition("==")
        assert sep, f"{path.name}: not pinned with ==: {raw!r}"
        found[canonical(name.split("[", 1)[0])] = version.strip()
    return found


@pytest.mark.parametrize(
    ("requirements", "lock"),
    [("requirements.txt", "requirements.lock"), ("requirements-dbt.txt", "requirements-dbt.lock")],
)
def test_direct_pins_are_locked_at_the_same_version(requirements, lock):
    direct = pins(REPO / requirements)
    locked = pins(REPO / lock)

    for name, version in direct.items():
        assert locked.get(name) == version, (
            f"{name}: {requirements} pins {version}, {lock} has {locked.get(name)}"
        )
