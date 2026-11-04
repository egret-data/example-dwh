from fixtures.manifest import good_project


def test_good_project_has_no_d_findings(lint):
    builder, _ = good_project()
    assert lint(builder, prefix="DWH-D") == []


def test_d01_model_without_description(lint):
    builder, ids = good_project()
    builder.node(ids["dwd_order"])["description"] = "  "
    assert lint(builder, prefix="DWH-D") == ["DWH-D01"]


def test_d02_column_without_description(lint):
    builder, ids = good_project()
    builder.node(ids["dim_customer"])["columns"]["city"]["description"] = ""
    assert lint(builder, prefix="DWH-D") == ["DWH-D02"]


def test_d03_source_table_without_description(lint):
    builder, ids = good_project()
    builder.source_node(ids["orders"])["description"] = ""
    assert lint(builder, prefix="DWH-D") == ["DWH-D03"]
