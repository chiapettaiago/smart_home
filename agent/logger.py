"""Logging rotativo do agente."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from .config import AgentConfig


def configure_logging(config: AgentConfig) -> logging.Logger:
    config.log_file.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("smart_home_agent")
    logger.setLevel(getattr(logging, config.log_level, logging.INFO))
    logger.propagate = False
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s [%(threadName)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler = RotatingFileHandler(
        config.log_file,
        maxBytes=config.log_max_bytes,
        backupCount=config.log_backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    if __import__("sys").stdout is not None:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    return logger
