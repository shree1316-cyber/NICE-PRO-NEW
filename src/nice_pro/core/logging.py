"""Central logging configuration."""

import sys
from pathlib import Path

from loguru import logger


def configure_logging(level: str = "INFO", log_directory: Path = Path("logs")) -> None:
    log_directory.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(sys.stderr, level=level, format="<green>{time:HH:mm:ss}</green> | <level>{message}</level>")
    logger.add(
        log_directory / "nice-pro.log",
        level=level,
        rotation="10 MB",
        retention="14 days",
        enqueue=True,
    )
