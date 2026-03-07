import datetime
import json
from dataclasses import asdict


def _serialize_value(obj):
    if isinstance(obj, datetime.datetime):
        return obj.isoformat() if obj is not None else None
    if hasattr(obj, "__dataclass_fields__"):
        return {f: _serialize_value(getattr(obj, f)) for f in obj.__dataclass_fields__}
    if isinstance(obj, list):
        return [_serialize_value(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _serialize_value(v) for k, v in obj.items()}
    return obj


def dto_to_json(dto) -> str:
    data = asdict(dto) if hasattr(dto, "__dataclass_fields__") else dto
    return json.dumps(_serialize_value(data))
