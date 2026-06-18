"""Cliente WebSocket resiliente e autenticado."""

from __future__ import annotations

import json
import logging
import random
import ssl
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

import websocket

from .commands import CommandExecutor, CommandValidationError
from .config import AgentConfig
from .heartbeat import HeartbeatWorker
from .system_info import heartbeat_snapshot, identity


MAX_MESSAGE_BYTES = 1_048_576


class AgentWebSocketClient:
    def __init__(
        self,
        config: AgentConfig,
        agent_id: str,
        command_executor: CommandExecutor,
        stop_event: threading.Event,
        logger: logging.Logger,
    ) -> None:
        self.config = config
        self.agent_id = agent_id
        self.command_executor = command_executor
        self.stop_event = stop_event
        self.logger = logger
        self.connected = threading.Event()
        self._send_lock = threading.Lock()
        self._socket_lock = threading.Lock()
        self._socket: websocket.WebSocketApp | None = None
        self._workers = ThreadPoolExecutor(max_workers=2, thread_name_prefix="command")
        self._reconnect_delay = config.reconnect_min_seconds
        self._heartbeat = HeartbeatWorker(
            agent_id=agent_id,
            interval_seconds=config.heartbeat_interval,
            sender=self.send_json,
            stop_event=stop_event,
            logger=logger,
        )

    def run_forever(self) -> None:
        self._heartbeat.start()
        while not self.stop_event.is_set():
            app = self._build_app()
            with self._socket_lock:
                self._socket = app
            try:
                self.logger.info("Conectando ao WebSocket %s", self.config.websocket_url)
                app.run_forever(
                    ping_interval=30,
                    ping_timeout=10,
                    sslopt={"cert_reqs": ssl.CERT_REQUIRED if self.config.verify_tls else ssl.CERT_NONE},
                )
            except Exception:
                self.logger.exception("Falha no loop WebSocket")
            finally:
                self.connected.clear()
                with self._socket_lock:
                    self._socket = None
            if self.stop_event.is_set():
                break
            wait_seconds = min(self._reconnect_delay, self.config.reconnect_max_seconds) + random.uniform(0, 1)
            self.logger.warning("WebSocket desconectado; nova tentativa em %.1fs", wait_seconds)
            self.stop_event.wait(wait_seconds)
            self._reconnect_delay = min(self._reconnect_delay * 2, self.config.reconnect_max_seconds)
        self._workers.shutdown(wait=False, cancel_futures=True)

    def close(self) -> None:
        self.connected.clear()
        with self._socket_lock:
            if self._socket:
                self._socket.close()

    def send_json(self, message: dict[str, Any]) -> bool:
        if not self.connected.is_set():
            return False
        encoded = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
        try:
            with self._send_lock, self._socket_lock:
                if not self._socket or not self.connected.is_set():
                    return False
                self._socket.send(encoded)
            return True
        except Exception:
            self.connected.clear()
            self.logger.exception("Falha ao enviar mensagem WebSocket")
            return False

    def _build_app(self) -> websocket.WebSocketApp:
        return websocket.WebSocketApp(
            self.config.websocket_url,
            header=[
                f"Authorization: Bearer {self.config.agent_token}",
                f"X-Agent-ID: {self.agent_id}",
            ],
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )

    def _on_open(self, _socket: websocket.WebSocketApp) -> None:
        self.connected.set()
        self._reconnect_delay = self.config.reconnect_min_seconds
        self.logger.info("WebSocket conectado e autenticado")
        self.send_json(
            {
                "type": "hello",
                "payload": {
                    **identity(self.agent_id),
                    "capabilities": [command.value for command in self.command_executor_commands()],
                    "protocol_version": 1,
                },
            }
        )
        self.send_json({"type": "heartbeat", "payload": heartbeat_snapshot(self.agent_id)})

    def _on_message(self, _socket: websocket.WebSocketApp, raw_message: str | bytes) -> None:
        if isinstance(raw_message, bytes):
            if len(raw_message) > MAX_MESSAGE_BYTES:
                self.logger.warning("Mensagem binária WebSocket excedeu o limite")
                return
            try:
                raw_message = raw_message.decode("utf-8")
            except UnicodeDecodeError:
                self.logger.warning("Mensagem WebSocket binária inválida")
                return
        if len(raw_message.encode("utf-8")) > MAX_MESSAGE_BYTES:
            self.logger.warning("Mensagem WebSocket excedeu o limite")
            return
        try:
            message = json.loads(raw_message)
        except json.JSONDecodeError:
            self.logger.warning("Mensagem WebSocket não contém JSON válido")
            return
        if not isinstance(message, dict):
            self.logger.warning("Mensagem WebSocket deve ser um objeto")
            return

        message_type = message.get("type")
        if message_type == "ping":
            self.send_json({"type": "pong", "timestamp": datetime.now(timezone.utc).isoformat()})
            return
        if message_type != "command":
            self.logger.debug("Mensagem ignorada: tipo=%r", message_type)
            return

        request_id = message.get("request_id")
        command = message.get("command")
        params = message.get("params", {})
        if not isinstance(request_id, str) or not request_id or len(request_id) > 128:
            self.logger.warning("Comando sem request_id válido")
            return
        if not isinstance(command, str) or len(command) > 64:
            self._send_command_error(request_id, "Comando inválido")
            return
        self._workers.submit(self._execute_command, request_id, command, params)

    def _execute_command(self, request_id: str, command: str, params: Any) -> None:
        try:
            result = self.command_executor.execute(command, params)
            response = {
                "type": "command_result",
                "request_id": request_id,
                **result,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            self.logger.info("Comando concluído: %s request_id=%s", command, request_id)
        except CommandValidationError as exc:
            self.logger.warning("Comando rejeitado: %s request_id=%s motivo=%s", command, request_id, exc)
            response = self._error_payload(request_id, command, str(exc), "validation_error")
        except Exception as exc:
            self.logger.exception("Falha ao executar comando %s request_id=%s", command, request_id)
            response = self._error_payload(request_id, command, str(exc), "execution_error")
        self.send_json(response)

    def _send_command_error(self, request_id: str, message: str) -> None:
        self.send_json(self._error_payload(request_id, "", message, "validation_error"))

    @staticmethod
    def _error_payload(request_id: str, command: str, message: str, code: str) -> dict[str, Any]:
        return {
            "type": "command_result",
            "request_id": request_id,
            "command": command,
            "success": False,
            "error": {"code": code, "message": message[:500]},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _on_error(self, _socket: websocket.WebSocketApp, error: Any) -> None:
        self.logger.error("Erro WebSocket: %s", error)

    def _on_close(
        self,
        _socket: websocket.WebSocketApp,
        status_code: int | None,
        message: str | None,
    ) -> None:
        self.connected.clear()
        self.logger.warning("WebSocket fechado: status=%s mensagem=%s", status_code, message)

    @staticmethod
    def command_executor_commands():
        from .commands import AllowedCommand

        return list(AllowedCommand)
