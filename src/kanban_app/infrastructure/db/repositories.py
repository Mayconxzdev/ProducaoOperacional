from __future__ import annotations

import json
import time
import unicodedata
from enum import Enum
from functools import wraps
from datetime import date, datetime
from typing import Iterable
from uuid import uuid4

from sqlalchemy import Select, and_, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from kanban_app.application.application_errors import OptimisticConflictError
from kanban_app.application.dto import CheckEntryDTO, DeadlineAlertDTO, HistoryEntryDTO, OpDetailDTO, OpFormDTO, OpListDTO, SectorDTO
from kanban_app.domain.enums import CheckState, OpStatus, coerce_check_state, coerce_op_status
from kanban_app.domain.option_lists import CHECK_FIELD_KEYS
from kanban_app.infrastructure.db.models import AppSettingModel, CheckEntryModel, DeadlineAlertSendModel, OpHistoryModel, OpModel, SectorModel, utc_now
from kanban_app.infrastructure.db.session import Database
from kanban_app.formatting import normalize_voltage_value


def _retry_if_database_busy(fn):
    """Repete a transação inteira quando o SQLite/NAS está temporariamente ocupado."""

    @wraps(fn)
    def wrapped(*args, **kwargs):
        delays = (0.0, 0.20, 0.50, 1.00)
        last_error = None
        for attempt, delay in enumerate(delays):
            if delay:
                time.sleep(delay)
            try:
                return fn(*args, **kwargs)
            except OperationalError as exc:
                message = str(exc).casefold()
                transient = any(
                    token in message
                    for token in (
                        "database is locked",
                        "database table is locked",
                        "database is busy",
                        "sqlite_busy",
                        "sqlite_locked",
                    )
                )
                if not transient or attempt == len(delays) - 1:
                    raise
                last_error = exc
        if last_error is not None:  # pragma: no cover - proteção defensiva
            raise last_error

    return wrapped


