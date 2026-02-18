"""
Загрузка и агрегация данных для отчёта по онлайн-продажам.
Поддержка фильтра по периоду и нормализация полей из CSV.
"""
import re
from datetime import datetime, timedelta, date
from pathlib import Path

import pandas as pd

DATA_CSV = Path(__file__).resolve().parent / "data" / "online_sales.csv"

# Форматы дат в таблице: 02.02.2026, 2.2.2026, 15.2.26
DATE_FORMATS = ["%d.%m.%Y", "%d.%m.%y"]


def _parse_date(s) -> datetime | None:
    if pd.isna(s) or not str(s).strip():
        return None
    s = str(s).strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    # Попытка без ведущих нулей (Windows-style %#d не везде есть)
    m = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{2,4})$", s)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000
        try:
            return datetime(y, mo, d)
        except ValueError:
            pass
    return None


def _to_float(val):
    if pd.isna(val) or val == "" or val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace(" ", "").replace("\u00a0", "")
    s = s.replace(",", ".")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def load_sales_df(csv_path: Path | None = None) -> pd.DataFrame:
    """Загружает CSV, нормализует имена столбцов и типы."""
    path = csv_path or DATA_CSV
    if not path.exists():
        return pd.DataFrame()

    df = pd.read_csv(path, encoding="utf-8-sig")
    # Убираем пробелы и табы в названиях столбцов
    df.columns = [str(c).strip() for c in df.columns]

    # Унифицируем ключевые имена (на случай разных экспортов)
    col_map = {}
    for c in df.columns:
        lower = c.lower()
        if "total amount" in lower or "totalamount" in lower:
            col_map[c] = "Total Amount"
        elif "date" in lower:
            col_map[c] = "Date"
        elif "sales channel" in lower:
            col_map[c] = "Sales channel"
        elif "product type" in lower:
            col_map[c] = "Product Type"
    df = df.rename(columns=col_map)

    if "Date" in df.columns:
        df["_date"] = df["Date"].apply(_parse_date)
        df = df[df["_date"].notna()].copy()
    if "Total Amount" in df.columns:
        df["_total"] = df["Total Amount"].apply(_to_float)
        df = df[df["_total"].notna()].copy()
    return df


def filter_by_period(
    df: pd.DataFrame,
    date_from: datetime | str | None = None,
    date_to: datetime | str | None = None,
) -> pd.DataFrame:
    """Фильтр по периоду (включительно)."""
    if df.empty or "_date" not in df.columns:
        return df
    if date_from is not None:
        if isinstance(date_from, str):
            date_from = _parse_date(date_from) or datetime.min
        df = df[df["_date"] >= date_from]
    if date_to is not None:
        if isinstance(date_to, str):
            date_to = _parse_date(date_to) or datetime.max
        df = df[df["_date"] <= date_to]
    return df


def _monday_of(d: date) -> date:
    """Понедельник недели, содержащей дату d."""
    return d - timedelta(days=d.weekday())


def _last_7_days(df: pd.DataFrame, ref: date) -> list[dict]:
    """Последние 7 дней относительно ref (ref - 6 .. ref включительно). Все 7 дней в выводе, отсутствующие — 0."""
    start = ref - timedelta(days=6)
    df = df.copy()
    df["_d"] = df["_date"].dt.date
    df = df[(df["_d"] >= start) & (df["_d"] <= ref)]
    agg = df.groupby("_d").agg(revenue=("_total", "sum"), orders=("_total", "count")).reset_index()
    by_d = agg.set_index("_d").to_dict("index")
    result = []
    for i in range(7):
        d = start + timedelta(days=i)
        row = by_d.get(d, {"revenue": 0, "orders": 0})
        result.append({
            "date": str(d),
            "label": d.strftime("%d.%m"),
            "revenue": float(row.get("revenue", 0)),
            "orders": int(row.get("orders", 0)),
        })
    return result


def _last_4_weeks(df: pd.DataFrame, ref: date) -> list[dict]:
    """4 недели (Пн–Вс), относительно недели, содержащей ref. Недели от старых к новым."""
    df = df.copy()
    df["_d"] = df["_date"].dt.date
    result = []
    for i in range(3, -1, -1):  # 3, 2, 1, 0 — от самой старой недели к текущей
        monday = _monday_of(ref) - timedelta(weeks=i)
        end = monday + timedelta(days=6)
        week_df = df[(df["_d"] >= monday) & (df["_d"] <= end)]
        rev = week_df["_total"].sum()
        cnt = len(week_df)
        result.append({
            "date": str(monday),
            "label": f"{monday.strftime('%d.%m')}–{end.strftime('%d.%m')}",
            "revenue": float(rev),
            "orders": int(cnt),
        })
    return result


