"""
Загрузка событий (рекламных кампаний) из Google Таблицы Event Calendar.
Сохраняет в data/events.csv. Таблица должна быть доступна по ссылке (Anyone with the link can view).
"""
import sys
from pathlib import Path

import pandas as pd
import requests

from config import event_calendar_csv_url

OUTPUT_CSV = Path(__file__).resolve().parent / "data" / "events.csv"


def fetch_events_df() -> pd.DataFrame:
    """Скачивает лист Event Calendar в CSV и возвращает DataFrame. Явно UTF-8, чтобы кириллица не искажалась."""
    url = event_calendar_csv_url()
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    # Google отдаёт CSV в UTF-8; принудительно UTF-8, иначе requests может угадать кодировку и кириллица станет кракозябрами
    resp.encoding = "utf-8"
    text = resp.text
    if text.startswith("\ufeff"):
        text = text[1:]
    from io import StringIO
    df = pd.read_csv(StringIO(text), encoding="utf-8")
    df.columns = [str(c).strip() for c in df.columns]
    return df


def main():
    print("Загрузка Event Calendar...")
    try:
        df = fetch_events_df()
    except requests.RequestException as e:
        print(
            "Не удалось загрузить таблицу. Проверьте доступ по ссылке.",
            file=sys.stderr,
        )
        raise SystemExit(1) from e

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    print(f"Сохранено: {OUTPUT_CSV}, строк: {len(df)}, столбцов: {len(df.columns)}")
    return df


if __name__ == "__main__":
    main()
