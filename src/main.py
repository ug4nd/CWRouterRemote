import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

PROJECT_SRC = Path(__file__).resolve().parent
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

from ugremotetools.gui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("UGRemoteTools")
    app.setOrganizationName("UGRemoteTools")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
