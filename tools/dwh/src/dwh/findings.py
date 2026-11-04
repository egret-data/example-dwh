"""A lint finding and how it is printed."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, order=True)
class Finding:
    path: str
    code: str
    message: str

    def render(self) -> str:
        return f"{self.path}: {self.code} {self.message}"


def rel(path: Path | str) -> str:
    """`path` relative to the working directory when it is inside it, else absolute."""
    resolved = Path(path).resolve()
    try:
        return str(resolved.relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(resolved)
