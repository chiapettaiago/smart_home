"""Configuração validada do agente Windows."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv


PACKAGE_DIR = Path(__file__).resolve().parent


def default_data_dir() -> Path:
    if os.name == "nt":
        return Path(os.getenv("PROGRAMDATA", r"C:\ProgramData")) / "SmartHomeAgent"
    return Path.home() / ".smart-home-agent"


def load_environment() -> None:
    explicit_path = os.getenv("AGENT_CONFIG_FILE", "").strip()
    candidates = [Path(explicit_path)] if explicit_path else [default_data_dir() / ".env", PACKAGE_DIR / ".env"]
    for path in candidates:
        if path.is_file():
            load_dotenv(path, override=False)
            return


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    return default if value is None else value.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} deve ser um número inteiro") from exc
    if value < minimum or value > maximum:
        raise ValueError(f"{name} deve estar entre {minimum} e {maximum}")
    return value


def _json_mapping(name: str, default: dict[str, str]) -> dict[str, str]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{name} deve conter um objeto JSON válido") from exc
    if not isinstance(value, dict) or not all(isinstance(key, str) and isinstance(item, str) for key, item in value.items()):
        raise ValueError(f"{name} deve mapear nomes para caminhos em texto")
    return {key.strip().lower(): os.path.expandvars(item.strip()) for key, item in value.items() if key.strip() and item.strip()}


def _csv(name: str) -> set[str]:
    return {item.strip().lower() for item in os.getenv(name, "").split(",") if item.strip()}


def default_programs() -> dict[str, str]:
    program_files = os.getenv("PROGRAMFILES", r"C:\Program Files")
    program_files_x86 = os.getenv("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
    local_app_data = os.getenv("LOCALAPPDATA", "")
    return {
        "chrome": str(Path(program_files) / "Google/Chrome/Application/chrome.exe"),
        "notepad": str(Path(os.getenv("WINDIR", r"C:\Windows")) / "System32/notepad.exe"),
        "vscode": str(Path(local_app_data) / "Programs/Microsoft VS Code/Code.exe"),
        "steam": str(Path(program_files_x86) / "Steam/steam.exe"),
    }


@dataclass(frozen=True, slots=True)
class AgentConfig:
    server_url: str
    websocket_url: str
    agent_token: str = field(repr=False)
    data_dir: Path
    heartbeat_interval: int
    reconnect_min_seconds: int
    reconnect_max_seconds: int
    http_timeout: int
    verify_tls: bool
    log_level: str
    log_max_bytes: int
    log_backup_count: int
    allowed_programs: dict[str, str]
    allowed_processes: set[str]
    allowed_url_hosts: set[str]
    process_list_limit: int

    @property
    def agent_id_file(self) -> Path:
        return self.data_dir / "agent_id"

    @property
    def log_file(self) -> Path:
        return self.data_dir / "logs" / "agent.log"

    @property
    def registration_url(self) -> str:
        return f"{self.server_url}/api/agents/register"

    @classmethod
    def from_env(cls) -> "AgentConfig":
        load_environment()
        server_url = os.getenv("SERVER_URL", "").strip().rstrip("/")
        if not server_url:
            raise ValueError("SERVER_URL não configurada")
        parsed_server = urlparse(server_url)
        if parsed_server.scheme not in {"http", "https"} or not parsed_server.netloc:
            raise ValueError("SERVER_URL deve usar http:// ou https://")

        websocket_url = os.getenv("WEBSOCKET_URL", "").strip()
        if not websocket_url:
            websocket_scheme = "wss" if parsed_server.scheme == "https" else "ws"
            websocket_url = f"{websocket_scheme}://{parsed_server.netloc}/ws/agents"
        parsed_websocket = urlparse(websocket_url)
        if parsed_websocket.scheme not in {"ws", "wss"} or not parsed_websocket.netloc:
            raise ValueError("WEBSOCKET_URL deve usar ws:// ou wss://")

        token = os.getenv("AGENT_TOKEN", "").strip()
        if len(token) < 16:
            raise ValueError("AGENT_TOKEN deve possuir pelo menos 16 caracteres")

        programs = _json_mapping("ALLOWED_PROGRAMS_JSON", default_programs())
        configured_processes = _csv("ALLOWED_PROCESSES")
        program_processes = {Path(path).name.lower() for path in programs.values()}

        config = cls(
            server_url=server_url,
            websocket_url=websocket_url,
            agent_token=token,
            data_dir=Path(os.path.expandvars(os.getenv("AGENT_DATA_DIR", str(default_data_dir())))).expanduser().resolve(),
            heartbeat_interval=_int("HEARTBEAT_INTERVAL_SECONDS", 15, 5, 3600),
            reconnect_min_seconds=_int("RECONNECT_MIN_SECONDS", 2, 1, 300),
            reconnect_max_seconds=_int("RECONNECT_MAX_SECONDS", 60, 2, 3600),
            http_timeout=_int("HTTP_TIMEOUT_SECONDS", 10, 1, 120),
            verify_tls=_bool("VERIFY_TLS", True),
            log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
            log_max_bytes=_int("LOG_MAX_BYTES", 5_242_880, 65_536, 104_857_600),
            log_backup_count=_int("LOG_BACKUP_COUNT", 5, 1, 50),
            allowed_programs=programs,
            allowed_processes=configured_processes | program_processes,
            allowed_url_hosts=_csv("ALLOWED_URL_HOSTS"),
            process_list_limit=_int("PROCESS_LIST_LIMIT", 250, 10, 2000),
        )
        if config.reconnect_max_seconds < config.reconnect_min_seconds:
            raise ValueError("RECONNECT_MAX_SECONDS deve ser maior ou igual a RECONNECT_MIN_SECONDS")
        config.data_dir.mkdir(parents=True, exist_ok=True)
        return config
