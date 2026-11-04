from pathlib import Path

from dwh.cli import main
from dwh.codes import CODES
from dwh.standards import STANDARD_FILES, check_standards

GOOD_RULE = """### STD-04-01 Durable keys (MUST)

Facts carry the durable key of each dimension.

Correct:

```sql
select customer_key from x
```

Incorrect:

```sql
select customer_sk from x
```

Source: Kimball (The Data Warehouse Toolkit, 3rd ed.) · Alibaba dim-layer · Spec §7
Checked by: DWH-T04, DWH-B04
"""


def write(root: Path, name: str, rules: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / name
    path.write_text(f"# {name}\n\nScope: test.\n\n## Rules\n\n{rules}")
    return path


def codes(findings):
    return [f.code for f in findings]


def test_good_rule_is_clean(tmp_path):
    write(tmp_path, "04-dimensions.md", GOOD_RULE)
    assert check_standards(tmp_path) == []


def test_r02_malformed_heading(tmp_path):
    write(tmp_path, "04-dimensions.md", GOOD_RULE.replace("(MUST)", "(MAY)"))
    assert codes(check_standards(tmp_path)) == ["DWH-R02"]


def test_r02_rule_number_must_match_the_file(tmp_path):
    write(tmp_path, "05-facts.md", GOOD_RULE)
    assert codes(check_standards(tmp_path)) == ["DWH-R02"]


def test_r02_duplicate_rule_id(tmp_path):
    write(tmp_path, "04-dimensions.md", GOOD_RULE + "\n" + GOOD_RULE)
    assert codes(check_standards(tmp_path)) == ["DWH-R02"]


def test_r03_missing_incorrect_example(tmp_path):
    rule = GOOD_RULE.replace("Incorrect:\n\n```sql\nselect customer_sk from x\n```\n", "")
    write(tmp_path, "04-dimensions.md", rule)
    assert codes(check_standards(tmp_path)) == ["DWH-R03"]


def test_r04_missing_source(tmp_path):
    rule = GOOD_RULE.replace(
        "Source: Kimball (The Data Warehouse Toolkit, 3rd ed.) · Alibaba dim-layer · Spec §7\n", ""
    )
    write(tmp_path, "04-dimensions.md", rule)
    assert codes(check_standards(tmp_path)) == ["DWH-R04"]


def test_r04_unknown_alibaba_slug(tmp_path):
    write(tmp_path, "04-dimensions.md", GOOD_RULE.replace("Alibaba dim-layer", "Alibaba dimension-page"))
    assert codes(check_standards(tmp_path)) == ["DWH-R04"]


def test_r05_unknown_lint_code(tmp_path):
    write(tmp_path, "04-dimensions.md", GOOD_RULE.replace("DWH-B04", "DWH-B99"))
    assert codes(check_standards(tmp_path)) == ["DWH-R05"]


def test_headings_inside_code_fences_are_ignored(tmp_path):
    rule = GOOD_RULE.replace("select customer_key from x", "### not a heading\nselect customer_key from x")
    write(tmp_path, "04-dimensions.md", rule)
    assert check_standards(tmp_path) == []


def test_require_all_reports_missing_files_and_uncited_codes(tmp_path):
    write(tmp_path, "04-dimensions.md", GOOD_RULE)

    found = codes(check_standards(tmp_path, require_all=True))

    assert found.count("DWH-R01") == len(STANDARD_FILES) - 1
    uncited = {c for c in CODES if not c.startswith("DWH-R")} - {"DWH-T04", "DWH-B04"}
    assert found.count("DWH-R06") == len(uncited)


def test_cli_check_standards(tmp_path, capsys):
    write(tmp_path, "04-dimensions.md", GOOD_RULE.replace("(MUST)", "(MAY)"))

    rc = main(["check-standards", "--standards", str(tmp_path)])

    assert rc == 1
    assert "DWH-R02" in capsys.readouterr().out
