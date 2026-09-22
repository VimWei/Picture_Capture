"""User-level recent-project registry (never deletes project data)."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path


def default_recent_projects_path() -> Path:
    base = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA")
    root = Path(base).expanduser() if base else Path.home() / ".picture_capture"
    return root / "PictureCapture" / "recent_projects.json" if base else root / "recent_projects.json"


def load_recent_projects(path: Path | None = None) -> list[dict[str, str]]:
    target = path or default_recent_projects_path()
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
        return [row for row in value if isinstance(row, dict) and row.get("path")] if isinstance(value, list) else []
    except (OSError, ValueError, TypeError):
        return []


def save_recent_projects(rows: list[dict[str, str]], path: Path | None = None) -> None:
    target = path or default_recent_projects_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(".tmp")
    temp.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, target)


def touch_recent_project(root: Path, path: Path | None = None) -> list[dict[str, str]]:
    resolved = root.expanduser().resolve()
    rows = [row for row in load_recent_projects(path) if Path(str(row["path"])).expanduser() != resolved]
    rows.insert(0, {"name": resolved.name, "path": str(resolved), "opened_at": datetime.now(timezone.utc).isoformat()})
    save_recent_projects(rows[:30], path)
    return rows[:30]


def remove_recent_project(root: Path, path: Path | None = None) -> list[dict[str, str]]:
    """Remove only the registry row. No project path is ever unlinked."""
    resolved = root.expanduser().resolve()
    rows = [row for row in load_recent_projects(path) if Path(str(row["path"])).expanduser() != resolved]
    save_recent_projects(rows, path)
    return rows
