from __future__ import annotations

from collections.abc import Mapping, Sequence
from math import floor
import re


TV_COLUMNS = (
    ("op", "OP", "OP"),
    ("status", "Status", "Status"),
    ("cliente", "Cliente", "Cliente"),
    ("modelo", "Modelo", "Modelo"),
    ("voltagem", "Voltagem", "V"),
    ("quantidade", "Quantidade", "Qtd"),
    ("inicio", "Início", "Início"),
    ("entrega", "Entrega", "Ent."),
    ("setor", "Setor", "Set."),
    ("pendencia", "Pendência", "Pendência"),
)

TV_COLUMN_KEYS = tuple(key for key, _label, _short in TV_COLUMNS)
TV_COLUMN_LABELS = {key: label for key, label, _short in TV_COLUMNS}
TV_COLUMN_SHORT_LABELS = {key: short for key, _label, short in TV_COLUMNS}

# Pesos relativos. Eles são sempre normalizados para ocupar exatamente o
# viewport da TV; por isso funcionam em qualquer resolução e não geram barra
# horizontal.
TV_DEFAULT_WIDTHS = {
    "op": 96,
    "status": 155,
    "cliente": 365,
    "modelo": 490,
    "voltagem": 110,
    "quantidade": 72,
    "inicio": 112,
    "entrega": 125,
    "setor": 190,
    "pendencia": 260,
}

# A TV mostra várias OPs ao mesmo tempo. Escalas individuais evitam que os
# campos de negócio sejam cortados em telas Full HD, sem sacrificar os dados
# importantes para uma fonte exageradamente grande.
TV_DEFAULT_FONT_SCALES = {
    "op": 48,
    "status": 42,
    "cliente": 35,
    "modelo": 48,
    "voltagem": 35,
    "quantidade": 70,
    "inicio": 35,
    "entrega": 35,
    "setor": 35,
    "pendencia": 40,
}
TV_DEFAULT_VISIBLE_COLUMNS = ["op", "status", "cliente", "modelo", "voltagem", "quantidade", "entrega", "setor"]
TV_DEFAULT_ALIGNMENTS = {
    "op": "center",
    "status": "center",
    "cliente": "left",
    "modelo": "left",
    "voltagem": "center",
    "quantidade": "center",
    "inicio": "center",
    "entrega": "center",
    "setor": "center",
    "pendencia": "left",
}
TV_DEFAULT_FORMATS = {key: "text" for key in TV_COLUMN_KEYS}
TV_DEFAULT_FORMATS.update({"inicio": "dd/MM/yy", "entrega": "dd/MM/yy"})
TV_DEFAULT_HEADERS = dict(TV_COLUMN_LABELS)
TV_DEFAULT_HEADERS.update({"voltagem": "V", "quantidade": "Qtd."})
TV_DEFAULT_STATUS_LABELS = {
    "PRIORIDADE": "Prioridade",
    "EM_ATRASO": "Em atraso",
    "EM_DIA": "Em dia",
    "AGUARDANDO": "Aguardando",
    "CONCLUIDO": "Concluído",
}

_ALIGNMENT_VALUES = {"left", "center", "right"}
_DATE_FORMAT_VALUES = {"dd/MM/yyyy", "dd/MM/yy", "dd/MM"}
_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def default_tv_settings() -> dict[str, object]:
    return {
        "visible_columns": list(TV_DEFAULT_VISIBLE_COLUMNS),
        "column_order": list(TV_COLUMN_KEYS),
        "column_widths": dict(TV_DEFAULT_WIDTHS),
        "column_font_scales": dict(TV_DEFAULT_FONT_SCALES),
        "column_headers": dict(TV_DEFAULT_HEADERS),
        "column_alignments": dict(TV_DEFAULT_ALIGNMENTS),
        "column_formats": dict(TV_DEFAULT_FORMATS),
        "sector_labels": {},
        "status_labels": dict(TV_DEFAULT_STATUS_LABELS),
        "sector_filter_mode": "all",
        "visible_sector_ids": [],
        "page_interval_seconds": 13,
        "lines_per_page": 10,
        "font_scale_percent": 100,
        "header_scale_percent": 100,
        "header_height_px": 48,
        "cell_padding_px": 7,
        "bold_rows": True,
        "show_grid": True,
        "header_background": "#1d3557",
        "header_foreground": "#ffffff",
        "screen_background": "#0f172a",
        "grid_color": "#10233d",
    }


