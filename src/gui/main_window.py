from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QThread, Qt
from PySide6.QtGui import QIntValidator
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


APP_STYLE = """
QMainWindow, QWidget {
    background-color: #202020;
    color: #eeeeee;
    font-size: 13px;
}
QFrame#TopBar {
    background-color: #121612;
    border: 1px solid #3DFF58;
    border-radius: 10px;
}
QLabel {
    color: #d7d7d7;
    background-color: transparent;
}
QLabel#TitleLabel {
    color: #7CFF6B;
    font-size: 21px;
    font-weight: bold;
}
QLabel#HintLabel {
    color: #b8c7b6;
}
QGroupBox {
    background-color: #303030;
    color: #eeeeee;
    border: 1px solid #4f5c4f;
    border-radius: 10px;
    margin-top: 12px;
    padding: 12px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #d7d7d7;
    font-weight: bold;
    background-color: #303030;
}
QLineEdit, QPlainTextEdit {
    background-color: #303030;
    color: #eeeeee;
    border: 1px solid #6a6a6a;
    border-radius: 7px;
    padding: 7px;
    selection-background-color: #3DFF58;
    selection-color: #101410;
}
QLineEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #3DFF58;
}
QPushButton {
    background-color: #263026;
    color: #eeeeee;
    border: 1px solid #3DFF58;
    border-radius: 8px;
    padding: 9px 12px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #2f3c2f;
}
QPushButton:pressed {
    background-color: #3DFF58;
    color: #101410;
}
QPushButton:disabled {
    color: #808a80;
    border-color: #465046;
    background-color: #252a25;
}
QCheckBox {
    color: #eeeeee;
    spacing: 8px;
    padding: 4px;
}
QCheckBox:disabled {
    color: #888888;
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
        self.resize(980, 760)
        self.setStyleSheet(APP_STYLE)

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
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.file_name_input = QLineEdit("Router1")
        self.file_name_input.setPlaceholderText("Например: Router1")
        self.file_name_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.file_hint_label = QLabel("Файл: router1_config.json")
        self.file_hint_label.setObjectName("HintLabel")
        self.file_hint_label.setMinimumWidth(260)
        self.file_hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.btn_load_json = QPushButton("Загрузить JSON")
        self.btn_save_json = QPushButton("Сохранить JSON")
        self.btn_deploy = QPushButton("Установить и запустить")
        self.btn_clear_logs = QPushButton("Очистить лог")

        top_layout.addWidget(title, 0, 0)
        file_name_label = QLabel("Имя файла")
        file_name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top_layout.addWidget(file_name_label, 0, 1)
        top_layout.addWidget(self.file_name_input, 0, 2)
        top_layout.addWidget(self.file_hint_label, 0, 3)
        top_layout.addWidget(self.btn_load_json, 1, 0)
        top_layout.addWidget(self.btn_save_json, 1, 1)
        top_layout.addWidget(self.btn_deploy, 1, 2)
        top_layout.addWidget(self.btn_clear_logs, 1, 3)
        top_layout.setColumnStretch(0, 1)
        top_layout.setColumnStretch(2, 2)
        top_layout.setColumnStretch(3, 2)

        layout.addWidget(top_bar)

        middle = QHBoxLayout()
        middle.setSpacing(10)

        self.connection_group = QGroupBox("SSH")
        connection_form = QFormLayout(self.connection_group)

        self.host_input = QLineEdit("192.168.1.1")
        self.port_input = QLineEdit("22")
        self.port_input.setValidator(QIntValidator(1, 65535, self))
        self.username_input = QLineEdit("root")
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_path_input = QLineEdit()
        self.key_path_input.setPlaceholderText("Необязательно")
        self.btn_choose_key = QPushButton("...")

        key_row = QWidget()
        key_row.setStyleSheet("background-color: transparent;")
        key_layout = QHBoxLayout(key_row)
        key_layout.setContentsMargins(0, 0, 0, 0)
        key_layout.setSpacing(6)
        key_layout.addWidget(self.key_path_input)
        key_layout.addWidget(self.btn_choose_key)

        connection_form.addRow("IP / Host", self.host_input)
        connection_form.addRow("Порт", self.port_input)
        connection_form.addRow("Логин", self.username_input)
        connection_form.addRow("Пароль", self.password_input)
        connection_form.addRow("SSH ключ", key_row)

        self.cloudflare_group = QGroupBox("Cloudflare Tunnel")
        cloudflare_form = QFormLayout(self.cloudflare_group)

        self.tunnel_token_input = QLineEdit()
        self.tunnel_token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.tunnel_token_input.setPlaceholderText("Tunnel token из Cloudflare Dashboard")
        cloudflare_form.addRow("Tunnel token", self.tunnel_token_input)

        self.ip_check_group = QGroupBox("Проверить IP адрес роутера через VPN")
        ip_check_layout = QVBoxLayout(self.ip_check_group)

        self.public_ip_output = QLineEdit()
        self.public_ip_output.setReadOnly(True)
        self.public_ip_output.setPlaceholderText("После проверки здесь появится внешний IP роутера")

        self.btn_check_ip = QPushButton("Проверить IP")
        self.btn_check_ip.setMinimumHeight(38)

        ip_check_layout.addWidget(self.btn_check_ip)
        ip_check_layout.addWidget(QLabel("IP адрес роутера"))
        ip_check_layout.addWidget(self.public_ip_output)

        left = QVBoxLayout()
        left.addWidget(self.connection_group)
        left.addWidget(self.cloudflare_group)
        left.addWidget(self.ip_check_group)

        self.actions_group = QGroupBox("Что сделать")
        actions_layout = QVBoxLayout(self.actions_group)

        common_group = QGroupBox("Общее")
        common_layout = QVBoxLayout(common_group)

        self.chk_update_lists = QCheckBox("Обновить список пакетов")
        self.chk_update_lists.setChecked(True)
        self.chk_status = QCheckBox("Проверить после выполнения")
        self.chk_status.setChecked(True)
        self.chk_dry_run = QCheckBox("Тестовый режим: ничего не менять")

        common_layout.addWidget(self.chk_update_lists)
        common_layout.addWidget(self.chk_status)
        common_layout.addWidget(self.chk_dry_run)

        cloudflared_group = QGroupBox("cloudflared")
        cloudflared_layout = QVBoxLayout(cloudflared_group)

        self.chk_cloudflared = QCheckBox("Установить cloudflared")
        self.chk_cloudflared.setChecked(True)
        self.chk_cloudflared_luci = QCheckBox("Установить LuCI cloudflared")
        self.chk_cloudflared_luci.setChecked(True)
        self.chk_cloudflared_service = QCheckBox("Настроить и запустить Cloudflare Tunnel")
        self.chk_cloudflared_service.setChecked(True)

        cloudflared_layout.addWidget(self.chk_cloudflared)
        cloudflared_layout.addWidget(self.chk_cloudflared_luci)
        cloudflared_layout.addWidget(self.chk_cloudflared_service)

        v2raya_group = QGroupBox("v2rayA")
        v2raya_layout = QVBoxLayout(v2raya_group)

        self.chk_v2raya = QCheckBox("Установить v2rayA")
        self.chk_v2raya.setChecked(True)
        self.chk_v2raya_luci = QCheckBox("Установить LuCI v2rayA")
        self.chk_v2raya_luci.setChecked(True)
        self.chk_v2raya_start = QCheckBox("Запустить v2rayA web UI")
        self.chk_v2raya_start.setChecked(True)

        v2raya_layout.addWidget(self.chk_v2raya)
        v2raya_layout.addWidget(self.chk_v2raya_luci)
        v2raya_layout.addWidget(self.chk_v2raya_start)

        actions_layout.addWidget(common_group)
        actions_layout.addWidget(cloudflared_group)
        actions_layout.addWidget(v2raya_group)

        note = QLabel(
            "VLESS ключи и VPN-режимы здесь не настраиваются.\n"
            "После установки зайди в v2rayA через Cloudflare route и настрой вручную."
        )
        note.setWordWrap(True)
        actions_layout.addWidget(note)
        actions_layout.addStretch()

        middle.addLayout(left, 3)
        middle.addWidget(self.actions_group, 2)
        layout.addLayout(middle)

        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMaximumBlockCount(300)
        self.log_output.setMinimumHeight(170)

        layout.addWidget(QLabel("Логи"))
        layout.addWidget(self.log_output, 1)

        self.status_label = QLabel("Готово")
        layout.addWidget(self.status_label)

    def _connect_signals(self) -> None:
        self.file_name_input.textChanged.connect(self.update_file_hint)
        self.btn_load_json.clicked.connect(self.load_json)
        self.btn_save_json.clicked.connect(self.save_json)
        self.btn_deploy.clicked.connect(lambda: self.start_action("deploy"))
        self.btn_check_ip.clicked.connect(lambda: self.start_action("check_public_ip"))
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
            or self.chk_v2raya_start.isChecked()
        )

        return RouterConfig(
            ssh=SSHConfig(
                host=self.host_input.text().strip(),
                port=int(self.port_input.text().strip() or "22"),
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
                enable_service=self.chk_v2raya_start.isChecked(),
            ),
            deploy=DeployOptions(
                dry_run=self.chk_dry_run.isChecked(),
                update_package_lists=self.chk_update_lists.isChecked(),
                check_status_after=self.chk_status.isChecked(),
                public_ip_service_url="https://api.ipify.org",
            ),
        )

    def apply_config(self, config: RouterConfig) -> None:
        self.host_input.setText(config.ssh.host)
        self.port_input.setText(str(config.ssh.port))
        self.username_input.setText(config.ssh.username)
        self.password_input.setText(config.ssh.password)
        self.key_path_input.setText(config.ssh.ssh_key_path)

        self.tunnel_token_input.setText(config.cloudflared.tunnel_token)

        self.chk_cloudflared.setChecked(config.cloudflared.install_package)
        self.chk_cloudflared_luci.setChecked(config.cloudflared.install_luci)
        self.chk_cloudflared_service.setChecked(config.cloudflared.configure_token_service)

        self.chk_v2raya.setChecked(config.v2raya.install_package)
        self.chk_v2raya_luci.setChecked(config.v2raya.install_luci)
        self.chk_v2raya_start.setChecked(config.v2raya.enable_service)

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

            initial_dir = str(self.current_json_path.parent) if self.current_json_path else str(Path.cwd())
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
        self.start_action("deploy")

    def start_action(self, action: str) -> None:
        config = self.collect_config()

        if self.worker_thread is not None:
            QMessageBox.warning(self, "Занято", "Операция уже выполняется.")
            return

        self.set_controls_enabled(False)
        self.status_label.setText("Выполняется ...")
        self.append_log("Старт.")

        self.worker_thread = QThread(self)
        self.worker = InstallWorker(config, action=action)
        self.worker.moveToThread(self.worker_thread)

        self.worker_thread.started.connect(self.worker.run)
        self.worker.log.connect(self.append_log)
        self.worker.result.connect(self.on_worker_result)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)

        self.worker_thread.start()

    def on_worker_result(self, action: str, value: str) -> None:
        if action == "check_public_ip":
            self.public_ip_output.setText(value)

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
            self.btn_check_ip,
            self.btn_clear_logs,
            self.btn_choose_key,
            self.connection_group,
            self.cloudflare_group,
            self.ip_check_group,
            self.actions_group,
        ]:
            widget.setEnabled(enabled)
