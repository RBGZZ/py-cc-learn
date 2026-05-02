from __future__ import annotations

import logging
import os
import sys
import traceback
import uuid
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import structlog

# === In-memory error log ===
MAX_IN_MEMORY_ERRORS = 100
_in_memory_error_log: list[dict[str, str]] = []


class ErrorLogSink:
    def log_error(self, error: Exception) -> None:
        pass

    def get_errors_path(self) -> str:
        return ""


_error_log_sink: ErrorLogSink | None = None
_error_queue: list[dict[str, Any]] = []


def attach_error_log_sink(sink: ErrorLogSink) -> None:
    global _error_log_sink
    if _error_log_sink is not None:
        return
    _error_log_sink = sink

    if _error_queue:
        queued = list(_error_queue)
        _error_queue.clear()
        for event in queued:
            if event["type"] == "error":
                sink.log_error(event["error"])


def get_in_memory_errors() -> list[dict[str, str]]:
    return list(_in_memory_error_log)


def _reset_error_log_for_testing() -> None:
    global _error_log_sink, _in_memory_error_log
    _error_log_sink = None
    _error_queue.clear()
    _in_memory_error_log = []


# === Structlog setup ===

_LOG_FORMAT = os.environ.get("LOG_FORMAT", "json")
_LOG_DIR = Path(os.environ.get("LOG_DIR", str(Path.home() / ".claude" / "logs")))
_ROTATING_MAX_BYTES = 100 * 1024 * 1024
_ROTATING_BACKUP_COUNT = 5

_initialized = False


def _add_request_id(
    logger: logging.Logger, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    ctx = structlog.contextvars.get_contextvars()
    request_id = ctx.get("request_id")
    if request_id:
        event_dict["request_id"] = request_id
    return event_dict


def _drop_color_message(
    logger: logging.Logger, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    event_dict.pop("color_message", None)
    return event_dict


def setup_logging(
    log_level: str = "INFO",
    log_dir: Path | None = None,
) -> None:
    global _initialized
    if _initialized:
        return

    directory = log_dir or _LOG_DIR
    directory.mkdir(parents=True, exist_ok=True)

    timestamper = structlog.processors.TimeStamper(fmt="iso")

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        timestamper,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        _add_request_id,
    ]

    if _LOG_FORMAT == "json" or _LOG_FORMAT == "structured":
        structlog.configure(
            processors=[
                *shared_processors,
                _drop_color_message,
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.stdlib.BoundLogger,
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )
    else:
        structlog.configure(
            processors=[
                *shared_processors,
                structlog.dev.ConsoleRenderer(),
            ],
            wrapper_class=structlog.stdlib.BoundLogger,
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    root_logger.handlers.clear()

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    console_formatter = logging.Formatter("%(message)s")
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    log_file = directory / "claude.log"
    file_handler = RotatingFileHandler(
        str(log_file),
        maxBytes=_ROTATING_MAX_BYTES,
        backupCount=_ROTATING_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    file_formatter = logging.Formatter("%(message)s")
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    _initialized = True


def get_logger(name: str = "py-cc") -> Any:
    return structlog.get_logger(name)


# === Error logging ===


def log_error(error: Any) -> None:
    if isinstance(error, Exception):
        err = error
    elif isinstance(error, str):
        err = Exception(error)
    else:
        err = Exception(str(error))

    try:
        if (
            os.environ.get("CLAUDE_CODE_USE_BEDROCK")
            or os.environ.get("CLAUDE_CODE_USE_VERTEX")
            or os.environ.get("CLAUDE_CODE_USE_FOUNDRY")
            or os.environ.get("DISABLE_ERROR_REPORTING")
        ):
            return

        error_str = (
            "".join(traceback.format_exception(type(err), err, err.__traceback__))
            if err.__traceback__
            else str(err)
        )

        error_info = {
            "error": error_str,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        if len(_in_memory_error_log) >= MAX_IN_MEMORY_ERRORS:
            _in_memory_error_log.pop(0)
        _in_memory_error_log.append(error_info)

        if _error_log_sink is None:
            _error_queue.append({"type": "error", "error": err})
            return

        _error_log_sink.log_error(err)
    except Exception:
        pass


def log_for_debugging(message: str, level: str = "debug") -> None:
    logger = get_logger("debug")
    log_method = getattr(logger, level, logger.debug)
    log_method(message)


# === Request ID middleware ===

_REQUEST_ID_HEADER = "X-Request-ID"


def get_request_id() -> str:
    ctx = structlog.contextvars.get_contextvars()
    return ctx.get("request_id", "unknown")


def set_request_id(request_id: str | None = None) -> str:
    rid = request_id or str(uuid.uuid4())
    structlog.contextvars.bind_contextvars(request_id=rid)
    return rid


def clear_request_id() -> None:
    structlog.contextvars.unbind_contextvars("request_id")
