from __future__ import annotations

from datetime import date
from collections.abc import Mapping

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QBrush, QColor, QFont

from kanban_app.application.dto import OpListDTO
from kanban_app.application.production_service import ProductionService
from kanban_app.domain.enums import OpStatus
from kanban_app.presentation.tv_focus_formatting import (
    tv_focus_date_label,
    tv_focus_op_label,
    tv_focus_sector_label,
    tv_focus_status_label,
)


STATUS_LABELS = {
    "PRIORIDADE": "Prioridade",
    "EM_ATRASO": "Em atraso",
    "EM_DIA": "Em dia",
    "AGUARDANDO": "Aguardando",
    "CONCLUIDO": "Concluído",
}

_ALIGNMENT_FLAGS = {
    "left": Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
    "center": Qt.AlignmentFlag.AlignCenter,
    "right": Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
}


def _status_value(status: OpStatus | str) -> str:
    return status.value if isinstance(status, OpStatus) else str(status or "")


class OpListModel(QAbstractTableModel):
    COLUMNS: tuple[tuple[str, str], ...] = (
        ("op", "OP"),
        ("status", "Status"),
        ("cliente", "Cliente"),
        ("modelo", "Modelo"),
        ("voltagem", "Voltagem"),
        ("quantidade", "Qtd"),
        ("inicio", "Início"),
        ("entrega", "Entrega"),
        ("setor", "Setor"),
        ("pendencia", "Pendência"),
    )
    SORTABLE = {"op", "status", "entrega", "setor"}

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ops: list[OpListDTO] = []
        self._sort_key = "entrega"
        self._sort_descending = False
        self._warning_color = "#f9a8d4"
        self._critical_color = "#ef4444"
        self._warning_days = 14
        self._critical_days = 7
        self._eligible_sector_ids: set[str] | None = None
        self._header_labels: dict[str, str] = {}
        self._column_alignments: dict[str, str] = {}
        self._column_formats: dict[str, str] = {}
        self._sector_labels: dict[str, str] = {}
        self._status_labels: dict[str, str] = dict(STATUS_LABELS)
        self._tv_mode = False
        self._tv_bold_all = False
        self._color_mode = "deadline"
        self._column_font_scales: dict[str, int] = {key: 100 for key, _label in self.COLUMNS}
        self._item_font = QFont()
        self._item_font.setPointSize(10)
        self._header_font = QFont()
        self._header_font.setPointSize(10)
        self._header_font.setBold(True)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._ops)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.COLUMNS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):
        if orientation == Qt.Horizontal and 0 <= section < len(self.COLUMNS):
            key, label = self.COLUMNS[section]
            if role == Qt.DisplayRole:
                return self._header_labels.get(key, label)
            if role == Qt.FontRole:
                return self._header_font
            if role == Qt.TextAlignmentRole:
                return int(self._alignment_flag(key, header=True))
        return super().headerData(section, orientation, role)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._ops)):
            return None
        op = self._ops[index.row()]
        key = self.COLUMNS[index.column()][0]
        if role == Qt.DisplayRole:
            return self._display_value(op, key)
        if role == Qt.ToolTipRole:
            return self._tooltip_value(op, key)
        if role == Qt.BackgroundRole:
            return QBrush(QColor(self._background_color(op)))
        if role == Qt.ForegroundRole:
            return QBrush(QColor(self._foreground_color(op)))
        if role == Qt.FontRole:
            font = QFont(self._item_font)
            scale = max(35, min(250, int(self._column_font_scales.get(key, 100)))) / 100
            font.setPointSize(max(7, round(self._item_font.pointSize() * scale)))
            font.setBold(self._tv_bold_all or (not self._tv_mode and key in {"op", "status"}))
            return font
        if role == Qt.TextAlignmentRole:
            return int(self._alignment_flag(key))
        if role == Qt.UserRole:
            return op
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        return Qt.ItemIsEnabled if index.isValid() else Qt.NoItemFlags

    def set_ops(self, ops: list[OpListDTO]) -> None:
        self.beginResetModel()
        self._ops = list(ops)
        self._sort_in_place()
        self.endResetModel()

    def set_colors(self, warning: str, critical: str) -> None:
        self._warning_color, self._critical_color = warning, critical
        self._emit_color_change()

    def set_deadline_rules(
        self,
        *,
        warning_days: int,
        critical_days: int,
        eligible_sector_ids: set[str] | None,
    ) -> None:
        self._warning_days = max(1, int(warning_days))
        self._critical_days = max(0, min(self._warning_days, int(critical_days)))
        self._eligible_sector_ids = None if eligible_sector_ids is None else set(eligible_sector_ids)
        self._emit_color_change()

    def set_presentation(
        self,
        *,
        item_point_size: int,
        header_labels: Mapping[str, str] | None = None,
        header_point_size: int | None = None,
        tv_mode: bool = False,
        tv_bold_all: bool = False,
        column_font_scales: Mapping[str, int] | None = None,
        column_alignments: Mapping[str, str] | None = None,
        column_formats: Mapping[str, str] | None = None,
        sector_labels: Mapping[str, str] | None = None,
        status_labels: Mapping[str, str] | None = None,
        color_mode: str = "deadline",
    ) -> None:
        self._item_font.setPointSize(max(7, int(item_point_size)))
        self._header_font.setPointSize(max(7, int(header_point_size or round(item_point_size * 0.92))))
        self._header_labels = {str(key): str(value) for key, value in (header_labels or {}).items()}
        self._tv_mode = bool(tv_mode)
        self._tv_bold_all = bool(tv_bold_all)
        self._column_font_scales = {
            key: max(35, min(250, int((column_font_scales or {}).get(key, 100))))
            for key, _label in self.COLUMNS
        }
        self._column_alignments = {
            key: str((column_alignments or {}).get(key, "center" if key not in {"cliente", "modelo", "pendencia"} else "left"))
            for key, _label in self.COLUMNS
        }
        self._column_formats = {str(key): str(value) for key, value in (column_formats or {}).items()}
        self._sector_labels = {str(key): str(value) for key, value in (sector_labels or {}).items()}
        self._status_labels = dict(STATUS_LABELS)
        self._status_labels.update({str(key): str(value) for key, value in (status_labels or {}).items()})
        self._color_mode = "sector" if str(color_mode).casefold() == "sector" else "deadline"
        self.headerDataChanged.emit(Qt.Horizontal, 0, len(self.COLUMNS) - 1)
        if self._ops:
            roles = [Qt.FontRole, Qt.DisplayRole, Qt.TextAlignmentRole, Qt.BackgroundRole, Qt.ForegroundRole]
            self.dataChanged.emit(self.index(0, 0), self.index(len(self._ops) - 1, len(self.COLUMNS) - 1), roles)

    def sort_by_column(self, column: int) -> None:
        if not 0 <= column < len(self.COLUMNS):
            return
        key = self.COLUMNS[column][0]
        if key not in self.SORTABLE:
            return
        self._sort_descending = not self._sort_descending if self._sort_key == key else False
        self._sort_key = key
        self.layoutAboutToBeChanged.emit()
        self._sort_in_place()
        self.layoutChanged.emit()

    def op_at(self, index: QModelIndex) -> OpListDTO | None:
        return self.data(index, Qt.UserRole) if index.isValid() else None

    def _sort_in_place(self) -> None:
        def delivery(op: OpListDTO):
            return (op.data_entrega is None, op.data_entrega or date.max, op.id)

        sorters = {
            "entrega": delivery,
            "op": lambda op: (op.numero_op == "", op.numero_op.zfill(20), op.id),
            "setor": lambda op: (op.setor_nome.casefold(), *delivery(op)),
            "status": lambda op: (STATUS_LABELS.get(_status_value(op.status), _status_value(op.status).replace("_", " ").title()), *delivery(op)),
        }
        self._ops.sort(key=sorters[self._sort_key], reverse=self._sort_descending)

    def _background_color(self, op: OpListDTO) -> str:
        if self._color_mode == "sector":
            return op.setor_cor or "#475569"
        # O status nunca define a cor. A base é sempre o setor e apenas as duas
        # faixas de prazo podem substituí-la.
        band = ProductionService.deadline_band(
            op,
            warning_days=self._warning_days,
            critical_days=self._critical_days,
            eligible_sector_ids=self._eligible_sector_ids,
        )
        if band == "critical":
            return self._critical_color
        if band == "warning":
            return self._warning_color
        return op.setor_cor or "#475569"


    def _foreground_color(self, op: OpListDTO) -> str:
        # Para a cor normal do setor, respeita exatamente a cor de texto escolhida
        # na Personalização. Nas faixas de prazo, calcula contraste sobre rosa ou
        # vermelho para manter a leitura segura.
        if self._color_mode == "sector":
            return op.setor_cor_texto or "#ffffff"
        band = ProductionService.deadline_band(
            op,
            warning_days=self._warning_days,
            critical_days=self._critical_days,
            eligible_sector_ids=self._eligible_sector_ids,
        )
        if band in {"critical", "warning"}:
            color = QColor(self._critical_color if band == "critical" else self._warning_color)
            return "#111827" if color.lightness() > 145 else "#ffffff"
        return op.setor_cor_texto or "#ffffff"

    def _display_value(self, op: OpListDTO, key: str) -> str:
        if self._tv_mode:
            values = {
                "op": tv_focus_op_label(op.numero_op),
                "status": tv_focus_status_label(op.status, self._status_labels),
                "cliente": op.cliente,
                "modelo": op.modelo,
                "voltagem": op.voltagem,
                "quantidade": "" if op.quantidade is None else str(op.quantidade),
                "inicio": tv_focus_date_label(op.data_inicio, self._column_formats.get("inicio", "dd/MM/yyyy")),
                "entrega": tv_focus_date_label(op.data_entrega, self._column_formats.get("entrega", "dd/MM/yyyy")),
                "setor": tv_focus_sector_label(op.setor_id, op.setor_nome, self._sector_labels),
                "pendencia": op.pendencia.replace("\n", " "),
            }
            return values[key]
        values = {
            "op": op.numero_op,
            "status": STATUS_LABELS.get(_status_value(op.status), _status_value(op.status).replace("_", " ").title()),
            "cliente": op.cliente,
            "modelo": op.modelo,
            "voltagem": op.voltagem,
            "quantidade": "" if op.quantidade is None else str(op.quantidade),
            "inicio": op.data_inicio.strftime("%d/%m/%Y") if op.data_inicio else "",
            "entrega": op.data_entrega.strftime("%d/%m/%Y") if op.data_entrega else "",
            "setor": op.setor_nome,
            "pendencia": op.pendencia.replace("\n", " "),
        }
        return values[key]

    def _tooltip_value(self, op: OpListDTO, key: str) -> str:
        values = {
            "op": op.numero_op,
            "status": STATUS_LABELS.get(_status_value(op.status), _status_value(op.status).replace("_", " ").title()),
            "cliente": op.cliente,
            "modelo": op.modelo,
            "voltagem": op.voltagem,
            "quantidade": "" if op.quantidade is None else str(op.quantidade),
            "inicio": op.data_inicio.strftime("%d/%m/%Y") if op.data_inicio else "",
            "entrega": op.data_entrega.strftime("%d/%m/%Y") if op.data_entrega else "",
            "setor": op.setor_nome,
            "pendencia": op.pendencia,
        }
        return values[key]

    def _alignment_flag(self, key: str, *, header: bool = False) -> Qt.AlignmentFlag:
        alignment = self._column_alignments.get(key)
        if alignment not in _ALIGNMENT_FLAGS:
            alignment = "left" if key in {"cliente", "modelo", "pendencia"} else "center"
        # Cabeçalhos herdam o alinhamento da coluna, o que torna a prévia igual
        # à TV real e deixa a personalização visualmente previsível.
        return _ALIGNMENT_FLAGS[alignment]

    def _emit_color_change(self) -> None:
        if self._ops:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(len(self._ops) - 1, len(self.COLUMNS) - 1),
                [Qt.BackgroundRole, Qt.ForegroundRole],
            )