def normalize_tv_settings(values: Mapping[str, object] | None) -> dict[str, object]:
    defaults = default_tv_settings()
    values = values or {}
    allowed_order = list(TV_COLUMN_KEYS)
    allowed = set(allowed_order)

    visible_raw = values.get("visible_columns", defaults["visible_columns"])
    visible = (
        [str(key) for key in visible_raw]
        if isinstance(visible_raw, Sequence) and not isinstance(visible_raw, (str, bytes))
        else list(defaults["visible_columns"])
    )
    visible = list(dict.fromkeys(key for key in visible if key in allowed))
    # OP é a referência principal do painel e nunca pode desaparecer por uma
    # configuração antiga ou incompleta.
    if "op" not in visible:
        visible.insert(0, "op")

    order_raw = values.get("column_order", defaults["column_order"])
    order = (
        [str(key) for key in order_raw]
        if isinstance(order_raw, Sequence) and not isinstance(order_raw, (str, bytes))
        else list(defaults["column_order"])
    )
    order = list(dict.fromkeys(key for key in order if key in allowed))
    order.extend(key for key in allowed_order if key not in order)

    widths = _normalize_int_map(values.get("column_widths"), TV_DEFAULT_WIDTHS, low=20, high=5000)
    font_scales = _normalize_int_map(values.get("column_font_scales"), TV_DEFAULT_FONT_SCALES, low=35, high=250)

    headers = _normalize_text_map(values.get("column_headers"), TV_DEFAULT_HEADERS, allowed_keys=allowed, max_length=40)
    alignments = _normalize_choice_map(
        values.get("column_alignments"), TV_DEFAULT_ALIGNMENTS, allowed_values=_ALIGNMENT_VALUES
    )
    formats = _normalize_choice_map(values.get("column_formats"), TV_DEFAULT_FORMATS, allowed_values=_DATE_FORMAT_VALUES | {"text"})
    for key in allowed - {"inicio", "entrega"}:
        formats[key] = "text"

    # Migra a antiga opção global de abreviação para valores individuais. A
    # partir daqui cada cabeçalho e cada data podem ser alterados separadamente.
    old_compact = bool(values.get("abbreviate_headers_and_dates", values.get("compact_labels", False)))
    if old_compact and "column_headers" not in values:
        headers.update(TV_COLUMN_SHORT_LABELS)
    if old_compact and "column_formats" not in values:
        formats["inicio"] = "dd/MM"
        formats["entrega"] = "dd/MM"

    sector_labels = _normalize_free_text_map(values.get("sector_labels"), max_length=50)
    status_labels = _normalize_text_map(
        values.get("status_labels"), TV_DEFAULT_STATUS_LABELS, allowed_keys=set(TV_DEFAULT_STATUS_LABELS), max_length=40
    )

    visible_sector_raw = values.get("visible_sector_ids", defaults["visible_sector_ids"])
    visible_sector_ids = (
        list(dict.fromkeys(str(value) for value in visible_sector_raw if str(value)))
        if isinstance(visible_sector_raw, Sequence) and not isinstance(visible_sector_raw, (str, bytes))
        else []
    )
    filter_mode = str(values.get("sector_filter_mode", defaults["sector_filter_mode"]) or "all").casefold()
    if filter_mode not in {"all", "selected"}:
        filter_mode = "all"

    def number(name: str, low: int, high: int) -> int:
        try:
            return max(low, min(high, int(values.get(name, defaults[name]))))
        except (TypeError, ValueError):
            return int(defaults[name])

    def boolean(name: str) -> bool:
        value = values.get(name, defaults[name])
        if isinstance(value, str):
            return value.strip().casefold() not in {"", "0", "false", "nao", "não", "off"}
        return bool(value)

    def color(name: str) -> str:
        raw = str(values.get(name, defaults[name]) or "").strip()
        return raw.lower() if _HEX_COLOR.fullmatch(raw) else str(defaults[name])

    return {
        "visible_columns": visible,
        "column_order": order,
        "column_widths": widths,
        "column_font_scales": font_scales,
        "column_headers": headers,
        "column_alignments": alignments,
        "column_formats": formats,
        "sector_labels": sector_labels,
        "status_labels": status_labels,
        "sector_filter_mode": filter_mode,
        "visible_sector_ids": visible_sector_ids,
        "page_interval_seconds": number("page_interval_seconds", 2, 300),
        "lines_per_page": number("lines_per_page", 1, 30),
        "font_scale_percent": number("font_scale_percent", 50, 250),
        "header_scale_percent": number("header_scale_percent", 50, 250),
        "header_height_px": number("header_height_px", 28, 140),
        "cell_padding_px": number("cell_padding_px", 0, 24),
        "bold_rows": boolean("bold_rows"),
        "show_grid": boolean("show_grid"),
        "header_background": color("header_background"),
        "header_foreground": color("header_foreground"),
        "screen_background": color("screen_background"),
        "grid_color": color("grid_color"),
    }


