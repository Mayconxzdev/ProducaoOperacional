from __future__ import annotations

import smtplib
from datetime import date
from email.message import EmailMessage

from kanban_app.application.dto import DeadlineAlertDTO
from kanban_app.infrastructure.config import SmtpConfig
from kanban_app.infrastructure.db.repositories import ProductionRepository


class DeadlineAlertService:
    MILESTONES = (14, 7, 3, 0)

    def __init__(self, repository: ProductionRepository, smtp: SmtpConfig, *, station_id: str):
        self.repository = repository
        self.smtp = smtp
        self.station_id = station_id

    def run_daily(self, today: date | None = None) -> int:
        current_day = today or date.today()
        alerts = [
            DeadlineAlertDTO(op=op, milestone_days=(op.data_entrega - current_day).days, days_remaining=(op.data_entrega - current_day).days)
            for op in self.repository.list_active_ops()
            if op.data_entrega is not None and (op.data_entrega - current_day).days in self.MILESTONES
        ]
        if not alerts:
            self.repository.set_setting("deadline.email_last_result", {"state": "skipped", "message": "Nenhuma OP atingiu marco de prazo.", "date": current_day.isoformat()}, station_id=self.station_id)
            return 0
        claimed_ids = self.repository.claim_deadline_alerts(alerts)
        if not claimed_ids:
            return 0
        recipients = self.repository.get_setting("deadline.email_recipients", [])
        if not isinstance(recipients, list) or not recipients:
            self.repository.mark_deadline_alerts(claimed_ids, success=False, error="Nenhum destinatário configurado.")
            self.repository.set_setting("deadline.email_last_result", {"state": "failed", "message": "Nenhum destinatário configurado.", "date": current_day.isoformat()}, station_id=self.station_id)
            return 0
        try:
            self._send(recipients, alerts)
        except Exception as exc:
            self.repository.mark_deadline_alerts(claimed_ids, success=False, error=str(exc))
            self.repository.set_setting("deadline.email_last_result", {"state": "failed", "message": str(exc), "date": current_day.isoformat()}, station_id=self.station_id)
            raise
        self.repository.mark_deadline_alerts(claimed_ids, success=True)
        self.repository.set_setting("deadline.email_last_result", {"state": "sent", "message": f"{len(alerts)} OP(s) enviadas em um e-mail consolidado.", "date": current_day.isoformat()}, station_id=self.station_id)
        return len(alerts)

    def _send(self, recipients: list[str], alerts: list[DeadlineAlertDTO]) -> None:
        if not self.smtp.enabled:
            raise RuntimeError("SMTP está desativado.")
        message = EmailMessage()
        message["Subject"] = "Produção Operacional - marcos de prazo"
        message["From"] = self.smtp.from_email or self.smtp.username
        message["To"] = ", ".join(recipients)
        headers = ("OP", "Cliente", "Modelo", "Quantidade", "Voltagem", "Setor", "Início", "Entrega", "Dias", "Status")
        lines = [" | ".join(headers), " | ".join("---" for _ in headers)]
        for alert in alerts:
            op = alert.op
            lines.append(" | ".join((op.numero_op, op.cliente, op.modelo, "" if op.quantidade is None else str(op.quantidade), op.voltagem, op.setor_nome, op.data_inicio.strftime("%d/%m/%Y") if op.data_inicio else "", op.data_entrega.strftime("%d/%m/%Y") if op.data_entrega else "", str(alert.days_remaining), (op.status.value if hasattr(op.status, "value") else str(op.status)).replace("_", " ").title())))
        message.set_content("\n".join(lines))
        if self.smtp.security_mode == "ssl_tls":
            with smtplib.SMTP_SSL(self.smtp.host, self.smtp.port, timeout=20) as server:
                if self.smtp.username:
                    server.login(self.smtp.username, self.smtp.password)
                server.send_message(message)
        else:
            with smtplib.SMTP(self.smtp.host, self.smtp.port, timeout=20) as server:
                server.starttls()
                if self.smtp.username:
                    server.login(self.smtp.username, self.smtp.password)
                server.send_message(message)
