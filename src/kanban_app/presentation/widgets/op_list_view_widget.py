from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHeaderView,
    QMenu,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from kanban_app.application.dto import OpListDTO
from kanban_app.presentation.tv_settings import fit_column_widths
from kanban_app.presentation.widgets._op_list_model_view import OpListModel


class _TvCellDelegate(QStyledItemDelegate):
    """Desenha a célula da TV preservando a cor do modelo e o espaço interno.

    Um seletor QSS ``QTableView::item`` faz o Fusion ignorar o BackgroundRole
    em algumas versões do Qt/Windows. O delegate evita essa regressão e deixa
    a prévia exatamente igual à TV real.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._padding = 7

    def set_padding(self, value: int) -> None:
        self._padding = max(0, min(24, int(value)))

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        painter.save()
        background = index.data(Qt.ItemDataRole.BackgroundRole)
        if background is not None:
            brush = background if hasattr(background, "color") else QColor(background)
            painter.fillRect(option.rect, brush)

        font = index.data(Qt.ItemDataRole.FontRole)
        if isinstance(font, QFont):
            painter.setFont(font)
        foreground = index.data(Qt.ItemDataRole.ForegroundRole)
        if foreground is not None:
            color = foreground.color() if hasattr(foreground, "color") else QColor(foreground)
            painter.setPen(QPen(color))

        alignment = index.data(Qt.ItemDataRole.TextAlignmentRole)
        try:
            flags = Qt.AlignmentFlag(int(alignment))
        except (TypeError, ValueError):
            flags = Qt.AlignmentFlag.AlignCenter
        flags |= Qt.AlignmentFlag.AlignVCenter
        rect = option.rect.adjusted(self._padding, 0, -self._padding, 0)
        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        metrics = painter.fontMetrics()
        text = metrics.elidedText(text, Qt.TextElideMode.ElideRight, max(1, rect.width()))
        painter.drawText(rect, flags, text)
        painter.restore()


class OpListViewWidget(QWidget):
    op_double_clicked = Signal(object)
    edit_requested = Signal(object)
    complete_requested = Signal(object)
    archive_requested = Signal(object)
    copy_number_requested = Signal(str)
    tv_column_widths_changed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tv_editor_mode = False
        self._applying_tv_layout = False
        self._last_tv_weights: dict[str, int] = {}
        self.model = OpListModel(self)
        self.table = QTableView(self)
        self.table.setModel(self.model)
        self._default_delegate = self.table.itemDelegate()
        self._tv_delegate = _TvCellDelegate(self.table)
        self.table.setFrameShape(QFrame.Shape.NoFrame)
        self.table.setCornerButtonEnabled(False)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
        self.table.setAlternatingRowColors(False)
        self.table.setMouseTracking(True)
        self.table.setWordWrap(False)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setMinimumSectionSize(28)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.doubleClicked.connect(self._emit_double_click)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.horizontalHeader().sectionClicked.connect(self.model.sort_by_column)
        self.table.horizontalHeader().sectionResized.connect(self._section_resized)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.table)
        for index, width in enumerate((82, 132, 210, 330, 100, 64, 104, 110, 150, 250)):
            self.table.setColumnWidth(index, width)

    def set_ops(self, ops: list[OpListDTO]) -> None:
        self.model.set_ops(ops)

    def set_deadline_colors(self, warning: str, critical: str) -> None:
        self.model.set_colors(warning, critical)

    def set_deadline_rules(
        self,
        *,
        warning_days: int,
        critical_days: int,
        eligible_sector_ids: set[str] | None,
    ) -> None:
        self.model.set_deadline_rules(
            warning_days=warning_days,
            critical_days=critical_days,
            eligible_sector_ids=eligible_sector_ids,
        )

    def set_tv_editor_mode(self, enabled: bool) -> None:
        self._tv_editor_mode = bool(enabled)
        if self.table.objectName() == "tvFocusTable":
            header = self.table.horizontalHeader()
            header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive if enabled else QHeaderView.ResizeMode.Fixed)
            header.setCursor(Qt.CursorShape.SplitHCursor if enabled else Qt.CursorShape.ArrowCursor)

    def apply_tv_layout(
        self,
        *,
        visible_columns: list[str],
        column_order: list[str],
        column_widths: Mapping[str, int],
        row_height: int,
        item_point_size: int,
        header_point_size: int | None = None,
        column_font_scales: Mapping[str, int] | None = None,
        column_headers: Mapping[str, str] | None = None,
        column_alignments: Mapping[str, str] | None = None,
        column_formats: Mapping[str, str] | None = None,
        sector_labels: Mapping[str, str] | None = None,
        status_labels: Mapping[str, str] | None = None,
        editable_columns: bool | None = None,
        color_mode: str = "deadline",
        bold_rows: bool = True,
        show_grid: bool = True,
        header_background: str = "#1d3557",
        header_foreground: str = "#ffffff",
        screen_background: str = "#0f172a",
        grid_color: str = "#10233d",
        cell_padding_px: int = 7,
    ) -> None:
        """Aplica o mesmo layout compartilhado à prévia e à TV real."""
        if editable_columns is not None:
            self._tv_editor_mode = bool(editable_columns)
        self._applying_tv_layout = True
        try:
            self.table.setObjectName("tvFocusTable")
            header = self.table.horizontalHeader()
            header.setStretchLastSection(False)
            header.setSectionsMovable(False)
            header.setMinimumSectionSize(28)
            header.setSectionResizeMode(
                QHeaderView.ResizeMode.Interactive if self._tv_editor_mode else QHeaderView.ResizeMode.Fixed
            )
            header.setCursor(Qt.CursorShape.SplitHCursor if self._tv_editor_mode else Qt.CursorShape.ArrowCursor)
            self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.table.setShowGrid(bool(show_grid))
            self._tv_delegate.set_padding(cell_padding_px)
            self.table.setItemDelegate(self._tv_delegate)
            self.table.setAlternatingRowColors(False)
            self.model.set_presentation(
                item_point_size=item_point_size,
                header_point_size=header_point_size,
                header_labels=column_headers,
                tv_mode=True,
                tv_bold_all=bool(bold_rows),
                column_font_scales=column_font_scales,
                column_alignments=column_alignments,
                column_formats=column_formats,
                sector_labels=sector_labels,
                status_labels=status_labels,
                color_mode=color_mode,
            )
            key_to_logical = {key: index for index, (key, _label) in enumerate(self.model.COLUMNS)}
            order = [key for key in column_order if key in key_to_logical]
            order.extend(key for key in key_to_logical if key not in order)
            visible = {key for key in visible_columns if key in key_to_logical}
            ordered_visible = [key for key in order if key in visible]

            for target_visual, key in enumerate(order):
                logical = key_to_logical[key]
                current_visual = header.visualIndex(logical)
                if current_visual != target_visual:
                    header.moveSection(current_visual, target_visual)

            for key, logical in key_to_logical.items():
                self.table.setColumnHidden(logical, key not in visible)

            available_width = max(1, self.table.viewport().width())
            fitted_widths = fit_column_widths(ordered_visible, column_widths, available_width, minimum_width=28)
            self._last_tv_weights = {key: int(column_widths.get(key, 100)) for key in key_to_logical}
            for key, logical in key_to_logical.items():
                if key in fitted_widths:
                    self.table.setColumnWidth(logical, fitted_widths[key])

            base_height = max(22, int(row_height))
            self.table.verticalHeader().setDefaultSectionSize(base_height)
            for row in range(self.table.model().rowCount()):
                self.table.setRowHeight(row, base_height)

            effective_header = max(7, int(header_point_size or round(item_point_size * 0.92)))
            padding = max(0, min(24, int(cell_padding_px)))
            header.setStyleSheet(
                f"""
                QHeaderView::section {{
                    background: {header_background};
                    color: {header_foreground};
                    border: 0;
                    border-right: {1 if show_grid else 0}px solid {grid_color};
                    border-bottom: {1 if show_grid else 0}px solid {grid_color};
                    padding: 2px {padding}px;
                    font-size: {effective_header}pt;
                    font-weight: 900;
                }}
                """
            )
            self.table.setStyleSheet(
                f"""
                QTableView#tvFocusTable {{
                    gridline-color: {grid_color};
                    background: {screen_background};
                    border: 0;
                    outline: 0;
                    selection-background-color: transparent;
                }}
                """
            )
        finally:
            self._applying_tv_layout = False

    def restore_office_layout(self) -> None:
        self._applying_tv_layout = True
        try:
            self.table.setObjectName("opListTable")
            self.table.horizontalHeader().setStretchLastSection(True)
            self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
            self.table.horizontalHeader().setCursor(Qt.CursorShape.ArrowCursor)
            self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self.table.setShowGrid(False)
            self.table.setItemDelegate(self._default_delegate)
            self.table.horizontalHeader().setStyleSheet("")
            self.table.setStyleSheet("")
            self.model.set_presentation(item_point_size=10, tv_mode=False, tv_bold_all=False, color_mode="deadline")
        finally:
            self._applying_tv_layout = False

    def current_visible_width_weights(self) -> dict[str, int]:
        key_to_logical = {key: index for index, (key, _label) in enumerate(self.model.COLUMNS)}
        result = dict(self._last_tv_weights)
        for key, logical in key_to_logical.items():
            if not self.table.isColumnHidden(logical):
                result[key] = max(28, self.table.columnWidth(logical))
        return result

    def _section_resized(self, logical: int, _old_size: int, _new_size: int) -> None:
        if self._applying_tv_layout or not self._tv_editor_mode or self.table.objectName() != "tvFocusTable":
            return
        if self.table.isColumnHidden(logical):
            return
        self.tv_column_widths_changed.emit(self.current_visible_width_weights())

    def _emit_double_click(self, index) -> None:
        op = self.model.op_at(index)
        if op is not None:
            self.op_double_clicked.emit(op)

    def _show_context_menu(self, position: QPoint) -> None:
        op = self.model.op_at(self.table.indexAt(position))
        if op is None:
            return
        menu = QMenu(self)
        edit = menu.addAction("Editar OP")
        complete = menu.addAction("Concluir OP")
        archive = menu.addAction("Arquivar OP")
        menu.addSeparator()
        copy = menu.addAction("Copiar número da OP")
        selected = menu.exec(self.table.viewport().mapToGlobal(position))
        if selected is edit:
            self.edit_requested.emit(op)
        elif selected is complete:
            self.complete_requested.emit(op)
        elif selected is archive:
            self.archive_requested.emit(op)
        elif selected is copy:
            self.copy_number_requested.emit(op.numero_op)
