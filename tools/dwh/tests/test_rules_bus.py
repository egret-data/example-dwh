from fixtures.manifest import good_project


def test_good_project_has_no_b_findings(lint):
    builder, _ = good_project()
    assert lint(builder, prefix="DWH-B") == []


def test_b01_dwd_without_process(lint):
    builder, ids = good_project()
    builder.node(ids["dwd_order"])["meta"].pop("process")
    assert lint(builder, prefix="DWH-B") == ["DWH-B01"]


def test_b01_dwd_with_unknown_process(lint):
    builder, ids = good_project()
    builder.node(ids["dwd_order"])["meta"]["process"] = "refund"
    assert lint(builder, prefix="DWH-B") == ["DWH-B01"]


def test_b02_dwd_name_must_match_its_process(lint):
    builder, ids = good_project()
    builder.node(ids["dwd_order"])["meta"]["process"] = "shipment"
    assert lint(builder, prefix="DWH-B") == ["DWH-B02"]


def test_b03_process_must_have_a_bus_matrix_row(lint):
    builder, _ = good_project()

    def mutate(files):
        rows = files["bus_matrix"]["bus_matrix"]
        files["bus_matrix"]["bus_matrix"] = [r for r in rows if r["process"] != "order"]

    assert lint(builder, mutate=mutate, prefix="DWH-B") == ["DWH-B03"]


def test_b04_key_column_must_be_a_bus_matrix_dimension_or_role(lint):
    builder, ids = good_project()
    builder.node(ids["dwd_order"])["columns"]["seller_key"] = {
        "name": "seller_key",
        "description": "S.",
        "meta": {},
    }
    assert lint(builder, prefix="DWH-B") == ["DWH-B04"]


def test_b04_role_names_are_accepted(lint):
    builder, ids = good_project()
    builder.node(ids["dwd_order"])["columns"]["order_date_key"] = {
        "name": "order_date_key",
        "description": "Order date.",
        "meta": {},
    }
    assert lint(builder, prefix="DWH-B") == []
