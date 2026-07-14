from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5


DEFAULT_SECTOR_NAMES: tuple[str, ...] = (
    "Projeto",
    "Serralheria",
    "Montagem",
    "Bicromatização",
    "Pintura",
    "Testes",
    "Qualidade",
    "Expedição",
)

DEFAULT_SECTOR_COLORS: tuple[str, ...] = (
    "#2563eb",
    "#a16207",
    "#16a34a",
    "#7c3aed",
    "#db2777",
    "#0891b2",
    "#0f766e",
    "#475569",
)

CHECK_GROUPS: dict[str, tuple[str, ...]] = {
    "Projetos": ("IT", "Corte/beneficiamento", "Acessórios", "Cadastro no Cybersul"),
    "Compras": ("Chapa", "Motor", "Hélice/Rotor", "Acessórios"),
    "Expedição": ("Plaquetas", "Adesivos", "Embalagem", "Destino", "Transportadora", "Data coleta"),
}

CHECK_FIELD_KEYS: tuple[str, ...] = tuple(
    f"{group}:{field}" for group, fields in CHECK_GROUPS.items() for field in fields
)


def stable_sector_id(name: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"producao-operacional/sector/{name.casefold()}"))
