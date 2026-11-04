"""The `dwh` command line."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from dwh.findings import Finding
from dwh.validate import validate


def report(findings: Sequence[Finding]) -> int:
    for finding in findings:
        print(finding.render())
    print(f"{len(findings)} finding(s)")
    return 1 if findings else 0


def cmd_validate(args: argparse.Namespace) -> int:
    return report(validate(args.warehouse))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dwh", description="example-dwh design metadata tools")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("validate", help="validate warehouse/*.yml (DWH-Y rules)")
    p.add_argument("--warehouse", type=Path, default=Path("warehouse"))
    p.set_defaults(func=cmd_validate)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
