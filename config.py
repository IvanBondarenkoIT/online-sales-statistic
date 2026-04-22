# ID таблицы из URL:
# https://docs.google.com/spreadsheets/d/1l60r1Rt83mALa2Hd3yViU8aOglSGlUPyeJQ39n084Xo/...
SPREADSHEET_ID = "1l60r1Rt83mALa2Hd3yViU8aOglSGlUPyeJQ39n084Xo"

# GID каждой вкладки (месяца). В URL при открытии вкладки: ...#gid=ЧИСЛО
SHEET_GIDS = [
    1132847113,  # январь 2026
    667824329,   # февраль 2026
    1824241654,  # март 2026
    178782011,   # апрель 2026
    2088494986,  # май 2026
]


def csv_export_url(gid: int) -> str:
    return f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv&gid={gid}"


# Event Calendar: рекламные кампании (события) для связи с продажами
# https://docs.google.com/spreadsheets/d/1y_5osZNvVIbvR0d0RubctL5WvlAmZhQ0c4OBzcqsVlo/edit?gid=0
EVENT_CALENDAR_SPREADSHEET_ID = "1y_5osZNvVIbvR0d0RubctL5WvlAmZhQ0c4OBzcqsVlo"
EVENT_CALENDAR_SHEET_GID = 0


def event_calendar_csv_url() -> str:
    return f"https://docs.google.com/spreadsheets/d/{EVENT_CALENDAR_SPREADSHEET_ID}/export?format=csv&gid={EVENT_CALENDAR_SHEET_GID}"
