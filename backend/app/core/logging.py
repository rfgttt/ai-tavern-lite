import logging
from logging.handlers import RotatingFileHandler
import sys

from .config import settings


def setup_logging():
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("ai_tavern")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(formatter)
    logger.addHandler(console)

    try:
        file_handler = RotatingFileHandler(
            settings.logs_dir / "app.log",
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError as error:
        console.handle(
            logging.LogRecord(
                name="ai_tavern",
                level=logging.WARNING,
                pathname=__file__,
                lineno=0,
                msg=f"File logging unavailable: {error}",
                args=(),
                exc_info=None,
            )
        )
    return logger


logger = setup_logging()
