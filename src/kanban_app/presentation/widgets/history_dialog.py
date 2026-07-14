from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLineEdit, QPushButton, QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from kanban_app.application.dto import OpListDTO


class HistoryDialog(QDialog):
    open_requested = Signal(object)
    reopen_requested = Signal(object)
    restore_requested = Signal(object)
    changes_requested = Signal(object)

    def __init__(self, concluded: list[OpListDTO], archived: list[OpListDTO], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Histórico")
        self.resize(980, 560)
        self._concluded = concluded
        self._archived = archived
        self.search = QLineEdit(self)
        self.search.setPlaceholderText("Buscar por número da OP ou cliente")
        self.search.textChanged.connect(self._apply_search)
        self.tabs = QTabWidget(self)
        self.concluded_table = self._build_table()
        self.archived_table = self._build_table()
        self.tabs.addTab(self._tab(self.concluded_table, concluded=True), "Concluídas")
        self.tabs.addTab(self._tab(self.archived_table, concluded=False), "Arquivadas")
        layout = QVBoxLayout(self)
        layout.addWidget(self.search)
        layout.addWidget(self.tabs)
        self._render(self.concluded_table, self._concluded)
        self._render(self.archived_table, self._archived)

    def _tab(self, table: QTableWidget, *, concluded: bool) -> QWidget:
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.addWidget(table)
        actions = QHBoxLayout()
        open_button = QPushButton("Consultar OP", panel)
        changes_button = QPushButton("Histórico de alterações", panel)
        state_button = QPushButton("Reabrir OP" if concluded else "Restaurar OP", panel)
        open_button.clicked.connect(lambda: self._emit(table, self.open_requested))
        changes_button.clicked.connect(lambda: self._emit(table, self.changes_requested))
        state_button.clicked.connect(lambda: self._emit(table, self.reopen_requested if concluded else self.restore_requested))
        actions.addWidget(open_button)
        actions.addWidget(changes_button)
        actions.addStretch(1)
        actions.addWidget(state_button)
        layout.addLayout(actions)
        return panel

    @staticmethod
    def _build_table() -> QTableWidget:
        table = QTableWidget()
        table.setColumnCount(7)
        table.setHorizontalHeaderLabels(["OP", "Cliente", "Modelo", "Status", "Setor", "Entrega", "Data"])
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.horizontalHeader().setStretchLastSection(True)
        return table

    def _render(self, table: QTableWidget, items: list[OpListDTO]) -> None:
        table.setRowCount(0)
        for op in items:
            row = table.rowCount()
            table.insertRow(row)
            values = [op.numero_op, op.cliente, op.modelo, (op.status.value if hasattr(op.status, "value") else str(op.status)).replace("_", " ").title(), op.setor_nome, op.data_entrega.strftime("%d/%m/%Y") if op.data_entrega else "", op.updated_at.strftime("%d/%m/%Y %H:%M")]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(256, op)
                table.setItem(row, column, item)

    def _apply_search(self, value: str) -> None:
        needle = value.casefold().strip()
        for table in (self.concluded_table, self.archived_table):
            for row in range(table.rowCount()):
                op = table.item(row, 0).data(256)
                table.setRowHidden(row, bool(needle and needle not in op.numero_op.casefold() and needle not in op.cliente.casefold()))

    @staticmethod
    def _emit(table: QTableWidget, signal) -> None:
        row = table.currentRow()
        if row < 0:
            return
        op = table.item(row, 0).data(256)
        signal.emit(op)
