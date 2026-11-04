"""DWH-Y02..Y06: consistency of warehouse/*.yml beyond what the JSON Schemas express (DWH-Y01)."""

import re
from collections import Counter
from collections.abc import Iterator

from dwh.findings import Finding
from dwh.warehouse import Warehouse

# Period tokens inside metric names (1d, 30d, 12h, nd, td, hh, mm) are not glossary words.
PERIOD_TOKEN = re.compile(r"^(\d+[dhmw]|nd|td|hh|mm)$")

UNIQUE_COLLECTIONS = (
    ("domains", "domains", "name"),
    ("processes", "processes", "name"),
    ("dimensions", "dimensions", "name"),
    ("modifiers", "modifier_types", "name"),
    ("modifiers", "modifiers", "name"),
    ("periods", "periods", "name"),
    ("glossary", "words", "word"),
    ("bus_matrix", "bus_matrix", "process"),
)


def y02_unique_names(wh: Warehouse) -> Iterator[Finding]:
    for file, key, field in UNIQUE_COLLECTIONS:
        counts = Counter(item[field] for item in wh.items(file, key))
        for name, n in sorted(counts.items()):
            if n > 1:
                yield Finding(wh.path(file), "DWH-Y02", f"{key}: {name!r} is defined {n} times")
    metric_names = Counter(
        metric["name"]
        for section in ("atomic", "derived", "calculated")
        for metric in wh.items("metrics", section)
    )
    for name, n in sorted(metric_names.items()):
        if n > 1:
            yield Finding(wh.path("metrics"), "DWH-Y02", f"metric {name!r} is defined {n} times")


def y03_references(wh: Warehouse) -> Iterator[Finding]:
    domains, processes, dimensions = set(wh.domains), set(wh.processes), set(wh.dimensions)
    metrics = set(wh.atomic) | set(wh.derived) | set(wh.calculated)

    def missing(file: str, where: str, value: str, known: set[str], kind: str) -> Iterator[Finding]:
        if value not in known:
            yield Finding(wh.path(file), "DWH-Y03", f"{where}: unknown {kind} {value!r}")

    for p in wh.items("processes", "processes"):
        yield from missing("processes", f"process {p['name']}", p["domain"], domains, "domain")
    for d in wh.items("dimensions", "dimensions"):
        if d["scope"] != "pub":
            yield from missing("dimensions", f"dimension {d['name']}", d["scope"], domains, "domain (scope)")
    for row in wh.items("bus_matrix", "bus_matrix"):
        yield from missing("bus_matrix", "bus_matrix row", row["process"], processes, "process")
        for cell in row["dimensions"]:
            where = f"bus_matrix row {row['process']}"
            yield from missing("bus_matrix", where, cell["dimension"], dimensions, "dimension")
    for t in wh.items("modifiers", "modifier_types"):
        yield from missing("modifiers", f"modifier type {t['name']}", t["domain"], domains, "domain")
    for m in wh.items("modifiers", "modifiers"):
        yield from missing(
            "modifiers", f"modifier {m['name']}", m["type"], set(wh.modifier_types), "modifier type"
        )
        for p in m["processes"]:
            yield from missing("modifiers", f"modifier {m['name']}", p, processes, "process")
    for a in wh.items("metrics", "atomic"):
        where = f"atomic metric {a['name']}"
        yield from missing("metrics", where, a["process"], processes, "process")
        if "non_additive_dimension" in a:
            yield from missing("metrics", where, a["non_additive_dimension"], dimensions, "dimension")
    for d in wh.items("metrics", "derived"):
        where = f"derived metric {d['name']}"
        yield from missing("metrics", where, d["atomic"], set(wh.atomic), "atomic metric")
        yield from missing("metrics", where, d["period"], set(wh.periods), "period")
        for m in d.get("modifiers", []):
            yield from missing("metrics", where, m, set(wh.modifiers), "modifier")
        for g in d["grain"]:
            yield from missing("metrics", where, g, dimensions, "dimension")
    for c in wh.items("metrics", "calculated"):
        for i in c["inputs"]:
            yield from missing("metrics", f"calculated metric {c['name']}", i, metrics, "metric")


def y04_date_dimension(wh: Warehouse) -> Iterator[Finding]:
    date = wh.dimensions.get("date")
    if date is None or date["scope"] != "pub":
        yield Finding(
            wh.path("dimensions"), "DWH-Y04", "dimension 'date' with scope 'pub' is mandatory (dim_pub_date)"
        )


def name_tokens(name: str) -> list[str]:
    return [token for token in name.split("_") if not PERIOD_TOKEN.match(token)]


def y05_glossary(wh: Warehouse) -> Iterator[Finding]:
    words = wh.words

    def check(file: str, kind: str, name: str) -> Iterator[Finding]:
        for token in name_tokens(name):
            if token not in words:
                yield Finding(wh.path(file), "DWH-Y05", f"{kind} {name}: {token!r} is not in glossary.yml")

    for d in wh.items("domains", "domains"):
        yield from check("domains", "domain", d["name"])
    for p in wh.items("processes", "processes"):
        yield from check("processes", "process", p["name"])
    for d in wh.items("dimensions", "dimensions"):
        yield from check("dimensions", "dimension", d["name"])
        for key in d["natural_key"]:
            yield from check("dimensions", f"dimension {d['name']} natural key", key)
        for attribute in d["attributes"]:
            yield from check("dimensions", f"dimension {d['name']} attribute", attribute["name"])
    for row in wh.items("bus_matrix", "bus_matrix"):
        for cell in row["dimensions"]:
            if "role" in cell:
                yield from check("bus_matrix", f"bus_matrix row {row['process']} role", cell["role"])
    for t in wh.items("modifiers", "modifier_types"):
        yield from check("modifiers", "modifier type", t["name"])
    for m in wh.items("modifiers", "modifiers"):
        yield from check("modifiers", "modifier", m["name"])
    for section in ("atomic", "derived", "calculated"):
        for metric in wh.items("metrics", section):
            yield from check("metrics", f"{section} metric", metric["name"])


def y06_scd1_attributes_are_current(wh: Warehouse) -> Iterator[Finding]:
    for d in wh.items("dimensions", "dimensions"):
        if d["history"] != "scd1":
            continue
        for attribute in d["attributes"]:
            if attribute["history"] == "historical":
                yield Finding(
                    wh.path("dimensions"),
                    "DWH-Y06",
                    f"dimension {d['name']}: attribute {attribute['name']} is historical "
                    "but the dimension is scd1",
                )


YAML_RULES = [
    y02_unique_names,
    y03_references,
    y04_date_dimension,
    y05_glossary,
    y06_scd1_attributes_are_current,
]
