"""
JobsDB 邮箱验证码登录流程：保持 Playwright 会话在两次请求之间
"""
import re
import time
from pathlib import Path

from .config import ACCOUNTS_BASE
from .operation_log import op_info, op_debug, op_error
from .app_logger import log_info, log_error

# 存储每个用户的登录会话： {user_id: {"playwright", "browser", "context", "page"}}
_login_sessions: dict[int, dict] = {}
_dflt_excluded = (
    "MOMAX, AIA, Prudential, Manulife, AXA, FTLife, FWD, BOC Life, HSBC Life, "
    "Hang Seng Insurance, Standard Chartered, family office, i-CABLE"
)


def _excluded_list() -> list[str]:
    parts = []
    for p in _dflt_excluded.split(","):
        p = p.strip()
        if p:
            parts.append(p)
    return parts


def _save_page_debug(user_id: int, page, suffix: str) -> None:
    """失败时保存页面 HTML 便于排查"""
    try:
        debug_dir = ACCOUNTS_BASE / str(user_id)
        debug_dir.mkdir(parents=True, exist_ok=True)
        f = debug_dir / f"jobsdb_login_{suffix}.html"
        html = page.content() if page else ""
        f.write_text(html[:50000], encoding="utf-8")  # 限制 50KB
        log_info("jobsdb_login 已保存页面快照", path=str(f), user_id=user_id)
    except Exception as ex:
        log_error("jobsdb_login 保存页面快照失败", err=str(ex), user_id=user_id)


