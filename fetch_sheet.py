"""
Загрузка данных из Google Таблицы «2026 Онлайн продажи / Online sales».
Поддерживаются несколько вкладок (по месяцам): данные объединяются в одну таблицу по дате.
Работает, если таблица доступна по ссылке (Anyone with the link can view).
"""
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import requests

from config import SHEET_GIDS, csv_export_url

OUTPUT_CSV = Path(__file__).resolve().parent / "data" / "online_sales.csv"


class FetchError(Exception):
    """Ошибка загрузки: ни одна вкладка не вернула данные."""

    def __init__(self, message: str, *, sheets_failed: int = 0, failed_gids: list[int] | None = None):
        super().__init__(message)
        self.sheets_failed = sheets_failed
        self.failed_gids = failed_gids or []


@dataclass
class FetchResult:
    """Результат загрузки всех вкладок из Google Sheets."""

    df: pd.DataFrame
    sheets_loaded: int = 0
    sheets_failed: int = 0
    failed_gids: list[int] = field(default_factory=list)

    @property
    def row_count(self) -> int:
        return len(self.df)


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


def fetch_via_csv_export() -> FetchResult:
    """
    Скачивает все вкладки из SHEET_GIDS, объединяет в одну таблицу.
    У каждого листа нормализуются имена колонок, чтобы данные февраля не терялись при concat.
    """
    frames = []
    sheets_loaded = 0
    sheets_failed = 0
    failed_gids: list[int] = []
    for gid in SHEET_GIDS:
        try:
            df = _fetch_one_sheet(gid)
            df = _normalize_columns(df)
            if not df.empty:
                frames.append(df)
                sheets_loaded += 1
        except Exception as e:
            sheets_failed += 1
            failed_gids.append(gid)
            sys.stderr.write(f"Вкладка gid={gid}: {e}\n")
            continue
    if not frames:
        raise FetchError(
            f"Не удалось загрузить данные ни с одной вкладки ({len(SHEET_GIDS)} gid). "
            f"Ошибки по gid: {failed_gids}",
            sheets_failed=sheets_failed or len(SHEET_GIDS),
            failed_gids=failed_gids,
        )
    combined = pd.concat(frames, ignore_index=True, sort=False)
    return FetchResult(
        df=combined,
        sheets_loaded=sheets_loaded,
        sheets_failed=sheets_failed,
        failed_gids=failed_gids,
    )


def main():
    print("Загрузка таблицы...")
    try:
        result = fetch_via_csv_export()
    except FetchError as e:
        print(str(e), file=sys.stderr)
        raise SystemExit(1) from e
    except requests.RequestException as e:
        print(
            "Не удалось загрузить по ссылке. Убедитесь, что таблица доступна: "
            "Настройки доступа → «Все, у кого есть ссылка» → Просмотр.",
            file=sys.stderr,
        )
        raise SystemExit(1) from e

    df = result.df
    print(
        f"Загружено листов: {result.sheets_loaded}/{len(SHEET_GIDS)}, "
        f"ошибок: {result.sheets_failed}, строк всего: {result.row_count}, столбцов: {len(df.columns)}"
    )
    if result.failed_gids:
        print("Не загружены gid:", result.failed_gids)
    print("Столбцы:", list(df.columns))

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    print(f"Сохранено: {OUTPUT_CSV}")

    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", None)
    pd.set_option("display.max_colwidth", 40)
    print("\nПервые 5 строк:")
    print(df.head().to_string())

    return df


if __name__ == "__main__":
    main()
