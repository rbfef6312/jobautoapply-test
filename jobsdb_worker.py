from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
import random
import re
import time
from urllib.parse import urlparse, urlencode, parse_qs, urlunparse
from typing import List, Dict, Any

from PySide6.QtCore import QThread, Signal

# 配置（可选从 api.config 读取，兼容 standalone）
def _cfg(key: str, default: Any) -> Any:
    try:
        from api.config import PAGE_DEFAULT_TIMEOUT_MS, WAIT_CARDS_TIMEOUT_MS
        if key == "page_timeout":
            return PAGE_DEFAULT_TIMEOUT_MS
        if key == "wait_cards_timeout":
            return WAIT_CARDS_TIMEOUT_MS
    except Exception:
        pass
    return default

# 选择器：主选 + 备用，页面结构变化时可快速切换
JOB_CARD_SELECTORS = [
    "article[data-automation='normalJob']",
    "article[data-automation='job-card']",
    "[data-automation='searchResults'] article",
]
SALARY_SELECTORS = [
    "a[data-automation='jobSalary']",
    "[data-automation='jobSalary']",
    "div.eihuid5b.eihuidhf.eihuid6n > span:nth-child(2)",  # 备用（类名易变）
]
DATE_SELECTORS = [
    "span > div._109pqcno:first-child",
    "span._18ybopc4",
    "[data-automation='jobDate']",
]

# 预置分类（抓取失败时回退）
DEFAULT_CLASSIFICATIONS: List[Dict[str, str]] = [
    {"name": "Accounting", "slug": "accounting"},
    {"name": "Administration & Office Support", "slug": "administration-office-support"},
    {"name": "Banking & Financial Services", "slug": "banking-financial-services"},
    {"name": "Construction", "slug": "construction"},
    {"name": "Design & Architecture", "slug": "design-architecture"},
    {"name": "Engineering", "slug": "engineering"},
    {"name": "Farming, Animals & Conservation", "slug": "farming-animals-conservation"},
    {"name": "Government & Defence", "slug": "government-defence"},
    {"name": "Healthcare & Medical", "slug": "healthcare-medical"},
    {"name": "Hospitality & Tourism", "slug": "hospitality-tourism"},
    {"name": "Human Resources & Recruitment", "slug": "human-resources-recruitment"},
    {"name": "Information & Communication Technology", "slug": "information-communication-technology"},
    {"name": "Insurance & Superannuation", "slug": "insurance-superannuation"},
    {"name": "Legal", "slug": "legal"},
    {"name": "Manufacturing, Transport & Logistics", "slug": "manufacturing-transport-logistics"},
    {"name": "Marketing & Communications", "slug": "marketing-communications"},
    {"name": "Mining, Resources & Energy", "slug": "mining-resources-energy"},
    {"name": "Real Estate & Property", "slug": "real-estate-property"},
    {"name": "Retail & Consumer Products", "slug": "retail-consumer-products"},
    {"name": "Sales", "slug": "sales"},
    {"name": "Science & Technology", "slug": "science-technology"},
    {"name": "Self Employment", "slug": "self-employment"},
    {"name": "Sport & Recreation", "slug": "sport-recreation"},
    {"name": "Trades & Services", "slug": "trades-services"},
]


@dataclass
class JobInfo:
    title: str = ""
    link: str = ""
    company: str = ""
    location: str = ""
    salary: str = ""
    date: str = ""


