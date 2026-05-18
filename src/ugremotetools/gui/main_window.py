from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Callable, Dict, Any, Optional

from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QScrollArea,
    QSplitter,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ugremotetools.router_scripts import (
    backup_script,
    cron_tailscale_script,
    detect_status_script,
    dns_script,
    install_base_script,
    install_tailscale_script,
    install_xray_script,
    redirect_and_udp_block_script,
    remove_v2raya_script,
    tailscale_zone_script,
)
from ugremotetools.ssh_client import RouterSSH
from ugremotetools.vless import build_xray_config, parse_vless_link


class UiSignals(QObject):
    log = Signal(str)
    done = Signal(bool, str)


class LogDialog(QDialog):
    def __init__(self, parent: "MainWindow"):
        super().__init__(parent)
        self.setWindowTitle("Логи выполнения")
        self.resize(980, 640)
        layout = QVBoxLayout(self)
        heading = QLabel("Логи выполнения")
        heading.setFont(QFont("Segoe UI", 16, QFont.Bold))
        heading.setAlignment(Qt.AlignCenter)
        layout.addWidget(heading)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setPlaceholderText("Здесь будет лог выполнения...")
        layout.addWidget(self.text, 1)

    def append(self, text: str) -> None:
        self.text.appendPlainText(text.rstrip())
        self.text.verticalScrollBar().setValue(self.text.verticalScrollBar().maximum())

    def clear(self) -> None:
        self.text.clear()


class FeatureDialog(QDialog):
    def __init__(self, parent: "MainWindow", title: str):
        super().__init__(parent)
        self.main = parent
        self.setWindowTitle(title)
        self.resize(760, 560)
        self.layout = QVBoxLayout(self)
        heading = QLabel(title)
        heading.setFont(QFont("Segoe UI", 16, QFont.Bold))
        heading.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(heading)

    def add_log(self):
        note = QLabel("Во время выполнения откроется отдельное окно с логами.")
        note.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(note)


