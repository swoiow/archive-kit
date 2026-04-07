from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from cells import json

from .models import BatchProcessResult


def to_jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {key: to_jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(item) for item in value]
    return value


def batch_result_to_dict(result: BatchProcessResult) -> dict[str, Any]:
    return to_jsonable(result)


def write_batch_report_json(
    result: BatchProcessResult,
    output_path: str | Path,
    *,
    indent: int = 2,
    ensure_ascii: bool = False,
) -> Path:
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = batch_result_to_dict(result)
    destination.write_text(
        json.dumps(payload, indent=indent, ensure_ascii=ensure_ascii, backend="json"),
        encoding="utf-8",
    )
    return destination
