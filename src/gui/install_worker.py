from __future__ import annotations

import traceback

from PySide6.QtCore import QObject, Signal, Slot

from core.deployer import RouterDeployer
from core.models import RouterConfig


class InstallWorker(QObject):
    log = Signal(str)
    finished = Signal(bool, str)

    def __init__(self, config: RouterConfig, action: str = "deploy_selected"):
        super().__init__()
        self.config = config
        self.action = action

    @Slot()
    def run(self) -> None:
        try:
            deployer = RouterDeployer(self.config, logger=self.log.emit)
            deployer.run(self.action)
            self.finished.emit(True, "Готово")
        except Exception as exc:
            self.log.emit("ОШИБКА:")
            self.log.emit(str(exc))
            self.log.emit(traceback.format_exc())
            self.finished.emit(False, str(exc))
