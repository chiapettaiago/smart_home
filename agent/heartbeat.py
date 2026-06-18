"""Produtor periódico de heartbeat."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from .system_info import heartbeat_snapshot


class HeartbeatWorker:
    def __init__(
        self,
        agent_id: str,
        interval_seconds: int,
        sender: Callable[[dict], bool],
        stop_event: threading.Event,
        logger: logging.Logger,
    ) -> None:
        self.agent_id = agent_id
        self.interval_seconds = interval_seconds
        self.sender = sender
        self.stop_event = stop_event
        self.logger = logger
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self._run, name="heartbeat", daemon=True)
        self.thread.start()

    def _run(self) -> None:
        while not self.stop_event.is_set():
            try:
                self.sender({"type": "heartbeat", "payload": heartbeat_snapshot(self.agent_id)})
            except Exception:
                self.logger.exception("Falha ao produzir heartbeat")
            self.stop_event.wait(self.interval_seconds)
