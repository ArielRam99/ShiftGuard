import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from flask import current_app, has_app_context


class _CurrentAppFilter(logging.Filter):
    """Keep file handlers isolated when more than one Flask app exists."""

    def __init__(self, app):
        super().__init__()
        self.app = app

    def filter(self, _record):
        return has_app_context() and current_app._get_current_object() is self.app


def configure_logging(app):
    """Configure application logging for ShiftGuard."""
    if app.config.get("TESTING"):
        return
    if "shiftguard_log_handler" in app.extensions:
        return
    log_directory = Path(app.config["DATABASE"]).resolve().parent / "logs"
    log_directory.mkdir(parents=True, exist_ok=True)

    log_file = (log_directory / "shiftguard.log").resolve()

    handler = RotatingFileHandler(
        log_file, maxBytes=1_000_000, backupCount=5, encoding="utf-8"
    )
    handler.addFilter(_CurrentAppFilter(app))
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
        )
    )
    app.logger.addHandler(handler)

    app.logger.setLevel(logging.INFO)
    app.extensions["shiftguard_log_handler"] = handler
    app.config["SHIFTGUARD_LOG_FILE"] = str(log_file)
