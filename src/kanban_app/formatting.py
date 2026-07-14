from __future__ import annotations

import re
from datetime import date, datetime


def parse_br_date(value: str | None) -> date | None:
    """Interpreta datas brasileiras digitadas com ou sem separadores.

    Aceita, entre outros: ``13082026``, ``13/08/2026``, ``13-08-2026`` e
    ``13.08.2026``. Valores vazios continuam vazios e datas inválidas retornam
    ``None``.
    """

    text = str(value or "").strip()
    if not text:
        return None

    digits = re.sub(r"\D", "", text)
    candidates: list[str] = []
    if len(digits) == 8:
        candidates.append(digits)
    elif len(digits) == 6:
        candidates.append(digits)

    normalized = re.sub(r"[.\-]", "/", text)
    candidates.append(normalized)

    for candidate in dict.fromkeys(candidates):
        for pattern in ("%d%m%Y", "%d%m%y", "%d/%m/%Y", "%d/%m/%y"):
            try:
                return datetime.strptime(candidate, pattern).date()
            except ValueError:
                continue
    return None


def format_br_date(value: date | None) -> str:
    return value.strftime("%d/%m/%Y") if value else ""


def normalize_voltage_value(value: str | None) -> str:
    """Normaliza a tensão armazenada sem acrescentar a unidade ``V``.

    Exemplos: ``440 V`` → ``440``; ``220/380VAC`` → ``220/380``; ``N/A`` é
    preservado. Textos incomuns são mantidos sem espaços supérfluos para não
    destruir informação legítima digitada pelo operador.
    """

    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return ""

    compact = re.sub(r"\s+", "", text.upper())
    if compact in {"N/A", "NA", "N.A.", "N/D", "ND", "NÃOAPLICÁVEL", "NAOAPLICAVEL"}:
        return "N/A"

    match = re.fullmatch(
        r"(?P<first>\d{2,4})(?:[/\\-](?P<second>\d{2,4}))?(?:V|VAC|VOLTS?|VOLT)?",
        compact,
        flags=re.IGNORECASE,
    )
    if match:
        first = match.group("first")
        second = match.group("second")
        return f"{first}/{second}" if second else first

    # Fallback conservador: remove apenas unidade terminal, sem alterar o resto.
    cleaned = re.sub(r"\s*(?:VAC|VOLTS?|VOLT|V)\s*$", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*[/\\-]\s*", "/", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def format_tensao_display(value: str | None) -> str:
    text = normalize_voltage_value(value)
    if not text:
        return "-"
    if text == "N/A":
        return text

    compact = re.sub(r"\s+", "", text.upper())
    match = re.fullmatch(r"(?P<digits>\d{2,4})(?:V)?(?P<motor>M|\(M\))?", compact)
    if match is None:
        return text

    digits = match.group("digits")
    has_motor_suffix = bool(match.group("motor"))
    if has_motor_suffix:
        return f"{digits}V (M)"
    return f"{digits}V"
