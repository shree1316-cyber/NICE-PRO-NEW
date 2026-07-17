from loguru import logger
import os

LOG_DIR = "logs"

os.makedirs(LOG_DIR, exist_ok=True)

logger.remove()

logger.add(
    f"{LOG_DIR}/nice.log",
    rotation="10 MB",
    retention="30 days",
    level="INFO",
    enqueue=True,
)

logger.add(
    lambda msg: print(msg, end=""),
    level="INFO",
)

log = logger
