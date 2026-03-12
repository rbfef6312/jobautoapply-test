"""自动投递：按用户设置每隔 N 小时运行一次"""
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from .database import SessionLocal, get_or_create_monitor_settings
from .storage import (
    state_file,
    get_current_email,
    append_log,
    append_external_job,
    increment_today,
    save_jobs_cache,
    load_excluded_companies,
)
from .runner import run_apply
from .main import (
    _running_task,
    _task_state,
    _current_worker,
    _jobs_cache,
    _jobs_cache_lock,
)

scheduler = BackgroundScheduler()


def _run_user_task(user_id: int):
    db = SessionLocal()
    try:
        s = get_or_create_monitor_settings(db, user_id)
        if not s.enabled:
            return

        mode = getattr(s, "mode", None) or 1
        interval_hours = getattr(s, "interval_hours", None) or 6
        if interval_hours not in (6, 12, 24, 36, 48):
            interval_hours = 6
        max_pages = max(1, min(8, getattr(s, "max_pages", None) or 3))

        now = datetime.utcnow()
        next_run = getattr(s, "next_run_at", None)
        if next_run and next_run > now:
            return

        if _running_task.get(user_id):
            return

        try:
            from .main import ensure_jobsdb_logged_in
            ensure_jobsdb_logged_in(user_id, clear_on_fail=False)
        except Exception:
            append_log(user_id, "自动投递：JobsDB 登录已失效，跳过本次，请先在 JobsDB 登录页重新登录。")
            s.next_run_at = now + timedelta(hours=interval_hours)
            db.commit()
            return

        path = state_file(user_id)
        if not path.exists():
            append_log(user_id, "自动投递：未登录 JobsDB，跳过本次。")
            s.next_run_at = now + timedelta(hours=interval_hours)
            db.commit()
            return

        _running_task[user_id] = True
        _task_state[user_id] = "running"
        with _jobs_cache_lock:
            _jobs_cache[user_id] = []

        s.last_run_started_at = now
        s.next_run_at = now + timedelta(hours=interval_hours)
        db.commit()

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

        jobs_list = []

        def on_log(m):
            append_log(user_id, m)

        def on_jobs(p, j):
            for x in j:
                x.setdefault("status", "")
                x.setdefault("message", "")
                jobs_list.append({"page": p, "job": x})

        def on_ext(t, u):
            append_external_job(user_id, t, u)

        def on_status(p, i, st, msg):
            if st == "成功":
                increment_today(user_id)
            applied_at = datetime.utcnow().isoformat() if st == "成功" else None
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

        def on_tick():
            with _jobs_cache_lock:
                _jobs_cache[user_id] = list(jobs_list)
            save_jobs_cache(user_id, jobs_list)

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
        # 用返回值构建职位列表（避免跨线程 Qt 信号未送达导致 jobs_list 为空）
        jobs_list = [
            {"page": p, "job": x}
            for (p, jlist) in (jobs_data or [])
            for x in jlist
        ]

        with _jobs_cache_lock:
            _jobs_cache[user_id] = jobs_list
        save_jobs_cache(user_id, jobs_list)
        success = sum(1 for x in jobs_list if (x.get("job") or {}).get("status") == "成功")
        failed = sum(1 for x in jobs_list if (x.get("job") or {}).get("status") == "失败")
        skip = sum(1 for x in jobs_list if (x.get("job") or {}).get("status") == "跳过")
        append_log(user_id, f"自动投递完成: 共 {len(jobs_list)} 个, 成功 {success}, 失败 {failed}, 跳过 {skip}")

        s.next_run_at = now + timedelta(hours=interval_hours)
        db.commit()
    finally:
        _running_task.pop(user_id, None)
        _task_state.pop(user_id, None)
        _current_worker.pop(user_id, None)
        db.close()


def _scheduled_job():
    db = SessionLocal()
    try:
        from .database import User
        users = db.query(User).all()
        for u in users:
            try:
                _run_user_task(u.id)
            except Exception as e:
                append_log(u.id, f"自动投递异常：{e}")
    finally:
        db.close()


def start_scheduler():
    scheduler.add_job(
        _scheduled_job,
        "interval",
        minutes=5,
        id="jobsdb_auto_apply",
        replace_existing=True,
    )
    scheduler.start()
