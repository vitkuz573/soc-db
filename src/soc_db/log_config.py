"""Structured logging configuration for soc-db."""

import json
import logging
import logging.config
import traceback
from datetime import UTC, datetime
from typing import Any

from soc_db.config import settings

_STANDARD_ATTRS = frozenset({
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "id",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
    "taskName",
})


class JSONFormatter(logging.Formatter):
    """Format log records as newline-delimited JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info and record.exc_info[0]:
            entry["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": "".join(traceback.format_exception(*record.exc_info)),
            }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_ATTRS:
                entry[key] = value
        return json.dumps(entry, default=str, ensure_ascii=False)


def setup_logging(level: str | None = None, fmt: str | None = None) -> None:
    """Configure root logger with structured output to stderr.

    Args:
        level: Override log level (default: from ``SOC_DB_LOG_LEVEL`` env
            or ``WARNING``).
        fmt: Override format — ``"json"`` or ``"plain"`` (default: from
            ``SOC_DB_LOG_FORMAT`` env or ``"json"``).
    """
    level = (level or settings.log_level).upper()
    fmt = (fmt or settings.log_format).lower()

    if fmt == "json":
        formatter: dict[str, Any] = {"()": JSONFormatter}
    else:
        formatter = {
            "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            "datefmt": "%Y-%m-%dT%H:%M:%S%z",
        }

    config: dict[str, Any] = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"main": formatter},
        "handlers": {
            "stderr": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stderr",
                "formatter": "main",
            },
        },
        "root": {
            "level": level,
            "handlers": ["stderr"],
        },
        "loggers": {
            "soc_db": {"level": level, "handlers": ["stderr"], "propagate": False},
            "uvicorn": {"level": "WARNING", "handlers": ["stderr"], "propagate": False},
            "uvicorn.access": {"level": "WARNING", "handlers": ["stderr"], "propagate": False},
        },
    }

    logging.config.dictConfig(config)
