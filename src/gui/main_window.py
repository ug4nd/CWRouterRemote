from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QThread
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.config_loader import load_router_config, save_router_config
from core.models import (
    CloudflaredConfig,
    DeployOptions,
    RouterConfig,
    SSHConfig,
    V2RayAConfig,
)
from gui.install_worker import InstallWorker


MONSTER_STYLE = """
QMainWindow, QWidget {
    background-color: #171a17;
    color: #e8eee6;
    font-size: 13px;
}
QFrame#TopBar {
    background-color: #202620;
    border: 2px solid #3DFF58;
    border-radius: 12px;
}
QGroupBox {
    background-color: #2b302b;
    color: #edf5ea;
    border: 2px solid #2f6f38;
    border-radius: 12px;
    margin-top: 12px;
    padding: 12px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 8px;
    color: #7CFF6B;
    font-weight: bold;
    background-color: #2b302b;
}
QLabel {
    color: #e8eee6;
}
QLabel#TitleLabel {
    color: #7CFF6B;
    font-size: 20px;
    font-weight: bold;
}
QLabel#HintLabel {
    color: #b5c6b2;
}
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox {
    background-color: #f2f4ef;
    color: #111711;
    border: 2px solid #90a090;
    border-radius: 8px;
    padding: 7px;
    selection-background-color: #3DFF58;
    selection-color: #071007;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus {
    border: 2px solid #3DFF58;
}
QPlainTextEdit {
    background-color: #edf0eb;
    color: #111711;
}
QPushButton {
    background-color: #293329;
    color: #f0fff0;
    border: 2px solid #3DFF58;
    border-radius: 10px;
    padding: 9px 14px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #354235;
}
QPushButton:pressed {
    background-color: #3DFF58;
    color: #071007;
}
QPushButton:disabled {
    color: #889088;
    border-color: #4a554a;
    background-color: #2a2e2a;
}
QCheckBox {
    color: #edf5ea;
    spacing: 10px;
    padding: 5px;
}
QCheckBox::indicator {
    width: 22px;
    height: 22px;
    border-radius: 5px;
    border: 2px solid #aebaae;
    background-color: #f2f4ef;
}
QCheckBox::indicator:hover {
    border: 2px solid #7CFF6B;
}
QCheckBox::indicator:checked {
    background-color: #3DFF58;
    border: 2px solid #7CFF6B;
    image: none;
}
QCheckBox::indicator:unchecked {
    background-color: #f2f4ef;
    border: 2px solid #aebaae;
}
"""



