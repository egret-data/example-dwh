import copy
import json
import subprocess

import yaml

from dwh.cli import main
from dwh.design_gate import added_concepts, check_gate, load_warehouse_at
from dwh.warehouse import Warehouse, load_warehouse
from fixtures.warehouse import MINIMAL, write_warehouse


def warehouse(mutate=None) -> Warehouse:
    data = copy.deepcopy(MINIMAL)
    if mutate:
        mutate(data)
    return Warehouse(root=None, data=data)


def add_crm(files):
    files["domains"]["domains"].append({"name": "crm", "description": "CRM.", "owner": "data-eng"})
    files["processes"]["processes"].append(
        {
            "name": "visit",
            "domain": "crm",
            "description": "A visit.",
            "fact_type": "transaction",
            "grain": "One row per visit.",
        }
    )
    files["metrics"]["atomic"].append(
        {
            "name": "visit",
            "process": "visit",
            "description": "Visits.",
            "aggregation": "count",
            "additivity": "additive",
        }
    )


def test_added_concepts_lists_new_domains_processes_dimensions_and_atomic_metrics():
    assert added_concepts(warehouse(), warehouse(add_crm)) == [
        "domain crm",
        "process visit",
        "atomic metric visit",
    ]


def test_reuse_changes_add_no_concepts():
    def add_derived(files):
        files["metrics"]["derived"].append(
            {
                "name": "order_amt_sum_td",
                "atomic": "order_amt",
                "period": "td",
                "grain": ["customer"],
                "description": "Lifetime order amount.",
            }
        )

    assert added_concepts(warehouse(), warehouse(add_derived)) == []


def test_gate_passes_with_label_and_existing_design_record(tmp_path):
    (tmp_path / "docs" / "designs").mkdir(parents=True)
    (tmp_path / "docs" / "designs" / "2026-11-05-crm.md").write_text("# CRM\n")

    findings = check_gate(
        ["domain crm"],
        body="Design: docs/designs/2026-11-05-crm.md",
        labels=["design-approved"],
        repo_root=tmp_path,
    )

    assert findings == []


def test_gate_requires_the_label(tmp_path):
    (tmp_path / "docs" / "designs").mkdir(parents=True)
    (tmp_path / "docs" / "designs" / "x.md").write_text("# X\n")

    findings = check_gate(["domain crm"], body="docs/designs/x.md", labels=[], repo_root=tmp_path)

    assert [f.code for f in findings] == ["DWH-G01"]


def test_gate_requires_a_link_to_an_existing_design_record(tmp_path):
    findings = check_gate(
        ["domain crm"], body="see docs/designs/missing.md", labels=["design-approved"], repo_root=tmp_path
    )

    assert [f.code for f in findings] == ["DWH-G02"]


def test_gate_is_silent_without_additions(tmp_path):
    assert check_gate([], body="", labels=[], repo_root=tmp_path) == []


def git(repo, *args):
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        check=True,
        capture_output=True,
    )


def test_load_warehouse_at_reads_the_base_commit_and_cli_end_to_end(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    write_warehouse(repo / "warehouse")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base")
    base = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()
    data = load_warehouse(repo / "warehouse").data
    add_crm(data)
    for name in ("domains", "processes", "metrics"):
        (repo / "warehouse" / f"{name}.yml").write_text(yaml.safe_dump(data[name], sort_keys=False))

    assert "crm" not in load_warehouse_at(base, "warehouse", repo).domains

    event = tmp_path / "event.json"
    event.write_text(json.dumps({"pull_request": {"body": "no design", "labels": []}}))
    rc = main(
        [
            "design-gate",
            "--base",
            base,
            "--event",
            str(event),
            "--warehouse",
            str(repo / "warehouse"),
            "--repo",
            str(repo),
        ]
    )

    out = capsys.readouterr().out
    assert rc == 1
    assert "DWH-G01" in out
    assert "DWH-G02" in out


def test_cli_rejects_an_unknown_base_ref(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    write_warehouse(repo / "warehouse")
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"pull_request": {"body": "", "labels": []}}))

    rc = main(
        [
            "design-gate",
            "--base",
            "no-such-ref",
            "--event",
            str(event),
            "--warehouse",
            str(repo / "warehouse"),
            "--repo",
            str(repo),
        ]
    )

    assert rc == 2
    assert "no-such-ref" in capsys.readouterr().err


