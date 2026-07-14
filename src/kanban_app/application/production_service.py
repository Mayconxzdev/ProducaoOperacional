from __future__ import annotations

from dataclasses import replace
from datetime import date

from kanban_app.application.dto import OpDetailDTO, OpFormDTO, OpListDTO, SectorDTO
from kanban_app.domain.enums import OpStatus
from kanban_app.infrastructure.db.repositories import ProductionRepository


class ProductionService:
    def __init__(self, repository: ProductionRepository, *, station_id: str):
        self.repository = repository
        self.station_id = station_id

    def list_active(self, order_by: str = "entrega") -> list[OpListDTO]:
        return self.repository.list_active_ops(order_by=order_by)

    def form_defaults(self) -> OpFormDTO:
        active_sectors = self.repository.list_sectors(active_only=True)
        return OpFormDTO(data_inicio=date.today(), setor_id=active_sectors[0].id if active_sectors else None)

    def create(self, form: OpFormDTO) -> OpDetailDTO:
        return self.repository.create_op(form, station_id=self.station_id)

    def update(self, op_id: int, form: OpFormDTO, row_version: int) -> OpDetailDTO:
        return self.repository.update_op(op_id, form, expected_row_version=row_version, station_id=self.station_id)

    def complete(self, op_id: int, row_version: int) -> OpDetailDTO:
        return self.repository.complete_op(op_id, expected_row_version=row_version, station_id=self.station_id)

    def reopen(self, op_id: int, row_version: int, status: OpStatus) -> OpDetailDTO:
        return self.repository.reopen_op(op_id, status=status, expected_row_version=row_version, station_id=self.station_id)

    def archive(self, op_id: int, row_version: int) -> OpDetailDTO:
        return self.repository.archive_op(op_id, expected_row_version=row_version, station_id=self.station_id)

    def restore(self, op_id: int, row_version: int) -> OpDetailDTO:
        return self.repository.restore_op(op_id, expected_row_version=row_version, station_id=self.station_id)

    def get(self, op_id: int) -> OpDetailDTO | None:
        return self.repository.get_op(op_id)

    def duplicates(self, number: str, exclude_id: int | None = None) -> list[OpListDTO]:
        return self.repository.find_by_number(number, exclude_id=exclude_id)

    def sectors(self, active_only: bool = False) -> list[SectorDTO]:
        return self.repository.list_sectors(active_only=active_only)

    def default_sector_for_import(self, form: OpFormDTO) -> OpFormDTO:
        if form.setor_id:
            return form
        return replace(form, setor_id=self.form_defaults().setor_id)

    @staticmethod
    def deadline_band(
        op: OpListDTO,
        today: date | None = None,
        *,
        warning_days: int = 14,
        critical_days: int = 7,
        eligible_sector_ids: set[str] | None = None,
    ) -> str:
        if op.data_entrega is None:
            return "sector"
        if eligible_sector_ids is not None and op.setor_id not in eligible_sector_ids:
            return "sector"
        remaining = (op.data_entrega - (today or date.today())).days
        if remaining <= critical_days:
            return "critical"
        if remaining <= warning_days:
            return "warning"
        return "sector"
