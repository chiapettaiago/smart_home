"""Whitelist e execução segura de comandos do agente."""

from __future__ import annotations

import ctypes
import logging
import os
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import psutil

from .config import AgentConfig
from .system_info import full_system_info, process_list


class AllowedCommand(StrEnum):
    SHUTDOWN = "shutdown"
    REBOOT = "reboot"
    LOCK_SCREEN = "lock_screen"
    SLEEP = "sleep"
    LOGOUT = "logout"
    OPEN_PROGRAM = "open_program"
    CLOSE_PROGRAM = "close_program"
    OPEN_URL = "open_url"
    GET_PROCESSES = "get_processes"
    GET_SYSTEM_INFO = "get_system_info"


class CommandValidationError(ValueError):
    pass


class CommandExecutor:
    def __init__(self, config: AgentConfig, agent_id: str, logger: logging.Logger) -> None:
        self.config = config
        self.agent_id = agent_id
        self.logger = logger

    def execute(self, command_value: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            command = AllowedCommand(command_value)
        except ValueError as exc:
            raise CommandValidationError("Comando não permitido") from exc
        if params is None:
            params = {}
        if not isinstance(params, dict):
            raise CommandValidationError("params deve ser um objeto")

        handlers = {
            AllowedCommand.SHUTDOWN: self._shutdown,
            AllowedCommand.REBOOT: self._reboot,
            AllowedCommand.LOCK_SCREEN: self._lock_screen,
            AllowedCommand.SLEEP: self._sleep,
            AllowedCommand.LOGOUT: self._logout,
            AllowedCommand.OPEN_PROGRAM: lambda: self._open_program(params),
            AllowedCommand.CLOSE_PROGRAM: lambda: self._close_program(params),
            AllowedCommand.OPEN_URL: lambda: self._open_url(params),
            AllowedCommand.GET_PROCESSES: self._get_processes,
            AllowedCommand.GET_SYSTEM_INFO: self._get_system_info,
        }
        self.logger.info("Executando comando permitido: %s", command.value)
        result = handlers[command]()
        return {"command": command.value, "success": True, "data": result}

    @staticmethod
    def _require_windows() -> None:
        if os.name != "nt":
            raise RuntimeError("Este comando só pode ser executado no Windows")

    def _shutdown(self) -> dict[str, str]:
        self._require_windows()
        self._exit_windows(0x00000001 | 0x00000004)
        return {"message": "Desligamento solicitado"}

    def _reboot(self) -> dict[str, str]:
        self._require_windows()
        self._exit_windows(0x00000002 | 0x00000004)
        return {"message": "Reinicialização solicitada"}

    def _logout(self) -> dict[str, str]:
        self._require_windows()
        import win32ts

        win32ts.WTSLogoffSession(
            win32ts.WTS_CURRENT_SERVER_HANDLE,
            self._active_session_id(),
            False,
        )
        return {"message": "Logout solicitado"}

    @staticmethod
    def _exit_windows(flags: int) -> None:
        import win32api
        import win32con
        import win32security

        token = win32security.OpenProcessToken(
            win32api.GetCurrentProcess(),
            win32con.TOKEN_ADJUST_PRIVILEGES | win32con.TOKEN_QUERY,
        )
        privilege = win32security.LookupPrivilegeValue(None, win32con.SE_SHUTDOWN_NAME)
        win32security.AdjustTokenPrivileges(token, False, [(privilege, win32con.SE_PRIVILEGE_ENABLED)])
        win32api.ExitWindowsEx(flags, 0)

    def _lock_screen(self) -> dict[str, str]:
        self._require_windows()
        rundll32 = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32" / "rundll32.exe"
        self._launch_in_active_session(rundll32, ["user32.dll,LockWorkStation"])
        return {"message": "Tela bloqueada"}

    def _sleep(self) -> dict[str, str]:
        self._require_windows()
        if not ctypes.windll.powrprof.SetSuspendState(False, True, False):
            raise ctypes.WinError()
        return {"message": "Suspensão solicitada"}

    def _open_program(self, params: dict[str, Any]) -> dict[str, str]:
        self._require_windows()
        name = self._required_string(params, "program", maximum=64).lower()
        path_value = self.config.allowed_programs.get(name)
        if not path_value:
            raise CommandValidationError("Programa não autorizado")
        path = Path(path_value).expanduser().resolve()
        if not path.is_file() or path.suffix.lower() != ".exe":
            raise CommandValidationError("Executável autorizado não encontrado")
        self._launch_in_active_session(path)
        return {"message": f"Programa '{name}' aberto"}

    def _close_program(self, params: dict[str, Any]) -> dict[str, Any]:
        process_name = self._required_string(params, "process", maximum=128).lower()
        if process_name not in self.config.allowed_processes:
            raise CommandValidationError("Processo não autorizado")
        terminated: list[int] = []
        for process in psutil.process_iter(["pid", "name"]):
            try:
                if (process.info.get("name") or "").lower() != process_name:
                    continue
                process.terminate()
                terminated.append(process.pid)
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                continue
        return {"message": "Solicitação de encerramento enviada", "terminated_pids": terminated}

    def _open_url(self, params: dict[str, Any]) -> dict[str, str]:
        self._require_windows()
        url = self._required_string(params, "url", maximum=2048)
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise CommandValidationError("URL deve usar HTTP ou HTTPS")
        if self.config.allowed_url_hosts and parsed.hostname.lower() not in self.config.allowed_url_hosts:
            raise CommandValidationError("Host da URL não autorizado")
        if parsed.username or parsed.password:
            raise CommandValidationError("Credenciais na URL não são permitidas")
        if any(character in url for character in {'"', "\r", "\n", "\t", " "}):
            raise CommandValidationError("URL contém caracteres não permitidos")
        explorer = Path(os.environ.get("WINDIR", r"C:\Windows")) / "explorer.exe"
        self._launch_in_active_session(explorer, [url])
        return {"message": "URL aberta", "host": parsed.hostname}

    def _get_processes(self) -> dict[str, Any]:
        processes = process_list(self.config.process_list_limit)
        return {"count": len(processes), "processes": processes}

    def _get_system_info(self) -> dict[str, Any]:
        return full_system_info(self.agent_id)

    @staticmethod
    def _required_string(params: dict[str, Any], field: str, maximum: int) -> str:
        value = params.get(field)
        if not isinstance(value, str):
            raise CommandValidationError(f"'{field}' deve ser texto")
        value = value.strip()
        if not value or len(value) > maximum or "\x00" in value:
            raise CommandValidationError(f"'{field}' inválido")
        return value

    @staticmethod
    def _quote_windows_argument(value: str) -> str:
        return '"' + value.replace('"', '\\"') + '"'

    def _launch_in_active_session(self, executable: Path, arguments: list[str] | None = None) -> None:
        self._require_windows()
        if not executable.is_file():
            raise RuntimeError(f"Executável não encontrado: {executable}")
        arguments = arguments or []
        command_line = " ".join(
            [self._quote_windows_argument(str(executable)), *(self._quote_windows_argument(item) for item in arguments)]
        )
        try:
            import win32con
            import win32process
            import win32profile
            import win32security
            import win32ts

            session_id = self._active_session_id()
            user_token = win32ts.WTSQueryUserToken(session_id)
            primary_token = win32security.DuplicateTokenEx(
                user_token,
                win32con.MAXIMUM_ALLOWED,
                None,
                win32security.SecurityIdentification,
                win32security.TokenPrimary,
            )
            environment = win32profile.CreateEnvironmentBlock(primary_token, False)
            win32process.CreateProcessAsUser(
                primary_token,
                str(executable),
                command_line,
                None,
                None,
                False,
                win32con.CREATE_UNICODE_ENVIRONMENT | win32con.CREATE_NEW_PROCESS_GROUP,
                environment,
                str(executable.parent),
                win32process.STARTUPINFO(),
            )
        except Exception:
            self.logger.exception("Falha ao iniciar processo na sessão interativa; tentando sessão atual")
            if arguments:
                os.startfile(  # type: ignore[attr-defined]
                    str(executable),
                    arguments=" ".join(self._quote_windows_argument(item) for item in arguments),
                )
            else:
                os.startfile(str(executable))  # type: ignore[attr-defined]

    @staticmethod
    def _active_session_id() -> int:
        import win32ts

        session_id = int(win32ts.WTSGetActiveConsoleSessionId())
        if session_id == 0xFFFFFFFF:
            raise RuntimeError("Nenhuma sessão interativa ativa")
        return session_id
