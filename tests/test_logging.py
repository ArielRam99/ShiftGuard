import logging
from logging.handlers import RotatingFileHandler

from shiftguard import create_app


def test_logging_creates_rotating_file_handler(tmp_path):
    app = create_app(
        {
            "TESTING": False,
            "DATABASE": str(tmp_path / "test.sqlite"),
        }
    )

    log_file = app.config["SHIFTGUARD_LOG_FILE"]

    handlers = [
        handler
        for handler in app.logger.handlers
        if isinstance(handler, RotatingFileHandler)
        and handler.baseFilename == log_file
    ]

    assert len(handlers) == 1
    assert handlers[0].maxBytes == 1_000_000
    assert handlers[0].backupCount == 5


def test_logging_does_not_duplicate_handler(tmp_path):
    app = create_app(
        {
            "TESTING": False,
            "DATABASE": str(tmp_path / "test.sqlite"),
        }
    )

    from shiftguard.logging_config import configure_logging

    configure_logging(app)

    log_file = app.config["SHIFTGUARD_LOG_FILE"]

    handlers = [
        handler
        for handler in app.logger.handlers
        if isinstance(handler, RotatingFileHandler)
        and handler.baseFilename == log_file
    ]

    assert len(handlers) == 1


def test_testing_mode_skips_runtime_log(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "test.sqlite"),
        }
    )

    assert "SHIFTGUARD_LOG_FILE" not in app.config