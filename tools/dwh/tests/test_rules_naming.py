from fixtures.manifest import good_project


def test_good_project_has_no_n_findings(lint):
    builder, _ = good_project()
    assert lint(builder, prefix="DWH-N") == []


def test_n01_dwd_name_without_load_suffix(lint):
    builder, ids = good_project()
    builder.node(ids["dwd_order"])["name"] = "dwd_trade_order"
    assert lint(builder, prefix="DWH-N") == ["DWH-N01"]


def test_n01_ads_name_without_subject(lint):
    builder, ids = good_project()
    builder.node(ids["ads_customer"])["name"] = "ads_bi"
    assert lint(builder, prefix="DWH-N") == ["DWH-N01"]


def test_n02_ods_source_segment_must_match_folder_and_source(lint):
    builder, ids = good_project()
    builder.node(ids["ods_orders"])["name"] = "ods_crm_orders_di"
    assert lint(builder, prefix="DWH-N") == ["DWH-N02"]


def test_n03_dim_scope_must_be_pub_or_a_domain(lint):
    builder, ids = good_project()
    node = builder.node(ids["dim_customer"])
    node["name"], node["original_file_path"] = "dim_crm_customer", "models/dim/crm/dim_crm_customer.sql"
    # `crm` is also not a glossary word.
    assert lint(builder, prefix="DWH-N") == ["DWH-N03", "DWH-N05"]


def test_n04_snapshot_must_be_a_hist_table(lint):
    builder, ids = good_project()
    builder.node(ids["hist"])["name"] = "dim_pub_city"
    assert lint(builder, prefix="DWH-N") == ["DWH-N04"]


def test_n04_only_snapshots_produce_hist_tables(lint):
    builder, ids = good_project()
    builder.node(ids["dim_customer"])["name"] = "dim_pub_customer_hist"
    assert lint(builder, prefix="DWH-N") == ["DWH-N04"]


def test_n05_name_token_not_in_glossary(lint):
    builder, ids = good_project()
    builder.node(ids["dws_customer"])["name"] = "dws_trade_buyer_segment_1d"
    assert lint(builder, prefix="DWH-N") == ["DWH-N05"]


def test_n06_column_token_not_in_glossary(lint):
    builder, ids = good_project()
    builder.node(ids["dwd_order"])["columns"]["order_segment"] = {
        "name": "order_segment",
        "description": "Segment.",
        "meta": {},
    }
    assert lint(builder, prefix="DWH-N") == ["DWH-N06"]


def test_ods_columns_are_exempt_from_the_glossary(lint):
    builder, ids = good_project()
    builder.node(ids["ods_orders"])["columns"]["weird_col"] = {
        "name": "weird_col",
        "description": "X.",
        "meta": {},
    }
    assert lint(builder, prefix="DWH-N") == []


def test_ads_name_may_end_in_a_period(lint):
    builder, ids = good_project()
    builder.node(ids["ads_customer"])["name"] = "ads_bi_customer_1d"
    assert lint(builder, prefix="DWH-N") == []


def test_n01_ads_period_suffix_must_be_a_known_period(lint):
    builder, ids = good_project()
    builder.node(ids["ads_customer"])["name"] = "ads_bi_customer_7d"
    assert lint(builder, prefix="DWH-N") == ["DWH-N01"]


def test_n02_ods_folder_must_match_the_source_segment(lint):
    builder, ids = good_project()
    builder.node(ids["ods_orders"])["original_file_path"] = "models/ods/crm/ods_shop_orders_di.sql"
    assert lint(builder, prefix="DWH-N") == ["DWH-N02"]


def test_n02_ods_must_read_the_source_named_in_its_name(lint):
    builder, ids = good_project()
    crm = builder.source(
        "crm",
        "orders",
        meta={"timezone": "Asia/Ho_Chi_Minh", "load": "df", "delete_handling": "none"},
    )
    builder.node(ids["ods_orders"])["depends_on"]["nodes"] = [crm]
    assert lint(builder, prefix="DWH-N") == ["DWH-N02"]
