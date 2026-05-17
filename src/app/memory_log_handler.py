"""
内存日志处理器：将最近的日志条目保留在环形缓冲区中，
供 REST 接口按需查询，用于远端诊断。
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class LogEntry:
    """单条内存日志条目。"""

    __slots__ = ("timestamp", "level", "logger_name", "message", "exc_info")

    def __init__(
        self,
        timestamp: str,
        level: str,
        logger_name: str,
        message: str,
        exc_info: Optional[str] = None,
    ) -> None:
        self.timestamp = timestamp
        self.level = level
        self.logger_name = logger_name
        self.message = message
        self.exc_info = exc_info


class MemoryLogHandler(logging.Handler):
    """将日志写入内存环形缓冲区的 Handler。

    缓冲区最大容量通过 `capacity` 控制（默认 2000）。
    达到上限后最旧的条目自动丢弃。
    """

    def __init__(self, capacity: int = 2000, level: int = logging.NOTSET) -> None:
        super().__init__(level=level)
        self._buffer: deque[LogEntry] = deque(maxlen=max(1, capacity))
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
        except Exception:
            msg = record.getMessage()

        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()
        exc_text: Optional[str] = None
        if record.exc_info and record.exc_info != (None, None, None):
            try:
                import traceback

                exc_text = "".join(traceback.format_exception(*record.exc_info))
            except Exception:
                exc_text = str(record.exc_info)

        entry = LogEntry(
            timestamp=ts,
            level=record.levelname,
            logger_name=record.name,
            message=msg,
            exc_info=exc_text,
        )

        with self._lock:
            self._buffer.append(entry)

    def query(
        self,
        *,
        level: Optional[str] = None,
        keyword: Optional[str] = None,
        lines: int = 100,
        since: Optional[str] = None,  # ISO 时间戳
    ) -> Dict[str, Any]:
        """查询内存中的日志。

        Args:
            level: 按级别过滤（如 "DEBUG", "WARNING", "ERROR"）
            keyword: 按消息关键字过滤（大小写不敏感）
            lines: 最大返回条数（≤ buffer 容量）
            since: 只返回此 ISO 时间戳之后的日志

        Returns:
            dict: {"total": ..., "returned": ..., "buffer_capacity": ..., "logs": [...]}
        """
        with self._lock:
            entries = list(self._buffer)

        total = len(entries)

        # 过滤
        if level:
            level_upper = level.upper()
            entries = [e for e in entries if e.level.upper() == level_upper]

        if keyword:
            kw_lower = keyword.lower()
            entries = [e for e in entries if kw_lower in e.message.lower() or kw_lower in e.logger_name.lower()]

        if since:
            entries = [e for e in entries if e.timestamp >= since]

        # 截取最后 lines 条
        if lines > 0:
            entries = entries[-lines:]

        return {
            "total": total,
            "returned": len(entries),
            "buffer_capacity": self._buffer.maxlen or 0,
            "logs": [
                {
                    "ts": e.timestamp,
                    "level": e.level,
                    "logger": e.logger_name,
                    "message": e.message,
                    "exc_info": e.exc_info,
                }
                for e in entries
            ],
        }

    def clear(self) -> None:
        """清空缓冲区。"""
        with self._lock:
            self._buffer.clear()

    def level_counts(self) -> Dict[str, int]:
        """返回各级别日志计数。"""
        with self._lock:
            counts: Dict[str, int] = {}
            for e in self._buffer:
                lvl = e.level
                counts[lvl] = counts.get(lvl, 0) + 1
            return counts


# 模块级单例引用，setup_logging 调用后设置
_memory_handler: Optional[MemoryLogHandler] = None


def get_memory_handler() -> Optional[MemoryLogHandler]:
    """获取全局内存日志处理器（可能为 None）。"""
    return _memory_handler


def set_memory_handler(handler: MemoryLogHandler) -> None:
    """设置全局内存日志处理器。"""
    global _memory_handler
    _memory_handler = handler
