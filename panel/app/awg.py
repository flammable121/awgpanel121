from __future__ import annotations

import io
import os
import shlex
import tarfile
from dataclasses import dataclass
import docker
from docker.errors import NotFound, APIError
from .config import Settings


class AwgError(RuntimeError):
    pass


@dataclass
class ExecResult:
    stdout: str
    stderr: str
    exit_code: int


class AwgController:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = docker.from_env()

    def _container(self):
        try:
            return self.client.containers.get(self.settings.awg_container)
        except NotFound as exc:
            raise AwgError(f"Container not found: {self.settings.awg_container}") from exc

    def exec(self, cmd: str, workdir: str | None = None) -> ExecResult:
        container = self._container()
        try:
            result = container.exec_run(cmd, workdir=workdir, demux=True)
        except APIError as exc:
            raise AwgError(str(exc)) from exc
        stdout, stderr = result.output or (b"", b"")
        return ExecResult(
            stdout=(stdout or b"").decode(errors="ignore"),
            stderr=(stderr or b"").decode(errors="ignore"),
            exit_code=result.exit_code,
        )

    def read_config(self) -> str:
        result = self.exec(f"cat {shlex.quote(self.settings.awg_config_path)}")
        if result.exit_code != 0:
            raise AwgError(result.stderr or result.stdout)
        return result.stdout

    def write_config(self, text: str) -> None:
        container = self._container()
        target_dir = os.path.dirname(self.settings.awg_config_path)
        filename = os.path.basename(self.settings.awg_config_path)

        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            data = text.encode()
            info = tarfile.TarInfo(name=filename)
            info.size = len(data)
            info.mode = 0o600
            tar.addfile(info, io.BytesIO(data))
        buf.seek(0)

        ok = container.put_archive(target_dir, buf.read())
        if not ok:
            raise AwgError("Failed to write config to container")

    def apply_config(self) -> None:
        cfg = shlex.quote(self.settings.awg_config_path)
        iface = shlex.quote(self.settings.awg_interface)
        cmd = f"sh -lc 'awg-quick strip {cfg} > /tmp/awg0.conf && awg syncconf {iface} /tmp/awg0.conf'"
        result = self.exec(cmd)
        if result.exit_code == 0:
            return

        # Fallback: restart interface if syncconf fails
        fallback_cmd = (
            "sh -lc '"
            "if [ -d /etc/amnezia/amneziawg ]; then "
            "cp {cfg} /etc/amnezia/amneziawg/{iface}.conf >/tmp/awgpanel_cp.log 2>&1 || true; "
            "fi; "
            "awg-quick down {iface} >/tmp/awgpanel_down.log 2>&1 || "
            "awg-quick down {cfg} >/tmp/awgpanel_down.log 2>&1 || "
            "ip link del {iface} >/tmp/awgpanel_down.log 2>&1 || true; "
            "awg-quick up {iface} >/tmp/awgpanel_up.log 2>&1 || "
            "awg-quick up {cfg} >/tmp/awgpanel_up.log 2>&1"
            "'"
        ).format(cfg=cfg, iface=iface)
        fallback = self.exec(fallback_cmd)
        if fallback.exit_code != 0:
            detail = result.stderr or result.stdout or fallback.stderr or fallback.stdout
            raise AwgError(detail.strip() or "Unable to apply config")

    def genkey(self) -> str:
        result = self.exec("awg genkey")
        if result.exit_code != 0:
            raise AwgError(result.stderr or result.stdout)
        return result.stdout.strip()

    def pubkey(self, private_key: str) -> str:
        cmd = f"sh -lc 'printf %s {shlex.quote(private_key)} | awg pubkey'"
        result = self.exec(cmd)
        if result.exit_code != 0:
            raise AwgError(result.stderr or result.stdout)
        return result.stdout.strip()

    def genpsk(self) -> str:
        result = self.exec("awg genpsk")
        if result.exit_code != 0:
            raise AwgError(result.stderr or result.stdout)
        return result.stdout.strip()

    def show(self) -> str:
        result = self.exec(f"awg show {shlex.quote(self.settings.awg_interface)}")
        if result.exit_code != 0:
            raise AwgError(result.stderr or result.stdout)
        return result.stdout

    def show_dump(self) -> str:
        result = self.exec("awg show all dump")
        if result.exit_code != 0:
            raise AwgError(result.stderr or result.stdout)
        return result.stdout

    def version(self) -> str:
        result = self.exec("awg --version")
        if result.exit_code != 0:
            raise AwgError(result.stderr or result.stdout)
        line = (result.stdout or result.stderr).strip().splitlines()
        return line[0] if line else "—"
