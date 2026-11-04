from dwh.cli import main
from dwh.validate import validate
from fixtures.warehouse import REPO


def codes(findings):
    return [f.code for f in findings]


def test_minimal_fixture_warehouse_is_clean(make_warehouse):
    assert validate(make_warehouse()) == []


def test_repository_warehouse_is_clean():
    assert validate(REPO / "warehouse") == []


def test_y01_missing_file(make_warehouse):
    findings = validate(make_warehouse(drop=["periods"]))

    assert codes(findings) == ["DWH-Y01"]
    assert findings[0].path.endswith("periods.yml")


def test_y01_schema_violation_names_the_field(make_warehouse):
    def mutate(files):
        files["processes"]["processes"][0]["fact_type"] = "weird"

    findings = validate(make_warehouse(mutate=mutate))

    assert codes(findings) == ["DWH-Y01"]
    assert "$.processes[0].fact_type" in findings[0].message


def test_y01_nd_period_requires_days(make_warehouse):
    def mutate(files):
        del files["metrics"]["derived"][1]["days"]

    assert codes(validate(make_warehouse(mutate=mutate))) == ["DWH-Y01"]


def test_y02_duplicate_process(make_warehouse):
    def mutate(files):
        processes = files["processes"]["processes"]
        processes.append(dict(processes[0]))

    assert codes(validate(make_warehouse(mutate=mutate))) == ["DWH-Y02"]


def test_y03_process_with_unknown_domain(make_warehouse):
    def mutate(files):
        files["processes"]["processes"][0]["domain"] = "crm"

    assert codes(validate(make_warehouse(mutate=mutate))) == ["DWH-Y03"]


def test_y03_bus_matrix_with_unknown_dimension(make_warehouse):
    def mutate(files):
        files["bus_matrix"]["bus_matrix"][0]["dimensions"][2]["dimension"] = "store"

    assert codes(validate(make_warehouse(mutate=mutate))) == ["DWH-Y03"]


def test_y03_derived_metric_with_unknown_atomic(make_warehouse):
    def mutate(files):
        files["metrics"]["derived"][0]["atomic"] = "gmv"

    assert codes(validate(make_warehouse(mutate=mutate))) == ["DWH-Y03"]


def test_y04_date_dimension_is_mandatory(make_warehouse):
    def mutate(files):
        dims = files["dimensions"]["dimensions"]
        files["dimensions"]["dimensions"] = [d for d in dims if d["name"] != "date"]

    # The two bus-matrix cells that use `date` also become unknown references.
    assert codes(validate(make_warehouse(mutate=mutate))) == ["DWH-Y03", "DWH-Y03", "DWH-Y04"]


def test_y05_name_token_not_in_glossary(make_warehouse):
    def mutate(files):
        attributes = files["dimensions"]["dimensions"][1]["attributes"]
        attributes.append({"name": "segment", "description": "Segment.", "history": "current"})

    findings = validate(make_warehouse(mutate=mutate))

    assert codes(findings) == ["DWH-Y05"]
    assert "'segment'" in findings[0].message


def test_y06_scd1_dimension_with_historical_attribute(make_warehouse):
    def mutate(files):
        files["dimensions"]["dimensions"][0]["attributes"][0]["history"] = "historical"

    assert codes(validate(make_warehouse(mutate=mutate))) == ["DWH-Y06"]


def test_cli_validate_reports_and_exits_1(make_warehouse, capsys):
    def mutate(files):
        files["dimensions"]["dimensions"][0]["attributes"][0]["history"] = "historical"

    rc = main(["validate", "--warehouse", str(make_warehouse(mutate=mutate))])

    out = capsys.readouterr().out
    assert rc == 1
    assert ": DWH-Y06 " in out
    assert out.strip().endswith("1 finding(s)")


def test_cli_validate_clean_exits_0(make_warehouse, capsys):
    assert main(["validate", "--warehouse", str(make_warehouse())]) == 0
    assert capsys.readouterr().out.strip() == "0 finding(s)"
