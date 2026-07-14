from __future__ import annotations

import argparse
from pathlib import Path

from kanban_app.application.deadline_alert_service import DeadlineAlertService
from kanban_app.bootstrap import AppContainer


def main() -> int:
    parser = argparse.ArgumentParser(description="Envia o alerta diário consolidado de prazo.")
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    container = AppContainer.create(Path(args.config))
    service = DeadlineAlertService(container.repository, container.config.smtp, station_id=container.station_id)
    print(service.run_daily())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
