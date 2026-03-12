"""按用户存储：storage_state, stats, external_jobs, logs, 配置等"""
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from .config import ACCOUNTS_BASE

EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")


def _user_dir(user_id: int) -> Path:
    d = ACCOUNTS_BASE / str(user_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def state_file(user_id: int) -> Path:
    return _user_dir(user_id) / "storage_state.json"


def stats_file(user_id: int) -> Path:
    return _user_dir(user_id) / "apply_stats.json"


def external_jobs_file(user_id: int) -> Path:
    return _user_dir(user_id) / "external_jobs.txt"


def external_jobs_done_file(user_id: int) -> Path:
    return _user_dir(user_id) / "external_jobs_done.txt"


def current_email_file(user_id: int) -> Path:
    return _user_dir(user_id) / "current_email.txt"


def logs_file(user_id: int) -> Path:
    return _user_dir(user_id) / "logs.txt"


def jobs_cache_file(user_id: int) -> Path:
    return _user_dir(user_id) / "jobs_cache.json"


def excluded_companies_file(user_id: int) -> Path:
    return _user_dir(user_id) / "excluded_companies.txt"


def auto_runs_file(user_id: int) -> Path:
    """自动投递任务汇总记录（最近若干次）"""
    return _user_dir(user_id) / "auto_runs.json"


def get_current_email(user_id: int) -> str:
    p = current_email_file(user_id)
    if not p.exists():
        return ""
    try:
        return p.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def save_current_email(user_id: int, email: str) -> None:
    _user_dir(user_id)
    current_email_file(user_id).write_text((email or "").strip(), encoding="utf-8")


def clear_jobsdb_session(user_id: int) -> None:
    """注销 JobsDB：删除 storage_state 和 current_email"""
    try:
        state_file(user_id).unlink(missing_ok=True)
    except Exception:
        pass
    save_current_email(user_id, "")


def load_stats(user_id: int) -> dict:
    p = stats_file(user_id)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return {k: int(v) for k, v in data.items() if k != "_" and isinstance(v, (int, float))}
    except Exception:
        return {}


def save_stats(user_id: int, data: dict) -> None:
    stats_file(user_id).parent.mkdir(parents=True, exist_ok=True)
    stats_file(user_id).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def stats_summary(user_id: int) -> tuple[int, int, int]:
    data = load_stats(user_id)
    today_str = datetime.now().strftime("%Y-%m-%d")

    def sum_days(n: int) -> int:
        total = 0
        for i in range(n):
            d = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            total += data.get(d, 0)
        return total

    return data.get(today_str, 0), sum_days(7), sum_days(30)


def increment_today(user_id: int) -> None:
    data = load_stats(user_id)
    today = datetime.now().strftime("%Y-%m-%d")
    data[today] = data.get(today, 0) + 1
    save_stats(user_id, data)


def load_external_jobs(user_id: int) -> list[tuple[str, str]]:
    p = external_jobs_file(user_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if "\t" in line:
            t, u = line.split("\t", 1)
            if t.strip() and u.strip():
                out.append((t.strip(), u.strip()))
    return out


def _normalize_title(s: str) -> str:
    return " ".join((s or "").strip().lower().split())


def append_external_job(user_id: int, title: str, url: str) -> bool:
    """追加外部职位。若 URL 或 Title 已存在则跳过，返回是否实际添加"""
    url = (url or "").strip()
    title = (title or "").strip()
    if not url or not title:
        return False
    existing = load_external_jobs(user_id)
    url_lower = url.lower()
    title_norm = _normalize_title(title)
    for t, u in existing:
        if (u or "").strip().lower() == url_lower:
            return False
        if _normalize_title(t) == title_norm:
            return False
    p = external_jobs_file(user_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(f"{title}\t{url}\n")
    return True


def clear_external_jobs(user_id: int) -> None:
    p = external_jobs_file(user_id)
    if p.exists():
        p.write_text("", encoding="utf-8")
    dp = external_jobs_done_file(user_id)
    if dp.exists():
        dp.write_text("", encoding="utf-8")


def load_external_jobs_done(user_id: int) -> set[str]:
    p = external_jobs_done_file(user_id)
    if not p.exists():
        return set()
    return {line.strip().lower() for line in p.read_text(encoding="utf-8").splitlines() if line.strip()}


def mark_external_job_done(user_id: int, url: str) -> None:
    url = (url or "").strip().lower()
    if not url:
        return
    p = external_jobs_done_file(user_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(f"{url}\n")


def append_log(user_id: int, message: str) -> None:
    p = logs_file(user_id)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        # 轮转：超过 5MB 时备份并截断
        try:
            from .config import LOG_MAX_BYTES, LOG_BACKUP_COUNT
            if p.exists() and p.stat().st_size >= LOG_MAX_BYTES:
                for i in range(LOG_BACKUP_COUNT - 1, 0, -1):
                    prev = p.parent / f"logs.{i}.txt"
                    curr = p.parent / f"logs.{i + 1}.txt"
                    if prev.exists():
                        prev.rename(curr)
                p.rename(p.parent / "logs.1.txt")
        except Exception:
            pass
        with p.open("a", encoding="utf-8") as f:
            f.write(f"[{ts}] {message}\n")
            f.flush()
    except Exception:
        pass


def read_logs(user_id: int, limit: int = 500) -> list[str]:
    p = logs_file(user_id)
    if not p.exists():
        return []
    lines = p.read_text(encoding="utf-8").strip().split("\n")
    return lines[-limit:] if limit else lines


def load_jobs_cache(user_id: int) -> list:
    """从文件加载职位列表（手动/自动投递后持久化）"""
    p = jobs_cache_file(user_id)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


DEFAULT_EXCLUDED_COMPANIES = ["MOMAX", "AIA", "Prudential"]


def load_excluded_companies(user_id: int) -> list[str]:
    """加载排除公司黑名单。空则返回默认列表"""
    p = excluded_companies_file(user_id)
    if not p.exists():
        return list(DEFAULT_EXCLUDED_COMPANIES)
    lines = p.read_text(encoding="utf-8").strip().split("\n")
    items = [x.strip() for x in lines if x.strip()]
    return items if items else list(DEFAULT_EXCLUDED_COMPANIES)


def save_excluded_companies(user_id: int, companies: list[str]) -> None:
    p = excluded_companies_file(user_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join((x.strip() for x in companies if x.strip()))
    p.write_text(text, encoding="utf-8")


def save_jobs_cache(user_id: int, jobs: list) -> None:
    """保存职位列表到文件（手动/自动投递共用）"""
    try:
        from .debug_log import debug
        debug("save_jobs_cache", user_id=user_id, count=len(jobs), path=str(jobs_cache_file(user_id)))
    except Exception:
        pass
    p = jobs_cache_file(user_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(jobs, ensure_ascii=False, indent=2)
    with p.open("w", encoding="utf-8") as f:
        f.write(content)
        f.flush()  # 确保写入磁盘


def load_auto_runs(user_id: int) -> list[dict]:
    """加载自动投递任务历史摘要（按时间顺序）"""
    p = auto_runs_file(user_id)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def record_auto_run(user_id: int, summary: dict) -> None:
    """追加一条自动投递任务摘要，自动裁剪为最近 20 条"""
    runs = load_auto_runs(user_id)
    # 确保有时间字段
    if "at" not in summary:
        summary = {**summary, "at": datetime.utcnow().isoformat()}
    runs.append(summary)
    # 只保留最近 20 条，避免文件无限增大
    runs = runs[-20:]
    p = auto_runs_file(user_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(runs, ensure_ascii=False, indent=2), encoding="utf-8")

