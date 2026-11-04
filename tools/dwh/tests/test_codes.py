"""Every code the rules can emit is registered, and every registered code is emitted somewhere."""

import re
from pathlib import Path

from dwh.codes import CODES

SRC = Path(__file__).resolve().parents[1] / "src" / "dwh"
CODE = re.compile(r"\"(DWH-[A-Z]\d\d)\"")


def emitted_codes() -> set[str]:
    found = set()
    for path in SRC.rglob("*.py"):
        if path.name != "codes.py":
            found.update(CODE.findall(path.read_text()))
    return found


def test_every_emitted_code_is_registered():
    assert emitted_codes() - set(CODES) == set()


def test_every_registered_code_is_emitted():
    assert set(CODES) - emitted_codes() == set()


def test_meanings_are_one_line():
    assert all(meaning and "\n" not in meaning for meaning in CODES.values())
