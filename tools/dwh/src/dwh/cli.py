"""The `dwh` command line."""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path, PurePosixPath

from dwh.catalog import write_catalog
from dwh.design_gate import added_concepts, check_gate, load_warehouse_at
from dwh.findings import Finding
from dwh.lint import Context, run_lint
from dwh.manifest import load_manifest
from dwh.scaffold import ScaffoldError, scaffold, write_files
from dwh.standards import check_standards
from dwh.sync_agents import STALE_SUFFIX, SkillError, sync
from dwh.validate import validate
from dwh.warehouse import load_warehouse


def report(findings: Sequence[Finding]) -> int:
    for finding in findings:
        print(finding.render())
    print(f"{len(findings)} finding(s)")
    return 1 if findings else 0


def cmd_validate(args: argparse.Namespace) -> int:
    return report(validate(args.warehouse))


def in_scope(findings: Sequence[Finding], changed: Sequence[str]) -> list[Finding]:
    """Findings on a changed file or in a changed file's folder (a model's .sql and .yml sit together)."""
    files = {PurePosixPath(path).as_posix() for path in changed}
    folders = {str(PurePosixPath(path).parent) for path in files}
    return [f for f in findings if f.path in files or str(PurePosixPath(f.path).parent) in folders]


def cmd_lint(args: argparse.Namespace) -> int:
    findings = validate(args.warehouse)
    if findings:
        return report(findings)  # --select never hides validation findings: the lint rules did not run
    if not args.manifest.is_file():
        print(f"dwh: {args.manifest} not found; run `make manifest` first", file=sys.stderr)
        return 2
    try:
        project = load_manifest(args.manifest, args.project_dir)
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        print(
            f"dwh: {args.manifest} is not a readable dbt manifest ({error!r}); run `make manifest`",
            file=sys.stderr,
        )
        return 2
    findings = run_lint(Context(load_warehouse(args.warehouse), project))
    if args.select:
        findings = [f for f in findings if f.code.startswith(tuple(args.select))]
    if args.changed is not None:
        findings = in_scope(findings, args.changed)
    return report(findings)


def cmd_catalog(args: argparse.Namespace) -> int:
    findings = validate(args.warehouse)
    if findings:
        return report(findings)
    if args.dbt_docs is not None and not args.dbt_docs.is_file():
        print(f"dwh: {args.dbt_docs} not found; run `make catalog`", file=sys.stderr)
        return 2
    index = write_catalog(load_warehouse(args.warehouse), args.out, args.dbt_docs)
    print(f"wrote {index}")
    return 0


def cmd_design_gate(args: argparse.Namespace) -> int:
    repo = args.repo.resolve()
    try:
        warehouse_rel = args.warehouse.resolve().relative_to(repo).as_posix()
    except ValueError:
        print("dwh: --warehouse must be inside --repo", file=sys.stderr)
        return 2
    try:
        base = load_warehouse_at(args.base, warehouse_rel, repo)
    except ValueError as exc:
        print(f"dwh: {exc}", file=sys.stderr)
        return 2
    event = json.loads(args.event.read_text())
    pull_request = event.get("pull_request") or {}
    labels = [label["name"] for label in pull_request.get("labels") or []]
    added = added_concepts(base, load_warehouse(args.warehouse))
    return report(check_gate(added, body=pull_request.get("body") or "", labels=labels, repo_root=repo))


def cmd_check_standards(args: argparse.Namespace) -> int:
    if not args.standards.is_dir():
        print(f"dwh: {args.standards} not found", file=sys.stderr)
        return 2
    return report(check_standards(args.standards, require_all=args.require_all))


def cmd_sync_agents(args: argparse.Namespace) -> int:
    try:
        changed = sync(args.repo, check=args.check)
    except SkillError as exc:
        print(f"dwh: {exc}", file=sys.stderr)
        return 2
    if args.check:
        for relative in changed:
            print(f"out of date: {relative}")
        if changed:
            print("run `make sync-agents` and commit the result")
            return 1
        print("agent files are up to date")
        return 0
    for relative in changed:
        if relative.endswith(STALE_SUFFIX):
            print(f"removed {relative.removesuffix(STALE_SUFFIX)}")
        else:
            print(f"wrote {relative}")
    return 0


