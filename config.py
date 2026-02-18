# ID таблицы из URL:
# https://docs.google.com/spreadsheets/d/1l60r1Rt83mALa2Hd3yViU8aOglSGlUPyeJQ39n084Xo/...
SPREADSHEET_ID = "1l60r1Rt83mALa2Hd3yViU8aOglSGlUPyeJQ39n084Xo"

# GID каждой вкладки (месяца). В URL при открытии вкладки: ...#gid=ЧИСЛО
SHEET_GIDS = [
    1132847113,  # январь 2026
    667824329,   # февраль 2026
    1824241654,  # март 2026
]


def csv_export_url(gid: int) -> str:
    return f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv&gid={gid}"
