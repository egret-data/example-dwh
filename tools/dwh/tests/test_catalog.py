from dwh.catalog import render_catalog, write_catalog
from dwh.cli import main
from dwh.warehouse import load_warehouse


def test_catalog_shows_bus_matrix_metrics_and_glossary(make_warehouse):
    page = render_catalog(load_warehouse(make_warehouse()), dbt_docs_link=None)

    assert "<th>customer</th>" in page
    assert "<td>order_date</td>" in page  # role name in the bus matrix cell
    assert "<td>app_order_amt_sum_30d</td>" in page
    assert "<td>nd (30 days)</td>" in page
    assert "<td>avg_order_amt_1d</td>" in page
    assert "dbt docs" not in page


def test_catalog_escapes_html(make_warehouse):
    def mutate(files):
        files["domains"]["domains"][0]["description"] = "<script>alert(1)</script>"

    page = render_catalog(load_warehouse(make_warehouse(mutate=mutate)), dbt_docs_link=None)

    assert "&lt;script&gt;" in page
    assert "<script>alert" not in page


def test_write_catalog_copies_and_links_dbt_docs(make_warehouse, tmp_path):
    docs = tmp_path / "static_index.html"
    docs.write_text("<html>dbt</html>")

    index = write_catalog(load_warehouse(make_warehouse()), tmp_path / "site", dbt_docs=docs)

    assert (tmp_path / "site" / "dbt" / "index.html").read_text() == "<html>dbt</html>"
    assert 'href="dbt/index.html"' in index.read_text()


def test_cli_catalog_writes_the_page(make_warehouse, tmp_path):
    rc = main(["catalog", "--warehouse", str(make_warehouse()), "--out", str(tmp_path / "site")])

    assert rc == 0
    assert (tmp_path / "site" / "index.html").is_file()


def test_cli_catalog_refuses_invalid_yaml(make_warehouse, tmp_path, capsys):
    rc = main(
        ["catalog", "--warehouse", str(make_warehouse(drop=["periods"])), "--out", str(tmp_path / "site")]
    )

    assert rc == 1
    assert "DWH-Y01" in capsys.readouterr().out
