"""
统一日志入口。
用法：
from breadfree.utils.logger import get_logger
logger = get_logger(__name__)
"""
from __future__ import annotations

import logging
import os
from logging import Logger

DEFAULT_LOG_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "logs"))
DEFAULT_LOG_FILE = os.path.join(DEFAULT_LOG_DIR, "breadfree.log")


def _ensure_log_dir():
    try:
        os.makedirs(DEFAULT_LOG_DIR, exist_ok=True)
    except Exception:
        pass


def _basic_formatter() -> logging.Formatter:
    return logging.Formatter(
        fmt="%(asctime)s %(levelname)-8s [%(name)s:%(lineno)d] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def get_logger(name: str | None = None, level: int = logging.INFO) -> Logger:
    if name is None:
        name = "breadfree"

    logger = logging.getLogger(name)
    logger.setLevel(level)

    if logger.handlers:
        return logger

    ch = logging.StreamHandler()
    ch.setLevel(level)
    ch.setFormatter(_basic_formatter())
    logger.addHandler(ch)

    try:
        _ensure_log_dir()
        fh = logging.FileHandler(DEFAULT_LOG_FILE, encoding="utf-8")
        fh.setLevel(level)
        fh.setFormatter(_basic_formatter())
        logger.addHandler(fh)
    except Exception:
        pass

    logger.propagate = False
    return logger


default_logger = get_logger("breadfree")
