"""
统一应用日志：控制台 + 文件，便于排查前后端及自动化操作问题
路径：data/logs/app.log
"""
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import DATA_DIR

LOG_DIR = DATA_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "app.log"

_handler_file = RotatingFileHandler(
    LOG_FILE,
    maxBytes=5 * 1024 * 1024,  # 5MB
    backupCount=3,
    encoding="utf-8",
)
_handler_file.setFormatter(
    logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
)

_handler_console = logging.StreamHandler(sys.stdout)
_handler_console.setFormatter(
    logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
)

logger = logging.getLogger("jobsdb")
logger.setLevel(logging.DEBUG)
logger.addHandler(_handler_file)
logger.addHandler(_handler_console)


def log_info(msg: str, **kwargs) -> None:
    extra = " | ".join(f"{k}={v}" for k, v in kwargs.items()) if kwargs else ""
    logger.info(f"{msg}" + (f" ({extra})" if extra else ""))


def log_warning(msg: str, **kwargs) -> None:
    extra = " | ".join(f"{k}={v}" for k, v in kwargs.items()) if kwargs else ""
    logger.warning(f"{msg}" + (f" ({extra})" if extra else ""))


def log_error(msg: str, **kwargs) -> None:
    extra = " | ".join(f"{k}={v}" for k, v in kwargs.items()) if kwargs else ""
    logger.error(f"{msg}" + (f" ({extra})" if extra else ""))


def log_debug(msg: str, **kwargs) -> None:
    extra = " | ".join(f"{k}={v}" for k, v in kwargs.items()) if kwargs else ""
    logger.debug(f"{msg}" + (f" ({extra})" if extra else ""))
