import logging
import sys
import os
from concurrent_log_handler import ConcurrentRotatingFileHandler
from logging.config import dictConfig

from src.app.memory_log_handler import MemoryLogHandler, set_memory_handler

LOG_CONFIG = {}  # 先占位，setup_logging 调用后会写入


class ShortNameFilter(logging.Filter):
    def __init__(self, segments: int = 1):
        super().__init__()
        self.segments = max(1, segments)

    def filter(self, record: logging.LogRecord) -> bool:
        full = getattr(record, "name", "") or ""
        parts = full.split(".")
        # 取前 N 段作为短名（默认 1 段：mcp.server.lowlevel.server -> mcp）
        short = ".".join(parts[:self.segments])

        # 也可以做一些归一化
        if short.startswith("uvicorn"):
            short = "uvicorn"
        elif short.startswith("mcp"):
            short = "mcp"

        record.short_name = short
        return True


def setup_logging(
    log_file: str = "resources/logs/app.log",
    level: int = logging.INFO,
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5,
    shorten_names: bool = True,  # 显示短名
):
    global LOG_CONFIG

    if getattr(setup_logging, "_configured", False):
        return

    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    fmt = "%(asctime)s %(levelname)s [%(process)d] %(name)s - %(message)s"
    if shorten_names:
        fmt = "%(asctime)s %(levelname)s [%(process)d] %(short_name)s - %(message)s"

    LOG_CONFIG = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {"format": fmt},
            "access": {
                "format": '%(asctime)s %(levelname)s [%(client_addr)s] Access - "%(request_line)s" %(status_code)s'
            },
        },
        "filters": {
            "shortname": {"()": ShortNameFilter}
        },
        "handlers": {
            "stdout": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "formatter": "default",
                "filters": ["shortname"] if shorten_names else [],
            },
            "file": {
                "class": "concurrent_log_handler.ConcurrentRotatingFileHandler",
                "filename": log_file,
                "maxBytes": max_bytes,
                "backupCount": backup_count,
                "encoding": "utf-8",
                "formatter": "default",
                "filters": ["shortname"] if shorten_names else [],
            },
        },
        "loggers": {
            "uvicorn":        {"level": logging.getLevelName(level), "handlers": [], "propagate": True},
            "uvicorn.error":  {"level": logging.getLevelName(level), "handlers": [], "propagate": True},
            "uvicorn.access": {"level": logging.getLevelName(level), "handlers": [], "propagate": True},
        },
        "root": {
            "level": logging.getLevelName(level),
            "handlers": ["stdout", "file"],
        },
    }

    dictConfig(LOG_CONFIG)  # 应用配置

    # 注册内存日志处理器（环形缓冲区，供 REST 接口查询）
    memory_handler = MemoryLogHandler(capacity=2000)
    memory_handler.setLevel(level)
    # 使用与 stdout 相同的格式
    memory_handler.setFormatter(logging.Formatter(fmt))
    root_logger = logging.getLogger()
    root_logger.addHandler(memory_handler)
    set_memory_handler(memory_handler)

    logging.getLogger().info(
        f"Logging setup complete. All logs will be written to {log_file} and stdout."
    )

    setup_logging._configured = True
