"""
调试日志：写入 data/debug.log，便于排查问题时复制全文发给人分析。
路径：项目根目录/data/debug.log
排查完成后可删除或清空此文件。
"""
from datetime import datetime
from pathlib import Path

from .config import DATA_DIR

_DEBUG_FILE = DATA_DIR / "debug.log"


def debug(msg: str, **kwargs) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    extra = " | ".join(f"{k}={v}" for k, v in kwargs.items()) if kwargs else ""
    line = f"[{ts}] {msg}"
    if extra:
        line += f" ({extra})"
    try:
        with _DEBUG_FILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
    except Exception:
        pass
