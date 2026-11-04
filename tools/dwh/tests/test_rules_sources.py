import pytest

from fixtures.manifest import good_project


def test_good_project_has_no_s_findings(lint):
    builder, _ = good_project()
    assert lint(builder, prefix="DWH-S") == []


@pytest.mark.parametrize(
    "change",
    [
        {"timezone": None},
        {"timezone": "Mars/Base"},
        {"load": "hourly"},
        {"delete_handling": "ignore"},
        {"watermark": None},
    ],
)
def test_s01_incomplete_or_invalid_source_meta(lint, change):
    builder, ids = good_project()
    meta = builder.source_node(ids["orders"])["meta"]
    for key, value in change.items():
        if value is None:
            meta.pop(key)
        else:
            meta[key] = value
    assert lint(builder, prefix="DWH-S") == ["DWH-S01"]


def test_s01_df_source_needs_no_watermark(lint):
    builder, ids = good_project()
    assert "watermark" not in builder.source_node(ids["customers"])["meta"]
    assert lint(builder, prefix="DWH-S") == []


def test_s02_di_source_without_delete_handling_needs_a_reason(lint):
    builder, ids = good_project()
    builder.source_node(ids["orders"])["meta"]["delete_handling"] = "none"
    assert lint(builder, prefix="DWH-S") == ["DWH-S02"]

    builder.source_node(ids["orders"])["meta"]["delete_handling_reason"] = "Rows are never deleted."
    assert lint(builder, prefix="DWH-S") == []
