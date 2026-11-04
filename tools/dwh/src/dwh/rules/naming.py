"""DWH-N: model and column naming (spec §7, 02-naming)."""

import re
from collections.abc import Iterator

from dwh.findings import Finding
from dwh.lint import Context
from dwh.manifest import LAYERS, Node

PERIODS = ("1d", "nd", "td", "1w", "hh", "mm")
_TOKENS = r"[a-z0-9]+(?:_[a-z0-9]+)*"

PATTERNS = {
    "ods": re.compile(rf"^ods_(?P<source>[a-z0-9]+)_(?P<table>{_TOKENS})_(?P<load>di|df)$"),
    "dim": re.compile(r"^dim_(?P<scope>[a-z0-9]+)_(?P<dimension>[a-z0-9]+(?:_[a-z0-9]+)*?)(?P<hist>_hist)?$"),
    "dwd": re.compile(rf"^dwd_(?P<domain>[a-z0-9]+)_(?P<process>{_TOKENS})_(?P<load>di|df)$"),
    "dws": re.compile(rf"^dws_(?P<domain>[a-z0-9]+)_(?P<grain>{_TOKENS})_(?P<period>{'|'.join(PERIODS)})$"),
    "ads": re.compile(
        rf"^ads_(?P<app>[a-z0-9]+)_(?P<subject>[a-z0-9]+(?:_[a-z0-9]+)*?)(?:_(?P<period>{'|'.join(PERIODS)}))?$"
    ),
}
TEMPLATES = {
    "ods": "ods_{source}_{table}_{di|df}",
    "dim": "dim_{pub|domain}_{dimension}[_hist]",
    "dwd": "dwd_{domain}_{process}_{di|df}",
    "dws": "dws_{domain}_{grain}[_{custom}]_{1d|nd|td|1w|hh|mm}",
    "ads": "ads_{app}_{subject}[_{1d|nd|td|1w|hh|mm}]",
}
GLOSSARY_LAYERS = ("dim", "dwd", "dws", "ads")
IGNORED_TOKENS = {*LAYERS, "di", "df", "pub", "hist", *PERIODS}
NUMERIC_PERIOD = re.compile(r"^\d+[dhmw]$")


def parse_name(node: Node) -> dict[str, str] | None:
    pattern = PATTERNS.get(node.layer or "")
    match = pattern.match(node.name) if pattern else None
    return match.groupdict() if match else None


def unknown_tokens(name: str, words: set[str]) -> list[str]:
    return [
        t
        for t in name.split("_")
        if t not in IGNORED_TOKENS and not NUMERIC_PERIOD.match(t) and t not in words
    ]


def n01_name_pattern(ctx: Context) -> Iterator[Finding]:
    for node in ctx.project.nodes.values():
        bad_period = node.layer == "ads" and NUMERIC_PERIOD.match(node.name.rsplit("_", 1)[-1])
        if node.layer and (parse_name(node) is None or (bad_period and not parse_name(node)["period"])):
            yield Finding(
                node.path, "DWH-N01", f"{node.name}: {node.layer} names follow {TEMPLATES[node.layer]}"
            )


def n02_ods_source_segment(ctx: Context) -> Iterator[Finding]:
    for node in ctx.project.nodes.values():
        parsed = parse_name(node) if node.layer == "ods" else None
        if parsed is None:
            continue
        sources = {s.source_name for s in ctx.project.source_deps(node)}
        if parsed["source"] != node.folder or sources - {parsed["source"]}:
            yield Finding(
                node.path,
                "DWH-N02",
                f"{node.name}: source segment {parsed['source']!r} must match its folder "
                f"models/ods/{node.folder}/ and the source() it reads",
            )


def n03_domain_segment(ctx: Context) -> Iterator[Finding]:
    domains = set(ctx.warehouse.domains)
    for node in ctx.project.nodes.values():
        parsed = parse_name(node)
        if parsed is None:
            continue
        if node.layer == "dim" and parsed["scope"] != "pub" and parsed["scope"] not in domains:
            yield Finding(
                node.path, "DWH-N03", f"{node.name}: scope {parsed['scope']!r} is neither pub nor a domain"
            )
        elif node.layer in ("dwd", "dws") and parsed["domain"] not in domains:
            yield Finding(
                node.path, "DWH-N03", f"{node.name}: {parsed['domain']!r} is not a domain in domains.yml"
            )


def n04_history_tables(ctx: Context) -> Iterator[Finding]:
    for node in ctx.project.nodes.values():
        parsed = parse_name(node) if node.layer == "dim" else None
        if parsed is None:
            continue
        if node.resource_type == "snapshot" and not parsed["hist"]:
            yield Finding(
                node.path, "DWH-N04", f"{node.name}: snapshots build SCD4 history tables named dim_..._hist"
            )
        elif node.resource_type == "model" and parsed["hist"]:
            yield Finding(node.path, "DWH-N04", f"{node.name}: only snapshots produce _hist tables")


def n05_name_glossary(ctx: Context) -> Iterator[Finding]:
    words = ctx.warehouse.words
    for node in ctx.project.nodes.values():
        if node.layer in GLOSSARY_LAYERS:
            for token in unknown_tokens(node.name, words):
                yield Finding(node.path, "DWH-N05", f"{node.name}: {token!r} is not in glossary.yml")


def n06_column_glossary(ctx: Context) -> Iterator[Finding]:
    words = ctx.warehouse.words
    for node in ctx.project.nodes.values():
        if node.layer not in GLOSSARY_LAYERS:
            continue
        for column in node.columns:
            for token in unknown_tokens(column, words):
                yield Finding(node.path, "DWH-N06", f"{node.name}.{column}: {token!r} is not in glossary.yml")


RULES = [
    n01_name_pattern,
    n02_ods_source_segment,
    n03_domain_segment,
    n04_history_tables,
    n05_name_glossary,
    n06_column_glossary,
]