def make_config_filename(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", name.strip()).strip("_")
    if not cleaned:
        cleaned = "router"
    return f"{cleaned.lower()}_config.json"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("CFRRemote")
        self.resize(980, 720)
        self.setStyleSheet(MONSTER_STYLE)

        self.worker_thread: QThread | None = None
        self.worker: InstallWorker | None = None
        self.current_json_path: Path | None = None

        self._build_ui()
        self._connect_signals()

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)

        layout = QVBoxLayout(root)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        top_bar = QFrame()
        top_bar.setObjectName("TopBar")
        top_layout = QGridLayout(top_bar)
        top_layout.setContentsMargins(12, 10, 12, 10)

        title = QLabel("CFRRemote")
        title.setObjectName("TitleLabel")

        self.file_name_input = QLineEdit("Router1")
        self.file_name_input.setPlaceholderText("Например: Router1")
        self.file_hint_label = QLabel("Файл: router1_config.json")
        self.file_hint_label.setObjectName("HintLabel")

        self.btn_load_json = QPushButton("Загрузить JSON")
        self.btn_save_json = QPushButton("Сохранить JSON")
        self.btn_deploy = QPushButton("Выполнить")
        self.btn_clear_logs = QPushButton("Очистить лог")

        top_layout.addWidget(title, 0, 0)
        top_layout.addWidget(QLabel("Имя файла"), 0, 1)
        top_layout.addWidget(self.file_name_input, 0, 2)
        top_layout.addWidget(self.file_hint_label, 0, 3)
        top_layout.addWidget(self.btn_load_json, 1, 0)
        top_layout.addWidget(self.btn_save_json, 1, 1)
        top_layout.addWidget(self.btn_deploy, 1, 2)
        top_layout.addWidget(self.btn_clear_logs, 1, 3)

        top_layout.setColumnStretch(2, 1)
        layout.addWidget(top_bar)

        middle = QHBoxLayout()
        middle.setSpacing(10)

        left = QVBoxLayout()
        right = QVBoxLayout()

        self.connection_group = QGroupBox("SSH")
        connection_form = QFormLayout(self.connection_group)

        self.host_input = QLineEdit("192.168.1.1")
        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(22)
        self.username_input = QLineEdit("root")
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_path_input = QLineEdit()
        self.key_path_input.setPlaceholderText("Необязательно")
        self.btn_choose_key = QPushButton("...")

        key_row = QWidget()
        key_layout = QHBoxLayout(key_row)
        key_layout.setContentsMargins(0, 0, 0, 0)
        key_layout.addWidget(self.key_path_input)
        key_layout.addWidget(self.btn_choose_key)

        connection_form.addRow("IP / Host", self.host_input)
        connection_form.addRow("Порт", self.port_input)
        connection_form.addRow("Логин", self.username_input)
        connection_form.addRow("Пароль", self.password_input)
        connection_form.addRow("SSH ключ", key_row)

        self.secret_group = QGroupBox("Конфигурация")
        secret_form = QFormLayout(self.secret_group)

        self.tunnel_token_input = QLineEdit()
        self.tunnel_token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.tunnel_token_input.setPlaceholderText("Cloudflare tunnel token")

        self.vless_input = QTextEdit()
        self.vless_input.setPlaceholderText("vless://...")
        self.vless_input.setFixedHeight(88)

        secret_form.addRow("Cloudflare token", self.tunnel_token_input)
        secret_form.addRow("VLESS / Xray", self.vless_input)

        left.addWidget(self.connection_group)
        left.addWidget(self.secret_group)

        self.actions_group = QGroupBox("Что выполнить")
        actions_layout = QVBoxLayout(self.actions_group)

        self.chk_update_lists = QCheckBox("Обновить список пакетов перед установкой")
        self.chk_update_lists.setChecked(True)
        self.chk_status = QCheckBox("Проверить сервисы после выполнения")
        self.chk_status.setChecked(True)
        self.chk_dry_run = QCheckBox("Тестовый режим: ничего не менять на роутере")

        common_group = QGroupBox("Общее")
        common_layout = QVBoxLayout(common_group)
        common_layout.addWidget(self.chk_update_lists)
        common_layout.addWidget(self.chk_status)
        common_layout.addWidget(self.chk_dry_run)

        cloudflare_group = QGroupBox("Cloudflared")
        cloudflare_layout = QVBoxLayout(cloudflare_group)
        self.chk_cloudflared = QCheckBox("Установить пакет cloudflared")
        self.chk_cloudflared.setChecked(True)
        self.chk_cloudflared_luci = QCheckBox("Установить LuCI-интерфейс для cloudflared")
        self.chk_cloudflared_luci.setChecked(True)
        self.chk_cloudflared_service = QCheckBox("Настроить token и запустить tunnel")
        self.chk_cloudflared_service.setChecked(True)
        cloudflare_layout.addWidget(self.chk_cloudflared)
        cloudflare_layout.addWidget(self.chk_cloudflared_luci)
        cloudflare_layout.addWidget(self.chk_cloudflared_service)

        v2raya_group = QGroupBox("v2rayA")
        v2raya_layout = QVBoxLayout(v2raya_group)
        self.chk_v2raya = QCheckBox("Установить пакет v2rayA")
        self.chk_v2raya.setChecked(True)
        self.chk_v2raya_luci = QCheckBox("Установить LuCI-интерфейс для v2rayA")
        self.chk_v2raya_luci.setChecked(True)
        self.chk_vless_prepare = QCheckBox("Сохранить VLESS/Xray, но VPN НЕ включать")
        self.chk_vless_prepare.setChecked(True)
        v2raya_layout.addWidget(self.chk_v2raya)
        v2raya_layout.addWidget(self.chk_v2raya_luci)
        v2raya_layout.addWidget(self.chk_vless_prepare)

        actions_layout.addWidget(common_group)
        actions_layout.addWidget(cloudflare_group)
        actions_layout.addWidget(v2raya_group)
        actions_layout.addStretch()
        right.addWidget(self.actions_group)

        middle.addLayout(left, 3)
        middle.addLayout(right, 2)
        layout.addLayout(middle)

        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMaximumBlockCount(400)
        self.log_output.setMinimumHeight(185)
        layout.addWidget(QLabel("Логи"))
        layout.addWidget(self.log_output, 1)

        self.status_label = QLabel("Готово")
        layout.addWidget(self.status_label)

    def _connect_signals(self) -> None:
        self.file_name_input.textChanged.connect(self.update_file_hint)
        self.btn_load_json.clicked.connect(self.load_json)
        self.btn_save_json.clicked.connect(self.save_json)
        self.btn_deploy.clicked.connect(self.deploy)
        self.btn_clear_logs.clicked.connect(self.log_output.clear)
        self.btn_choose_key.clicked.connect(self.choose_key)

    def update_file_hint(self) -> None:
        self.file_hint_label.setText(f"Файл: {make_config_filename(self.file_name_input.text())}")

    def choose_key(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Выбрать SSH ключ")
        if path:
            self.key_path_input.setText(path)

    def append_log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_output.appendPlainText(f"[{timestamp}] {message}")

    def collect_config(self) -> RouterConfig:
        cloudflare_enabled = (
            self.chk_cloudflared.isChecked()
            or self.chk_cloudflared_luci.isChecked()
            or self.chk_cloudflared_service.isChecked()
        )
        v2raya_enabled = (
            self.chk_v2raya.isChecked()
            or self.chk_v2raya_luci.isChecked()
            or self.chk_vless_prepare.isChecked()
        )

        return RouterConfig(
            ssh=SSHConfig(
                host=self.host_input.text().strip(),
                port=self.port_input.value(),
                username=self.username_input.text().strip(),
                password=self.password_input.text(),
                ssh_key_path=self.key_path_input.text().strip(),
            ),
            cloudflared=CloudflaredConfig(
                enabled=cloudflare_enabled,
                install_package=self.chk_cloudflared.isChecked(),
                install_luci=self.chk_cloudflared_luci.isChecked(),
                configure_token_service=self.chk_cloudflared_service.isChecked(),
                tunnel_token=self.tunnel_token_input.text().strip(),
            ),
            v2raya=V2RayAConfig(
                enabled=v2raya_enabled,
                install_package=self.chk_v2raya.isChecked(),
                install_luci=self.chk_v2raya_luci.isChecked(),
                core="xray",
                enable_service=False,
                vless_uri=self.vless_input.toPlainText().strip(),
                prepare_vless_config=self.chk_vless_prepare.isChecked(),
            ),
            deploy=DeployOptions(
                dry_run=self.chk_dry_run.isChecked(),
                update_package_lists=self.chk_update_lists.isChecked(),
                check_status_after=self.chk_status.isChecked(),
            ),
        )

    def apply_config(self, config: RouterConfig) -> None:
        self.host_input.setText(config.ssh.host)
        self.port_input.setValue(config.ssh.port)
        self.username_input.setText(config.ssh.username)
        self.password_input.setText(config.ssh.password)
        self.key_path_input.setText(config.ssh.ssh_key_path)

        self.tunnel_token_input.setText(config.cloudflared.tunnel_token)
        self.vless_input.setPlainText(config.v2raya.vless_uri)

        self.chk_cloudflared.setChecked(config.cloudflared.install_package)
        self.chk_cloudflared_luci.setChecked(config.cloudflared.install_luci)
        self.chk_cloudflared_service.setChecked(config.cloudflared.configure_token_service)

        self.chk_v2raya.setChecked(config.v2raya.install_package)
        self.chk_v2raya_luci.setChecked(config.v2raya.install_luci)
        self.chk_vless_prepare.setChecked(config.v2raya.prepare_vless_config)

        self.chk_update_lists.setChecked(config.deploy.update_package_lists)
        self.chk_status.setChecked(config.deploy.check_status_after)
        self.chk_dry_run.setChecked(config.deploy.dry_run)

    def load_json(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Загрузить JSON",
            "",
            "JSON файлы (*.json);;Все файлы (*.*)",
        )
        if not path:
            return

        try:
            config = load_router_config(path)
            self.current_json_path = Path(path)
            self.file_name_input.setText(self.current_json_path.stem.replace("_config", ""))
            self.apply_config(config)
            self.append_log(f"JSON загружен: {Path(path).name}")
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка загрузки", str(exc))

    def save_json(self) -> None:
        try:
            config = self.collect_config()
            filename = make_config_filename(self.file_name_input.text())

            if self.current_json_path:
                initial_dir = str(self.current_json_path.parent)
            else:
                initial_dir = str(Path.cwd())

            default_path = str(Path(initial_dir) / filename)
            path, _ = QFileDialog.getSaveFileName(
                self,
                "Сохранить JSON",
                default_path,
                "JSON файлы (*.json);;Все файлы (*.*)",
            )
            if not path:
                return

            save_router_config(path, config)
            self.current_json_path = Path(path)
            self.append_log(f"JSON сохранён: {Path(path).name}")
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка сохранения", str(exc))

    def deploy(self) -> None:
        config = self.collect_config()

        if self.worker_thread is not None:
            QMessageBox.warning(self, "Занято", "Операция уже выполняется.")
            return

        self.set_controls_enabled(False)
        self.status_label.setText("Выполняется ...")
        self.append_log("Старт.")

        self.worker_thread = QThread(self)
        self.worker = InstallWorker(config)
        self.worker.moveToThread(self.worker_thread)

        self.worker_thread.started.connect(self.worker.run)
        self.worker.log.connect(self.append_log)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)

        self.worker_thread.start()

    def on_worker_finished(self, ok: bool, message: str) -> None:
        self.append_log("Завершено." if ok else "Завершено с ошибкой.")
        self.status_label.setText("Готово" if ok else "Ошибка")

        self.set_controls_enabled(True)
        self.worker = None
        self.worker_thread = None

    def set_controls_enabled(self, enabled: bool) -> None:
        for widget in [
            self.file_name_input,
            self.btn_load_json,
            self.btn_save_json,
            self.btn_deploy,
            self.btn_clear_logs,
            self.btn_choose_key,
            self.connection_group,
            self.secret_group,
            self.actions_group,
        ]:
            widget.setEnabled(enabled)
