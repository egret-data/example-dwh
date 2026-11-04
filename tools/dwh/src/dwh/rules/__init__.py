"""Lint rule families. Each module exposes RULES: functions `Context -> Iterable[Finding]`."""

from dwh.rules import docs, layers, naming, sources, testing

FAMILIES = (docs, sources, testing, naming, layers)
ALL_RULES = [rule for family in FAMILIES for rule in family.RULES]