def _prev_7_days(df: pd.DataFrame, ref: date) -> dict:
    """Предыдущие 7 дней (ref-13 .. ref-7). Для сравнения с последними 7 днями."""
    start = ref - timedelta(days=13)
    end = ref - timedelta(days=7)
    df = df.copy()
    df["_d"] = df["_date"].dt.date
    df = df[(df["_d"] >= start) & (df["_d"] <= end)]
    return {"total_revenue": float(round(df["_total"].sum(), 2)), "orders_count": len(df)}


def _prev_4_weeks(df: pd.DataFrame, ref: date) -> dict:
    """4 недели до текущего блока (недели -4 .. -1 относительно недели ref)."""
    df = df.copy()
    df["_d"] = df["_date"].dt.date
    total_rev = 0.0
    total_ord = 0
    for i in range(4, 0, -1):  # 4, 3, 2, 1 — предыдущие 4 недели
        monday = _monday_of(ref) - timedelta(weeks=i)
        end = monday + timedelta(days=6)
        week_df = df[(df["_d"] >= monday) & (df["_d"] <= end)]
        total_rev += week_df["_total"].sum()
        total_ord += len(week_df)
    return {"total_revenue": float(round(total_rev, 2)), "orders_count": total_ord}


def _weekly_trend(df: pd.DataFrame, ref: date, num_weeks: int = 8) -> list[dict]:
    """Выручка по неделям за последние num_weeks (для графика тренда). От старых к новым."""
    df = df.copy()
    df["_d"] = df["_date"].dt.date
    result = []
    for i in range(num_weeks - 1, -1, -1):  # от 7 недель назад до текущей
        monday = _monday_of(ref) - timedelta(weeks=i)
        end = monday + timedelta(days=6)
        week_df = df[(df["_d"] >= monday) & (df["_d"] <= end)]
        rev = week_df["_total"].sum()
        cnt = len(week_df)
        result.append({
            "label": monday.strftime("%d.%m"),
            "revenue": float(rev),
            "orders": int(cnt),
        })
    return result


def _aggregate_by_day(df: pd.DataFrame, date_from_dt: datetime, date_to_dt: datetime) -> tuple[list[dict], str]:
    """
    Агрегат по времени: при большом периоде — по неделям или месяцам.
    Возвращает (список {date, label, revenue, orders}, group_by: "day"|"week"|"month").
    """
    span_days = (date_to_dt - date_from_dt).days + 1
    if span_days > 31:
        df = df.copy()
        df["_period"] = df["_date"].dt.to_period("M").dt.start_time.dt.date
        group_col = "_period"
        group_by = "month"
    elif span_days > 14:
        df = df.copy()
        df["_period"] = (df["_date"] - pd.to_timedelta(df["_date"].dt.weekday, unit="d")).dt.date
        group_col = "_period"
        group_by = "week"
    else:
        df = df.copy()
        df["_period"] = df["_date"].dt.date
        group_col = "_period"
        group_by = "day"

    agg = df.groupby(group_col).agg(revenue=("_total", "sum"), orders=("_total", "count")).reset_index()
    agg = agg.sort_values(group_col)
    result = []
    for _, r in agg.iterrows():
        d = r[group_col]
        if not isinstance(d, date) and hasattr(d, "date"):
            d = d.date()
        elif not isinstance(d, date):
            d = date.fromisoformat(str(d)[:10])
        if group_by == "day":
            label = d.strftime("%d.%m")
        elif group_by == "week":
            end = d + timedelta(days=6)
            label = f"{d.strftime('%d.%m')}–{end.strftime('%d.%m')}"
        else:
            label = d.strftime("%m.%Y")
        result.append({"date": str(d), "label": label, "revenue": float(r["revenue"]), "orders": int(r["orders"])})
    return result, group_by


def _parse_reference_date(s: str | None) -> date:
    """Парсит дату YYYY-MM-DD; при пустом/ошибке — сегодня."""
    if not s or not str(s).strip():
        return date.today()
    try:
        return date.fromisoformat(str(s).strip()[:10])
    except ValueError:
        return date.today()


