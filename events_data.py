"""
События (рекламные кампании) из Event Calendar: загрузка, пересечение с периодом, продажи по целевой группе.
"""
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from report_data import _parse_date, sales_in_period

EVENTS_CSV = Path(__file__).resolve().parent / "data" / "events.csv"

# Ключевые слова для маппинга колонок (нижний регистр)
COL_NAME = ("название", "company", "название компании")
COL_DATE_START = ("дата начала", "дата начла", "date start", "start")
COL_DATE_END = ("дата конца", "date end", "end")
COL_BUDGET = ("бюджет на день", "бюджет", "budget")
COL_CAMPAIGN_TYPE = ("тип рекламной", "тип рекламной компании", "campaign type")
COL_SALES_TARGET = ("sales target", "sales target")
COL_PRODUCT_TYPE = ("product type", "product type")
COL_COST = ("сумма затрат", "затрат", "cost")


def _find_column(df: pd.DataFrame, keywords: tuple[str, ...]) -> str | None:
    """Возвращает имя первой колонки, содержащей любое из ключевых слов."""
    for col in df.columns:
        lower = str(col).strip().lower()
        for kw in keywords:
            if kw in lower:
                return col
    return None


def _to_float(val) -> float | None:
    if pd.isna(val) or val == "" or val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace(" ", "").replace("\u00a0", "").replace(",", ".")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def load_events_df(csv_path: Path | None = None) -> pd.DataFrame:
    """Загружает events.csv и нормализует колонки по ключевым словам."""
    path = csv_path or EVENTS_CSV
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, encoding="utf-8-sig")
    df.columns = [str(c).strip() for c in df.columns]
    return df


# Порядок колонок в Event Calendar (если по ключевым словам не нашли)
EVENT_COLUMN_INDEX = {
    "name": 0,
    "date_start": 1,
    "date_end": 2,
    "budget_per_day": 3,
    "campaign_type": 4,
    "sales_target": 5,
    "product_type": 6,
    "cost_total": 10,  # первая «Сумма затрат»
}


def parse_events(csv_path: Path | None = None) -> list[dict[str, Any]]:
    """
    Парсит events.csv в список событий: name, date_start, date_end, campaign_type,
    sales_target, product_type, budget_per_day, cost_total.
    Строки без даты начала пропускаются.
    """
    df = load_events_df(csv_path)
    if df.empty:
        return []

    cols = df.columns
    col_name = _find_column(df, COL_NAME) or (cols[0] if len(cols) > 0 else None)
    col_start = _find_column(df, COL_DATE_START) or (cols[EVENT_COLUMN_INDEX["date_start"]] if len(cols) > EVENT_COLUMN_INDEX["date_start"] else None)
    col_end = _find_column(df, COL_DATE_END) or (cols[EVENT_COLUMN_INDEX["date_end"]] if len(cols) > EVENT_COLUMN_INDEX["date_end"] else None)
    col_budget = _find_column(df, COL_BUDGET) or (cols[EVENT_COLUMN_INDEX["budget_per_day"]] if len(cols) > EVENT_COLUMN_INDEX["budget_per_day"] else None)
    col_campaign = _find_column(df, COL_CAMPAIGN_TYPE) or (cols[EVENT_COLUMN_INDEX["campaign_type"]] if len(cols) > EVENT_COLUMN_INDEX["campaign_type"] else None)
    col_target = _find_column(df, COL_SALES_TARGET) or (cols[EVENT_COLUMN_INDEX["sales_target"]] if len(cols) > EVENT_COLUMN_INDEX["sales_target"] else None)
    col_pt = _find_column(df, COL_PRODUCT_TYPE) or (cols[EVENT_COLUMN_INDEX["product_type"]] if len(cols) > EVENT_COLUMN_INDEX["product_type"] else None)
    col_cost = _find_column(df, COL_COST) or (cols[EVENT_COLUMN_INDEX["cost_total"]] if len(cols) > EVENT_COLUMN_INDEX["cost_total"] else None)

    events = []
    for _, row in df.iterrows():
        if col_start is None:
            continue
        start_val = row.get(col_start)
        dt_start = _parse_date(start_val)
        if dt_start is None:
            continue
        date_start = dt_start.date() if hasattr(dt_start, "date") else dt_start

        end_val = row.get(col_end) if col_end else None
        dt_end = _parse_date(end_val)
        date_end = dt_end.date() if dt_end and hasattr(dt_end, "date") else date_start

        name = str(row.get(col_name, "") or "").strip() or "—"
        campaign_type = str(row.get(col_campaign, "") or "").strip() if col_campaign else ""
        sales_target = str(row.get(col_target, "") or "").strip() if col_target else ""
        product_type = str(row.get(col_pt, "") or "").strip() if col_pt else ""
        budget_per_day = str(row.get(col_budget, "") or "").strip() if col_budget else ""
        cost_total = _to_float(row.get(col_cost)) if col_cost else None
        if cost_total is not None and cost_total <= 0:
            cost_total = None

        events.append({
            "name": name,
            "date_start": date_start.isoformat(),
            "date_end": date_end.isoformat(),
            "campaign_type": campaign_type,
            "sales_target": sales_target or None,
            "product_type": product_type or None,
            "budget_per_day": budget_per_day or None,
            "cost_total": cost_total,
        })
    return events


