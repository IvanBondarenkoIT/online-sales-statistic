"""
Тесты загрузки данных из Google Таблицы (fetch_sheet).
Проверяем: доступ по export URL, структуру полученного DataFrame.
"""
import pytest
import requests
import pandas as pd

from config import SHEET_GIDS, csv_export_url, SPREADSHEET_ID
from fetch_sheet import FetchResult, fetch_via_csv_export, _fetch_one_sheet, _normalize_columns


def test_config_has_spreadsheet_id_and_gids():
    """В config заданы SPREADSHEET_ID и хотя бы один SHEET_GIDS."""
    assert SPREADSHEET_ID
    assert isinstance(SHEET_GIDS, list)
    assert len(SHEET_GIDS) >= 1


def test_csv_export_url_format():
    """URL экспорта содержит ID таблицы и gid."""
    url = csv_export_url(667824329)
    assert SPREADSHEET_ID in url
    assert "format=csv" in url
    assert "gid=667824329" in url


@pytest.mark.integration
def test_fetch_one_sheet_returns_dataframe():
    """Один лист по gid скачивается и парсится в DataFrame (интеграционный тест — нужен доступ в сеть и к таблице)."""
    gid = SHEET_GIDS[0]
    try:
        df = _fetch_one_sheet(gid)
    except requests.RequestException as e:
        pytest.skip(f"Нет доступа к таблице или сеть: {e}")
    assert not df.empty
    df = _normalize_columns(df)
    # Ожидаем колонки, как в реальном CSV
    cols_lower = [str(c).lower() for c in df.columns]
    assert any("date" in c for c in cols_lower)
    assert any("total" in c and "amount" in c for c in cols_lower)


@pytest.mark.integration
def test_fetch_via_csv_export_returns_combined_data():
    """fetch_via_csv_export возвращает объединённую таблицу с данными (интеграционный тест)."""
    try:
        result = fetch_via_csv_export()
    except requests.RequestException as e:
        pytest.skip(f"Нет доступа к таблице или сеть: {e}")
    assert isinstance(result, FetchResult)
    df = result.df
    assert isinstance(df, pd.DataFrame)
    assert not df.empty, "Ожидаются данные из хотя бы одной вкладки"
    # Проверка, что есть столбцы с датой и суммой
    df.columns = [str(c).strip() for c in df.columns]
    has_date = any("date" in c.lower() for c in df.columns)
    has_amount = any("total amount" in c.lower() or "totalamount" in c.lower() for c in df.columns)
    assert has_date, f"Ожидается колонка с датой, есть: {list(df.columns)}"
    assert has_amount, f"Ожидается колонка Total Amount, есть: {list(df.columns)}"
