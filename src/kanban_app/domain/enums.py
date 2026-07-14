from __future__ import annotations

from enum import Enum


class OpStatus(str, Enum):
    PRIORIDADE = "PRIORIDADE"
    EM_ATRASO = "EM_ATRASO"
    EM_DIA = "EM_DIA"
    AGUARDANDO = "AGUARDANDO"
    CONCLUIDO = "CONCLUIDO"


class CheckState(str, Enum):
    NAO_INFORMADO = "NAO_INFORMADO"
    SIM = "SIM"
    NAO = "NAO"


_LEGACY_STATUS_ALIASES = {
    "ATENCAO": OpStatus.EM_ATRASO,
    "ATRASADA": OpStatus.EM_ATRASO,
    "ATRASADO": OpStatus.EM_ATRASO,
    "EM ATENCAO": OpStatus.EM_ATRASO,
    "EM_ATENCAO": OpStatus.EM_ATRASO,
    "PRONTO": OpStatus.CONCLUIDO,
    "RESOLVIDA": OpStatus.CONCLUIDO,
    "RESOLVIDO": OpStatus.CONCLUIDO,
    "AGUARDANDO_ADM": OpStatus.AGUARDANDO,
}


def coerce_op_status(value: OpStatus | str | object, default: OpStatus = OpStatus.EM_DIA) -> OpStatus:
    """Normaliza valores vindos do Qt, JSON e bases legadas sem pressupor `.value`."""
    if isinstance(value, OpStatus):
        return value
    raw = str(value or "").strip()
    if raw.startswith("OpStatus."):
        raw = raw.split(".", 1)[1]
    normalized = raw.upper().replace("-", "_").replace(" ", "_")
    if normalized in _LEGACY_STATUS_ALIASES:
        return _LEGACY_STATUS_ALIASES[normalized]
    try:
        return OpStatus(normalized)
    except ValueError:
        return default


def coerce_check_state(value: CheckState | str | object, default: CheckState = CheckState.NAO_INFORMADO) -> CheckState:
    if isinstance(value, CheckState):
        return value
    raw = str(value or "").strip()
    if raw.startswith("CheckState."):
        raw = raw.split(".", 1)[1]
    normalized = raw.upper().replace("-", "_").replace(" ", "_")
    aliases = {
        "": default,
        "NAO_INFORMADO": CheckState.NAO_INFORMADO,
        "NÃO_INFORMADO": CheckState.NAO_INFORMADO,
        "NÃO INFORMADO": CheckState.NAO_INFORMADO,
        "SIM": CheckState.SIM,
        "NAO": CheckState.NAO,
        "NÃO": CheckState.NAO,
    }
    return aliases.get(normalized, default)
