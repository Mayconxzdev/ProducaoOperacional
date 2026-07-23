from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import date, datetime

from PySide6.QtCore import QThreadPool, QTimer
from PySide6.QtGui import QAction, QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QToolBar,
    QVBoxLayout,
)

from kanban_app.application.deadline_alert_service import DeadlineAlertService
from kanban_app.application.dto import ImportPreviewDTO, OpDetailDTO, OpFormDTO, OpListDTO
from kanban_app.application.error_reporting import friendly_error_message
from kanban_app.bootstrap import AppContainer
from kanban_app.domain.enums import OpStatus
from kanban_app.presentation.widgets.background_task import BackgroundTask
from kanban_app.presentation.widgets.history_dialog import HistoryDialog
from kanban_app.presentation.widgets.import_batch_dialog import ImportBatchDialog
from kanban_app.presentation.widgets.op_form_dialog import OpFormDialog, STATUS_LABELS
from kanban_app.presentation.widgets.op_list_view_widget import OpListViewWidget
from kanban_app.presentation.widgets.personalization_dialog import PersonalizationDialog
from kanban_app.presentation.widgets.tv_focus_window import TvFocusWindow
from kanban_app.presentation.tv_settings import default_tv_settings, normalize_tv_settings
from kanban_app.presentation.theme import apply_theme
from kanban_app.infrastructure.logging_setup import log_path


