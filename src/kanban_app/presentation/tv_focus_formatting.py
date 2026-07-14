from __future__ import annotations

from datetime import date
from collections.abc import Mapping

from kanban_app.domain.enums import OpStatus


_DEFAULT_STATUS_LABELS = {
    OpStatus.PRIORIDADE.value: "Prioridade",
    OpStatus.EM_ATRASO.value: "Em atraso",
    OpStatus.EM_DIA.value: "Em dia",
    OpStatus.AGUARDANDO.value: "Aguardando",
    OpStatus.CONCLUIDO.value: "Concluído",
}


def tv_focus_op_label(value: str) -> str:
    """Mantém o número integral; a largura personalizada decide o corte visual."""
    return str(value or "").strip()


def tv_focus_status_label(status: OpStatus | str, labels: Mapping[str, str] | None = None) -> str:
    configured = labels or {}
    value = status.value if isinstance(status, OpStatus) else str(status or "")
    return str(configured.get(value) or _DEFAULT_STATUS_LABELS.get(value) or value.replace("_", " ").title())


def tv_focus_sector_label(
    sector_id: str | None,
    sector_name: str,
    labels: Mapping[str, str] | None = None,
) -> str:
    text = str(sector_name or "").strip()
    configured = labels or {}
    if sector_id and str(sector_id) in configured:
        return str(configured[str(sector_id)] or text)
    return text


def tv_focus_date_label(value: date | None, display_format: str = "dd/MM/yyyy") -> str:
    if value is None:
        return ""
    formats = {
        "dd/MM/yyyy": "%d/%m/%Y",
        "dd/MM/yy": "%d/%m/%y",
        "dd/MM": "%d/%m",
    }
    return value.strftime(formats.get(str(display_format), "%d/%m/%Y"))
