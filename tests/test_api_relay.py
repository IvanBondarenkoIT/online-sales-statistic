"""
Тесты цепочки ретрансляции: refresh-by-key → sales-table / data-status.
"""
from datetime import datetime
from unittest.mock import patch

import pandas as pd
import pytest

from fetch_sheet import FetchResult


API_KEY = "test-export-key"
SAMPLE_ROWS = [
    {
        "Date": "21.04.2026",
        "Sales channel": "WOLT",
        "Product Type": "Purges",
        "Total Amount": "42",
    },
    {
        "Date": "21.4.26",
        "Sales channel": "Website",
        "Product Type": "Purges",
        "Total Amount": "46,99",
    },
    {
        "Date": "21.04.2026",
        "Sales channel": "Telephone",
        "Product Type": "Coffee",
        "Total Amount": "2310",
    },
    {
        "Date": "21.4.26",
        "Sales channel": "WOLT",
        "Product Type": "Purges",
        "Total Amount": "77",
    },
    {
        "Date": "21.4.26",
        "Sales channel": "WOLT",
        "Product Type": "Purges",
        "Total Amount": "42",
    },
    {
        "Date": "21.4.26",
        "Sales channel": "Website",
        "Product Type": "Purges",
        "Total Amount": "126,65",
    },
    {
        "Date": "21.4.2026",
        "Sales channel": "Facebook",
        "Product Type": "Capsules",
        "Total Amount": "480",
    },
    {
        "Date": "21.04.2026",
        "Sales channel": "WOLT",
        "Product Type": "Purges",
        "Total Amount": "42",
    },
]


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("API_EXPORT_KEY", API_KEY)
    monkeypatch.setenv("SECRET_KEY", "test-secret")

    import app as app_module
    import report_data

    csv_path = tmp_path / "online_sales.csv"
    monkeypatch.setattr(report_data, "DATA_CSV", csv_path)
    monkeypatch.setattr(app_module, "DATA_CSV", csv_path)

    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as test_client:
        yield test_client, csv_path


def _sample_fetch_result() -> FetchResult:
    return FetchResult(
        df=pd.DataFrame(SAMPLE_ROWS),
        sheets_loaded=7,
        sheets_failed=0,
        failed_gids=[],
    )


def _auth_headers():
    return {"X-API-Key": API_KEY}


def test_sales_table_without_key_returns_401(client):
    test_client, _ = client
    resp = test_client.get("/api/sales-table?date=2026-04-21")
    assert resp.status_code == 401


def test_sales_table_empty_csv_reports_data_loaded_false(client):
    test_client, _ = client
    resp = test_client.get("/api/sales-table?date=2026-04-21", headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["count"] == 0
    assert data["data_loaded"] is False
    assert "refresh-by-key" in data["hint"]


def test_refresh_by_key_empty_fetch_returns_500_and_keeps_old_csv(client):
    test_client, csv_path = client
    csv_path.write_text(
        "Date,Total Amount,Sales channel,Product Type\n"
        "21.04.2026,99,WOLT,Purges\n",
        encoding="utf-8-sig",
    )
    old_content = csv_path.read_text(encoding="utf-8-sig")

    with patch("fetch_sheet.fetch_via_csv_export", side_effect=Exception("network down")):
        resp = test_client.post("/api/refresh-by-key", headers=_auth_headers())

    assert resp.status_code == 500
    assert resp.get_json()["ok"] is False
    assert csv_path.read_text(encoding="utf-8-sig") == old_content


def test_refresh_by_key_success_returns_metadata(client):
    test_client, csv_path = client
    with patch("fetch_sheet.fetch_via_csv_export", return_value=_sample_fetch_result()):
        resp = test_client.post("/api/refresh-by-key", headers=_auth_headers())

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["rows"] == 8
    assert data["sheets_loaded"] == 7
    assert data["max_date"] == "2026-04-21"
    assert csv_path.exists()


def test_sales_table_after_refresh_returns_eight_rows(client):
    test_client, _ = client
    with patch("fetch_sheet.fetch_via_csv_export", return_value=_sample_fetch_result()):
        refresh = test_client.post("/api/refresh-by-key", headers=_auth_headers())
        assert refresh.status_code == 200

    resp = test_client.get("/api/sales-table?date=2026-04-21", headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["data_loaded"] is True
    assert data["count"] == 8
    assert len(data["rows"]) == 8


def test_data_status_endpoint(client):
    test_client, _ = client
    with patch("fetch_sheet.fetch_via_csv_export", return_value=_sample_fetch_result()):
        test_client.post("/api/refresh-by-key", headers=_auth_headers())

    resp = test_client.get("/api/data-status", headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["data_loaded"] is True
    assert data["row_count"] == 8
    assert data["max_date"] == "2026-04-21"
    assert data["file_mtime"] is not None


def test_sales_table_refresh_query_triggers_reload(client):
    test_client, _ = client
    with patch("fetch_sheet.fetch_via_csv_export", return_value=_sample_fetch_result()) as mock_fetch:
        resp = test_client.get(
            "/api/sales-table?date=2026-04-21&refresh=1",
            headers=_auth_headers(),
        )

    assert mock_fetch.called
    assert resp.status_code == 200
    assert resp.get_json()["count"] == 8
