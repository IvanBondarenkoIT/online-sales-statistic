"""
Веб-приложение отчёта по онлайн-продажам.
Защита: логин/пароль из .env (ADMIN_USER, ADMIN_PASSWORD).
API: GET /api/report?date=..., exclude=...; GET /api/events?date=...&period=7d|4w;
     GET /api/events-analysis?date=...&period=7d|4w; POST /api/refresh.
"""
import os
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, request, send_from_directory, session, url_for

from report_data import DATA_CSV, build_report, load_sales_df, _parse_date
from events_data import get_events_with_sales, get_events_analysis

load_dotenv()

app = Flask(__name__, static_folder="static", static_url_path="")
app.secret_key = __import__("os").environ.get("SECRET_KEY", "dev-secret-change-in-production")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

ADMIN_USER = __import__("os").environ.get("ADMIN_USER", "admin")
ADMIN_PASSWORD = __import__("os").environ.get("ADMIN_PASSWORD", "admin")
API_EXPORT_KEY = os.environ.get("API_EXPORT_KEY", "").strip()


def auth_required(f):
    def wrapped(*args, **kwargs):
        if session.get("auth"):
            return f(*args, **kwargs)
        if request.path.startswith("/api/"):
            return jsonify({"error": "Unauthorized"}), 401
        return redirect(url_for("login", next=request.url))
    wrapped.__name__ = f.__name__
    return wrapped


def _require_api_key() -> tuple[bool, tuple]:
    """Проверяет ключ API из заголовка X-API-Key или query api_key."""
    expected = (API_EXPORT_KEY or "").strip()
    provided = (request.headers.get("X-API-Key") or request.args.get("api_key") or "").strip()
    if not expected:
        return False, (jsonify({"error": "API key is not configured"}), 500)
    if not provided or provided != expected:
        return False, (jsonify({"error": "Unauthorized"}), 401)
    return True, ()


def _json_safe(v):
    """Приводит pandas/numpy значения к JSON-совместимым."""
    if hasattr(v, "item"):
        try:
            v = v.item()
        except Exception:
            pass
    if hasattr(v, "isoformat"):
        try:
            return v.isoformat()
        except Exception:
            pass
    if v != v:  # NaN
        return None
    return v


def _sales_date_bounds(df) -> tuple[str | None, str | None]:
    """min/max даты продаж из загруженного DataFrame."""
    if df.empty or "_date" not in df.columns:
        return None, None
    valid = df["_date"].dropna()
    if valid.empty:
        return None, None
    return valid.min().date().isoformat(), valid.max().date().isoformat()


def _sales_data_status() -> dict:
    """Метаданные о текущем CSV продаж (для cron и мониторинга)."""
    csv_exists = DATA_CSV.exists()
    file_mtime = None
    if csv_exists:
        file_mtime = datetime.fromtimestamp(DATA_CSV.stat().st_mtime).isoformat()
    df = load_sales_df()
    min_date, max_date = _sales_date_bounds(df)
    return {
        "csv_exists": csv_exists,
        "csv_path": str(DATA_CSV),
        "row_count": len(df),
        "data_loaded": csv_exists and not df.empty,
        "min_date": min_date,
        "max_date": max_date,
        "file_mtime": file_mtime,
    }


def _refresh_sales_and_events() -> tuple[bool, str | None, dict | None]:
    """Обновляет sales/events CSV из Google. Возвращает (ok, error, meta)."""
    meta: dict = {}
    try:
        from fetch_sheet import FetchError, fetch_via_csv_export
        result = fetch_via_csv_export()
        if result.row_count == 0:
            return False, "Google Sheets export returned zero rows; existing CSV was not modified", meta
        DATA_CSV.parent.mkdir(parents=True, exist_ok=True)
        result.df.to_csv(DATA_CSV, index=False, encoding="utf-8-sig")
        min_date, max_date = _sales_date_bounds(load_sales_df())
        meta = {
            "rows": result.row_count,
            "sheets_loaded": result.sheets_loaded,
            "sheets_failed": result.sheets_failed,
            "failed_gids": result.failed_gids,
            "min_date": min_date,
            "max_date": max_date,
            "csv_path": str(DATA_CSV),
        }
    except FetchError as e:
        return False, str(e), meta
    except Exception as e:
        return False, str(e), meta
    try:
        from fetch_events import fetch_events_df
        events_df = fetch_events_df()
        from events_data import EVENTS_CSV
        EVENTS_CSV.parent.mkdir(parents=True, exist_ok=True)
        events_df.to_csv(EVENTS_CSV, index=False, encoding="utf-8-sig")
    except Exception:
        pass  # события опциональны: при ошибке оставляем старый events.csv
    return True, None, meta


def _parse_sales_table_date(date_param: str) -> date | None:
    date_param = (date_param or "").strip()
    if not date_param:
        return None
    try:
        return date.fromisoformat(date_param[:10])
    except ValueError:
        parsed = _parse_date(date_param)
        return parsed.date() if parsed is not None else None


