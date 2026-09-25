from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from kanban_app.application.dto import MonthlyOpItemDTO, MonthlyReportSummaryDTO
from kanban_app.application.report_service import MONTH_NAMES, MonthlyReportService
from kanban_app.formatting import format_br_date
from kanban_app.infrastructure.db.repositories import ProductionRepository
from kanban_app.presentation.widgets.chart_widgets import (
    FlowBarChartWidget,
    PunctualityDonutWidget,
    SectorBarChartWidget,
)


class MonthlyReportDialog(QDialog):
    """Janela completa para análise gerencial mensal, gráficos e exportação em PDF/Excel."""

    def __init__(
        self,
        parent: QWidget | None,
        *,
        repository: ProductionRepository,
        initial_year: int | None = None,
        initial_month: int | None = None,
    ):
        super().__init__(parent)
        self.repository = repository
        self.service = MonthlyReportService(repository)

        today = date.today()
        self._current_year = initial_year or today.year
        self._current_month = initial_month or today.month
        self._current_summary: MonthlyReportSummaryDTO | None = None

        self.setWindowTitle("📊 Relatório Mensal de Produção & Gráficos")
        self.resize(1200, 800)
        self.setMinimumSize(980, 680)

        self._build_ui()
        self._load_data()

    def _build_ui(self) -> None:
        self.setStyleSheet(
            """
            QDialog { background-color: #0b1329; color: #f8fafc; font-family: 'Segoe UI', Arial, sans-serif; }
            QLabel { color: #f8fafc; }
            QComboBox, QSpinBox {
                background-color: #1e293b; color: #f8fafc; border: 1px solid #475569;
                border-radius: 6px; padding: 4px 8px; font-weight: bold; min-height: 28px;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background-color: #1e293b; color: #f8fafc; selection-background-color: #2563eb;
            }
            QTabWidget::pane { border: 1px solid #334155; border-radius: 8px; background: #172033; }
            QTabBar::tab {
                background: #1e293b; color: #94a3b8; border: 1px solid #334155;
                padding: 7px 18px; border-top-left-radius: 6px; border-top-right-radius: 6px;
                font-weight: 600; margin-right: 4px;
            }
            QTabBar::tab:selected { background: #2563eb; color: #ffffff; border-color: #2563eb; }
            QTabBar::tab:hover:!selected { background: #334155; color: #f8fafc; }
            QTableWidget {
                background-color: #172033; alternate-background-color: #1e293b;
                gridline-color: #24324a; border: none; color: #f1f5f9;
            }
            QHeaderView::section {
                background-color: #0f172a; color: #94a3b8; font-weight: 700;
                border: none; border-bottom: 2px solid #334155; padding: 6px 8px;
            }
            """
        )

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 16, 18, 16)
        main_layout.setSpacing(12)

        # 1. Barra Superior de Seleção de Período
        period_frame = QFrame(self)
        period_frame.setObjectName("periodFrame")
        period_frame.setStyleSheet(
            "QFrame#periodFrame { background: #172033; border: 1px solid #334155; border-radius: 8px; padding: 4px; }"
        )
        p_layout = QHBoxLayout(period_frame)
        p_layout.setContentsMargins(12, 6, 12, 6)
        p_layout.setSpacing(8)

        lbl_periodo = QLabel("Período de Análise:", period_frame)
        lbl_periodo.setStyleSheet("color: #94a3b8; font-weight: 700; font-size: 10pt;")
        p_layout.addWidget(lbl_periodo)

        self.btn_this_month = QPushButton("📅 Este Mês (em andamento)", period_frame)
        self.btn_prev_month = QPushButton("◀ Mês Anterior", period_frame)
        self.btn_prev_2_months = QPushButton("◀◀ 2 Meses Atrás", period_frame)

        self._period_buttons = [self.btn_this_month, self.btn_prev_month, self.btn_prev_2_months]
        for btn in self._period_buttons:
            btn.setStyleSheet(
                "QPushButton { background: #1e293b; color: #cbd5e1; border: 1px solid #334155; "
                "border-radius: 6px; padding: 6px 14px; font-weight: 600; min-height: 24px; } "
                "QPushButton:hover { background: #334155; color: #ffffff; border-color: #38bdf8; }"
            )
            p_layout.addWidget(btn)

        self.btn_this_month.clicked.connect(self._select_this_month)
        self.btn_prev_month.clicked.connect(self._select_prev_month)
        self.btn_prev_2_months.clicked.connect(self._select_prev_2_months)

        p_layout.addSpacing(8)

        # Comboboxes diretos de Mês e Ano
        self.combo_month = QComboBox(period_frame)
        for i in range(1, 13):
            self.combo_month.addItem(MONTH_NAMES[i], i)
        self.combo_month.setCurrentIndex(self._current_month - 1)
        self.combo_month.currentIndexChanged.connect(self._on_combo_changed)
        p_layout.addWidget(self.combo_month)

        self.spin_year = QSpinBox(period_frame)
        self.spin_year.setRange(2020, 2035)
        self.spin_year.setValue(self._current_year)
        self.spin_year.valueChanged.connect(self._on_combo_changed)
        p_layout.addWidget(self.spin_year)

        p_layout.addStretch(1)

        # Badge de Situação
        self.status_badge = QLabel("", period_frame)
        self.status_badge.setObjectName("statusBadge")
        p_layout.addWidget(self.status_badge)

        main_layout.addWidget(period_frame)

        # 2. Cards de Indicadores (KPIs)
        kpi_layout = QHBoxLayout()
        kpi_layout.setSpacing(10)

        self.card_in = self._create_kpi_card("ENTRADAS NO MÊS", "#3b82f6", "#93c5fd")
        self.card_out = self._create_kpi_card("CONCLUÍDAS", "#10b981", "#86efac")
        self.card_on_time = self._create_kpi_card("ENTREGUE NO PRAZO", "#22c55e", "#4ade80")
        self.card_delayed = self._create_kpi_card("COM ATRASO", "#ef4444", "#fca5a5")
        self.card_in_line = self._create_kpi_card("EM LINHA HOJE", "#f59e0b", "#fde047")

        for c in (self.card_in, self.card_out, self.card_on_time, self.card_delayed, self.card_in_line):
            kpi_layout.addWidget(c)

        main_layout.addLayout(kpi_layout)

        # 3. Painel de Gráficos (3 colunas com fundo escuro harmonioso)
        charts_frame = QFrame(self)
        charts_frame.setObjectName("chartsFrame")
        charts_frame.setStyleSheet(
            "QFrame#chartsFrame { background: #172033; border: 1px solid #334155; border-radius: 8px; }"
        )
        charts_layout = QHBoxLayout(charts_frame)
        charts_layout.setContentsMargins(14, 10, 14, 10)
        charts_layout.setSpacing(16)

        # Coluna 1: Pontualidade
        col1 = QVBoxLayout()
        col1_title = QLabel("🎯 Pontualidade de Entrega", charts_frame)
        col1_title.setStyleSheet("font-weight: 700; color: #f8fafc; font-size: 10pt;")
        col1.addWidget(col1_title)
        self.donut_widget = PunctualityDonutWidget(charts_frame)
        col1.addWidget(self.donut_widget)
        charts_layout.addLayout(col1, 1)

        # Coluna 2: Fluxo Semanal
        col2 = QVBoxLayout()
        col2_header = QHBoxLayout()
        col2_title = QLabel("📊 Fluxo Semanal", charts_frame)
        col2_title.setStyleSheet("font-weight: 700; color: #f8fafc; font-size: 10pt;")
        col2_header.addWidget(col2_title)
        col2_sub = QLabel("<span style='color: #3b82f6;'>■ Entradas</span> &nbsp;&bull;&nbsp; <span style='color: #10b981;'>■ Saídas</span>", charts_frame)
        col2_sub.setStyleSheet("font-size: 8pt; color: #94a3b8; font-weight: 600;")
        col2_header.addStretch(1)
        col2_header.addWidget(col2_sub)
        col2.addLayout(col2_header)
        self.flow_bar_widget = FlowBarChartWidget(charts_frame)
        col2.addWidget(self.flow_bar_widget)
        charts_layout.addLayout(col2, 2)

        # Coluna 3: Distribuição por Setores
        col3 = QVBoxLayout()
        col3_title = QLabel("🏭 OPs por Setor", charts_frame)
        col3_title.setStyleSheet("font-weight: 700; color: #f8fafc; font-size: 10pt;")
        col3.addWidget(col3_title)
        self.sector_bar_widget = SectorBarChartWidget(charts_frame)
        col3.addWidget(self.sector_bar_widget)
        charts_layout.addLayout(col3, 2)

        main_layout.addWidget(charts_frame, 0)

        # 4. Tabela de Detalhamento com Abas
        self.tab_widget = QTabWidget(self)
        self.tab_widget.setObjectName("reportTabs")

        self.table_all = self._create_data_table()
        self.table_on_time = self._create_data_table()
        self.table_delayed = self._create_data_table()
        self.table_in_line = self._create_data_table()

        self.tab_widget.addTab(self.table_all, "Todas as OPs")
        self.tab_widget.addTab(self.table_on_time, "No Prazo")
        self.tab_widget.addTab(self.table_delayed, "Com Atraso")
        self.tab_widget.addTab(self.table_in_line, "Em Produção")

        main_layout.addWidget(self.tab_widget, 1)

        # 5. Barra Inferior de Ações
        bottom_bar = QHBoxLayout()

        self.btn_export_pdf = QPushButton("📄 Exportar Relatório em PDF", self)
        self.btn_export_pdf.setObjectName("primaryButton")
        self.btn_export_pdf.setStyleSheet(
            "QPushButton { background: #2563eb; color: #ffffff; font-weight: bold; "
            "padding: 9px 20px; border-radius: 6px; font-size: 10pt; border: none; } "
            "QPushButton:hover { background: #1d4ed8; }"
        )
        self.btn_export_pdf.clicked.connect(self._export_pdf)
        bottom_bar.addWidget(self.btn_export_pdf)

        self.btn_export_excel = QPushButton("📊 Exportar Planilha Excel (.xlsx)", self)
        self.btn_export_excel.setStyleSheet(
            "QPushButton { background: #16a34a; color: #ffffff; font-weight: bold; "
            "padding: 9px 20px; border-radius: 6px; font-size: 10pt; border: none; } "
            "QPushButton:hover { background: #15803d; }"
        )
        self.btn_export_excel.clicked.connect(self._export_excel)
        bottom_bar.addWidget(self.btn_export_excel)

        bottom_bar.addStretch(1)

        btn_close = QPushButton("Fechar", self)
        btn_close.setStyleSheet(
            "QPushButton { background: #334155; color: #f8fafc; font-weight: 600; "
            "padding: 9px 24px; border-radius: 6px; font-size: 10pt; border: 1px solid #475569; } "
            "QPushButton:hover { background: #475569; }"
        )
        btn_close.clicked.connect(self.accept)
        bottom_bar.addWidget(btn_close)

        main_layout.addLayout(bottom_bar)

    def _create_kpi_card(self, title: str, accent_color: str, sub_color: str) -> QFrame:
        card = QFrame(self)
        card.setObjectName("kpiCard")
        card.setStyleSheet(
            f"QFrame#kpiCard {{ background: #172033; border: 1px solid #334155; "
            f"border-left: 4px solid {accent_color}; border-radius: 6px; padding: 6px; }}"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)

        lbl_title = QLabel(title, card)
        lbl_title.setStyleSheet("color: #94a3b8; font-size: 8pt; font-weight: 700; letter-spacing: 0.5px;")
        layout.addWidget(lbl_title)

        lbl_value = QLabel("0 OPs", card)
        lbl_value.setObjectName("kpiValue")
        lbl_value.setStyleSheet("color: #f8fafc; font-size: 16pt; font-weight: 900;")
        layout.addWidget(lbl_value)

        lbl_sub = QLabel("-", card)
        lbl_sub.setObjectName("kpiSub")
        lbl_sub.setStyleSheet(f"color: {sub_color}; font-size: 8.5pt; font-weight: 600;")
        layout.addWidget(lbl_sub)

        return card

    def _create_data_table(self) -> QTableWidget:
        table = QTableWidget(self)
        table.setColumnCount(10)
        table.setHorizontalHeaderLabels([
            "OP",
            "Cliente",
            "Modelo",
            "Qtd",
            "Setor",
            "Início",
            "Entrega",
            "Conclusão",
            "Ciclo",
            "Situação",
        ])
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        return table

    def _select_this_month(self) -> None:
        today = date.today()
        self.spin_year.setValue(today.year)
        self.combo_month.setCurrentIndex(today.month - 1)
        self._highlight_button(self.btn_this_month)

    def _select_prev_month(self) -> None:
        today = date.today()
        m = today.month - 1
        y = today.year
        if m < 1:
            m = 12
            y -= 1
        self.spin_year.setValue(y)
        self.combo_month.setCurrentIndex(m - 1)
        self._highlight_button(self.btn_prev_month)

    def _select_prev_2_months(self) -> None:
        today = date.today()
        m = today.month - 2
        y = today.year
        while m < 1:
            m += 12
            y -= 1
        self.spin_year.setValue(y)
        self.combo_month.setCurrentIndex(m - 1)
        self._highlight_button(self.btn_prev_2_months)

    def _highlight_button(self, active_btn: QPushButton) -> None:
        for btn in self._period_buttons:
            if btn is active_btn:
                btn.setStyleSheet(
                    "QPushButton { background: #2563eb; color: #ffffff; border: 1px solid #3b82f6; "
                    "border-radius: 6px; padding: 6px 14px; font-weight: bold; min-height: 24px; }"
                )
            else:
                btn.setStyleSheet(
                    "QPushButton { background: #1e293b; color: #cbd5e1; border: 1px solid #334155; "
                    "border-radius: 6px; padding: 6px 14px; font-weight: 600; min-height: 24px; } "
                    "QPushButton:hover { background: #334155; color: #ffffff; border-color: #38bdf8; }"
                )

    def _on_combo_changed(self) -> None:
        self._current_year = self.spin_year.value()
        self._current_month = self.combo_month.currentData()
        self._load_data()

    def _load_data(self) -> None:
        summary = self.service.build_summary(self._current_year, self._current_month)
        self._current_summary = summary

        # Atualiza Badge de Situação
        if summary.is_mes_fechado:
            self.status_badge.setText("● MÊS FECHADO / CONCLUÍDO")
            self.status_badge.setStyleSheet(
                "background: #14532d; color: #86efac; border: 1px solid #166534; padding: 6px 14px; border-radius: 6px; font-weight: bold;"
            )
        else:
            self.status_badge.setText(f"● PARCIAL EM ANDAMENTO (até {format_br_date(summary.data_referencia)})")
            self.status_badge.setStyleSheet(
                "background: #78350f; color: #fde047; border: 1px solid #92400e; padding: 6px 14px; border-radius: 6px; font-weight: bold;"
            )

        # Atualiza Cards de KPI
        ops_in_txt = "1 OP" if summary.total_criadas == 1 else f"{summary.total_criadas} OPs"
        pecas_in_txt = "1 peça" if summary.total_criadas_pecas == 1 else f"{summary.total_criadas_pecas} peças"
        self._update_kpi(self.card_in, ops_in_txt, pecas_in_txt)

        ops_out_txt = "1 OP" if summary.total_concluidas == 1 else f"{summary.total_concluidas} OPs"
        ciclo_txt = f"Ciclo Médio: {summary.lead_time_medio_dias:.1f}d" if summary.total_concluidas > 0 else "Sem saídas"
        self._update_kpi(self.card_out, ops_out_txt, ciclo_txt)

        ops_on_time_txt = "1 OP" if summary.concluidas_no_prazo == 1 else f"{summary.concluidas_no_prazo} OPs"
        pont_txt = f"Pontualidade: {summary.taxa_pontualidade:.1f}%" if summary.total_concluidas > 0 else "N/A"
        self._update_kpi(self.card_on_time, ops_on_time_txt, pont_txt)

        ops_delayed_txt = "1 OP" if summary.concluidas_com_atraso == 1 else f"{summary.concluidas_com_atraso} OPs"
        taxa_atraso = (100.0 - summary.taxa_pontualidade) if summary.total_concluidas > 0 else 0.0
        self._update_kpi(self.card_delayed, ops_delayed_txt, f"Taxa de Atraso: {taxa_atraso:.1f}%")

        ops_in_line_txt = "1 OP" if summary.em_producao_agora == 1 else f"{summary.em_producao_agora} OPs"
        if summary.is_mes_fechado:
            conf_txt = f"Conformidade: {summary.taxa_conformidade:.1f}%"
        else:
            conf_txt = f"Conformidade: {summary.taxa_conformidade:.1f}% • {summary.em_atraso_agora} atraso" if summary.em_atraso_agora > 0 else f"Conformidade: {summary.taxa_conformidade:.1f}% • Em dia"
        self._update_kpi(self.card_in_line, ops_in_line_txt, conf_txt)

        # Atualiza Gráficos
        self.donut_widget.set_data(
            summary.taxa_pontualidade,
            summary.concluidas_no_prazo,
            summary.concluidas_com_atraso,
        )
        self.flow_bar_widget.set_data(summary.semanas_stats)
        self.sector_bar_widget.set_data(summary.setores_stats)

        # Atualiza Tabelas das Abas
        ops_all = summary.ops
        ops_on_time = [op for op in summary.ops if op.categoria == "CONCLUIDA_NO_PRAZO"]
        ops_delayed = [op for op in summary.ops if op.categoria == "CONCLUIDA_COM_ATRASO"]
        ops_in_line = [op for op in summary.ops if op.categoria in {"EM_PRODUCAO", "EM_ATRASO"}]

        self._populate_table(self.table_all, ops_all)
        self._populate_table(self.table_on_time, ops_on_time)
        self._populate_table(self.table_delayed, ops_delayed)
        self._populate_table(self.table_in_line, ops_in_line)

        self.tab_widget.setTabText(0, f"Todas as OPs ({len(ops_all)})")
        self.tab_widget.setTabText(1, f"No Prazo ({len(ops_on_time)})")
        self.tab_widget.setTabText(2, f"Com Atraso ({len(ops_delayed)})")
        self.tab_widget.setTabText(3, f"Em Produção ({len(ops_in_line)})")

    def _update_kpi(self, card: QFrame, val: str, sub: str) -> None:
        val_lbl = card.findChild(QLabel, "kpiValue")
        sub_lbl = card.findChild(QLabel, "kpiSub")
        if val_lbl:
            val_lbl.setText(val)
        if sub_lbl:
            sub_lbl.setText(sub)

    def _populate_table(self, table: QTableWidget, ops: list[MonthlyOpItemDTO] | tuple[MonthlyOpItemDTO, ...]) -> None:
        table.setRowCount(len(ops))
        for r, op in enumerate(ops):
            dt_conc = op.completed_at.strftime("%d/%m/%Y") if op.completed_at else "-"
            ciclo_str = f"{op.dias_producao} d" if op.dias_producao is not None else "-"

            table.setItem(r, 0, QTableWidgetItem(op.numero_op))
            table.setItem(r, 1, QTableWidgetItem(op.cliente))
            table.setItem(r, 2, QTableWidgetItem(op.modelo))
            table.setItem(r, 3, QTableWidgetItem(str(op.quantidade or "-")))
            table.setItem(r, 4, QTableWidgetItem(op.setor_nome))
            table.setItem(r, 5, QTableWidgetItem(format_br_date(op.data_inicio) or "-"))
            table.setItem(r, 6, QTableWidgetItem(format_br_date(op.data_entrega) or "-"))
            table.setItem(r, 7, QTableWidgetItem(dt_conc))
            table.setItem(r, 8, QTableWidgetItem(ciclo_str))

            if op.categoria == "CONCLUIDA_NO_PRAZO":
                badge_item = QTableWidgetItem("✔ No Prazo")
                badge_item.setForeground(QColor("#4ade80"))
            elif op.categoria == "CONCLUIDA_COM_ATRASO":
                badge_item = QTableWidgetItem("✖ Com Atraso")
                badge_item.setForeground(QColor("#f87171"))
            elif op.categoria == "EM_ATRASO":
                badge_item = QTableWidgetItem("🚨 Atrasada Hoje")
                badge_item.setForeground(QColor("#ef4444"))
            else:
                badge_item = QTableWidgetItem("⚙ Em Linha")
                badge_item.setForeground(QColor("#60a5fa"))

            table.setItem(r, 9, badge_item)

            for col in (0, 3, 5, 6, 7, 8, 9):
                it = table.item(r, col)
                if it:
                    it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

    def _export_pdf(self) -> None:
        if not self._current_summary:
            return

        default_name = f"Relatorio_Producao_{self._current_summary.nome_mes}_{self._current_summary.ano}.pdf"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Salvar Relatório Executivo em PDF",
            str(Path.home() / default_name),
            "Documentos PDF (*.pdf)",
        )
        if not file_path:
            return

        try:
            saved = self.service.export_to_pdf(self._current_summary, file_path)
            if not saved or not Path(saved).is_file():
                raise FileNotFoundError(f"O arquivo PDF não foi encontrado após a geração: {saved}")

            res = QMessageBox.information(
                self,
                "PDF Exportado",
                f"Relatório exportado com sucesso em:\n{saved}\n\nDeseja abrir o arquivo agora?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if res == QMessageBox.StandardButton.Yes:
                os.startfile(str(saved))
        except PermissionError:
            QMessageBox.critical(
                self,
                "Arquivo Bloqueado",
                "Não foi possível salvar o PDF porque o arquivo já está aberto em outro programa "
                "(como Navegador ou Leitor de PDF).\n\n"
                "Por favor, feche o arquivo e tente exportar novamente."
            )
        except Exception as exc:
            QMessageBox.critical(self, "Erro na Exportação", f"Não foi possível gerar o PDF:\n{exc}")

    def _export_excel(self) -> None:
        if not self._current_summary:
            return

        default_name = f"Dados_Producao_{self._current_summary.nome_mes}_{self._current_summary.ano}.xlsx"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Salvar Planilha Excel (.xlsx)",
            str(Path.home() / default_name),
            "Planilha do Excel (*.xlsx)",
        )
        if not file_path:
            return

        try:
            saved = self.service.export_to_excel(self._current_summary, file_path)
            if not saved or not Path(saved).is_file():
                raise FileNotFoundError(f"A planilha Excel não foi encontrada após a geração: {saved}")

            res = QMessageBox.information(
                self,
                "Planilha Exportada",
                f"Planilha exportada com sucesso em:\n{saved}\n\nDeseja abrir no Excel agora?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if res == QMessageBox.StandardButton.Yes:
                os.startfile(str(saved))
        except PermissionError:
            QMessageBox.critical(
                self,
                "Arquivo Bloqueado",
                "Não foi possível salvar a planilha porque o arquivo já está aberto no Microsoft Excel "
                "ou em outro visualizador.\n\n"
                "Por favor, feche a planilha e tente exportar novamente."
            )
        except Exception as exc:
            QMessageBox.critical(self, "Erro na Exportação", f"Não foi possível exportar a planilha:\n{exc}")
