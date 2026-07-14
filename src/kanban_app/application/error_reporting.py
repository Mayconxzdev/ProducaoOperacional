from __future__ import annotations

import re

_BACKGROUND_PREFIX = "(Background on this error at:"
_EXCEPTION_LINE = re.compile(r"^(?:[\w.]+Error|[\w.]+Exception|[\w.]+Warning):\s*(.+)$")
_SQLALCHEMY_LINE = re.compile(r"^sqlalchemy\.exc\.[\w]+:\s*(.+)$", re.IGNORECASE)
_DBAPI_WRAPPER = re.compile(r"^\([^)]*(?:Error|Exception)\)\s*(.+)$", re.IGNORECASE)


def root_cause_from_trace(trace: str) -> str:
    """Retorna a causa útil e ignora o link genérico e o restante do traceback."""
    lines = [line.strip() for line in str(trace or "").splitlines() if line.strip()]
    for line in reversed(lines):
        if line.startswith(_BACKGROUND_PREFIX) or "sqlalche.me/e/" in line:
            continue
        match = _SQLALCHEMY_LINE.match(line)
        if match:
            value = match.group(1).strip()
            wrapped = _DBAPI_WRAPPER.match(value)
            return wrapped.group(1).strip() if wrapped else value
        match = _EXCEPTION_LINE.match(line)
        if match:
            value = match.group(1).strip()
            wrapped = _DBAPI_WRAPPER.match(value)
            return wrapped.group(1).strip() if wrapped else value
    for line in reversed(lines):
        if not line.startswith(("Traceback", "File ", "[SQL:", "[parameters:")):
            return line
    return "Erro inesperado."


def friendly_error_message(trace: str) -> str:
    cause = root_cause_from_trace(trace)
    normalized = cause.casefold()

    if any(token in normalized for token in ("database is locked", "database table is locked", "database is busy")):
        return (
            "O banco do NAS estava ocupado por outra operação. O aplicativo tentou novamente, "
            "mas não conseguiu concluir. Aguarde alguns segundos e salve outra vez."
        )
    if "no such table" in normalized or "no such column" in normalized or "has no column named" in normalized:
        return (
            "A estrutura do banco no NAS está desatualizada ou incompleta. Nenhuma alteração foi salva. "
            "Feche as outras estações e abra esta versão novamente para executar a correção automática do banco."
        )
    if "readonly database" in normalized or "read-only" in normalized or "attempt to write a readonly" in normalized:
        return (
            "O aplicativo conseguiu ler o banco, mas não possui permissão para gravar no NAS. "
            "Verifique as permissões da pasta compartilhada."
        )
    if "foreign key constraint failed" in normalized:
        return (
            "O setor ou registro relacionado foi alterado em outra estação. Reabra a OP e tente salvar novamente."
        )
    if "unique constraint failed" in normalized:
        return "Já existe um registro com os mesmos dados exclusivos. Reabra a tela e revise as informações."
    if any(token in normalized for token in ("disk i/o error", "network", "i/o error", "unable to open database file")):
        return (
            "Houve falha de comunicação com o banco no NAS. Nenhuma alteração foi salva. "
            "Confirme a rede e o acesso à pasta compartilhada."
        )
    if "database disk image is malformed" in normalized or "malformed" in normalized:
        return (
            "O banco não passou na verificação de integridade. Não continue editando até restaurar um backup válido."
        )
    return cause
