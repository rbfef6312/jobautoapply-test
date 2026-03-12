"""
操作指令日志：记录前后端及自动化操作，便于统计与排查
写入：data/accounts/{user_id}/operations.jsonl
"""
import json
from datetime import datetime
from pathlib import Path

from .storage import operations_file, _user_dir
from .app_logger import log_info, log_debug, log_error


def _append_operation(user_id: int, action: str, detail: str = "", level: str = "info", source: str = "backend") -> None:
    """追加一条操作记录"""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = {
        "ts": ts,
        "user_id": user_id,
        "action": action,
        "detail": detail,
        "level": level,
        "source": source,
    }
    try:
        p = operations_file(user_id)
        _user_dir(user_id)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            f.flush()
    except Exception as e:
        log_error("operation_log append failed", err=str(e), user_id=user_id)


def op_info(user_id: int, action: str, detail: str = "", source: str = "backend") -> None:
    _append_operation(user_id, action, detail, level="info", source=source)
    log_info(action, user_id=user_id, detail=detail[:80] if detail else "", source=source)


def op_debug(user_id: int, action: str, detail: str = "", source: str = "backend") -> None:
    _append_operation(user_id, action, detail, level="debug", source=source)
    log_debug(action, user_id=user_id, detail=detail[:80] if detail else "", source=source)


def op_error(user_id: int, action: str, detail: str = "", source: str = "backend") -> None:
    _append_operation(user_id, action, detail, level="error", source=source)
    log_error(action, user_id=user_id, detail=detail[:80] if detail else "", source=source)


def read_operations(user_id: int, limit: int = 500) -> list[dict]:
    """读取用户操作日志（倒序，最新的在前）"""
    p = operations_file(user_id)
    if not p.exists():
        return []
    lines = []
    try:
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        lines.append(json.loads(line))
                    except Exception:
                        pass
    except Exception:
        return []
    return list(reversed(lines[-limit:]))
