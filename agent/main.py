"""Ponto de entrada do agente Windows."""

from __future__ import annotations

import logging
import signal
import sys
import threading
from typing import Any

import requests

from . import __version__
from .commands import CommandExecutor
from .config import AgentConfig
from .logger import configure_logging
from .system_info import identity, load_or_create_agent_id
from .websocket_client import AgentWebSocketClient


class WindowsAgent:
    def __init__(self, config: AgentConfig, logger: logging.Logger) -> None:
        self.config = config
        self.logger = logger
        self.stop_event = threading.Event()
        self.agent_id = load_or_create_agent_id(config.agent_id_file)
        self.executor = CommandExecutor(config, self.agent_id, logger)
        self.websocket = AgentWebSocketClient(config, self.agent_id, self.executor, self.stop_event, logger)

    def run(self, external_stop_event: threading.Event | None = None) -> None:
        if external_stop_event:
            threading.Thread(
                target=self._watch_external_stop,
                args=(external_stop_event,),
                name="service-stop-watcher",
                daemon=True,
            ).start()
        self.logger.info("Agente iniciado: id=%s versão=%s", self.agent_id, __version__)
        self._register_http()
        try:
            self.websocket.run_forever()
        finally:
            self.logger.info("Agente finalizado")

    def stop(self) -> None:
        self.stop_event.set()
        self.websocket.close()

    def _watch_external_stop(self, event: threading.Event) -> None:
        event.wait()
        self.stop()

    def _register_http(self) -> None:
        payload: dict[str, Any] = {
            **identity(self.agent_id),
            "agent_version": __version__,
            "websocket_protocol_version": 1,
        }
        try:
            response = requests.post(
                self.config.registration_url,
                headers={
                    "Authorization": f"Bearer {self.config.agent_token}",
                    "X-Agent-ID": self.agent_id,
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self.config.http_timeout,
                verify=self.config.verify_tls,
            )
            if response.status_code in {200, 201, 202, 204}:
                self.logger.info("Registro HTTP concluído")
            elif response.status_code == 404:
                self.logger.warning("Endpoint de registro HTTP ainda não existe; seguindo com WebSocket")
            else:
                self.logger.warning("Registro HTTP recusado: status=%s", response.status_code)
        except requests.RequestException as exc:
            self.logger.warning("Registro HTTP indisponível: %s", exc)


def main() -> int:
    try:
        config = AgentConfig.from_env()
    except ValueError as exc:
        print(f"Configuração inválida: {exc}", file=sys.stderr)
        return 2
    logger = configure_logging(config)
    agent = WindowsAgent(config, logger)

    def stop_handler(_signum: int, _frame: Any) -> None:
        logger.info("Sinal de encerramento recebido")
        agent.stop()

    signal.signal(signal.SIGINT, stop_handler)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, stop_handler)
    try:
        agent.run()
    except KeyboardInterrupt:
        agent.stop()
    except Exception:
        logger.exception("Falha fatal do agente")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