def build_report(
    date_from: str | None = None,
    date_to: str | None = None,
    reference_date: str | None = None,
    exclude_product_types: list[str] | None = None,
    csv_path: Path | None = None,
) -> dict:
    """
    Строит агрегаты для дашборда.
    Если задан reference_date (одна дата, по умолчанию сегодня):
      - by_day = последние 7 дней (ref-6 .. ref);
      - by_week = 4 недели (Пн–Вс) относительно недели ref;
      - summary_7d и summary_4w.
    Иначе — старый режим по date_from/date_to с масштабированием по периоду.
    """
    use_ref = reference_date is not None and str(reference_date).strip()
    ref = _parse_reference_date(reference_date) if use_ref else None

    df = load_sales_df(csv_path)

    if use_ref and ref is not None:
        # Режим «на дату»: последние 7 дней + 4 недели + данные для аналитики (8 недель назад)
        week_start = _monday_of(ref) - timedelta(weeks=7)  # 8 недель для тренда и сравнений
        date_from_dt = datetime.combine(week_start, datetime.min.time())
        date_to_dt = datetime.combine(ref, datetime.max.time())
        df = filter_by_period(df, date_from_dt, date_to_dt)
    else:
        df = filter_by_period(df, date_from, date_to)

    product_types_raw = df["Product Type"].dropna().astype(str).str.strip()
    product_types_raw = product_types_raw[product_types_raw != ""]
    product_types_available = sorted(product_types_raw.unique().tolist())

    if exclude_product_types:
        exclude_set = {x.strip() for x in exclude_product_types if x and str(x).strip()}
        df = df[~product_types_raw.isin(exclude_set)].copy()

    if df.empty:
        empty = {
            "summary": {"total_revenue": 0, "orders_count": 0, "date_from": None, "date_to": None},
            "by_day": [],
            "by_day_group": "day",
            "by_channel": [],
            "by_product_type": [],
            "product_types_available": product_types_available,
        }
        if use_ref:
            empty["reference_date"] = ref.isoformat() if ref else None
            empty["summary_7d"] = {"total_revenue": 0, "orders_count": 0}
            empty["summary_4w"] = {"total_revenue": 0, "orders_count": 0}
            empty["prev_7d"] = {"total_revenue": 0, "orders_count": 0}
            empty["prev_4w"] = {"total_revenue": 0, "orders_count": 0}
            empty["by_week"] = []
            empty["weekly_trend"] = []
        return empty

    if use_ref and ref is not None:
        by_day = _last_7_days(df, ref)
        by_week = _last_4_weeks(df, ref)
        summary_7d = {"total_revenue": float(round(sum(d["revenue"] for d in by_day), 2)), "orders_count": sum(d["orders"] for d in by_day)}
        summary_4w = {"total_revenue": float(round(sum(d["revenue"] for d in by_week), 2)), "orders_count": sum(d["orders"] for d in by_week)}
        prev_7d = _prev_7_days(df, ref)
        prev_4w = _prev_4_weeks(df, ref)
        weekly_trend = _weekly_trend(df, ref, 8)
        ch = df.groupby(df["Sales channel"].fillna("—").astype(str))["_total"].sum().reset_index()
        ch.columns = ["channel", "revenue"]
        by_channel = [{"channel": r["channel"], "revenue": float(r["revenue"])} for _, r in ch.sort_values("revenue", ascending=False).iterrows()]
        pt = df.groupby(df["Product Type"].fillna("—").astype(str))["_total"].sum().reset_index()
        pt.columns = ["product_type", "revenue"]
        by_product_type = [{"product_type": r["product_type"], "revenue": float(r["revenue"])} for _, r in pt.sort_values("revenue", ascending=False).iterrows()]
        return {
            "reference_date": ref.isoformat(),
            "summary_7d": summary_7d,
            "summary_4w": summary_4w,
            "prev_7d": prev_7d,
            "prev_4w": prev_4w,
            "weekly_trend": weekly_trend,
            "by_day": by_day,
            "by_week": by_week,
            "by_channel": by_channel,
            "by_product_type": by_product_type,
            "product_types_available": product_types_available,
        }
    # Старый режим: date_from / date_to
    total_revenue = df["_total"].sum()
    orders_count = len(df)
    dates = df["_date"]
    date_from_dt = dates.min()
    date_to_dt = dates.max()
    by_day, by_day_group = _aggregate_by_day(df, date_from_dt, date_to_dt)
    ch = df.groupby(df["Sales channel"].fillna("—").astype(str))["_total"].sum().reset_index()
    ch.columns = ["channel", "revenue"]
    by_channel = [{"channel": r["channel"], "revenue": float(r["revenue"])} for _, r in ch.sort_values("revenue", ascending=False).iterrows()]
    pt = df.groupby(df["Product Type"].fillna("—").astype(str))["_total"].sum().reset_index()
    pt.columns = ["product_type", "revenue"]
    by_product_type = [{"product_type": r["product_type"], "revenue": float(r["revenue"])} for _, r in pt.sort_values("revenue", ascending=False).iterrows()]
    return {
        "summary": {
            "total_revenue": float(round(total_revenue, 2)),
            "orders_count": int(orders_count),
            "date_from": date_from_dt.strftime("%Y-%m-%d") if date_from_dt else None,
            "date_to": date_to_dt.strftime("%Y-%m-%d") if date_to_dt else None,
        },
        "by_day": by_day,
        "by_day_group": by_day_group,
        "by_channel": by_channel,
        "by_product_type": by_product_type,
        "product_types_available": product_types_available,
    }