def _monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _period_bounds(ref: date, period: str) -> tuple[date, date]:
    """Возвращает (period_start, period_end) для 7d или 4w."""
    if period == "4w":
        # 4 недели: понедельник (ref - 3 недели) .. ref
        period_start = _monday_of(ref) - timedelta(weeks=3)
        period_end = ref
    else:
        # 7d: ref-6 .. ref
        period_start = ref - timedelta(days=6)
        period_end = ref
    return period_start, period_end


def _overlap(
    ev_start: date, ev_end: date, period_start: date, period_end: date
) -> tuple[date, date] | None:
    """Пересечение [ev_start, ev_end] с [period_start, period_end]. None если нет пересечения."""
    if ev_end < period_start or ev_start > period_end:
        return None
    return (
        max(ev_start, period_start),
        min(ev_end, period_end),
    )


def get_events_with_sales(
    reference_date: str | date,
    period: str = "7d",
    csv_path: Path | None = None,
) -> dict[str, Any]:
    """
    Вариант 1: события, пересекающиеся с периодом (7d или 4w), и продажи по целевой группе за период пересечения.
    """
    ref = reference_date if isinstance(reference_date, date) else date.fromisoformat(str(reference_date)[:10])
    period_start, period_end = _period_bounds(ref, period)
    events_raw = parse_events(csv_path)

    result_events = []
    for ev in events_raw:
        ev_start = date.fromisoformat(ev["date_start"])
        ev_end = date.fromisoformat(ev["date_end"])
        overlap = _overlap(ev_start, ev_end, period_start, period_end)
        if overlap is None:
            continue
        overlap_start, overlap_end = overlap

        sales = sales_in_period(
            overlap_start,
            overlap_end,
            sales_channel=ev.get("sales_target"),
            product_type=ev.get("product_type"),
            csv_path=csv_path,
        )

        result_events.append({
            **ev,
            "overlap_start": overlap_start.isoformat(),
            "overlap_end": overlap_end.isoformat(),
            "sales_during": sales,
        })

    return {
        "reference_date": ref.isoformat(),
        "period": period,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "events": result_events,
    }


def get_events_analysis(
    reference_date: str | date,
    period: str = "7d",
    csv_path: Path | None = None,
) -> dict[str, Any]:
    """
    Вариант 3: события за период + продажи во время пересечения, за N дней до старта события, прирост, ROI.
    """
    ref = reference_date if isinstance(reference_date, date) else date.fromisoformat(str(reference_date)[:10])
    period_start, period_end = _period_bounds(ref, period)
    events_raw = parse_events(csv_path)

    result_events = []
    for ev in events_raw:
        ev_start = date.fromisoformat(ev["date_start"])
        ev_end = date.fromisoformat(ev["date_end"])
        overlap = _overlap(ev_start, ev_end, period_start, period_end)
        if overlap is None:
            continue
        overlap_start, overlap_end = overlap
        days_count = (overlap_end - overlap_start).days + 1

        sales_during = sales_in_period(
            overlap_start, overlap_end,
            sales_channel=ev.get("sales_target"),
            product_type=ev.get("product_type"),
            csv_path=csv_path,
        )

        before_end = ev_start - timedelta(days=1)
        before_start = before_end - timedelta(days=days_count - 1)
        sales_before = sales_in_period(
            before_start, before_end,
            sales_channel=ev.get("sales_target"),
            product_type=ev.get("product_type"),
            csv_path=csv_path,
        )

        rev_during = sales_during["total_revenue"]
        rev_before = sales_before["total_revenue"]
        revenue_change = round(rev_during - rev_before, 2)
        revenue_change_pct = round((revenue_change / rev_before * 100), 1) if rev_before else 0.0
        roi = None
        cost_total = ev.get("cost_total")
        if cost_total and cost_total > 0 and revenue_change is not None:
            roi = round(revenue_change / cost_total, 2)

        result_events.append({
            **ev,
            "overlap_start": overlap_start.isoformat(),
            "overlap_end": overlap_end.isoformat(),
            "days_count": days_count,
            "sales_during": sales_during,
            "sales_before": sales_before,
            "revenue_change": revenue_change,
            "revenue_change_pct": revenue_change_pct,
            "roi": roi,
        })

    return {
        "reference_date": ref.isoformat(),
        "period": period,
        "events": result_events,
    }
