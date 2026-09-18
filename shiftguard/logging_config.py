import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging(app):
    """Configure application logging for ShiftGuard."""
    if app.config.get("TESTING"):
        return
    log_directory = Path(app.instance_path) / "logs"
    log_directory.mkdir(parents=True, exist_ok=True)

    log_file = (log_directory / "shiftguard.log").resolve()

    existing_handler = next(
        (
            handler
            for handler in app.logger.handlers
            if isinstance(handler, RotatingFileHandler)
            and Path(handler.baseFilename).resolve() == log_file
        ),
        None,
    )

    if existing_handler is None:
        handler = RotatingFileHandler(
            log_file,
            maxBytes=1_000_000,
            backupCount=5,
            encoding="utf-8",
        )

        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
            )
        )

        app.logger.addHandler(handler)

    app.logger.setLevel(logging.INFO)
    app.config["SHIFTGUARD_LOG_FILE"] = str(log_file)