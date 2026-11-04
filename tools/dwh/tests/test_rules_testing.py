from fixtures.manifest import good_project


def test_good_project_has_no_t_findings(lint):
    builder, _ = good_project()
    assert lint(builder, prefix="DWH-T") == []


def test_t01_model_without_grain_test(lint):
    builder, ids = good_project()
    for uid in builder.find_tests(ids["dim_customer"], "unique"):
        builder.remove(uid)
    assert lint(builder, prefix="DWH-T") == ["DWH-T01"]


def test_t02_grain_column_without_not_null(lint):
    builder, ids = good_project()
    for uid in builder.find_tests(ids["dws_customer"], "not_null", column="customer_key"):
        builder.remove(uid)
    assert lint(builder, prefix="DWH-T") == ["DWH-T02"]


def test_t03_contract_required_on_dim_dwd_dws(lint):
    builder, ids = good_project()
    builder.node(ids["dwd_order"])["contract"]["enforced"] = False
    assert lint(builder, prefix="DWH-T") == ["DWH-T03"]


def test_t03_not_required_on_ods_and_ads(lint):
    builder, ids = good_project()
    assert builder.node(ids["ads_customer"])["contract"]["enforced"] is False
    assert builder.node(ids["ods_orders"])["contract"]["enforced"] is False
    assert lint(builder, prefix="DWH-T") == []


def test_t04_key_column_without_relationships_test(lint):
    builder, ids = good_project()
    for uid in builder.find_tests(ids["dwd_order"], "relationships"):
        builder.remove(uid)
    assert lint(builder, prefix="DWH-T") == ["DWH-T04"]
