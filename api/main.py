"""
JobsDB 投递控制台 - FastAPI 后端
"""
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from sqlalchemy import text

from .config import ACCOUNTS_BASE
from .database import Base, SessionLocal, engine, get_db, get_or_create_monitor_settings, User, MonitorSettings
from .auth import get_password_hash, verify_password, create_access_token, get_current_user_id
from .storage import (
    state_file,
    jobs_cache_file,
    get_current_email,
    save_current_email,
    stats_summary,
    load_stats,
    load_jobs_cache,
    save_jobs_cache,
    load_excluded_companies,
    save_excluded_companies,
    DEFAULT_EXCLUDED_COMPANIES,
    load_external_jobs,
    load_external_jobs_done,
    mark_external_job_done,
    append_external_job,
    clear_external_jobs,
    append_log,
    read_logs,
    increment_today,
    clear_jobsdb_session,
    load_auto_runs,
    record_auto_run,
)
from .runner import run_apply
from .debug_log import debug
from .operation_log import op_info, op_error, read_operations
from .jobsdb_login import start_login as jobsdb_start_login, verify_login as jobsdb_verify_login

# 任务状态（手动触发/定时任务）
_running_task: dict[int, bool] = {}
_task_state: dict[int, str] = {}  # "idle" | "running" | "paused"
_current_worker: dict[int, object] = {}  # user_id -> JobsdbWorker
_jobs_cache: dict[int, list] = {}
_jobs_cache_lock = threading.Lock()
_last_verify_success: dict[int, float] = {}  # user_id -> timestamp，用于登录成功后短时内跳过校验


def init_db():
    Base.metadata.create_all(bind=engine)
    # 为已有表补充新列（自动投递）
    for _, sql in [
        ("mode", "ALTER TABLE monitor_settings ADD COLUMN mode INTEGER DEFAULT 1"),
        ("interval_hours", "ALTER TABLE monitor_settings ADD COLUMN interval_hours INTEGER DEFAULT 4"),
        ("max_pages", "ALTER TABLE monitor_settings ADD COLUMN max_pages INTEGER DEFAULT 3"),
        ("next_run_at", "ALTER TABLE monitor_settings ADD COLUMN next_run_at DATETIME"),
        ("last_run_started_at", "ALTER TABLE monitor_settings ADD COLUMN last_run_started_at DATETIME"),
        ("experience_years", "ALTER TABLE monitor_settings ADD COLUMN experience_years INTEGER DEFAULT 3"),
        ("expected_salary", "ALTER TABLE monitor_settings ADD COLUMN expected_salary VARCHAR(20) DEFAULT '16K'"),
    ]:
        try:
            with engine.connect() as conn:
                conn.execute(text(sql))
                conn.commit()
        except Exception:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    from .scheduler import start_scheduler
    start_scheduler()
    yield
    from .scheduler import scheduler
    scheduler.shutdown(wait=False)


