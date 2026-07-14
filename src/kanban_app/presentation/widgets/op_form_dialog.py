from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QCalendarWidget,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QFormLayout,
    QGroupBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QScrollArea,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from kanban_app.application.dto import CheckEntryDTO, OpDetailDTO, OpFormDTO, SectorDTO
from kanban_app.domain.enums import CheckState, OpStatus
from kanban_app.domain.option_lists import CHECK_GROUPS
from kanban_app.formatting import format_br_date, normalize_voltage_value, parse_br_date


STATUS_LABELS = {
    OpStatus.PRIORIDADE: "Prioridade",
    OpStatus.EM_ATRASO: "Em atraso",
    OpStatus.EM_DIA: "Em dia",
    OpStatus.AGUARDANDO: "Aguardando",
    OpStatus.CONCLUIDO: "Concluído",
}
CHECK_LABELS = {
    CheckState.NAO_INFORMADO: "Não informado",
    CheckState.SIM: "Sim",
    CheckState.NAO: "Não",
}


class FlexibleDateInput(QWidget):
    """Campo de data brasileiro que aceita digitação com ou sem barras."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(38)
        self.line_edit = QLineEdit(self)
        self.line_edit.setMinimumHeight(34)
        self.line_edit.setPlaceholderText("dd/mm/aaaa ou ddmmaaaa")
        self.line_edit.setMaxLength(10)
        self.line_edit.setToolTip(
            "Digite 13082026 ou 13/08/2026. Ao sair do campo, a data será normalizada para 13/08/2026."
        )
        self.calendar_button = QToolButton(self)
        self.calendar_button.setText("...")
        self.calendar_button.setToolTip("Abrir calendário")
        self.calendar_button.setFixedSize(38, 34)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self.line_edit, 1)
        layout.addWidget(self.calendar_button)
        self.line_edit.editingFinished.connect(self.normalize)
        self.calendar_button.clicked.connect(self._open_calendar)

    def set_date(self, value: date | None) -> None:
        self.line_edit.setText(format_br_date(value))
        self._set_invalid(False)

    def date_value(self) -> date | None:
        return parse_br_date(self.line_edit.text())

    def is_valid_or_empty(self) -> bool:
        text = self.line_edit.text().strip()
        return not text or self.date_value() is not None

    def normalize(self) -> None:
        text = self.line_edit.text().strip()
        if not text:
            self.line_edit.clear()
            self._set_invalid(False)
            return
        parsed = parse_br_date(text)
        if parsed is None:
            self._set_invalid(True)
            return
        self.line_edit.setText(format_br_date(parsed))
        self._set_invalid(False)

    def _set_invalid(self, invalid: bool) -> None:
        self.line_edit.setProperty("invalidDate", bool(invalid))
        self.line_edit.setStyleSheet("border: 1px solid #ef4444;" if invalid else "")
        self.line_edit.setToolTip(
            "Data inválida. Use dd/mm/aaaa ou ddmmaaaa."
            if invalid
            else "Digite 13082026 ou 13/08/2026. Ao sair do campo, a data será normalizada."
        )

    def _open_calendar(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Selecionar data")
        dialog.resize(360, 320)
        layout = QVBoxLayout(dialog)
        calendar = QCalendarWidget(dialog)
        current = self.date_value()
        if current:
            calendar.setSelectedDate(QDate(current.year, current.month, current.day))
        layout.addWidget(calendar, 1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Reset,
            parent=dialog,
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Usar data")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        buttons.button(QDialogButtonBox.StandardButton.Reset).setText("Limpar")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        buttons.button(QDialogButtonBox.StandardButton.Reset).clicked.connect(
            lambda: (self.set_date(None), dialog.reject())
        )
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected = calendar.selectedDate()
            self.set_date(date(selected.year(), selected.month(), selected.day()))



class OpFormDialog(QDialog):
    def __init__(
        self,
        *,
        sectors: list[SectorDTO],
        voltages: list[str],
        initial: OpDetailDTO | OpFormDTO | None = None,
        read_only: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Cadastrar OP" if initial is None else "Editar OP")
        self.resize(860, 720)
        self.setMinimumSize(720, 640)
        self._sectors = sectors
        self._read_only = read_only
        self._build_identity_tab(voltages)
        self._build_check_tab()
        self.tabs = QTabWidget(self)
        self.tabs.addTab(self._identity_tab, "Cadastro/Editar OP")
        self.tabs.addTab(self._check_tab, "Check Acompanhamento")
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Fechar" if read_only else "Cancelar", self)
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        if not read_only:
            save = QPushButton("Salvar OP", self)
            save.setObjectName("primaryButton")
            save.clicked.connect(self._validate_and_accept)
            buttons.addWidget(save)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 12)
        layout.addWidget(self.tabs)
        layout.addLayout(buttons)
        self._load(initial)
        if read_only:
            self._set_read_only()

    def _build_identity_tab(self, voltages: list[str]) -> None:
        self._identity_tab = QWidget(self)
        form = QFormLayout(self._identity_tab)
        form.setContentsMargins(18, 18, 18, 18)
        form.setSpacing(13)
        self.number_edit = QLineEdit(self)
        self.number_edit.setPlaceholderText("Somente dígitos quando informado")
        self.client_edit = QLineEdit(self)
        self.model_edit = QLineEdit(self)
        self.quantity_edit = QLineEdit(self)
        self.quantity_edit.setPlaceholderText("Número inteiro positivo")
        self.voltage_combo = QComboBox(self)
        self.voltage_combo.setEditable(True)
        self.voltage_combo.addItems([str(value) for value in voltages if str(value).strip()])
        self.start_date = self._date_edit()
        self.delivery_date = self._date_edit()
        self.sector_combo = QComboBox(self)
        self.sector_combo.addItem("", None)
        for sector in self._sectors:
            if sector.ativo:
                self.sector_combo.addItem(sector.nome, sector.id)
        self.status_combo = QComboBox(self)
        for status, label in STATUS_LABELS.items():
            self.status_combo.addItem(label, status)
        self.pending_edit = QPlainTextEdit(self)
        self.pending_edit.setPlaceholderText("Pendência interna, opcional")
        self.pending_edit.setFixedHeight(100)
        form.addRow("Número da OP", self.number_edit)
        form.addRow("Cliente", self.client_edit)
        form.addRow("Modelo", self.model_edit)
        form.addRow("Quantidade", self.quantity_edit)
        form.addRow("Voltagem", self.voltage_combo)
        form.addRow("Data de início", self.start_date)
        form.addRow("Prazo de entrega", self.delivery_date)
        form.addRow("Setor", self.sector_combo)
        form.addRow("Status", self.status_combo)
        form.addRow("Pendência", self.pending_edit)

    def _build_check_tab(self) -> None:
        self._check_tab = QWidget(self)
        layout = QVBoxLayout(self._check_tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        title = QLabel("Acompanhamento interno da OP", self._check_tab)
        title.setObjectName("detailTitle")
        layout.addWidget(title)

        note = QLabel(
            "Use ‘Não informado’ enquanto o item ainda não foi conferido. "
            "Este check não altera status, prazo, cores, TV/Foco ou alertas.",
            self._check_tab,
        )
        note.setObjectName("helpText")
        note.setWordWrap(True)
        layout.addWidget(note)

        self._check_scroll = QScrollArea(self._check_tab)
        self._check_scroll.setWidgetResizable(True)
        self._check_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._check_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget(self._check_scroll)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 4, 0)
        content_layout.setSpacing(10)

        self._check_inputs: dict[str, QComboBox] = {}
        self._check_groups: list[QGroupBox] = []
        state_tooltips = {
            CheckState.NAO_INFORMADO: "Ainda não conferido ou não preenchido.",
            CheckState.SIM: "Item conferido e disponível/concluído.",
            CheckState.NAO: "Item conferido e ainda não disponível/concluído.",
        }

        for group_name, fields in CHECK_GROUPS.items():
            group = QGroupBox(group_name, content)
            group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            grid = QGridLayout(group)
            grid.setContentsMargins(16, 18, 16, 14)
            grid.setHorizontalSpacing(14)
            grid.setVerticalSpacing(10)
            grid.setColumnStretch(1, 1)
            grid.setColumnStretch(3, 1)

            for index, field in enumerate(fields):
                row = index // 2
                pair = index % 2
                label_column = pair * 2
                input_column = label_column + 1

                label = QLabel(field, group)
                label.setWordWrap(True)
                label.setMinimumWidth(105)
                label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)

                key = f"{group_name}:{field}"
                combo = QComboBox(group)
                combo.setMinimumWidth(170)
                combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                combo.setAccessibleName(f"{group_name} - {field}")
                combo.setToolTip("Selecione Não informado, Sim ou Não.")
                for state, state_label in CHECK_LABELS.items():
                    combo.addItem(state_label, state)
                    item_index = combo.count() - 1
                    combo.setItemData(item_index, state_tooltips[state], Qt.ItemDataRole.ToolTipRole)

                self._check_inputs[key] = combo
                grid.addWidget(label, row, label_column)
                grid.addWidget(combo, row, input_column)

            self._check_groups.append(group)
            content_layout.addWidget(group)

        content_layout.addStretch(1)
        self._check_scroll.setWidget(content)
        layout.addWidget(self._check_scroll, 1)

    @staticmethod
    def _date_edit() -> FlexibleDateInput:
        return FlexibleDateInput()

    def _load(self, initial: OpDetailDTO | OpFormDTO | None) -> None:
        if initial is None:
            self._set_date(self.start_date, date.today())
            if self.sector_combo.count() > 1:
                self.sector_combo.setCurrentIndex(1)
            self._set_combo_data(self.status_combo, OpStatus.EM_DIA)
            return
        self.number_edit.setText(initial.numero_op)
        self.client_edit.setText(initial.cliente)
        self.model_edit.setText(initial.modelo)
        self.quantity_edit.setText("" if initial.quantidade is None else str(initial.quantidade))
        self.voltage_combo.setEditText(initial.voltagem)
        self._set_date(self.start_date, initial.data_inicio)
        self._set_date(self.delivery_date, initial.data_entrega)
        self._set_combo_data(self.sector_combo, initial.setor_id)
        self._set_combo_data(self.status_combo, initial.status)
        self.pending_edit.setPlainText(initial.pendencia)
        entries = {entry.field_key: entry for entry in getattr(initial, "acompanhamento", ())}
        for key, combo in self._check_inputs.items():
            self._set_combo_data(combo, entries.get(key, CheckEntryDTO(key)).state)

    def form_value(self) -> OpFormDTO:
        quantity_text = self.quantity_edit.text().strip()
        quantity = int(quantity_text) if quantity_text else None
        checks = tuple(CheckEntryDTO(field_key=key, state=self._enum_value(CheckState, combo.currentData())) for key, combo in self._check_inputs.items())
        return OpFormDTO(
            numero_op=self.number_edit.text().strip(),
            cliente=self.client_edit.text().strip(),
            modelo=self.model_edit.text().strip(),
            quantidade=quantity,
            voltagem=normalize_voltage_value(self.voltage_combo.currentText()),
            data_inicio=self._date_value(self.start_date),
            data_entrega=self._date_value(self.delivery_date),
            setor_id=self.sector_combo.currentData(),
            status=self._enum_value(OpStatus, self.status_combo.currentData()),
            pendencia=self.pending_edit.toPlainText().strip(),
            acompanhamento=checks,
        )

    def _validate_and_accept(self) -> None:
        number = self.number_edit.text().strip()
        if number and not number.isdigit():
            QMessageBox.warning(self, "Número da OP", "Quando informado, o Número da OP deve conter apenas dígitos.")
            return
        quantity = self.quantity_edit.text().strip()
        if quantity and (not quantity.isdigit() or int(quantity) <= 0):
            QMessageBox.warning(self, "Quantidade", "Quando informada, a quantidade deve ser um número inteiro positivo.")
            return
        for label, editor in (("Data de início", self.start_date), ("Prazo de entrega", self.delivery_date)):
            editor.normalize()
            if not editor.is_valid_or_empty():
                QMessageBox.warning(
                    self,
                    label,
                    f"{label} inválida. Digite, por exemplo, 13082026 ou 13/08/2026.",
                )
                editor.line_edit.setFocus()
                return
        self.accept()

    def _set_read_only(self) -> None:
        for widget in (self.number_edit, self.client_edit, self.model_edit, self.quantity_edit, self.voltage_combo, self.start_date, self.delivery_date, self.sector_combo, self.status_combo, self.pending_edit, *self._check_inputs.values()):
            widget.setEnabled(False)

    @staticmethod
    def _set_date(editor: FlexibleDateInput, value: date | None) -> None:
        editor.set_date(value)

    @staticmethod
    def _date_value(editor: FlexibleDateInput) -> date | None:
        return editor.date_value()

    @staticmethod
    def _set_combo_data(combo: QComboBox, data) -> None:
        index = combo.findData(data)
        if index >= 0:
            combo.setCurrentIndex(index)

    @staticmethod
    def _enum_value(enum_type, value):
        return value if isinstance(value, enum_type) else enum_type(str(value))
