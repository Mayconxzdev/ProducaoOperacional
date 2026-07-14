from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import QSize, QTime, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from kanban_app import __version__
from kanban_app.application.dto import OpListDTO, SectorDTO
from kanban_app.infrastructure.config import AppConfig
from kanban_app.infrastructure.db.repositories import ProductionRepository
from kanban_app.infrastructure.services.station_runtime import StationRuntimeStore
from kanban_app.presentation.tv_settings import (
    TV_COLUMN_LABELS,
    TV_DEFAULT_STATUS_LABELS,
    default_tv_settings,
    normalize_tv_settings,
)
from kanban_app.presentation.widgets.tv_focus_window import TvFocusWindow


_ALIGNMENT_OPTIONS = (
    ("Esquerda", "left"),
    ("Centro", "center"),
    ("Direita", "right"),
)
_DATE_FORMAT_OPTIONS = (
    ("Completa: 18/01/2026", "dd/MM/yyyy"),
    ("Ano curto: 18/01/26", "dd/MM/yy"),
    ("Sem ano: 18/01", "dd/MM"),
)


class ColorInput(QWidget):
    color_changed = Signal(str)

    def __init__(self, value: str, parent=None):
        super().__init__(parent)
        self.swatch = QPushButton(self)
        self.swatch.setFixedSize(58, 38)
        self.swatch.setCursor(Qt.CursorShape.PointingHandCursor)
        self.swatch.setToolTip("Clique para escolher a cor visualmente")
        self.edit = QLineEdit(str(value or ""), self)
        self.edit.setMaximumWidth(120)
        self.edit.setPlaceholderText("#RRGGBB")
        choose = QPushButton("Escolher…", self)
        choose.setToolTip("Abrir o seletor visual de cor")
        choose.clicked.connect(self._choose)
        self.swatch.clicked.connect(self._choose)
        self.edit.textChanged.connect(self._refresh)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.swatch)
        layout.addWidget(self.edit)
        layout.addWidget(choose)
        layout.addStretch(1)
        self._refresh(self.edit.text())

    def text(self) -> str:
        return self.edit.text().strip()

    def setText(self, value: str) -> None:
        self.edit.setText(value)

    def is_valid(self) -> bool:
        return QColor(self.text()).isValid()

    def _choose(self) -> None:
        current = QColor(self.text())
        color = QColorDialog.getColor(current if current.isValid() else QColor("#475569"), self, "Escolher cor")
        if color.isValid():
            self.setText(color.name())

    def _refresh(self, value: str) -> None:
        color = QColor(value)
        shown = color.name() if color.isValid() else "#475569"
        border = "#ef4444" if not color.isValid() else "#7890ad"
        self.swatch.setStyleSheet(
            f"background: {shown}; border: 2px solid {border}; border-radius: 7px;"
        )
        self.edit.setProperty("invalid", not color.isValid())
        self.edit.style().unpolish(self.edit)
        self.edit.style().polish(self.edit)
        self.color_changed.emit(value)


class SectorListCard(QFrame):
    """Cartão visual que preserva as cores próprias de cada setor no painel."""

    def __init__(self, sector: SectorDTO, parent=None):
        super().__init__(parent)
        self.sector = sector
        self._selected = False
        self.setObjectName("sectorListCard")
        self.setMinimumHeight(56)
        self.name_label = QLabel(f"{sector.ordem}. {sector.nome}", self)
        self.name_label.setObjectName("sectorCardName")
        self.state_label = QLabel("ATIVO" if sector.ativo else "INATIVO", self)
        self.state_label.setObjectName("sectorCardState")
        self.state_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 7, 10, 7)
        layout.setSpacing(10)
        layout.addWidget(self.name_label, 1)
        layout.addWidget(self.state_label)
        self._apply_style()

    def set_selected(self, selected: bool) -> None:
        self._selected = bool(selected)
        self._apply_style()

    def _apply_style(self) -> None:
        background = QColor(self.sector.cor)
        foreground = QColor(self.sector.cor_texto)
        background_name = background.name() if background.isValid() else "#475569"
        foreground_name = foreground.name() if foreground.isValid() else "#ffffff"
        border_width = 3 if self._selected else 1
        self.setStyleSheet(
            f"""
            QFrame#sectorListCard {{
                background: {background_name}; border: {border_width}px solid {foreground_name};
                border-radius: 7px;
            }}
            QLabel#sectorCardName {{ color: {foreground_name}; background: transparent; font-weight: 800; }}
            QLabel#sectorCardState {{ color: {foreground_name}; background: transparent; font-size: 9px; font-weight: 750; }}
            """
        )