def fit_column_widths(
    ordered_keys: Sequence[str],
    weights: Mapping[str, object],
    available_width: int,
    *,
    minimum_width: int = 28,
) -> dict[str, int]:
    """Distribui toda a largura preservando a proporção configurada."""

    keys = list(dict.fromkeys(str(key) for key in ordered_keys if str(key)))
    if not keys:
        return {}
    total_width = max(len(keys), int(available_width))
    min_width = max(1, min(int(minimum_width), total_width // len(keys)))

    normalized_weights: dict[str, float] = {}
    for key in keys:
        try:
            normalized_weights[key] = max(1.0, float(weights.get(key, 100)))
        except (TypeError, ValueError):
            normalized_weights[key] = 100.0

    fixed: dict[str, int] = {}
    remaining = list(keys)
    remaining_width = total_width
    while remaining:
        total_weight = sum(normalized_weights[key] for key in remaining) or float(len(remaining))
        too_small = [
            key for key in remaining if remaining_width * normalized_weights[key] / total_weight < min_width
        ]
        if not too_small:
            break
        for key in too_small:
            fixed[key] = min_width
            remaining.remove(key)
            remaining_width -= min_width
        if remaining_width <= 0:
            base, extra = divmod(total_width, len(keys))
            return {key: base + (1 if index < extra else 0) for index, key in enumerate(keys)}

    if not remaining:
        return fixed

    total_weight = sum(normalized_weights[key] for key in remaining) or float(len(remaining))
    raw = {key: remaining_width * normalized_weights[key] / total_weight for key in remaining}
    allocated = {key: floor(raw[key]) for key in remaining}
    missing = remaining_width - sum(allocated.values())
    ranked = sorted(
        remaining,
        key=lambda key: (raw[key] - allocated[key], normalized_weights[key]),
        reverse=True,
    )
    for key in ranked[:missing]:
        allocated[key] += 1

    result = {key: fixed.get(key, allocated.get(key, min_width)) for key in keys}
    delta = total_width - sum(result.values())
    if delta:
        result[keys[-1]] += delta
    return result


def _normalize_int_map(raw: object, defaults: Mapping[str, int], *, low: int, high: int) -> dict[str, int]:
    result = dict(defaults)
    if not isinstance(raw, Mapping):
        return result
    for key, value in raw.items():
        if str(key) not in result:
            continue
        try:
            result[str(key)] = max(low, min(high, int(value)))
        except (TypeError, ValueError):
            continue
    return result


def _normalize_text_map(
    raw: object,
    defaults: Mapping[str, str],
    *,
    allowed_keys: set[str],
    max_length: int,
) -> dict[str, str]:
    result = dict(defaults)
    if not isinstance(raw, Mapping):
        return result
    for key, value in raw.items():
        key = str(key)
        if key not in allowed_keys:
            continue
        text = str(value or "").strip()[:max_length]
        result[key] = text or result[key]
    return result


def _normalize_choice_map(
    raw: object,
    defaults: Mapping[str, str],
    *,
    allowed_values: set[str],
) -> dict[str, str]:
    result = dict(defaults)
    if not isinstance(raw, Mapping):
        return result
    for key, value in raw.items():
        key = str(key)
        text = str(value or "")
        if key in result and text in allowed_values:
            result[key] = text
    return result


def _normalize_free_text_map(raw: object, *, max_length: int) -> dict[str, str]:
    if not isinstance(raw, Mapping):
        return {}
    result: dict[str, str] = {}
    for key, value in raw.items():
        text = str(value or "").strip()[:max_length]
        if text:
            result[str(key)] = text
    return result
