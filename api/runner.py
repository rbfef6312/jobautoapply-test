"""
使用现有 JobsdbWorker 运行投递任务（需要 PySide6）
"""
import sys
import threading
from pathlib import Path

# 确保项目根目录在 path 中
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QCoreApplication


def run_apply(
    state_file: str,
    account_id: str,
    excluded_companies: list[str] | None = None,
    max_pages: int = 10,
    show_browser: bool = False,
    human_level: int = 1,
    mode_type: int = 1,
    mode2_keyword: str = "",
    mode3_category_slug: str = "",
    experience_years: int = 3,
    expected_salary: str = "16K",
    on_log=None,
    on_jobs_loaded=None,
    on_job_status=None,
    on_external=None,
    worker_holder: dict | None = None,
    worker_key=None,
    on_tick=None,
):
    """
    运行投递任务。回调：on_log(msg), on_jobs_loaded(page_idx, jobs), on_job_status(page_idx, job_idx, status, msg), on_external(title, url)
    返回本次创建的 worker，供调用方判断是否仍为当前任务。
    """
    from jobsdb_worker import JobsdbWorker

    logs: list[str] = []
    jobs_data: list[tuple] = []
    job_statuses: list[dict] = []

    def _on_log(msg: str):
        logs.append(msg)
        if on_log:
            on_log(msg)

    def _on_jobs(p: int, j: list):
        jobs_data.append((p, j))
        if on_jobs_loaded:
            on_jobs_loaded(p, j)

    def _jobs_callback(p: int, j: list):
        """直接回调，不依赖 Qt 信号，确保后台线程（自动投递）能可靠收集职位"""
        jobs_data.append((p, j))
        try:
            from .debug_log import debug
            debug("runner _jobs_callback", page=p, count=len(j), total_pages=len(jobs_data))
        except Exception:
            pass

    def _log_callback(msg: str):
        """直接回调写日志，不依赖 Qt 信号"""
        if on_log:
            on_log(msg)

    def _status_callback(p: int, i: int, s: str, m: str):
        """直接回调更新投递状态，确保职位列表备注实时更新"""
        if on_job_status:
            on_job_status(p, i, s, m)

    def _on_status(p: int, i: int, s: str, m: str):
        job_statuses.append({"page": p, "job": i, "status": s, "message": m})
        if on_job_status:
            on_job_status(p, i, s, m)

    def _on_ext(t: str, u: str):
        if on_external:
            on_external(t, u)

    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    worker = JobsdbWorker(
        state_file=state_file,
        excluded_companies=excluded_companies or [],
        max_pages=max_pages,
        show_browser=show_browser,
        slow_mo_ms=0,
        human_level=human_level,
        mode_type=mode_type,
        mode2_keyword=mode2_keyword,
        mode3_category_slug=mode3_category_slug,
        experience_years=experience_years,
        expected_salary=expected_salary,
        on_jobs_loaded_callback=_jobs_callback,
        on_log_callback=_log_callback,
        on_job_status_callback=_status_callback,
    )
    worker.log_message.connect(_on_log)
    worker.jobs_loaded.connect(_on_jobs)
    worker.job_status_changed.connect(_on_status)
    worker.external_job_detected.connect(_on_ext)
    if worker_holder is not None and worker_key is not None:
        worker_holder[worker_key] = worker
    try:
        worker.start()
        import time
        _last_tick = time.time()
        while worker.isRunning():
            app.processEvents()
            if on_tick and (time.time() - _last_tick) >= 0.5:
                _last_tick = time.time()
                try:
                    on_tick()
                except Exception:
                    pass
            time.sleep(0.2)  # 降低 CPU 占用
        worker.wait()
        flat_count = sum(len(j) for _, j in jobs_data)
        try:
            from .debug_log import debug
            debug("run_apply 返回", pages=len(jobs_data), jobs=flat_count)
        except Exception:
            pass
        return (worker, jobs_data)
    finally:
        # 仅当当前仍是本 worker 时才移除，避免用户已重启任务时误删新 worker
        if worker_holder is not None and worker_key is not None and worker_holder.get(worker_key) is worker:
            worker_holder.pop(worker_key, None)
