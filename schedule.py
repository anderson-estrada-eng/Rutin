"""Motor de rutina / horarios tipo hoja de cálculo."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


DAY_START_MIN = 6 * 60  # 6:00 AM
DAY_END_MIN = 16 * 60  # 4:00 PM
NIGHT_NEXT_MIN = 7 * 60  # 7:00 AM (día siguiente, referencia informativa)


def minutes_to_clock(total: int) -> str:
    """Convierte minutos desde medianoche a 'H:MM AM/PM'."""
    total = int(total) % (24 * 60)
    h24 = total // 60
    m = total % 60
    suffix = "AM" if h24 < 12 else "PM"
    h12 = h24 % 12
    if h12 == 0:
        h12 = 12
    return f"{h12}:{m:02d} {suffix}"


def clock_to_minutes(text: str) -> int | None:
    """Parsea '6:30 AM', '16:00', '6am' → minutos desde medianoche."""
    if text is None:
        return None
    s = str(text).strip().upper().replace(".", "")
    if not s:
        return None

    am = s.endswith("AM")
    pm = s.endswith("PM")
    if am or pm:
        s = s[:-2].strip()

    if ":" in s:
        parts = s.split(":")
        try:
            h = int(parts[0])
            m = int(parts[1]) if len(parts) > 1 else 0
        except ValueError:
            return None
    else:
        try:
            h = int(s)
            m = 0
        except ValueError:
            return None

    if am or pm:
        if h == 12:
            h = 0
        if pm:
            h += 12
    if not (0 <= h < 24 and 0 <= m < 60):
        return None
    return h * 60 + m


def parse_duration(value: Any) -> int:
    """
    Acepta minutos (int), '45', '45m', '1h', '1h30', '1:30', '1.5h'.
    Devuelve minutos >= 0.
    """
    if value is None or value == "":
        return 0
    if isinstance(value, (int, float)):
        return max(0, int(round(float(value))))

    s = str(value).strip().lower().replace(" ", "")
    if not s:
        return 0

    if s.endswith("min"):
        s = s[:-3]
    elif s.endswith("mins"):
        s = s[:-4]
    elif s.endswith("m") and not s.endswith("am") and not s.endswith("pm"):
        # sólo si es tipo 45m
        if s[:-1].replace(".", "").isdigit():
            s = s[:-1]

    if "h" in s:
        # 1h30, 1h30m, 1.5h
        if s.endswith("h"):
            try:
                return max(0, int(round(float(s[:-1]) * 60)))
            except ValueError:
                return 0
        left, right = s.split("h", 1)
        right = right.rstrip("m")
        try:
            hours = float(left) if left else 0
            mins = float(right) if right else 0
            return max(0, int(round(hours * 60 + mins)))
        except ValueError:
            return 0

    if ":" in s:
        parts = s.split(":")
        try:
            h = int(parts[0])
            m = int(parts[1]) if len(parts) > 1 else 0
            return max(0, h * 60 + m)
        except ValueError:
            return 0

    try:
        return max(0, int(round(float(s))))
    except ValueError:
        return 0


def format_duration(mins: int) -> str:
    mins = max(0, int(mins))
    if mins == 0:
        return "0m"
    h, m = divmod(mins, 60)
    if h and m:
        return f"{h}h {m}m"
    if h:
        return f"{h}h"
    return f"{m}m"


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    s = str(value).strip().lower()
    return s in {"1", "true", "sí", "si", "yes", "y", "x", "✓", "check"}


def recompute_sheet(sheet: dict[str, Any]) -> dict[str, Any]:
    """
    Recalcula inicio/fin de filas con horario=True, en el orden del array.
    - day_start: inicio del día (default 6:00 AM)
    - day_end: tope suave informativo (4:00 PM); si se pasa, se marca overflow
    Las filas sin horario no consumen tiempo del timeline.
    """
    sheet = deepcopy(sheet)
    rows: list[dict[str, Any]] = sheet.setdefault("rows", [])
    start = clock_to_minutes(sheet.get("day_start"))
    if start is None:
        start = DAY_START_MIN
    soft_end = clock_to_minutes(sheet.get("day_end"))
    if soft_end is None:
        soft_end = DAY_END_MIN

    sheet["day_start"] = minutes_to_clock(start)
    sheet["day_end"] = minutes_to_clock(soft_end)
    sheet["night_next"] = minutes_to_clock(NIGHT_NEXT_MIN)

    cursor = start
    overflow = False

    for row in rows:
        timed = as_bool(row.get("timed", True))
        row["timed"] = timed
        row["link"] = normalize_link(row.get("link", ""))
        duration = parse_duration(row.get("duration"))
        row["duration_minutes"] = duration
        row["duration_label"] = format_duration(duration)

        if not timed:
            row["start"] = ""
            row["end"] = ""
            row["start_minutes"] = None
            row["end_minutes"] = None
            row["overflow"] = False
            continue

        row_start = cursor
        row_end = cursor + duration
        row["start_minutes"] = row_start
        row["end_minutes"] = row_end
        row["start"] = minutes_to_clock(row_start)
        row["end"] = minutes_to_clock(row_end)
        row["overflow"] = row_end > soft_end
        if row["overflow"]:
            overflow = True
        cursor = row_end

    sheet["timeline_end"] = minutes_to_clock(cursor)
    sheet["timeline_end_minutes"] = cursor
    sheet["overflow"] = overflow
    sheet["remaining_minutes"] = max(0, soft_end - cursor)
    sheet["remaining_label"] = format_duration(sheet["remaining_minutes"])
    return sheet


def move_row(sheet: dict[str, Any], from_index: int, to_index: int) -> dict[str, Any]:
    rows = sheet.get("rows", [])
    if not rows:
        return recompute_sheet(sheet)
    n = len(rows)
    from_index = max(0, min(n - 1, int(from_index)))
    to_index = max(0, min(n - 1, int(to_index)))
    if from_index == to_index:
        return recompute_sheet(sheet)
    item = rows.pop(from_index)
    rows.insert(to_index, item)
    return recompute_sheet(sheet)


def normalize_link(value: Any) -> str:
    """
    Normaliza vínculos:
    - hoja interna: 'sheet:id', '#id', o solo el id/nombre
    - externa / documento: https://..., http://..., o ruta tipo archivo.pdf
    """
    if value is None:
        return ""
    s = str(value).strip()
    if not s:
        return ""
    lower = s.lower()
    if lower.startswith("sheet:"):
        target = s.split(":", 1)[1].strip()
        return f"sheet:{target}" if target else ""
    if s.startswith("#") and not s.startswith("#sheet"):
        target = s[1:].strip()
        return f"sheet:{target}" if target else ""
    return s


def new_row(
    task: str = "",
    timed: bool = True,
    duration: Any = 30,
    notes: str = "",
    link: Any = "",
) -> dict[str, Any]:
    return {
        "task": task,
        "timed": timed,
        "duration": duration,
        "notes": notes,
        "link": normalize_link(link),
    }


def blank_sheet(name: str = "Nueva hoja") -> dict[str, Any]:
    """Hoja nueva vacía (sin filas de ejemplo)."""
    return recompute_sheet(
        {
            "name": name,
            "day_start": "6:00 AM",
            "day_end": "4:00 PM",
            "rows": [],
        }
    )


def starter_sheet(name: str = "Rutina del día") -> dict[str, Any]:
    """Plantilla inicial solo para el workbook por defecto."""
    return recompute_sheet(
        {
            "name": name,
            "day_start": "6:00 AM",
            "day_end": "4:00 PM",
            "rows": [
                new_row("Despertar / higiene", True, 30, "", ""),
                new_row("Desayuno", True, 30, "", ""),
                new_row(
                    "Bloque de estudio / trabajo",
                    True,
                    120,
                    "Ver plan semanal",
                    "sheet:semana",
                ),
                new_row("Notas / recordatorios", False, 0, "Sin horario fijo", ""),
            ],
        }
    )


def default_workbook() -> dict[str, Any]:
    return {
        "active_sheet_id": "dia",
        "sheets": {
            "dia": starter_sheet("Rutina del día"),
            "semana": recompute_sheet(
                {
                    "name": "Semana",
                    "day_start": "6:00 AM",
                    "day_end": "4:00 PM",
                    "rows": [
                        new_row("Lunes — planificar", True, 45, "", "sheet:dia"),
                        new_row(
                            "Martes — estudio",
                            True,
                            90,
                            "Recurso externo",
                            "https://www.notion.so",
                        ),
                        new_row("Miércoles — ejercicio", True, 60, "", ""),
                    ],
                }
            ),
        },
    }
