"""Coleta de informações do Windows usando psutil."""

from __future__ import annotations

import getpass
import os
import platform
import socket
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil


def load_or_create_agent_id(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        value = path.read_text(encoding="utf-8").strip()
        try:
            return str(uuid.UUID(value))
        except ValueError:
            pass
    value = str(uuid.uuid4())
    temporary = path.with_suffix(".tmp")
    temporary.write_text(value, encoding="utf-8")
    os.replace(temporary, path)
    return value


def local_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("1.1.1.1", 80))
        return str(sock.getsockname()[0])
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"
    finally:
        sock.close()


def logged_in_user() -> str:
    users = psutil.users()
    if users:
        return users[0].name
    try:
        return getpass.getuser()
    except OSError:
        return "unknown"


def identity(agent_id: str) -> dict[str, Any]:
    return {
        "agent_id": agent_id,
        "hostname": socket.gethostname(),
        "ip_address": local_ip(),
        "os": platform.system(),
        "os_version": platform.version(),
        "os_release": platform.release(),
        "architecture": platform.machine(),
        "python_version": platform.python_version(),
    }


def disk_usage() -> dict[str, Any]:
    root = Path(os.environ.get("SystemDrive", "C:") + "\\") if os.name == "nt" else Path("/")
    usage = psutil.disk_usage(str(root))
    return {
        "path": str(root),
        "total_bytes": usage.total,
        "used_bytes": usage.used,
        "free_bytes": usage.free,
        "percent": usage.percent,
    }


def heartbeat_snapshot(agent_id: str) -> dict[str, Any]:
    boot_time = psutil.boot_time()
    return {
        **identity(agent_id),
        "status": "online",
        "cpu_percent": psutil.cpu_percent(interval=None),
        "ram_percent": psutil.virtual_memory().percent,
        "disk": disk_usage(),
        "logged_in_user": logged_in_user(),
        "uptime_seconds": max(0, int(time.time() - boot_time)),
        "boot_time": datetime.fromtimestamp(boot_time, timezone.utc).isoformat(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def full_system_info(agent_id: str) -> dict[str, Any]:
    memory = psutil.virtual_memory()
    return {
        **heartbeat_snapshot(agent_id),
        "cpu_count_logical": psutil.cpu_count(logical=True),
        "cpu_count_physical": psutil.cpu_count(logical=False),
        "ram_total_bytes": memory.total,
        "ram_available_bytes": memory.available,
        "platform": platform.platform(),
    }


def process_list(limit: int) -> list[dict[str, Any]]:
    processes: list[dict[str, Any]] = []
    for process in psutil.process_iter(["pid", "name", "username", "memory_percent", "create_time"]):
        try:
            info = process.info
            processes.append(
                {
                    "pid": info["pid"],
                    "name": info.get("name") or "unknown",
                    "username": info.get("username"),
                    "memory_percent": round(float(info.get("memory_percent") or 0), 2),
                    "create_time": info.get("create_time"),
                }
            )
        except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
            continue
        if len(processes) >= limit:
            break
    return processes
