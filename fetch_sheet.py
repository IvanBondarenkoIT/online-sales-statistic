"""
Загрузка данных из Google Таблицы «2026 Онлайн продажи / Online sales».
Поддерживаются несколько вкладок (по месяцам): данные объединяются в одну таблицу по дате.
Работает, если таблица доступна по ссылке (Anyone with the link can view).
"""
import sys
from pathlib import Path

import pandas as pd
import requests

from config import SHEET_GIDS, csv_export_url

OUTPUT_CSV = Path(__file__).resolve().parent / "data" / "online_sales.csv"


def _fetch_one_sheet(gid: int) -> pd.DataFrame:
    """Скачивает одну вкладку (лист) по gid в CSV."""
    url = csv_export_url(gid)
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    text = resp.text
    if text.startswith("\ufeff"):
        text = text[1:]
    from io import StringIO
    return pd.read_csv(StringIO(text))


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Единые имена колонок (Date, Total Amount, ...), чтобы январь/февраль/март выровнялись при объединении."""
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
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
    if df.columns.duplicated().any():
        df = df.loc[:, ~df.columns.duplicated(keep="first")]
    return df


def fetch_via_csv_export() -> pd.DataFrame:
    """
    Скачивает все вкладки из SHEET_GIDS, объединяет в одну таблицу.
    У каждого листа нормализуются имена колонок, чтобы данные февраля не терялись при concat.
    """
    frames = []
    for gid in SHEET_GIDS:
        try:
            df = _fetch_one_sheet(gid)
            df = _normalize_columns(df)
            if not df.empty:
                frames.append(df)
        except Exception as e:
            # Одна вкладка может быть недоступна или пустой — пропускаем
            sys.stderr.write(f"Вкладка gid={gid}: {e}\n")
            continue
    if not frames:
        return pd.DataFrame()
    combined = pd.concat(frames, ignore_index=True, sort=False)
    return combined


def main():
    print("Загрузка таблицы...")
    try:
        df = fetch_via_csv_export()
    except requests.RequestException as e:
        print(
            "Не удалось загрузить по ссылке. Убедитесь, что таблица доступна: "
            "Настройки доступа → «Все, у кого есть ссылка» → Просмотр.",
            file=sys.stderr,
        )
        raise SystemExit(1) from e

    print(f"Загружено листов: {len(SHEET_GIDS)}, строк всего: {len(df)}, столбцов: {len(df.columns)}")
    print("Столбцы:", list(df.columns))

    # Сохраняем локально
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    print(f"Сохранено: {OUTPUT_CSV}")

    # Показываем первые строки (без лишнего вывода)
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", None)
    pd.set_option("display.max_colwidth", 40)
    print("\nПервые 5 строк:")
    print(df.head().to_string())

    return df


if __name__ == "__main__":
    main()
