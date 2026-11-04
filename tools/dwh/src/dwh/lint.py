"""Run lint rules over the warehouse design and the dbt manifest."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from dwh.findings import Finding
from dwh.manifest import Project
from dwh.warehouse import Warehouse


@dataclass(frozen=True)
class Context:
    warehouse: Warehouse
    project: Project


Rule = Callable[[Context], Iterable[Finding]]


def run_lint(ctx: Context, rules: Iterable[Rule] | None = None) -> list[Finding]:
    from dwh.rules import ALL_RULES  # rules import Context from this module

    selected = ALL_RULES if rules is None else list(rules)
    return sorted({finding for rule in selected for finding in rule(ctx)})
