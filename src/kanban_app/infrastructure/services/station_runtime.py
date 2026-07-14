from __future__ import annotations

import json
import os
import re
import socket
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path

from kanban_app.application.dto import OpListDTO, StationRoleDTO
from kanban_app.domain.enums import OpStatus, coerce_op_status


def station_id() -> str:
    raw = os.environ.get("KANBAN_MACHINE_ID") or os.environ.get("COMPUTERNAME") or socket.gethostname()
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(raw or "estacao").strip()) or "estacao"


class StationRuntimeStore:
    def __init__(self, root: Path | None = None):
        base = root or Path(os.environ.get("KANBAN_LOCAL_APP_DIR") or Path(os.environ.get("LOCALAPPDATA", Path.home())) / "ProducaoOperacional")
        self.root = Path(base)
        self.root.mkdir(parents=True, exist_ok=True)

    @property
    def role_path(self) -> Path:
        return self.root / "station_role.json"

    @property
    def cache_path(self) -> Path:
        return self.root / "last_ops_cache.json"

    @property
    def appearance_path(self) -> Path:
        """Preferência visual local; não deve ser sincronizada pelo banco do NAS."""

        return self.root / "office_appearance.json"

    def load_role(self) -> StationRoleDTO:
        try:
            raw = json.loads(self.role_path.read_text(encoding="utf-8"))
        except Exception:
            return StationRoleDTO()
        return StationRoleDTO(
            role=str(raw.get("role") or "office"),
            fullscreen=bool(raw.get("fullscreen", False)),
            monitor_name=str(raw.get("monitor_name") or ""),
            start_with_windows=bool(raw.get("start_with_windows", False)),
        )

    def save_role(self, role: StationRoleDTO) -> None:
        self._atomic_write(self.role_path, asdict(role))

    def save_cache(self, ops: list[OpListDTO]) -> None:
        self._atomic_write(
            self.cache_path,
            [
                {
                    **asdict(op),
                    "status": op.status.value if isinstance(op.status, OpStatus) else str(op.status),
                    "data_inicio": op.data_inicio.isoformat() if op.data_inicio else None,
                    "data_entrega": op.data_entrega.isoformat() if op.data_entrega else None,
                    "updated_at": op.updated_at.isoformat(),
                }
                for op in ops
            ],
        )

    def load_cache(self) -> list[OpListDTO]:
        try:
            rows = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        result: list[OpListDTO] = []
        for row in rows if isinstance(rows, list) else []:
            try:
                result.append(
                    OpListDTO(
                        **{
                            **row,
                            "status": coerce_op_status(row.get("status")),
                            "data_inicio": date.fromisoformat(row["data_inicio"]) if row.get("data_inicio") else None,
                            "data_entrega": date.fromisoformat(row["data_entrega"]) if row.get("data_entrega") else None,
                            "updated_at": datetime.fromisoformat(row["updated_at"]),
                        }
                    )
                )
            except Exception:
                continue
        return result

    def clear_cache(self) -> None:
        self.cache_path.unlink(missing_ok=True)

    def load_theme_mode(self, default: str = "system") -> str:
        fallback = self._normalize_theme_mode(default)
        try:
            raw = json.loads(self.appearance_path.read_text(encoding="utf-8"))
        except Exception:
            return fallback
        return self._normalize_theme_mode(raw.get("theme_mode") if isinstance(raw, dict) else fallback)

    def save_theme_mode(self, theme_mode: str) -> None:
        self._atomic_write(self.appearance_path, {"theme_mode": self._normalize_theme_mode(theme_mode)})

    @staticmethod
    def _normalize_theme_mode(value: object) -> str:
        candidate = str(value or "system").casefold()
        return candidate if candidate in {"system", "light", "dark"} else "system"

    @staticmethod
    def _atomic_write(path: Path, payload) -> None:
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)
