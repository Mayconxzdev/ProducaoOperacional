from __future__ import annotations

import calendar
import csv
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Sequence

from kanban_app.application.dto import (
    MonthlyOpItemDTO,
    MonthlyReportSummaryDTO,
    MonthlySectorStatDTO,
    MonthlyWeekStatDTO,
    SectorDTO,
)
from kanban_app.formatting import format_br_date
from kanban_app.infrastructure.db.repositories import ProductionRepository

MONTH_NAMES = (
    "",
    "Janeiro",
    "Fevereiro",
    "Março",
    "Abril",
    "Maio",
    "Junho",
    "Julho",
    "Agosto",
    "Setembro",
    "Outubro",
    "Novembro",
    "Dezembro",
)


class MonthlyReportService:
    def __init__(self, repository: ProductionRepository):
        self.repository = repository

    def build_summary(
        self,
        year: int,
        month: int,
        *,
        reference_date: date | None = None,
    ) -> MonthlyReportSummaryDTO:
        today = reference_date or date.today()
        month = max(1, min(12, int(month)))
        year = max(2000, min(2100, int(year)))

        _, last_day = calendar.monthrange(year, month)
        periodo_inicio = date(year, month, 1)
        periodo_fim = date(year, month, last_day)

        is_current_month = (year == today.year and month == today.month)
        is_mes_fechado = not is_current_month and (periodo_fim < today)

        raw_ops, sectors = self.repository.get_monthly_report_raw(periodo_inicio, periodo_fim)

        items: list[MonthlyOpItemDTO] = []
        created_count = 0
        created_pcs = 0
        concluded_count = 0
        concluded_pcs = 0
        on_time_count = 0
        delayed_count = 0
        lead_time_days_total = 0
        lead_time_ops_count = 0
        in_production_now = 0
        in_delay_now = 0
        remaining_forecast = 0

        sector_counts: dict[str, int] = {s.nome: 0 for s in sectors}
        sector_pcs: dict[str, int] = {s.nome: 0 for s in sectors}

        seen_op_ids: set[int] = set()

        for op in raw_ops:
            op_id = int(op["id"])
            op_created_at: datetime | None = op["created_at"]
            op_completed_at: datetime | None = op["completed_at"]
            d_inicio: date | None = op["data_inicio"]
            d_entrega: date | None = op["data_entrega"]
            qtd = op["quantidade"] if op["quantidade"] is not None else 0
            sec_nome = str(op["setor_nome"] or "Sem setor")
            status_str = str(op["status"] or "")

            created_in_month = False
            if op_created_at and periodo_inicio <= op_created_at.date() <= periodo_fim:
                created_in_month = True
            elif d_inicio and periodo_inicio <= d_inicio <= periodo_fim:
                created_in_month = True

            completed_in_month = False
            if op_completed_at and periodo_inicio <= op_completed_at.date() <= periodo_fim:
                completed_in_month = True

            # OPs ativas no mês atual
            is_active_current = is_current_month and not op["archived"] and status_str != "CONCLUIDO"

            # Se não pertence a este mês, descarta
            if not (created_in_month or completed_in_month or (is_current_month and is_active_current)):
                continue

            if op_id in seen_op_ids:
                continue
            seen_op_ids.add(op_id)

            if created_in_month:
                created_count += 1
                created_pcs += qtd

            entregue_no_prazo: bool | None = None
            esta_em_atraso = False
            dias_producao: int | None = None
            categoria = "EM_PRODUCAO"

            if completed_in_month:
                concluded_count += 1
                concluded_pcs += qtd

                if d_entrega is not None and op_completed_at is not None:
                    if op_completed_at.date() <= d_entrega:
                        entregue_no_prazo = True
                        on_time_count += 1
                        categoria = "CONCLUIDA_NO_PRAZO"
                    else:
                        entregue_no_prazo = False
                        delayed_count += 1
                        categoria = "CONCLUIDA_COM_ATRASO"
                else:
                    entregue_no_prazo = True
                    on_time_count += 1
                    categoria = "CONCLUIDA_NO_PRAZO"

                if d_inicio and op_completed_at:
                    diff = (op_completed_at.date() - d_inicio).days
                    dias_producao = max(0, diff)
                    lead_time_days_total += dias_producao
                    lead_time_ops_count += 1
            else:
                # OP não concluída
                if is_current_month and is_active_current:
                    in_production_now += 1
                    if d_entrega and d_entrega < today:
                        esta_em_atraso = True
                        in_delay_now += 1
                        categoria = "EM_ATRASO"
                    else:
                        categoria = "EM_PRODUCAO"
                        if d_entrega and today <= d_entrega <= periodo_fim:
                            remaining_forecast += 1

                    if d_inicio:
                        dias_producao = max(0, (today - d_inicio).days)

            # Acúmulo por setor
            if sec_nome not in sector_counts:
                sector_counts[sec_nome] = 0
                sector_pcs[sec_nome] = 0
            sector_counts[sec_nome] += 1
            sector_pcs[sec_nome] += qtd

            items.append(
                MonthlyOpItemDTO(
                    op_id=op_id,
                    numero_op=str(op["numero_op"]),
                    cliente=str(op["cliente"]),
                    modelo=str(op["modelo"]),
                    quantidade=op["quantidade"],
                    voltagem=str(op["voltagem"] or ""),
                    setor_nome=sec_nome,
                    status=status_str,
                    data_inicio=d_inicio,
                    data_entrega=d_entrega,
                    completed_at=op_completed_at,
                    dias_producao=dias_producao,
                    entregue_no_prazo=entregue_no_prazo,
                    esta_em_atraso=esta_em_atraso,
                    categoria=categoria,
                )
            )

        # Ordena OPs por número de OP ou entrega
        items.sort(key=lambda x: (x.data_entrega or date.max, x.numero_op))

        # Taxa de pontualidade
        taxa_pontualidade = 100.0
        if concluded_count > 0:
            taxa_pontualidade = round((on_time_count / concluded_count) * 100.0, 1)

        # Lead time médio
        lead_time_medio = 0.0
        if lead_time_ops_count > 0:
            lead_time_medio = round(lead_time_days_total / lead_time_ops_count, 1)

        # Estatísticas por Setor
        sector_stats: list[MonthlySectorStatDTO] = []
        sec_color_map = {s.nome: s.cor for s in sectors}
        sec_id_map = {s.nome: s.id for s in sectors}
        for s_nome, count in sector_counts.items():
            if count > 0:
                sector_stats.append(
                    MonthlySectorStatDTO(
                        setor_id=sec_id_map.get(s_nome),
                        setor_nome=s_nome,
                        cor=sec_color_map.get(s_nome, "#475569"),
                        total_ops=count,
                        total_quantidade=sector_pcs.get(s_nome, 0),
                    )
                )
        sector_stats.sort(key=lambda s: s.total_ops, reverse=True)

        # Semanas do mês (divisão em blocos de 7 dias)
        week_stats: list[MonthlyWeekStatDTO] = []
        cur_day = 1
        week_idx = 1
        while cur_day <= last_day:
            w_start = date(year, month, cur_day)
            w_end_day = min(cur_day + 6, last_day)
            w_end = date(year, month, w_end_day)

            # Conta criadas e concluídas nessa janela
            w_in = 0
            w_out = 0
            for item in items:
                if item.data_inicio and w_start <= item.data_inicio <= w_end:
                    w_in += 1
                if item.completed_at and w_start <= item.completed_at.date() <= w_end:
                    w_out += 1

            week_stats.append(
                MonthlyWeekStatDTO(
                    label=f"Sem {week_idx} ({w_start.day:02d}-{w_end.day:02d})",
                    data_inicio=w_start,
                    data_fim=w_end,
                    entradas=w_in,
                    saidas=w_out,
                )
            )
            cur_day = w_end_day + 1
            week_idx += 1

        return MonthlyReportSummaryDTO(
            ano=year,
            mes=month,
            nome_mes=MONTH_NAMES[month],
            periodo_inicio=periodo_inicio,
            periodo_fim=periodo_fim,
            data_referencia=today,
            is_mes_fechado=is_mes_fechado,
            total_criadas=created_count,
            total_criadas_pecas=created_pcs,
            total_concluidas=concluded_count,
            total_concluidas_pecas=concluded_pcs,
            concluidas_no_prazo=on_time_count,
            concluidas_com_atraso=delayed_count,
            taxa_pontualidade=taxa_pontualidade,
            lead_time_medio_dias=lead_time_medio,
            em_producao_agora=in_production_now,
            em_atraso_agora=in_delay_now,
            previsao_restante_mes=remaining_forecast,
            setores_stats=tuple(sector_stats),
            semanas_stats=tuple(week_stats),
            ops=tuple(items),
        )

    def export_to_csv(self, summary: MonthlyReportSummaryDTO, file_path: str | Path) -> Path:
        target = Path(file_path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)

        with target.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f, delimiter=";")
            # Cabeçalho do relatório
            writer.writerow(["RELATÓRIO MENSAL DE PRODUÇÃO", f"{summary.nome_mes} / {summary.ano}"])
            status_desc = "MÊS FECHADO" if summary.is_mes_fechado else f"PARCIAL EM ANDAMENTO (até {format_br_date(summary.data_referencia)})"
            writer.writerow(["Situação", status_desc])
            writer.writerow([])

            # Resumo de Indicadores
            writer.writerow(["INDICADORES GERAIS", "VALOR"])
            writer.writerow(["Total de OPs Criadas no Mês", summary.total_criadas])
            writer.writerow(["Volume de Peças Criadas", summary.total_criadas_pecas])
            writer.writerow(["Total de OPs Concluídas no Mês", summary.total_concluidas])
            writer.writerow(["Volume de Peças Concluídas", summary.total_concluidas_pecas])
            writer.writerow(["Concluídas no Prazo", summary.concluidas_no_prazo])
            writer.writerow(["Concluídas com Atraso", summary.concluidas_com_atraso])
            writer.writerow(["Índice de Pontualidade (%)", f"{summary.taxa_pontualidade}%"])
            writer.writerow(["Lead Time Médio (Dias)", f"{summary.lead_time_medio_dias} dias"])
            if not summary.is_mes_fechado:
                writer.writerow(["Em Produção no Momento", summary.em_producao_agora])
                writer.writerow(["Atualmente em Atraso", summary.em_atraso_agora])
                writer.writerow(["Previsão de Entrega até Fim do Mês", summary.previsao_restante_mes])
            writer.writerow([])

            # Tabela de OPs
            writer.writerow([
                "OP",
                "Cliente",
                "Modelo",
                "Quantidade",
                "Voltagem",
                "Setor",
                "Data Início",
                "Prazo Entrega",
                "Data Conclusão",
                "Dias Produção",
                "Situação",
            ])

            for op in summary.ops:
                dt_conc = op.completed_at.strftime("%d/%m/%Y") if op.completed_at else ""
                sit = "Concluída no Prazo"
                if op.categoria == "CONCLUIDA_COM_ATRASO":
                    sit = "Concluída com Atraso"
                elif op.categoria == "EM_ATRASO":
                    sit = "Em Linha (Atrasada)"
                elif op.categoria == "EM_PRODUCAO":
                    sit = "Em Produção"

                writer.writerow([
                    op.numero_op,
                    op.cliente,
                    op.modelo,
                    op.quantidade if op.quantidade is not None else "",
                    op.voltagem,
                    op.setor_nome,
                    format_br_date(op.data_inicio),
                    format_br_date(op.data_entrega),
                    dt_conc,
                    op.dias_producao if op.dias_producao is not None else "",
                    sit,
                ])

        return target

    def export_to_pdf(self, summary: MonthlyReportSummaryDTO, file_path: str | Path) -> Path:
        """Exporta o relatório executivo em formato PDF diagramado usando PySide6 nativo."""
        from PySide6.QtCore import QMarginsF
        from PySide6.QtGui import QFont, QPageLayout, QPageSize, QPdfWriter, QTextDocument

        target = Path(file_path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)

        html = self._generate_html_report(summary)

        doc = QTextDocument()
        doc.setDefaultFont(QFont("Segoe UI", 9))
        doc.setHtml(html)

        writer = QPdfWriter(str(target))
        writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        writer.setPageMargins(QMarginsF(12, 12, 12, 12), QPageLayout.Unit.Millimeter)

        doc.print_(writer)
        del writer
        return target

    def _generate_html_report(self, s: MonthlyReportSummaryDTO) -> str:
        status_badge = (
            "<span style='background: #166534; color: #ffffff; padding: 4px 10px; border-radius: 4px; font-weight: bold;'>MÊS FECHADO / CONCLUÍDO</span>"
            if s.is_mes_fechado
            else f"<span style='background: #b45309; color: #ffffff; padding: 4px 10px; border-radius: 4px; font-weight: bold;'>PARCIAL EM ANDAMENTO (até {format_br_date(s.data_referencia)})</span>"
        )

        rows_html = []
        for op in s.ops:
            dt_conc = op.completed_at.strftime("%d/%m/%Y") if op.completed_at else "-"
            if op.categoria == "CONCLUIDA_NO_PRAZO":
                badge = "<span style='color: #15803d; font-weight: bold;'>No Prazo</span>"
            elif op.categoria == "CONCLUIDA_COM_ATRASO":
                badge = "<span style='color: #b91c1c; font-weight: bold;'>Com Atraso</span>"
            elif op.categoria == "EM_ATRASO":
                badge = "<span style='color: #dc2626; font-weight: bold;'>Atrasada Hoje</span>"
            else:
                badge = "<span style='color: #2563eb;'>Em Linha</span>"

            rows_html.append(
                f"""
                <tr>
                    <td style='font-weight: bold; padding: 5px; border-bottom: 1px solid #e2e8f0;'>{op.numero_op}</td>
                    <td style='padding: 5px; border-bottom: 1px solid #e2e8f0;'>{op.cliente}</td>
                    <td style='padding: 5px; border-bottom: 1px solid #e2e8f0;'>{op.modelo}</td>
                    <td style='padding: 5px; border-bottom: 1px solid #e2e8f0; text-align: center;'>{op.quantidade or '-'}</td>
                    <td style='padding: 5px; border-bottom: 1px solid #e2e8f0;'>{op.setor_nome}</td>
                    <td style='padding: 5px; border-bottom: 1px solid #e2e8f0; text-align: center;'>{format_br_date(op.data_inicio) or '-'}</td>
                    <td style='padding: 5px; border-bottom: 1px solid #e2e8f0; text-align: center;'>{format_br_date(op.data_entrega) or '-'}</td>
                    <td style='padding: 5px; border-bottom: 1px solid #e2e8f0; text-align: center;'>{dt_conc}</td>
                    <td style='padding: 5px; border-bottom: 1px solid #e2e8f0; text-align: center;'>{op.dias_producao if op.dias_producao is not None else '-'} d</td>
                    <td style='padding: 5px; border-bottom: 1px solid #e2e8f0; text-align: center;'>{badge}</td>
                </tr>
                """
            )

        # Barras de semanas
        weeks_html = []
        max_ops = max([max(w.entradas, w.saidas) for w in s.semanas_stats] + [1])
        for w in s.semanas_stats:
            in_pct = int((w.entradas / max_ops) * 100)
            out_pct = int((w.saidas / max_ops) * 100)
            weeks_html.append(
                f"""
                <div style='margin-bottom: 6px;'>
                    <div style='font-size: 11px; font-weight: bold; color: #475569;'>{w.label}: {w.entradas} entraram, {w.saidas} saíram</div>
                    <div style='background: #e2e8f0; height: 10px; border-radius: 4px; overflow: hidden; margin-top: 2px;'>
                        <div style='background: #2563eb; width: {in_pct}%; height: 5px;'></div>
                        <div style='background: #16a34a; width: {out_pct}%; height: 5px;'></div>
                    </div>
                </div>
                """
            )

        # Setores
        sector_bars = []
        max_sec = max([sec.total_ops for sec in s.setores_stats] + [1])
        for sec in s.setores_stats:
            pct = int((sec.total_ops / max_sec) * 100)
            sector_bars.append(
                f"""
                <div style='margin-bottom: 5px;'>
                    <div style='font-size: 11px;'><strong>{sec.setor_nome}:</strong> {sec.total_ops} OPs ({sec.total_quantidade} peças)</div>
                    <div style='background: #e2e8f0; height: 8px; border-radius: 4px;'>
                        <div style='background: {sec.cor}; width: {pct}%; height: 8px; border-radius: 4px;'></div>
                    </div>
                </div>
                """
            )

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: 'Segoe UI', Arial, sans-serif; color: #1e293b; line-height: 1.3; }}
                h1, h2, h3 {{ margin: 0; padding: 0; }}
                .kpi-table {{ width: 100%; border-collapse: separate; border-spacing: 8px; margin: 15px 0; }}
                .kpi-card {{ background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 6px; padding: 10px; text-align: center; }}
                .kpi-num {{ font-size: 20px; font-weight: 900; color: #0f172a; margin-top: 4px; }}
                .kpi-lbl {{ font-size: 10px; font-weight: bold; color: #64748b; text-transform: uppercase; }}
                table.data {{ width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 11px; }}
                th {{ background: #1e293b; color: #ffffff; padding: 6px; text-align: left; }}
            </style>
        </head>
        <body>
            <div style='border-bottom: 2px solid #2563eb; padding-bottom: 10px; margin-bottom: 12px;'>
                <table style='width: 100%;'>
                    <tr>
                        <td>
                            <h1 style='color: #0f172a; font-size: 20px;'>PRODUÇÃO OPERACIONAL</h1>
                            <div style='color: #64748b; font-size: 12px;'>Relatório Mensal de Gestão de Ordens de Produção</div>
                        </td>
                        <td style='text-align: right;'>
                            <h2 style='color: #2563eb; font-size: 18px;'>{s.nome_mes.upper()} / {s.ano}</h2>
                            <div style='margin-top: 4px;'>{status_badge}</div>
                        </td>
                    </tr>
                </table>
            </div>

            <!-- KPIs -->
            <table class='kpi-table'>
                <tr>
                    <td class='kpi-card' style='border-left: 4px solid #2563eb;'>
                        <div class='kpi-lbl'>Entradas no Mês</div>
                        <div class='kpi-num'>{s.total_criadas} OPs</div>
                        <div style='font-size: 10px; color: #64748b;'>{s.total_criadas_pecas} peças</div>
                    </td>
                    <td class='kpi-card' style='border-left: 4px solid #16a34a;'>
                        <div class='kpi-lbl'>Concluídas</div>
                        <div class='kpi-num'>{s.total_concluidas} OPs</div>
                        <div style='font-size: 10px; color: #64748b;'>{s.total_concluidas_pecas} peças</div>
                    </td>
                    <td class='kpi-card' style='border-left: 4px solid #10b981;'>
                        <div class='kpi-lbl'>Entregas no Prazo</div>
                        <div class='kpi-num' style='color: #15803d;'>{s.concluidas_no_prazo} OPs</div>
                        <div style='font-size: 10px; color: #15803d;'>Pontualidade: {s.taxa_pontualidade}%</div>
                    </td>
                    <td class='kpi-card' style='border-left: 4px solid #ef4444;'>
                        <div class='kpi-lbl'>Entregas com Atraso</div>
                        <div class='kpi-num' style='color: #b91c1c;'>{s.concluidas_com_atraso} OPs</div>
                        <div style='font-size: 10px; color: #b91c1c;'>Lead Time: {s.lead_time_medio_dias}d</div>
                    </td>
                    <td class='kpi-card' style='border-left: 4px solid #f59e0b;'>
                        <div class='kpi-lbl'>Em Produção Hoje</div>
                        <div class='kpi-num' style='color: #b45309;'>{s.em_producao_agora} OPs</div>
                        <div style='font-size: 10px; color: #dc2626;'>{s.em_atraso_agora} em atraso</div>
                    </td>
                </tr>
            </table>

            <!-- Gráficos Resumidos -->
            <table style='width: 100%; margin-bottom: 15px;'>
                <tr>
                    <td style='width: 50%; vertical-align: top; padding-right: 10px;'>
                        <div style='background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 6px; padding: 10px;'>
                            <div style='font-weight: bold; font-size: 12px; margin-bottom: 8px; color: #1e293b;'>Fluxo de Produção (Semana a Semana)</div>
                            <div style='font-size: 10px; margin-bottom: 6px;'><span style='color: #2563eb;'>■ Entradas</span> | <span style='color: #16a34a;'>■ Conclusões</span></div>
                            {''.join(weeks_html) if weeks_html else '<em>Sem movimentação registrada</em>'}
                        </div>
                    </td>
                    <td style='width: 50%; vertical-align: top; padding-left: 10px;'>
                        <div style='background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 6px; padding: 10px;'>
                            <div style='font-weight: bold; font-size: 12px; margin-bottom: 8px; color: #1e293b;'>Distribuição por Setores</div>
                            {''.join(sector_bars) if sector_bars else '<em>Sem movimentação por setor</em>'}
                        </div>
                    </td>
                </tr>
            </table>

            <!-- Tabela Detalhada -->
            <div style='margin-top: 15px;'>
                <div style='font-weight: bold; font-size: 13px; color: #0f172a; margin-bottom: 6px;'>Detalhamento das Ordens de Produção ({len(s.ops)} registros)</div>
                <table class='data'>
                    <thead>
                        <tr>
                            <th>OP</th>
                            <th>Cliente</th>
                            <th>Modelo</th>
                            <th style='text-align: center;'>Qtd</th>
                            <th>Setor</th>
                            <th style='text-align: center;'>Início</th>
                            <th style='text-align: center;'>Entrega</th>
                            <th style='text-align: center;'>Conclusão</th>
                            <th style='text-align: center;'>Ciclo</th>
                            <th style='text-align: center;'>Situação</th>
                        </tr>
                    </thead>
                    <tbody>
                        {''.join(rows_html) if rows_html else '<tr><td colspan=\"10\" style=\"text-align: center; padding: 15px;\">Nenhuma OP encontrada para este período.</td></tr>'}
                    </tbody>
                </table>
            </div>

            <div style='margin-top: 25px; border-top: 1px solid #cbd5e1; padding-top: 6px; font-size: 9px; color: #94a3b8; text-align: right;'>
                Produção Operacional • Documento gerado em {datetime.now().strftime('%d/%m/%Y às %H:%M')} • Página 1 de 1
            </div>
        </body>
        </html>
        """
        return html
