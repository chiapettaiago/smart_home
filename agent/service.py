"""Serviço Windows baseado em pywin32."""

from __future__ import annotations

import sys
import threading
from pathlib import Path

if getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(sys.executable).resolve().parent))
elif __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import servicemanager
import win32event
import win32service
import win32serviceutil

from agent.config import AgentConfig
from agent.logger import configure_logging
from agent.main import WindowsAgent


class SmartHomeAgentService(win32serviceutil.ServiceFramework):
    _svc_name_ = "SmartHomeWindowsAgent"
    _svc_display_name_ = "Smart Home Windows Agent"
    _svc_description_ = "Cliente seguro do servidor central de automação residencial."

    def __init__(self, args) -> None:
        super().__init__(args)
        self.stop_handle = win32event.CreateEvent(None, 0, 0, None)
        self.stop_event = threading.Event()
        self.agent: WindowsAgent | None = None

    def SvcStop(self) -> None:
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        self.stop_event.set()
        if self.agent:
            self.agent.stop()
        win32event.SetEvent(self.stop_handle)

    def SvcDoRun(self) -> None:
        servicemanager.LogInfoMsg("Smart Home Windows Agent iniciando")
        try:
            config = AgentConfig.from_env()
            logger = configure_logging(config)
            self.agent = WindowsAgent(config, logger)
            self.agent.run(external_stop_event=self.stop_event)
        except Exception as exc:
            servicemanager.LogErrorMsg(f"Falha fatal no Smart Home Windows Agent: {exc}")
            raise
        finally:
            servicemanager.LogInfoMsg("Smart Home Windows Agent finalizado")


if __name__ == "__main__":
    if getattr(sys, "frozen", False) and len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(SmartHomeAgentService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(SmartHomeAgentService)
