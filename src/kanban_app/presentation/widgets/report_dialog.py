from __future__ import annotations

import os
import subprocess
import sys
from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate, Qt
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
    QSplitter,
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
    """Janela completa para análise gerencial mensal, gráficos e exportação em PDF/CSV."""

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
        self.resize(1180, 780)
        self.setMinimumSize(960, 640)

        self._build_ui()
        self._load_data()

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 14, 16, 14)
        main_layout.setSpacing(10)

        # 1. Barra Superior de Seleção de Período
        period_frame = QFrame(self)
        period_frame.setObjectName("periodFrame")
        period_frame.setStyleSheet(
            "QFrame#periodFrame { background: #1e293b; border-radius: 8px; padding: 6px; }"
        )
        p_layout = QHBoxLayout(period_frame)
        p_layout.setContentsMargins(10, 6, 10, 6)
        p_layout.setSpacing(8)

        lbl_periodo = QLabel("Período de Análise:", period_frame)
        lbl_periodo.setStyleSheet("color: #94a3b8; font-weight: bold; font-size: 11pt;")
        p_layout.addWidget(lbl_periodo)

        self.btn_this_month = QPushButton("📅 Este Mês (em andamento)", period_frame)
        self.btn_prev_month = QPushButton("◀ Mês Anterior", period_frame)
        self.btn_prev_2_months = QPushButton("◀◀ 2 Meses Atrás", period_frame)

        for btn in (self.btn_this_month, self.btn_prev_month, self.btn_prev_2_months):
            btn.setStyleSheet(
                "QPushButton { background: #334155; color: #f8fafc; border: 1px solid #475569; "
                "border-radius: 5px; padding: 4px 10px; font-weight: bold; } "
                "QPushButton:hover { background: #475569; border-color: #38bdf8; }"
            )
            p_layout.addWidget(btn)

        self.btn_this_month.clicked.connect(self._select_this_month)
        self.btn_prev_month.clicked.connect(self._select_prev_month)
        self.btn_prev_2_months.clicked.connect(self._select_prev_2_months)

        p_layout.addSpacing(10)

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

        # Badge de Situação (Mês Fechado vs Em Andamento)
        self.status_badge = QLabel("", period_frame)
        self.status_badge.setObjectName("statusBadge")
        p_layout.addWidget(self.status_badge)

        main_layout.addWidget(period_frame)

        # 2. Cards de Indicadores (KPIs)
        kpi_layout = QHBoxLayout()
        kpi_layout.setSpacing(10)

        self.card_in = self._create_kpi_card("ENTRADAS NO MÊS", "#2563eb")
        self.card_out = self._create_kpi_card("CONCLUÍDAS", "#16a34a")
        self.card_on_time = self._create_kpi_card("NO PRAZO", "#10b981")
        self.card_delayed = self._create_kpi_card("COM ATRASO", "#ef4444")
        self.card_in_line = self._create_kpi_card("EM LINHA HOJE", "#f59e0b")

        for c in (self.card_in, self.card_out, self.card_on_time, self.card_delayed, self.card_in_line):
            kpi_layout.addWidget(c)

        main_layout.addLayout(kpi_layout)

        # 3. Painel de Gráficos (3 colunas)
        charts_frame = QFrame(self)
        charts_frame.setObjectName("chartsFrame")
        charts_frame.setStyleSheet(
            "QFrame#chartsFrame { background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 8px; }"
        )
        charts_layout = QHBoxLayout(charts_frame)
        charts_layout.setContentsMargins(12, 10, 12, 10)
        charts_layout.setSpacing(14)

        # Coluna 1: Pontualidade
        col1 = QVBoxLayout()
        col1_title = QLabel("🎯 Pontualidade de Entrega", charts_frame)
        col1_title.setStyleSheet("font-weight: bold; color: #1e293b; font-size: 10pt;")
        col1.addWidget(col1_title)
        self.donut_widget = PunctualityDonutWidget(charts_frame)
        col1.addWidget(self.donut_widget)
        charts_layout.addLayout(col1, 1)

        # Coluna 2: Fluxo Semanal
        col2 = QVBoxLayout()
        col2_title = QLabel("📊 Fluxo Semanal (Entradas vs Saídas)", charts_frame)
        col2_title.setStyleSheet("font-weight: bold; color: #1e293b; font-size: 10pt;")
        col2.addWidget(col2_title)
        self.flow_bar_widget = FlowBarChartWidget(charts_frame)
        col2.addWidget(self.flow_bar_widget)
        charts_layout.addLayout(col2, 2)

        # Coluna 3: Distribuição por Setores
        col3 = QVBoxLayout()
        col3_title = QLabel("🏭 OPs por Setor", charts_frame)
        col3_title.setStyleSheet("font-weight: bold; color: #1e293b; font-size: 10pt;")
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

        self.tab_widget.addTab(self.table_all, "Todas as OPs do Mês")
        self.tab_widget.addTab(self.table_on_time, "Concluídas no Prazo")
        self.tab_widget.addTab(self.table_delayed, "Concluídas com Atraso")
        self.tab_widget.addTab(self.table_in_line, "Em Produção no Chão de Fábrica")

        main_layout.addWidget(self.tab_widget, 1)

        # 5. Barra Inferior de Ações
        bottom_bar = QHBoxLayout()

        self.btn_export_pdf = QPushButton("📄 Exportar Relatório em PDF", self)
        self.btn_export_pdf.setObjectName("primaryButton")
        self.btn_export_pdf.setStyleSheet(
            "QPushButton#primaryButton { background: #2563eb; color: #ffffff; font-weight: bold; "
            "padding: 8px 18px; border-radius: 6px; font-size: 10pt; } "
            "QPushButton#primaryButton:hover { background: #1d4ed8; }"
        )
        self.btn_export_pdf.clicked.connect(self._export_pdf)
        bottom_bar.addWidget(self.btn_export_pdf)

        self.btn_export_csv = QPushButton("📊 Exportar Dados em Planilha (CSV / Excel)", self)
        self.btn_export_csv.setStyleSheet(
            "QPushButton { background: #0f766e; color: #ffffff; font-weight: bold; "
            "padding: 8px 16px; border-radius: 6px; font-size: 10pt; } "
            "QPushButton:hover { background: #0d9488; }"
        )
        self.btn_export_csv.clicked.connect(self._export_csv)
        bottom_bar.addWidget(self.btn_export_csv)

        bottom_bar.addStretch(1)

        btn_close = QPushButton("Fechar", self)
        btn_close.setFixedWidth(100)
        btn_close.clicked.connect(self.accept)
        bottom_bar.addWidget(btn_close)

        main_layout.addLayout(bottom_bar)

    def _create_kpi_card(self, title: str, border_color: str) -> QFrame:
        card = QFrame(self)
        card.setObjectName("kpiCard")
        card.setStyleSheet(
            f"QFrame#kpiCard {{ background: #ffffff; border: 1px solid #cbd5e1; "
            f"border-left: 5px solid {border_color}; border-radius: 6px; padding: 6px; }}"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)

        lbl_title = QLabel(title, card)
        lbl_title.setStyleSheet("color: #64748b; font-size: 8pt; font-weight: bold; letter-spacing: 0.5px;")
        layout.addWidget(lbl_title)

        lbl_value = QLabel("0 OPs", card)
        lbl_value.setObjectName("kpiValue")
        lbl_value.setStyleSheet("color: #0f172a; font-size: 15pt; font-weight: 900;")
        layout.addWidget(lbl_value)

        lbl_sub = QLabel("-", card)
        lbl_sub.setObjectName("kpiSub")
        lbl_sub.setStyleSheet("color: #64748b; font-size: 8pt;")
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

    def _select_prev_month(self) -> None:
        today = date.today()
        m = today.month - 1
        y = today.year
        if m < 1:
            m = 12
            y -= 1
        self.spin_year.setValue(y)
        self.combo_month.setCurrentIndex(m - 1)

    def _select_prev_2_months(self) -> None:
        today = date.today()
        m = today.month - 2
        y = today.year
        while m < 1:
            m += 12
            y -= 1
        self.spin_year.setValue(y)
        self.combo_month.setCurrentIndex(m - 1)

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
                "background: #166534; color: #ffffff; padding: 6px 12px; border-radius: 6px; font-weight: bold;"
            )
        else:
            self.status_badge.setText(f"● PARCIAL EM ANDAMENTO (até {format_br_date(summary.data_referencia)})")
            self.status_badge.setStyleSheet(
                "background: #b45309; color: #ffffff; padding: 6px 12px; border-radius: 6px; font-weight: bold;"
            )

        # Atualiza Cards de KPI
        self._update_kpi(self.card_in, f"{summary.total_criadas} OPs", f"{summary.total_criadas_pecas} peças")
        self._update_kpi(self.card_out, f"{summary.total_concluidas} OPs", f"{summary.total_concluidas_pecas} peças")
        self._update_kpi(
            self.card_on_time,
            f"{summary.concluidas_no_prazo} OPs",
            f"Pontualidade: {summary.taxa_pontualidade:.1f}%",
        )
        self._update_kpi(
            self.card_delayed,
            f"{summary.concluidas_com_atraso} OPs",
            f"Lead Time: {summary.lead_time_medio_dias:.1f}d",
        )
        self._update_kpi(
            self.card_in_line,
            f"{summary.em_producao_agora} OPs",
            f"{summary.em_atraso_agora} em atraso hoje",
        )

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
                badge_item.setForeground(QColor("#15803d"))
            elif op.categoria == "CONCLUIDA_COM_ATRASO":
                badge_item = QTableWidgetItem("✖ Com Atraso")
                badge_item.setForeground(QColor("#b91c1c"))
            elif op.categoria == "EM_ATRASO":
                badge_item = QTableWidgetItem("🚨 Atrasada Hoje")
                badge_item.setForeground(QColor("#dc2626"))
            else:
                badge_item = QTableWidgetItem("⚙ Em Linha")
                badge_item.setForeground(QColor("#2563eb"))

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
            res = QMessageBox.information(
                self,
                "PDF Exportado",
                f"Relatório exportado com sucesso em:\n{saved}\n\nDeseja abrir o arquivo agora?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if res == QMessageBox.StandardButton.Yes:
                os.startfile(str(saved))
        except Exception as exc:
            QMessageBox.critical(self, "Erro na Exportação", f"Não foi possível gerar o PDF:\n{exc}")

    def _export_csv(self) -> None:
        if not self._current_summary:
            return

        default_name = f"Dados_Producao_{self._current_summary.nome_mes}_{self._current_summary.ano}.csv"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Salvar Dados da Produção em CSV / Planilha",
            str(Path.home() / default_name),
            "Arquivos CSV (*.csv)",
        )
        if not file_path:
            return

        try:
            saved = self.service.export_to_csv(self._current_summary, file_path)
            res = QMessageBox.information(
                self,
                "CSV Exportado",
                f"Dados exportados com sucesso em:\n{saved}\n\nDeseja abrir o arquivo no Excel agora?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if res == QMessageBox.StandardButton.Yes:
                os.startfile(str(saved))
        except Exception as exc:
            QMessageBox.critical(self, "Erro na Exportação", f"Não foi possível exportar a planilha:\n{exc}")
