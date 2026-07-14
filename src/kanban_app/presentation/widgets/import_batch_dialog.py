from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from kanban_app.application.dto import ImportPreviewDTO


class ImportBatchDialog(QDialog):
    edit_requested = Signal(int, object)
    confirm_all_requested = Signal(object)

    def __init__(self, previews: list[ImportPreviewDTO], parent=None):
        super().__init__(parent)
        self.previews = list(previews)
        self.setWindowTitle("Importar Ordens de Produção")
        self.resize(1240, 720)
        self.setMinimumSize(980, 580)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 16)
        root.setSpacing(12)

        heading = QHBoxLayout()
        title_block = QVBoxLayout()
        title = QLabel("Revisão da importação", self)
        title.setObjectName("dialogTitle")
        description = QLabel(
            "Os dados foram extraídos dos documentos. Revise os itens em amarelo ou vermelho antes de criar as OPs.",
            self,
        )
        description.setWordWrap(True)
        description.setObjectName("helpText")
        title_block.addWidget(title)
        title_block.addWidget(description)
        heading.addLayout(title_block, 1)
        self.summary_badge = QLabel(self)
        self.summary_badge.setObjectName("summaryBadge")
        self.summary_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.summary_badge.setMinimumWidth(260)
        heading.addWidget(self.summary_badge)
        root.addLayout(heading)

        panel = QFrame(self)
        panel.setObjectName("settingsPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(12, 12, 12, 12)
        panel_layout.setSpacing(10)

        self.table = QTableWidget(0, 8, panel)
        self.table.setHorizontalHeaderLabels(("Arquivo", "OP", "Cliente", "Modelo", "Qtd", "Voltagem", "Entrega", "Situação"))
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(lambda _index: self._edit_selected())
        self.table.currentCellChanged.connect(lambda *_args: self._update_details())
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        for column in (4, 5, 6):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        panel_layout.addWidget(self.table, 1)

        self.details = QFrame(panel)
        self.details.setObjectName("importDetails")
        details_layout = QVBoxLayout(self.details)
        details_layout.setContentsMargins(14, 12, 14, 12)
        self.details_title = QLabel("Selecione um documento", self.details)
        self.details_title.setObjectName("detailTitle")
        self.details_text = QLabel(self.details)
        self.details_text.setWordWrap(True)
        self.details_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        details_layout.addWidget(self.details_title)
        details_layout.addWidget(self.details_text)
        panel_layout.addWidget(self.details)
        root.addWidget(panel, 1)

        actions = QHBoxLayout()
        self.edit_button = QPushButton("Revisar OP selecionada", self)
        self.confirm_button = QPushButton(self)
        self.confirm_button.setObjectName("primaryButton")
        close = QPushButton("Fechar", self)
        self.edit_button.clicked.connect(self._edit_selected)
        self.confirm_button.clicked.connect(self._confirm_complete)
        close.clicked.connect(self.reject)
        actions.addWidget(self.edit_button)
        actions.addStretch(1)
        actions.addWidget(close)
        actions.addWidget(self.confirm_button)
        root.addLayout(actions)

        for preview in self.previews:
            self._append_preview(preview)
        if self.table.rowCount():
            self.table.selectRow(0)
        self._refresh_summary()
        self._update_details()

    def update_preview(self, row: int, preview: ImportPreviewDTO) -> None:
        if not 0 <= row < len(self.previews):
            return
        self.previews[row] = preview
        self._fill_row(row, preview)
        self.table.selectRow(row)
        self._refresh_summary()
        self._update_details()

    def complete_previews(self) -> list[ImportPreviewDTO]:
        return [preview for preview in self.previews if not preview.errors and not preview.missing_fields]

    def _append_preview(self, preview: ImportPreviewDTO) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setRowHeight(row, 46)
        self._fill_row(row, preview)

    def _fill_row(self, row: int, preview: ImportPreviewDTO) -> None:
        form = preview.form
        status = self._status_text(preview)
        values = (
            Path(preview.source_path).name,
            form.numero_op,
            form.cliente,
            form.modelo,
            "" if form.quantidade is None else str(form.quantidade),
            form.voltagem,
            form.data_entrega.strftime("%d/%m/%Y") if form.data_entrega else "",
            status,
        )
        background, foreground = self._status_colors(preview)
        for column, value in enumerate(values):
            item = self.table.item(row, column) or QTableWidgetItem()
            item.setText(value)
            item.setData(Qt.ItemDataRole.UserRole, preview if column == 0 else None)
            item.setToolTip(preview.source_path if column == 0 else status if column == 7 else value)
            if column == 7:
                item.setBackground(QColor(background))
                item.setForeground(QColor(foreground))
                font = item.font()
                font.setBold(True)
                item.setFont(font)
            self.table.setItem(row, column, item)

    def _refresh_summary(self) -> None:
        complete = len(self.complete_previews())
        review = sum(1 for preview in self.previews if preview.missing_fields and not preview.errors)
        errors = sum(1 for preview in self.previews if preview.errors)
        self.summary_badge.setText(f"{complete} completas  •  {review} revisar  •  {errors} erro(s)")
        self.confirm_button.setText(f"Criar {complete} OP(s) completa(s)")
        self.confirm_button.setEnabled(complete > 0)

    def _update_details(self) -> None:
        row = self.table.currentRow()
        enabled = 0 <= row < len(self.previews)
        self.edit_button.setEnabled(enabled)
        if not enabled:
            self.details_title.setText("Nenhum documento selecionado")
            self.details_text.setText("")
            return
        preview = self.previews[row]
        form = preview.form
        self.details_title.setText(Path(preview.source_path).name)
        if preview.errors:
            state = "Erro de leitura: " + "; ".join(preview.errors)
        elif preview.missing_fields:
            state = "Preencha antes de criar: " + ", ".join(preview.missing_fields)
        else:
            state = "Documento completo e pronto para criação."
        self.details_text.setText(
            f"{state}\n\n"
            f"OP: {form.numero_op or '—'}   |   Cliente: {form.cliente or '—'}   |   Modelo: {form.modelo or '—'}\n"
            f"Quantidade: {form.quantidade if form.quantidade is not None else '—'}   |   Voltagem: {form.voltagem or '—'}   |   "
            f"Entrega: {form.data_entrega.strftime('%d/%m/%Y') if form.data_entrega else '—'}\n"
            f"Arquivo: {preview.source_path}"
        )

    def _confirm_complete(self) -> None:
        complete = self.complete_previews()
        if complete:
            self.confirm_all_requested.emit(complete)

    @staticmethod
    def _status_text(preview: ImportPreviewDTO) -> str:
        if preview.errors:
            return "Erro de leitura"
        if preview.missing_fields:
            return "Revisar: " + ", ".join(preview.missing_fields)
        return "Pronta para criar"

    @staticmethod
    def _status_colors(preview: ImportPreviewDTO) -> tuple[str, str]:
        if preview.errors:
            return "#fee2e2", "#991b1b"
        if preview.missing_fields:
            return "#fef3c7", "#92400e"
        return "#dcfce7", "#166534"

    def _edit_selected(self) -> None:
        row = self.table.currentRow()
        if 0 <= row < len(self.previews):
            self.edit_requested.emit(row, self.previews[row])
