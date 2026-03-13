"""API 与 Worker 统一配置"""
import os
from pathlib import Path
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parent.parent
API_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
ACCOUNTS_BASE = DATA_DIR / "accounts"

SECRET_KEY = os.environ.get("JOBSDB_SECRET_KEY", "dev-secret-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 天

# Worker / Playwright 相关
JOBSDB_BASE_URL = os.environ.get("JOBSDB_BASE_URL", "https://hk.jobsdb.com")
# 调试：JOBSDB_HEADED=1 时使用有界面浏览器，需配合 noVNC 查看（ENABLE_NOVNC=1）
JOBSDB_HEADED = os.environ.get("JOBSDB_HEADED", "").lower() in ("1", "true", "yes")

# 住宅代理：JOBSDB_PROXY=socks5://host:port:user:pass 或 socks5://user:pass@host:port
def _parse_proxy() -> dict | None:
    raw = os.environ.get("JOBSDB_PROXY", "").strip()
    if not raw:
        return None
    # 支持 socks5://host:port:user:pass 格式
    if raw.startswith("socks5://") or raw.startswith("http://") or raw.startswith("https://"):
        rest = raw.split("://", 1)[1]
        parts = rest.split(":")
        if len(parts) >= 4 and "@" not in rest:
            # host:port:user:pass
            host, port, user, pw = parts[0], parts[1], parts[2], ":".join(parts[3:])
            proto = "socks5" if "socks5" in raw else "http"
            return {
                "server": f"{proto}://{host}:{port}",
                "username": user,
                "password": pw,
            }
        # 标准 user:pass@host:port
        parsed = urlparse(raw)
        if parsed.hostname and parsed.port:
            out = {"server": f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"}
            if parsed.username:
                out["username"] = parsed.username
            if parsed.password:
                out["password"] = parsed.password
            if out.get("username") or out.get("password"):
                return out
            return {"server": out["server"]}
    return None


JOBSDB_PROXY = _parse_proxy()
PAGE_DEFAULT_TIMEOUT_MS = int(os.environ.get("JOBSDB_PAGE_TIMEOUT", "45000"))
WAIT_CARDS_TIMEOUT_MS = int(os.environ.get("JOBSDB_CARDS_TIMEOUT", "15000"))
EXPECT_POPUP_TIMEOUT_MS = int(os.environ.get("JOBSDB_POPUP_TIMEOUT", "1500"))
EXTERNAL_SITE_SLEEP_SEC = int(os.environ.get("JOBSDB_EXTERNAL_SLEEP", "30"))
FORM_RETRY_COUNT = int(os.environ.get("JOBSDB_FORM_RETRY", "3"))
JOB_INTERVAL_SEC = (10, 15)  # 单职位间隔范围（秒）

# 日志轮转
LOG_MAX_BYTES = int(os.environ.get("JOBSDB_LOG_MAX_BYTES", str(5 * 1024 * 1024)))  # 5MB
LOG_BACKUP_COUNT = int(os.environ.get("JOBSDB_LOG_BACKUP", "3"))

# 确保目录存在
DATA_DIR.mkdir(parents=True, exist_ok=True)
ACCOUNTS_BASE.mkdir(parents=True, exist_ok=True)
