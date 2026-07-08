"""Organización de hojas: pestañas, carpetas y layout del workbook."""

from __future__ import annotations

import copy
import uuid
from typing import Any


def _new_folder_id() -> str:
    return "folder-" + uuid.uuid4().hex[:8]


def ensure_layout(data: dict[str, Any]) -> dict[str, Any]:
    """Garantiza layout[] alineado con sheets{} sin borrar datos."""
    data = copy.deepcopy(data)
    sheets = data.get("sheets") or {}
    layout = data.get("layout")

    if not layout:
        data["layout"] = [{"type": "sheet", "id": sid} for sid in sheets]
        return data

    seen: set[str] = set()
    cleaned: list[dict[str, Any]] = []

    def walk(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            t = item.get("type")
            if t == "sheet":
                sid = item.get("id")
                if sid in sheets and sid not in seen:
                    seen.add(sid)
                    out.append({"type": "sheet", "id": sid})
            elif t == "folder":
                fid = item.get("id") or _new_folder_id()
                name = str(item.get("name") or "Carpeta").strip() or "Carpeta"
                children = walk(item.get("items") or [])
                out.append(
                    {
                        "type": "folder",
                        "id": fid,
                        "name": name,
                        "expanded": bool(item.get("expanded", False)),
                        "items": children,
                    }
                )
        return out

    cleaned = walk(layout)

    for sid in sheets:
        if sid not in seen:
            cleaned.append({"type": "sheet", "id": sid})
            seen.add(sid)

    data["layout"] = cleaned
    return data


def layout_sheet_ids(layout: list[dict[str, Any]]) -> list[str]:
    ids: list[str] = []

    def walk(items: list[dict[str, Any]]) -> None:
        for item in items:
            if item.get("type") == "sheet" and item.get("id"):
                ids.append(item["id"])
            elif item.get("type") == "folder":
                walk(item.get("items") or [])

    walk(layout)
    return ids


def remove_sheet_from_layout(layout: list[dict[str, Any]], sheet_id: str) -> list[dict[str, Any]]:
    layout = copy.deepcopy(layout)

    def walk(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for item in items:
            if item.get("type") == "sheet":
                if item.get("id") != sheet_id:
                    out.append(item)
            elif item.get("type") == "folder":
                item["items"] = walk(item.get("items") or [])
                out.append(item)
        return out

    return walk(layout)


def append_sheet_to_layout(layout: list[dict[str, Any]], sheet_id: str) -> list[dict[str, Any]]:
    layout = copy.deepcopy(layout)
    if sheet_id in layout_sheet_ids(layout):
        return layout
    layout.append({"type": "sheet", "id": sheet_id})
    return layout


def create_folder(layout: list[dict[str, Any]], name: str) -> tuple[list[dict[str, Any]], str]:
    layout = copy.deepcopy(layout)
    fid = _new_folder_id()
    layout.append(
        {
            "type": "folder",
            "id": fid,
            "name": (name or "Carpeta").strip() or "Carpeta",
            "expanded": False,
            "items": [],
        }
    )
    return layout, fid


def move_sheet_in_layout(
    layout: list[dict[str, Any]],
    sheet_id: str,
    *,
    folder_id: str | None = None,
    root_index: int | None = None,
) -> list[dict[str, Any]]:
    """Mueve una hoja a carpeta o a posición en la raíz."""
    layout = remove_sheet_from_layout(layout, sheet_id)
    layout = copy.deepcopy(layout)

    if folder_id:
        for item in layout:
            if item.get("type") == "folder" and item.get("id") == folder_id:
                item.setdefault("items", []).append({"type": "sheet", "id": sheet_id})
                return layout
        layout.append({"type": "sheet", "id": sheet_id})
        return layout

    if root_index is not None:
        root_index = max(0, min(len(layout), int(root_index)))
        layout.insert(root_index, {"type": "sheet", "id": sheet_id})
        return layout

    layout.append({"type": "sheet", "id": sheet_id})
    return layout