class JobsdbWorker(QThread):
    """
    后台线程：负责使用 Playwright 抓取 JobsDB 职位并（未来）自动投递。

    当前 skeleton 版本仅：
    - 使用保存的 storage_state 恢复登录
    - 打开 JobsDB 职位列表第一页
    - 抓取该页的职位信息并发回 UI
    """

    jobs_loaded = Signal(int, list)  # page_index, List[Dict]
    job_status_changed = Signal(int, int, str, str)  # page_index, job_index, status, message
    log_message = Signal(str)
    # 仅当点击 Apply 后跳转到非 JobsDB 域名时发出，供外部投递待办记录
    external_job_detected = Signal(str, str)  # title, job_url（JobsDB 职位链接）

    def __init__(
        self,
        state_file: str,
        excluded_companies: list[str] | None = None,
        max_pages: int = 10,
        show_browser: bool = True,
        slow_mo_ms: int = 0,
        debug_dir: str | None = None,
        human_level: int = 1,
        mode_type: int = 1,
        mode2_keyword: str = "",
        mode3_category_slug: str = "",
        experience_years: int = 3,
        expected_salary: str = "16K",
        on_jobs_loaded_callback=None,
        on_log_callback=None,
        on_job_status_callback=None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.on_jobs_loaded_callback = on_jobs_loaded_callback
        self.on_log_callback = on_log_callback
        self.on_job_status_callback = on_job_status_callback  # 直接回调更新状态，不依赖 Qt 信号
        self.state_file = state_file
        self.excluded_companies = excluded_companies or []
        self.max_pages = max(1, int(max_pages))
        self.show_browser = bool(show_browser)
        self.slow_mo_ms = max(0, int(slow_mo_ms))
        self.debug_dir = Path(debug_dir) if debug_dir else (Path(__file__).resolve().parent / "debug")
        # 0: 低（速度优先），1: 中（推荐），2: 高（更像真人）
        self.human_level = human_level if human_level in (0, 1, 2) else 1
        # 1: 推荐岗位，2: 职位关键词，3: 职位类别
        self.mode_type = mode_type if mode_type in (1, 2, 3) else 1
        self.mode2_keyword = (mode2_keyword or "").strip()
        self.mode3_category_slug = (mode3_category_slug or "").strip()
        # 经验年限：0~5 对应 0年、1年…5年
        self.experience_years = max(0, min(5, int(experience_years) if experience_years is not None else 3))
        # 期望月薪：16K, 17K, ..., 30K
        self.expected_salary = (expected_salary or "16K").strip().upper()
        self._stop_requested = False
        self._paused = False

    def request_stop(self) -> None:
        self._stop_requested = True

    def request_pause(self) -> None:
        self._paused = True

    def request_resume(self) -> None:
        self._paused = False

    def _wait_if_paused(self) -> None:
        while self._paused and not self._stop_requested:
            time.sleep(0.5)

    def _compute_jobs_url(self) -> str:
        """根据模式构造职位列表 URL。均使用 /zh/ 中文版，确保与用户手动访问一致。"""
        try:
            from api.config import JOBSDB_BASE_URL
            base = JOBSDB_BASE_URL.rstrip("/") + "/zh"
        except Exception:
            base = "https://hk.jobsdb.com/zh"
        if self.mode_type == 1:
            # 推荐岗位 / 最近3天职位（登录后 JobsDB 会展示个性化推荐）
            return f"{base}/jobs?daterange=3"
        if self.mode_type == 2:
            kw = self.mode2_keyword.lower().replace(" ", "-")
            if not kw:
                return f"{base}/jobs?daterange=3"
            return f"{base}/{kw}-jobs?daterange=3"
        if self.mode_type == 3:
            slug = self.mode3_category_slug.strip().lower().replace(" ", "-")
            if not slug:
                return f"{base}/jobs?daterange=3"
            return f"{base}/jobs-in-{slug}?daterange=3"
        return f"{base}/jobs?daterange=3"

    def run(self) -> None:  # noqa: D401
        """
        QThread 入口。
        """
        self._run_impl()

    def _log(self, msg: str) -> None:
        """同时 emit 和直接回调，确保日志在后台线程也能写入"""
        self.log_message.emit(msg)
        if self.on_log_callback:
            try:
                self.on_log_callback(msg)
            except Exception:
                pass

    def _emit_status(self, page_index: int, job_index: int, status: str, message: str = "") -> None:
        """同时 emit 和直接回调，确保投递状态能实时更新到职位列表"""
        self.job_status_changed.emit(page_index, job_index, status, message)
        if self.on_job_status_callback:
            try:
                self.on_job_status_callback(page_index, job_index, status, message)
            except Exception:
                pass

    def _run_impl(self) -> None:
        try:
            from playwright.sync_api import sync_playwright  # type: ignore
        except ImportError:
            self._log(
                "未安装 Playwright，无法执行抓取。\n"
                "请先在命令行中执行：\n"
                "  pip install playwright\n"
                "  playwright install"
            )
            return

        self._log("启动 Playwright，准备抓取并投递 JobsDB 职位…")

        try:
            with sync_playwright() as p:
                # 尽量贴近真实浏览器，降低“无卡片/反爬页面”的概率
                browser = p.chromium.launch(
                    headless=not self.show_browser,
                    slow_mo=self.slow_mo_ms if self.show_browser else 0,
                    args=["--disable-blink-features=AutomationControlled"],
                )
                context = browser.new_context(
                    storage_state=self.state_file,
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/134.0.0.0 Safari/537.36"
                    ),
                    locale="zh-HK",
                    timezone_id="Asia/Hong_Kong",
                    extra_http_headers={"Accept-Language": "zh-HK,zh;q=0.9,en;q=0.8"},
                )
                context.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
                )
                list_page = context.new_page()
                list_page.set_default_timeout(_cfg("page_timeout", 45000))

                jobs_url = self._compute_jobs_url()
                mode_names = {1: "推荐岗位", 2: "职位关键词", 3: "职位类别"}
                self._log(f"使用模式：{mode_names.get(self.mode_type, '推荐岗位')}，请求 URL：{jobs_url}")
                list_page.goto(jobs_url, wait_until="domcontentloaded")
                self._random_wait(3, 5)  # 等待职位列表/个性化推荐内容加载
                try:
                    final_url = list_page.url
                    page_title = list_page.title()
                    self._log(f"[排查] 加载后实际 URL：{final_url}\n[排查] 页面标题：{page_title}")
                except Exception as e:
                    self._log(f"[排查] 无法读取页面信息：{e}")

                for page_index in range(1, self.max_pages + 1):
                    self._wait_if_paused()
                    if self._stop_requested:
                        self._log("收到停止请求，中断任务。")
                        break

                    ok = self._wait_for_job_cards(list_page)
                    if not ok:
                        self._dump_debug_artifacts(list_page, prefix=f"list_page_{page_index}_no_cards")
                        url = ""
                        title = ""
                        try:
                            url = list_page.url
                        except Exception:
                            url = ""
                        try:
                            title = list_page.title()
                        except Exception:
                            title = ""
                        self._log(
                            "在页面中未找到职位卡片。\n"
                            f"- url: {url}\n"
                            f"- title: {title}\n"
                            "可能原因：登录态未生效 / 被反爬拦截 / 页面结构改变。"
                        )
                        break

                    jobs = self._extract_jobs_from_list_page(list_page)
                    if not jobs:
                        self._log("未能从当前页面提取到任何职位。")
                        break
                    try:
                        curl = list_page.url
                        preview = " | ".join((j.get("title") or j.get("company") or "-")[:30] for j in jobs[:5])
                        self._log(f"[排查] 第{page_index}页 URL：{curl}，职位数：{len(jobs)}，前几条：{preview}")
                    except Exception:
                        pass
                    if self.on_jobs_loaded_callback:
                        try:
                            self.on_jobs_loaded_callback(page_index, jobs)
                        except Exception:
                            pass
                    self.jobs_loaded.emit(page_index, jobs)

                    # 逐条投递
                    for job_index, job in enumerate(jobs, start=1):
                        self._wait_if_paused()
                        if self._stop_requested:
                            self._log("收到停止请求，中断投递。")
                            break

                        title = (job.get("title") or "").strip()
                        company = (job.get("company") or "").strip()
                        link = (job.get("link") or "").strip()

                        if title and "PART-TIME" in title.upper():
                            self._emit_status(page_index, job_index, "跳过", "PART-TIME")
                            continue

                        if self._is_company_excluded(company):
                            self._emit_status(page_index, job_index, "跳过", f"排除公司：{company}")
                            continue

                        if not link:
                            self._emit_status(page_index, job_index, "失败", "缺少职位链接")
                            continue

                        self._emit_status(page_index, job_index, "投递中", "")
                        success, message = self._apply_single_job(context, link, title)
                        # 仅当填表失败时重试 3 次；已投递/外部站点等直接跳过
                        if not success and self._is_form_failure(message):
                            for attempt in range(2):
                                self._log(f"填表失败（第{attempt + 1}次），{message}，稍后重试…")
                                self._random_wait(2, 5)
                                success, message = self._apply_single_job(context, link, title)
                                if success or not self._is_form_failure(message):
                                    break
                            if not success:
                                message = f"重试3次后仍失败：{message}"
                        self._emit_status(
                            page_index,
                            job_index,
                            "成功" if success else "失败",
                            message,
                        )

                        self._random_wait(10, 15)

                    if self._stop_requested:
                        break

                    # 翻页
                    has_next = self._goto_next_page(list_page, page_index + 1)
                    if not has_next:
                        self._log("未检测到下一页，任务结束。")
                        break

                    self._random_wait(2, 5)

                browser.close()
        except Exception as e:  # noqa: BLE001
            self._log(f"抓取职位列表时发生异常：{e}")

    def _dump_debug_artifacts(self, page, prefix: str) -> None:  # type: ignore[no-untyped-def]
        """不再保存截图/HTML，仅保留空实现避免调用处报错。"""
        pass

    def _random_wait(self, min_seconds: int, max_seconds: int) -> None:
        # 根据人类化等级调整等待区间
        factor = 1.0
        if self.human_level == 0:
            factor = 0.6
        elif self.human_level == 2:
            factor = 1.4
        t = random.uniform(float(min_seconds), float(max_seconds)) * factor
        time.sleep(t)

    def _random_scroll(self, page) -> None:  # type: ignore[no-untyped-def]
        try:
            height = page.evaluate("() => document.body.scrollHeight") or 0
            if height <= 0:
                return

            # 根据人类化等级控制滚动次数与幅度
            if self.human_level == 0:
                # 低：少量轻微滚动
                steps = 1
            elif self.human_level == 2:
                # 高：多段慢滚
                steps = 3
            else:
                # 中：适中
                steps = 2

            for _ in range(steps):
                top = random.randint(0, int(height))
                page.evaluate(
                    "(top) => window.scrollTo({top, behavior: 'smooth'})",
                    top,
                )
                self._random_wait(0, 2)
        except Exception:
            return

    def _is_form_failure(self, message: str) -> bool:
        """是否属于填表/检测失败（可重试）；已投递、外部站点等不可重试。"""
        if not message:
            return True
        m = message.lower()
        if "已投递" in m or "you applied" in m:
            return False
        if "外部" in m or "外站" in m or "external" in m:
            return False
        if "未找到 apply 按钮" in m or "apply 按钮" in m and "未找到" in m:
            return True  # 元素未找到，可重试
        if "timeout" in m or "超时" in m or "timed out" in m:
            return True  # 网络/加载超时，可重试
        return True

    def _is_on_jobsdb_domain(self, url: str) -> bool:
        """判断是否仍在 JobsDB/SEEK 体系内。JobsDB 属 SEEK 集团，申请表单可能托管于 seek.com 等域名。"""
        try:
            if not url or url.strip() in ("about:blank", ""):
                return True  # 空白页/未跳转时不判定为站外
            host = urlparse(url).netloc.lower()
            if "jobsdb.com" in host or "jobsdb.hk" in host:
                return True
            if "seek.com" in host or "seek.com.au" in host:
                return True  # SEEK 集团申请表单
            if "jobstreet.com" in host:
                return True  # SEEK 旗下品牌
            return False
        except Exception:
            return False

    def _is_company_excluded(self, company: str) -> bool:
        if not company:
            return False
        c = company.lower()
        for key in self.excluded_companies:
            if key and key.lower() in c:
                return True
        return False

    def _wait_for_job_cards(self, list_page) -> bool:  # type: ignore[no-untyped-def]
        timeout = _cfg("wait_cards_timeout", 15000)
        for sel in JOB_CARD_SELECTORS:
            try:
                locator = list_page.locator(sel)
                locator.first.wait_for(timeout=timeout)
                if locator.count() > 0:
                    return True
            except Exception:
                continue
        return False

    def _extract_jobs_from_list_page(self, list_page) -> List[Dict[str, str]]:  # type: ignore[no-untyped-def]
        locator = None
        for sel in JOB_CARD_SELECTORS:
            loc = list_page.locator(sel)
            if loc.count() > 0:
                locator = loc
                break
        if locator is None:
            locator = list_page.locator(JOB_CARD_SELECTORS[0])
        count = locator.count()
        self._log(f"检测到职位卡片数量：{count}")

        jobs: List[Dict[str, str]] = []
        for i in range(count):
            if self._stop_requested:
                break

            card = locator.nth(i)
            job = JobInfo()

            try:
                job.title = card.get_attribute("aria-label") or ""
            except Exception:
                job.title = ""

            # 链接（可能是相对路径；/zh/xxx-jobs 页面的链接是 /zh/job/xxx，需兼容）
            try:
                link_loc = card.locator("a[href*='/job/']").first
                if link_loc.count() > 0:
                    href = link_loc.get_attribute("href") or ""
                    # 排除非职位详情链接（如 /job/apply 等）
                    if "/job/" in href and "/job/apply" not in href:
                        if href.startswith("http"):
                            job.link = href
                        else:
                            base = "https://hk.jobsdb.com"
                            try:
                                from api.config import JOBSDB_BASE_URL
                                base = JOBSDB_BASE_URL.rstrip("/")
                            except Exception:
                                pass
                            job.link = base + (href if href.startswith("/") else "/" + href)
            except Exception:
                job.link = ""

            # 公司
            try:
                company_loc = card.locator("a[data-automation='jobCompany']").first
                if company_loc.count() > 0:
                    job.company = company_loc.inner_text().strip()
            except Exception:
                job.company = ""

            # 地点
            try:
                location_loc = card.locator("a[data-automation='jobLocation']").first
                if location_loc.count() > 0:
                    job.location = location_loc.inner_text().strip()
            except Exception:
                job.location = ""

            # 薪资（多选器 fallback）
            job.salary = "Not specified"
            for sel in SALARY_SELECTORS:
                try:
                    salary_loc = card.locator(sel).first
                    if salary_loc.count() > 0:
                        job.salary = salary_loc.inner_text().strip() or "Not specified"
                        break
                except Exception:
                    continue

            # 日期（多选器 fallback）
            for sel in DATE_SELECTORS:
                try:
                    date_loc = card.locator(sel).first
                    if date_loc.count() > 0:
                        text = date_loc.inner_text().strip()
                        if text:
                            if "Viewed" in text:
                                text = text.split("Viewed")[0].strip()
                            job.date = text
                            break
                except Exception:
                    continue

            jobs.append(
                {
                    "title": job.title,
                    "link": job.link,
                    "company": job.company,
                    "location": job.location,
                    "salary": job.salary,
                    "date": job.date,
                }
            )

        return jobs

    def _apply_single_job(self, context, job_link: str, job_title: str = "") -> tuple[bool, str]:  # type: ignore[no-untyped-def]
        detail_page = context.new_page()
        detail_page.set_default_timeout(25000)
        try:
            detail_page.goto(job_link, wait_until="domcontentloaded")
            # 列表页 ⇨ 职位详情页：稍等一会儿即可
            self._random_wait(1, 3)

            # 如果该职位已显示 "You applied on"，直接跳过（不再滚动）
            try:
                applied_banner = detail_page.get_by_text("You applied on", exact=False)
                if applied_banner.count() > 0:
                    self.log_message.emit("检测到该职位已投递（You applied on），跳过本次申请。")
                    return False, "已投递，跳过"
            except Exception:
                pass

            # 仅对未投递的职位做随机滚动，确保按钮懒加载出来
            for _ in range(3):
                self._random_scroll(detail_page)
                self._random_wait(0, 2)

            # 尝试多种 Apply 按钮 selector
            apply_selectors = [
                "a[data-automation='job-detail-apply']",
                "button[data-automation='job-detail-apply']",
                "button:has-text('Apply Now')",
                "a:has-text('Apply Now')",
            ]

            apply_btn = None

            # 先尝试基于语义的“Quick apply / Apply now”按钮
            role_candidates = [
                "Quick apply",
                "Quick Apply",
                "Apply now",
                "Apply Now",
            ]
            for name in role_candidates:
                btn = detail_page.get_by_role("button", name=name)
                if btn.count() > 0:
                    apply_btn = btn.first
                    break

            for sel in apply_selectors:
                if apply_btn is not None:
                    break
                loc = detail_page.locator(sel).first
                try:
                    loc.wait_for(state="visible", timeout=15000)
                except Exception:
                    continue
                if loc.count() > 0:
                    apply_btn = loc
                    break

            if apply_btn is None or apply_btn.count() <= 0:
                self._dump_debug_artifacts(detail_page, prefix="no_apply_button")
                return False, "未找到 Apply 按钮"

            apply_page = detail_page
            try:
                # 有些职位会在新窗口/新标签打开申请表单
                popup_timeout = 1500
                try:
                    from api.config import EXPECT_POPUP_TIMEOUT_MS
                    popup_timeout = EXPECT_POPUP_TIMEOUT_MS
                except Exception:
                    pass
                with detail_page.expect_popup(timeout=popup_timeout) as pop:
                    apply_btn.click(no_wait_after=True, force=True)
                apply_page = pop.value
            except Exception as e:
                # 多数职位是在当前标签内跳转，这里超时不代表点击失败
                # 如果已经在 apply 表单页，就直接进入填表逻辑，不再重复点击
                try:
                    current_url = detail_page.url
                except Exception:
                    current_url = ""
                if "/apply" in current_url:
                    self.log_message.emit(
                        "expect_popup 超时，但已检测到处于申请表单页面，直接开始填表。"
                    )
                    apply_page = detail_page
                else:
                    self.log_message.emit(
                        f"expect_popup 超时或失败（当前 url: {current_url}），尝试在当前页继续点击：{e}"
                    )
                    try:
                        apply_btn.click(timeout=1500, no_wait_after=True, force=True)
                    except Exception as e2:  # noqa: BLE001
                        # 即使这里报错，也有可能页面已经跳转到申请表单，因此不直接返回失败，改为记录并继续尝试填表
                        self.log_message.emit(f"点击 Apply 按钮出现异常，继续尝试填表：{e2}")
                        self._dump_debug_artifacts(detail_page, prefix="apply_click_timeout")


            self._random_wait(4, 8)

            apply_url = apply_page.url
            if not self._is_on_jobsdb_domain(apply_url):
                self.external_job_detected.emit((job_title or "").strip() or "（无标题）", job_link)
                self.log_message.emit(f"已记录外部投递：{job_title or '（无标题）'} → {job_link}\n[排查] 申请页 URL：{apply_url}")
                if self.show_browser:
                    ext_sleep = 30
                    try:
                        from api.config import EXTERNAL_SITE_SLEEP_SEC
                        ext_sleep = EXTERNAL_SITE_SLEEP_SEC
                    except Exception:
                        pass
                    self.log_message.emit(f"[调试] 浏览器可见，请查看地址栏 URL，{ext_sleep} 秒后自动关闭…")
                    time.sleep(ext_sleep)
                try:
                    apply_page.close()
                except Exception:
                    pass
                return False, "外部站点，已记录供手动投递"

            ok, msg = self._fill_application_form(apply_page, job_title, job_link)
            return ok, msg
        except Exception as e:  # noqa: BLE001
            return False, f"投递异常：{e}"
        finally:
            try:
                detail_page.close()
            except Exception:
                pass

    def _fill_application_form(self, page, job_title: str = "", job_link: str = "") -> tuple[bool, str]:  # type: ignore[no-untyped-def]
        try:
            # Step 1: 选择“不附加 Cover letter”
            try:
                # 先确保 Cover letter 区域已经渲染
                try:
                    section = page.get_by_text("Cover letter", exact=False)
                    if section.count() > 0:
                        section.first.scroll_into_view_if_needed(timeout=3000)
                        self._random_wait(0, 1)
                except Exception:
                    pass

                # 优先用语义 role 匹配（多种大小写/引号写法）
                patterns = [
                    "Don't include a cover letter",
                    "Don’t include a cover letter",
                    "don't include a cover letter",
                ]
                no_cover = None
                for name in patterns:
                    cand = page.get_by_role("radio", name=name)
                    if cand.count() > 0:
                        no_cover = cand.first
                        break

                # 如果还没找到，退回到通过文本 label 的方式
                if no_cover is None:
                    label_loc = page.locator("text=\"Don't include a cover letter\"").first
                    if label_loc.count() == 0:
                        label_loc = page.locator("text=\"Don’t include a cover letter\"").first
                    if label_loc.count() > 0:
                        # label 的 for/id 关联的 input
                        input_id = label_loc.get_attribute("for")
                        if input_id:
                            no_cover = page.locator(f"input#{input_id}").first

                if no_cover.count() > 0:
                    self.log_message.emit("选择：Don't include a cover letter")
                    no_cover.scroll_into_view_if_needed(timeout=3000)
                    no_cover.click()
                    self._random_wait(0, 1)
                else:
                    # 兼容旧的 data-testid 写法
                    legacy_no_cover = page.locator("input[data-testid='coverLetter-method-none']").first
                    if legacy_no_cover.count() > 0:
                        self.log_message.emit("选择：Don't include a cover letter（legacy selector）")
                        legacy_no_cover.scroll_into_view_if_needed(timeout=3000)
                        legacy_no_cover.click()
                        self._random_wait(0, 1)
            except Exception as e:  # noqa: BLE001
                self.log_message.emit(f"选择 Cover letter 选项时出错：{e}")

            # Step 2: 点击 Continue 进入问题页
            try:
                # 使用正则匹配名称中包含 Continue（处理箭头图标等情况）
                cont = page.get_by_role("button", name=re.compile("continue", re.IGNORECASE))
                if cont.count() == 0:
                    cont = page.locator("button[data-testid='continue-button'], [data-testid='continue-button']")
                if cont.count() > 0:
                    btn = cont.first
                    self.log_message.emit("点击 Continue 按钮")
                    btn.scroll_into_view_if_needed(timeout=3000)
                    btn.click()
                    self._random_wait(1, 2)
                else:
                    self.log_message.emit("未找到 Continue 按钮")
            except Exception as e:  # noqa: BLE001
                self.log_message.emit(f"点击 Continue 按钮时出错：{e}")

            if not self._is_on_jobsdb_domain(page.url):
                self.external_job_detected.emit((job_title or "").strip() or "（无标题）", job_link)
                self.log_message.emit(f"[排查] Continue 后申请页 URL：{page.url}")
                if self.show_browser:
                    ext_sleep = 30
                    try:
                        from api.config import EXTERNAL_SITE_SLEEP_SEC
                        ext_sleep = EXTERNAL_SITE_SLEEP_SEC
                    except Exception:
                        pass
                    self.log_message.emit(f"[调试] 浏览器可见，请查看地址栏，{ext_sleep} 秒后自动关闭…")
                    time.sleep(ext_sleep)
                try:
                    page.close()
                except Exception:
                    pass
                return False, "跳转到外站，已记录供手动投递"

            # 最多重试 3 轮：处理必填问题，未填的随机选择
            for _ in range(3):
                if self._stop_requested:
                    return False, "已停止"

                self._fill_all_unanswered_questions(page)
                self._handle_experience_questions(page)
                self._handle_salary_questions(page)
                self._handle_notice_questions(page)
                self._handle_language_fluency(page)

                errors = page.locator("[id*='question-'][id$='-message']")
                if errors.count() == 0:
                    break

                for i in range(errors.count()):
                    if self._stop_requested:
                        return False, "已停止"

                    err = errors.nth(i)
                    err_id = (err.get_attribute("id") or "").strip()
                    if not err_id.endswith("-message"):
                        continue
                    qid = err_id.replace("-message", "")
                    q = page.locator(f"#{qid}").first
                    if q.count() <= 0:
                        continue

                    q_text = ""
                    label = page.locator(f"label[for='{qid}']").first
                    if label.count() > 0:
                        try:
                            q_text = label.inner_text().strip()
                        except Exception:
                            q_text = ""

                    tag = ""
                    try:
                        tag = (q.evaluate("el => el.tagName") or "").lower()
                    except Exception:
                        tag = ""

                    if tag == "select":
                        self._fill_select(q, q_text)
                    elif tag == "textarea":
                        self._type_like_human(q, self._answer_for(q_text))
                    elif tag == "input":
                        itype = (q.get_attribute("type") or "").lower()
                        if itype == "radio":
                            self._fill_radio_group(page, q, q_text)
                        elif itype == "checkbox":
                            if "language" in q_text.lower() and "fluent" in q_text.lower():
                                self._handle_language_fluency(page)
                            else:
                                try:
                                    if not q.is_checked():
                                        q.click()
                                except Exception:
                                    pass
                        elif itype in ("text", "number"):
                            val = self._answer_for(q_text)
                            if itype == "number" and "experience" in q_text.lower():
                                val = str(self.experience_years)
                            self._fill_input(q, val)

                cont2 = page.locator("button[data-testid='continue-button'], [data-testid='continue-button']").first
                if cont2.count() > 0:
                    cont2.click()
                    self._random_wait(1, 3)

                if not self._is_on_jobsdb_domain(page.url):
                    self.external_job_detected.emit((job_title or "").strip() or "（无标题）", job_link)
                    self.log_message.emit(f"[排查] 填表后申请页 URL：{page.url}")
                    if self.show_browser:
                        ext_sleep = 30
                        try:
                            from api.config import EXTERNAL_SITE_SLEEP_SEC
                            ext_sleep = EXTERNAL_SITE_SLEEP_SEC
                        except Exception:
                            pass
                        self.log_message.emit(f"[调试] 浏览器可见，请查看地址栏，{ext_sleep} 秒后自动关闭…")
                        time.sleep(ext_sleep)
                    try:
                        page.close()
                    except Exception:
                        pass
                    return False, "跳转到外站，已记录供手动投递"

            # profile 更新页可能需要再点一次 continue
            try:
                if "apply/profile" in page.url or page.get_by_text("Update JobsDB Profile", exact=False).count() > 0:
                    self.log_message.emit("检测到 Update JobsDB Profile 页面，尝试直接 Continue")
                    for _ in range(2):
                        cont3 = page.locator("button[data-testid='continue-button'], [data-testid='continue-button']").first
                        if cont3.count() > 0:
                            cont3.scroll_into_view_if_needed(timeout=3000)
                            cont3.click()
                            self._random_wait(1, 2)
                        # 如果已经跳出 profile 页面就停止
                        if "apply/profile" not in page.url:
                            break
            except Exception:
                pass

            # Submit
            clicked = False

            # 1) 优先尝试语义：文本包含 Submit / Submit application
            try:
                role_names = [
                    "Submit application",
                    "Submit Application",
                    "Submit",
                ]
                for name in role_names:
                    btn = page.get_by_role("button", name=name)
                    if btn.count() > 0:
                        b = btn.first
                        b.scroll_into_view_if_needed(timeout=3000)
                        b.click()
                        clicked = True
                        break
            except Exception:
                clicked = False

            # 2) 退回原有 data-testid / type 选择器
            if not clicked:
                submit_selectors = [
                    "button[data-testid='review-submit-application']",
                    "button[data-testid='submit-application']",
                    "button[type='submit']",
                ]
                for sel in submit_selectors:
                    btn = page.locator(sel).first
                    if btn.count() > 0:
                        try:
                            btn.scroll_into_view_if_needed(timeout=3000)
                            btn.click()
                            clicked = True
                            break
                        except Exception:
                            continue

            # 3) 兜底：遍历所有 button，文本里含 submit/application 就点
            if not clicked:
                buttons = page.locator("button")
                for i in range(buttons.count()):
                    b = buttons.nth(i)
                    try:
                        txt = (b.inner_text() or "").strip().lower()
                        if "submit" in txt or "application" in txt:
                            b.scroll_into_view_if_needed(timeout=3000)
                            b.click()
                            clicked = True
                            break
                    except Exception:
                        continue

            if not clicked:
                return False, "未找到提交按钮"

            self._random_wait(2, 4)
            if not self._is_on_jobsdb_domain(page.url):
                self.external_job_detected.emit((job_title or "").strip() or "（无标题）", job_link)
                self.log_message.emit(f"[排查] 提交后申请页 URL：{page.url}")
                if self.show_browser:
                    self.log_message.emit("[调试] 浏览器可见，请查看地址栏，30 秒后自动关闭…")
                    time.sleep(30)
                try:
                    page.close()
                except Exception:
                    pass
                return False, "提交后跳转到外站，已记录供手动投递"

            return True, "已提交"
        except Exception as e:  # noqa: BLE001
            return False, f"表单异常：{e}"

    NOTICE_ANSWER = "NONE, I'M READY TO GO"

    def _answer_for(self, question_text: str) -> str:
        presets = {
            "How many years' experience do you have as an analyst programmer?": "No experience",
            "How many years' experience do you have in an application support function?": "No experience",
        }
        if question_text in presets:
            return presets[question_text]
        if self._is_salary_question(question_text or ""):
            n = str(self._expected_salary_value())
            return n + "000"
        if self._is_notice_question(question_text or ""):
            return self.NOTICE_ANSWER
        return "N/A"

    def _type_like_human(self, locator, text: str) -> None:  # type: ignore[no-untyped-def]
        try:
            locator.fill("")
            locator.type(text, delay=random.randint(50, 250))
        except Exception:
            try:
                locator.fill(text)
            except Exception:
                pass

    def _fill_input(self, locator, text: str) -> None:  # type: ignore[no-untyped-def]
        self._type_like_human(locator, text)

    def _is_salary_question(self, text: str) -> bool:
        t = (text or "").lower()
        return "salary" in t or "expected monthly" in t or "basic salary" in t

    def _expected_salary_value(self) -> int:
        """用户设置的期望月薪（K 为单位），如 16。"""
        m = re.search(r"(\d+)\s*k", self.expected_salary, re.I)
        n = m.group(1) if m else self.expected_salary.replace("K", "").replace("k", "").strip()
        return int(n) if n and n.isdigit() else 16

    def _parse_salary_from_option_label(self, label: str) -> int | None:
        """从选项文字解析出月薪数值（K 为单位），如 HK$16,000 -> 16；范围取下限。"""
        lab = (label or "").replace(",", "").replace(" ", "").lower()
        m = re.search(r"(\d+)\s*k", lab)
        if m:
            return int(m.group(1))
        m = re.search(r"(\d{2,})", lab)
        if m:
            num = int(m.group(1))
            if num >= 1000:
                return num // 1000
            return num
        return None

    def _match_salary_option(self, label: str) -> bool:
        """选项是否 >= 用户设置的最低月薪（绝不选低于最低的）。"""
        opt_val = self._parse_salary_from_option_label(label)
        if opt_val is None:
            return False
        return opt_val >= self._expected_salary_value()

    def _pick_best_salary_option(self, labels: list[str]) -> str | None:
        """在 >= 最低月薪的选项中选一个（优先选等于最低的，否则选最小且 >= 最低的）。"""
        min_k = self._expected_salary_value()
        candidates: list[tuple[int, str]] = []
        for lab in labels:
            k = self._parse_salary_from_option_label(lab)
            if k is not None and k >= min_k:
                candidates.append((k, lab))
        if not candidates:
            return None
        candidates.sort(key=lambda x: x[0])
        return candidates[0][1]

    def _is_notice_question(self, text: str) -> bool:
        t = (text or "").lower()
        return "notice" in t and "employer" in t

    def _match_notice_option(self, label: str) -> bool:
        """是否匹配「无需通知，随时到岗」类选项。"""
        lab = (label or "").lower()
        return "none" in lab and ("ready" in lab or "go" in lab)

    def _match_experience_option(self, label: str) -> bool:
        """选项是否匹配用户设置的经验年限。"""
        lab = (label or "").strip().lower()
        n = self.experience_years
        if n == 0:
            return "no experience" in lab or "0 year" in lab or "less than 1" in lab
        # 用 (?!\d) 避免 1 匹配到 "10 years"
        return re.search(rf"\b{n}(?!\d)\s*year", lab) is not None

    def _fill_select(self, locator, question_text: str) -> None:  # type: ignore[no-untyped-def]
        try:
            options = locator.locator("option")
            labels = options.all_text_contents()
            labels = [x.strip() for x in labels if x and x.strip()]
            if not labels:
                return

            target = None
            if "experience" in (question_text or "").lower():
                for lab in labels:
                    if self._match_experience_option(lab):
                        target = lab
                        break
            elif self._is_salary_question(question_text or ""):
                target = self._pick_best_salary_option(labels)
            elif self._is_notice_question(question_text or ""):
                for lab in labels:
                    if self._match_notice_option(lab):
                        target = lab
                        break
            if target is None and not self._is_salary_question(question_text or "") and not self._is_notice_question(question_text or ""):
                # 薪资、notice 题绝不随机；其他题可随机
                if len(labels) > 1:
                    target = labels[random.randint(1, len(labels) - 1)]
                else:
                    target = labels[0]
            if target is not None:
                locator.select_option(label=target)
        except Exception:
            return

    def _fill_radio_group(self, page, q_locator, question_text: str) -> None:  # type: ignore[no-untyped-def]
        try:
            name = (q_locator.get_attribute("name") or "").strip()
            if not name:
                return
            radios = page.locator(f"input[type='radio'][name='{name}']")
            if radios.count() <= 0:
                return

            picked = None
            if "experience" in (question_text or "").lower():
                for i in range(radios.count()):
                    r = radios.nth(i)
                    rid = (r.get_attribute("id") or "").strip()
                    if not rid:
                        continue
                    lab_elem = page.locator(f"label[for='{rid}']").first
                    if lab_elem.count() <= 0:
                        continue
                    t = (lab_elem.inner_text() or "").strip()
                    if self._match_experience_option(t):
                        picked = r
                        break
            elif self._is_salary_question(question_text or ""):
                min_k = self._expected_salary_value()
                candidates: list[tuple[int, object]] = []
                for i in range(radios.count()):
                    r = radios.nth(i)
                    rid = (r.get_attribute("id") or "").strip()
                    if not rid:
                        continue
                    lab_elem = page.locator(f"label[for='{rid}']").first
                    if lab_elem.count() <= 0:
                        continue
                    t = (lab_elem.inner_text() or "").strip()
                    k = self._parse_salary_from_option_label(t)
                    if k is not None and k >= min_k:
                        candidates.append((k, r))
                if candidates:
                    candidates.sort(key=lambda x: x[0])
                    picked = candidates[0][1]
            elif self._is_notice_question(question_text or ""):
                for i in range(radios.count()):
                    r = radios.nth(i)
                    rid = (r.get_attribute("id") or "").strip()
                    if not rid:
                        continue
                    lab_elem = page.locator(f"label[for='{rid}']").first
                    if lab_elem.count() <= 0:
                        continue
                    t = (lab_elem.inner_text() or "").strip()
                    if self._match_notice_option(t):
                        picked = r
                        break

            if picked is None and not self._is_salary_question(question_text or "") and not self._is_notice_question(question_text or ""):
                picked = radios.nth(random.randint(0, radios.count() - 1))

            if picked is not None:
                picked.click()
        except Exception:
            return

    def _fill_all_unanswered_questions(self, page) -> None:  # type: ignore[no-untyped-def]
        """ANSWER EMPLOYER QUESTIONS：扫描所有题目，未填的随机选择答案。"""
        try:
            # Select 下拉框（兼容 question- / data-testid / 普通 select）
            selects = page.locator(
                "select[id*='question-'], select[data-testid*='question'], "
                "select[name*='question'], form select"
            )
            for i in range(min(selects.count(), 80)):
                if self._stop_requested:
                    return
                try:
                    sel = selects.nth(i)
                    if sel.count() <= 0:
                        continue
                    val = sel.get_attribute("value") or ""
                    if not val or val.strip() == "":
                        self._fill_select(sel, "")
                        self._random_wait(0, 1)
                except Exception:
                    pass

            # Radio 单选项
            radios_by_name: set[str] = set()
            rads = page.locator("input[type='radio'][id*='question-'], input[type='radio'][name*='question']")
            for i in range(min(rads.count(), 200)):
                if self._stop_requested:
                    return
                try:
                    r = rads.nth(i)
                    name = (r.get_attribute("name") or "").strip()
                    if not name or name in radios_by_name:
                        continue
                    radios_by_name.add(name)
                    group = page.locator(f"input[type='radio'][name='{name}']")
                    if group.count() <= 0:
                        continue
                    checked = any(
                        group.nth(j).is_checked() for j in range(group.count())
                    )
                    if not checked:
                        self._fill_radio_group(page, r, "")
                        self._random_wait(0, 1)
                except Exception:
                    pass

            # Checkbox  checkbox（语言类由 _handle_language_fluency 处理，这里处理其他的）
            cbs = page.locator("input[type='checkbox'][id*='question-']")
            for i in range(min(cbs.count(), 100)):
                if self._stop_requested:
                    return
                try:
                    cb = cbs.nth(i)
                    if cb.count() <= 0:
                        continue
                    cid = (cb.get_attribute("id") or "").strip()
                    if not cid:
                        continue
                    lab = page.locator(f"label[for='{cid}']").first
                    lab_text = ""
                    if lab.count() > 0:
                        lab_text = (lab.inner_text() or "").strip().lower()
                    if lab_text in ("english", "mandarin", "cantonese"):
                        continue  # 交给 _handle_language_fluency
                    if not cb.is_checked():
                        cb.click()
                        self._random_wait(0, 1)
                except Exception:
                    pass

            # Textarea / 文本
            textareas = page.locator("textarea[id*='question-']")
            for i in range(min(textareas.count(), 50)):
                if self._stop_requested:
                    return
                try:
                    ta = textareas.nth(i)
                    if ta.count() <= 0:
                        continue
                    content = ta.input_value() or ""
                    if not content.strip():
                        self._type_like_human(ta, "N/A")
                        self._random_wait(0, 1)
                except Exception:
                    pass

            # input text / number
            txts = page.locator("input[type='text'][id*='question-'], input[type='number'][id*='question-']")
            for i in range(min(txts.count(), 50)):
                if self._stop_requested:
                    return
                try:
                    inp = txts.nth(i)
                    if inp.count() <= 0:
                        continue
                    iid = (inp.get_attribute("id") or "").strip()
                    val = inp.input_value() or ""
                    if val.strip():
                        continue
                    lab = page.locator(f"label[for='{iid}']").first
                    q_text = (lab.inner_text() or "").strip() if lab.count() > 0 else ""
                    fill_val = self._answer_for(q_text)
                    if "experience" in q_text.lower() and "year" in q_text.lower():
                        fill_val = str(self.experience_years)
                    self._fill_input(inp, fill_val)
                    self._random_wait(0, 1)
                except Exception:
                    pass
        except Exception:
            pass

    def _handle_salary_questions(self, page) -> None:  # type: ignore[no-untyped-def]
        """主动扫描并填写期望月薪类问题。"""
        try:
            selects = page.locator("select")
            for i in range(min(selects.count(), 50)):
                sel = selects.nth(i)
                sid = (sel.get_attribute("id") or "").strip()
                if not sid:
                    continue
                label = page.locator(f"label[for='{sid}']").first
                if label.count() <= 0:
                    continue
                t = (label.inner_text() or "").strip().lower()
                if self._is_salary_question(t):
                    self._fill_select(sel, t)
                    self._random_wait(0, 1)
            nums = page.locator("input[type='number'], input[type='text']")
            for i in range(min(nums.count(), 50)):
                n = nums.nth(i)
                nid = (n.get_attribute("id") or "").strip()
                if not nid:
                    continue
                label = page.locator(f"label[for='{nid}']").first
                if label.count() <= 0:
                    continue
                t = (label.inner_text() or "").strip()
                if self._is_salary_question(t):
                    val = self._answer_for(t)
                    if val != "N/A":
                        self._fill_input(n, val)
                        self._random_wait(0, 1)
        except Exception:
            pass

    def _handle_notice_questions(self, page) -> None:  # type: ignore[no-untyped-def]
        """主动扫描并填写 notice 类问题：NONE, I'M READY TO GO。"""
        try:
            selects = page.locator("select")
            for i in range(min(selects.count(), 50)):
                sel = selects.nth(i)
                sid = (sel.get_attribute("id") or "").strip()
                if not sid:
                    continue
                label = page.locator(f"label[for='{sid}']").first
                if label.count() <= 0:
                    continue
                t = (label.inner_text() or "").strip()
                if self._is_notice_question(t):
                    self._fill_select(sel, t)
                    self._random_wait(0, 1)
        except Exception:
            pass

    def _handle_experience_questions(self, page) -> None:  # type: ignore[no-untyped-def]
        # 主动扫描：select / radio / number input（experience 相关）
        try:
            selects = page.locator("select")
            for i in range(min(selects.count(), 50)):
                sel = selects.nth(i)
                sid = (sel.get_attribute("id") or "").strip()
                if not sid:
                    continue
                label = page.locator(f"label[for='{sid}']").first
                if label.count() <= 0:
                    continue
                t = (label.inner_text() or "").strip().lower()
                if "experience" in t:
                    self._fill_select(sel, t)
                    self._random_wait(1, 2)
        except Exception:
            pass

        try:
            nums = page.locator("input[type='number']")
            for i in range(min(nums.count(), 50)):
                n = nums.nth(i)
                nid = (n.get_attribute("id") or "").strip()
                if not nid:
                    continue
                label = page.locator(f"label[for='{nid}']").first
                if label.count() <= 0:
                    continue
                t = (label.inner_text() or "").strip().lower()
                if "experience" in t:
                    self._fill_input(n, str(self.experience_years))
                    self._random_wait(1, 2)
        except Exception:
            pass

    def _handle_language_fluency(self, page) -> None:  # type: ignore[no-untyped-def]
        # 语言熟练度：勾选 English/Mandarin/Cantonese
        try:
            checkboxes = page.locator("input[type='checkbox']")
            for i in range(min(checkboxes.count(), 200)):
                cb = checkboxes.nth(i)
                cid = (cb.get_attribute("id") or "").strip()
                if not cid:
                    continue
                lab = page.locator(f"label[for='{cid}']").first
                if lab.count() <= 0:
                    continue
                text = (lab.inner_text() or "").strip()
                if text.lower() in ("english", "mandarin", "cantonese"):
                    try:
                        if not cb.is_checked():
                            cb.click()
                            self._random_wait(1, 2)
                    except Exception:
                        continue
        except Exception:
            return

    def _goto_next_page(self, list_page, next_page_index: int) -> bool:  # type: ignore[no-untyped-def]
        # 优先尝试点击“下一页”按钮；失败则尝试 URL 增加 page= 参数
        try:
            candidates = [
                "a[rel='next']",
                "a[aria-label*='Next']",
                "button[aria-label*='Next']",
                "[data-automation='pagination-next']",
            ]
            for sel in candidates:
                loc = list_page.locator(sel).first
                if loc.count() > 0:
                    try:
                        loc.click()
                        self._random_wait(1, 2)
                        try:
                            self.log_message.emit(f"[排查] 翻页至第{next_page_index}页（点击按钮），当前 URL：{list_page.url}")
                        except Exception:
                            pass
                        return True
                    except Exception:
                        continue
        except Exception:
            pass

        try:
            u = urlparse(list_page.url)
            q = parse_qs(u.query)
            q["page"] = [str(next_page_index)]
            new_query = urlencode(q, doseq=True)
            new_url = urlunparse((u.scheme, u.netloc, u.path, u.params, new_query, u.fragment))
            list_page.goto(new_url, wait_until="load")
            self._random_wait(1, 2)
            try:
                self.log_message.emit(f"[排查] 翻页至第{next_page_index}页（URL 切换），当前 URL：{list_page.url}")
            except Exception:
                pass
            return True
        except Exception as e:
            self.log_message.emit(f"[排查] 翻页失败：{e}")
            return False