def _sales_table_rows(target_dt: date) -> tuple[list[dict], int]:
    df = load_sales_df()
    if df.empty or "_date" not in df.columns:
        return [], 0
    day_df = df[df["_date"].dt.date == target_dt].copy()
    if day_df.empty:
        return [], 0
    rows = []
    for _, row in day_df.iterrows():
        item = {}
        for col in day_df.columns:
            if col == "_date":
                item[col] = row[col].date().isoformat() if row[col] is not None else None
            else:
                item[col] = _json_safe(row[col])
        rows.append(item)
    return rows, len(rows)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        if session.get("auth"):
            return redirect(request.args.get("next") or url_for("index"))
        return send_from_directory(app.static_folder, "login.html")
    user = (request.form.get("username") or "").strip()
    password = (request.form.get("password") or "").strip()
    if user == ADMIN_USER and password == ADMIN_PASSWORD:
        session["auth"] = True
        return redirect(request.form.get("next") or request.args.get("next") or url_for("index"))
    next_url = request.form.get("next") or request.args.get("next") or ""
    return redirect(url_for("login", error=1, next=next_url))


@app.route("/logout")
def logout():
    session.pop("auth", None)
    return redirect(url_for("login"))


@app.route("/")
@auth_required
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/report")
@auth_required
def api_report():
    date_param = request.args.get("date")
    reference_date = date_param if date_param else date.today().isoformat()
    exclude = request.args.get("exclude")
    exclude_list = [x.strip() for x in exclude.split(",") if x.strip()] if exclude else None
    data = build_report(reference_date=reference_date, exclude_product_types=exclude_list)
    return jsonify(data)


@app.route("/api/events")
@auth_required
def api_events():
    """События за период (7d/4w) и продажи по целевой группе (Вариант 1)."""
    date_param = request.args.get("date") or ""
    ref = date.fromisoformat(date_param.strip()[:10]) if date_param.strip() else date.today()
    period = request.args.get("period", "7d").lower()
    if period not in ("7d", "4w"):
        period = "7d"
    try:
        data = get_events_with_sales(ref, period=period)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/events-analysis")
@auth_required
def api_events_analysis():
    """Аналитика по событиям: до/во время, прирост, ROI (Вариант 3)."""
    date_param = request.args.get("date") or ""
    ref = date.fromisoformat(date_param.strip()[:10]) if date_param.strip() else date.today()
    period = request.args.get("period", "7d").lower()
    if period not in ("7d", "4w"):
        period = "7d"
    try:
        data = get_events_analysis(ref, period=period)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/refresh", methods=["POST"])
@auth_required
def api_refresh():
    """Обновляет data/online_sales.csv и data/events.csv из Google и возвращает новый отчёт."""
    ok, error, meta = _refresh_sales_and_events()
    if not ok:
        return jsonify({"ok": False, "error": error, **meta}), 500
    date_param = request.args.get("date")
    reference_date = date_param if date_param else date.today().isoformat()
    exclude = request.args.get("exclude")
    exclude_list = [x.strip() for x in exclude.split(",") if x.strip()] if exclude else None
    data = build_report(reference_date=reference_date, exclude_product_types=exclude_list)
    return jsonify({"ok": True, "report": data, **meta})


@app.route("/api/refresh-by-key", methods=["POST"])
def api_refresh_by_key():
    """
    Обновляет data/online_sales.csv и data/events.csv из Google по API ключу.
    Использование: POST /api/refresh-by-key (+ X-API-Key или query api_key).
    """
    ok, err = _require_api_key()
    if not ok:
        return err
    ok_refresh, error, meta = _refresh_sales_and_events()
    if not ok_refresh:
        return jsonify({"ok": False, "error": error, **meta}), 500
    return jsonify({"ok": True, **meta})


@app.route("/api/data-status")
def api_data_status():
    """Статус локального CSV продаж (для cron перед выгрузкой)."""
    ok, err = _require_api_key()
    if not ok:
        return err
    return jsonify({"ok": True, **_sales_data_status()})


@app.route("/api/sales-table")
def api_sales_table():
    """
    Возвращает строки таблицы онлайн-продаж за указанную дату.
    Доступ: по API ключу (X-API-Key или query api_key).
    Query: date=YYYY-MM-DD (или DD.MM.YYYY); refresh=1 — обновить из Google перед выборкой.
    """
    ok, err = _require_api_key()
    if not ok:
        return err

    date_param = (request.args.get("date") or "").strip()
    if not date_param:
        return jsonify({"error": "date query parameter is required"}), 400

    target_dt = _parse_sales_table_date(date_param)
    if target_dt is None:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD or DD.MM.YYYY"}), 400

    refresh_flag = (request.args.get("refresh") or "").strip().lower() in ("1", "true", "yes")
    if refresh_flag:
        ok_refresh, error, _meta = _refresh_sales_and_events()
        if not ok_refresh:
            return jsonify({"ok": False, "error": error, "date": target_dt.isoformat()}), 500

    status = _sales_data_status()
    if not status["data_loaded"]:
        return jsonify({
            "ok": True,
            "date": target_dt.isoformat(),
            "count": 0,
            "rows": [],
            "data_loaded": False,
            "hint": "Call POST /api/refresh-by-key first",
            **status,
        })

    rows, count = _sales_table_rows(target_dt)
    payload = {
        "ok": True,
        "date": target_dt.isoformat(),
        "count": count,
        "rows": rows,
        "data_loaded": True,
        "max_date": status.get("max_date"),
    }
    if count == 0:
        payload["hint"] = "No sales rows for this date in loaded data"
    return jsonify(payload)


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true")
