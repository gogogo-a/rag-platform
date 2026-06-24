import json
from contextvars import ContextVar
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from log import logger


_database_duration_stats: ContextVar[dict] = ContextVar(
    "database_duration_stats",
    default={"database_duration_ms": 0.0, "database_query_count": 0},
)


def reset_database_duration() -> None:
    _database_duration_stats.set({"database_duration_ms": 0.0, "database_query_count": 0})


def record_database_duration(duration_ms: float) -> None:
    stats = _database_duration_stats.get()
    stats["database_duration_ms"] += duration_ms
    stats["database_query_count"] += 1


def get_database_duration_summary() -> dict:
    stats = _database_duration_stats.get()
    return {
        "database_duration_ms": round(stats["database_duration_ms"], 3),
        "database_query_count": stats["database_query_count"],
    }


def _to_plain_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (Decimal, UUID, bytes, bytearray)):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _to_plain_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_plain_value(item) for item in value]
    if hasattr(value, "model_dump"):
        return _to_plain_value(value.model_dump())
    if hasattr(value, "dict"):
        return _to_plain_value(value.dict())
    if hasattr(value, "__dict__"):
        return _to_plain_value({
            key: item
            for key, item in vars(value).items()
            if not key.startswith("_")
        })
    return str(value)


def to_json_text(value: Any) -> str:
    return json.dumps(_to_plain_value(value), ensure_ascii=False, default=str)


def log_database_return(source: str, value: Any) -> None:
    logger.info(f"数据库返回 {source}: {to_json_text(value)}")