class MainWindow(QMainWindow):
    def __init__(self, container: AppContainer):
        super().__init__()
        self.container = container
        self.setWindowTitle("Produção Operacional")
        self.resize(1450, 860)
        self._pool = QThreadPool.globalInstance()
        self._tasks: set[BackgroundTask] = set()
        self._refresh_running = False
        self._last_snapshot_token: tuple[object, ...] | None = None
        self._closing = False
        self._offline = False
        self._tv_window: TvFocusWindow | None = None
        self._warning_color = "#f9a8d4"
        self._critical_color = "#ef4444"
        self._deadline_rules = {"warning_days": 14, "critical_days": 7, "eligible_sector_ids": None}
        self._tv_settings = default_tv_settings()
        try:
            self._tv_settings = self._read_tv_settings()
        except Exception:
            # O cache e a primeira atualização assíncrona mantêm a estação
            # utilizável mesmo durante uma indisponibilidade momentânea do NAS.
            pass
        self._deadline_email_hour = "08:00"
        self._last_alert_minute = ""
        self.list_view = OpListViewWidget(self)
        self.setCentralWidget(self.list_view)
        self._build_toolbar()
        self.statusBar().showMessage("")
        self.list_view.op_double_clicked.connect(self._show_op_actions)
        self.list_view.edit_requested.connect(self._open_edit)
        self.list_view.complete_requested.connect(self._complete_op)
        self.list_view.archive_requested.connect(self._archive_op)
        self.list_view.copy_number_requested.connect(lambda value: QGuiApplication.clipboard().setText(value))
        cached = self.container.runtime_store.load_cache()
        if cached:
            self.list_view.set_ops(cached)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self.refresh_automatically)
        self._refresh_timer.start(1_500)
        self._deadline_timer = QTimer(self)
        self._deadline_timer.timeout.connect(self._run_due_deadline_alert)
        self._deadline_timer.start(30_000)
        QTimer.singleShot(0, self.refresh_automatically)

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Operações", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        for text, callback in (
            ("Nova OP", self._new_op),
            ("Importar OP", self._import_ops),
            ("Histórico", self._open_history),
            ("Personalização", self._open_personalization),
            ("Abrir modo TV/Foco", self._open_tv),
        ):
            action = QAction(text, self)
            action.triggered.connect(lambda _checked=False, cb=callback: cb())
            toolbar.addAction(action)
        if self.container.is_demo:
            toolbar.addSeparator()
            notice = QLabel("MODO DEMONSTRAÇÃO — dados fictícios locais", toolbar)
            notice.setObjectName("demoNotice")
            notice.setStyleSheet("font-weight: 700; color: #78350f; background: #fef3c7; padding: 6px 10px; border-radius: 4px;")
            toolbar.addWidget(notice)
            for text, callback in (
                ("Guia da demonstração", self._show_demo_guide),
                ("Restaurar 10 OPs fictícias", self._reset_demo),
            ):
                action = QAction(text, self)
                action.triggered.connect(lambda _checked=False, cb=callback: cb())
                toolbar.addAction(action)

    def refresh_automatically(self) -> None:
        if self._closing or self._refresh_running:
            return
        self._refresh_running = True
        self._run_task(
            self._load_refresh_snapshot,
            self._apply_refresh,
            self._refresh_failed,
        )

    def _load_refresh_snapshot(self):
        tv_defaults = normalize_tv_settings(self._tv_settings)
        defaults: dict[str, object] = {
            "deadline.warning_color": self._warning_color,
            "deadline.critical_color": self._critical_color,
            "deadline.warning_days": self._deadline_rules.get("warning_days", 14),
            "deadline.critical_days": self._deadline_rules.get("critical_days", 7),
            "deadline.email_hour": self._deadline_email_hour,
        }
        defaults.update({f"tv.{name}": value for name, value in tv_defaults.items()})
        return self.container.repository.read_shared_snapshot(
            defaults.keys(),
            defaults=defaults,
        )

    def _apply_refresh(self, result) -> None:
        ops, values, database_token = result
        warning_color = str(values.get("deadline.warning_color") or "#f9a8d4")
        critical_color = str(values.get("deadline.critical_color") or "#ef4444")
        try:
            warning_days = max(1, int(values.get("deadline.warning_days", 14)))
            critical_days = max(0, min(warning_days, int(values.get("deadline.critical_days", 7))))
        except (TypeError, ValueError):
            warning_days, critical_days = 14, 7
        deadline_rules = {
            "warning_days": warning_days,
            "critical_days": critical_days,
            "eligible_sector_ids": None,
        }
        tv_names = tuple(default_tv_settings())
        tv_settings = normalize_tv_settings(
            {name: values.get(f"tv.{name}") for name in tv_names}
        )
        deadline_email_hour = str(values.get("deadline.email_hour") or "08:00")

        effective_token = (*database_token, date.today().isoformat())
        data_changed = effective_token != self._last_snapshot_token
        settings_changed = tv_settings != self._tv_settings
        self._last_snapshot_token = effective_token
        self._warning_color = warning_color
        self._critical_color = critical_color
        self._deadline_rules = deadline_rules
        self._deadline_email_hour = deadline_email_hour
        self._tv_settings = tv_settings
        self._refresh_running = False
        self._offline = False
        self.container.database.clear_read_only()
        self.statusBar().showMessage("")

        if data_changed:
            self.container.runtime_store.save_cache(ops)
            self.list_view.set_ops(ops)
        self._apply_shared_colors()
        if self._tv_window:
            if settings_changed:
                self._tv_window.apply_settings(self._tv_settings)
            if data_changed:
                self._tv_window.set_ops(ops)
            self._tv_window.set_offline(False)
            self._apply_shared_colors()

    def _refresh_failed(self, error: str) -> None:
        self._refresh_running = False
        self._offline = True
        self.container.database.set_read_only("NAS indisponível. Alterações bloqueadas até a conexão voltar.")
        self.statusBar().showMessage("NAS indisponível: exibindo os últimos dados válidos em modo somente leitura.")
        if self._tv_window:
            self._tv_window.set_offline(True)

    def _run_due_deadline_alert(self) -> None:
        current_minute = datetime.now().strftime("%Y-%m-%d %H:%M")
        if self._offline or not current_minute.endswith(self._deadline_email_hour) or current_minute == self._last_alert_minute:
            return
        self._last_alert_minute = current_minute
        service = DeadlineAlertService(self.container.repository, self.container.config.smtp, station_id=self.container.station_id)
        self._run_task(service.run_daily, lambda _count: None, lambda _error: None)

    def _apply_shared_colors(self) -> None:
        self.list_view.set_deadline_colors(self._warning_color, self._critical_color)
        self.list_view.set_deadline_rules(**self._deadline_rules)
        if self._tv_window:
            self._tv_window.set_deadline_colors(self._warning_color, self._critical_color)
            self._tv_window.set_deadline_rules(**self._deadline_rules)

    def _new_op(self) -> None:
        self._load_form(None)

    def _open_edit(self, op: OpListDTO) -> None:
        self._load_form(op.id)

    def _load_form(self, op_id: int | None, preview: ImportPreviewDTO | None = None, *, read_only: bool = False) -> None:
        def load():
            detail = self.container.production_service.get(op_id) if op_id is not None else None
            initial = preview.form if preview is not None else (detail or self.container.production_service.form_defaults())
            return initial, self.container.production_service.sectors(active_only=True), self.container.repository.recent_voltages(), detail

        def show(result) -> None:
            initial, sectors, voltages, detail = result
            dialog = OpFormDialog(sectors=sectors, voltages=voltages, initial=initial, read_only=read_only, parent=self)
            if dialog.exec() != QDialog.DialogCode.Accepted or read_only:
                return
            self._save_form(dialog.form_value(), detail)

        self._run_task(load, show)

    def _save_form(self, form: OpFormDTO, existing: OpDetailDTO | None) -> None:
        def find_duplicates():
            return self.container.production_service.duplicates(form.numero_op, exclude_id=existing.id if existing else None)

        def continue_after_duplicates(duplicates: list[OpListDTO]) -> None:
            if duplicates:
                examples = ", ".join(f"OP {op.numero_op} ({op.cliente})" for op in duplicates[:3])
                answer = QMessageBox.question(self, "Número de OP já existente", f"Já existe {examples}. Deseja salvar uma duplicata mesmo assim?")
                if answer != QMessageBox.StandardButton.Yes:
                    return
            operation = (lambda: self.container.production_service.update(existing.id, form, existing.row_version)) if existing else (lambda: self.container.production_service.create(form))
            self._run_write(operation)

        self._run_task(find_duplicates, continue_after_duplicates)

    def _show_op_actions(self, op: OpListDTO) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Ações da OP")
        label = QLabel(f"OP {op.numero_op or 'sem número'}\n{op.cliente or 'Cliente não informado'}", dialog)
        complete = QPushButton("Concluir OP", dialog)
        edit = QPushButton("Editar OP", dialog)
        cancel = QPushButton("Cancelar", dialog)
        layout = QVBoxLayout(dialog)
        layout.addWidget(label)
        layout.addWidget(complete)
        layout.addWidget(edit)
        layout.addWidget(cancel)
        complete.clicked.connect(lambda: (dialog.accept(), self._complete_op(op)))
        edit.clicked.connect(lambda: (dialog.accept(), self._open_edit(op)))
        cancel.clicked.connect(dialog.reject)
        dialog.exec()

    def _complete_op(self, op: OpListDTO) -> None:
        self._run_write(lambda: self.container.production_service.complete(op.id, op.row_version))

    def _archive_op(self, op: OpListDTO) -> None:
        if QMessageBox.question(self, "Arquivar OP", f"Arquivar a OP {op.numero_op or op.id}? Ela poderá ser restaurada no Histórico.") != QMessageBox.StandardButton.Yes:
            return
        self._run_write(lambda: self.container.production_service.archive(op.id, op.row_version))

    def _open_history(self) -> None:
        self._run_task(
            lambda: (self.container.repository.list_concluded_ops(), self.container.repository.list_archived_ops()),
            self._show_history,
        )

    def _show_history(self, result) -> None:
        concluded, archived = result
        dialog = HistoryDialog(concluded, archived, self)
        dialog.open_requested.connect(lambda op: self._load_form(op.id, read_only=True))
        dialog.reopen_requested.connect(self._reopen_op)
        dialog.restore_requested.connect(lambda op: self._run_write(lambda: self.container.production_service.restore(op.id, op.row_version)))
        dialog.changes_requested.connect(self._show_changes)
        dialog.exec()

    def _reopen_op(self, op: OpListDTO) -> None:
        options = [status for status in OpStatus if status != OpStatus.CONCLUIDO]
        labels = [STATUS_LABELS[status] for status in options]
        label, accepted = QInputDialog.getItem(self, "Reabrir OP", "Novo status", labels, 2, False)
        if not accepted:
            return
        status = next(status for status, status_label in STATUS_LABELS.items() if status_label == label)
        self._run_write(lambda: self.container.production_service.reopen(op.id, op.row_version, status))

    def _show_changes(self, op: OpListDTO) -> None:
        def show(entries) -> None:
            dialog = QDialog(self)
            dialog.setWindowTitle(f"Alterações da OP {op.numero_op}")
            text = QPlainTextEdit(dialog)
            text.setReadOnly(True)
            text.setPlainText("\n".join(f"{entry.occurred_at:%d/%m/%Y %H:%M} | {entry.event_type} | {entry.field_name} | {entry.old_value} -> {entry.new_value} | {entry.station_id}" for entry in entries))
            layout = QVBoxLayout(dialog)
            layout.addWidget(text)
            dialog.resize(780, 500)
            dialog.exec()

        self._run_task(lambda: self.container.repository.history_for_op(op.id), show)

    def _import_ops(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Importar OP", "", "Documentos (*.pdf *.docx *.odt)")
        if not paths:
            return
        def extract():
            default_sector = self.container.production_service.form_defaults().setor_id
            return [self.container.document_import_service.extract(path, default_sector_id=default_sector) for path in paths]
        self._run_task(extract, self._show_import_batch)

    def _show_import_batch(self, previews: list[ImportPreviewDTO]) -> None:
        dialog = ImportBatchDialog(previews, self)
        dialog.edit_requested.connect(lambda row, preview: self._edit_import_preview(dialog, row, preview))
        dialog.confirm_all_requested.connect(lambda complete: self._confirm_import_batch(dialog, list(complete)))
        dialog.exec()

    def _edit_import_preview(self, batch_dialog: ImportBatchDialog, row: int, preview: ImportPreviewDTO) -> None:
        def load_options():
            return self.container.repository.list_sectors(active_only=True), self.container.repository.recent_voltages()

        def show_editor(result) -> None:
            sectors, voltages = result
            editor = OpFormDialog(sectors=sectors, voltages=voltages, initial=preview.form, parent=batch_dialog)
            editor.setWindowTitle(f"Revisar importação — {preview.form.numero_op or 'nova OP'}")
            if editor.exec() != QDialog.DialogCode.Accepted:
                return
            form = editor.form_value()
            updated = replace(
                preview,
                form=form,
                missing_fields=tuple(self.container.document_import_service.missing_fields_for_form(form)),
                errors=(),
            )
            batch_dialog.update_preview(row, updated)

        self._run_task(load_options, show_editor)

    def _confirm_import_batch(self, batch_dialog: ImportBatchDialog, previews: list[ImportPreviewDTO]) -> None:
        complete = [preview for preview in previews if not preview.errors and not preview.missing_fields]
        if not complete:
            QMessageBox.information(batch_dialog, "Nada para criar", "Revise os campos obrigatórios antes de criar as OPs.")
            return

        def inspect_duplicates():
            return [(preview, self.container.production_service.duplicates(preview.form.numero_op)) for preview in complete]

        def ask_confirmation(rows) -> None:
            duplicates = [(preview, matches) for preview, matches in rows if matches]
            existing_numbers = {preview.form.numero_op for preview, _matches in duplicates}
            selected: list[ImportPreviewDTO] = []
            repeated_in_batch: set[str] = set()
            for preview, matches in rows:
                number = preview.form.numero_op
                if matches or number in {item.form.numero_op for item in selected}:
                    if not matches:
                        repeated_in_batch.add(number)
                    continue
                selected.append(preview)
            if not selected:
                QMessageBox.information(
                    batch_dialog,
                    "Nenhuma OP nova",
                    "Todos os itens selecionados já existem no Kanban ou se repetem no mesmo lote.",
                )
                return
            message = f"Criar {len(selected)} OP(s) nova(s) e completa(s)?"
            if duplicates:
                numbers = ", ".join(sorted(existing_numbers))
                message += (
                    f"\n\n{len(duplicates)} item(ns) com número já existente ({numbers}) serão bloqueados."
                )
            if repeated_in_batch:
                message += f"\n\nNúmeros repetidos no mesmo lote serão bloqueados: {', '.join(sorted(repeated_in_batch))}."
            if QMessageBox.question(batch_dialog, "Confirmar importação", message) != QMessageBox.StandardButton.Yes:
                return
            batch_dialog.accept()
            self._run_task(lambda: self._create_import_batch(selected), self._finish_import_batch, self._write_failed)

        self._run_task(inspect_duplicates, ask_confirmation)

    def _create_import_batch(self, previews: list[ImportPreviewDTO]) -> tuple[int, list[str]]:
        created = 0
        errors: list[str] = []
        for preview in previews:
            try:
                self.container.production_service.create(preview.form)
                created += 1
            except Exception as exc:  # mantém o lote avançando e informa cada falha ao final
                source = preview.form.numero_op or preview.source_path
                errors.append(f"{source}: {exc}")
        return created, errors

    def _finish_import_batch(self, result: tuple[int, list[str]]) -> None:
        created, errors = result
        self.refresh_automatically()
        if errors:
            detail = "\n".join(errors[:8])
            if len(errors) > 8:
                detail += f"\n... e mais {len(errors) - 8} falha(s)."
            QMessageBox.warning(
                self,
                "Importação concluída com ressalvas",
                f"{created} OP(s) criada(s). {len(errors)} item(ns) falharam.\n\n{detail}",
            )
        else:
            QMessageBox.information(self, "Importação concluída", f"{created} OP(s) criada(s) com sucesso.")

    def _open_personalization(self) -> None:
        if self._offline:
            QMessageBox.warning(self, "NAS indisponível", "A personalização está bloqueada enquanto o NAS estiver indisponível.")
            return
        dialog = PersonalizationDialog(
            self.container.repository,
            self.container.config,
            self.container.station_id,
            preview_ops=list(self.list_view.model._ops),
            tv_settings=self._tv_settings,
            runtime_store=self.container.runtime_store,
            theme_mode=self.container.runtime_store.load_theme_mode(self.container.config.theme_mode),
            parent=self,
        )
        dialog.tv_settings_changed.connect(self._apply_tv_settings_immediately)
        dialog.office_theme_changed.connect(self._apply_office_theme)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh_automatically()

    def _open_tv(self, fullscreen: bool = True, screen=None) -> None:
        if self._tv_window is None:
            self._tv_window = TvFocusWindow(settings=self._tv_settings)
        else:
            self._tv_window.apply_settings(self._tv_settings)
        self._tv_window.set_ops(list(self.list_view.model._ops))
        self._tv_window.set_offline(self._offline)
        self._apply_shared_colors()
        if screen is not None:
            self._tv_window.setGeometry(screen.geometry())
            handle = self._tv_window.windowHandle()
            if handle is not None:
                handle.setScreen(screen)
        if fullscreen:
            self._tv_window.showFullScreen()
        else:
            self._tv_window.showMaximized()
        self._tv_window.raise_()
        self.refresh_automatically()

    def _show_demo_guide(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Guia rápido — Modo Demonstração")
        dialog.setMinimumWidth(610)
        layout = QVBoxLayout(dialog)
        title = QLabel("Aprenda o fluxo sem tocar na operação real", dialog)
        title.setObjectName("dialogTitle")
        layout.addWidget(title)
        instructions = (
            "1. Selecione uma OP e use Editar ou Concluir para praticar o fluxo de produção.",
            "2. Crie uma OP com Nova OP ou importe um documento fictício para testar o cadastro.",
            "3. Abra o modo TV/Foco para ver as 10 OPs em duas páginas automáticas.",
            "4. Em Personalização, altere cores, colunas e textos da TV; tudo fica salvo apenas nesta demonstração.",
            "5. Use Restaurar 10 OPs fictícias quando quiser voltar ao ponto inicial.",
        )
        for instruction in instructions:
            item = QLabel(instruction, dialog)
            item.setWordWrap(True)
            item.setStyleSheet("padding: 5px 0;")
            layout.addWidget(item)
        safety = QLabel(
            "Segurança: este modo usa um banco SQLite local separado e mantém SMTP desativado. "
            "Nenhum dado do NAS é lido, alterado ou enviado.",
            dialog,
        )
        safety.setWordWrap(True)
        safety.setObjectName("helpText")
        layout.addWidget(safety)
        close = QPushButton("Entendi", dialog)
        close.clicked.connect(dialog.accept)
        layout.addWidget(close)
        dialog.exec()

    def _reset_demo(self) -> None:
        if self._refresh_running:
            QMessageBox.information(
                self,
                "Aguarde a atualização",
                "A demonstração ainda está carregando os dados locais. Aguarde alguns segundos e tente novamente.",
            )
            return
        if QMessageBox.question(
            self,
            "Restaurar demonstração",
            "As OPs, o histórico e as personalizações feitas somente nesta demonstração serão apagados. "
            "A base voltará às 10 OPs fictícias iniciais. Continuar?",
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.container = self.container.reset_demo()
            self._tv_settings = self._read_tv_settings()
            self._last_snapshot_token = None
            self._offline = False
            self.list_view.set_ops([])
            self.refresh_automatically()
        except Exception as exc:
            self._show_detailed_error("Não foi possível restaurar a demonstração", str(exc))
            return
        QMessageBox.information(self, "Demonstração restaurada", "As 10 OPs fictícias foram restauradas com sucesso.")

    def _read_tv_settings(self) -> dict[str, object]:
        defaults = normalize_tv_settings(getattr(self, "_tv_settings", default_tv_settings()))
        names = tuple(defaults)
        keys = [f"tv.{name}" for name in names]
        values = self.container.repository.get_settings(
            keys,
            defaults={f"tv.{name}": defaults[name] for name in names},
        )
        return normalize_tv_settings({name: values[f"tv.{name}"] for name in names})

    def _read_deadline_rules(self) -> dict[str, object]:
        # As faixas de prazo valem para qualquer setor. O status nunca define a
        # cor; fora das faixas, a linha volta à cor configurada para o setor.
        try:
            warning_days = max(1, int(self.container.repository.get_setting("deadline.warning_days", 14)))
            critical_days = max(0, min(warning_days, int(self.container.repository.get_setting("deadline.critical_days", 7))))
        except (TypeError, ValueError):
            warning_days, critical_days = 14, 7
        return {"warning_days": warning_days, "critical_days": critical_days, "eligible_sector_ids": None}

    def _apply_tv_settings_immediately(self, settings: dict[str, object]) -> None:
        self._tv_settings = normalize_tv_settings(settings)
        if self._tv_window:
            self._tv_window.apply_settings(self._tv_settings)
            self._tv_window.set_ops(list(self.list_view.model._ops))

    def _apply_office_theme(self, theme_mode: str) -> None:
        app = QApplication.instance()
        if app is not None:
            apply_theme(app, theme_mode)

    def _run_write(self, operation: Callable[[], object]) -> None:
        if self._offline or self.container.database.is_read_only():
            QMessageBox.warning(self, "Alterações bloqueadas", "O NAS está indisponível. A aplicação permanece em modo somente leitura até a reconexão.")
            return
        self._run_task(operation, lambda _result: self.refresh_automatically(), self._write_failed)

    def _write_failed(self, error: str) -> None:
        if "OptimisticConflictError" in error or "alterada em outra estação" in error:
            QMessageBox.warning(
                self,
                "Conflito de alteração",
                "Esta OP foi alterada em outra estação. A lista será recarregada; os dados digitados não foram gravados.",
            )
            self.refresh_automatically()
            return
        self._show_detailed_error("Não foi possível salvar", error)

    def _run_task(self, operation: Callable[[], object], on_success: Callable[[object], None], on_failure: Callable[[str], None] | None = None) -> None:
        task = BackgroundTask(operation)
        self._tasks.add(task)
        task.signals.finished.connect(lambda result: self._finish_task(task, lambda: on_success(result)))
        task.signals.failed.connect(lambda error: self._finish_task(task, lambda: (on_failure or self._show_task_error)(error)))
        self._pool.start(task)

    def _finish_task(self, task: BackgroundTask, callback: Callable[[], None]) -> None:
        self._tasks.discard(task)
        if not self._closing:
            callback()

    def closeEvent(self, event) -> None:
        self._closing = True
        self._refresh_timer.stop()
        self._deadline_timer.stop()
        if self._tv_window:
            self._tv_window.close()
        super().closeEvent(event)

    def _show_task_error(self, error: str) -> None:
        self._show_detailed_error("Operação não concluída", error)

    def _show_detailed_error(self, title: str, error: str) -> None:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(title)
        box.setText(self._error_message(error))
        box.setInformativeText(
            "Nenhum dado foi salvo. Os detalhes técnicos foram registrados em:\n"
            f"{log_path()}"
        )
        box.setDetailedText(str(error))
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        box.exec()

    @staticmethod
    def _error_message(error: str) -> str:
        return friendly_error_message(error)