app = FastAPI(title="JobsDB 投递 API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def ensure_jobsdb_logged_in(user_id: int, clear_on_fail: bool = True) -> None:
    """
    使用与正式投递相同的 storage_state 轻量打开一次 JobsDB，校验登录态是否仍然有效。
    - clear_on_fail=True：校验失败时清理 session 并抛出 HTTPException（用于 run_apply）
    - clear_on_fail=False：校验失败时仅抛出，不清理（用于 status，避免误删刚登录成功的数据）
    """
    path = state_file(user_id)
    if not path.exists():
        # 根本没有登录过
        raise HTTPException(status_code=400, detail="请先在 JobsDB 登录页完成登录")

    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError:
        # 未安装 Playwright 时不强制校验，避免接口直接不可用（正式投递本身也会失败并在日志中体现）
        return

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                storage_state=str(path),
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/134.0.0.0 Safari/537.36"
                ),
                locale="zh-HK",
                timezone_id="Asia/Hong_Kong",
                extra_http_headers={"Accept-Language": "zh-HK,zh;q=0.9,en;q=0.8"},
            )
            page = context.new_page()
            page.set_default_timeout(45000)
            url = "https://hk.jobsdb.com/zh/jobs?daterange=3"
            page.goto(url, wait_until="domcontentloaded")
            import time
            time.sleep(3)  # 等待 SPA 渲染完成

            current_url = ""
            try:
                current_url = page.url or ""
            except Exception:
                current_url = ""

            # 1) URL 明显是登录/账户入口
            lowered = current_url.lower()
            looks_like_login = any(
                key in lowered for key in ("/login", "signin", "/oauth", "session-expired")
            )
            if "account" in lowered and "accounts.google.com" in lowered:
                looks_like_login = True

            # 2) 正向信号：已登录时通常有「登出 / 個人檔案 / My profile」
            has_logout_ui = False
            try:
                for t in ["登出", "個人檔案", "My profile", "Log out", "Sign out"]:
                    if page.get_by_text(t, exact=False).count() > 0:
                        has_logout_ui = True
                        break
            except Exception:
                pass

            if has_logout_ui:
                # 明确已登录，不检查负向信号
                browser.close()
                return

            # 3) 负向信号：页面上有明确的“登入 / Log in”链接或按钮（排除页脚等次要区域）
            has_login_ui = False
            try:
                # 仅检查导航/头部区域的登录按钮，避免误判页脚「登入|注册」等
                nav = page.locator("header, nav, [role='navigation'], .navbar, .header").first
                if nav.count() > 0:
                    for t in ["登入", "登录", "Log in", "Sign in"]:
                        if nav.get_by_role("link", name=t).count() > 0 or nav.get_by_role("button", name=t).count() > 0:
                            has_login_ui = True
                            break
                if not has_login_ui:
                    # 若无明确 nav，退回到全页：仅当存在 role=button 或 role=link 且文本匹配
                    for t in ["Log in", "Sign in"]:
                        if page.get_by_role("button", name=t).count() > 0 or page.get_by_role("link", name=t).count() > 0:
                            has_login_ui = True
                            break
            except Exception:
                pass

            if looks_like_login or has_login_ui:
                append_log(user_id, f"[排查] 登录校验失败：URL={current_url[:80]}... looks_like_login={looks_like_login} has_login_ui={has_login_ui}")
                if clear_on_fail:
                    clear_jobsdb_session(user_id)
                    append_log(user_id, "检测到 JobsDB 登录已失效，请在 JobsDB 登录页重新登录。")
                raise HTTPException(
                    status_code=400,
                    detail="JobsDB 登录已失效，请在 JobsDB 登录页重新登录后再开始投递。",
                )

            browser.close()
    except HTTPException:
        # 直接透传给上层
        raise
    except Exception:
        # 网络波动或 JobsDB 页面临时异常时，不强制阻断；后续正式投递仍会在日志中暴露问题
        return


# -------- 请求/响应模型 --------
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: str = ""


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class MonitorSettingsUpdate(BaseModel):
    enabled: bool | None = None
    mode: int | None = None
    interval_hours: int | None = None
    max_pages: int | None = None
    mode2_keywords: str | None = None
    mode3_category: str | None = None
    experience_years: int | None = None
    expected_salary: str | None = None


class JobsDBLoginStart(BaseModel):
    email: str


class JobsDBLoginVerify(BaseModel):
    code: str


class ManualApplyRequest(BaseModel):
    mode1: bool = True
    mode2: bool = False
    mode2_keywords: str = ""
    mode3: bool = False
    mode3_category: str = ""
    max_pages: int = 3
    experience_years: int = 3
    expected_salary: str = "16K"
    excluded_companies: str = "MOMAX, AIA, Prudential, Manulife, AXA, FTLife, FWD"
    show_browser: bool = False  # 调试：显示浏览器窗口，便于排查