class PersonalizationDialog(QDialog):
    tv_settings_changed = Signal(object)
    office_theme_changed = Signal(str)

    def __init__(
        self,
        repository: ProductionRepository,
        config: AppConfig,
        station_id: str,
        *,
        preview_ops: list[OpListDTO] | None = None,
        tv_settings: dict[str, object] | None = None,
        runtime_store: StationRuntimeStore | None = None,
        theme_mode: str | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.repository = repository
        self.config = config
        self.station_id = station_id
        self.runtime_store = runtime_store
        self.preview_ops = list(preview_ops or [])
        self._sectors = self.repository.list_sectors()
        self._initial_tv_settings = normalize_tv_settings(tv_settings or self._read_tv_settings())
        self._initial_theme_mode = (
            self.runtime_store.load_theme_mode(theme_mode or config.theme_mode)
            if self.runtime_store is not None
            else str(theme_mode or config.theme_mode or "system")
        )
        self._updating_tv_controls = False
        self._screen_fitted = False
        self._large_preview: TvFocusWindow | None = None
        self.setWindowTitle("Personalização")
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)
        self.resize(1480, 880)
        self.setMinimumSize(1080, 680)

        self.tabs = QTabWidget(self)
        self._build_sectors_tab()
        self._build_office_appearance_tab()
        self._build_deadlines_tab()
        self._build_tv_tab()
        self._build_email_tab()
        self._build_diagnostics_tab()

        save = QPushButton("Salvar alterações", self)
        save.setObjectName("primaryButton")
        save.setMinimumWidth(150)
        cancel = QPushButton("Cancelar", self)
        cancel.setMinimumWidth(105)
        save.clicked.connect(self._save)
        cancel.clicked.connect(self.reject)
        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(cancel)
        actions.addWidget(save)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 10)
        layout.setSpacing(10)
        layout.addWidget(self.tabs, 1)
        layout.addLayout(actions)
        self._load_sectors()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._screen_fitted:
            return
        self._screen_fitted = True
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        if area.width() < 1540 or area.height() < 920:
            margin = 8
            self.setGeometry(area.adjusted(margin, margin, -margin, -margin))
        else:
            width = min(1500, area.width() - 40)
            height = min(900, area.height() - 40)
            self.resize(width, height)
            self.move(area.center() - self.rect().center())

    def closeEvent(self, event) -> None:
        if self._large_preview is not None:
            self._large_preview.close()
        if hasattr(self, "tv_preview"):
            self.tv_preview._timer.stop()
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # Abas gerais
    # ------------------------------------------------------------------
    def _build_sectors_tab(self) -> None:
        tab = QWidget(self)
        splitter = QSplitter(Qt.Orientation.Horizontal, tab)
        self.sector_list = QListWidget(splitter)
        self.sector_list.setObjectName("sectorList")
        self.sector_list.setMinimumWidth(300)
        self.sector_list.setSpacing(2)
        self.sector_list.currentItemChanged.connect(self._load_selected_sector)

        editor = QFrame(splitter)
        editor.setObjectName("settingsPanel")
        form = QFormLayout(editor)
        form.setContentsMargins(22, 22, 22, 22)
        form.setSpacing(16)
        self.sector_name = QLineEdit(editor)
        self.sector_color = ColorInput("#475569", editor)
        self.sector_text_color = ColorInput("#ffffff", editor)
        self.sector_active = QCheckBox("Exibir este setor nas listas", editor)
        self.sector_order = QSpinBox(editor)
        self.sector_order.setRange(1, 999)
        self.sector_preview = QLabel("Prévia do setor", editor)
        self.sector_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sector_preview.setMinimumHeight(60)
        self.sector_color.color_changed.connect(self._refresh_sector_preview)
        self.sector_text_color.color_changed.connect(self._refresh_sector_preview)
        self.sector_name.textChanged.connect(lambda _value: self._refresh_sector_preview())
        form.addRow("Nome do setor", self.sector_name)

        colors = QWidget(editor)
        colors_layout = QHBoxLayout(colors)
        colors_layout.setContentsMargins(0, 0, 0, 0)
        colors_layout.setSpacing(16)
        background_box = QVBoxLayout()
        background_box.setContentsMargins(0, 0, 0, 0)
        background_box.addWidget(QLabel("Fundo da linha", colors))
        background_box.addWidget(self.sector_color)
        text_box = QVBoxLayout()
        text_box.setContentsMargins(0, 0, 0, 0)
        text_box.addWidget(QLabel("Texto da linha", colors))
        text_box.addWidget(self.sector_text_color)
        colors_layout.addLayout(background_box, 1)
        colors_layout.addLayout(text_box, 1)
        form.addRow("Cores do setor", colors)

        suggest_contrast = QPushButton("Sugerir cor de texto com bom contraste", editor)
        suggest_contrast.clicked.connect(self._suggest_sector_text_contrast)
        form.addRow("", suggest_contrast)
        form.addRow("Ordem", self.sector_order)
        form.addRow("", self.sector_active)
        form.addRow("Como aparecerá", self.sector_preview)
        actions = QHBoxLayout()
        add = QPushButton("Novo setor", editor)
        save = QPushButton("Salvar setor", editor)
        delete = QPushButton("Excluir setor", editor)
        save.setObjectName("primaryButton")
        add.clicked.connect(self._add_sector)
        save.clicked.connect(self._save_sector)
        delete.clicked.connect(self._delete_sector)
        actions.addWidget(add)
        actions.addWidget(save)
        actions.addWidget(delete)
        actions.addStretch(1)
        form.addRow(actions)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        layout = QVBoxLayout(tab)
        note = QLabel(
            "A ordem, o nome, a cor de fundo e a cor do texto são compartilhados entre os PCs "
            "do Escritório e a estação TV/Foco."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addWidget(splitter, 1)
        self.tabs.addTab(tab, "Setores")

    def _build_office_appearance_tab(self) -> None:
        tab = QWidget(self)
        form = QFormLayout(tab)
        form.setContentsMargins(24, 24, 24, 24)
        form.setSpacing(16)
        self.office_theme = QComboBox(tab)
        self.office_theme.addItem("Seguir o tema do Windows", "system")
        self.office_theme.addItem("Modo claro", "light")
        self.office_theme.addItem("Modo escuro", "dark")
        index = self.office_theme.findData(self._initial_theme_mode)
        self.office_theme.setCurrentIndex(index if index >= 0 else 0)
        form.addRow("Tema do Kanban Escritório", self.office_theme)
        note = QLabel(
            "A escolha é salva somente neste computador e é aplicada imediatamente ao salvar. "
            "Ela não altera as cores, as colunas ou o layout compartilhado da TV/Foco.",
            tab,
        )
        note.setObjectName("helpText")
        note.setWordWrap(True)
        form.addRow("", note)
        form.addRow("", QLabel("Escolha Modo claro para ambientes bem iluminados ou Modo escuro para reduzir o brilho visual.", tab))
        form.addRow("", QWidget(tab))
        self.tabs.addTab(tab, "Escritório")

    def _build_deadlines_tab(self) -> None:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)
        note = QLabel(
            "A cor normal vem do setor. As duas faixas de prazo substituem essa cor em qualquer setor: "
            "atenção (rosa) e crítico (vermelho). O status nunca define a cor."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        panel = QFrame(tab)
        panel.setObjectName("settingsPanel")
        form = QFormLayout(panel)
        form.setContentsMargins(22, 22, 22, 22)
        form.setSpacing(16)
        self.warning_color = ColorInput(str(self.repository.get_setting("deadline.warning_color", "#f9a8d4")), panel)
        self.critical_color = ColorInput(str(self.repository.get_setting("deadline.critical_color", "#ef4444")), panel)
        self.warning_days = QSpinBox(panel)
        self.warning_days.setRange(1, 365)
        self.warning_days.setSuffix(" dias")
        self.warning_days.setValue(int(self.repository.get_setting("deadline.warning_days", 14)))
        self.critical_days = QSpinBox(panel)
        self.critical_days.setRange(0, 364)
        self.critical_days.setSuffix(" dias")
        self.critical_days.setValue(int(self.repository.get_setting("deadline.critical_days", 7)))
        self.warning_preview = QLabel("OP com entrega entre 8 e 14 dias", panel)
        self.critical_preview = QLabel("OP com entrega em 7 dias ou menos", panel)
        for preview in (self.warning_preview, self.critical_preview):
            preview.setMinimumHeight(60)
            preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.warning_color.color_changed.connect(self._refresh_deadline_previews)
        self.critical_color.color_changed.connect(self._refresh_deadline_previews)
        self.warning_days.valueChanged.connect(self._refresh_deadline_previews)
        self.critical_days.valueChanged.connect(self._refresh_deadline_previews)
        form.addRow("Iniciar atenção em", self.warning_days)
        form.addRow("Iniciar crítico em", self.critical_days)
        form.addRow("Cor de atenção", self.warning_color)
        form.addRow("Prévia", self.warning_preview)
        form.addRow("Cor crítica", self.critical_color)
        form.addRow("Prévia", self.critical_preview)
        layout.addWidget(panel)
        layout.addStretch(1)
        self._refresh_deadline_previews()
        self.tabs.addTab(tab, "Prazos e cores")

    # ------------------------------------------------------------------
    # TV/Foco
    # ------------------------------------------------------------------
    def _build_tv_tab(self) -> None:
        tab = QWidget(self)
        settings = self._initial_tv_settings
        root = QVBoxLayout(tab)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)
        description = QLabel(
            "Personalize exatamente o que será exibido na TV. Cada página usa toda a área disponível; "
            "se houver menos OPs que o limite, somente as linhas existentes crescem proporcionalmente."
        )
        description.setWordWrap(True)
        description.setObjectName("helpText")
        root.addWidget(description)

        splitter = QSplitter(Qt.Orientation.Horizontal, tab)
        splitter.setChildrenCollapsible(False)
        left = QFrame(splitter)
        left.setObjectName("settingsPanel")
        left.setMinimumWidth(480)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(10, 10, 10, 10)
        left_layout.setSpacing(8)
        self.tv_control_tabs = QTabWidget(left)
        self.tv_control_tabs.addTab(self._build_tv_page_controls(settings), "Página")
        self.tv_control_tabs.addTab(self._build_tv_columns_controls(settings), "Colunas")
        self.tv_control_tabs.addTab(self._build_tv_labels_controls(settings), "Textos e datas")
        self.tv_control_tabs.addTab(self._build_tv_sector_controls(settings), "Setores")
        self.tv_control_tabs.addTab(self._build_tv_colors_controls(settings), "Visual")
        left_layout.addWidget(self.tv_control_tabs, 1)

        preview_panel = QFrame(splitter)
        preview_panel.setObjectName("settingsPanel")
        preview_panel.setMinimumWidth(360)
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(10, 10, 10, 10)
        preview_layout.setSpacing(7)
        preview_title = QLabel("Prévia real da TV/Foco", preview_panel)
        preview_title.setObjectName("dialogTitle")
        preview_layout.addWidget(preview_title)
        preview_note = QLabel(
            "A prévia usa o mesmo componente, as mesmas cores, formatos, larguras e paginação da TV real. "
            "Arraste as divisórias do cabeçalho para ajustar larguras visualmente."
        )
        preview_note.setWordWrap(True)
        preview_note.setObjectName("helpText")
        preview_layout.addWidget(preview_note)
        self.tv_preview = TvFocusWindow(settings=settings, editable_columns=True, parent=preview_panel)
        self.tv_preview.setMinimumSize(480, 380)
        self.tv_preview.column_widths_changed.connect(self._preview_widths_changed)
        preview_layout.addWidget(self.tv_preview, 1)
        preview_actions = QHBoxLayout()
        previous = QPushButton("◀ Página anterior", preview_panel)
        next_page = QPushButton("Próxima página ▶", preview_panel)
        enlarge = QPushButton("Abrir prévia ampliada", preview_panel)
        previous.clicked.connect(self._preview_previous_page)
        next_page.clicked.connect(self._preview_next_page)
        enlarge.clicked.connect(self._open_large_preview)
        preview_actions.addWidget(previous)
        preview_actions.addWidget(next_page)
        preview_actions.addStretch(1)
        preview_actions.addWidget(enlarge)
        preview_layout.addLayout(preview_actions)
        self.tv_preview_info = QLabel(preview_panel)
        self.tv_preview_info.setObjectName("helpText")
        self.tv_preview_info.setWordWrap(True)
        preview_layout.addWidget(self.tv_preview_info)

        splitter.addWidget(left)
        splitter.addWidget(preview_panel)
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 4)
        splitter.setSizes([760, 650])
        root.addWidget(splitter, 1)
        self.tabs.addTab(tab, "TV/Foco")
        self._refresh_tv_preview()

    def _build_tv_page_controls(self, settings: dict[str, object]) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        page_group = QGroupBox("Paginação", page)
        form = QFormLayout(page_group)
        form.setSpacing(12)
        self.tv_interval = QSpinBox(page_group)
        self.tv_interval.setRange(2, 300)
        self.tv_interval.setSuffix(" s")
        self.tv_interval.setValue(int(settings["page_interval_seconds"]))
        self.tv_interval.setToolTip("Tempo que cada página permanece visível antes de trocar automaticamente.")
        self.tv_lines = QSpinBox(page_group)
        self.tv_lines.setRange(1, 30)
        self.tv_lines.setSuffix(" OPs")
        self.tv_lines.setValue(int(settings["lines_per_page"]))
        self.tv_lines.setToolTip(
            "Quantidade máxima por página. Se a página tiver menos OPs, elas aumentam para ocupar toda a altura."
        )
        form.addRow("Trocar página a cada", self.tv_interval)
        form.addRow("Máximo por página", self.tv_lines)
        layout.addWidget(page_group)

        text_group = QGroupBox("Texto, cabeçalho e espaço", page)
        text_form = QFormLayout(text_group)
        text_form.setSpacing(12)
        self.tv_font = QSpinBox(text_group)
        self.tv_font.setRange(50, 250)
        self.tv_font.setSuffix(" %")
        self.tv_font.setValue(int(settings["font_scale_percent"]))
        self.tv_font.setToolTip("Escala geral do texto dentro das linhas. Cada coluna ainda pode ter sua própria escala.")
        self.tv_header_scale = QSpinBox(text_group)
        self.tv_header_scale.setRange(50, 250)
        self.tv_header_scale.setSuffix(" %")
        self.tv_header_scale.setValue(int(settings["header_scale_percent"]))
        self.tv_header_scale.setToolTip("Aumenta ou reduz apenas o texto do cabeçalho.")
        self.tv_header_height = QSpinBox(text_group)
        self.tv_header_height.setRange(28, 140)
        self.tv_header_height.setSuffix(" px")
        self.tv_header_height.setValue(int(settings["header_height_px"]))
        self.tv_header_height.setToolTip("Altura fixa da faixa do cabeçalho na TV.")
        self.tv_padding = QSpinBox(text_group)
        self.tv_padding.setRange(0, 24)
        self.tv_padding.setSuffix(" px")
        self.tv_padding.setValue(int(settings["cell_padding_px"]))
        self.tv_padding.setToolTip("Espaço lateral dentro de cada célula.")
        self.tv_bold = QCheckBox("Texto das linhas em negrito", text_group)
        self.tv_bold.setChecked(bool(settings["bold_rows"]))
        text_form.addRow("Escala das linhas", self.tv_font)
        text_form.addRow("Escala do cabeçalho", self.tv_header_scale)
        text_form.addRow("Altura do cabeçalho", self.tv_header_height)
        text_form.addRow("Espaço interno", self.tv_padding)
        text_form.addRow("", self.tv_bold)
        layout.addWidget(text_group)

        preset_group = QGroupBox("Modelos rápidos", page)
        preset_layout = QHBoxLayout(preset_group)
        self.tv_preset = QComboBox(preset_group)
        self.tv_preset.addItem("Completo — mais informações", "complete")
        self.tv_preset.addItem("Compacto — mais colunas", "compact")
        self.tv_preset.addItem("Produção — leitura rápida", "production")
        apply_preset = QPushButton("Aplicar modelo", preset_group)
        apply_preset.clicked.connect(self._apply_tv_preset)
        preset_layout.addWidget(self.tv_preset, 1)
        preset_layout.addWidget(apply_preset)
        layout.addWidget(preset_group)
        layout.addStretch(1)

        for widget in (self.tv_interval, self.tv_lines, self.tv_font, self.tv_header_scale, self.tv_header_height, self.tv_padding):
            widget.valueChanged.connect(self._refresh_tv_preview)
        self.tv_bold.toggled.connect(self._refresh_tv_preview)
        return page

    def _build_tv_columns_controls(self, settings: dict[str, object]) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        help_text = QLabel(
            "Marque o que aparece, defina o título exato do cabeçalho, largura proporcional, tamanho, alinhamento e formato. "
            "Exemplo: somente Voltagem pode usar o título “Volt”, sem abreviar nenhuma outra coluna."
        )
        help_text.setWordWrap(True)
        help_text.setObjectName("helpText")
        layout.addWidget(help_text)

        self.tv_columns = QTableWidget(0, 6, page)
        self.tv_columns.setHorizontalHeaderLabels(
            ("Exibir", "Coluna", "Título exibido", "Largura (peso)", "Texto (%)", "Alinhamento")
        )
        self.tv_columns.verticalHeader().setVisible(False)
        self.tv_columns.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tv_columns.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tv_columns.setAlternatingRowColors(True)
        self.tv_columns.setShowGrid(True)
        self.tv_columns.setMinimumHeight(430)
        header = self.tv_columns.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        for index in (3, 4, 5):
            header.setSectionResizeMode(index, QHeaderView.ResizeMode.ResizeToContents)
        rows = []
        for key in settings["column_order"]:
            rows.append(
                {
                    "key": key,
                    "visible": key in settings["visible_columns"],
                    "header": settings["column_headers"][key],
                    "width": settings["column_widths"][key],
                    "font": settings["column_font_scales"][key],
                    "alignment": settings["column_alignments"][key],
                    "format": settings["column_formats"][key],
                }
            )
        self._populate_tv_columns(rows)
        layout.addWidget(self.tv_columns, 1)

        row1 = QHBoxLayout()
        mark_all = QPushButton("Marcar todas", page)
        unmark = QPushButton("Só OP", page)
        up = QPushButton("Subir", page)
        down = QPushButton("Descer", page)
        mark_all.clicked.connect(lambda: self._set_all_columns_visible(True))
        unmark.clicked.connect(lambda: self._set_all_columns_visible(False))
        up.clicked.connect(lambda: self._move_tv_column(-1))
        down.clicked.connect(lambda: self._move_tv_column(1))
        row1.addWidget(mark_all)
        row1.addWidget(unmark)
        row1.addStretch(1)
        row1.addWidget(up)
        row1.addWidget(down)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        equalize = QPushButton("Igualar larguras", page)
        reset = QPushButton("Restaurar padrão", page)
        equalize.clicked.connect(self._equalize_tv_widths)
        reset.clicked.connect(self._reset_tv_columns)
        row2.addWidget(equalize)
        row2.addWidget(reset)
        row2.addStretch(1)
        layout.addLayout(row2)
        return page

    def _build_tv_labels_controls(self, settings: dict[str, object]) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        note = QLabel(
            "Esses textos alteram somente o conteúdo das células. Use o campo “Título exibido” na aba Colunas para mudar o cabeçalho. "
            "Cada status e cada setor podem ter seu próprio texto, sem abreviação global."
        )
        note.setWordWrap(True)
        note.setObjectName("helpText")
        layout.addWidget(note)

        date_group = QGroupBox("Formato individual das datas", page)
        date_form = QFormLayout(date_group)
        self.tv_start_date_format = QComboBox(date_group)
        self.tv_delivery_date_format = QComboBox(date_group)
        for combo, key in ((self.tv_start_date_format, "inicio"), (self.tv_delivery_date_format, "entrega")):
            for label, value in _DATE_FORMAT_OPTIONS:
                combo.addItem(label, value)
            combo.setCurrentIndex(max(0, combo.findData(settings["column_formats"][key])))
            combo.currentIndexChanged.connect(self._refresh_tv_preview)
        date_form.addRow("Coluna Início", self.tv_start_date_format)
        date_form.addRow("Coluna Entrega", self.tv_delivery_date_format)
        layout.addWidget(date_group)

        label_tabs = QTabWidget(page)
        self.tv_labels_tabs = label_tabs

        status_page = QWidget(label_tabs)
        status_layout = QVBoxLayout(status_page)
        status_layout.setContentsMargins(6, 6, 6, 6)
        self.tv_status_labels = QTableWidget(0, 2, status_page)
        self.tv_status_labels.setHorizontalHeaderLabels(("Status original", "Texto mostrado na TV"))
        self.tv_status_labels.verticalHeader().setVisible(False)
        self.tv_status_labels.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.tv_status_labels.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for key, original in TV_DEFAULT_STATUS_LABELS.items():
            row = self.tv_status_labels.rowCount()
            self.tv_status_labels.insertRow(row)
            original_item = QTableWidgetItem(original)
            original_item.setData(Qt.ItemDataRole.UserRole, key)
            original_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.tv_status_labels.setItem(row, 0, original_item)
            edit = QLineEdit(str(settings["status_labels"].get(key, original)), self.tv_status_labels)
            edit.setPlaceholderText(original)
            edit.textChanged.connect(self._refresh_tv_preview)
            self.tv_status_labels.setCellWidget(row, 1, edit)
            self.tv_status_labels.setRowHeight(row, 44)
        status_layout.addWidget(self.tv_status_labels)
        label_tabs.addTab(status_page, "Status")

        sector_page = QWidget(label_tabs)
        sector_layout = QVBoxLayout(sector_page)
        sector_layout.setContentsMargins(6, 6, 6, 6)
        self.tv_sector_labels = QTableWidget(0, 2, sector_page)
        self.tv_sector_labels.setHorizontalHeaderLabels(("Setor original", "Texto mostrado na TV"))
        self.tv_sector_labels.verticalHeader().setVisible(False)
        self.tv_sector_labels.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.tv_sector_labels.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        sector_layout.addWidget(self.tv_sector_labels)
        label_tabs.addTab(sector_page, "Setores")
        layout.addWidget(label_tabs, 1)
        reset = QPushButton("Restaurar todos os nomes completos", page)
        reset.clicked.connect(self._reset_tv_labels)
        layout.addWidget(reset, 0, Qt.AlignmentFlag.AlignLeft)
        return page

    def _build_tv_sector_controls(self, settings: dict[str, object]) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        note = QLabel(
            "Escolha se a TV mostra todos os setores ativos ou somente os marcados. Esta configuração é compartilhada com a estação TV."
        )
        note.setWordWrap(True)
        note.setObjectName("helpText")
        layout.addWidget(note)
        self.tv_sector_mode = QComboBox(page)
        self.tv_sector_mode.addItem("Todos os setores ativos", "all")
        self.tv_sector_mode.addItem("Somente os setores selecionados", "selected")
        index = self.tv_sector_mode.findData(settings["sector_filter_mode"])
        self.tv_sector_mode.setCurrentIndex(max(0, index))
        self.tv_sector_mode.currentIndexChanged.connect(self._toggle_sector_selection)
        self.tv_sector_mode.currentIndexChanged.connect(self._refresh_tv_preview)
        layout.addWidget(self.tv_sector_mode)
        self.tv_sector_checks = QListWidget(page)
        self.tv_sector_checks.setAlternatingRowColors(True)
        self.tv_sector_checks.setMinimumHeight(360)
        layout.addWidget(self.tv_sector_checks, 1)
        actions = QHBoxLayout()
        mark = QPushButton("Marcar todos", page)
        unmark = QPushButton("Desmarcar todos", page)
        mark.clicked.connect(lambda: self._set_all_tv_sectors(True))
        unmark.clicked.connect(lambda: self._set_all_tv_sectors(False))
        actions.addWidget(mark)
        actions.addWidget(unmark)
        actions.addStretch(1)
        layout.addLayout(actions)
        self._tv_sector_mark_button = mark
        self._tv_sector_unmark_button = unmark
        return page

    def _build_tv_colors_controls(self, settings: dict[str, object]) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        note = QLabel(
            "As linhas usam a cor do setor e, nas faixas definidas em Prazos e cores, rosa ou vermelho. Aqui você ajusta somente a estrutura visual da tabela."
        )
        note.setWordWrap(True)
        note.setObjectName("helpText")
        layout.addWidget(note)
        panel = QGroupBox("Cabeçalho, tela e divisões", page)
        form = QFormLayout(panel)
        form.setSpacing(14)
        self.tv_header_background = ColorInput(str(settings["header_background"]), panel)
        self.tv_header_foreground = ColorInput(str(settings["header_foreground"]), panel)
        self.tv_screen_background = ColorInput(str(settings["screen_background"]), panel)
        self.tv_grid_color = ColorInput(str(settings["grid_color"]), panel)
        self.tv_show_grid = QCheckBox("Mostrar divisões entre células", panel)
        self.tv_show_grid.setChecked(bool(settings["show_grid"]))
        form.addRow("Fundo do cabeçalho", self.tv_header_background)
        form.addRow("Texto do cabeçalho", self.tv_header_foreground)
        form.addRow("Fundo da tela", self.tv_screen_background)
        form.addRow("Cor das divisões", self.tv_grid_color)
        form.addRow("", self.tv_show_grid)
        layout.addWidget(panel)
        layout.addStretch(1)
        for color in (
            self.tv_header_background,
            self.tv_header_foreground,
            self.tv_screen_background,
            self.tv_grid_color,
        ):
            color.color_changed.connect(self._refresh_tv_preview)
        self.tv_show_grid.toggled.connect(self._refresh_tv_preview)
        return page

    # ------------------------------------------------------------------
    # E-mail e diagnóstico
    # ------------------------------------------------------------------
    def _build_email_tab(self) -> None:
        tab = QWidget(self)
        form = QFormLayout(tab)
        form.setContentsMargins(24, 24, 24, 24)
        form.setSpacing(16)
        recipients = self.repository.get_setting("deadline.email_recipients", [])
        self.email_recipients = QLineEdit(", ".join(recipients if isinstance(recipients, list) else []), tab)
        self.email_recipients.setPlaceholderText("producao@empresa.com.br, gerente@empresa.com.br")
        self.email_time = QTimeEdit(tab)
        saved_time = str(self.repository.get_setting("deadline.email_hour", "08:00"))
        try:
            hour, minute = (saved_time.split(":") + ["00"])[:2]
            self.email_time.setTime(QTime(int(hour), int(minute)))
        except ValueError:
            self.email_time.setTime(QTime(8, 0))
        form.addRow("Destinatários", self.email_recipients)
        form.addRow("Horário diário", self.email_time)
        help_label = QLabel("O envio só ocorre quando houver OPs nos marcos de 14, 7, 3 ou 0 dias.")
        help_label.setWordWrap(True)
        form.addRow("", help_label)
        self.tabs.addTab(tab, "E-mail")

    def _build_diagnostics_tab(self) -> None:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        self.connection_label = QLabel(tab)
        database = QLabel(f"Banco central: {self.config.database_path}")
        database.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        backups = QLabel(f"Backups de migração: {self.config.backups_dir}")
        backups.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(database)
        layout.addWidget(backups)
        layout.addWidget(QLabel(f"Versão do aplicativo: {__version__}"))
        layout.addWidget(self.connection_label)
        test = QPushButton("Testar conexão agora", tab)
        test.clicked.connect(self._test_connection)
        layout.addWidget(test, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addStretch(1)
        self._test_connection()
        self.tabs.addTab(tab, "Armazenamento")

    # ------------------------------------------------------------------
    # Setores gerais
    # ------------------------------------------------------------------
    def _load_sectors(self) -> None:
        self._sectors = self.repository.list_sectors()
        current_id = None
        if self.sector_list.currentItem() is not None:
            current = self.sector_list.currentItem().data(Qt.ItemDataRole.UserRole)
            current_id = getattr(current, "id", None)
        self.sector_list.clear()
        selected_row = 0
        for row, sector in enumerate(self._sectors):
            item = QListWidgetItem(f"{sector.ordem}. {sector.nome}{'' if sector.ativo else ' (inativo)'}")
            item.setData(Qt.ItemDataRole.UserRole, sector)
            card = SectorListCard(sector, self.sector_list)
            item.setSizeHint(QSize(0, 62))
            self.sector_list.addItem(item)
            self.sector_list.setItemWidget(item, card)
            if sector.id == current_id:
                selected_row = row
        if self.sector_list.count():
            self.sector_list.setCurrentRow(selected_row)
        if hasattr(self, "tv_sector_labels"):
            self._rebuild_tv_sector_customizations()
            self._refresh_tv_preview()

    def _load_selected_sector(self, item) -> None:
        self._sync_sector_card_selection(item)
        if item is None:
            return
        sector = item.data(Qt.ItemDataRole.UserRole)
        self.sector_name.setText(sector.nome)
        self.sector_color.setText(sector.cor)
        self.sector_text_color.setText(sector.cor_texto)
        self.sector_active.setChecked(sector.ativo)
        self.sector_order.setValue(sector.ordem)
        self._refresh_sector_preview()

    def _sync_sector_card_selection(self, current_item) -> None:
        for row in range(self.sector_list.count()):
            item = self.sector_list.item(row)
            card = self.sector_list.itemWidget(item)
            if isinstance(card, SectorListCard):
                card.set_selected(item is current_item)

    def _refresh_sector_preview(self, *_args) -> None:
        background_color = QColor(self.sector_color.text())
        foreground_color = QColor(self.sector_text_color.text())
        background = background_color.name() if background_color.isValid() else "#475569"
        foreground = foreground_color.name() if foreground_color.isValid() else "#ffffff"
        self.sector_preview.setText(self.sector_name.text().strip() or "Nome do setor")
        self.sector_preview.setStyleSheet(
            f"background: {background}; color: {foreground}; font-weight: 700; "
            "border: 1px solid rgba(255,255,255,0.22); border-radius: 5px;"
        )

    def _suggest_sector_text_contrast(self) -> None:
        color = QColor(self.sector_color.text())
        if not color.isValid():
            QMessageBox.warning(self, "Cor do setor", "Escolha primeiro uma cor de fundo válida.")
            return
        self.sector_text_color.setText("#111827" if color.lightness() > 150 else "#ffffff")

    def _add_sector(self) -> None:
        name, accepted = QInputDialog.getText(self, "Adicionar setor", "Nome do setor")
        if accepted:
            try:
                self.repository.add_sector(name, "#475569", station_id=self.station_id, cor_texto="#ffffff")
            except ValueError as exc:
                QMessageBox.warning(self, "Setor", str(exc))
            self._load_sectors()

    def _save_sector(self) -> None:
        item = self.sector_list.currentItem()
        if item is None:
            return
        if not self.sector_color.is_valid():
            QMessageBox.warning(self, "Setor", "Informe uma cor de fundo válida no formato #RRGGBB.")
            return
        if not self.sector_text_color.is_valid():
            QMessageBox.warning(self, "Setor", "Informe uma cor de texto válida no formato #RRGGBB.")
            return
        sector = item.data(Qt.ItemDataRole.UserRole)
        try:
            self.repository.update_sector(
                sector.id,
                nome=self.sector_name.text(),
                cor=self.sector_color.text(),
                cor_texto=self.sector_text_color.text(),
                ativo=self.sector_active.isChecked(),
                ordem=self.sector_order.value(),
                station_id=self.station_id,
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Setor", str(exc))
        self._load_sectors()

    def _delete_sector(self) -> None:
        item = self.sector_list.currentItem()
        if item is None:
            return
        source = item.data(Qt.ItemDataRole.UserRole)
        destinations = [sector for sector in self.repository.list_sectors(active_only=True) if sector.id != source.id]
        if not destinations:
            QMessageBox.warning(self, "Excluir setor", "Não existe outro setor ativo para receber as OPs.")
            return
        names = [sector.nome for sector in destinations]
        choice, accepted = QInputDialog.getItem(self, "Excluir setor", "Migrar as OPs para", names, 0, False)
        if not accepted:
            return
        if QMessageBox.question(
            self,
            "Excluir setor",
            f"Migrar as OPs de {source.nome} para {choice} e excluir o setor?",
        ) != QMessageBox.StandardButton.Yes:
            return
        destination = next(sector for sector in destinations if sector.nome == choice)
        self.repository.delete_sector_with_migration(source.id, destination.id, station_id=self.station_id)
        self._load_sectors()

    # ------------------------------------------------------------------
    # Controles TV/Foco
    # ------------------------------------------------------------------
    def _populate_tv_columns(self, rows: list[dict[str, object]]) -> None:
        self._updating_tv_controls = True
        try:
            self.tv_columns.setRowCount(0)
            for data in rows:
                key = str(data["key"])
                row = self.tv_columns.rowCount()
                self.tv_columns.insertRow(row)
                self.tv_columns.setRowHeight(row, 46)
                visible = QTableWidgetItem()
                visible.setData(Qt.ItemDataRole.UserRole, key)
                visible.setFlags(
                    Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable
                )
                visible.setCheckState(Qt.CheckState.Checked if bool(data["visible"]) else Qt.CheckState.Unchecked)
                if key == "op":
                    visible.setFlags(visible.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
                    visible.setCheckState(Qt.CheckState.Checked)
                    visible.setToolTip("A coluna OP permanece visível para identificar cada linha.")
                name = QTableWidgetItem(TV_COLUMN_LABELS[key])
                name.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                header_edit = QLineEdit(str(data["header"]), self.tv_columns)
                header_edit.setToolTip("Texto exato que aparecerá no cabeçalho desta coluna. Ex.: V, Volt ou Voltagem.")
                header_edit.setPlaceholderText(TV_COLUMN_LABELS[key])
                header_edit.setToolTip("Texto exato que aparecerá no cabeçalho desta coluna.")
                width = QSpinBox(self.tv_columns)
                width.setRange(20, 5000)
                width.setValue(int(data["width"]))
                width.setToolTip("Peso relativo da largura. Aumente para dar mais espaço a esta coluna; a TV redistribui toda a tela proporcionalmente.")
                width.setToolTip("Peso proporcional. Peso 200 ocupa o dobro da largura de peso 100.")
                font_scale = QSpinBox(self.tv_columns)
                font_scale.setRange(50, 250)
                font_scale.setSuffix(" %")
                font_scale.setValue(int(data["font"]))
                font_scale.setToolTip("Tamanho do texto somente nesta coluna, relativo à escala geral das linhas.")
                font_scale.setToolTip("Tamanho do texto somente desta coluna.")
                alignment = QComboBox(self.tv_columns)
                alignment.setToolTip("Alinhamento do cabeçalho e do conteúdo desta coluna.")
                for label, value in _ALIGNMENT_OPTIONS:
                    alignment.addItem(label, value)
                alignment.setCurrentIndex(max(0, alignment.findData(data["alignment"])))
                for widget_signal in (
                    header_edit.textChanged,
                    width.valueChanged,
                    font_scale.valueChanged,
                    alignment.currentIndexChanged,
                ):
                    widget_signal.connect(self._refresh_tv_preview)
                self.tv_columns.setItem(row, 0, visible)
                self.tv_columns.setItem(row, 1, name)
                self.tv_columns.setCellWidget(row, 2, header_edit)
                self.tv_columns.setCellWidget(row, 3, width)
                self.tv_columns.setCellWidget(row, 4, font_scale)
                self.tv_columns.setCellWidget(row, 5, alignment)
        finally:
            self._updating_tv_controls = False
        if not getattr(self, "_tv_column_signal_connected", False):
            self.tv_columns.itemChanged.connect(self._column_item_changed)
            self._tv_column_signal_connected = True

    def _column_item_changed(self, _item) -> None:
        self._refresh_tv_preview()

    def _collect_column_rows(self) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for row in range(self.tv_columns.rowCount()):
            item = self.tv_columns.item(row, 0)
            key = str(item.data(Qt.ItemDataRole.UserRole))
            rows.append(
                {
                    "key": key,
                    "visible": item.checkState() == Qt.CheckState.Checked,
                    "header": self.tv_columns.cellWidget(row, 2).text().strip() or TV_COLUMN_LABELS[key],
                    "width": self.tv_columns.cellWidget(row, 3).value(),
                    "font": self.tv_columns.cellWidget(row, 4).value(),
                    "alignment": self.tv_columns.cellWidget(row, 5).currentData(),
                    "format": (
                        self.tv_start_date_format.currentData() if key == "inicio" and hasattr(self, "tv_start_date_format")
                        else self.tv_delivery_date_format.currentData() if key == "entrega" and hasattr(self, "tv_delivery_date_format")
                        else "text"
                    ),
                }
            )
        return rows

    def _move_tv_column(self, direction: int) -> None:
        row = self.tv_columns.currentRow()
        target = row + direction
        if row < 0 or target < 0 or target >= self.tv_columns.rowCount():
            return
        rows = self._collect_column_rows()
        rows[row], rows[target] = rows[target], rows[row]
        self._populate_tv_columns(rows)
        self.tv_columns.selectRow(target)
        self._refresh_tv_preview()

    def _set_all_columns_visible(self, checked: bool) -> None:
        self._updating_tv_controls = True
        try:
            for row in range(self.tv_columns.rowCount()):
                item = self.tv_columns.item(row, 0)
                key = str(item.data(Qt.ItemDataRole.UserRole))
                item.setCheckState(Qt.CheckState.Checked if checked or key == "op" else Qt.CheckState.Unchecked)
        finally:
            self._updating_tv_controls = False
        self._refresh_tv_preview()

    def _equalize_tv_widths(self) -> None:
        self._updating_tv_controls = True
        try:
            for row in range(self.tv_columns.rowCount()):
                if self.tv_columns.item(row, 0).checkState() == Qt.CheckState.Checked:
                    self.tv_columns.cellWidget(row, 3).setValue(100)
        finally:
            self._updating_tv_controls = False
        self._refresh_tv_preview()

    def _reset_tv_columns(self) -> None:
        defaults = default_tv_settings()
        rows = []
        for key in defaults["column_order"]:
            rows.append(
                {
                    "key": key,
                    "visible": key in defaults["visible_columns"],
                    "header": defaults["column_headers"][key],
                    "width": defaults["column_widths"][key],
                    "font": defaults["column_font_scales"][key],
                    "alignment": defaults["column_alignments"][key],
                    "format": defaults["column_formats"][key],
                }
            )
        self._populate_tv_columns(rows)
        if hasattr(self, "tv_start_date_format"):
            self.tv_start_date_format.setCurrentIndex(max(0, self.tv_start_date_format.findData(defaults["column_formats"]["inicio"])))
            self.tv_delivery_date_format.setCurrentIndex(max(0, self.tv_delivery_date_format.findData(defaults["column_formats"]["entrega"])))
        self._refresh_tv_preview()

    def _apply_tv_preset(self) -> None:
        preset = self.tv_preset.currentData()
        rows = self._collect_column_rows()
        by_key = {row["key"]: row for row in rows}
        defaults = default_tv_settings()
        if preset == "complete":
            visible = {"op", "status", "cliente", "modelo", "voltagem", "quantidade", "inicio", "entrega", "setor"}
            headers = dict(defaults["column_headers"])
            formats = {"inicio": "dd/MM/yyyy", "entrega": "dd/MM/yyyy"}
            lines, font = 8, 95
        elif preset == "compact":
            visible = {"op", "status", "cliente", "modelo", "voltagem", "quantidade", "entrega", "setor"}
            headers = {
                "op": "OP", "status": "Status", "cliente": "Cliente", "modelo": "Modelo",
                "voltagem": "V", "quantidade": "Qtd", "inicio": "Início", "entrega": "Ent.",
                "setor": "Set.", "pendencia": "Pend."
            }
            formats = {"inicio": "dd/MM", "entrega": "dd/MM"}
            lines, font = 10, 100
        else:
            visible = {"op", "cliente", "modelo", "quantidade", "entrega", "setor"}
            headers = {
                "op": "OP", "status": "Status", "cliente": "Cliente", "modelo": "Modelo",
                "voltagem": "Volt", "quantidade": "Qtd", "inicio": "Início", "entrega": "Entrega",
                "setor": "Setor", "pendencia": "Pendência"
            }
            formats = {"inicio": "dd/MM/yyyy", "entrega": "dd/MM/yyyy"}
            lines, font = 10, 105
        for key, row in by_key.items():
            row["visible"] = key in visible
            row["header"] = headers.get(key, TV_COLUMN_LABELS[key])
            if key in formats:
                row["format"] = formats[key]
        ordered = [by_key[key] for key in defaults["column_order"]]
        self._populate_tv_columns(ordered)
        if hasattr(self, "tv_start_date_format"):
            self.tv_start_date_format.setCurrentIndex(max(0, self.tv_start_date_format.findData(formats.get("inicio", "dd/MM/yyyy"))))
            self.tv_delivery_date_format.setCurrentIndex(max(0, self.tv_delivery_date_format.findData(formats.get("entrega", "dd/MM/yyyy"))))
        self.tv_lines.setValue(lines)
        self.tv_font.setValue(font)
        self._refresh_tv_preview()

    def _reset_tv_labels(self) -> None:
        for row in range(self.tv_status_labels.rowCount()):
            original = self.tv_status_labels.item(row, 0).text()
            self.tv_status_labels.cellWidget(row, 1).setText(original)
        for row in range(self.tv_sector_labels.rowCount()):
            original = self.tv_sector_labels.item(row, 0).text()
            self.tv_sector_labels.cellWidget(row, 1).setText(original)
        self._refresh_tv_preview()

    def _current_sector_label_values(self) -> dict[str, str]:
        if not hasattr(self, "tv_sector_labels"):
            return dict(self._initial_tv_settings.get("sector_labels", {}))
        result: dict[str, str] = {}
        for row in range(self.tv_sector_labels.rowCount()):
            item = self.tv_sector_labels.item(row, 0)
            sector_id = str(item.data(Qt.ItemDataRole.UserRole))
            value = self.tv_sector_labels.cellWidget(row, 1).text().strip()
            if value and value != item.text():
                result[sector_id] = value
        return result

    def _current_selected_sector_ids(self) -> set[str]:
        if not hasattr(self, "tv_sector_checks"):
            return set(self._initial_tv_settings.get("visible_sector_ids", []))
        result = set()
        for row in range(self.tv_sector_checks.count()):
            item = self.tv_sector_checks.item(row)
            if item.checkState() == Qt.CheckState.Checked:
                result.add(str(item.data(Qt.ItemDataRole.UserRole)))
        return result

    def _rebuild_tv_sector_customizations(self) -> None:
        existing_labels = self._current_sector_label_values()
        existing_selected = self._current_selected_sector_ids()
        if not existing_labels:
            existing_labels = dict(self._initial_tv_settings.get("sector_labels", {}))
        if not existing_selected:
            existing_selected = set(self._initial_tv_settings.get("visible_sector_ids", []))
        self._updating_tv_controls = True
        try:
            self.tv_sector_labels.setRowCount(0)
            self.tv_sector_checks.clear()
            for sector in self._sectors:
                if not sector.ativo:
                    continue
                row = self.tv_sector_labels.rowCount()
                self.tv_sector_labels.insertRow(row)
                original = QTableWidgetItem(sector.nome)
                original.setData(Qt.ItemDataRole.UserRole, sector.id)
                original.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                self.tv_sector_labels.setItem(row, 0, original)
                edit = QLineEdit(existing_labels.get(sector.id, sector.nome), self.tv_sector_labels)
                edit.setPlaceholderText(sector.nome)
                edit.textChanged.connect(self._refresh_tv_preview)
                self.tv_sector_labels.setCellWidget(row, 1, edit)
                self.tv_sector_labels.setRowHeight(row, 44)
                check_item = QListWidgetItem(sector.nome)
                check_item.setData(Qt.ItemDataRole.UserRole, sector.id)
                check_item.setFlags(check_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                checked = not existing_selected or sector.id in existing_selected
                check_item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
                check_item.setForeground(QColor(sector.cor))
                self.tv_sector_checks.addItem(check_item)
        finally:
            self._updating_tv_controls = False
        if not getattr(self, "_tv_sector_signal_connected", False):
            self.tv_sector_checks.itemChanged.connect(self._sector_check_changed)
            self._tv_sector_signal_connected = True
        self._toggle_sector_selection()

    def _sector_check_changed(self, _item) -> None:
        self._refresh_tv_preview()

    def _toggle_sector_selection(self, *_args) -> None:
        if not hasattr(self, "tv_sector_mode"):
            return
        selected_mode = self.tv_sector_mode.currentData() == "selected"
        self.tv_sector_checks.setEnabled(selected_mode)
        self._tv_sector_mark_button.setEnabled(selected_mode)
        self._tv_sector_unmark_button.setEnabled(selected_mode)

    def _set_all_tv_sectors(self, checked: bool) -> None:
        self._updating_tv_controls = True
        try:
            for row in range(self.tv_sector_checks.count()):
                self.tv_sector_checks.item(row).setCheckState(
                    Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
                )
        finally:
            self._updating_tv_controls = False
        self._refresh_tv_preview()

    def _current_status_labels(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for row in range(self.tv_status_labels.rowCount()):
            item = self.tv_status_labels.item(row, 0)
            key = str(item.data(Qt.ItemDataRole.UserRole))
            result[key] = self.tv_status_labels.cellWidget(row, 1).text().strip() or item.text()
        return result

    def _current_tv_settings(self) -> dict[str, object]:
        rows = self._collect_column_rows()
        visible = [str(row["key"]) for row in rows if bool(row["visible"])]
        order = [str(row["key"]) for row in rows]
        values = {
            "visible_columns": visible,
            "column_order": order,
            "column_widths": {str(row["key"]): int(row["width"]) for row in rows},
            "column_font_scales": {str(row["key"]): int(row["font"]) for row in rows},
            "column_headers": {str(row["key"]): str(row["header"]) for row in rows},
            "column_alignments": {str(row["key"]): str(row["alignment"]) for row in rows},
            "column_formats": {str(row["key"]): str(row["format"]) for row in rows},
            "sector_labels": self._current_sector_label_values(),
            "status_labels": self._current_status_labels(),
            "sector_filter_mode": self.tv_sector_mode.currentData(),
            "visible_sector_ids": sorted(self._current_selected_sector_ids()),
            "page_interval_seconds": self.tv_interval.value(),
            "lines_per_page": self.tv_lines.value(),
            "font_scale_percent": self.tv_font.value(),
            "header_scale_percent": self.tv_header_scale.value(),
            "header_height_px": self.tv_header_height.value(),
            "cell_padding_px": self.tv_padding.value(),
            "bold_rows": self.tv_bold.isChecked(),
            "show_grid": self.tv_show_grid.isChecked(),
            "header_background": self.tv_header_background.text(),
            "header_foreground": self.tv_header_foreground.text(),
            "screen_background": self.tv_screen_background.text(),
            "grid_color": self.tv_grid_color.text(),
        }
        return normalize_tv_settings(values)

    def _preview_ops_with_current_sectors(self) -> list[OpListDTO]:
        sectors = {sector.id: sector for sector in self._sectors}
        result = []
        for op in self.preview_ops:
            sector = sectors.get(op.setor_id)
            if sector is None:
                result.append(op)
            else:
                result.append(
                    replace(
                        op,
                        setor_nome=sector.nome,
                        setor_cor=sector.cor,
                        setor_cor_texto=sector.cor_texto,
                    )
                )
        return result

    def _refresh_tv_preview(self, *_args) -> None:
        if not hasattr(self, "tv_preview") or self._updating_tv_controls:
            return
        settings = self._current_tv_settings()
        self.tv_preview.set_deadline_colors(self.warning_color.text(), self.critical_color.text())
        self.tv_preview.set_deadline_rules(
            warning_days=self.warning_days.value(),
            critical_days=min(self.warning_days.value(), self.critical_days.value()),
            eligible_sector_ids=None,
        )
        self.tv_preview.apply_settings(settings)
        self.tv_preview.set_ops(self._preview_ops_with_current_sectors())
        total = len(self.tv_preview._display_ops)
        lines = int(settings["lines_per_page"])
        shown = min(total, lines)
        pages = max(1, (total + lines - 1) // lines) if total else 1
        visible_names = [settings["column_headers"][key] for key in settings["column_order"] if key in settings["visible_columns"]]
        self._tv_preview_base_info = (
            f"{shown} OP(s) nesta página • limite {lines} • {pages} página(s) • "
            f"colunas: {', '.join(visible_names)}. A última página também preenche toda a altura."
        )
        self._update_preview_page_text()
        if self._large_preview is not None and self._large_preview.isVisible():
            self._large_preview.set_deadline_colors(self.warning_color.text(), self.critical_color.text())
            self._large_preview.set_deadline_rules(
                warning_days=self.warning_days.value(),
                critical_days=min(self.warning_days.value(), self.critical_days.value()),
                eligible_sector_ids=None,
            )
            self._large_preview.apply_settings(settings)
            self._large_preview.set_ops(self._preview_ops_with_current_sectors())

    def _preview_widths_changed(self, widths: dict[str, int]) -> None:
        if self._updating_tv_controls:
            return
        self._updating_tv_controls = True
        try:
            for row in range(self.tv_columns.rowCount()):
                key = str(self.tv_columns.item(row, 0).data(Qt.ItemDataRole.UserRole))
                if key in widths and self.tv_columns.item(row, 0).checkState() == Qt.CheckState.Checked:
                    self.tv_columns.cellWidget(row, 3).setValue(int(widths[key]))
        finally:
            self._updating_tv_controls = False
        self._refresh_tv_preview()

    def _preview_previous_page(self) -> None:
        self.tv_preview.previous_page()
        self._update_preview_page_text()

    def _preview_next_page(self) -> None:
        self.tv_preview.next_page()
        self._update_preview_page_text()

    def _update_preview_page_text(self) -> None:
        current = self.tv_preview.current_page + 1
        total = self.tv_preview.page_count
        base = getattr(self, "_tv_preview_base_info", "")
        self.tv_preview_info.setText(f"{base} Página atual: {current}/{total}.")

    def _open_large_preview(self) -> None:
        settings = self._current_tv_settings()
        if self._large_preview is None:
            self._large_preview = TvFocusWindow(settings=settings, editable_columns=False)
            self._large_preview.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self._large_preview.set_deadline_colors(self.warning_color.text(), self.critical_color.text())
        self._large_preview.set_deadline_rules(
            warning_days=self.warning_days.value(),
            critical_days=min(self.warning_days.value(), self.critical_days.value()),
            eligible_sector_ids=None,
        )
        self._large_preview.apply_settings(settings)
        self._large_preview.set_ops(self._preview_ops_with_current_sectors())
        self._large_preview.showMaximized()
        self._large_preview.raise_()
        self._large_preview.activateWindow()

    # ------------------------------------------------------------------
    # Prazos e persistência
    # ------------------------------------------------------------------
    def _refresh_deadline_previews(self, *_args) -> None:
        warning_days = self.warning_days.value()
        critical_days = min(warning_days, self.critical_days.value())
        self.warning_preview.setText(f"OP com entrega entre {critical_days + 1} e {warning_days} dias")
        self.critical_preview.setText(f"OP com entrega em {critical_days} dias ou menos")
        for field, preview in ((self.warning_color, self.warning_preview), (self.critical_color, self.critical_preview)):
            color = QColor(field.text())
            background = color.name() if color.isValid() else "#475569"
            foreground = "#111827" if color.lightness() > 145 else "#ffffff"
            preview.setStyleSheet(
                f"background: {background}; color: {foreground}; font-weight: 700; border-radius: 5px;"
            )
        if hasattr(self, "tv_preview"):
            self._refresh_tv_preview()

    def _save(self) -> None:
        color_fields = (
            self.warning_color,
            self.critical_color,
            self.tv_header_background,
            self.tv_header_foreground,
            self.tv_screen_background,
            self.tv_grid_color,
        )
        if any(not field.is_valid() for field in color_fields):
            QMessageBox.warning(self, "Cores", "Todas as cores precisam estar no formato válido #RRGGBB.")
            return
        settings = self._current_tv_settings()
        if settings["sector_filter_mode"] == "selected" and not settings["visible_sector_ids"]:
            QMessageBox.warning(
                self,
                "Setores na TV",
                "Selecione pelo menos um setor ou escolha “Todos os setores ativos”.",
            )
            self.tv_control_tabs.setCurrentIndex(3)
            return
        recipients = [value.strip() for value in self.email_recipients.text().split(",") if value.strip()]
        values = {
            "deadline.warning_color": self.warning_color.text(),
            "deadline.critical_color": self.critical_color.text(),
            "deadline.warning_days": self.warning_days.value(),
            "deadline.critical_days": min(self.warning_days.value(), self.critical_days.value()),
            # A regra atual é independente do setor. O valor antigo é limpo para
            # que nenhuma estação mantenha o corte legado em Qualidade.
            "deadline.cutoff_sector_id": None,
            "deadline.email_recipients": recipients,
            "deadline.email_hour": self.email_time.time().toString("HH:mm"),
        }
        values.update({f"tv.{key}": value for key, value in settings.items()})
        try:
            self.repository.set_settings(values, station_id=self.station_id)
        except Exception as exc:
            QMessageBox.warning(self, "Não foi possível salvar", str(exc))
            return
        if self.runtime_store is not None:
            mode = str(self.office_theme.currentData() or "system")
            self.runtime_store.save_theme_mode(mode)
            self.office_theme_changed.emit(mode)
        self.tv_settings_changed.emit(settings)
        self.accept()

    def _read_tv_settings(self) -> dict[str, object]:
        defaults = default_tv_settings()
        keys = [f"tv.{key}" for key in defaults]
        values = self.repository.get_settings(
            keys,
            defaults={f"tv.{key}": value for key, value in defaults.items()},
        )
        return {key: values[f"tv.{key}"] for key in defaults}

    def _test_connection(self) -> None:
        available = self.repository.database.test_connection()
        self.connection_label.setText(
            "Conexão com o NAS: disponível" if available else "Conexão com o NAS: indisponível"
        )
        self.connection_label.setObjectName("successLabel" if available else "errorLabel")
        self.connection_label.style().unpolish(self.connection_label)
        self.connection_label.style().polish(self.connection_label)
