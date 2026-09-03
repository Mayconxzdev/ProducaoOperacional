from __future__ import annotations

import json
from datetime import date, datetime, time
from typing import Sequence

from PySide6.QtCore import QDate, QTime, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from kanban_app.application.dto import OpDetailDTO, OpListDTO, OpReminderDTO, OpReminderFormDTO
from kanban_app.infrastructure.db.repositories import ProductionRepository


class OpReminderDialog(QDialog):
    """Diálogo para configurar e agendar um lembrete visual de OP na TV."""

    DAY_NAMES = (
        ("monday", "Segunda"),
        ("tuesday", "Terça"),
        ("wednesday", "Quarta"),
        ("thursday", "Quinta"),
        ("friday", "Sexta"),
        ("saturday", "Sábado"),
        ("sunday", "Domingo"),
    )

    def __init__(
        self,
        parent: QWidget | None,
        *,
        repository: ProductionRepository,
        station_id: str,
        op: OpDetailDTO | OpListDTO | None = None,
        reminder: OpReminderDTO | None = None,
    ):
        super().__init__(parent)
        self.repository = repository
        self.station_id = station_id
        self.op = op
        self.reminder = reminder
        self.saved_reminder: OpReminderDTO | None = None

        title = "Editar Lembrete na TV" if reminder else "⏰ Agendar Lembrete na TV"
        self.setWindowTitle(title)
        self.setMinimumWidth(540)
        self._build_ui()
        self._populate_data()
        self._check_conflict()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Cabeçalho da OP
        header_card = QFrame(self)
        header_card.setObjectName("opHeaderCard")
        header_card.setStyleSheet(
            "QFrame#opHeaderCard { background: #1e293b; border-radius: 6px; padding: 10px; }"
        )
        h_layout = QVBoxLayout(header_card)
        h_layout.setContentsMargins(6, 6, 6, 6)

        op_num = self.op.numero_op if self.op else (self.reminder.numero_op if self.reminder else "")
        cliente = self.op.cliente if self.op else (self.reminder.cliente if self.reminder else "")
        modelo = self.op.modelo if self.op else (self.reminder.modelo if self.reminder else "")

        title_text = f"OP {op_num}" if op_num else "Lembrete Geral da Produção"
        op_title = QLabel(title_text, header_card)
        op_title.setStyleSheet("color: #38bdf8; font-size: 13pt; font-weight: bold;")
        h_layout.addWidget(op_title)

        if cliente or modelo:
            info_label = QLabel(f"Cliente: {cliente or '-'}  |  Modelo: {modelo or '-'}", header_card)
            info_label.setStyleSheet("color: #cbd5e1; font-size: 10pt;")
            h_layout.addWidget(info_label)

        layout.addWidget(header_card)

        # Formulário principal
        form = QFormLayout()
        form.setSpacing(10)

        # Mensagem do lembrete
        self.message_edit = QPlainTextEdit(self)
        self.message_edit.setPlaceholderText("Digite o aviso ou pendência a ser exibida em destaque na TV...")
        self.message_edit.setMaximumHeight(85)
        form.addRow("Mensagem do lembrete *:", self.message_edit)

        # Horário
        self.time_edit = QTimeEdit(self)
        self.time_edit.setDisplayFormat("HH:mm")
        self.time_edit.setTime(QTime.currentTime().addSecs(120))  # Padrão: 2 min a frente
        self.time_edit.timeChanged.connect(self._check_conflict)
        form.addRow("Horário de exibição *:", self.time_edit)

        # Duração na tela
        dur_box = QHBoxLayout()
        self.duration_spin = QSpinBox(self)
        self.duration_spin.setRange(5, 600)
        self.duration_spin.setValue(30)
        self.duration_spin.setSuffix(" segundos")
        self.duration_spin.valueChanged.connect(self._check_conflict)
        dur_box.addWidget(self.duration_spin)

        btn_15 = QPushButton("15s", self)
        btn_30 = QPushButton("30s", self)
        btn_60 = QPushButton("1 min", self)
        btn_15.clicked.connect(lambda: self.duration_spin.setValue(15))
        btn_30.clicked.connect(lambda: self.duration_spin.setValue(30))
        btn_60.clicked.connect(lambda: self.duration_spin.setValue(60))
        dur_box.addWidget(btn_15)
        dur_box.addWidget(btn_30)
        dur_box.addWidget(btn_60)
        form.addRow("Tempo na tela da TV:", dur_box)

        # Recorrência / Frequência
        self.recurrence_combo = QComboBox(self)
        self.recurrence_combo.addItem("Apenas uma vez (na data abaixo)", "ONCE")
        self.recurrence_combo.addItem("Todos os dias", "DAILY")
        self.recurrence_combo.addItem("Dias úteis (Segunda a Sexta)", "WEEKDAYS")
        self.recurrence_combo.addItem("Personalizar dias da semana", "CUSTOM")
        self.recurrence_combo.currentIndexChanged.connect(self._on_recurrence_changed)
        form.addRow("Frequência:", self.recurrence_combo)

        # Data única
        self.date_edit = QDateEdit(self)
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setDisplayFormat("dd/MM/yyyy")
        self.date_edit.dateChanged.connect(self._check_conflict)
        self.date_row = form.addRow("Data de exibição:", self.date_edit)

        # Caixa com checkboxes dos dias da semana (para CUSTOM)
        self.days_group = QGroupBox("Selecione os dias da semana:", self)
        days_layout = QHBoxLayout(self.days_group)
        self.day_checkboxes: dict[str, QCheckBox] = {}
        for key, name in self.DAY_NAMES:
            cb = QCheckBox(name, self.days_group)
            cb.stateChanged.connect(self._check_conflict)
            self.day_checkboxes[key] = cb
            days_layout.addWidget(cb)
        self.days_group.setVisible(False)
        form.addRow("", self.days_group)

        layout.addLayout(form)

        # Painel de conflito e recomendação
        self.conflict_frame = QFrame(self)
        self.conflict_frame.setObjectName("conflictFrame")
        self.conflict_frame.setStyleSheet(
            "QFrame#conflictFrame { background: #3b2a1a; border: 1px solid #d97706; border-radius: 6px; padding: 8px; }"
        )
        c_layout = QVBoxLayout(self.conflict_frame)
        c_layout.setContentsMargins(8, 8, 8, 8)
        self.conflict_label = QLabel("", self.conflict_frame)
        self.conflict_label.setStyleSheet("color: #fef08a; font-weight: bold;")
        self.conflict_label.setWordWrap(True)
        c_layout.addWidget(self.conflict_label)

        self.btn_recommend = QPushButton("💡 Usar horário livre sugerido", self.conflict_frame)
        self.btn_recommend.setStyleSheet(
            "background: #d97706; color: white; font-weight: bold; border-radius: 4px; padding: 6px 12px;"
        )
        self.btn_recommend.clicked.connect(self._apply_recommended_time)
        c_layout.addWidget(self.btn_recommend, 0, Qt.AlignmentFlag.AlignLeft)
        self.conflict_frame.setVisible(False)
        layout.addWidget(self.conflict_frame)

        # Indicador de horário livre
        self.available_label = QLabel("✓ Horário livre disponível para exibição na TV", self)
        self.available_label.setStyleSheet("color: #22c55e; font-weight: bold;")
        layout.addWidget(self.available_label)

        # Botões de ação
        actions = QHBoxLayout()
        actions.addStretch(1)
        self.btn_cancel = QPushButton("Cancelar", self)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_save = QPushButton("Salvar Lembrete", self)
        self.btn_save.setObjectName("primaryButton")
        self.btn_save.clicked.connect(self._save)
        actions.addWidget(self.btn_cancel)
        actions.addWidget(self.btn_save)
        layout.addLayout(actions)

    def _populate_data(self) -> None:
        if self.reminder:
            self.message_edit.setPlainText(self.reminder.mensagem)
            t_parts = self.reminder.horario.split(":")
            if len(t_parts) >= 2:
                self.time_edit.setTime(QTime(int(t_parts[0]), int(t_parts[1])))
            self.duration_spin.setValue(self.reminder.duracao_segundos)

            idx = self.recurrence_combo.findData(self.reminder.tipo_recorrencia)
            if idx >= 0:
                self.recurrence_combo.setCurrentIndex(idx)

            if self.reminder.data_inicio:
                self.date_edit.setDate(QDate(self.reminder.data_inicio.year, self.reminder.data_inicio.month, self.reminder.data_inicio.day))

            for key in self.reminder.dias_semana:
                if key in self.day_checkboxes:
                    self.day_checkboxes[key].setChecked(True)
        elif self.op:
            pendencia = getattr(self.op, "pendencia", "")
            if pendencia:
                self.message_edit.setPlainText(pendencia)

        self._on_recurrence_changed()

    def _on_recurrence_changed(self) -> None:
        mode = self.recurrence_combo.currentData()
        self.date_edit.setEnabled(mode == "ONCE")
        self.days_group.setVisible(mode == "CUSTOM")
        self._check_conflict()

    def _selected_days(self) -> list[str]:
        mode = self.recurrence_combo.currentData()
        if mode == "DAILY":
            return [k for k, _ in self.DAY_NAMES]
        if mode == "WEEKDAYS":
            return ["monday", "tuesday", "wednesday", "thursday", "friday"]
        if mode == "CUSTOM":
            return [k for k, cb in self.day_checkboxes.items() if cb.isChecked()]
        if mode == "ONCE":
            q_date = self.date_edit.date()
            py_date = date(q_date.year(), q_date.month(), q_date.day())
            day_idx = py_date.weekday()
            return [self.DAY_NAMES[day_idx][0]]
        return []

    def _check_conflict(self) -> None:
        horario = self.time_edit.time().toString("HH:mm")
        duracao = self.duration_spin.value()
        dias = self._selected_days()
        q_date = self.date_edit.date()
        target_date = date(q_date.year(), q_date.month(), q_date.day()) if self.recurrence_combo.currentData() == "ONCE" else None
        exclude_id = self.reminder.id if self.reminder else None

        conflict = self.repository.find_conflicting_reminder(
            horario, duracao, dias_semana=dias, data=target_date, exclude_id=exclude_id
        )
        if conflict:
            sugestao = self.repository.suggest_next_available_time(
                horario, duracao, dias_semana=dias, data=target_date
            )
            self._suggested_time = sugestao
            self.conflict_label.setText(
                f"⚠️ Atenção: Já existe outro lembrete ativo no horário {conflict.horario} "
                f"(OP {conflict.numero_op or 'Geral'} - {conflict.duracao_segundos}s)."
            )
            self.btn_recommend.setText(f"💡 Usar próximo horário livre: {sugestao}")
            self.conflict_frame.setVisible(True)
            self.available_label.setVisible(False)
        else:
            self._suggested_time = None
            self.conflict_frame.setVisible(False)
            self.available_label.setVisible(True)

    def _apply_recommended_time(self) -> None:
        if getattr(self, "_suggested_time", None):
            parts = self._suggested_time.split(":")
            if len(parts) >= 2:
                self.time_edit.setTime(QTime(int(parts[0]), int(parts[1])))

    def _save(self) -> None:
        mensagem = self.message_edit.toPlainText().strip()
        if not mensagem:
            QMessageBox.warning(self, "Mensagem obrigatória", "Digite a mensagem ou pendência a ser exibida na TV.")
            self.message_edit.setFocus()
            return

        horario = self.time_edit.time().toString("HH:mm")
        duracao = self.duration_spin.value()
        mode = self.recurrence_combo.currentData()
        dias = self._selected_days()

        if mode == "CUSTOM" and not dias:
            QMessageBox.warning(self, "Dias da semana", "Selecione ao menos um dia da semana para o lembrete personalizado.")
            return

        q_date = self.date_edit.date()
        data_inicio = date(q_date.year(), q_date.month(), q_date.day()) if mode == "ONCE" else date.today()

        op_id = self.op.id if self.op else (self.reminder.op_id if self.reminder else None)
        op_num = self.op.numero_op if self.op else (self.reminder.numero_op if self.reminder else "")
        cliente = self.op.cliente if self.op else (self.reminder.cliente if self.reminder else "")
        modelo = self.op.modelo if self.op else (self.reminder.modelo if self.reminder else "")

        form = OpReminderFormDTO(
            mensagem=mensagem,
            horario=horario,
            op_id=op_id,
            numero_op=op_num,
            cliente=cliente,
            modelo=modelo,
            data_inicio=data_inicio,
            duracao_segundos=duracao,
            tipo_recorrencia=mode,
            dias_semana=tuple(dias),
            ativo=True,
        )

        try:
            if self.reminder:
                self.saved_reminder = self.repository.update_reminder(
                    self.reminder.id, form, station_id=self.station_id
                )
            else:
                self.saved_reminder = self.repository.create_reminder(
                    form, station_id=self.station_id
                )
            self.accept()
        except Exception as exc:
            QMessageBox.critical(self, "Erro ao salvar", f"Não foi possível salvar o lembrete:\n{exc}")