# -------- 认证 --------
@app.post("/api/auth/register")
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == req.email).first():
        raise HTTPException(status_code=400, detail="该邮箱已注册")
    user = User(
        email=req.email,
        password_hash=get_password_hash(req.password),
        name=(req.name or req.email.split("@")[0])[:100],
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    op_info(user.id, "auth_register", f"email={user.email}", source="backend")
    token = create_access_token(data={"sub": str(user.id)})
    return {"token": token, "user": {"id": user.id, "email": user.email, "name": user.name}}


@app.post("/api/auth/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == req.email).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="邮箱或密码错误")
    op_info(user.id, "auth_login", f"email={user.email}", source="backend")
    token = create_access_token(data={"sub": str(user.id)})
    return {"token": token, "user": {"id": user.id, "email": user.email, "name": user.name}}


@app.get("/api/auth/me")
def me(user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"id": user.id, "email": user.email, "name": user.name}


# -------- 统计 --------
@app.get("/api/stats")
def get_stats(user_id: int = Depends(get_current_user_id)):
    today, d7, d30 = stats_summary(user_id)
    email = get_current_email(user_id)
    auto_runs = load_auto_runs(user_id)

    from datetime import datetime as dt

    def _is_today(iso: str) -> bool:
        try:
            return dt.fromisoformat(iso).date() == dt.now().date()
        except Exception:
            return False

    today_runs = [r for r in auto_runs if _is_today(r.get("at", ""))]
    today_auto_count = len(today_runs)
    today_auto_success = sum((r.get("success") or 0) for r in today_runs)

    fail_streak = 0
    for r in reversed(auto_runs):
        if r.get("kind") == "auto" and r.get("status") in ("login_failed", "all_failed"):
            fail_streak += 1
        else:
            break
    last_auto = next((r for r in reversed(auto_runs) if r.get("kind") == "auto"), None)

    return {
        "today": today,
        "last7": d7,
        "last30": d30,
        "jobsdb_email": email,
        "auto_today_runs": today_auto_count,
        "auto_today_success": today_auto_success,
        "auto_fail_streak": fail_streak,
        "auto_last": last_auto,
    }


@app.get("/api/stats/daily")
def get_stats_daily(user_id: int = Depends(get_current_user_id), days: int = 14):
    """返回最近 N 天每日投递数，用于图表展示"""
    from datetime import datetime, timedelta
    data = load_stats(user_id)
    days = max(7, min(60, days))
    out = []
    for i in range(days - 1, -1, -1):
        d = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        out.append({"date": d, "count": data.get(d, 0)})
    return {"items": out}


# -------- 自动投递（原监控设置）--------
def _run_auto_apply_once(user_id: int) -> None:
    """
    立即按当前自动投递设置跑一轮（与定时任务逻辑一致），
    用于用户在自动投递页点击「保存」后立刻执行一次。
    """
    op_info(user_id, "apply_run_auto", "开始自动投递", source="job")
    debug("_run_auto_apply_once: 开始", user_id=user_id)
    from datetime import datetime, timedelta

    db = SessionLocal()
    try:
        s = get_or_create_monitor_settings(db, user_id)
        if not getattr(s, "enabled", False):
            debug("_run_auto_apply_once: enabled=False 跳过", user_id=user_id)
            return

        mode = getattr(s, "mode", None) or 1
        interval_hours = getattr(s, "interval_hours", None) or 6
        if interval_hours not in (6, 12, 24, 36, 48):
            interval_hours = 6
        max_pages = max(1, min(8, getattr(s, "max_pages", None) or 3))

        now = datetime.utcnow()

        if _running_task.get(user_id):
            return

        _running_task[user_id] = True
        _task_state[user_id] = "running"

        # 记录本次任务前外部待办数量，用于计算新增外部投递
        ext_before = len(load_external_jobs(user_id))

        try:
            ensure_jobsdb_logged_in(user_id, clear_on_fail=False)
        except Exception:
            append_log(user_id, "自动投递：JobsDB 登录已失效，跳过本次，请先在 JobsDB 登录页重新登录。")
            s.next_run_at = now + timedelta(hours=interval_hours)
            db.commit()
            # 记录一次登录失败的自动任务
            record_auto_run(
                user_id,
                {
                    "kind": "auto",
                    "status": "login_failed",
                    "reason": "JobsDB 登录已失效",
                    "total": 0,
                    "success": 0,
                    "failed": 0,
                    "skip": 0,
                    "external": max(0, len(load_external_jobs(user_id)) - ext_before),
                    "duration_sec": 0,
                    "at": now.isoformat(),
                },
            )
            return

        path = state_file(user_id)
        if not path.exists():
            append_log(user_id, "自动投递：未登录 JobsDB，跳过本次。")
            s.next_run_at = now + timedelta(hours=interval_hours)
            db.commit()
            return

        m2k = ""
        m3c = ""
        if mode == 2 and (s.mode2_keywords or "").strip():
            m2k = (s.mode2_keywords or "").strip().split(",")[0].strip() or ""
        if mode == 3 and (s.mode3_category or "").strip():
            m3c = (s.mode3_category or "").strip()
        exp_years = max(0, min(5, getattr(s, "experience_years", None) or 3))
        salary = (getattr(s, "expected_salary", None) or "16K").strip().upper()
        if salary not in ("16K", "17K", "18K", "19K", "20K", "22K", "25K", "28K", "30K"):
            salary = "16K"

        s.last_run_started_at = now
        s.next_run_at = now + timedelta(hours=interval_hours)
        db.commit()

        jobs_list: list[dict] = []

        def on_log(m: str) -> None:
            append_log(user_id, m)

        def on_jobs(p: int, j: list) -> None:
            for x in j:
                x.setdefault("status", "")
                x.setdefault("message", "")
                jobs_list.append({"page": p, "job": x})

        def on_ext(t: str, u: str) -> None:
            append_external_job(user_id, t, u)

        def on_tick() -> None:
            with _jobs_cache_lock:
                _jobs_cache[user_id] = list(jobs_list)
            save_jobs_cache(user_id, jobs_list)

        def on_status(p: int, i: int, st: str, msg: str | None) -> None:
            if st == "成功":
                increment_today(user_id)
            from datetime import datetime as dt
            applied_at = dt.utcnow().isoformat() if st == "成功" else None
            last_block_end = -1
            for idx in range(len(jobs_list) - 1, -1, -1):
                if jobs_list[idx]["page"] == p:
                    last_block_end = idx
                    break
            if last_block_end < 0:
                return
            block_start = last_block_end
            while block_start > 0 and jobs_list[block_start - 1]["page"] == p:
                block_start -= 1
            target = block_start + (i - 1)
            if 0 <= target <= last_block_end:
                jobs_list[target]["job"]["status"] = st
                jobs_list[target]["job"]["message"] = msg or ""
                if applied_at is not None:
                    jobs_list[target]["job"]["applied_at"] = applied_at

        _, jobs_data = run_apply(
            state_file=str(path),
            account_id=get_current_email(user_id) or str(user_id),
            excluded_companies=load_excluded_companies(user_id),
            max_pages=max_pages,
            show_browser=False,
            human_level=1,
            mode_type=mode,
            mode2_keyword=m2k,
            mode3_category_slug=m3c,
            experience_years=exp_years,
            expected_salary=salary,
            on_log=on_log,
            on_jobs_loaded=on_jobs,
            on_job_status=on_status,
            on_external=on_ext,
            worker_holder=_current_worker,
            worker_key=user_id,
            on_tick=on_tick,
        )
        jobs_list = [
            {"page": p, "job": x}
            for (p, jlist) in (jobs_data or [])
            for x in jlist
        ]
        debug("_run_auto_apply_once: 完成", user_id=user_id, jobs_count=len(jobs_list))

        with _jobs_cache_lock:
            _jobs_cache[user_id] = jobs_list
        save_jobs_cache(user_id, jobs_list)
        debug("_run_auto_apply_once: 已保存职位", user_id=user_id, path=str(jobs_cache_file(user_id)))
        success = sum(1 for x in jobs_list if (x.get("job") or {}).get("status") == "成功")
        failed = sum(1 for x in jobs_list if (x.get("job") or {}).get("status") == "失败")
        skip = sum(1 for x in jobs_list if (x.get("job") or {}).get("status") == "跳过")
        append_log(user_id, f"自动投递完成: 共 {len(jobs_list)} 个, 成功 {success}, 失败 {failed}, 跳过 {skip}")

        # 记录任务摘要，便于 Dashboard 展示“今日状况”
        from datetime import datetime as dt

        ext_after = len(load_external_jobs(user_id))
        external_new = max(0, ext_after - ext_before)
        duration_sec = int((dt.utcnow() - now).total_seconds())
        status = "ok"
        reason = ""
        if success <= 0 and len(jobs_list) > 0:
            status = "all_failed"
            reason = "本次任务无成功投递"
        elif len(jobs_list) == 0:
            status = "no_jobs"
            reason = "本次未发现任何可投职位"
        record_auto_run(
            user_id,
            {
                "kind": "auto",
                "status": status,
                "reason": reason,
                "total": len(jobs_list),
                "success": success,
                "failed": failed,
                "skip": skip,
                "external": external_new,
                "duration_sec": duration_sec,
                "at": now.isoformat(),
            },
        )

        s.next_run_at = now + timedelta(hours=interval_hours)
        db.commit()
    except Exception as e:
        debug("_run_auto_apply_once: 异常", user_id=user_id, err=str(e))
        import traceback
        debug("_run_auto_apply_once: traceback", tb=traceback.format_exc())
    finally:
        _running_task.pop(user_id, None)
        _task_state.pop(user_id, None)
        _current_worker.pop(user_id, None)
        db.close()


@app.get("/api/monitor")
def get_monitor(user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    s = get_or_create_monitor_settings(db, user_id)
    mode = getattr(s, "mode", None) or 1
    interval_hours = getattr(s, "interval_hours", None) or 6
    max_pages = getattr(s, "max_pages", None) or 3
    exp_years = getattr(s, "experience_years", None)
    if exp_years is None:
        exp_years = 3
    exp_years = max(0, min(5, int(exp_years)))
    salary = (getattr(s, "expected_salary", None) or "16K").strip().upper()
    if salary not in ("16K", "17K", "18K", "19K", "20K", "22K", "25K", "28K", "30K"):
        salary = "16K"
    next_run_at = getattr(s, "next_run_at", None)
    last_run_started_at = getattr(s, "last_run_started_at", None)
    return {
        "enabled": s.enabled,
        "mode": mode,
        "interval_hours": interval_hours,
        "max_pages": max_pages,
        "mode2_keywords": s.mode2_keywords or "",
        "mode3_category": s.mode3_category or "",
        "experience_years": exp_years,
        "expected_salary": salary,
        "next_run_at": next_run_at.isoformat() if next_run_at else None,
        "last_run_started_at": last_run_started_at.isoformat() if last_run_started_at else None,
    }


@app.put("/api/monitor")
def update_monitor(
    req: MonitorSettingsUpdate,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    s = get_or_create_monitor_settings(db, user_id)
    should_trigger_now = False
    if req.enabled is not None:
        previously_enabled = bool(s.enabled)
        s.enabled = req.enabled
        if req.enabled:
            from datetime import datetime
            s.next_run_at = datetime.utcnow()
            # 保存时若已开启，则立即跑一轮（用户点击保存即表示要执行）
            should_trigger_now = True
    if req.mode is not None:
        s.mode = max(1, min(3, req.mode))
    if req.interval_hours is not None:
        s.interval_hours = req.interval_hours if req.interval_hours in (6, 12, 24, 36, 48) else 6
    if req.max_pages is not None:
        s.max_pages = max(1, min(8, req.max_pages))
    if req.mode2_keywords is not None:
        s.mode2_keywords = req.mode2_keywords[:500]
    if req.mode3_category is not None:
        s.mode3_category = req.mode3_category[:100]
    if req.experience_years is not None:
        s.experience_years = max(0, min(5, req.experience_years))
    if req.expected_salary is not None:
        val = (req.expected_salary or "16K").strip().upper()
        if val in ("16K", "17K", "18K", "19K", "20K", "22K", "25K", "28K", "30K"):
            s.expected_salary = val
    db.commit()

    op_info(user_id, "monitor_update", f"enabled={s.enabled} mode={s.mode}", source="backend")
    if should_trigger_now:
        debug("update_monitor: 保存成功，启动自动投递线程", user_id=user_id)
        t = threading.Thread(target=_run_auto_apply_once, args=(user_id,))
        t.daemon = True
        t.start()
    else:
        debug("update_monitor: 保存成功，enabled=False 不触发", user_id=user_id)

    return {"ok": True}


# -------- JobsDB 登录 --------
@app.post("/api/jobsdb/login/start")
def jobsdb_login_start(
    req: JobsDBLoginStart,
    user_id: int = Depends(get_current_user_id),
):
    path = state_file(user_id)
    ok, msg = jobsdb_start_login(user_id, req.email.strip(), path)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "message": msg}


@app.post("/api/jobsdb/login/verify")
def jobsdb_login_verify(
    req: JobsDBLoginVerify,
    user_id: int = Depends(get_current_user_id),
):
    import time
    path = state_file(user_id)
    ok, msg = jobsdb_verify_login(user_id, req.code.strip(), path)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    if msg and "@" in msg:
        save_current_email(user_id, msg)
    _last_verify_success[user_id] = time.time()
    return {"ok": True, "message": "登录成功"}


@app.get("/api/jobsdb/status")
def jobsdb_status(user_id: int = Depends(get_current_user_id)):
    """
    返回 JobsDB 登录状态（仅根据 storage_state 文件存在 + 保存的邮箱）。
    真实登录态校验在「开始投递」时由 ensure_jobsdb_logged_in 完成，避免 status 误判导致 UI 反复提示未登录。
    """
    path = state_file(user_id)
    email = get_current_email(user_id)
    logged_in = path.exists()
    return {"logged_in": logged_in, "email": email or ""}


@app.delete("/api/jobsdb/logout")
def jobsdb_logout(user_id: int = Depends(get_current_user_id)):
    op_info(user_id, "jobsdb_logout", "", source="backend")
    clear_jobsdb_session(user_id)
    return {"ok": True, "message": "已注销 JobsDB 账号"}


# -------- 分类列表（模式三用）--------
@app.get("/api/classifications")
def get_classifications():
    from jobsdb_worker import DEFAULT_CLASSIFICATIONS
    cache = ACCOUNTS_BASE / "classifications.json"
    if cache.exists():
        import json
        try:
            data = json.loads(cache.read_text(encoding="utf-8"))
            return data.get("items", DEFAULT_CLASSIFICATIONS)
        except Exception:
            pass
    return DEFAULT_CLASSIFICATIONS


# -------- 手动触发投递 --------
@app.post("/api/apply/run")
def run_manual_apply(
    req: ManualApplyRequest,
    user_id: int = Depends(get_current_user_id),
):
    if _running_task.get(user_id):
        raise HTTPException(status_code=400, detail="已有任务在运行")
    op_info(user_id, "apply_run_manual", f"modes=m1={req.mode1} m2={req.mode2} m3={req.mode3}", source="backend")

    # 在真正启动投递任务前，先用 Playwright 进行一次轻量校验，确保 JobsDB 登录态仍然有效
    ensure_jobsdb_logged_in(user_id)
    path = state_file(user_id)

    def _run():
        _running_task[user_id] = True
        _task_state[user_id] = "running"
        with _jobs_cache_lock:
            _jobs_cache[user_id] = []  # 任务开始时清空，便于实时展示
        jobs_list = []
        account_id = get_current_email(user_id) or str(user_id)

        def on_log(m):
            append_log(user_id, m)

        def on_jobs(p, j):
            for x in j:
                x.setdefault("status", "")
                x.setdefault("message", "")
                jobs_list.append({"page": p, "job": x})
            with _jobs_cache_lock:
                _jobs_cache[user_id] = jobs_list  # 同一引用，on_status 更新后前端可见

        def on_status(p, i, s, m):
            if s == "成功":
                increment_today(user_id)
            from datetime import datetime as dt
            applied_at = dt.utcnow().isoformat() if s == "成功" else None
            # 找到 page p 最近一批中的第 i 个 job（1-based），多模式时 page 会重复
            last_block_end = -1
            for idx in range(len(jobs_list) - 1, -1, -1):
                if jobs_list[idx]["page"] == p:
                    last_block_end = idx
                    break
            if last_block_end < 0:
                return
            block_start = last_block_end
            while block_start > 0 and jobs_list[block_start - 1]["page"] == p:
                block_start -= 1
            target = block_start + (i - 1)
            if 0 <= target <= last_block_end:
                jobs_list[target]["job"]["status"] = s
                jobs_list[target]["job"]["message"] = m or ""
                if applied_at is not None:
                    jobs_list[target]["job"]["applied_at"] = applied_at

        def on_ext(t, u):
            append_external_job(user_id, t, u)

        modes = []
        if req.mode1:
            modes.append((1, "", ""))
        if req.mode2 and req.mode2_keywords.strip():
            for kw in req.mode2_keywords.split(","):
                k = kw.strip()
                if k:
                    modes.append((2, k, ""))
        if req.mode3 and req.mode3_category.strip():
            modes.append((3, "", req.mode3_category.strip()))

        if not modes:
            modes = [(1, "", "")]

        excluded = load_excluded_companies(user_id)
        max_pages = max(1, min(10, int(req.max_pages) if req.max_pages else 3))
        exp_years = max(0, min(5, int(req.experience_years) if req.experience_years is not None else 3))
        salary = (req.expected_salary or "16K").strip().upper()[:10] or "16K"

        last_worker = None
        for mode_type, m2k, m3c in modes:
            last_worker, _ = run_apply(
                state_file=str(path),
                account_id=account_id,
                excluded_companies=excluded,
                max_pages=max_pages,
                show_browser=bool(req.show_browser),
                human_level=1,
                mode_type=mode_type,
                mode2_keyword=m2k,
                mode3_category_slug=m3c,
                experience_years=exp_years,
                expected_salary=salary,
                on_log=on_log,
                on_jobs_loaded=on_jobs,
                on_job_status=on_status,
                on_external=on_ext,
                worker_holder=_current_worker,
                worker_key=user_id,
            )
            # 用户点击停止并重启后，当前 worker 已被替换，不再跑下一个模式
            if _current_worker.get(user_id) is not last_worker:
                break

        debug("run_manual_apply: 完成", user_id=user_id, jobs_count=len(jobs_list))

        with _jobs_cache_lock:
            _jobs_cache[user_id] = jobs_list
        save_jobs_cache(user_id, jobs_list)
        debug("run_manual_apply: 已保存职位", user_id=user_id)
        success = sum(1 for x in jobs_list if (x.get("job") or {}).get("status") == "成功")
        failed = sum(1 for x in jobs_list if (x.get("job") or {}).get("status") == "失败")
        skip = sum(1 for x in jobs_list if (x.get("job") or {}).get("status") == "跳过")
        append_log(user_id, f"手动投递完成: 共 {len(jobs_list)} 个, 成功 {success}, 失败 {failed}, 跳过 {skip}")

        from datetime import datetime as dt
        record_auto_run(
            user_id,
            {
                "kind": "manual",
                "status": "ok",
                "total": len(jobs_list),
                "success": success,
                "failed": failed,
                "skip": skip,
                "at": dt.utcnow().isoformat(),
            },
        )

        # 仅当当前仍是本任务时才清空状态，避免用户已重启任务时覆盖
        if last_worker is not None and _current_worker.get(user_id) is last_worker:
            _running_task[user_id] = False
            _task_state[user_id] = "idle"
            _current_worker.pop(user_id, None)

    t = threading.Thread(target=_run)
    t.start()
    return {"ok": True, "message": "任务已启动，请查看日志"}


@app.get("/api/apply/status")
def apply_status(user_id: int = Depends(get_current_user_id)):
    state = _task_state.get(user_id, "idle")
    # 更稳健的运行中判断：同时参考 _running_task 与 _task_state
    running_flag = bool(_running_task.get(user_id))
    running = running_flag or state in ("running", "paused")
    progress = None
    with _jobs_cache_lock:
        jobs = _jobs_cache.get(user_id) or []
    if jobs:
        total = len(jobs)
        success = sum(1 for j in jobs if (j.get("job") or {}).get("status") == "成功")
        failed = sum(1 for j in jobs if (j.get("job") or {}).get("status") == "失败")
        skip = sum(1 for j in jobs if (j.get("job") or {}).get("status") == "跳过")
        pending = sum(1 for j in jobs if not (j.get("job") or {}).get("status"))
        progress = {"total": total, "success": success, "failed": failed, "skip": skip, "pending": pending}
    return {"running": running, "state": state, "progress": progress}


@app.post("/api/apply/pause")
def apply_pause(user_id: int = Depends(get_current_user_id)):
    worker = _current_worker.get(user_id)
    if not worker:
        raise HTTPException(status_code=400, detail="当前无运行中的任务")
    worker.request_pause()
    _task_state[user_id] = "paused"
    return {"ok": True, "state": "paused"}


@app.post("/api/apply/resume")
def apply_resume(user_id: int = Depends(get_current_user_id)):
    worker = _current_worker.get(user_id)
    if not worker:
        raise HTTPException(status_code=400, detail="当前无运行中的任务")
    worker.request_resume()
    _task_state[user_id] = "running"
    return {"ok": True, "state": "running"}


@app.post("/api/apply/stop")
def apply_stop(user_id: int = Depends(get_current_user_id)):
    worker = _current_worker.get(user_id)
    if not worker:
        raise HTTPException(status_code=400, detail="当前无运行中的任务")
    worker.request_stop()
    # 立即置为 idle，便于用户切换模式后重新开始（旧 worker 会在后台自行退出）
    _running_task[user_id] = False
    _task_state[user_id] = "idle"
    return {"ok": True, "message": "已请求停止，可切换模式后重新开始"}


# -------- 职位列表 --------
@app.get("/api/jobs")
def get_jobs(user_id: int = Depends(get_current_user_id)):
    # 有手动任务在跑时，用内存缓存做实时展示；否则一律从文件加载
    with _jobs_cache_lock:
        mem = _jobs_cache.get(user_id)
    if _running_task.get(user_id) and mem is not None:
        debug("get_jobs: 用内存缓存", user_id=user_id, count=len(mem))
        return {"jobs": mem}
    from_file = load_jobs_cache(user_id)
    debug("get_jobs: 从文件加载", user_id=user_id, count=len(from_file))
    return {"jobs": from_file}


# -------- 日志 --------
@app.get("/api/logs")
def get_logs(user_id: int = Depends(get_current_user_id), limit: int = 500, ops: int = 0):
    """logs: 用户文本日志; operations: 操作指令日志（ops=1 时返回）"""
    lines = read_logs(user_id, limit=limit)
    out = {"logs": lines}
    if ops:
        out["operations"] = read_operations(user_id, limit=min(500, limit))
    return out


class LogReportRequest(BaseModel):
    action: str
    detail: str = ""
    level: str = "info"


@app.post("/api/logs/report")
def report_log(req: LogReportRequest, user_id: int = Depends(get_current_user_id)):
    """前端上报操作日志"""
    op_info(user_id, req.action, req.detail, source="frontend")
    return {"ok": True}


# -------- 排除公司黑名单 --------
@app.get("/api/excluded-companies")
def get_excluded_companies(user_id: int = Depends(get_current_user_id)):
    return {"companies": load_excluded_companies(user_id)}


class ExcludedCompaniesUpdate(BaseModel):
    companies: list[str]


@app.put("/api/excluded-companies")
def update_excluded_companies(
    req: ExcludedCompaniesUpdate,
    user_id: int = Depends(get_current_user_id),
):
    items = [x.strip() for x in req.companies if x and x.strip()]
    save_excluded_companies(user_id, items if items else list(DEFAULT_EXCLUDED_COMPANIES))
    return {"ok": True, "companies": load_excluded_companies(user_id)}


# -------- 外部投递待办 --------
@app.get("/api/external")
def get_external(user_id: int = Depends(get_current_user_id), include_done: bool = False):
    items = load_external_jobs(user_id)
    done_set = load_external_jobs_done(user_id)
    jobs = [{"title": t, "url": u, "done": u.strip().lower() in done_set} for t, u in items]
    if not include_done:
        jobs = [j for j in jobs if not j["done"]]
    return {"jobs": jobs}


class ExternalMarkDoneRequest(BaseModel):
    url: str


@app.post("/api/external/mark-done")
def external_mark_done(
    req: ExternalMarkDoneRequest,
    user_id: int = Depends(get_current_user_id),
):
    mark_external_job_done(user_id, req.url)
    return {"ok": True}


@app.delete("/api/external")
def clear_external(user_id: int = Depends(get_current_user_id)):
    clear_external_jobs(user_id)
    return {"ok": True}


# -------- 健康检查 --------
@app.get("/api/health")
def health():
    return {"status": "ok"}


# -------- 生产环境：静态文件与 SPA --------
_STATIC_DIR = Path(__file__).resolve().parent.parent / "web" / "dist"
if _STATIC_DIR.exists():
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse

    app.mount("/assets", StaticFiles(directory=_STATIC_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path.startswith("api"):
            raise HTTPException(status_code=404, detail="Not found")
        path = full_path.split("?")[0]
        if path in ("", "index.html"):
            return FileResponse(_STATIC_DIR / "index.html")
        f = _STATIC_DIR / path
        if f.is_file():
            return FileResponse(f)
        return FileResponse(_STATIC_DIR / "index.html")
