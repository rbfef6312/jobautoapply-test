"""API 与 Worker 统一配置"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
API_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
ACCOUNTS_BASE = DATA_DIR / "accounts"

SECRET_KEY = os.environ.get("JOBSDB_SECRET_KEY", "dev-secret-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 天

# Worker / Playwright 相关
JOBSDB_BASE_URL = os.environ.get("JOBSDB_BASE_URL", "https://hk.jobsdb.com")
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
