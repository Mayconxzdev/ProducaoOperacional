from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from kanban_app.infrastructure.db.base import Base


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class AppMetaModel(Base):
    __tablename__ = "app_meta"

    meta_key: Mapped[str] = mapped_column(String(120), primary_key=True)
    meta_value: Mapped[str] = mapped_column(Text, nullable=False, default="")


class SectorModel(Base):
    __tablename__ = "sectors"
    __table_args__ = (UniqueConstraint("nome", name="uq_sectors_nome"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    ordem: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    cor: Mapped[str] = mapped_column(String(16), nullable=False, default="#475569")
    cor_texto: Mapped[str] = mapped_column(String(16), nullable=False, default="#ffffff")
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)


class OpModel(Base):
    __tablename__ = "ops"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    numero_op: Mapped[str] = mapped_column(String(80), nullable=False, default="", index=True)
    cliente: Mapped[str] = mapped_column(String(200), nullable=False, default="", index=True)
    modelo: Mapped[str] = mapped_column(String(240), nullable=False, default="")
    quantidade: Mapped[int | None] = mapped_column(Integer, nullable=True)
    voltagem: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    data_inicio: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    data_entrega: Mapped[datetime | None] = mapped_column(Date, nullable=True, index=True)
    setor_id: Mapped[str | None] = mapped_column(ForeignKey("sectors.id", ondelete="RESTRICT"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="EM_DIA", index=True)
    pendencia: Mapped[str] = mapped_column(Text, nullable=False, default="")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now, onupdate=utc_now, index=True)


class CheckEntryModel(Base):
    __tablename__ = "op_acompanhamento"
    __table_args__ = (UniqueConstraint("op_id", "field_key", name="uq_acompanhamento_op_field"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    op_id: Mapped[int] = mapped_column(ForeignKey("ops.id", ondelete="CASCADE"), nullable=False, index=True)
    field_key: Mapped[str] = mapped_column(String(120), nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="NAO_INFORMADO")
    station_id: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)


class OpHistoryModel(Base):
    __tablename__ = "op_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    op_id: Mapped[int] = mapped_column(ForeignKey("ops.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    field_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    old_value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    new_value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    station_id: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now, index=True)


class AppSettingModel(Base):
    __tablename__ = "app_settings"

    setting_key: Mapped[str] = mapped_column(String(160), primary_key=True)
    setting_value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_station_id: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)


class DeadlineAlertSendModel(Base):
    __tablename__ = "deadline_alert_sends"
    __table_args__ = (UniqueConstraint("op_id", "milestone_date", "milestone_days", name="uq_deadline_alert_milestone"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    op_id: Mapped[int] = mapped_column(ForeignKey("ops.id", ondelete="CASCADE"), nullable=False, index=True)
    milestone_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    milestone_days: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING", index=True)
    error: Mapped[str] = mapped_column(Text, nullable=False, default="")
    sent_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)


class OpImportSourceModel(Base):
    """Rastreia a fonte para impedir reprocessamento entre execuções e aliases do NAS."""

    __tablename__ = "op_import_sources"

    source_key: Mapped[str] = mapped_column(String(1024), primary_key=True)
    source_group: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    source_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_modified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    state: Mapped[str] = mapped_column(String(40), nullable=False, default="BASELINED", index=True)
    op_number: Mapped[str] = mapped_column(String(80), nullable=False, default="", index=True)
    op_id: Mapped[int | None] = mapped_column(ForeignKey("ops.id", ondelete="SET NULL"), nullable=True, index=True)
    error: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)


class AppRunLockModel(Base):
    """Lease curto compartilhado para impedir duas estações integradoras simultâneas."""

    __tablename__ = "app_run_locks"

    lock_key: Mapped[str] = mapped_column(String(160), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    lease_until: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
