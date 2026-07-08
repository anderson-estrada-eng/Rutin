"""App Flask: rutina tipo hoja de cálculo → GitHub / PythonAnywhere."""

from __future__ import annotations

import json
import re
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from schedule import (
    blank_sheet,
    default_workbook,
    move_row,
    new_row,
    normalize_link,
    parse_duration,
    recompute_sheet,
    as_bool,
)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_FILE = DATA_DIR / "workbook.json"

app = Flask(__name__)


def ensure_data() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not DATA_FILE.exists():
        save_workbook(default_workbook())


def load_workbook() -> dict:
    ensure_data()
    with DATA_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)
    # Normalizar hojas
    sheets = data.get("sheets") or {}
    for sid, sheet in list(sheets.items()):
        sheets[sid] = recompute_sheet(sheet)
    data["sheets"] = sheets
    if not data.get("active_sheet_id") or data["active_sheet_id"] not in sheets:
        data["active_sheet_id"] = next(iter(sheets), None)
    return data


def save_workbook(data: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = DATA_FILE.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(DATA_FILE)


def slugify(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9áéíóúñÁÉÍÓÚÑ]+", "-", (name or "hoja").strip().lower())
    s = s.strip("-") or "hoja"
    return s[:40]


@app.route("/")
def index():
    return render_template("index.html")


@app.get("/api/workbook")
def api_get_workbook():
    return jsonify(load_workbook())


@app.put("/api/workbook")
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
    save_workbook(data)
    return jsonify({"id": sid, "workbook": data})


@app.patch("/api/sheets/<sheet_id>")
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
def api_delete_sheet(sheet_id: str):
    data = load_workbook()
    if sheet_id not in data["sheets"]:
        return jsonify({"error": "Hoja no encontrada"}), 404
    if len(data["sheets"]) <= 1:
        return jsonify({"error": "Debes tener al menos una hoja"}), 400
    del data["sheets"][sheet_id]
    if data.get("active_sheet_id") == sheet_id:
        data["active_sheet_id"] = next(iter(data["sheets"]))
    save_workbook(data)
    return jsonify(data)


@app.post("/api/sheets/<sheet_id>/rows")
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
def api_recompute(sheet_id: str):
    data = load_workbook()
    if sheet_id not in data["sheets"]:
        return jsonify({"error": "Hoja no encontrada"}), 404
    data["sheets"][sheet_id] = recompute_sheet(data["sheets"][sheet_id])
    save_workbook(data)
    return jsonify(data["sheets"][sheet_id])


@app.post("/api/active/<sheet_id>")
def api_set_active(sheet_id: str):
    data = load_workbook()
    if sheet_id not in data["sheets"]:
        return jsonify({"error": "Hoja no encontrada"}), 404
    data["active_sheet_id"] = sheet_id
    save_workbook(data)
    return jsonify(data)


# Entrada WSGI para PythonAnywhere (también sirve `python app.py`)
application = app

if __name__ == "__main__":
    ensure_data()
    app.run(host="0.0.0.0", port=5000, debug=True)
