from __future__ import annotations

import json
import re
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
class OpDiscoveryConfig:
    enabled: bool = False
    source_root_candidates: tuple[Path, ...] = ()
    production_relative_path: Path = Path("Clientes/00_PRODUZINDO")
    groups: tuple[str, ...] = ("00_GRUPO_A", "00_GRUPO_B")
    document_extensions: tuple[str, ...] = (".odt", ".docx", ".pdf")
    schedule_days: tuple[str, ...] = ("monday", "tuesday", "wednesday", "thursday", "friday")
    schedule_times: tuple[str, ...] = ("08:00", "14:00", "17:00")
    initial_sector_name: str = "Projeto"
    worker_lease_minutes: int = 20


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
    op_discovery: OpDiscoveryConfig


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path).resolve()
    payload = json.loads(config_path.read_text(encoding="utf-8-sig"))
    nas_root = Path(str(payload.get("nas_root") or config_path.parent.parent))
    database_path = Path(str(payload.get("database_path") or nas_root / "data" / "producao.db"))
    smtp_raw = payload.get("smtp") if isinstance(payload.get("smtp"), dict) else {}
    discovery_raw = payload.get("op_discovery") if isinstance(payload.get("op_discovery"), dict) else {}
    root_candidates = discovery_raw.get("source_root_candidates")
    if not isinstance(root_candidates, list):
        root_candidates = []
    groups = discovery_raw.get("groups")
    if not isinstance(groups, list) or not groups:
        groups = ["00_GRUPO_A", "00_GRUPO_B"]
    extensions = discovery_raw.get("document_extensions")
    if not isinstance(extensions, list) or not extensions:
        extensions = [".odt", ".docx", ".pdf"]
    schedule = discovery_raw.get("schedule") if isinstance(discovery_raw.get("schedule"), dict) else {}
    schedule_days = schedule.get("days") if isinstance(schedule.get("days"), list) else ["monday", "tuesday", "wednesday", "thursday", "friday"]
    schedule_times = schedule.get("times") if isinstance(schedule.get("times"), list) else ["08:00", "14:00", "17:00"]
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
        op_discovery=OpDiscoveryConfig(
            enabled=bool(discovery_raw.get("enabled", False)),
            source_root_candidates=tuple(Path(str(item)) for item in root_candidates if str(item or "").strip()),
            production_relative_path=Path(str(discovery_raw.get("production_relative_path") or "Clientes/00_PRODUZINDO")),
            groups=tuple(str(item).strip() for item in groups if str(item or "").strip()),
            document_extensions=tuple(
                suffix for suffix in (str(item or "").strip().casefold() for item in extensions)
                if suffix in {".odt", ".docx", ".pdf"}
            ) or (".odt", ".docx", ".pdf"),
            schedule_days=tuple(dict.fromkeys(
                value for value in (str(item or "").strip().casefold() for item in schedule_days)
                if value in {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}
            )),
            schedule_times=tuple(dict.fromkeys(
                value for value in (str(item or "").strip() for item in schedule_times)
                if re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value)
            )),
            initial_sector_name=str(discovery_raw.get("initial_sector_name") or "Projeto").strip() or "Projeto",
            worker_lease_minutes=max(5, min(120, int(discovery_raw.get("worker_lease_minutes") or 20))),
        ),
    )


def save_op_discovery_config(path: str | Path, discovery: OpDiscoveryConfig) -> None:
    """Persiste somente a configuração da integração, preservando segredos locais."""

    config_path = Path(path)
    payload = json.loads(config_path.read_text(encoding="utf-8-sig"))
    payload["op_discovery"] = {
        "enabled": bool(discovery.enabled),
        "source_root_candidates": [str(item) for item in discovery.source_root_candidates],
        "production_relative_path": str(discovery.production_relative_path),
        "groups": list(discovery.groups),
        "document_extensions": list(discovery.document_extensions),
        "schedule": {
            "days": list(discovery.schedule_days),
            "times": list(discovery.schedule_times),
        },
        "initial_sector_name": discovery.initial_sector_name,
        "worker_lease_minutes": int(discovery.worker_lease_minutes),
    }
    temporary = config_path.with_suffix(config_path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(config_path)
