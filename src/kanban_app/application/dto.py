from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date

from kanban_app.domain.enums import OpStatus


@dataclass(frozen=True, slots=True)
class SectorDTO:
    id: str
    nome: str
    ordem: int
    cor: str
    cor_texto: str
    ativo: bool


@dataclass(frozen=True, slots=True)
class CheckEntryDTO:
    """Texto livre de um campo do acompanhamento interno da OP.

    O atributo conservou o nome ``state`` por compatibilidade com os registros
    já existentes, mas não representa mais uma lista fechada de opções.
    """

    field_key: str
    state: str = ""
    updated_at: datetime | None = None
    station_id: str = ""


@dataclass(frozen=True, slots=True)
class OpFormDTO:
    numero_op: str = ""
    cliente: str = ""
    modelo: str = ""
    quantidade: int | None = None
    voltagem: str = ""
    data_inicio: date | None = None
    data_entrega: date | None = None
    setor_id: str | None = None
    status: OpStatus = OpStatus.EM_DIA
    pendencia: str = ""
    acompanhamento: tuple[CheckEntryDTO, ...] = ()


@dataclass(frozen=True, slots=True)
class OpListDTO:
    id: int
    numero_op: str
    cliente: str
    modelo: str
    quantidade: int | None
    voltagem: str
    data_inicio: date | None
    data_entrega: date | None
    setor_id: str | None
    setor_nome: str
    setor_cor: str
    setor_cor_texto: str
    status: OpStatus
    pendencia: str
    row_version: int
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class OpDetailDTO(OpListDTO):
    completed_at: datetime | None
    archived: bool
    archived_at: datetime | None
    acompanhamento: tuple[CheckEntryDTO, ...] = ()


@dataclass(frozen=True, slots=True)
class HistoryEntryDTO:
    id: int
    op_id: int
    event_type: str
    field_name: str
    old_value: str
    new_value: str
    station_id: str
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class ImportPreviewDTO:
    source_path: str
    form: OpFormDTO
    missing_fields: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    duplicate_op_ids: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class OpImportSourceDTO:
    """Estado técnico de um documento observado pela integração automática."""

    source_key: str
    state: str
    source_size: int | None = None
    source_modified_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class DeadlineAlertDTO:
    op: OpListDTO
    milestone_days: int
    days_remaining: int


@dataclass(frozen=True, slots=True)
class StationRoleDTO:
    role: str = "office"
    fullscreen: bool = False
    monitor_name: str = ""
    start_with_windows: bool = False


@dataclass(frozen=True, slots=True)
class OpReminderFormDTO:
    mensagem: str
    horario: str
    op_id: int | None = None
    numero_op: str = ""
    cliente: str = ""
    modelo: str = ""
    data_inicio: date | None = None
    data_fim: date | None = None
    duracao_segundos: int = 30
    tipo_recorrencia: str = "ONCE"
    dias_semana: tuple[str, ...] = ()
    ativo: bool = True


@dataclass(frozen=True, slots=True)
class OpReminderDTO:
    id: str
    mensagem: str
    horario: str
    op_id: int | None
    numero_op: str
    cliente: str
    modelo: str
    data_inicio: date | None
    data_fim: date | None
    duracao_segundos: int
    tipo_recorrencia: str
    dias_semana: tuple[str, ...]
    ativo: bool
    created_by_station: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class MonthlyOpItemDTO:
    op_id: int
    numero_op: str
    cliente: str
    modelo: str
    quantidade: int | None
    voltagem: str
    setor_nome: str
    status: str
    data_inicio: date | None
    data_entrega: date | None
    completed_at: datetime | None
    dias_producao: int | None
    entregue_no_prazo: bool | None
    esta_em_atraso: bool
    categoria: str


@dataclass(frozen=True, slots=True)
class MonthlySectorStatDTO:
    setor_id: str | None
    setor_nome: str
    cor: str
    total_ops: int
    total_quantidade: int


@dataclass(frozen=True, slots=True)
class MonthlyWeekStatDTO:
    label: str
    data_inicio: date
    data_fim: date
    entradas: int
    saidas: int


@dataclass(frozen=True, slots=True)
class MonthlyReportSummaryDTO:
    ano: int
    mes: int
    nome_mes: str
    periodo_inicio: date
    periodo_fim: date
    data_referencia: date
    is_mes_fechado: bool
    total_criadas: int
    total_criadas_pecas: int
    total_concluidas: int
    total_concluidas_pecas: int
    concluidas_no_prazo: int
    concluidas_com_atraso: int
    taxa_pontualidade: float
    taxa_conformidade: float
    lead_time_medio_dias: float
    em_producao_agora: int
    em_atraso_agora: int
    previsao_restante_mes: int
    setores_stats: tuple[MonthlySectorStatDTO, ...]
    semanas_stats: tuple[MonthlyWeekStatDTO, ...]
    ops: tuple[MonthlyOpItemDTO, ...]

