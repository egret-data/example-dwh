"""DWH-T: minimum tests and contracts per layer (spec §7, 09-dbt-conventions)."""

from collections.abc import Iterable, Iterator

from dwh.findings import Finding
from dwh.lint import Context
from dwh.manifest import DataTest

CONTRACT_LAYERS = ("dim", "dwd", "dws")
KEY_RELATIONSHIP_LAYERS = ("dwd", "dws")


def is_uniqueness(test: DataTest) -> bool:
    return (test.name == "unique" and test.namespace is None) or (
        test.name == "unique_combination_of_columns" and test.namespace == "dbt_utils"
    )


def grain_columns(tests: Iterable[DataTest]) -> set[str]:
    columns: set[str] = set()
    for test in tests:
        if test.name == "unique" and test.namespace is None and test.column_name:
            columns.add(test.column_name)
        elif test.name == "unique_combination_of_columns" and test.namespace == "dbt_utils":
            columns.update(test.kwargs.get("combination_of_columns") or [])
    return columns


def t01_grain_test(ctx: Context) -> Iterator[Finding]:
    for node in ctx.project.models():
        if not any(is_uniqueness(t) for t in ctx.project.tests_for(node.unique_id)):
            yield Finding(
                node.path,
                "DWH-T01",
                f"{node.name}: no grain test (unique or dbt_utils.unique_combination_of_columns)",
            )


def t02_grain_columns_not_null(ctx: Context) -> Iterator[Finding]:
    for node in ctx.project.models():
        tests = ctx.project.tests_for(node.unique_id)
        not_null = {t.column_name for t in tests if t.name == "not_null"}
        for column in sorted(grain_columns(tests) - not_null):
            yield Finding(node.path, "DWH-T02", f"{node.name}.{column}: grain column has no not_null test")


def t03_contract(ctx: Context) -> Iterator[Finding]:
    for node in ctx.project.models():
        if node.layer in CONTRACT_LAYERS and not node.contract_enforced:
            yield Finding(
                node.path, "DWH-T03", f"{node.name}: {node.layer} models need contract: {{enforced: true}}"
            )


def t04_key_relationships(ctx: Context) -> Iterator[Finding]:
    for node in ctx.project.models():
        if node.layer not in KEY_RELATIONSHIP_LAYERS:
            continue
        related = {t.column_name for t in ctx.project.tests_for(node.unique_id) if t.name == "relationships"}
        for column in sorted(node.columns):
            if column.endswith("_key") and column not in related:
                yield Finding(
                    node.path,
                    "DWH-T04",
                    f"{node.name}.{column}: key column has no relationships test to its dimension",
                )


RULES = [t01_grain_test, t02_grain_columns_not_null, t03_contract, t04_key_relationships]
