from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QThread
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSpinBox,
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


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("CWRouterRemote")
        self.resize(1120, 760)

        self.loaded_config: RouterConfig | None = None
        self.worker_thread: QThread | None = None
        self.worker: InstallWorker | None = None

        self._build_ui()
        self._connect_signals()

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)

        main_layout = QHBoxLayout(root)

        self.sidebar = QFrame()
        self.sidebar.setFrameShape(QFrame.Shape.StyledPanel)
        self.sidebar.setFixedWidth(260)

        sidebar_layout = QVBoxLayout(self.sidebar)

        self.btn_load_json = QPushButton("Загрузить JSON")
        self.btn_save_json = QPushButton("Сохранить JSON")
        self.btn_deploy = QPushButton("Выполнить выбранное")
        self.btn_clear_logs = QPushButton("Очистить лог")

        for button in [
            self.btn_load_json,
            self.btn_save_json,
            self.btn_deploy,
            self.btn_clear_logs,
        ]:
            button.setMinimumHeight(38)
            sidebar_layout.addWidget(button)

        sidebar_layout.addSpacing(12)
        sidebar_layout.addWidget(QLabel("Временные кнопки для тестов"))

        self.btn_test_ssh = QPushButton("1. Проверить SSH")
        self.btn_detect = QPushButton("2. Определить OpenWrt")
        self.btn_install_cf = QPushButton("3. Установить cloudflared")
        self.btn_install_cf_luci = QPushButton("4. Установить LuCI cloudflared")
        self.btn_config_cf = QPushButton("5. Настроить cloudflared")
        self.btn_check_cf = QPushButton("6. Проверить cloudflared")
        self.btn_install_v2 = QPushButton("7. Установить v2rayA")
        self.btn_install_v2_luci = QPushButton("8. Установить LuCI v2rayA")
        self.btn_config_v2 = QPushButton("9. Подготовить VLESS для v2rayA")
        self.btn_check_v2 = QPushButton("10. Проверить v2rayA")

        self.debug_buttons = [
            self.btn_test_ssh,
            self.btn_detect,
            self.btn_install_cf,
            self.btn_install_cf_luci,
            self.btn_config_cf,
            self.btn_check_cf,
            self.btn_install_v2,
            self.btn_install_v2_luci,
            self.btn_config_v2,
            self.btn_check_v2,
        ]

        for button in self.debug_buttons:
            button.setMinimumHeight(32)
            sidebar_layout.addWidget(button)

        sidebar_layout.addStretch()

        self.status_label = QLabel("Готово")
        self.status_label.setWordWrap(True)
        sidebar_layout.addWidget(self.status_label)

        content = QWidget()
        content_layout = QVBoxLayout(content)

        top_layout = QHBoxLayout()

        self.connection_group = QGroupBox("SSH подключение")
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
        self.btn_choose_key = QPushButton("Выбрать ключ")

        key_row = QWidget()
        key_layout = QHBoxLayout(key_row)
        key_layout.setContentsMargins(0, 0, 0, 0)
        key_layout.addWidget(self.key_path_input)
        key_layout.addWidget(self.btn_choose_key)

        connection_form.addRow("IP / Host", self.host_input)
        connection_form.addRow("Порт", self.port_input)
        connection_form.addRow("Логин", self.username_input)
        connection_form.addRow("Пароль / passphrase", self.password_input)
        connection_form.addRow("SSH ключ", key_row)

        self.actions_group = QGroupBox("Что выполнять автоматически")
        actions_layout = QVBoxLayout(self.actions_group)

        self.chk_dry_run = QCheckBox("Только показать команды, ничего не менять")
        self.chk_update_lists = QCheckBox("Обновлять список пакетов перед установкой")
        self.chk_update_lists.setChecked(True)

        self.chk_cloudflared = QCheckBox("Установить cloudflared")
        self.chk_cloudflared.setChecked(True)
        self.chk_cloudflared_luci = QCheckBox("Установить LuCI для cloudflared, если доступно")
        self.chk_cloudflared_luci.setChecked(True)
        self.chk_cloudflared_service = QCheckBox("Настроить cloudflared tunnel token из JSON")
        self.chk_cloudflared_service.setChecked(True)

        self.chk_v2raya = QCheckBox("Установить v2rayA")
        self.chk_v2raya.setChecked(True)
        self.chk_v2raya_luci = QCheckBox("Установить LuCI для v2rayA, если доступно")
        self.chk_v2raya_luci.setChecked(True)
        self.chk_status = QCheckBox("Проверить сервисы после выполнения")
        self.chk_status.setChecked(True)

        for checkbox in [
            self.chk_dry_run,
            self.chk_update_lists,
            self.chk_cloudflared,
            self.chk_cloudflared_luci,
            self.chk_cloudflared_service,
            self.chk_v2raya,
            self.chk_v2raya_luci,
            self.chk_status,
        ]:
            actions_layout.addWidget(checkbox)

        actions_layout.addStretch()

        top_layout.addWidget(self.connection_group, 2)
        top_layout.addWidget(self.actions_group, 2)

        info_group = QGroupBox("JSON конфиг")
        info_layout = QVBoxLayout(info_group)
        self.json_info_label = QLabel(
            "Cloudflare tunnel token и VLESS/Xray ссылка берутся из JSON.\n"
            "В GUI они специально не показываются, чтобы не светить секреты на экране.\n"
            "Кнопка «Сохранить JSON» сохранит текущие SSH-поля и галочки, но секреты из загруженного JSON сохранит тоже."
        )
        self.json_info_label.setWordWrap(True)
        info_layout.addWidget(self.json_info_label)

        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMinimumHeight(350)

        content_layout.addLayout(top_layout)
        content_layout.addWidget(info_group)
        content_layout.addWidget(QLabel("Логи"))
        content_layout.addWidget(self.log_output, 1)

        main_layout.addWidget(self.sidebar)
        main_layout.addWidget(content, 1)

    def _connect_signals(self) -> None:
        self.btn_load_json.clicked.connect(self.load_json)
        self.btn_save_json.clicked.connect(self.save_json)
        self.btn_deploy.clicked.connect(lambda: self.start_action("deploy_selected"))
        self.btn_clear_logs.clicked.connect(self.log_output.clear)
        self.btn_choose_key.clicked.connect(self.choose_key)

        self.btn_test_ssh.clicked.connect(lambda: self.start_action("test_ssh"))
        self.btn_detect.clicked.connect(lambda: self.start_action("detect_system"))
        self.btn_install_cf.clicked.connect(lambda: self.start_action("install_cloudflared"))
        self.btn_install_cf_luci.clicked.connect(lambda: self.start_action("install_cloudflared_luci"))
        self.btn_config_cf.clicked.connect(lambda: self.start_action("configure_cloudflared"))
        self.btn_check_cf.clicked.connect(lambda: self.start_action("check_cloudflared"))
        self.btn_install_v2.clicked.connect(lambda: self.start_action("install_v2raya"))
        self.btn_install_v2_luci.clicked.connect(lambda: self.start_action("install_v2raya_luci"))
        self.btn_config_v2.clicked.connect(lambda: self.start_action("configure_v2raya"))
        self.btn_check_v2.clicked.connect(lambda: self.start_action("check_v2raya"))

        self.chk_cloudflared.toggled.connect(self._sync_checkbox_state)
        self.chk_v2raya.toggled.connect(self._sync_checkbox_state)
        self._sync_checkbox_state()

    def _sync_checkbox_state(self) -> None:
        self.chk_cloudflared_luci.setEnabled(True)
        self.chk_cloudflared_service.setEnabled(True)

        v2raya_enabled = self.chk_v2raya.isChecked()
        self.chk_v2raya_luci.setEnabled(v2raya_enabled)

    def choose_key(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Выбрать SSH ключ")
        if path:
            self.key_path_input.setText(path)

    def append_log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_output.appendPlainText(f"[{timestamp}] {message}")

    def collect_config(self) -> RouterConfig:
        base_config = self.loaded_config or RouterConfig()

        return RouterConfig(
            name=base_config.name,
            ssh=SSHConfig(
                host=self.host_input.text().strip(),
                port=self.port_input.value(),
                username=self.username_input.text().strip(),
                password=self.password_input.text(),
                ssh_key_path=self.key_path_input.text().strip(),
                connect_timeout=base_config.ssh.connect_timeout,
                command_timeout=base_config.ssh.command_timeout,
            ),
            cloudflared=CloudflaredConfig(
                enabled=(
                    self.chk_cloudflared.isChecked()
                    or self.chk_cloudflared_luci.isChecked()
                    or self.chk_cloudflared_service.isChecked()
                ),
                install_package=self.chk_cloudflared.isChecked(),
                install_luci=self.chk_cloudflared_luci.isChecked(),
                configure_token_service=self.chk_cloudflared_service.isChecked(),
                tunnel_token=base_config.cloudflared.tunnel_token,
                service_name=base_config.cloudflared.service_name,
                token_path=base_config.cloudflared.token_path,
                init_script_path=base_config.cloudflared.init_script_path,
            ),
            v2raya=V2RayAConfig(
                enabled=self.chk_v2raya.isChecked(),
                install_package=self.chk_v2raya.isChecked(),
                install_luci=self.chk_v2raya_luci.isChecked(),
                core=base_config.v2raya.core or "xray",
                enable_service=base_config.v2raya.enable_service,
                vless_uri=base_config.v2raya.vless_uri,
                prepare_vless_config=base_config.v2raya.prepare_vless_config,
                prepared_config_path=base_config.v2raya.prepared_config_path,
            ),
            deploy=DeployOptions(
                dry_run=self.chk_dry_run.isChecked(),
                update_package_lists=self.chk_update_lists.isChecked(),
                detect_only=False,
                check_status_after=self.chk_status.isChecked(),
            ),
        )

    def apply_config(self, config: RouterConfig) -> None:
        self.loaded_config = config

        self.host_input.setText(config.ssh.host)
        self.port_input.setValue(config.ssh.port)
        self.username_input.setText(config.ssh.username)
        self.password_input.setText(config.ssh.password)
        self.key_path_input.setText(config.ssh.ssh_key_path)

        self.chk_cloudflared.setChecked(config.cloudflared.enabled)
        self.chk_cloudflared_luci.setChecked(config.cloudflared.install_luci)
        self.chk_cloudflared_service.setChecked(config.cloudflared.configure_token_service)

        self.chk_v2raya.setChecked(config.v2raya.enabled)
        self.chk_v2raya_luci.setChecked(config.v2raya.install_luci)

        self.chk_dry_run.setChecked(config.deploy.dry_run)
        self.chk_update_lists.setChecked(config.deploy.update_package_lists)
        self.chk_status.setChecked(config.deploy.check_status_after)

        self._sync_checkbox_state()

    def load_json(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Загрузить JSON роутера",
            "",
            "JSON файлы (*.json);;Все файлы (*.*)",
        )
        if not path:
            return

        try:
            config = load_router_config(path)
            self.apply_config(config)
            self.append_log(f"JSON загружен: {path}")
            if config.cloudflared.tunnel_token:
                self.append_log("Cloudflare tunnel token найден в JSON.")
            else:
                self.append_log("Cloudflare tunnel token в JSON пустой.")
            if config.v2raya.vless_uri:
                self.append_log("VLESS/Xray ссылка найдена в JSON. Автоимпорт пока отключен.")
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка загрузки", str(exc))

    def save_json(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить JSON роутера",
            "router.json",
            "JSON файлы (*.json);;Все файлы (*.*)",
        )
        if not path:
            return

        try:
            config = self.collect_config()
            save_router_config(path, config)
            self.loaded_config = config
            self.append_log(f"JSON сохранён: {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка сохранения", str(exc))

    def start_action(self, action: str) -> None:
        config = self.collect_config()
        self.start_worker(config, action)

    def start_worker(self, config: RouterConfig, action: str) -> None:
        if self.worker_thread is not None:
            QMessageBox.warning(self, "Занято", "Уже выполняется другая операция.")
            return

        # Для одиночных тестов валидирует backend, потому что некоторым действиям не нужен token.
        self.set_controls_enabled(False)
        self.status_label.setText("Выполняется ...")
        self.append_log(f"Старт действия: {action}")

        self.worker_thread = QThread(self)
        self.worker = InstallWorker(config, action=action)
        self.worker.moveToThread(self.worker_thread)

        self.worker_thread.started.connect(self.worker.run)
        self.worker.log.connect(self.append_log)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)

        self.worker_thread.start()

    def on_worker_finished(self, ok: bool, message: str) -> None:
        self.append_log("Операция завершена." if ok else f"Операция завершилась ошибкой: {message}")
        self.status_label.setText("Готово" if ok else "Ошибка")

        self.set_controls_enabled(True)

        self.worker = None
        self.worker_thread = None

    def set_controls_enabled(self, enabled: bool) -> None:
        for widget in [
            self.btn_load_json,
            self.btn_save_json,
            self.btn_deploy,
            self.btn_clear_logs,
            self.btn_choose_key,
            self.connection_group,
            self.actions_group,
        ] + self.debug_buttons:
            widget.setEnabled(enabled)

        if enabled:
            self._sync_checkbox_state()