def cmd_scaffold(args: argparse.Namespace) -> int:
    findings = validate(args.warehouse)
    if findings:
        return report(findings)
    try:
        files = scaffold(
            args.name,
            load_warehouse(args.warehouse),
            project_dir=args.project_dir,
            grain=args.grain,
            metrics=args.metric,
            upstream=args.upstream,
            watermark=args.watermark,
        )
        if args.write:
            for path in write_files(files, Path(".")):
                print(f"wrote {path}")
            return 0
    except ScaffoldError as exc:
        print(f"dwh: {exc}", file=sys.stderr)
        return 2
    for path, text in files.items():
        print(f"# {path}\n{text}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dwh", description="example-dwh design metadata tools")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("validate", help="validate warehouse/*.yml (DWH-Y rules)")
    p.add_argument("--warehouse", type=Path, default=Path("warehouse"))
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("lint", help="lint the dbt project against the warehouse design")
    p.add_argument("--warehouse", type=Path, default=Path("warehouse"))
    p.add_argument("--manifest", type=Path, default=Path(".dbt/target/manifest.json"))
    p.add_argument(
        "--project-dir", default="dags/dbt", help="dbt project directory, prefixed onto reported paths"
    )
    p.add_argument("--select", nargs="*", default=[], help="only report codes starting with these prefixes")
    p.add_argument(
        "--changed",
        nargs="*",
        default=None,
        metavar="FILE",
        help="only report findings for these files' folders",
    )
    p.set_defaults(func=cmd_lint)

    p = sub.add_parser("design-gate", help="require an approved design for model-extending changes")
    p.add_argument("--base", required=True, help="git ref of the PR base, e.g. origin/main")
    p.add_argument("--event", type=Path, required=True, help="GitHub event JSON ($GITHUB_EVENT_PATH)")
    p.add_argument("--warehouse", type=Path, default=Path("warehouse"))
    p.add_argument("--repo", type=Path, default=Path("."))
    p.set_defaults(func=cmd_design_gate)

    p = sub.add_parser("catalog", help="render the design catalogue as static HTML")
    p.add_argument("--warehouse", type=Path, default=Path("warehouse"))
    p.add_argument("--out", type=Path, default=Path("site"))
    p.add_argument("--dbt-docs", type=Path, default=None, help="dbt's static_index.html to publish alongside")
    p.set_defaults(func=cmd_catalog)

    p = sub.add_parser(
        "check-standards", help="check the rulebook format and its lint-code citations (DWH-R)"
    )
    p.add_argument("--standards", type=Path, default=Path("docs/standards"))
    p.add_argument(
        "--require-all", action="store_true", help="also require every file and every code citation"
    )
    p.set_defaults(func=cmd_check_standards)

    p = sub.add_parser("sync-agents", help="generate per-tool AI files from AGENTS.md and skills/")
    p.add_argument("--repo", type=Path, default=Path("."))
    p.add_argument("--check", action="store_true", help="only report drift (exit 1)")
    p.set_defaults(func=cmd_sync_agents)

    p = sub.add_parser("scaffold", help="generate a model's .sql/.yml (and SCD4 snapshot) from the design")
    p.add_argument("name", help="model name, e.g. dwd_trade_order_di")
    p.add_argument("--from", dest="upstream", nargs="+", default=[], metavar="MODEL")
    p.add_argument("--grain", nargs="+", default=[], metavar="COLUMN")
    p.add_argument("--metric", nargs="+", default=[], metavar="NAME")
    p.add_argument("--watermark", default="updated_at", help="ODS di watermark column")
    p.add_argument("--warehouse", type=Path, default=Path("warehouse"))
    p.add_argument("--project-dir", default="dags/dbt")
    p.add_argument("--write", action="store_true", help="write the files (never overwrites)")
    p.set_defaults(func=cmd_scaffold)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
