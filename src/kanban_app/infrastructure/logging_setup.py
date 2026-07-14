from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOG_PATH: Path | None = None


def configure_logging(base_dir: Path | None = None) -> Path:
    global _LOG_PATH
    if _LOG_PATH is not None:
        return _LOG_PATH
    base = Path(base_dir) if base_dir is not None else Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "ProducaoOperacional" / "logs"
    base.mkdir(parents=True, exist_ok=True)
    path = base / "producao_operacional.log"
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not any(isinstance(handler, RotatingFileHandler) and getattr(handler, "baseFilename", "") == str(path) for handler in root.handlers):
        handler = RotatingFileHandler(path, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
        root.addHandler(handler)
    _LOG_PATH = path
    return path


def log_path() -> Path:
    return configure_logging()