class ProductionRepository:
    def __init__(self, database: Database):
        self.database = database

    def read_shared_snapshot(
        self,
        setting_keys: Iterable[str],
        *,
        defaults: dict[str, object] | None = None,
    ) -> tuple[list[OpListDTO], dict[str, object], tuple[object, ...]]:
        """Lê OPs e configurações em uma única transação curta e consistente."""
        requested = list(dict.fromkeys(str(key) for key in setting_keys))
        fallback = dict(defaults or {})
        with self.database.session() as session:
            rows = session.execute(self._active_query(order_by="entrega")).all()
            ops = [self._list_dto(op, sector) for op, sector in rows]

            settings = dict(fallback)
            if requested:
                setting_rows = session.execute(
                    select(AppSettingModel).where(AppSettingModel.setting_key.in_(requested))
                ).scalars()
                for row in setting_rows:
                    try:
                        settings[row.setting_key] = json.loads(row.setting_value)
                    except (json.JSONDecodeError, TypeError):
                        settings[row.setting_key] = row.setting_value

            op_stats = session.execute(
                select(
                    func.count(OpModel.id),
                    func.max(OpModel.updated_at),
                    func.coalesce(func.sum(OpModel.row_version), 0),
                )
            ).one()
            sector_stats = session.execute(
                select(func.count(SectorModel.id), func.max(SectorModel.updated_at))
            ).one()
            setting_stats = session.execute(
                select(
                    func.count(AppSettingModel.setting_key),
                    func.max(AppSettingModel.updated_at),
                    func.coalesce(func.sum(AppSettingModel.version), 0),
                )
            ).one()
            token = (*op_stats, *sector_stats, *setting_stats)
            return ops, settings, token

    def list_active_ops(self, *, order_by: str = "entrega") -> list[OpListDTO]:
        with self.database.session() as session:
            query = self._active_query(order_by=order_by)
            rows = session.execute(query).all()
            return [self._list_dto(op, sector) for op, sector in rows]

    def list_concluded_ops(self) -> list[OpListDTO]:
        with self.database.session() as session:
            rows = session.execute(
                select(OpModel, SectorModel)
                .outerjoin(SectorModel, OpModel.setor_id == SectorModel.id)
                .where(and_(OpModel.archived.is_(False), OpModel.status == OpStatus.CONCLUIDO.value))
                .order_by(OpModel.completed_at.desc(), OpModel.id.desc())
            ).all()
            return [self._list_dto(op, sector) for op, sector in rows]

    def list_archived_ops(self) -> list[OpListDTO]:
        with self.database.session() as session:
            rows = session.execute(
                select(OpModel, SectorModel)
                .outerjoin(SectorModel, OpModel.setor_id == SectorModel.id)
                .where(OpModel.archived.is_(True))
                .order_by(OpModel.archived_at.desc(), OpModel.id.desc())
            ).all()
            return [self._list_dto(op, sector) for op, sector in rows]

    def get_op(self, op_id: int) -> OpDetailDTO | None:
        with self.database.session() as session:
            row = session.execute(
                select(OpModel, SectorModel)
                .outerjoin(SectorModel, OpModel.setor_id == SectorModel.id)
                .where(OpModel.id == int(op_id))
            ).one_or_none()
            if row is None:
                return None
            op, sector = row
            checks = self._checks_for_op(session, op.id)
            return self._detail_dto(op, sector, checks)

    def find_by_number(self, numero_op: str, *, exclude_id: int | None = None) -> list[OpListDTO]:
        clean = str(numero_op or "").strip()
        if not clean:
            return []
        with self.database.session() as session:
            query = (
                select(OpModel, SectorModel)
                .outerjoin(SectorModel, OpModel.setor_id == SectorModel.id)
                .where(OpModel.numero_op == clean)
                .order_by(OpModel.updated_at.desc())
            )
            if exclude_id is not None:
                query = query.where(OpModel.id != int(exclude_id))
            return [self._list_dto(op, sector) for op, sector in session.execute(query).all()]

    @_retry_if_database_busy
    def create_op(self, form: OpFormDTO, *, station_id: str) -> OpDetailDTO:
        self._validate_form(form)
        now = utc_now()
        with self.database.write_session() as session:
            op = OpModel(**self._form_values(form), created_at=now, updated_at=now)
            if op.status == OpStatus.CONCLUIDO.value:
                op.completed_at = now
            session.add(op)
            session.flush()
            self._replace_check_entries(session, op.id, form.acompanhamento, station_id, now)
            self._history(session, op.id, "CRIADA", "", "", "", station_id, now)
            session.flush()
            return self._detail_from_session(session, op)

    @_retry_if_database_busy
    def update_op(self, op_id: int, form: OpFormDTO, *, expected_row_version: int, station_id: str) -> OpDetailDTO:
        self._validate_form(form)
        now = utc_now()
        with self.database.write_session() as session:
            op = self._load_for_write(session, op_id, expected_row_version)
            changed = False
            for field, value in self._form_values(form).items():
                if field == "status":
                    continue
                current = getattr(op, field)
                if current != value:
                    self._history(session, op.id, "EDITADA", field, self._history_value(current), self._history_value(value), station_id, now)
                    setattr(op, field, value)
                    changed = True
            status = self._coerce_status(form.status)
            if op.status != status.value:
                self._set_status(session, op, status, station_id, now)
                changed = True
            if self._replace_check_entries(session, op.id, form.acompanhamento, station_id, now):
                changed = True
            if changed:
                op.row_version += 1
                op.updated_at = now
            session.flush()
            return self._detail_from_session(session, op)

    @_retry_if_database_busy
    def complete_op(self, op_id: int, *, expected_row_version: int, station_id: str) -> OpDetailDTO:
        now = utc_now()
        with self.database.write_session() as session:
            op = self._load_for_write(session, op_id, expected_row_version)
            self._set_status(session, op, OpStatus.CONCLUIDO, station_id, now)
            op.row_version += 1
            op.updated_at = now
            return self._detail_from_session(session, op)

    @_retry_if_database_busy
    def reopen_op(self, op_id: int, *, status: OpStatus | str, expected_row_version: int, station_id: str) -> OpDetailDTO:
        normalized_status = self._coerce_status(status)
        if normalized_status == OpStatus.CONCLUIDO:
            raise ValueError("Escolha um status ativo para reabrir a OP.")
        now = utc_now()
        with self.database.write_session() as session:
            op = self._load_for_write(session, op_id, expected_row_version)
            if op.archived:
                raise ValueError("Restaure a OP arquivada antes de reabri-la.")
            previous = op.status
            op.status = normalized_status.value
            op.completed_at = None
            op.row_version += 1
            op.updated_at = now
            self._history(session, op.id, "REABERTA", "status", previous, normalized_status.value, station_id, now)
            return self._detail_from_session(session, op)

    @_retry_if_database_busy
    def archive_op(self, op_id: int, *, expected_row_version: int, station_id: str) -> OpDetailDTO:
        now = utc_now()
        with self.database.write_session() as session:
            op = self._load_for_write(session, op_id, expected_row_version)
            op.archived = True
            op.archived_at = now
            op.row_version += 1
            op.updated_at = now
            self._history(session, op.id, "ARQUIVADA", "", "", "", station_id, now)
            return self._detail_from_session(session, op)

    @_retry_if_database_busy
    def restore_op(self, op_id: int, *, expected_row_version: int, station_id: str) -> OpDetailDTO:
        now = utc_now()
        with self.database.write_session() as session:
            op = self._load_for_write(session, op_id, expected_row_version)
            op.archived = False
            op.archived_at = None
            op.row_version += 1
            op.updated_at = now
            self._history(session, op.id, "RESTAURADA", "", "", "", station_id, now)
            return self._detail_from_session(session, op)

    def history_for_op(self, op_id: int) -> list[HistoryEntryDTO]:
        with self.database.session() as session:
            rows = session.execute(select(OpHistoryModel).where(OpHistoryModel.op_id == int(op_id)).order_by(OpHistoryModel.occurred_at.desc(), OpHistoryModel.id.desc())).scalars()
            return [HistoryEntryDTO(id=row.id, op_id=row.op_id, event_type=row.event_type, field_name=row.field_name, old_value=row.old_value, new_value=row.new_value, station_id=row.station_id, occurred_at=row.occurred_at) for row in rows]

    def list_sectors(self, *, active_only: bool = False) -> list[SectorDTO]:
        with self.database.session() as session:
            query = select(SectorModel)
            if active_only:
                query = query.where(SectorModel.ativo.is_(True))
            rows = session.execute(query.order_by(SectorModel.ordem, SectorModel.nome)).scalars()
            return [SectorDTO(id=row.id, nome=row.nome, ordem=row.ordem, cor=row.cor, cor_texto=row.cor_texto, ativo=row.ativo) for row in rows]

    @_retry_if_database_busy
    def add_sector(self, nome: str, cor: str, *, station_id: str, cor_texto: str | None = None) -> SectorDTO:
        clean_name = str(nome or "").strip()
        if not clean_name:
            raise ValueError("Informe o nome do setor.")
        with self.database.write_session() as session:
            target_key = self._sector_key(clean_name)
            existing = next(
                (row for row in session.execute(select(SectorModel)).scalars() if self._sector_key(row.nome) == target_key),
                None,
            )
            if existing:
                raise ValueError("Já existe um setor com esse nome ou equivalente.")
            order = int(session.execute(select(SectorModel.ordem).order_by(SectorModel.ordem.desc())).scalar() or 0) + 1
            background = self._color_or_default(cor)
            sector = SectorModel(
                id=str(uuid4()),
                nome=clean_name,
                ordem=order,
                cor=background,
                cor_texto=self._color_or_default(cor_texto, default=self._contrast_text_color(background)),
                ativo=True,
            )
            session.add(sector)
            session.flush()
            return SectorDTO(id=sector.id, nome=sector.nome, ordem=sector.ordem, cor=sector.cor, cor_texto=sector.cor_texto, ativo=sector.ativo)

    @_retry_if_database_busy
    def update_sector(
        self,
        sector_id: str,
        *,
        nome: str,
        cor: str,
        ativo: bool,
        ordem: int,
        station_id: str,
        cor_texto: str | None = None,
    ) -> SectorDTO:
        with self.database.write_session() as session:
            sector = session.get(SectorModel, sector_id)
            if not sector:
                raise ValueError("Setor não encontrado.")
            clean_name = str(nome or "").strip()
            if not clean_name:
                raise ValueError("Informe o nome do setor.")
            target_key = self._sector_key(clean_name)
            duplicate = next(
                (row for row in session.execute(select(SectorModel)).scalars() if row.id != sector.id and self._sector_key(row.nome) == target_key),
                None,
            )
            if duplicate:
                raise ValueError("Já existe um setor com esse nome ou equivalente.")
            sector.nome = clean_name
            sector.cor = self._color_or_default(cor)
            sector.cor_texto = self._color_or_default(
                cor_texto,
                default=sector.cor_texto or self._contrast_text_color(sector.cor),
            )
            sector.ativo = bool(ativo)
            self._reorder_sector(session, sector.id, max(1, int(ordem)))
            session.flush()
            return SectorDTO(id=sector.id, nome=sector.nome, ordem=sector.ordem, cor=sector.cor, cor_texto=sector.cor_texto, ativo=sector.ativo)

    @_retry_if_database_busy
    def delete_sector_with_migration(self, sector_id: str, destination_sector_id: str, *, station_id: str) -> None:
        if sector_id == destination_sector_id:
            raise ValueError("Escolha outro setor de destino.")
        with self.database.write_session() as session:
            source = session.get(SectorModel, sector_id)
            destination = session.get(SectorModel, destination_sector_id)
            if not source or not destination or not destination.ativo:
                raise ValueError("Setor de origem ou destino inválido.")
            affected = session.execute(select(OpModel).where(OpModel.setor_id == source.id)).scalars().all()
            now = utc_now()
            for op in affected:
                op.setor_id = destination.id
                op.row_version += 1
                op.updated_at = now
                self._history(session, op.id, "SETOR_MIGRADO", "setor", source.nome, destination.nome, station_id, now)
            session.delete(source)
            session.flush()
            self._compact_sector_orders(session)

    @staticmethod
    def _compact_sector_orders(session: Session) -> None:
        sectors = list(session.execute(select(SectorModel).order_by(SectorModel.ordem, SectorModel.nome)).scalars())
        for position, sector in enumerate(sectors, start=1):
            sector.ordem = position

    @staticmethod
    def _reorder_sector(session: Session, sector_id: str, desired_order: int) -> None:
        sectors = list(session.execute(select(SectorModel).order_by(SectorModel.ordem, SectorModel.nome)).scalars())
        moved = next((sector for sector in sectors if sector.id == sector_id), None)
        if moved is None:
            return
        sectors.remove(moved)
        insert_at = max(0, min(len(sectors), int(desired_order) - 1))
        sectors.insert(insert_at, moved)
        for position, sector in enumerate(sectors, start=1):
            sector.ordem = position

    def recent_voltages(self) -> list[str]:
        with self.database.session() as session:
            values = session.execute(select(OpModel.voltagem).where(OpModel.voltagem != "").distinct().order_by(OpModel.voltagem)).scalars()
            return [str(value) for value in values]

    def get_setting(self, key: str, default=None):
        return self.get_settings((key,), defaults={key: default})[key]

    def get_settings(self, keys: Iterable[str], *, defaults: dict[str, object] | None = None) -> dict[str, object]:
        """Lê um conjunto de configurações em um único snapshot do banco.

        A leitura anterior abria uma sessão para cada campo da TV. Durante uma
        alteração feita por outro PC era possível combinar valores antigos e
        novos na mesma atualização. Um único snapshot evita esse estado parcial.
        """
        ordered_keys = list(dict.fromkeys(str(key) for key in keys))
        fallback = dict(defaults or {})
        if not ordered_keys:
            return {}
        with self.database.session() as session:
            rows = session.execute(select(AppSettingModel).where(AppSettingModel.setting_key.in_(ordered_keys))).scalars().all()
            by_key = {row.setting_key: row for row in rows}
            result: dict[str, object] = {}
            for key in ordered_keys:
                row = by_key.get(key)
                if row is None:
                    result[key] = fallback.get(key)
                    continue
                try:
                    result[key] = json.loads(row.setting_value)
                except (json.JSONDecodeError, TypeError):
                    result[key] = row.setting_value
            return result

    def set_setting(self, key: str, value, *, station_id: str) -> None:
        self.set_settings({key: value}, station_id=station_id)

    @_retry_if_database_busy
    def set_settings(self, values: dict[str, object], *, station_id: str) -> None:
        """Salva um grupo de preferências de forma atômica e compartilhada."""
        if not values:
            return
        now = utc_now()
        with self.database.write_session() as session:
            keys = list(values)
            rows = session.execute(select(AppSettingModel).where(AppSettingModel.setting_key.in_(keys))).scalars().all()
            by_key = {row.setting_key: row for row in rows}
            for key, value in values.items():
                serialized = json.dumps(self._json_compatible(value), ensure_ascii=False)
                row = by_key.get(key)
                if row is None:
                    session.add(
                        AppSettingModel(
                            setting_key=key,
                            setting_value=serialized,
                            version=1,
                            updated_station_id=station_id,
                            updated_at=now,
                        )
                    )
                else:
                    row.setting_value = serialized
                    row.version += 1
                    row.updated_station_id = station_id
                    row.updated_at = now

    @_retry_if_database_busy
    def claim_deadline_alerts(self, alerts: list[DeadlineAlertDTO]) -> list[int]:
        claimed: list[int] = []
        with self.database.write_session() as session:
            for alert in alerts:
                existing = session.execute(
                    select(DeadlineAlertSendModel).where(
                        and_(
                            DeadlineAlertSendModel.op_id == alert.op.id,
                            DeadlineAlertSendModel.milestone_date == alert.op.data_entrega,
                            DeadlineAlertSendModel.milestone_days == alert.milestone_days,
                        )
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    continue
                record = DeadlineAlertSendModel(
                    op_id=alert.op.id,
                    milestone_date=alert.op.data_entrega,
                    milestone_days=alert.milestone_days,
                    status="PENDING",
                    sent_at=utc_now(),
                )
                session.add(record)
                session.flush()
                claimed.append(record.id)
        return claimed

    @_retry_if_database_busy
    def mark_deadline_alerts(self, record_ids: list[int], *, success: bool, error: str = "") -> None:
        if not record_ids:
            return
        with self.database.write_session() as session:
            rows = session.execute(select(DeadlineAlertSendModel).where(DeadlineAlertSendModel.id.in_(record_ids))).scalars()
            for row in rows:
                row.status = "SENT" if success else "FAILED"
                row.error = str(error or "")
                row.sent_at = utc_now()

    def _active_query(self, *, order_by: str) -> Select:
        query = select(OpModel, SectorModel).outerjoin(SectorModel, OpModel.setor_id == SectorModel.id).where(and_(OpModel.archived.is_(False), OpModel.status != OpStatus.CONCLUIDO.value))
        if order_by == "op":
            return query.order_by(OpModel.numero_op, OpModel.id)
        if order_by == "setor":
            return query.order_by(SectorModel.ordem, OpModel.data_entrega.is_(None), OpModel.data_entrega, OpModel.id)
        if order_by == "status":
            return query.order_by(OpModel.status, OpModel.data_entrega.is_(None), OpModel.data_entrega, OpModel.id)
        return query.order_by(OpModel.data_entrega.is_(None), OpModel.data_entrega, OpModel.id)

    @staticmethod
    def _list_dto(op: OpModel, sector: SectorModel | None) -> OpListDTO:
        return OpListDTO(
            id=op.id,
            numero_op=op.numero_op,
            cliente=op.cliente,
            modelo=op.modelo,
            quantidade=op.quantidade,
            voltagem=op.voltagem,
            data_inicio=op.data_inicio,
            data_entrega=op.data_entrega,
            setor_id=op.setor_id,
            setor_nome=sector.nome if sector else "",
            setor_cor=sector.cor if sector else "#475569",
            setor_cor_texto=sector.cor_texto if sector else "#ffffff",
            status=coerce_op_status(op.status),
            pendencia=op.pendencia,
            row_version=op.row_version,
            updated_at=op.updated_at,
        )

    def _detail_from_session(self, session: Session, op: OpModel) -> OpDetailDTO:
        sector = session.get(SectorModel, op.setor_id) if op.setor_id else None
        return self._detail_dto(op, sector, self._checks_for_op(session, op.id))

    def _detail_dto(self, op: OpModel, sector: SectorModel | None, checks: tuple[CheckEntryDTO, ...]) -> OpDetailDTO:
        base = self._list_dto(op, sector)
        return OpDetailDTO(
            id=base.id,
            numero_op=base.numero_op,
            cliente=base.cliente,
            modelo=base.modelo,
            quantidade=base.quantidade,
            voltagem=base.voltagem,
            data_inicio=base.data_inicio,
            data_entrega=base.data_entrega,
            setor_id=base.setor_id,
            setor_nome=base.setor_nome,
            setor_cor=base.setor_cor,
            setor_cor_texto=base.setor_cor_texto,
            status=base.status,
            pendencia=base.pendencia,
            row_version=base.row_version,
            updated_at=base.updated_at,
            completed_at=op.completed_at,
            archived=op.archived,
            archived_at=op.archived_at,
            acompanhamento=checks,
        )

    @staticmethod
    def _checks_for_op(session: Session, op_id: int) -> tuple[CheckEntryDTO, ...]:
        values = {row.field_key: row for row in session.execute(select(CheckEntryModel).where(CheckEntryModel.op_id == op_id)).scalars()}
        return tuple(CheckEntryDTO(field_key=key, state=coerce_check_state(values[key].state), updated_at=values[key].updated_at, station_id=values[key].station_id) if key in values else CheckEntryDTO(field_key=key) for key in CHECK_FIELD_KEYS)

    @staticmethod
    def _history(session: Session, op_id: int, event_type: str, field_name: str, old_value: str, new_value: str, station_id: str, now: datetime) -> None:
        session.add(OpHistoryModel(op_id=op_id, event_type=event_type, field_name=field_name, old_value=old_value, new_value=new_value, station_id=station_id, occurred_at=now))


    def _replace_check_entries(self, session: Session, op_id: int, entries: Iterable[CheckEntryDTO], station_id: str, now: datetime) -> bool:
        provided = {entry.field_key: entry.state for entry in entries if entry.field_key in CHECK_FIELD_KEYS}
        changed = False
        existing = {row.field_key: row for row in session.execute(select(CheckEntryModel).where(CheckEntryModel.op_id == op_id)).scalars()}
        for key in CHECK_FIELD_KEYS:
            new_state = provided.get(key, existing.get(key).state if key in existing else CheckState.NAO_INFORMADO)
            new_value = self._coerce_check_state(new_state).value
            row = existing.get(key)
            if row is None:
                if new_value != CheckState.NAO_INFORMADO.value:
                    session.add(CheckEntryModel(op_id=op_id, field_key=key, state=new_value, station_id=station_id, updated_at=now))
                    self._history(session, op_id, "ACOMPANHAMENTO", key, CheckState.NAO_INFORMADO.value, new_value, station_id, now)
                    changed = True
            elif row.state != new_value:
                self._history(session, op_id, "ACOMPANHAMENTO", key, row.state, new_value, station_id, now)
                row.state, row.station_id, row.updated_at = new_value, station_id, now
                changed = True
        return changed

    @classmethod
    def _form_values(cls, form: OpFormDTO) -> dict[str, object]:
        return {
            "numero_op": str(form.numero_op or "").strip(),
            "cliente": str(form.cliente or "").strip(),
            "modelo": str(form.modelo or "").strip(),
            "quantidade": form.quantidade,
            "voltagem": normalize_voltage_value(form.voltagem),
            "data_inicio": form.data_inicio,
            "data_entrega": form.data_entrega,
            "setor_id": form.setor_id or None,
            "status": cls._coerce_status(form.status).value,
            "pendencia": str(form.pendencia or "").strip(),
        }

    @staticmethod
    def _coerce_status(value: OpStatus | str) -> OpStatus:
        return coerce_op_status(value)

    @staticmethod
    def _coerce_check_state(value: CheckState | str) -> CheckState:
        return coerce_check_state(value)

    def _validate_form(self, form: OpFormDTO) -> None:
        number = str(form.numero_op or "").strip()
        if number and not number.isdigit():
            raise ValueError("Número da OP deve conter apenas dígitos.")
        if form.quantidade is not None and int(form.quantidade) <= 0:
            raise ValueError("Quantidade deve ser um número inteiro positivo.")
        if form.setor_id:
            with self.database.session() as session:
                sector = session.get(SectorModel, form.setor_id)
                if sector is None:
                    raise ValueError("O setor informado não está cadastrado.")

    @staticmethod
    def _load_for_write(session: Session, op_id: int, expected_row_version: int) -> OpModel:
        op = session.get(OpModel, int(op_id))
        if op is None:
            raise ValueError("OP não encontrada.")
        if op.row_version != int(expected_row_version):
            raise OptimisticConflictError("Esta OP foi alterada em outra estação. Recarregue os dados antes de salvar.")
        return op

    def _set_status(self, session: Session, op: OpModel, status: OpStatus | str, station_id: str, now: datetime) -> None:
        normalized_status = self._coerce_status(status)
        old = op.status
        if old == normalized_status.value:
            return
        op.status = normalized_status.value
        op.completed_at = now if normalized_status == OpStatus.CONCLUIDO else None
        self._history(session, op.id, "STATUS", "status", old, normalized_status.value, station_id, now)

    @staticmethod
    def _history_value(value) -> str:
        if value is None:
            return ""
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        return str(value)

    @classmethod
    def _json_compatible(cls, value):
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        if isinstance(value, dict):
            return {str(key): cls._json_compatible(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [cls._json_compatible(item) for item in value]
        return value

    @staticmethod
    def _sector_key(value: str) -> str:
        normalized = unicodedata.normalize("NFKD", str(value or "").casefold())
        return "".join(char for char in normalized if char.isalnum() and not unicodedata.combining(char))

    @staticmethod
    def _color_or_default(color: str | None, *, default: str = "#475569") -> str:
        value = str(color or "").strip()
        if len(value) == 7 and value.startswith("#"):
            return value.lower()
        return default

    @staticmethod
    def _contrast_text_color(background: str) -> str:
        value = str(background or "#475569").lstrip("#")
        try:
            red, green, blue = int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
        except (ValueError, IndexError):
            return "#ffffff"
        luminance = (red * 299 + green * 587 + blue * 114) / 1000
        return "#111827" if luminance > 150 else "#ffffff"
