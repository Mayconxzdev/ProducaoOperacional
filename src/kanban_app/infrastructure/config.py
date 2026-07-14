from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SmtpConfig:
    enabled: bool = False
    host: str = ""
    port: int = 465
    username: str = ""
    password: str = ""
    from_email: str = ""
    security_mode: str = "ssl_tls"


@dataclass(frozen=True, slots=True)
class AppConfig:
    config_path: Path
    nas_root: Path
    database_path: Path
    backups_dir: Path
    state_dir: Path
    imports_dir: Path
    theme_mode: str
    smtp: SmtpConfig


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path).resolve()
    payload = json.loads(config_path.read_text(encoding="utf-8-sig"))
    nas_root = Path(str(payload.get("nas_root") or config_path.parent.parent))
    database_path = Path(str(payload.get("database_path") or nas_root / "data" / "producao.db"))
    smtp_raw = payload.get("smtp") if isinstance(payload.get("smtp"), dict) else {}
    return AppConfig(
        config_path=config_path,
        nas_root=nas_root,
        database_path=database_path,
        backups_dir=Path(str(payload.get("backups_dir") or nas_root / "backups")),
        state_dir=Path(str(payload.get("state_dir") or nas_root / "state")),
        imports_dir=Path(str(payload.get("imports_incoming_dir") or nas_root / "imports")),
        theme_mode=str(payload.get("theme_mode") or "system"),
        smtp=SmtpConfig(
            enabled=bool(smtp_raw.get("enabled", False)),
            host=str(smtp_raw.get("host") or ""),
            port=int(smtp_raw.get("port") or 465),
            username=str(smtp_raw.get("username") or ""),
            password=str(smtp_raw.get("password") or ""),
            from_email=str(smtp_raw.get("from_email") or ""),
            security_mode=str(smtp_raw.get("security_mode") or "ssl_tls"),
        ),
    )
