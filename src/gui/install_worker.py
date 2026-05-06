from PySide6.QtCore import QObject, Signal, Slot

from core.installer import CloudflaredInstaller, InstallError


class InstallWorker(QObject):
    finished = Signal()
    log = Signal(str)
    error = Signal(str)
    success = Signal()

    def __init__(self, installer: CloudflaredInstaller) -> None:
        super().__init__()
        self.installer = installer

    @Slot()
    def run(self) -> None:
        try:
            logs = self.installer.install_from_repo()
            for line in logs:
                self.log.emit(line)
            self.success.emit()
        except InstallError as e:
            self.error.emit(str(e))
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit()