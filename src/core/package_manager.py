from __future__ import annotations

from dataclasses import dataclass

from core.ssh_client import SSHClient


@dataclass
class SystemInfo:
    package_manager: str
    openwrt_release: str
    architecture: str
    kernel: str


class PackageManager:
    def __init__(self, ssh: SSHClient):
        self.ssh = ssh

    def detect_system(self) -> SystemInfo:
        command = r"""
PM="none"
if command -v apk >/dev/null 2>&1; then
  PM="apk"
elif command -v opkg >/dev/null 2>&1; then
  PM="opkg"
fi

OPENWRT_RELEASE="$(cat /etc/openwrt_release 2>/dev/null || true)"
ARCH="$(uname -m 2>/dev/null || true)"
KERNEL="$(uname -r 2>/dev/null || true)"

printf 'PM=%s\n' "$PM"
printf 'ARCH=%s\n' "$ARCH"
printf 'KERNEL=%s\n' "$KERNEL"
printf '%s\n' "$OPENWRT_RELEASE"
"""
        result = self.ssh.run_checked(command, timeout=30)

        lines = result.stdout.splitlines()
        pm = "none"
        arch = ""
        kernel = ""
        release_lines: list[str] = []

        for line in lines:
            if line.startswith("PM="):
                pm = line.split("=", 1)[1].strip()
            elif line.startswith("ARCH="):
                arch = line.split("=", 1)[1].strip()
            elif line.startswith("KERNEL="):
                kernel = line.split("=", 1)[1].strip()
            else:
                release_lines.append(line)

        return SystemInfo(
            package_manager=pm,
            openwrt_release="\n".join(release_lines).strip(),
            architecture=arch,
            kernel=kernel,
        )

    def update(self, pm: str) -> None:
        self.ssh.logger("Обновляю список пакетов ...")
        if pm == "apk":
            self.ssh.run_checked("apk update", timeout=180)
        elif pm == "opkg":
            self.ssh.run_checked("opkg update", timeout=180)
        else:
            raise RuntimeError(f"Неизвестный пакетный менеджер: {pm}")

    def install(self, pm: str, packages: list[str], required: bool = True) -> None:
        if not packages:
            return

        package_list = " ".join(packages)
        self.ssh.logger(f"Устанавливаю: {package_list}")

        if pm == "apk":
            command = f"apk add {package_list}"
        elif pm == "opkg":
            command = f"opkg install {package_list}"
        else:
            raise RuntimeError(f"Неизвестный пакетный менеджер: {pm}")

        if required:
            self.ssh.run_checked(command, timeout=420)
            self.ssh.logger(f"Готово: {package_list}")
        else:
            result = self.ssh.run_command(command, timeout=420)
            if result.ok:
                self.ssh.logger(f"Готово: {package_list}")
            else:
                self.ssh.logger(f"Опциональный пакет не установлен: {package_list}")