def start_login(user_id: int, email: str, state_path: Path) -> tuple[bool, str]:
    """开始 JobsDB 登录：打开页面，输入邮箱，请求验证码。返回 (success, message)"""
    from playwright.sync_api import sync_playwright

    try:
        from api.config import JOBSDB_HEADED
        use_headed = JOBSDB_HEADED
    except Exception:
        use_headed = False

    op_info(user_id, "jobsdb_login_start", f"email={email} headed={use_headed}", source="backend")
    _close_session(user_id)

    try:
        from api.config import JOBSDB_PROXY
        proxy = JOBSDB_PROXY
    except Exception:
        proxy = None

    try:
        p = sync_playwright().start()
        launch_opts = {"headless": not use_headed, "args": ["--disable-blink-features=AutomationControlled"]}
        if proxy:
            launch_opts["proxy"] = proxy
        browser = p.chromium.launch(**launch_opts)
        context = browser.new_context(
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
        page = context.new_page()
        # 代理下连接较慢，超时调大；wait_until=domcontentloaded 比 load 更快
        page.set_default_timeout(60000)

        op_debug(user_id, "jobsdb_login_page_goto", "打开登录页", source="job")
        page.goto(
            "https://hk.jobsdb.com/zh/oauth/login?locale=hk&language=zh&realm=Username-Password-Authentication",
            wait_until="domcontentloaded",
        )
        time.sleep(4)
        url_after = page.url or ""
        op_debug(user_id, "jobsdb_login_page_loaded", f"url={url_after[:80]}", source="job")

        # 输入邮箱（SEEK 登录页为 React SPA，fill() 可能不触发 onChange，用 press_sequential_keys 模拟真实输入）
        def _do_fill(loc):
            try:
                loc.click()  # 先聚焦
                time.sleep(0.2)
                loc.press_sequentially(email, delay=30)  # 模拟逐字输入，触发 React 事件
                time.sleep(0.3)
                return True
            except Exception:
                try:
                    loc.fill(email)
                    return True
                except Exception:
                    return False

        filled = False
        # 1. 优先用 label（SEEK 页有 "Email address"）
        for lbl in ["Email address", "Email", "email", "電子郵件", "电邮"]:
            try:
                inp = page.get_by_label(lbl)
                if inp.count() > 0:
                    if _do_fill(inp.first):
                        filled = True
                        op_debug(user_id, "jobsdb_login_email_filled", f"by_label={lbl}", source="job")
                        break
            except Exception:
                pass
        # 2. 常规选择器
        if not filled:
            email_input = page.locator("input[type='email'], input[name*='email'], input[placeholder*='email' i], input[autocomplete='email']")
            if email_input.count() > 0:
                # 取可见的（避免填到隐藏的重复元素）
                for i in range(min(email_input.count(), 5)):
                    try:
                        el = email_input.nth(i)
                        if el.is_visible():
                            if _do_fill(el):
                                filled = True
                                op_debug(user_id, "jobsdb_login_email_filled", f"input nth={i}", source="job")
                            break
                    except Exception:
                        continue
        # 3. fallback: input[type=text] 且 name 含 email
        if not filled:
            for i in range(page.locator("input[type='text']").count()):
                try:
                    inp = page.locator("input[type='text']").nth(i)
                    if "email" in (inp.get_attribute("name") or "").lower() and inp.is_visible():
                        if _do_fill(inp):
                            filled = True
                            op_debug(user_id, "jobsdb_login_email_filled", f"fallback idx={i}", source="job")
                        break
                except Exception:
                    continue

        if not filled:
            _save_page_debug(user_id, page, "no_email_input")
            op_error(user_id, "jobsdb_login_fail", "未找到或无法填充邮箱输入框，已保存页面快照", source="job")
            return False, "未找到或无法填充邮箱输入框，JobsDB 页面结构可能已更改"

        time.sleep(0.8)

        # 点击发送验证码按钮
        btn = page.get_by_role("button", name=re.compile("email me a sign in code", re.I))
        if btn.count() == 0:
            btn = page.get_by_role("button", name=re.compile("sign in code|send code|发送.*代码|发送.*验证码", re.I))
        if btn.count() == 0:
            btn = page.locator("button[type='submit']")

        if btn.count() > 0:
            op_debug(user_id, "jobsdb_login_click_send_code", "找到并点击发送验证码按钮", source="job")
            btn.first.click()
            time.sleep(4)
            op_info(user_id, "jobsdb_login_send_code_clicked", "已点击发送验证码，等待邮箱接收", source="job")
        else:
            _save_page_debug(user_id, page, "no_send_button")
            op_error(user_id, "jobsdb_login_fail", "未找到发送验证码按钮，已保存页面快照", source="job")
            return False, "未找到“Email me a sign in code”按钮，JobsDB 页面结构可能已更改"

        _login_sessions[user_id] = {
            "playwright": p,
            "browser": browser,
            "context": context,
            "page": page,
            "email": email,
        }
        return True, "验证码已发送，请查收邮箱后输入（若未收到请查看垃圾邮件，或稍等 2–5 分钟）"
    except Exception as e:
        op_error(user_id, "jobsdb_login_exception", str(e), source="job")
        return False, str(e)


def verify_login(user_id: int, code: str, state_path: Path) -> tuple[bool, str]:
    """输入验证码完成登录，保存 storage_state"""
    from .storage import append_log
    op_info(user_id, "jobsdb_verify_start", f"code_len={len(code or '')}", source="backend")

    session = _login_sessions.get(user_id)
    if not session:
        append_log(user_id, "[排查] 验证失败：登录会话已过期")
        return False, "登录会话已过期，请重新发起登录"

    try:
        page = session["page"]
        context = session["context"]

        # 输入验证码：页面是多个小输入框（6 位或 3-3 分组）
        digits = re.sub(r"\D", "", code or "")
        if not digits:
            return False, "验证码为空"

        # 优先匹配数字输入框：type=tel / inputmode=numeric / aria-label 包含 digit
        boxes = page.locator(
            "input[type='tel'], "
            "input[inputmode='numeric'], "
            "input[aria-label*='digit' i]"
        )
        count = boxes.count()
        if count == 0:
            # 退回到所有可见 input
            boxes = page.locator("input")
            count = boxes.count()

        if count <= 1:
            # 只有一个输入框时，直接填完整验证码
            try:
                boxes.first.fill(digits)
            except Exception:
                pass
        else:
            # 多个小框：逐个填入
            for idx, ch in enumerate(digits):
                if idx >= count:
                    break
                try:
                    box = boxes.nth(idx)
                    if box.is_visible():
                        box.fill(ch)
                except Exception:
                    continue
        time.sleep(1)

        # 提交：按钮文本为 “Sign in”
        submit = page.get_by_role("button", name=re.compile("sign in|verify|submit|confirm|确认|验证", re.I))
        if submit.count() == 0:
            submit = page.locator("button[type='submit'], button:has-text('Sign in')")
        if submit.count() > 0:
            try:
                submit.first.click()
            except Exception:
                pass

        # 等待跳转回 JobsDB：最多 15 秒轮询
        for i in range(15):
            try:
                url = page.url
            except Exception:
                url = ""
            if url and "jobsdb.com" in url and "login" not in url.lower():
                time.sleep(2)  # 等待 post-redirect 的 cookie / JS 完成
                state_path.parent.mkdir(parents=True, exist_ok=True)
                context.storage_state(path=str(state_path))
                email = session.get("email", "")
                _close_session(user_id)
                append_log(user_id, f"[排查] JobsDB 登录成功，已保存 session，跳转 URL={url[:80]}...")
                return True, email or "登录成功"
            time.sleep(1)

        try:
            final_url = page.url or ""
            append_log(user_id, f"[排查] 验证失败：15 秒内未跳回 JobsDB，当前 URL={final_url[:100]}...")
        except Exception:
            pass
        return False, "验证码可能错误或已过期，请重试"
    except Exception as e:
        append_log(user_id, f"[排查] 验证异常：{e}")
        return False, str(e)
    finally:
        pass  # _close_session 在成功时已调用


def _close_session(user_id: int) -> None:
    session = _login_sessions.pop(user_id, None)
    if session:
        try:
            session.get("browser") and session["browser"].close()
        except Exception:
            pass
        try:
            session.get("playwright") and session["playwright"].stop()
        except Exception:
            pass
