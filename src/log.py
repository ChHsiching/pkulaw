"""Structured logging for PKULaw CLI crawler."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_logger: logging.Logger | None = None


class _Formatter(logging.Formatter):
    """Custom format: [YYYY-MM-DD HH:MM:SS] LEVEL message"""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = self.formatTime(record, datefmt="%Y-%m-%d %H:%M:%S")
        level = record.levelname
        if level == "WARNING":
            level = "WARN"
        return f"[{timestamp}] {level:5s} {record.getMessage()}"


def setup_logger(
    log_file: Path,
    level: int = logging.INFO,
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 3,
) -> logging.Logger:
    """Configure and return the application logger."""
    global _logger

    logger = logging.getLogger("pkulaw")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    formatter = _Formatter()

    log_file.parent.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        str(log_file),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    _logger = logger
    return logger


def get_logger() -> logging.Logger:
    """Return the configured logger."""
    if _logger is None:
        return logging.getLogger("pkulaw")
    return _logger