class ClassificationFetcher(QThread):
    """后台抓取 JobsDB 职位分类（Any classification）。"""
    classifications_loaded = Signal(list)  # List[Dict[str, str]] with name, slug
    log_message = Signal(str)

    def __init__(self, cache_file: str, parent=None) -> None:
        super().__init__(parent)
        self.cache_file = Path(cache_file)

    def run(self) -> None:
        try:
            from playwright.sync_api import sync_playwright  # type: ignore
        except ImportError:
            self.classifications_loaded.emit(DEFAULT_CLASSIFICATIONS)
            return

        classifications: List[Dict[str, str]] = []
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
                    ),
                    locale="en-US",
                )
                page = context.new_page()
                page.set_default_timeout(15000)
                page.goto("https://hk.jobsdb.com/jobs?daterange=3", wait_until="domcontentloaded")
                time.sleep(2)

                # 策略1：找所有 jobs-in- 链接
                links = page.locator("a[href*='/jobs-in-']")
                seen_slugs: set[str] = set()
                for i in range(min(links.count(), 100)):
                    try:
                        a = links.nth(i)
                        href = a.get_attribute("href") or ""
                        text = (a.inner_text() or "").strip()
                        if not href or not text or "jobs-in-" not in href:
                            continue
                        m = re.search(r"/jobs-in-([a-z0-9-]+)", href, re.I)
                        if m:
                            slug = m.group(1).lower()
                            if slug not in seen_slugs and len(slug) > 1:
                                seen_slugs.add(slug)
                                name = text.split("\n")[0].strip()[:80]
                                if name:
                                    classifications.append({"name": name, "slug": slug})
                    except Exception:
                        continue

                browser.close()
        except Exception as e:  # noqa: BLE001
            self.log_message.emit(f"抓取分类时出错：{e}，使用预置列表。")

        if not classifications:
            classifications = DEFAULT_CLASSIFICATIONS.copy()
            self.log_message.emit("使用预置分类列表。")
        else:
            self.log_message.emit(f"已抓取 {len(classifications)} 个职位分类。")

        # 保存缓存
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            data: Dict[str, Any] = {
                "_fetched_at": int(time.time()),
                "items": classifications,
            }
            self.cache_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

        self.classifications_loaded.emit(classifications)

