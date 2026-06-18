"""Instalação e remoção assistida do serviço Windows."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .config import PACKAGE_DIR, default_data_dir


def require_windows_admin() -> None:
    if os.name != "nt":
        raise SystemExit("Este instalador deve ser executado no Windows.")
    import ctypes

    if not ctypes.windll.shell32.IsUserAnAdmin():
        raise SystemExit("Abra o PowerShell como Administrador.")


def copy_configuration(source: Path | None) -> Path:
    data_dir = default_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    target = data_dir / ".env"
    source = source or (PACKAGE_DIR / ".env")
    if not source.is_file():
        raise SystemExit(f"Arquivo de configuração não encontrado: {source}")
    shutil.copy2(source, target)
    protect_file(target)
    return target


def protect_file(path: Path) -> None:
    """Restringe o .env ao SYSTEM e aos administradores locais."""
    import ntsecuritycon
    import win32security

    dacl = win32security.ACL()
    system_sid = win32security.CreateWellKnownSid(win32security.WinLocalSystemSid, None)
    administrators_sid = win32security.CreateWellKnownSid(win32security.WinBuiltinAdministratorsSid, None)
    dacl.AddAccessAllowedAce(win32security.ACL_REVISION, ntsecuritycon.FILE_ALL_ACCESS, system_sid)
    dacl.AddAccessAllowedAce(win32security.ACL_REVISION, ntsecuritycon.FILE_ALL_ACCESS, administrators_sid)
    win32security.SetNamedSecurityInfo(
        str(path),
        win32security.SE_FILE_OBJECT,
        win32security.DACL_SECURITY_INFORMATION | win32security.PROTECTED_DACL_SECURITY_INFORMATION,
        None,
        None,
        dacl,
        None,
    )


def service_command(*arguments: str) -> None:
    if getattr(sys, "frozen", False):
        service_executable = Path(sys.executable).resolve().with_name("SmartHomeAgentService.exe")
        subprocess.run([str(service_executable), *arguments], check=True)
        return
    service_script = PACKAGE_DIR / "service.py"
    subprocess.run([sys.executable, str(service_script), *arguments], check=True)


def install(config_path: Path | None) -> None:
    require_windows_admin()
    target = copy_configuration(config_path)
    service_command("install", "--startup", "auto")
    service_command("start")
    print(f"Serviço instalado e iniciado. Configuração: {target}")


def remove() -> None:
    require_windows_admin()
    try:
        service_command("stop")
    except subprocess.CalledProcessError:
        pass
    service_command("remove")
    print("Serviço removido.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    install_parser = subparsers.add_parser("install")
    install_parser.add_argument("--config", type=Path, help="Caminho para o .env configurado")
    subparsers.add_parser("remove")
    args = parser.parse_args()
    if args.action == "install":
        install(args.config)
    else:
        remove()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