class TailscaleDialog(FeatureDialog):
    def __init__(self, parent: "MainWindow"):
        super().__init__(parent, "Удалённый доступ Tailscale")

        box = QGroupBox("Tailscale")
        grid = QGridLayout(box)
        self.auth_key = QLineEdit(parent.tailscale_auth.text())
        self.auth_key.setEchoMode(QLineEdit.Password)
        self.auth_key.setPlaceholderText("tskey-auth-... если нужно подключить роутер к сети")
        self.peer_ip = QLineEdit(parent.tailscale_peer_ip.text())
        self.peer_ip.setPlaceholderText("Tailscale IP Windows/peer для wake-ping, например 100.77.73.23")
        grid.addWidget(QLabel("Auth key"), 0, 0)
        grid.addWidget(self.auth_key, 0, 1, 1, 3)
        grid.addWidget(QLabel("Wake peer IP"), 1, 0)
        grid.addWidget(self.peer_ip, 1, 1, 1, 3)
        self.layout.addWidget(box)

        auto_box = QGroupBox("Галки для автоматического выполнения через JSON")
        auto = QVBoxLayout(auto_box)
        self.auto_install_connect = QCheckBox("install_connect: установить Tailscale, если его нет, и подключить по auth key")
        self.auto_install_connect.setChecked(True)
        self.auto_zone = QCheckBox("configure_zone: создать/починить firewall-зону tailscale0")
        self.auto_zone.setChecked(True)
        self.auto_cron = QCheckBox("configure_cron: health/daily + rc.local wake-ping до peer IP")
        self.auto_cron.setChecked(True)
        auto.addWidget(self.auto_install_connect)
        auto.addWidget(self.auto_zone)
        auto.addWidget(self.auto_cron)
        self.layout.addWidget(auto_box)

        buttons = QGroupBox("Ручные действия")
        b = QGridLayout(buttons)
        items = [
            ("Установить/подключить Tailscale", self.install_connect),
            ("Настроить firewall-зону Tailscale", self.zone),
            ("Настроить cron Tailscale", self.cron),
            ("Статус Tailscale", self.status),
            ("Выполнить отмеченное", self.run_checked),
        ]
        for i, (text, fn) in enumerate(items):
            btn = QPushButton(text)
            btn.clicked.connect(fn)
            b.addWidget(btn, i // 2, i % 2)
        self.layout.addWidget(buttons)
        self.add_log()
        self.layout.addStretch(1)

    def _sync(self):
        self.main.tailscale_auth.setText(self.auth_key.text())
        self.main.tailscale_peer_ip.setText(self.peer_ip.text())

    def install_connect(self):
        self._sync()
        self.main.action_install_tailscale()

    def zone(self):
        self.main.action_tailscale_zone()

    def cron(self):
        self.main.action_cron()

    def status(self):
        self.main.action_status()

    def run_checked(self):
        self._sync()
        steps = []
        if self.auto_install_connect.isChecked():
            steps.append(("Установить/подключить Tailscale", lambda ssh: self.main._run_script(ssh, install_tailscale_script(self.auth_key.text().strip()), timeout=420)))
        if self.auto_zone.isChecked():
            steps.append(("Настроить Tailscale-зону", lambda ssh: self.main._run_script(ssh, tailscale_zone_script(), timeout=180)))
        if self.auto_cron.isChecked():
            steps.append(("Настроить cron/rc.local Tailscale", lambda ssh: self.main._run_script(ssh, cron_tailscale_script(self.peer_ip.text().strip()), timeout=180)))
        self.main.run_steps("Tailscale: выполнить отмеченное", steps)


class XrayDialog(FeatureDialog):
    def __init__(self, parent: "MainWindow"):
        super().__init__(parent, "Установка и настройка Xray")

        box = QGroupBox("VLESS / Xray")
        grid = QGridLayout(box)
        self.vless_link = QLineEdit(parent.vless_link.text())
        self.vless_link.setPlaceholderText("vless://UUID@SERVER:PORT?...#name")
        self.xray_port = QSpinBox()
        self.xray_port.setRange(1, 65535)
        self.xray_port.setValue(parent.xray_port.value())
        self.server_ip = QLineEdit(parent.server_ip.text())
        self.server_ip.setPlaceholderText("IP VLESS-сервера для bypass")
        self.block_udp = QCheckBox("Полностью блокировать UDP LAN→WAN")
        self.block_udp.setChecked(parent.block_udp.isChecked())
        grid.addWidget(QLabel("VLESS ссылка"), 0, 0)
        grid.addWidget(self.vless_link, 0, 1, 1, 3)
        grid.addWidget(QLabel("Xray redirect порт"), 1, 0)
        grid.addWidget(self.xray_port, 1, 1)
        grid.addWidget(QLabel("VLESS server IP"), 1, 2)
        grid.addWidget(self.server_ip, 1, 3)
        grid.addWidget(self.block_udp, 2, 0, 1, 4)
        self.layout.addWidget(box)

        auto_box = QGroupBox("Галки для автоматического выполнения через JSON")
        auto = QVBoxLayout(auto_box)
        self.auto_remove_v2raya = QCheckBox("remove_v2raya: удалить v2rayA и LuCI-плагин")
        self.auto_install_xray = QCheckBox("install_xray_core: установить/проверить xray-core")
        self.auto_update_vless = QCheckBox("update_vless: загрузить новый config.json из VLESS-ссылки")
        self.auto_redirect = QCheckBox("configure_redirect: настроить REDIRECT TCP и KillSwitch")
        self.auto_block_udp = QCheckBox("block_udp: полностью заблокировать UDP LAN→WAN")
        for cb in [self.auto_remove_v2raya, self.auto_install_xray, self.auto_update_vless, self.auto_redirect, self.auto_block_udp]:
            cb.setChecked(True)
            auto.addWidget(cb)
        self.layout.addWidget(auto_box)

        buttons = QGroupBox("Ручные действия")
        b = QGridLayout(buttons)
        items = [
            ("Удалить v2rayA", self.remove_v2raya),
            ("Установить/проверить xray-core", self.install_xray),
            ("Сменить VLESS ключ", self.update_vless),
            ("Настроить REDIRECT/KillSwitch", self.redirect),
            ("Backup рабочих конфигов", self.backup),
            ("Выполнить отмеченное", self.run_checked),
        ]
        for i, (text, fn) in enumerate(items):
            btn = QPushButton(text)
            btn.clicked.connect(fn)
            b.addWidget(btn, i // 2, i % 2)
        self.layout.addWidget(buttons)
        self.add_log()
        self.layout.addStretch(1)

    def _sync(self):
        self.main.vless_link.setText(self.vless_link.text())
        self.main.xray_port.setValue(self.xray_port.value())
        self.main.server_ip.setText(self.server_ip.text())
        self.main.block_udp.setChecked(self.block_udp.isChecked())

    def remove_v2raya(self):
        self.main.action_remove_v2raya()

    def install_xray(self):
        self.main.action_install_xray()

    def update_vless(self):
        self._sync()
        self.main.action_update_vless()

    def redirect(self):
        self._sync()
        self.main.action_redirect()

    def backup(self):
        self.main.action_backup()

    def run_checked(self):
        self._sync()
        steps = []
        if self.auto_remove_v2raya.isChecked():
            steps.append(("Удалить v2rayA", lambda ssh: self.main._run_script(ssh, remove_v2raya_script(), timeout=240)))
        if self.auto_install_xray.isChecked():
            steps.append(("Установить/проверить xray-core", lambda ssh: self.main._run_script(ssh, install_xray_script(), timeout=420)))
        if self.auto_update_vless.isChecked():
            steps.append(("Сменить VLESS ключ", self.main._update_vless_step))
        if self.auto_redirect.isChecked():
            steps.append(("Настроить REDIRECT/KillSwitch", lambda ssh: self.main._run_script(ssh, redirect_and_udp_block_script(self.server_ip.text().strip(), self.xray_port.value(), self.auto_block_udp.isChecked()), timeout=180)))
        self.main.run_steps("Xray/VLESS: выполнить отмеченное", steps)


class DnsDialog(FeatureDialog):
    def __init__(self, parent: "MainWindow"):
        super().__init__(parent, "Настройка DNS для Vless")
        box = QGroupBox("DNS настройки")
        grid = QGridLayout(box)
        self.lan_ip = QLineEdit(parent.lan_ip.text())
        self.dns1 = QLineEdit(parent.dns1.text())
        self.dns2 = QLineEdit(parent.dns2.text())
        self.dns3 = QLineEdit(parent.dns3.text())
        grid.addWidget(QLabel("LAN IP роутера"), 0, 0)
        grid.addWidget(self.lan_ip, 0, 1)
        grid.addWidget(QLabel("DNS 1"), 1, 0)
        grid.addWidget(self.dns1, 1, 1)
        grid.addWidget(QLabel("DNS 2"), 1, 2)
        grid.addWidget(self.dns2, 1, 3)
        grid.addWidget(QLabel("DNS 3"), 2, 0)
        grid.addWidget(self.dns3, 2, 1)
        self.layout.addWidget(box)

        auto_box = QGroupBox("Галки для автоматического выполнения через JSON")
        auto = QVBoxLayout(auto_box)
        self.auto_dns = QCheckBox("configure: игнорировать DNS провайдера, поставить 8.8.8.8/8.8.4.4/9.9.9.9 и включить Force-LAN-DNS")
        self.auto_dns.setChecked(True)
        auto.addWidget(self.auto_dns)
        self.layout.addWidget(auto_box)

        buttons = QGroupBox("Ручные действия")
        b = QGridLayout(buttons)
        for i, (text, fn) in enumerate([
            ("Настроить DNS + Force DNS", self.configure),
            ("Статус DNS", self.status),
            ("Выполнить отмеченное", self.run_checked),
        ]):
            btn = QPushButton(text)
            btn.clicked.connect(fn)
            b.addWidget(btn, i // 2, i % 2)
        self.layout.addWidget(buttons)
        self.add_log()
        self.layout.addStretch(1)

    def _sync(self):
        self.main.lan_ip.setText(self.lan_ip.text())
        self.main.dns1.setText(self.dns1.text())
        self.main.dns2.setText(self.dns2.text())
        self.main.dns3.setText(self.dns3.text())

    def configure(self):
        self._sync()
        self.main.action_dns()

    def status(self):
        self.main.action_status()

    def run_checked(self):
        self._sync()
        steps = []
        if self.auto_dns.isChecked():
            steps.append(("Настроить DNS + Force DNS", lambda ssh: self.main._run_script(ssh, dns_script(self.lan_ip.text().strip(), self.dns1.text().strip(), self.dns2.text().strip(), self.dns3.text().strip()), timeout=180)))
        self.main.run_steps("DNS: выполнить отмеченное", steps)


class JsonAutomationDialog(QDialog):
    """Preview JSON and let the user choose which automatic actions to run."""

    def __init__(self, parent: "MainWindow", cfg: Dict[str, Any], path: str):
        super().__init__(parent)
        self.main = parent
        self.cfg = cfg
        self.path = path
        self.setWindowTitle("Автоматическое выполнение JSON")
        self.resize(1120, 720)

        root = QVBoxLayout(self)
        heading = QLabel("JSON config: просмотр и выбор действий")
        heading.setFont(QFont("Segoe UI", 16, QFont.Bold))
        heading.setAlignment(Qt.AlignCenter)
        root.addWidget(heading)

        subtitle = QLabel(f"Файл: {path}")
        subtitle.setAlignment(Qt.AlignCenter)
        root.addWidget(subtitle)

        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter, 1)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("Информация из JSON config"))
        self.json_text = QPlainTextEdit()
        self.json_text.setReadOnly(True)
        self.json_text.setPlainText(json.dumps(cfg, indent=2, ensure_ascii=False))
        left_layout.addWidget(self.json_text, 1)
        splitter.addWidget(left)

        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right = QWidget()
        self.right_layout = QVBoxLayout(right)

        self.checks: Dict[str, QCheckBox] = {}
        self._add_checks()
        self.right_layout.addStretch(1)
        right_scroll.setWidget(right)
        splitter.addWidget(right_scroll)
        splitter.setSizes([620, 480])

        buttons = QHBoxLayout()
        run_btn = QPushButton("Выполнить отмеченное")
        run_btn.clicked.connect(self.run_selected)
        cancel_btn = QPushButton("Закрыть")
        cancel_btn.clicked.connect(self.reject)
        buttons.addStretch(1)
        buttons.addWidget(run_btn)
        buttons.addWidget(cancel_btn)
        root.addLayout(buttons)

    def _check(self, key: str, text: str, checked: bool) -> QCheckBox:
        cb = QCheckBox(text)
        cb.setChecked(bool(checked))
        self.checks[key] = cb
        return cb

    def _add_checks(self) -> None:
        cfg = self.cfg

        backup_box = QGroupBox("Общее")
        bl = QVBoxLayout(backup_box)
        bl.addWidget(self._check("backup", "Backup рабочих конфигов", cfg.get("backup", True)))
        self.right_layout.addWidget(backup_box)

        ts = cfg.get("tailscale", {})
        ts_box = QGroupBox("Удалённый доступ Tailscale")
        tsl = QVBoxLayout(ts_box)
        tsl.addWidget(self._check("tailscale.enabled", "Включить блок Tailscale", ts.get("enabled", False)))
        tsl.addWidget(self._check("tailscale.install_connect", "Установить/подключить Tailscale по auth key", ts.get("install_connect", True)))
        tsl.addWidget(self._check("tailscale.configure_zone", "Настроить firewall-зону tailscale0", ts.get("configure_zone", True)))
        tsl.addWidget(self._check("tailscale.configure_cron", "Настроить rc.local + health/daily wake-ping", ts.get("configure_cron", True)))
        peer = ts.get("wake_peer_ip", self.main.tailscale_peer_ip.text().strip())
        delay = ts.get("wake_delay", 90)
        tsl.addWidget(QLabel(f"Wake peer IP: {peer or 'не указан'} | Delay: {delay} сек."))
        self.right_layout.addWidget(ts_box)

        xr = cfg.get("xray", {})
        xr_box = QGroupBox("Установка и настройка Xray")
        xrl = QVBoxLayout(xr_box)
        xrl.addWidget(self._check("xray.enabled", "Включить блок Xray/VLESS", xr.get("enabled", False)))
        xrl.addWidget(self._check("xray.remove_v2raya", "Удалить v2rayA и LuCI-плагин", xr.get("remove_v2raya", False)))
        xrl.addWidget(self._check("xray.install_xray_core", "Установить/проверить xray-core", xr.get("install_xray_core", True)))
        xrl.addWidget(self._check("xray.update_vless", "Сменить VLESS ключ / загрузить config.json", xr.get("update_vless", True)))
        xrl.addWidget(self._check("xray.configure_redirect", "Настроить REDIRECT TCP / KillSwitch", xr.get("configure_redirect", True)))
        xrl.addWidget(self._check("xray.block_udp", "Полностью заблокировать UDP LAN→WAN", xr.get("block_udp", True)))
        vless_link = str(xr.get("vless_link", ""))
        xrl.addWidget(QLabel("VLESS: " + (vless_link[:72] + "..." if len(vless_link) > 72 else vless_link or "не указан")))
        self.right_layout.addWidget(xr_box)

        dns = cfg.get("dns", {})
        dns_box = QGroupBox("Настройка DNS для Vless")
        dnsl = QVBoxLayout(dns_box)
        dnsl.addWidget(self._check("dns.enabled", "Включить блок DNS", dns.get("enabled", False)))
        dnsl.addWidget(self._check("dns.configure", "Игнорировать DNS провайдера + Force-LAN-DNS", dns.get("configure", True)))
        dnsl.addWidget(QLabel(f"DNS: {dns.get('dns1', self.main.dns1.text())}, {dns.get('dns2', self.main.dns2.text())}, {dns.get('dns3', self.main.dns3.text())}"))
        self.right_layout.addWidget(dns_box)

    def _checked(self, key: str) -> bool:
        return self.checks[key].isChecked()

    def run_selected(self) -> None:
        self.main._apply_config_to_fields(self.cfg)
        steps = self.main._build_json_steps(self.cfg, self._checked)
        self.accept()
        self.main.run_steps("Автоматическое выполнение JSON", steps)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("UGRemoteTools")
        self.resize(1040, 760)
        self.signals = UiSignals()
        self.signals.log.connect(self.append_log)
        self.signals.done.connect(self.on_task_done)
        self.log_dialog: Optional[LogDialog] = None
        self._busy = False
        self.buttons: list[QPushButton] = []
        self._build_ui()
        self._apply_style()

    def _build_ui(self) -> None:
        root = QWidget()
        main = QVBoxLayout(root)

        title = QLabel("UGRemoteTools")
        title.setAlignment(Qt.AlignCenter)
        title.setFont(QFont("Segoe UI", 24, QFont.Bold))
        main.addWidget(title)

        conn_box = QGroupBox("SSH подключение к OpenWrt")
        grid = QGridLayout(conn_box)
        self.host = QLineEdit("192.168.7.1")
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(22)
        self.username = QLineEdit("root")
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        self.lan_ip = QLineEdit("192.168.7.1")
        self.tailscale_auth = QLineEdit()
        self.tailscale_auth.setEchoMode(QLineEdit.Password)
        self.tailscale_auth.setPlaceholderText("tskey-auth-... для подключения Tailscale")
        self.tailscale_peer_ip = QLineEdit("100.77.73.23")
        self.tailscale_peer_ip.setPlaceholderText("Peer IP для wake-ping, например Windows 100.77.73.23")
        grid.addWidget(QLabel("Адрес роутера"), 0, 0)
        grid.addWidget(self.host, 0, 1)
        grid.addWidget(QLabel("SSH порт"), 0, 2)
        grid.addWidget(self.port, 0, 3)
        grid.addWidget(QLabel("Логин"), 1, 0)
        grid.addWidget(self.username, 1, 1)
        grid.addWidget(QLabel("Пароль"), 1, 2)
        grid.addWidget(self.password, 1, 3)
        grid.addWidget(QLabel("LAN IP"), 2, 0)
        grid.addWidget(self.lan_ip, 2, 1)
        grid.addWidget(QLabel("Tailscale auth key"), 3, 0)
        grid.addWidget(self.tailscale_auth, 3, 1, 1, 3)
        grid.addWidget(QLabel("Tailscale wake peer IP"), 4, 0)
        grid.addWidget(self.tailscale_peer_ip, 4, 1, 1, 3)
        main.addWidget(conn_box)

        utility = QGroupBox("Быстрые действия")
        ugrid = QGridLayout(utility)
        quick = [
            ("Проверить SSH", self.action_test_ssh),
            ("Статус роутера", self.action_status),
            ("Backup рабочих конфигов", self.action_backup),
            ("Установить base пакеты", self.action_install_base),
        ]
        for i, (text, fn) in enumerate(quick):
            btn = QPushButton(text)
            btn.clicked.connect(fn)
            self.buttons.append(btn)
            ugrid.addWidget(btn, i // 2, i % 2)
        main.addWidget(utility)

        modules = QGroupBox("Основные функции")
        mgrid = QGridLayout(modules)
        open_buttons = [
            ("Удалённый доступ Tailscale", self.open_tailscale),
            ("Установка и настройка Xray", self.open_xray),
            ("Настройка DNS для Vless", self.open_dns),
        ]
        for i, (text, fn) in enumerate(open_buttons):
            btn = QPushButton(text)
            btn.clicked.connect(fn)
            self.buttons.append(btn)
            mgrid.addWidget(btn, 0, i)
        main.addWidget(modules)

        hidden_box = QGroupBox("Настройка VLESS и DNS")
        hgrid = QGridLayout(hidden_box)
        self.vless_link = QLineEdit()
        self.vless_link.setPlaceholderText("vless://UUID@SERVER:PORT?...#name")
        self.xray_port = QSpinBox()
        self.xray_port.setRange(1, 65535)
        self.xray_port.setValue(12345)
        self.server_ip = QLineEdit()
        self.server_ip.setPlaceholderText("IP VLESS-сервера для bypass")
        self.dns1 = QLineEdit("8.8.8.8")
        self.dns2 = QLineEdit("8.8.4.4")
        self.dns3 = QLineEdit("9.9.9.9")
        self.block_udp = QCheckBox("Полностью блокировать UDP LAN→WAN")
        self.block_udp.setChecked(True)
        hgrid.addWidget(QLabel("VLESS"), 0, 0)
        hgrid.addWidget(self.vless_link, 0, 1, 1, 5)
        hgrid.addWidget(QLabel("Xray порт"), 1, 0)
        hgrid.addWidget(self.xray_port, 1, 1)
        hgrid.addWidget(QLabel("VLESS server IP"), 1, 2)
        hgrid.addWidget(self.server_ip, 1, 3)
        hgrid.addWidget(self.block_udp, 1, 4, 1, 2)
        hgrid.addWidget(QLabel("DNS"), 2, 0)
        hgrid.addWidget(self.dns1, 2, 1)
        hgrid.addWidget(self.dns2, 2, 2)
        hgrid.addWidget(self.dns3, 2, 3)
        main.addWidget(hidden_box)

        auto_box = QGroupBox("Автоматическое выполнение всего через JSON config")
        agrid = QGridLayout(auto_box)
        self.json_path = QLineEdit()
        self.json_path.setPlaceholderText("Путь к router_config.json")
        browse = QPushButton("Выбрать JSON")
        browse.clicked.connect(self.select_json)
        run_auto = QPushButton("Выполнить JSON")
        run_auto.clicked.connect(self.action_run_json)
        sample = QPushButton("Создать пример JSON")
        sample.clicked.connect(self.write_sample_json)
        for b in [browse, run_auto, sample]:
            self.buttons.append(b)
        agrid.addWidget(QLabel("JSON config"), 0, 0)
        agrid.addWidget(self.json_path, 0, 1)
        agrid.addWidget(browse, 0, 2)
        agrid.addWidget(run_auto, 1, 1)
        agrid.addWidget(sample, 1, 2)
        main.addWidget(auto_box)

        main.addStretch(1)
        self.setCentralWidget(root)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QWidget { background: #0f0f0f; color: #e8e8e8; font-family: Segoe UI, Arial; font-size: 13px; }
            QLabel { color: #cfcfcf; }
            QGroupBox { border: 1px solid #28d14f; border-radius: 8px; margin-top: 14px; padding: 10px; }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; color: #28d14f; font-weight: bold; }
            QLineEdit, QSpinBox, QPlainTextEdit { background: #171717; color: #ffffff; border: 1px solid #555; border-radius: 6px; padding: 7px; selection-background-color: #28d14f; }
            QLineEdit:focus, QSpinBox:focus, QPlainTextEdit:focus { border: 1px solid #28d14f; }
            QPushButton { background: #111; color: #ffffff; border: 1px solid #28d14f; border-radius: 8px; padding: 10px; font-weight: bold; }
            QPushButton:hover { background: #19351f; }
            QPushButton:disabled { color: #777; border-color: #555; background: #151515; }
            QCheckBox { color: #e8e8e8; spacing: 8px; }
            """
        )

    def open_tailscale(self):
        TailscaleDialog(self).exec()

    def open_xray(self):
        XrayDialog(self).exec()

    def open_dns(self):
        DnsDialog(self).exec()

    def _ensure_log_dialog(self) -> None:
        if self.log_dialog is None:
            self.log_dialog = LogDialog(self)

    def append_log(self, text: str) -> None:
        self._ensure_log_dialog()
        self.log_dialog.append(text)

    def on_task_done(self, ok: bool, message: str) -> None:
        self._busy = False
        for btn in self.buttons:
            btn.setEnabled(True)
        if ok:
            QMessageBox.information(self, "Готово", message)
        else:
            QMessageBox.critical(self, "Ошибка", message)

    def _conn_args(self):
        return {
            "host": self.host.text().strip(),
            "port": int(self.port.value()),
            "username": self.username.text().strip(),
            "password": self.password.text(),
        }

    def _run_task(self, name: str, func: Callable[[RouterSSH], None]) -> None:
        if self._busy:
            return
        self._busy = True
        for btn in self.buttons:
            btn.setEnabled(False)
        self._ensure_log_dialog()
        self.log_dialog.clear()
        self.log_dialog.show()
        self.log_dialog.raise_()
        self.log_dialog.activateWindow()
        self.append_log(f"\n=== {name} ===")

        def worker():
            try:
                with RouterSSH(**self._conn_args()) as ssh:
                    func(ssh)
                self.signals.done.emit(True, f"{name}: выполнено")
            except Exception as exc:
                self.signals.log.emit(f"ERROR: {exc}")
                self.signals.done.emit(False, str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def run_steps(self, name: str, steps: list[tuple[str, Callable[[RouterSSH], None]]]) -> None:
        if not steps:
            QMessageBox.warning(self, name, "Нет отмеченных действий")
            return
        def task(ssh: RouterSSH):
            for step_name, step_fn in steps:
                self.signals.log.emit(f"\n--- {step_name} ---")
                step_fn(ssh)
        self._run_task(name, task)

    def _run_script(self, ssh: RouterSSH, script: str, timeout: int = 180) -> None:
        res = ssh.run("/bin/sh -s << 'UGREMOTE_EOF'\n" + script + "\nUGREMOTE_EOF", timeout=timeout)
        if res.stdout:
            self.signals.log.emit(res.stdout)
        if res.stderr:
            self.signals.log.emit(res.stderr)
        if not res.ok:
            raise RuntimeError(f"Команда завершилась с кодом {res.code}")

    def _update_vless_step(self, ssh: RouterSSH) -> None:
        vless_text = self.vless_link.text().strip()
        if not vless_text:
            raise RuntimeError("VLESS-ссылка не указана")
        vless = parse_vless_link(vless_text)
        if not self.server_ip.text().strip():
            self.server_ip.setText(vless.server)
        config = build_xray_config(vless, self.xray_port.value())
        self.signals.log.emit(f"Parsed VLESS server: {vless.server}:{vless.port}")
        ssh.upload_text(config, "/tmp/ugremote-xray-config.json")
        script = r'''
set -u
mkdir -p /etc/xray
cp /etc/xray/config.json /etc/xray/config.json.backup-before-update 2>/dev/null || true
cp /tmp/ugremote-xray-config.json /etc/xray/config.json
xray run -test -config /etc/xray/config.json
if [ "$?" -ne 0 ]; then
  echo "Config test failed, restoring backup"
  cp /etc/xray/config.json.backup-before-update /etc/xray/config.json 2>/dev/null || true
  exit 1
fi
uci set xray.enabled.enabled='1' 2>/dev/null || true
uci commit xray 2>/dev/null || true
/etc/init.d/xray enable 2>/dev/null || true
/etc/init.d/xray stop 2>/dev/null || true
/etc/init.d/xray start
sleep 2
ps w | grep -i '[x]ray' || exit 1
curl -x http://127.0.0.1:10809 https://api.ipify.org 2>/dev/null || true
echo ""
echo "VLESS key updated"
'''
        self._run_script(ssh, script, timeout=180)

    def action_test_ssh(self):
        def task(ssh: RouterSSH):
            res = ssh.run("echo connected; uname -a; cat /etc/openwrt_release 2>/dev/null || true")
            self.signals.log.emit(res.stdout + res.stderr)
            if not res.ok:
                raise RuntimeError("SSH test failed")
        self._run_task("Проверить SSH", task)

    def action_status(self):
        self._run_task("Статус роутера", lambda ssh: self._run_script(ssh, detect_status_script()))

    def action_backup(self):
        self._run_task("Backup рабочих конфигов", lambda ssh: self._run_script(ssh, backup_script()))

    def action_remove_v2raya(self):
        self._run_task("Удалить v2rayA", lambda ssh: self._run_script(ssh, remove_v2raya_script(), timeout=240))

    def action_install_base(self):
        self._run_task("Установить base пакеты", lambda ssh: self._run_script(ssh, install_base_script(), timeout=300))

    def action_install_xray(self):
        self._run_task("Установить/проверить xray-core", lambda ssh: self._run_script(ssh, install_xray_script(), timeout=420))

    def action_update_vless(self):
        try:
            parse_vless_link(self.vless_link.text().strip())
        except Exception as exc:
            QMessageBox.critical(self, "VLESS", str(exc))
            return
        self._run_task("Сменить VLESS ключ", self._update_vless_step)

    def action_install_tailscale(self):
        auth_key = self.tailscale_auth.text().strip()
        self._run_task("Установить/подключить Tailscale", lambda ssh: self._run_script(ssh, install_tailscale_script(auth_key), timeout=420))

    def action_dns(self):
        script = dns_script(self.lan_ip.text().strip(), self.dns1.text().strip(), self.dns2.text().strip(), self.dns3.text().strip())
        self._run_task("Настроить DNS + Force DNS", lambda ssh: self._run_script(ssh, script, timeout=180))

    def action_redirect(self):
        server = self.server_ip.text().strip()
        if not server and self.vless_link.text().strip():
            try:
                server = parse_vless_link(self.vless_link.text().strip()).server
                self.server_ip.setText(server)
            except Exception:
                pass
        script = redirect_and_udp_block_script(server, self.xray_port.value(), self.block_udp.isChecked())
        self._run_task("Настроить KillSwitch", lambda ssh: self._run_script(ssh, script, timeout=180))

    def action_tailscale_zone(self):
        self._run_task("Настроить Tailscale-зону", lambda ssh: self._run_script(ssh, tailscale_zone_script(), timeout=180))

    def action_cron(self):
        self._run_task("Настроить cron/rc.local Tailscale", lambda ssh: self._run_script(ssh, cron_tailscale_script(self.tailscale_peer_ip.text().strip()), timeout=180))

    def select_json(self):
        path, _ = QFileDialog.getOpenFileName(self, "Выбери JSON config", "", "JSON files (*.json);;All files (*.*)")
        if not path:
            return
        self.json_path.setText(path)
        try:
            cfg = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception as exc:
            QMessageBox.critical(self, "JSON", f"Не удалось прочитать JSON: {exc}")
            return
        self._apply_config_to_fields(cfg)
        JsonAutomationDialog(self, cfg, path).exec()

    def _sample_config(self) -> Dict[str, Any]:
        return {
            "router": {
                "host": "192.168.7.1",
                "port": 22,
                "username": "root",
                "password": "password_here",
                "lan_ip": "192.168.7.1"
            },
            "backup": True,
            "tailscale": {
                "enabled": True,
                "auth_key": "tskey-auth-...",
                "wake_peer_ip": "100.77.73.23",
                "install_connect": True,
                "configure_zone": True,
                "configure_cron": True
            },
            "xray": {
                "enabled": True,
                "remove_v2raya": True,
                "install_xray_core": True,
                "update_vless": True,
                "vless_link": "vless://UUID@SERVER:PORT?type=tcp&encryption=none&security=reality&pbk=PUBLIC_KEY&fp=chrome&sni=DOMAIN&sid=SHORT_ID&spx=%2F&flow=xtls-rprx-vision#name",
                "xray_port": 12345,
                "configure_redirect": True,
                "block_udp": True,
                "vless_server_ip": "SERVER_IP"
            },
            "dns": {
                "enabled": True,
                "configure": True,
                "dns1": "8.8.8.8",
                "dns2": "8.8.4.4",
                "dns3": "9.9.9.9",
                "force_lan_dns": True
            }
        }

    def write_sample_json(self):
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить пример JSON", "router_config.example.json", "JSON files (*.json)")
        if not path:
            return
        Path(path).write_text(json.dumps(self._sample_config(), indent=2, ensure_ascii=False), encoding="utf-8")
        QMessageBox.information(self, "JSON", f"Пример сохранён:\n{path}")

    def _apply_config_to_fields(self, cfg: Dict[str, Any]) -> None:
        router = cfg.get("router", {})
        self.host.setText(str(router.get("host", self.host.text())))
        self.port.setValue(int(router.get("port", self.port.value())))
        self.username.setText(str(router.get("username", self.username.text())))
        if router.get("password"):
            self.password.setText(str(router.get("password")))
        self.lan_ip.setText(str(router.get("lan_ip", self.lan_ip.text())))

        ts = cfg.get("tailscale", {})
        if ts.get("auth_key"):
            self.tailscale_auth.setText(str(ts.get("auth_key")))
        if ts.get("wake_peer_ip"):
            self.tailscale_peer_ip.setText(str(ts.get("wake_peer_ip")))

        xr = cfg.get("xray", {})
        if xr.get("vless_link"):
            self.vless_link.setText(str(xr.get("vless_link")))
        if xr.get("xray_port"):
            self.xray_port.setValue(int(xr.get("xray_port")))
        if xr.get("vless_server_ip"):
            self.server_ip.setText(str(xr.get("vless_server_ip")))
        self.block_udp.setChecked(bool(xr.get("block_udp", self.block_udp.isChecked())))

        dns = cfg.get("dns", {})
        self.dns1.setText(str(dns.get("dns1", self.dns1.text())))
        self.dns2.setText(str(dns.get("dns2", self.dns2.text())))
        self.dns3.setText(str(dns.get("dns3", self.dns3.text())))

    def _build_json_steps(self, cfg: Dict[str, Any], checked: Optional[Callable[[str], bool]] = None) -> list[tuple[str, Callable[[RouterSSH], None]]]:
        def is_checked(key: str, default: bool) -> bool:
            if checked is None:
                return default
            return checked(key)

        steps: list[tuple[str, Callable[[RouterSSH], None]]] = []
        if is_checked("backup", cfg.get("backup", True)):
            steps.append(("Backup рабочих конфигов", lambda ssh: self._run_script(ssh, backup_script(), timeout=180)))

        ts = cfg.get("tailscale", {})
        if is_checked("tailscale.enabled", bool(ts.get("enabled"))):
            if is_checked("tailscale.install_connect", bool(ts.get("install_connect", True))):
                steps.append(("Tailscale: установить/подключить", lambda ssh: self._run_script(ssh, install_tailscale_script(str(ts.get("auth_key", ""))), timeout=420)))
            if is_checked("tailscale.configure_zone", bool(ts.get("configure_zone", True))):
                steps.append(("Tailscale: firewall-зона", lambda ssh: self._run_script(ssh, tailscale_zone_script(), timeout=180)))
            if is_checked("tailscale.configure_cron", bool(ts.get("configure_cron", True))):
                steps.append(("Tailscale: cron/rc.local", lambda ssh: self._run_script(ssh, cron_tailscale_script(str(ts.get("wake_peer_ip", self.tailscale_peer_ip.text().strip())), int(ts.get("wake_delay", 90))), timeout=180)))

        xr = cfg.get("xray", {})
        if is_checked("xray.enabled", bool(xr.get("enabled"))):
            if is_checked("xray.remove_v2raya", bool(xr.get("remove_v2raya", False))):
                steps.append(("Xray: удалить v2rayA", lambda ssh: self._run_script(ssh, remove_v2raya_script(), timeout=240)))
            if is_checked("xray.install_xray_core", bool(xr.get("install_xray_core", True))):
                steps.append(("Xray: установить/проверить xray-core", lambda ssh: self._run_script(ssh, install_xray_script(), timeout=420)))
            if is_checked("xray.update_vless", bool(xr.get("update_vless", True))):
                steps.append(("Xray: сменить VLESS", self._update_vless_step))
            if is_checked("xray.configure_redirect", bool(xr.get("configure_redirect", True))):
                block_udp = is_checked("xray.block_udp", bool(xr.get("block_udp", True)))
                steps.append(("Xray: REDIRECT/KillSwitch", lambda ssh: self._run_script(ssh, redirect_and_udp_block_script(str(xr.get("vless_server_ip", self.server_ip.text().strip())), int(xr.get("xray_port", self.xray_port.value())), block_udp), timeout=180)))

        dns = cfg.get("dns", {})
        if is_checked("dns.enabled", bool(dns.get("enabled"))) and is_checked("dns.configure", bool(dns.get("configure", True))):
            steps.append(("DNS: peerdns=0 + Force-LAN-DNS", lambda ssh: self._run_script(ssh, dns_script(self.lan_ip.text().strip(), str(dns.get("dns1", self.dns1.text())), str(dns.get("dns2", self.dns2.text())), str(dns.get("dns3", self.dns3.text()))), timeout=180)))

        return steps

    def action_run_json(self):
        path = self.json_path.text().strip()
        if not path:
            QMessageBox.warning(self, "JSON", "Выбери JSON config")
            return
        try:
            cfg = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception as exc:
            QMessageBox.critical(self, "JSON", f"Не удалось прочитать JSON: {exc}")
            return
        self._apply_config_to_fields(cfg)
        JsonAutomationDialog(self, cfg, path).exec()