def test_gate_rejects_a_path_traversal_link(tmp_path):
    (tmp_path / "docs" / "designs").mkdir(parents=True)
    (tmp_path / "README.md").write_text("# readme\n")

    findings = check_gate(
        ["domain crm"], body="docs/designs/../../README.md", labels=["design-approved"], repo_root=tmp_path
    )

    assert [f.code for f in findings] == ["DWH-G02"]


def test_gate_rejects_a_symlink_leaving_docs_designs(tmp_path):
    (tmp_path / "docs" / "designs").mkdir(parents=True)
    (tmp_path / "outside.md").write_text("# outside\n")
    (tmp_path / "docs" / "designs" / "evil.md").symlink_to(tmp_path / "outside.md")

    findings = check_gate(
        ["domain crm"], body="docs/designs/evil.md", labels=["design-approved"], repo_root=tmp_path
    )

    assert [f.code for f in findings] == ["DWH-G02"]


def test_gate_rejects_a_link_that_is_part_of_a_url(tmp_path):
    (tmp_path / "docs" / "designs").mkdir(parents=True)
    (tmp_path / "docs" / "designs" / "a.md").write_text("# A\n")

    findings = check_gate(
        ["domain crm"],
        body="https://example.com/docs/designs/a.md",
        labels=["design-approved"],
        repo_root=tmp_path,
    )

    assert [f.code for f in findings] == ["DWH-G02"]


def test_added_concepts_reports_a_new_dimension():
    def add_dimension(files):
        files["dimensions"]["dimensions"].append(
            {"name": "store", "description": "Store.", "scd_type": 1, "attributes": []}
        )

    assert added_concepts(warehouse(), warehouse(add_dimension)) == ["dimension store"]


def make_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    write_warehouse(repo / "warehouse")
    (repo / "docs" / "designs").mkdir(parents=True)
    (repo / "docs" / "designs" / "crm.md").write_text("# CRM\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base")
    base = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()
    return repo, base


def run_gate(tmp_path, repo, base, event_body, warehouse_dir=None):
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"pull_request": event_body}))
    return main(
        [
            "design-gate",
            "--base",
            base,
            "--event",
            str(event),
            "--warehouse",
            str(warehouse_dir or repo / "warehouse"),
            "--repo",
            str(repo),
        ]
    )


def test_cli_passes_with_label_and_design_link(tmp_path, capsys):
    repo, base = make_repo(tmp_path)
    data = load_warehouse(repo / "warehouse").data
    add_crm(data)
    for name in ("domains", "processes", "metrics"):
        (repo / "warehouse" / f"{name}.yml").write_text(yaml.safe_dump(data[name], sort_keys=False))
    body = {"body": "Design: docs/designs/crm.md", "labels": [{"name": "design-approved"}]}

    assert run_gate(tmp_path, repo, base, body) == 0


def test_cli_rejects_a_warehouse_outside_the_repo(tmp_path, capsys):
    repo, base = make_repo(tmp_path)
    outside = tmp_path / "elsewhere"
    write_warehouse(outside)

    rc = run_gate(tmp_path, repo, base, {"body": "", "labels": []}, warehouse_dir=outside)

    assert rc == 2
    assert "--warehouse must be inside --repo" in capsys.readouterr().err


def test_cli_rejects_malformed_base_yaml(tmp_path, capsys):
    repo, _ = make_repo(tmp_path)
    (repo / "warehouse" / "domains.yml").write_text("domains: [unclosed\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "broken")
    broken = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()

    rc = run_gate(tmp_path, repo, broken, {"body": "", "labels": []})

    assert rc == 2
    assert "dwh:" in capsys.readouterr().err
