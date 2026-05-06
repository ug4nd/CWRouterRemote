from pathlib import Path
from PySide6.QtCore import QThread
from gui.install_worker import InstallWorker
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QFileDialog,
    QMessageBox,
    QGroupBox,
)

from core.config_loader import load_router_config
from core.ssh_client import RouterSSHClient, SSHConnectionError
from core.installer import CloudflaredInstaller, InstallError


class MainWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("CWRouterRemote")
        self.setGeometry(200, 120, 900, 600)

        self.loaded_config: dict | None = None
        self.ssh_client = RouterSSHClient()
        self.installer = CloudflaredInstaller(self.ssh_client)

        self.install_thread: QThread | None = None
        self.install_worker: InstallWorker | None = None

        self._build_ui()

        self.raise_()
        self.activateWindow()

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(12)

        form_group = QGroupBox("Подключение к роутеру")
        form_layout = QGridLayout()
        form_layout.setHorizontalSpacing(10)
        form_layout.setVerticalSpacing(10)

        self.host_input = QLineEdit()
        self.host_input.setPlaceholderText("192.168.1.1")

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("root")

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Пароль")
        self.password_input.setEchoMode(QLineEdit.Password)

        form_layout.addWidget(QLabel("Адрес роутера"), 0, 0)
        form_layout.addWidget(self.host_input, 0, 1)

        form_layout.addWidget(QLabel("Логин"), 1, 0)
        form_layout.addWidget(self.username_input, 1, 1)

        form_layout.addWidget(QLabel("Пароль"), 2, 0)
        form_layout.addWidget(self.password_input, 2, 1)

        form_group.setLayout(form_layout)
        root_layout.addWidget(form_group)

        buttons_group = QGroupBox("Действия")
        buttons_layout = QHBoxLayout()

        self.ssh_button = QPushButton("SSH connect")
        self.install_button = QPushButton("Install cloudflared")
        self.load_config_button = QPushButton("Load config")

        self.ssh_button.clicked.connect(self.on_ssh_connect_clicked)
        self.install_button.clicked.connect(self.on_install_clicked)
        self.load_config_button.clicked.connect(self.on_load_config_clicked)

        buttons_layout.addWidget(self.ssh_button)
        buttons_layout.addWidget(self.install_button)
        buttons_layout.addWidget(self.load_config_button)

        buttons_group.setLayout(buttons_layout)
        root_layout.addWidget(buttons_group)

        logs_group = QGroupBox("Логи")
        logs_layout = QVBoxLayout()

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setPlaceholderText("Здесь будут логи программы...")

        logs_layout.addWidget(self.log_output)
        logs_group.setLayout(logs_layout)

        root_layout.addWidget(logs_group)

        self._log("GUI запущен")
        self._log("Окно успешно создано")

    def _log(self, message: str) -> None:
        self.log_output.append(message)

    def _show_error(self, title: str, message: str) -> None:
        QMessageBox.critical(self, title, message)
        self._log(f"[ERROR] {message}")

    def on_load_config_clicked(self) -> None:
        start_dir = Path.cwd() / "router_configs"

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Выбери конфиг роутера",
            str(start_dir),
            "JSON files (*.json)",
        )

        if not file_path:
            self._log("Загрузка конфига отменена")
            return

        try:
            config = load_router_config(file_path)
        except Exception as e:
            self._show_error("Ошибка загрузки конфига", str(e))
            return

        self.loaded_config = config
        self.host_input.setText(config["host"])
        self.username_input.setText(config["username"])
        self.password_input.setText(config["password"])

        token_state = "есть" if config["tunnel_token"].strip() else "нет"

        self._log(
            f"Конфиг загружен: {Path(file_path).name} | "
            f"name={config['name']} | token={token_state}"
        )

    def on_ssh_connect_clicked(self) -> None:
        host = self.host_input.text().strip()
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()

        if not host or not username:
            self._show_error("Ошибка", "Заполни адрес роутера и логин")
            return

        self._log(f"Подключение к {host} по SSH...")

        try:
            info = self.ssh_client.connect(
                host=host,
                username=username,
                password=password,
            )
        except SSHConnectionError as e:
            self._show_error("Ошибка SSH", str(e))
            return

        self._log("[OK] SSH-подключение успешно")
        self._log(f"OpenWrt release: {info.openwrt_release}")
        self._log(f"Architecture: {info.architecture}")
        self._log(f"Package manager: {info.package_manager}")

        if info.package_manager == "none":
            self._show_error(
                "Ошибка",
                "Не удалось определить пакетный менеджер (apk/opkg)"
            )

    def on_install_clicked(self) -> None:
        if not self.ssh_client.is_connected():
            self._show_error("Ошибка", "Сначала подключись по SSH")
            return

        if self.install_thread is not None:
            self._log("Установка уже выполняется")
            return

        self._log("Запускаю установку cloudflared...")
        self.install_button.setEnabled(False)
        self.ssh_button.setEnabled(False)
        self.load_config_button.setEnabled(False)

        thread = QThread()
        worker = InstallWorker(self.installer)

        worker.moveToThread(thread)

        thread.started.connect(worker.run)

        worker.log.connect(self._log)
        worker.error.connect(self._on_install_error)
        worker.success.connect(self._on_install_success)

        worker.finished.connect(self._on_install_worker_finished)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)

        thread.finished.connect(self._on_install_thread_finished)
        thread.finished.connect(thread.deleteLater)

        self.install_thread = thread
        self.install_worker = worker

        thread.start()

    def _on_install_success(self) -> None:
        self._log("[OK] Установка завершена успешно")


    def _on_install_error(self, message: str) -> None:
        self._show_error("Ошибка установки", message)


    def _on_install_worker_finished(self) -> None:
        self.install_button.setEnabled(True)
        self.ssh_button.setEnabled(True)
        self.load_config_button.setEnabled(True)


    def _on_install_thread_finished(self) -> None:
        self.install_thread = None
        self.install_worker = None
    
    def closeEvent(self, event) -> None:
        if self.install_thread is not None and self.install_thread.isRunning():
            self.install_thread.quit()
            self.install_thread.wait(5000)

        self.ssh_client.disconnect()
        super().closeEvent(event)