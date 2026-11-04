"""DWH-S: source table metadata (spec §4: load type, watermark, timezone, delete handling)."""

from collections.abc import Iterator
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dwh.findings import Finding
from dwh.lint import Context

LOADS = ("di", "df")
DELETE_HANDLING = ("none", "soft_delete_flag", "full_compare")


def is_timezone(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        return False
    return True


def s01_source_meta(ctx: Context) -> Iterator[Finding]:
    for source in ctx.project.sources.values():
        meta = source.meta
        problems = []
        if meta.get("load") not in LOADS:
            problems.append(f"meta.load must be one of {', '.join(LOADS)}, got {meta.get('load')!r}")
        if not is_timezone(meta.get("timezone")):
            problems.append(f"meta.timezone must be an IANA timezone, got {meta.get('timezone')!r}")
        if meta.get("delete_handling") not in DELETE_HANDLING:
            problems.append(
                f"meta.delete_handling must be one of {', '.join(DELETE_HANDLING)}, "
                f"got {meta.get('delete_handling')!r}"
            )
        if meta.get("load") == "di" and not meta.get("watermark"):
            problems.append("meta.watermark is required for a di load")
        for problem in problems:
            yield Finding(source.path, "DWH-S01", f"{source.source_name}.{source.name}: {problem}")


def s02_di_without_delete_handling(ctx: Context) -> Iterator[Finding]:
    for source in ctx.project.sources.values():
        meta = source.meta
        if (
            meta.get("load") == "di"
            and meta.get("delete_handling") == "none"
            and not meta.get("delete_handling_reason")
        ):
            yield Finding(
                source.path,
                "DWH-S02",
                f"{source.source_name}.{source.name}: a di load cannot see hard deletes; set delete_handling "
                "or explain in meta.delete_handling_reason why rows are never deleted",
            )


RULES = [s01_source_meta, s02_di_without_delete_handling]
