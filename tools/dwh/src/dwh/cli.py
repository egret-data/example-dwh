"""The `dwh` command line."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from dwh.findings import Finding
from dwh.lint import Context, run_lint
from dwh.manifest import load_manifest
from dwh.validate import validate
from dwh.warehouse import load_warehouse


def report(findings: Sequence[Finding]) -> int:
    for finding in findings:
        print(finding.render())
    print(f"{len(findings)} finding(s)")
    return 1 if findings else 0


def cmd_validate(args: argparse.Namespace) -> int:
    return report(validate(args.warehouse))


def cmd_lint(args: argparse.Namespace) -> int:
    findings = validate(args.warehouse)
    if not findings:
        if not args.manifest.is_file():
            print(f"dwh: {args.manifest} not found; run `make manifest` first", file=sys.stderr)
            return 2
        findings = run_lint(Context(load_warehouse(args.warehouse), load_manifest(args.manifest)))
    if args.select:
        findings = [f for f in findings if f.code.startswith(tuple(args.select))]
    return report(findings)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dwh", description="example-dwh design metadata tools")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("validate", help="validate warehouse/*.yml (DWH-Y rules)")
    p.add_argument("--warehouse", type=Path, default=Path("warehouse"))
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("lint", help="lint the dbt project against the warehouse design")
    p.add_argument("--warehouse", type=Path, default=Path("warehouse"))
    p.add_argument("--manifest", type=Path, default=Path(".dbt/target/manifest.json"))
    p.add_argument("--select", nargs="*", default=[], help="only report codes starting with these prefixes")
    p.set_defaults(func=cmd_lint)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
