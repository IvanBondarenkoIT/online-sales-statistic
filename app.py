"""
Веб-приложение отчёта по онлайн-продажам.
Защита: логин/пароль из .env (ADMIN_USER, ADMIN_PASSWORD).
API: GET /api/report?date=YYYY-MM-DD, exclude=...; POST /api/refresh.
"""
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, request, send_from_directory, session, url_for

from report_data import DATA_CSV, build_report

load_dotenv()

app = Flask(__name__, static_folder="static", static_url_path="")
app.secret_key = __import__("os").environ.get("SECRET_KEY", "dev-secret-change-in-production")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

ADMIN_USER = __import__("os").environ.get("ADMIN_USER", "admin")
ADMIN_PASSWORD = __import__("os").environ.get("ADMIN_PASSWORD", "admin")


def auth_required(f):
    def wrapped(*args, **kwargs):
        if session.get("auth"):
            return f(*args, **kwargs)
        if request.path.startswith("/api/"):
            return jsonify({"error": "Unauthorized"}), 401
        return redirect(url_for("login", next=request.url))
    wrapped.__name__ = f.__name__
    return wrapped


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


@app.route("/api/refresh", methods=["POST"])
@auth_required
def api_refresh():
    """Обновляет data/online_sales.csv из Google Таблицы и возвращает новый отчёт."""
    try:
        from fetch_sheet import fetch_via_csv_export
        df = fetch_via_csv_export()
        DATA_CSV.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(DATA_CSV, index=False, encoding="utf-8-sig")
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    date_param = request.args.get("date")
    reference_date = date_param if date_param else date.today().isoformat()
    exclude = request.args.get("exclude")
    exclude_list = [x.strip() for x in exclude.split(",") if x.strip()] if exclude else None
    data = build_report(reference_date=reference_date, exclude_product_types=exclude_list)
    return jsonify({"ok": True, "report": data})


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true")
