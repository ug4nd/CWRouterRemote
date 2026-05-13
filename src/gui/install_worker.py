from __future__ import annotations

import traceback

from PySide6.QtCore import QObject, Signal, Slot

from core.deployer import RouterDeployer
from core.models import RouterConfig


class InstallWorker(QObject):
    log = Signal(str)
    finished = Signal(bool, str)
    result = Signal(str, str)

    def __init__(self, config: RouterConfig, action: str = "deploy"):
        super().__init__()
        self.config = config
        self.action = action

    @Slot()
    def run(self) -> None:
        try:
            value = RouterDeployer(self.config, logger=self.log.emit).run(self.action)

            if value is not None:
                self.result.emit(self.action, value)

            self.finished.emit(True, "Готово")
        except Exception as exc:
            self.log.emit("ОШИБКА: " + str(exc))
            self.log.emit(traceback.format_exc())
            self.finished.emit(False, str(exc))
