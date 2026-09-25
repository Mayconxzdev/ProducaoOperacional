from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from kanban_app.application.dto import MonthlySectorStatDTO, MonthlyWeekStatDTO


class PunctualityDonutWidget(QWidget):
    """Gráfico de anel (Donut) profissional com taxa de pontualidade das entregas."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setMinimumSize(200, 170)
        self._on_time_pct: float = 100.0
        self._on_time_count: int = 0
        self._delayed_count: int = 0

    def set_data(self, on_time_pct: float, on_time_count: int, delayed_count: int) -> None:
        self._on_time_pct = max(0.0, min(100.0, float(on_time_pct)))
        self._on_time_count = int(on_time_count)
        self._delayed_count = int(delayed_count)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        side = min(w - 12, h - 30)
        rect = QRectF((w - side) / 2, 4, side, side)

        pen_width = max(11, int(side * 0.11))
        rect.adjust(pen_width / 2, pen_width / 2, -pen_width / 2, -pen_width / 2)

        total = self._on_time_count + self._delayed_count
        if total == 0:
            # Sem dados: anel cinza escuro
            gray_pen = QPen(QColor("#334155"), pen_width, Qt.PenStyle.SolidLine)
            painter.setPen(gray_pen)
            painter.drawEllipse(rect)

            painter.setPen(QColor("#94a3b8"))
            painter.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "Sem saídas")
        elif self._delayed_count == 0:
            # 100% no prazo: anel inteiramente verde, zero cor vermelha
            green_pen = QPen(QColor("#22c55e"), pen_width, Qt.PenStyle.SolidLine)
            painter.setPen(green_pen)
            painter.drawEllipse(rect)

            painter.setPen(QColor("#4ade80"))
            f_num = QFont("Segoe UI", max(11, int(side * 0.135)), QFont.Weight.Bold)
            painter.setFont(f_num)
            text_rect = QRectF(rect.x(), rect.y() + rect.height() * 0.23, rect.width(), rect.height() * 0.35)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, f"{self._on_time_pct:.1f}%")

            f_lbl = QFont("Segoe UI", max(8, int(side * 0.08)), QFont.Weight.DemiBold)
            painter.setFont(f_lbl)
            painter.setPen(QColor("#86efac"))
            lbl_rect = QRectF(rect.x(), rect.y() + rect.height() * 0.55, rect.width(), rect.height() * 0.25)
            painter.drawText(lbl_rect, Qt.AlignmentFlag.AlignCenter, "No Prazo")
        elif self._on_time_count == 0:
            # 100% com atraso: anel inteiramente vermelho
            red_pen = QPen(QColor("#ef4444"), pen_width, Qt.PenStyle.SolidLine)
            painter.setPen(red_pen)
            painter.drawEllipse(rect)

            painter.setPen(QColor("#f87171"))
            f_num = QFont("Segoe UI", max(11, int(side * 0.135)), QFont.Weight.Bold)
            painter.setFont(f_num)
            text_rect = QRectF(rect.x(), rect.y() + rect.height() * 0.23, rect.width(), rect.height() * 0.35)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, f"{self._on_time_pct:.1f}%")

            f_lbl = QFont("Segoe UI", max(8, int(side * 0.08)), QFont.Weight.DemiBold)
            painter.setFont(f_lbl)
            painter.setPen(QColor("#fca5a5"))
            lbl_rect = QRectF(rect.x(), rect.y() + rect.height() * 0.55, rect.width(), rect.height() * 0.25)
            painter.drawText(lbl_rect, Qt.AlignmentFlag.AlignCenter, "Com Atraso")
        else:
            # Misto: anel base vermelho e arco verde proporcional
            bg_pen = QPen(QColor("#ef4444"), pen_width, Qt.PenStyle.SolidLine)
            painter.setPen(bg_pen)
            painter.drawEllipse(rect)

            span_angle = int((self._on_time_pct / 100.0) * 360 * 16)
            green_pen = QPen(QColor("#22c55e"), pen_width, Qt.PenStyle.SolidLine)
            painter.setPen(green_pen)
            painter.drawArc(rect, 90 * 16, -span_angle)

            painter.setPen(QColor("#f8fafc"))
            f_num = QFont("Segoe UI", max(11, int(side * 0.135)), QFont.Weight.Bold)
            painter.setFont(f_num)
            text_rect = QRectF(rect.x(), rect.y() + rect.height() * 0.23, rect.width(), rect.height() * 0.35)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, f"{self._on_time_pct:.1f}%")

            f_lbl = QFont("Segoe UI", max(8, int(side * 0.08)), QFont.Weight.DemiBold)
            painter.setFont(f_lbl)
            painter.setPen(QColor("#94a3b8"))
            lbl_rect = QRectF(rect.x(), rect.y() + rect.height() * 0.55, rect.width(), rect.height() * 0.25)
            painter.drawText(lbl_rect, Qt.AlignmentFlag.AlignCenter, "No Prazo")

        # Legenda inferior
        leg_rect = QRectF(0, h - 26, w, 22)
        leg_font = QFont("Segoe UI", 9, QFont.Weight.Medium)
        painter.setFont(leg_font)
        painter.setPen(QColor("#cbd5e1"))
        leg_text = f"✔ {self._on_time_count} no prazo   •   ✖ {self._delayed_count} com atraso"
        painter.drawText(leg_rect, Qt.AlignmentFlag.AlignCenter, leg_text)


class FlowBarChartWidget(QWidget):
    """Gráfico de barras verticais de fluxo (entradas vs saídas semanais)."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setMinimumSize(280, 170)
        self._semanas: list[MonthlyWeekStatDTO] = []

    def set_data(self, semanas: list[MonthlyWeekStatDTO] | tuple[MonthlyWeekStatDTO, ...]) -> None:
        self._semanas = list(semanas)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        margin_left = 32
        margin_bottom = 28
        margin_top = 20
        margin_right = 16

        chart_w = w - margin_left - margin_right
        chart_h = h - margin_top - margin_bottom

        if not self._semanas:
            painter.setPen(QColor("#94a3b8"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Sem movimentação registrada no mês.")
            return

        max_val = max([max(s.entradas, s.saidas) for s in self._semanas] + [5])

        # Linhas de grade suaves (estilo dark theme)
        painter.setPen(QPen(QColor("#334155"), 1, Qt.PenStyle.DashLine))
        painter.drawLine(margin_left, margin_top, margin_left + chart_w, margin_top)
        painter.drawLine(margin_left, margin_top + chart_h // 2, margin_left + chart_w, margin_top + chart_h // 2)
        painter.setPen(QPen(QColor("#475569"), 1, Qt.PenStyle.SolidLine))
        painter.drawLine(margin_left, margin_top + chart_h, margin_left + chart_w, margin_top + chart_h)

        # Rótulos no eixo Y
        painter.setFont(QFont("Segoe UI", 8))
        painter.setPen(QColor("#94a3b8"))
        painter.drawText(QRectF(0, margin_top - 8, margin_left - 4, 16), Qt.AlignmentFlag.AlignRight, str(max_val))
        painter.drawText(QRectF(0, margin_top + chart_h // 2 - 8, margin_left - 4, 16), Qt.AlignmentFlag.AlignRight, str(max_val // 2))
        painter.drawText(QRectF(0, margin_top + chart_h - 8, margin_left - 4, 16), Qt.AlignmentFlag.AlignRight, "0")

        n_groups = len(self._semanas)
        group_w = chart_w / n_groups
        bar_w = min(22.0, max(8.0, group_w * 0.32))

        for idx, sem in enumerate(self._semanas):
            cx = margin_left + idx * group_w + group_w / 2

            h_in = (sem.entradas / max_val) * chart_h
            h_out = (sem.saidas / max_val) * chart_h

            x_in = cx - bar_w - 2
            y_in = margin_top + chart_h - h_in
            x_out = cx + 2
            y_out = margin_top + chart_h - h_out

            # Barra de entradas (Azul Vibrante)
            if sem.entradas > 0:
                painter.setBrush(QBrush(QColor("#3b82f6")))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(QRectF(x_in, y_in, bar_w, h_in), 3, 3)

                # Número acima da barra
                painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
                painter.setPen(QColor("#93c5fd"))
                painter.drawText(QRectF(x_in - 4, y_in - 14, bar_w + 8, 14), Qt.AlignmentFlag.AlignCenter, str(sem.entradas))

            # Barra de saídas (Verde Esmeralda)
            if sem.saidas > 0:
                painter.setBrush(QBrush(QColor("#10b981")))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(QRectF(x_out, y_out, bar_w, h_out), 3, 3)

                # Número acima da barra
                painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
                painter.setPen(QColor("#86efac"))
                painter.drawText(QRectF(x_out - 4, y_out - 14, bar_w + 8, 14), Qt.AlignmentFlag.AlignCenter, str(sem.saidas))

            # Rótulo da semana abaixo
            painter.setPen(QColor("#94a3b8"))
            painter.setFont(QFont("Segoe UI", 8))
            lbl_rect = QRectF(margin_left + idx * group_w, margin_top + chart_h + 4, group_w, 20)
            short_lbl = sem.label.split(" ")[0] + " " + sem.label.split(" ")[1] if " " in sem.label else sem.label
            painter.drawText(lbl_rect, Qt.AlignmentFlag.AlignCenter, short_lbl)


class SectorBarChartWidget(QWidget):
    """Gráfico de barras horizontais com a distribuição de OPs por setor."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setMinimumSize(280, 170)
        self._setores: list[MonthlySectorStatDTO] = []

    def set_data(self, setores: list[MonthlySectorStatDTO] | tuple[MonthlySectorStatDTO, ...]) -> None:
        self._setores = list(setores)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        if not self._setores:
            painter.setPen(QColor("#94a3b8"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Nenhuma OP alocada em setores no período.")
            return

        visible_count = min(6, len(self._setores))
        displayed = self._setores[:visible_count]
        max_ops = max([s.total_ops for s in displayed] + [1])

        label_w = 100
        val_w = 65
        bar_area_w = w - label_w - val_w - 20
        row_h = (h - 10) / visible_count

        for idx, sec in enumerate(displayed):
            y = 6 + idx * row_h
            bar_y = y + (row_h - 14) / 2

            # Nome do setor (texto claro)
            painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Medium))
            painter.setPen(QColor("#f1f5f9"))
            text_rect = QRectF(8, y, label_w - 10, row_h)
            metrics = painter.fontMetrics()
            elided = metrics.elidedText(sec.setor_nome, Qt.TextElideMode.ElideRight, int(label_w - 12))
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided)

            # Barra de fundo escura
            bar_x = label_w
            painter.setBrush(QBrush(QColor("#334155")))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(QRectF(bar_x, bar_y, bar_area_w, 14), 4, 4)

            # Barra preenchida colorida com a cor do setor
            fill_w = max(6.0, (sec.total_ops / max_ops) * bar_area_w)
            bar_color = QColor(sec.cor if sec.cor else "#3b82f6")
            painter.setBrush(QBrush(bar_color))
            painter.drawRoundedRect(QRectF(bar_x, bar_y, fill_w, 14), 4, 4)

            # Quantidade à direita
            painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            painter.setPen(QColor("#94a3b8"))
            val_rect = QRectF(bar_x + bar_area_w + 8, y, val_w, row_h)
            op_lbl = f"{sec.total_ops} OP" if sec.total_ops == 1 else f"{sec.total_ops} OPs"
            painter.drawText(val_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, op_lbl)
