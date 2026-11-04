"""DWH-D: descriptions (spec §7, 09-dbt-conventions: every model and column is described)."""

from collections.abc import Iterator

from dwh.findings import Finding
from dwh.lint import Context


def d01_model_description(ctx: Context) -> Iterator[Finding]:
    for node in ctx.project.nodes.values():
        if not node.description.strip():
            yield Finding(node.path, "DWH-D01", f"{node.name}: model has no description")


def d02_column_description(ctx: Context) -> Iterator[Finding]:
    for node in ctx.project.nodes.values():
        for column in node.columns.values():
            if not column.description.strip():
                yield Finding(node.path, "DWH-D02", f"{node.name}.{column.name}: column has no description")


def d03_source_description(ctx: Context) -> Iterator[Finding]:
    for source in ctx.project.sources.values():
        if not source.description.strip():
            yield Finding(
                source.path, "DWH-D03", f"{source.source_name}.{source.name}: source table has no description"
            )


RULES = [d01_model_description, d02_column_description, d03_source_description]
