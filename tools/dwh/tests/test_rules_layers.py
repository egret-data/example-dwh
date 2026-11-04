from fixtures.manifest import good_project


def test_good_project_has_no_l_findings(lint):
    builder, _ = good_project()
    assert lint(builder, prefix="DWH-L") == []


def test_l01_model_outside_a_layer_folder(lint):
    builder, ids = good_project()
    builder.model("stg_orders", "models/staging/stg_orders.sql", deps=[ids["ods_orders"]])
    assert lint(builder, prefix="DWH-L") == ["DWH-L01"]


def test_l02_name_prefix_must_match_the_layer_folder(lint):
    builder, ids = good_project()
    builder.node(ids["ads_customer"])["name"] = "dws_bi_customer_daily"
    assert lint(builder, prefix="DWH-L") == ["DWH-L02"]


def test_l03_only_ods_reads_sources(lint):
    builder, ids = good_project()
    builder.node(ids["dwd_order"])["depends_on"]["nodes"].append(ids["orders"])
    assert lint(builder, prefix="DWH-L") == ["DWH-L03"]


def test_l03_ods_must_not_ref_models(lint):
    builder, ids = good_project()
    builder.node(ids["ods_orders"])["depends_on"]["nodes"].append(ids["ods_customers"])
    assert lint(builder, prefix="DWH-L") == ["DWH-L03"]


def test_l04_dim_must_not_read_dwd(lint):
    builder, ids = good_project()
    builder.model("dim_pub_shop", "models/dim/pub/dim_pub_shop.sql", deps=[ids["dwd_order"]])
    assert lint(builder, prefix="DWH-L") == ["DWH-L04"]


def test_l04_ads_may_read_dwd_only_with_a_written_reason(lint):
    builder, ids = good_project()
    builder.node(ids["ads_customer"])["depends_on"]["nodes"].append(ids["dwd_order"])
    assert lint(builder, prefix="DWH-L") == ["DWH-L04"]

    builder.node(ids["ads_customer"])["meta"]["dwd_reason"] = "Order-level export for the finance app."
    assert lint(builder, prefix="DWH-L") == []


def test_l04_accumulating_snapshot_reads_transaction_facts_not_ods(lint):
    builder, ids = good_project()
    good = builder.model(
        "dwd_trade_shipment_di",
        "models/dwd/trade/dwd_trade_shipment_di.sql",
        deps=[ids["dwd_order"]],
        meta={"process": "shipment"},
    )
    assert lint(builder, prefix="DWH-L") == []

    builder.node(good)["depends_on"]["nodes"].append(ids["ods_orders"])
    assert lint(builder, prefix="DWH-L") == ["DWH-L04"]


def test_l04_snapshot_reads_ods_only(lint):
    builder, ids = good_project()
    builder.snapshot("dim_pub_shop_hist", "snapshots/dim_pub_shop_hist.yml", deps=[ids["dim_customer"]])
    assert lint(builder, prefix="DWH-L") == ["DWH-L04"]


def test_l05_chain_deeper_than_ten(lint):
    builder, ids = good_project()
    previous = ids["ods_customers"]
    for i in range(1, 12):  # dim chain of 11 models
        previous = builder.model(f"dim_pub_c{i}", f"models/dim/pub/dim_pub_c{i}.sql", deps=[previous])
    assert lint(builder, prefix="DWH-L") == ["DWH-L05"]


def test_l05_chain_of_exactly_ten_is_allowed(lint):
    builder, ids = good_project()
    previous = ids["ods_customers"]
    for i in range(1, 11):  # dim chain of 10 models
        previous = builder.model(f"dim_pub_c{i}", f"models/dim/pub/dim_pub_c{i}.sql", deps=[previous])
    assert lint(builder, prefix="DWH-L") == []


def test_l03_ods_must_read_a_source(lint):
    builder, ids = good_project()
    builder.node(ids["ods_orders"])["depends_on"]["nodes"] = []
    assert lint(builder, prefix="DWH-L") == ["DWH-L03"]
