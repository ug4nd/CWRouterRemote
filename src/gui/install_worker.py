from __future__ import annotations

import traceback

from PySide6.QtCore import QObject, Signal, Slot

from core.deployer import RouterDeployer
from core.models import RouterConfig


class InstallWorker(QObject):
    log = Signal(str)
    finished = Signal(bool, str)

    def __init__(self, config: RouterConfig):
        super().__init__()
        self.config = config

    @Slot()
    def run(self) -> None:
        try:
            RouterDeployer(self.config, logger=self.log.emit).run()
            self.finished.emit(True, "Готово")
        except Exception as exc:
            self.log.emit("ОШИБКА: " + str(exc))
            self.log.emit(traceback.format_exc())
            self.finished.emit(False, str(exc))
