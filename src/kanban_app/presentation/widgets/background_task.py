from __future__ import annotations

import logging
from traceback import format_exception

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

logger = logging.getLogger(__name__)


class BackgroundTaskSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class BackgroundTask(QRunnable):
    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = BackgroundTaskSignals()

    @Slot()
    def run(self) -> None:
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as exc:  # pragma: no cover - gui worker
            logger.exception("Falha em tarefa de segundo plano")
            trace = "".join(format_exception(type(exc), exc, exc.__traceback__))
            try:
                self.signals.failed.emit(trace)
            except RuntimeError:
                pass
            return
        try:
            self.signals.finished.emit(result)
        except RuntimeError:
            pass
