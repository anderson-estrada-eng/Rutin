"""App Flask: rutina tipo hoja de cálculo → GitHub / PythonAnywhere."""

from __future__ import annotations

import json
import re
from functools import wraps
from pathlib import Path

from flask import (
    Flask,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from auth import (
    clear_fails,
    ensure_secrets,
    is_locked,
    load_flask_secret,
    lock_remaining,
    register_fail,
    verify_credentials,
)
from schedule import (
    as_bool,
    blank_sheet,
    default_workbook,
    move_row,
    new_row,
    normalize_link,
    parse_duration,
    recompute_sheet,
)
from workbook_layout import (
    append_sheet_to_layout,
    create_folder,
    ensure_layout,
    remove_sheet_from_layout,
)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_FILE = DATA_DIR / "workbook.json"
DATA_EXAMPLE = DATA_DIR / "workbook.example.json"

ensure_secrets()

app = Flask(__name__)
app.secret_key = load_flask_secret()
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=False,  # True automático detrás de HTTPS en before_request
    PERMANENT_SESSION_LIFETIME=60 * 60 * 12,  # 12 horas
    MAX_CONTENT_LENGTH=2 * 1024 * 1024,
)


def ensure_data() -> None:
    """Crea workbook solo si NO existe. Nunca pisa datos del usuario."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if DATA_FILE.exists():
        return
    if DATA_EXAMPLE.exists():
        DATA_FILE.write_text(DATA_EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
        return
    save_workbook(default_workbook())


def normalize_workbook(data: dict) -> dict:
    data = ensure_layout(data)
    sheets = data.get("sheets") or {}
    for sid, sheet in list(sheets.items()):
        sheets[sid] = recompute_sheet(sheet)
    data["sheets"] = sheets
    if not data.get("active_sheet_id") or data["active_sheet_id"] not in sheets:
        data["active_sheet_id"] = next(iter(sheets), None)
    return data


def load_workbook() -> dict:
    ensure_data()
    with DATA_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return normalize_workbook(data)


def save_workbook(data: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data = normalize_workbook(data)
    tmp = DATA_FILE.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(DATA_FILE)


def slugify(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9áéíóúñÁÉÍÓÚÑ]+", "-", (name or "hoja").strip().lower())
    s = s.strip("-") or "hoja"
    return s[:40]


def logged_in() -> bool:
    return bool(session.get("authed") and session.get("user"))


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not logged_in():
            if request.path.startswith("/api/"):
                return jsonify({"error": "No autorizado"}), 401
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


@app.before_request
def _secure_cookie_and_gate():
    # Cookie Secure en HTTPS (PythonAnywhere)
    if request.is_secure or request.headers.get("X-Forwarded-Proto") == "https":
        app.config["SESSION_COOKIE_SECURE"] = True

    open_endpoints = {"login", "static", "health"}
    if request.endpoint in open_endpoints or (request.endpoint or "").startswith("static"):
        return None
    if logged_in():
        return None
    if request.path.startswith("/static/"):
        return None
    if request.path.startswith("/api/"):
        return jsonify({"error": "No autorizado"}), 401
    return redirect(url_for("login", next=request.path))


@app.after_request
def _security_headers(resp):
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "same-origin"
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    return resp


@app.get("/health")
def health():
    return jsonify({"ok": True})


@app.route("/login", methods=["GET", "POST"])
def login():
    if logged_in():
        return redirect(url_for("index"))

    error = None
    if request.method == "POST":
        if is_locked():
            mins = max(1, (lock_remaining() + 59) // 60)
            error = f"Demasiados intentos. Espera ~{mins} min e inténtalo de nuevo."
        else:
            username = (request.form.get("username") or "").strip()
            password = request.form.get("password") or ""
            # Escapado básico de tamaño
            if len(username) > 64 or len(password) > 256:
                register_fail()
                error = "Usuario o contraseña incorrectos."
            elif verify_credentials(username, password):
                clear_fails()
                session.clear()
                session["authed"] = True
                session["user"] = username
                session.permanent = True
                nxt = request.args.get("next") or url_for("index")
                if not nxt.startswith("/") or nxt.startswith("//"):
                    nxt = url_for("index")
                return redirect(nxt)
            else:
                register_fail()
                error = "Usuario o contraseña incorrectos."

    return render_template("login.html", error=error)


@app.post("/logout")
@login_required
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.get("/")
@login_required
def index():
    return render_template("index.html", username=session.get("user", ""))


@app.get("/api/workbook")
@login_required
def api_get_workbook():
    return jsonify(load_workbook())


@app.put("/api/workbook")
@login_required
def api_put_workbook():
    payload = request.get_json(force=True, silent=True) or {}
    sheets = payload.get("sheets") or {}
    for sid, sheet in list(sheets.items()):
        sheets[sid] = recompute_sheet(sheet)
    payload["sheets"] = sheets
    if not payload.get("active_sheet_id") or payload["active_sheet_id"] not in sheets:
        payload["active_sheet_id"] = next(iter(sheets), None)
    save_workbook(payload)
    return jsonify(payload)


@app.post("/api/sheets")
@login_required
def api_create_sheet():
    data = load_workbook()
    body = request.get_json(force=True, silent=True) or {}
    name = (body.get("name") or "Nueva hoja").strip() or "Nueva hoja"
    base = slugify(name)
    sid = base
    i = 2
    while sid in data["sheets"]:
        sid = f"{base}-{i}"
        i += 1
    sheet = blank_sheet(name)
    if body.get("day_start"):
        sheet["day_start"] = body["day_start"]
    if body.get("day_end"):
        sheet["day_end"] = body["day_end"]
    sheet = recompute_sheet(sheet)
    data["sheets"][sid] = sheet
    data["active_sheet_id"] = sid
    data["layout"] = append_sheet_to_layout(data.get("layout") or [], sid)
    save_workbook(data)
    return jsonify({"id": sid, "workbook": data})


@app.patch("/api/sheets/<sheet_id>")
@login_required
def api_patch_sheet(sheet_id: str):
    data = load_workbook()
    if sheet_id not in data["sheets"]:
        return jsonify({"error": "Hoja no encontrada"}), 404
    body = request.get_json(force=True, silent=True) or {}
    sheet = data["sheets"][sheet_id]
    if "name" in body:
        sheet["name"] = str(body["name"]).strip() or sheet["name"]
    if "day_start" in body:
        sheet["day_start"] = body["day_start"]
    if "day_end" in body:
        sheet["day_end"] = body["day_end"]
    if "rows" in body and isinstance(body["rows"], list):
        sheet["rows"] = body["rows"]
    data["sheets"][sheet_id] = recompute_sheet(sheet)
    data["active_sheet_id"] = sheet_id
    save_workbook(data)
    return jsonify(data["sheets"][sheet_id])


@app.delete("/api/sheets/<sheet_id>")
@login_required
def api_delete_sheet(sheet_id: str):
    data = load_workbook()
    if sheet_id not in data["sheets"]:
        return jsonify({"error": "Hoja no encontrada"}), 404
    if len(data["sheets"]) <= 1:
        return jsonify({"error": "Debes tener al menos una hoja"}), 400
    del data["sheets"][sheet_id]
    data["layout"] = remove_sheet_from_layout(data.get("layout") or [], sheet_id)
    if data.get("active_sheet_id") == sheet_id:
        data["active_sheet_id"] = next(iter(data["sheets"]))
    save_workbook(data)
    return jsonify(data)


@app.post("/api/sheets/<sheet_id>/rows")
@login_required
def api_add_row(sheet_id: str):
    data = load_workbook()
    if sheet_id not in data["sheets"]:
        return jsonify({"error": "Hoja no encontrada"}), 404
    body = request.get_json(force=True, silent=True) or {}
    sheet = data["sheets"][sheet_id]
    row = new_row(
        task=body.get("task", ""),
        timed=as_bool(body.get("timed", True)),
        duration=body.get("duration", 30),
        notes=body.get("notes", ""),
        link=body.get("link", ""),
    )
    index = body.get("index")
    if index is None:
        sheet["rows"].append(row)
    else:
        sheet["rows"].insert(max(0, int(index)), row)
    data["sheets"][sheet_id] = recompute_sheet(sheet)
    save_workbook(data)
    return jsonify(data["sheets"][sheet_id])


@app.patch("/api/sheets/<sheet_id>/rows/<int:row_index>")
@login_required
def api_patch_row(sheet_id: str, row_index: int):
    data = load_workbook()
    if sheet_id not in data["sheets"]:
        return jsonify({"error": "Hoja no encontrada"}), 404
    sheet = data["sheets"][sheet_id]
    rows = sheet.get("rows", [])
    if row_index < 0 or row_index >= len(rows):
        return jsonify({"error": "Fila no encontrada"}), 404
    body = request.get_json(force=True, silent=True) or {}
    row = rows[row_index]
    if "task" in body:
        row["task"] = str(body["task"])
    if "notes" in body:
        row["notes"] = str(body["notes"])
    if "link" in body:
        row["link"] = normalize_link(body["link"])
    if "timed" in body:
        row["timed"] = as_bool(body["timed"])
    if "duration" in body:
        row["duration"] = parse_duration(body["duration"])
    data["sheets"][sheet_id] = recompute_sheet(sheet)
    save_workbook(data)
    return jsonify(data["sheets"][sheet_id])


@app.delete("/api/sheets/<sheet_id>/rows/<int:row_index>")
@login_required
def api_delete_row(sheet_id: str, row_index: int):
    data = load_workbook()
    if sheet_id not in data["sheets"]:
        return jsonify({"error": "Hoja no encontrada"}), 404
    sheet = data["sheets"][sheet_id]
    rows = sheet.get("rows", [])
    if row_index < 0 or row_index >= len(rows):
        return jsonify({"error": "Fila no encontrada"}), 404
    rows.pop(row_index)
    data["sheets"][sheet_id] = recompute_sheet(sheet)
    save_workbook(data)
    return jsonify(data["sheets"][sheet_id])


@app.post("/api/sheets/<sheet_id>/move")
@login_required
def api_move_row(sheet_id: str):
    data = load_workbook()
    if sheet_id not in data["sheets"]:
        return jsonify({"error": "Hoja no encontrada"}), 404
    body = request.get_json(force=True, silent=True) or {}
    try:
        from_index = int(body["from"])
        to_index = int(body["to"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "Usa { from, to }"}), 400
    sheet = move_row(data["sheets"][sheet_id], from_index, to_index)
    data["sheets"][sheet_id] = sheet
    save_workbook(data)
    return jsonify(sheet)


@app.post("/api/sheets/<sheet_id>/recompute")
@login_required
def api_recompute(sheet_id: str):
    data = load_workbook()
    if sheet_id not in data["sheets"]:
        return jsonify({"error": "Hoja no encontrada"}), 404
    data["sheets"][sheet_id] = recompute_sheet(data["sheets"][sheet_id])
    save_workbook(data)
    return jsonify(data["sheets"][sheet_id])


@app.put("/api/layout")
@login_required
def api_put_layout():
    data = load_workbook()
    body = request.get_json(force=True, silent=True) or {}
    if "layout" not in body:
        return jsonify({"error": "Falta layout"}), 400
    data["layout"] = body["layout"]
    save_workbook(data)
    return jsonify(data)


@app.post("/api/folders")
@login_required
def api_create_folder():
    data = load_workbook()
    body = request.get_json(force=True, silent=True) or {}
    name = (body.get("name") or "Carpeta").strip() or "Carpeta"
    data["layout"], folder_id = create_folder(data.get("layout") or [], name)
    save_workbook(data)
    return jsonify({"id": folder_id, "workbook": data})


@app.post("/api/active/<sheet_id>")
@login_required
def api_set_active(sheet_id: str):
    data = load_workbook()
    if sheet_id not in data["sheets"]:
        return jsonify({"error": "Hoja no encontrada"}), 404
    data["active_sheet_id"] = sheet_id
    save_workbook(data)
    return jsonify(data)


# Entrada WSGI para PythonAnywhere
application = app

if __name__ == "__main__":
    ensure_data()
    app.run(host="0.0.0.0", port=5000, debug=False)
