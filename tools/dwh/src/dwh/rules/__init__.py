"""Lint rule families. Each module exposes RULES: functions `Context -> Iterable[Finding]`."""

from dwh.rules import docs, sources, testing

FAMILIES = (docs, sources, testing)
ALL_RULES = [rule for family in FAMILIES for rule in family.RULES]
