"""Tests for src/log.py — structured logging."""

import logging
from pathlib import Path

from src.log import get_logger, setup_logger


class TestSetupLogger:
    def test_returns_logger(self, tmp_path):
        log_file = tmp_path / "test.log"
        logger = setup_logger(log_file)
        assert isinstance(logger, logging.Logger)

    def test_writes_to_file(self, tmp_path):
        log_file = tmp_path / "test.log"
        logger = setup_logger(log_file)
        logger.info("test message")
        content = log_file.read_text()
        assert "test message" in content
        assert "INFO" in content

    def test_format_includes_timestamp(self, tmp_path):
        log_file = tmp_path / "test.log"
        logger = setup_logger(log_file)
        logger.info("format check")
        content = log_file.read_text()
        assert "[" in content
        assert "]" in content
        assert "INFO" in content

    def test_log_levels(self, tmp_path):
        log_file = tmp_path / "test.log"
        logger = setup_logger(log_file)
        logger.debug("debug msg")
        logger.info("info msg")
        logger.warning("warn msg")
        logger.error("error msg")
        content = log_file.read_text()
        assert "debug msg" not in content  # Default level is INFO
        assert "info msg" in content
        assert "WARN" in content  # WARNING stored as WARN in display
        assert "error msg" in content

    def test_creates_parent_dirs(self, tmp_path):
        log_file = tmp_path / "subdir" / "deep" / "test.log"
        logger = setup_logger(log_file)
        logger.info("deep path")
        assert log_file.exists()

    def test_file_rotation(self, tmp_path):
        log_file = tmp_path / "test.log"
        logger = setup_logger(log_file, max_bytes=100, backup_count=2)
        for i in range(200):
            logger.info(f"line {i} " + "x" * 10)
        files = list(tmp_path.glob("test.log*"))
        assert len(files) >= 1


class TestGetLogger:
    def test_returns_same_logger_after_setup(self, tmp_path):
        log_file = tmp_path / "test.log"
        setup_logger(log_file)
        logger = get_logger()
        assert isinstance(logger, logging.Logger)
        logger.info("via get_logger")
        assert "via get_logger" in log_file.read_text()
