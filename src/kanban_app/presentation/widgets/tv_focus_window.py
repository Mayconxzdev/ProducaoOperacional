from __future__ import annotations

from datetime import date
from math import ceil

from PySide6.QtCore import QTime, QTimer, Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QStackedLayout, QVBoxLayout, QWidget

from kanban_app.application.dto import OpListDTO, OpReminderDTO
from kanban_app.presentation.tv_settings import normalize_tv_settings
from kanban_app.presentation.widgets.op_list_view_widget import OpListViewWidget


class TvReminderOverlay(QWidget):
    """Card modal de destaque flutuante que aparece no centro da TV por cima da lista."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("tvReminderOverlay")
        self.setVisible(False)

        self.setStyleSheet("QWidget#tvReminderOverlay { background: rgba(0, 0, 0, 0.75); }")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(40, 40, 40, 40)
        root_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.card = QFrame(self)
        self.card.setObjectName("tvReminderCard")

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(36, 28, 36, 28)
        card_layout.setSpacing(14)

        self.header_title = QLabel("🚨 LEMBRETE OPERACIONAL", self.card)
        self.header_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.header_title.setObjectName("reminderHeaderTitle")
        card_layout.addWidget(self.header_title)

        self.op_info = QLabel("", self.card)
        self.op_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.op_info.setObjectName("reminderOpInfo")
        self.op_info.setWordWrap(True)
        card_layout.addWidget(self.op_info)

        self.message_label = QLabel("", self.card)
        self.message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message_label.setObjectName("reminderMessage")
        self.message_label.setWordWrap(True)
        card_layout.addWidget(self.message_label)

        self.footer_label = QLabel("", self.card)
        self.footer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.footer_label.setObjectName("reminderFooter")
        card_layout.addWidget(self.footer_label)

        root_layout.addWidget(self.card)

    def apply_style(
        self,
        *,
        background: str = "#0f172a",
        foreground: str = "#f8fafc",
        border_color: str = "#38bdf8",
        font_scale_percent: int = 100,
        width_percent: int = 65,
    ) -> None:
        scale = font_scale_percent / 100
        h_pt = max(14, round(22 * scale))
        info_pt = max(11, round(15 * scale))
        msg_pt = max(16, round(26 * scale))
        foot_pt = max(10, round(13 * scale))

        self.card.setStyleSheet(
            f"QFrame#tvReminderCard {{"
            f"  background-color: {background};"
            f"  border: 4px solid {border_color};"
            f"  border-radius: 14px;"
            f"}}"
            f"QLabel#reminderHeaderTitle {{"
            f"  color: {border_color};"
            f"  font-size: {h_pt}pt;"
            f"  font-weight: 900;"
            f"  letter-spacing: 1px;"
            f"}}"
            f"QLabel#reminderOpInfo {{"
            f"  color: #94a3b8;"
            f"  font-size: {info_pt}pt;"
            f"  font-weight: 600;"
            f"}}"
            f"QLabel#reminderMessage {{"
            f"  color: {foreground};"
            f"  font-size: {msg_pt}pt;"
            f"  font-weight: 800;"
            f"  padding: 8px 0;"
            f"}}"
            f"QLabel#reminderFooter {{"
            f"  color: #64748b;"
            f"  font-size: {foot_pt}pt;"
            f"  font-weight: 600;"
            f"}}"
        )
        if self.parentWidget():
            parent_w = max(400, self.parentWidget().width())
            card_w = max(400, round(parent_w * (width_percent / 100)))
            self.card.setMaximumWidth(card_w)

    def show_reminder(self, reminder: OpReminderDTO | dict[str, object], remaining_seconds: int) -> None:
        if isinstance(reminder, dict):
            num = str(reminder.get("numero_op", ""))
            cliente = str(reminder.get("cliente", ""))
            modelo = str(reminder.get("modelo", ""))
            msg = str(reminder.get("mensagem", ""))
        else:
            num = reminder.numero_op
            cliente = reminder.cliente
            modelo = reminder.modelo
            msg = reminder.mensagem

        if num:
            self.header_title.setText(f"🚨 LEMBRETE OPERACIONAL — OP {num}")
        else:
            self.header_title.setText("🚨 LEMBRETE OPERACIONAL")

        info_parts = []
        if cliente:
            info_parts.append(f"CLIENTE: {cliente}")
        if modelo:
            info_parts.append(f"MODELO: {modelo}")
        self.op_info.setText("   •   ".join(info_parts) if info_parts else "")
        self.op_info.setVisible(bool(info_parts))

        self.message_label.setText(msg)
        self.footer_label.setText(f"Exibindo na TV por mais {remaining_seconds}s...")
        self.setVisible(True)
        self.raise_()

    def update_countdown(self, remaining_seconds: int) -> None:
        self.footer_label.setText(f"Exibindo na TV por mais {remaining_seconds}s...")


class TvFocusWindow(QWidget):
    """Painel de tela cheia controlado pelas configurações centrais do NAS."""

    column_widths_changed = Signal(object)

    def __init__(
        self,
        *,
        settings: dict[str, object] | None = None,
        visible_columns: list[str] | None = None,
        page_interval_seconds: int | None = None,
        lines_per_page: int | None = None,
        editable_columns: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("TV/Foco")
        self.setObjectName("tvFocusWindow")
        self.list_view = OpListViewWidget(self)
        self.list_view.set_tv_editor_mode(editable_columns)
        self.list_view.tv_column_widths_changed.connect(self.column_widths_changed)
        self.list_view.table.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.list_view.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        try:
            self.list_view.table.horizontalHeader().sectionClicked.disconnect(self.list_view.model.sort_by_column)
        except (RuntimeError, TypeError):
            pass

        self.empty_notice = QLabel("Nenhuma OP ativa para exibir", self)
        self.empty_notice.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_notice.setObjectName("tvEmptyNotice")
        stack_host = QWidget(self)
        stack = QStackedLayout(stack_host)
        stack.setStackingMode(QStackedLayout.StackingMode.StackAll)
        stack.setContentsMargins(0, 0, 0, 0)
        stack.addWidget(self.list_view)
        stack.addWidget(self.empty_notice)
        self.reminder_overlay = TvReminderOverlay(stack_host)
        stack.addWidget(self.reminder_overlay)

        self.offline_notice = QLabel("Dados offline: exibindo a última atualização válida.", self)
        self.offline_notice.setObjectName("offlineNotice")
        self.offline_notice.setVisible(False)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.offline_notice)
        layout.addWidget(stack_host, 1)

        self._all_ops: list[OpListDTO] = []
        self._display_ops: list[OpListDTO] = []
        self._page = 0
        self._editable_columns = bool(editable_columns)
        self._metrics_pending = False
        self._last_header_height = 0
        self._reminders: list[OpReminderDTO] = []
        self._active_reminder: OpReminderDTO | dict[str, object] | None = None
        self._remaining_reminder_seconds: int = 0
        self._last_triggered_keys: set[str] = set()

        compatibility_settings = dict(settings or {})
        if visible_columns is not None:
            compatibility_settings["visible_columns"] = visible_columns
        if page_interval_seconds is not None:
            compatibility_settings["page_interval_seconds"] = page_interval_seconds
        if lines_per_page is not None:
            compatibility_settings["lines_per_page"] = lines_per_page
        self._settings = normalize_tv_settings(compatibility_settings)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.next_page)

        self._reminder_checker = QTimer(self)
        self._reminder_checker.timeout.connect(self._check_reminders_tick)
        self._reminder_checker.start(1000)

        self.apply_settings(compatibility_settings)

    @property
    def settings(self) -> dict[str, object]:
        return normalize_tv_settings(self._settings)

    @property
    def current_page(self) -> int:
        return self._page

    @property
    def page_count(self) -> int:
        return self._page_count()

    def set_editable_columns(self, enabled: bool) -> None:
        self._editable_columns = bool(enabled)
        self.list_view.set_tv_editor_mode(enabled)
        self._schedule_metrics()

    def apply_settings(self, settings: dict[str, object]) -> None:
        previous = getattr(self, "_settings", None)
        normalized = normalize_tv_settings(settings)
        previous_lines = previous.get("lines_per_page") if previous else None
        previous_interval = previous.get("page_interval_seconds") if previous else None
        previous_filter = (
            previous.get("sector_filter_mode"), tuple(previous.get("visible_sector_ids", []))
        ) if previous else None
        self._settings = normalized
        interval = int(normalized["page_interval_seconds"]) * 1000
        # O refresh de dados não reinicia a contagem da página. O timer muda
        # somente quando o próprio intervalo foi alterado.
        if not self._timer.isActive() or previous_interval != normalized["page_interval_seconds"]:
            self._timer.start(interval)
        if previous_lines != normalized["lines_per_page"]:
            self._page = 0
        current_filter = (normalized["sector_filter_mode"], tuple(normalized["visible_sector_ids"]))
        if previous_filter != current_filter:
            self._page = 0
        self._apply_sector_filter()
        self._apply_screen_style()
        self.list_view.apply_tv_layout(
            visible_columns=list(normalized["visible_columns"]),
            column_order=list(normalized["column_order"]),
            column_widths=dict(normalized["column_widths"]),
            column_font_scales=dict(normalized["column_font_scales"]),
            column_headers=dict(normalized["column_headers"]),
            column_alignments=dict(normalized["column_alignments"]),
            column_formats=dict(normalized["column_formats"]),
            sector_labels=dict(normalized["sector_labels"]),
            status_labels=dict(normalized["status_labels"]),
            row_height=40,
            item_point_size=max(9, round(12 * int(normalized["font_scale_percent"]) / 100)),
            header_point_size=max(9, round(11 * int(normalized["header_scale_percent"]) / 100)),
            editable_columns=self._editable_columns,
            color_mode="deadline",
            bold_rows=bool(normalized["bold_rows"]),
            show_grid=bool(normalized["show_grid"]),
            header_background=str(normalized["header_background"]),
            header_foreground=str(normalized["header_foreground"]),
            screen_background=str(normalized["screen_background"]),
            grid_color=str(normalized["grid_color"]),
            cell_padding_px=int(normalized["cell_padding_px"]),
        )
        self.reminder_overlay.apply_style(
            background=str(normalized.get("reminder_card_background", "#0f172a")),
            foreground=str(normalized.get("reminder_card_foreground", "#f8fafc")),
            border_color=str(normalized.get("reminder_card_border", "#38bdf8")),
            font_scale_percent=int(normalized.get("reminder_font_scale_percent", 100)),
            width_percent=int(normalized.get("reminder_width_percent", 65)),
        )
        self._render_page()

    def set_reminders(self, reminders: list[OpReminderDTO]) -> None:
        """Atualiza a lista de lembretes ativos para monitoramento contínuo na TV."""
        self._reminders = list(reminders)

    def trigger_test_reminder(self, duration_seconds: int = 10) -> None:
        """Dispara imediatamente um lembrete demonstrativo na TV para validação visual."""
        test_data = {
            "numero_op": "5320",
            "cliente": "ELETRICA COMANDO",
            "modelo": "VESPER PE 300e T4 0,5CV 440V",
            "mensagem": "Atenção: Conferir pintura e flange quadrado antes de embalar!",
        }
        self._active_reminder = test_data
        self._remaining_reminder_seconds = duration_seconds
        if self._settings.get("reminder_pause_pagination", True):
            self._timer.stop()
        self.reminder_overlay.apply_style(
            background=str(self._settings.get("reminder_card_background", "#0f172a")),
            foreground=str(self._settings.get("reminder_card_foreground", "#f8fafc")),
            border_color=str(self._settings.get("reminder_card_border", "#38bdf8")),
            font_scale_percent=int(self._settings.get("reminder_font_scale_percent", 100)),
            width_percent=int(self._settings.get("reminder_width_percent", 65)),
        )
        self.reminder_overlay.show_reminder(test_data, duration_seconds)

    def _check_reminders_tick(self) -> None:
        if self._active_reminder is not None:
            self._remaining_reminder_seconds -= 1
            if self._remaining_reminder_seconds <= 0:
                self._active_reminder = None
                self.reminder_overlay.setVisible(False)
                if self._settings.get("reminder_pause_pagination", True) and not self._timer.isActive():
                    interval = int(self._settings.get("page_interval_seconds", 13)) * 1000
                    self._timer.start(interval)
            else:
                self.reminder_overlay.update_countdown(self._remaining_reminder_seconds)
            return

        if not self._settings.get("reminder_enabled", True) or not self._reminders:
            return

        now_time = QTime.currentTime().toString("HH:mm")
        today = date.today()
        day_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        today_name = day_names[today.weekday()]

        for r in self._reminders:
            if not r.ativo:
                continue
            if r.horario != now_time:
                continue
            trigger_key = f"{r.id}:{today.isoformat()}:{now_time}"
            if trigger_key in self._last_triggered_keys:
                continue

            matches = False
            if r.tipo_recorrencia == "DAILY":
                matches = True
            elif r.tipo_recorrencia == "WEEKDAYS":
                matches = today.weekday() < 5
            elif r.tipo_recorrencia == "CUSTOM":
                matches = today_name in [d.lower() for d in r.dias_semana]
            elif r.tipo_recorrencia == "ONCE":
                matches = (r.data_inicio == today) if r.data_inicio else True

            if matches:
                self._last_triggered_keys.add(trigger_key)
                self._active_reminder = r
                self._remaining_reminder_seconds = max(5, r.duracao_segundos)
                if self._settings.get("reminder_pause_pagination", True):
                    self._timer.stop()
                self.reminder_overlay.apply_style(
                    background=str(self._settings.get("reminder_card_background", "#0f172a")),
                    foreground=str(self._settings.get("reminder_card_foreground", "#f8fafc")),
                    border_color=str(self._settings.get("reminder_card_border", "#38bdf8")),
                    font_scale_percent=int(self._settings.get("reminder_font_scale_percent", 100)),
                    width_percent=int(self._settings.get("reminder_width_percent", 65)),
                )
                self.reminder_overlay.show_reminder(r, self._remaining_reminder_seconds)
                break

    def set_ops(self, ops: list[OpListDTO]) -> None:
        self._all_ops = list(ops)
        self._apply_sector_filter()
        self._page %= self._page_count()
        self._render_page()

    def set_offline(self, offline: bool) -> None:
        self.offline_notice.setVisible(offline)
        self._schedule_metrics()

    def set_deadline_colors(self, warning: str, critical: str) -> None:
        self.list_view.set_deadline_colors(warning, critical)

    def set_deadline_rules(
        self,
        *,
        warning_days: int,
        critical_days: int,
        eligible_sector_ids: set[str] | None,
    ) -> None:
        self.list_view.set_deadline_rules(
            warning_days=warning_days,
            critical_days=critical_days,
            eligible_sector_ids=eligible_sector_ids,
        )

    def next_page(self) -> None:
        if self._page_count() <= 1:
            return
        self._page = (self._page + 1) % self._page_count()
        self._render_page()

    def previous_page(self) -> None:
        if self._page_count() <= 1:
            return
        self._page = (self._page - 1) % self._page_count()
        self._render_page()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._schedule_metrics()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._schedule_metrics()

    def _apply_sector_filter(self) -> None:
        mode = str(self._settings.get("sector_filter_mode", "all"))
        selected = {str(value) for value in self._settings.get("visible_sector_ids", [])}
        if mode == "selected":
            self._display_ops = [op for op in self._all_ops if op.setor_id and str(op.setor_id) in selected]
        else:
            self._display_ops = list(self._all_ops)

    def _page_count(self) -> int:
        return max(1, ceil(len(self._display_ops) / int(self._settings["lines_per_page"])))

    def _render_page(self) -> None:
        if not hasattr(self, "_settings"):
            return
        lines = int(self._settings["lines_per_page"])
        start = self._page * lines
        page_ops = self._display_ops[start : start + lines]
        self.list_view.set_ops(page_ops)
        # A barra fica oculta na TV, mas o QTableView pode preservar um offset
        # interno após redimensionar linhas. Sempre iniciar cada página no topo.
        self.list_view.table.scrollToTop()
        self.list_view.table.verticalScrollBar().setValue(0)
        self.empty_notice.setVisible(not page_ops)
        self._schedule_metrics()

    def _schedule_metrics(self) -> None:
        if self._metrics_pending:
            return
        self._metrics_pending = True
        QTimer.singleShot(0, self._apply_metrics)

    def _apply_metrics(self) -> None:
        self._metrics_pending = False
        if not hasattr(self, "_settings"):
            return
        table = self.list_view.table
        total_table_height = max(1, table.height())
        configured_lines = max(1, int(self._settings["lines_per_page"]))
        current_rows = len(self.list_view.model._ops)

        target_header_height = max(28, min(int(self._settings["header_height_px"]), max(28, total_table_height // 3)))
        header = table.horizontalHeader()
        if self._last_header_height != target_header_height:
            self._last_header_height = target_header_height
            header.setFixedHeight(target_header_height)
            self._schedule_metrics()

        available_height = max(1, table.viewport().height())
        visible_rows = min(configured_lines, max(1, current_rows))
        base_row_height, remainder = divmod(available_height, visible_rows)
        base_row_height = max(22, base_row_height)

        # O tamanho da fonte NÃO deve inflar excessivamente quando há menos linhas na página,
        # pois a largura das colunas é fixa e a fonte gigante estoura as células (gerando reticências).
        # Por isso, o point_size nominal baseia-se na altura correspondente a configured_lines.
        nominal_row_height = max(22, available_height // configured_lines)
        row_scale = int(self._settings["font_scale_percent"]) / 100
        header_scale = int(self._settings["header_scale_percent"]) / 100
        point_size = max(8, min(72, round(nominal_row_height * 0.30 * row_scale)))
        header_point_size = max(8, min(48, round(target_header_height * 0.40 * header_scale)))
        self.list_view.apply_tv_layout(
            visible_columns=list(self._settings["visible_columns"]),
            column_order=list(self._settings["column_order"]),
            column_widths=dict(self._settings["column_widths"]),
            column_font_scales=dict(self._settings["column_font_scales"]),
            column_headers=dict(self._settings["column_headers"]),
            column_alignments=dict(self._settings["column_alignments"]),
            column_formats=dict(self._settings["column_formats"]),
            sector_labels=dict(self._settings["sector_labels"]),
            status_labels=dict(self._settings["status_labels"]),
            row_height=base_row_height,
            item_point_size=point_size,
            header_point_size=header_point_size,
            editable_columns=self._editable_columns,
            color_mode="deadline",
            bold_rows=bool(self._settings["bold_rows"]),
            show_grid=bool(self._settings["show_grid"]),
            header_background=str(self._settings["header_background"]),
            header_foreground=str(self._settings["header_foreground"]),
            screen_background=str(self._settings["screen_background"]),
            grid_color=str(self._settings["grid_color"]),
            cell_padding_px=int(self._settings["cell_padding_px"]),
        )
        if current_rows:
            for row in range(table.model().rowCount()):
                table.setRowHeight(row, base_row_height + (1 if row < remainder else 0))
            table.scrollToTop()
            table.verticalScrollBar().setValue(0)

    def _apply_screen_style(self) -> None:
        background = str(self._settings["screen_background"])
        self.setStyleSheet(f"QWidget#tvFocusWindow {{ background: {background}; }}")
        self.empty_notice.setStyleSheet(
            f"QLabel#tvEmptyNotice {{ color: #b9c8dc; background: {background}; font-size: 20pt; font-weight: 700; }}"
        )
