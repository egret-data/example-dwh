"""`dwh catalog`: one static HTML page of the design metadata (spec §5), linked to dbt docs."""

import html
import shutil
from collections.abc import Iterable, Sequence
from pathlib import Path

from dwh.warehouse import Warehouse

STYLE = """
body { font-family: system-ui, sans-serif; margin: 2rem auto; max-width: 72rem; padding: 0 1rem; }
table { border-collapse: collapse; width: 100%; margin-bottom: 2rem; font-size: 0.9rem; }
th, td { border: 1px solid #d0d7de; padding: 0.35rem 0.6rem; text-align: left; vertical-align: top; }
th { background: #f6f8fa; }
nav a { margin-right: 1rem; }
"""


def esc(value: object) -> str:
    return html.escape(str(value))


def table(headers: Sequence[str], rows: Iterable[Sequence[object]]) -> str:
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in row) + "</tr>" for row in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def bus_matrix(wh: Warehouse) -> str:
    dimensions = list(wh.dimensions)
    rows = []
    for process, row in wh.bus.items():
        cells: dict[str, list[str]] = {}
        for cell in row["dimensions"]:
            cells.setdefault(cell["dimension"], []).append(cell.get("role", "✓"))
        rows.append([process, *[", ".join(cells.get(d, [])) for d in dimensions]])
    return table(["process", *dimensions], rows)


def period_label(derived: dict) -> str:
    return f"nd ({derived['days']} days)" if derived["period"] == "nd" else derived["period"]


def render_catalog(wh: Warehouse, dbt_docs_link: str | None) -> str:
    sections = [
        (
            "Domains",
            table(
                ["name", "owner", "description"],
                [[d["name"], d["owner"], d["description"]] for d in wh.domains.values()],
            ),
        ),
        (
            "Business processes",
            table(
                ["name", "domain", "fact type", "grain", "description"],
                [
                    [p["name"], p["domain"], p["fact_type"], p["grain"], p["description"]]
                    for p in wh.processes.values()
                ],
            ),
        ),
        (
            "Dimensions",
            table(
                ["name", "scope", "history", "natural key", "attributes"],
                [
                    [
                        d["name"],
                        d["scope"],
                        d["history"],
                        ", ".join(d["natural_key"]),
                        ", ".join(f"{a['name']} ({a['history']})" for a in d["attributes"]),
                    ]
                    for d in wh.dimensions.values()
                ],
            ),
        ),
        ("Bus matrix", bus_matrix(wh)),
        (
            "Atomic metrics",
            table(
                ["name", "process", "aggregation", "additivity", "description"],
                [
                    [a["name"], a["process"], a["aggregation"], a["additivity"], a["description"]]
                    for a in wh.atomic.values()
                ],
            ),
        ),
        (
            "Derived metrics",
            table(
                ["column", "atomic", "period", "modifiers", "grain", "description"],
                [
                    [
                        d["name"],
                        d["atomic"],
                        period_label(d),
                        ", ".join(d.get("modifiers", [])),
                        ", ".join(d["grain"]),
                        d["description"],
                    ]
                    for d in wh.derived.values()
                ],
            ),
        ),
        (
            "Calculated metrics",
            table(
                ["name", "formula", "inputs", "description"],
                [
                    [c["name"], c["formula"], ", ".join(c["inputs"]), c["description"]]
                    for c in wh.calculated.values()
                ],
            ),
        ),
        (
            "Modifiers",
            table(
                ["name", "type", "predicate", "processes", "description"],
                [
                    [m["name"], m["type"], m["predicate"], ", ".join(m["processes"]), m["description"]]
                    for m in wh.modifiers.values()
                ],
            ),
        ),
        (
            "Glossary",
            table(["word", "meaning"], [[w["word"], w["meaning"]] for w in wh.items("glossary", "words")]),
        ),
    ]
    anchors = [title.lower().replace(" ", "-") for title, _ in sections]
    nav = "".join(f'<a href="#{a}">{esc(t)}</a>' for a, (t, _) in zip(anchors, sections, strict=True))
    dbt = (
        f'<p><a href="{esc(dbt_docs_link)}">dbt docs: models, columns and lineage</a></p>'
        if dbt_docs_link
        else ""
    )
    body = "".join(
        f'<h2 id="{a}">{esc(t)}</h2>{content}' for a, (t, content) in zip(anchors, sections, strict=True)
    )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>example-dwh catalogue</title><style>{STYLE}</style></head>"
        f"<body><h1>example-dwh catalogue</h1><nav>{nav}</nav>{dbt}{body}</body></html>"
    )


def write_catalog(wh: Warehouse, out: Path, dbt_docs: Path | None) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    link = None
    if dbt_docs is not None:
        (out / "dbt").mkdir(exist_ok=True)
        shutil.copyfile(dbt_docs, out / "dbt" / "index.html")
        link = "dbt/index.html"
    index = out / "index.html"
    index.write_text(render_catalog(wh, link))
    return index
