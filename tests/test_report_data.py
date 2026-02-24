"""
Тесты загрузки и агрегации данных отчёта (report_data).
Проверяем: наличие CSV, парсинг дат и сумм, структуру build_report.
"""
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from report_data import (
    DATA_CSV,
    build_report,
    load_sales_df,
)


def test_load_sales_df_uses_default_path():
    """Загрузка идёт из data/online_sales.csv по умолчанию."""
    df = load_sales_df()
    # Либо пустой (файла нет), либо с колонками
    assert isinstance(df, pd.DataFrame)
    if not df.empty:
        assert "_date" in df.columns
        assert "_total" in df.columns


def test_load_sales_df_returns_empty_for_missing_file():
    """При отсутствии файла возвращается пустой DataFrame."""
    path = Path("/nonexistent/online_sales.csv")
    df = load_sales_df(csv_path=path)
    assert isinstance(df, pd.DataFrame)
    assert df.empty


def test_load_sales_df_normalizes_columns():
    """Проверка: после загрузки есть нормализованные колонки Date, Total Amount, Sales channel, Product Type."""
    if not DATA_CSV.exists():
        pytest.skip("data/online_sales.csv отсутствует — запустите fetch_sheet.py")
    df = load_sales_df()
    assert not df.empty, "Ожидаются данные в data/online_sales.csv"
    for col in ("Date", "Total Amount", "Sales channel", "Product Type"):
        assert col in df.columns, f"Ожидается колонка: {col}"


def test_build_report_has_expected_structure_when_data_exists():
    """При наличии данных отчёт содержит reference_date, summary_7d, by_day, by_week, by_channel, product_types_available."""
    if not DATA_CSV.exists():
        pytest.skip("data/online_sales.csv отсутствует")
    report = build_report(reference_date="2026-02-17")
    assert "reference_date" in report
    assert "summary_7d" in report
    assert "summary_4w" in report
    assert "by_day" in report
    assert "by_week" in report
    assert "by_channel" in report
    assert "by_product_type" in report
    assert "product_types_available" in report
    assert report["reference_date"] == "2026-02-17"
    assert "total_revenue" in report["summary_7d"]
    assert "orders_count" in report["summary_7d"]
    assert len(report["by_day"]) == 7
    assert len(report["by_week"]) == 4


def test_build_report_empty_csv_returns_empty_structure():
    """При пустом CSV отчёт возвращает нулевые агрегаты и пустые списки."""
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(b"Date,Total Amount,Sales channel,Product Type\n")
        path = Path(f.name)
    try:
        report = build_report(reference_date="2026-02-17", csv_path=path)
        assert report["summary_7d"]["total_revenue"] == 0
        assert report["summary_7d"]["orders_count"] == 0
        assert report["by_day"] == [] or all(d["revenue"] == 0 and d["orders"] == 0 for d in report["by_day"])
    finally:
        path.unlink(missing_ok=True)


def test_build_report_with_exclude_filters_product_types():
    """Параметр exclude_product_types исключает указанные типы товаров из агрегатов."""
    if not DATA_CSV.exists():
        pytest.skip("data/online_sales.csv отсутствует")
    report_full = build_report(reference_date="2026-02-17")
    report_excluded = build_report(
        reference_date="2026-02-17",
        exclude_product_types=["Coffee", "Purges"],
    )
    # Исключение части товаров должно уменьшить выручку (если такие типы есть)
    rev_full = report_full["summary_7d"]["total_revenue"]
    rev_excl = report_excluded["summary_7d"]["total_revenue"]
    assert rev_excl <= rev_full
