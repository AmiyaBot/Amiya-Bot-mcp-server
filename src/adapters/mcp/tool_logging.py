from __future__ import annotations

import logging
from time import perf_counter
from typing import Any


def _short_repr(value: Any, max_length: int = 120) -> str:
    text = repr(value)
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def summarize_args(**kwargs: Any) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key, value in kwargs.items():
        if isinstance(value, str):
            summary[key] = value if len(value) <= 80 else value[:77] + "..."
            continue
        if isinstance(value, list):
            summary[key] = [_short_repr(item, max_length=60) for item in value[:10]]
            if len(value) > 10:
                summary[f"{key}_total"] = len(value)
            continue
        summary[key] = value
    return summary


def summarize_response(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        summary: dict[str, Any] = {"keys": sorted(payload.keys())}

        data = payload.get("data")
        if isinstance(data, dict):
            summary["data_key_count"] = len(data)
            summary["data_keys"] = sorted(data.keys())[:10]
        elif data is not None:
            summary["data_type"] = type(data).__name__

        candidates = payload.get("candidates")
        if isinstance(candidates, list):
            summary["candidate_count"] = len(candidates)

        message = payload.get("message")
        if message:
            summary["message"] = _short_repr(message, max_length=100)

        if "image_url" in payload:
            summary["has_image_url"] = bool(payload.get("image_url"))
        if "image_path" in payload:
            summary["has_image_path"] = bool(payload.get("image_path"))

        return summary

    if isinstance(payload, str):
        return {
            "payload_type": "str",
            "payload_length": len(payload),
            "payload_preview": payload if len(payload) <= 100 else payload[:97] + "...",
        }

    if payload is None:
        return {"payload": None}

    return {
        "payload_type": type(payload).__name__,
        "payload_preview": _short_repr(payload),
    }


def log_tool_start(logger: logging.Logger, tool_name: str, **kwargs: Any) -> float:
    started_at = perf_counter()
    logger.info("MCP 工具调用开始: tool=%s args=%s", tool_name, summarize_args(**kwargs))
    return started_at


def log_tool_not_ready(logger: logging.Logger, tool_name: str) -> None:
    logger.warning("MCP 工具调用失败: tool=%s reason=context_not_ready", tool_name)


def log_tool_end(logger: logging.Logger, tool_name: str, started_at: float, payload: Any) -> None:
    elapsed_ms = int((perf_counter() - started_at) * 1000)
    logger.info(
        "MCP 工具调用结束: tool=%s elapsed_ms=%s response=%s",
        tool_name,
        elapsed_ms,
        summarize_response(payload),
    )


def log_tool_exception(logger: logging.Logger, tool_name: str, started_at: float, **kwargs: Any) -> None:
    elapsed_ms = int((perf_counter() - started_at) * 1000)
    logger.exception(
        "MCP 工具调用异常: tool=%s elapsed_ms=%s args=%s",
        tool_name,
        elapsed_ms,
        summarize_args(**kwargs),
    )