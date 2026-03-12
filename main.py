import json
import os
import re
import sys
from datetime import datetime, timedelta

# 打包为 exe 时使用内嵌的 Chromium，必须在 import playwright 之前设置
if getattr(sys, "frozen", False):
    _base = sys._MEIPASS
    _browsers_path = os.path.join(_base, "playwright_browsers")
    if os.path.isdir(_browsers_path):
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = _browsers_path
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QStandardItemModel, QStandardItem
from PySide6.QtWidgets import (
    QFrame,
    QApplication,
    QMainWindow,
    QVBoxLayout,
    QWidget,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QTableView,
    QPlainTextEdit,
    QLineEdit,
    QFormLayout,
    QGroupBox,
    QSpinBox,
    QCheckBox,
    QComboBox,
    QMessageBox,
    QTabWidget,
    QScrollArea,
)

from jobsdb_worker import JobsdbWorker, ClassificationFetcher


PROJECT_ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
ACCOUNTS_DIR = PROJECT_ROOT / "accounts"
STATE_FILE = ACCOUNTS_DIR / "current_state.json"
CURRENT_ACCOUNT_FILE = ACCOUNTS_DIR / "current_account.txt"
CLASSIFICATIONS_CACHE = ACCOUNTS_DIR / "classifications.json"
CACHE_EXPIRE_DAYS = 7

EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")


def _get_account_id() -> str:
    """用于统计/外部投递的账号标识：优先用邮箱，无则用 default。"""
    email = _get_current_account_email()
    return email.strip() if email else "default"


def _get_current_account_email() -> str:
    """读取当前已登录账号的邮箱，用于统计和展示。"""
    if not CURRENT_ACCOUNT_FILE.exists():
        return ""
    try:
        return CURRENT_ACCOUNT_FILE.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def _save_current_account_email(email: str) -> None:
    ACCOUNTS_DIR.mkdir(parents=True, exist_ok=True)
    CURRENT_ACCOUNT_FILE.write_text((email or "").strip(), encoding="utf-8")


def _extract_email_from_context(context) -> str | None:
    """从已登录的浏览器 context 中尝试提取邮箱。"""
    try:
        pages = context.pages
        if not pages:
            return None
        page = pages[0]
        result = page.evaluate(
            """() => {
                const text = document.body ? (document.body.innerText || '') : '';
                const m = text.match(/[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\\.[a-zA-Z0-9-.]+/);
                return m ? m[0] : null;
            }"""
        )
        if result and isinstance(result, str) and "@" in result:
            return result
        return None
    except Exception:
        return None


def _extract_email_from_state_file() -> str | None:
    """从 storage state JSON 中尝试解析邮箱。"""
    if not STATE_FILE.exists():
        return None
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        s = json.dumps(data)
        m = EMAIL_PATTERN.search(s)
        if m:
            return m.group(0)
    except Exception:
        pass
    return None


def _sanitize_account_id(raw: str) -> str:
    """账号标识转安全文件名。"""
    s = re.sub(r'[<>:"/\\|?*]', "_", (raw or "").strip())
    return s or "default"


def _stats_file_for(account_id: str) -> Path:
    return ACCOUNTS_DIR / f"apply_stats_{_sanitize_account_id(account_id)}.json"


def _external_jobs_file(account_id: str) -> Path:
    return ACCOUNTS_DIR / f"external_jobs_{_sanitize_account_id(account_id)}.txt"


def _load_external_jobs(account_id: str) -> list[tuple[str, str]]:
    p = _external_jobs_file(account_id)
    if not p.exists():
        return []
    out: list[tuple[str, str]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if "\t" in line:
            t, u = line.split("\t", 1)
            if t and u:
                out.append((t.strip(), u.strip()))
    return out


def _append_external_job(account_id: str, title: str, url: str) -> None:
    if not title and not url:
        return
    ACCOUNTS_DIR.mkdir(parents=True, exist_ok=True)
    p = _external_jobs_file(account_id)
    with p.open("a", encoding="utf-8") as f:
        f.write(f"{title}\t{url}\n")


def _load_stats(account_id: str) -> dict[str, int]:
    p = _stats_file_for(account_id)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return {k: int(v) for k, v in data.items() if k != "_"}
    except Exception:
        return {}


def _save_stats(account_id: str, data: dict[str, int]) -> None:
    if not account_id or not account_id.strip():
        return
    ACCOUNTS_DIR.mkdir(parents=True, exist_ok=True)
    p = _stats_file_for(account_id)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _increment_today(account_id: str) -> None:
    if not account_id or not account_id.strip():
        return
    data = _load_stats(account_id)
    today = datetime.now().strftime("%Y-%m-%d")
    data[today] = data.get(today, 0) + 1
    _save_stats(account_id, data)


def _stats_summary(account_id: str) -> tuple[int, int, int]:
    data = _load_stats(account_id)
    today_str = datetime.now().strftime("%Y-%m-%d")
    today_count = data.get(today_str, 0)

    def sum_days(n: int) -> int:
        total = 0
        for i in range(n):
            d = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            total += data.get(d, 0)
        return total

    return today_count, sum_days(7), sum_days(30)


def _load_classifications_from_cache() -> list[dict[str, str]]:
    if not CLASSIFICATIONS_CACHE.exists():
        return []
    try:
        data = json.loads(CLASSIFICATIONS_CACHE.read_text(encoding="utf-8"))
        items = data.get("items", [])
        fetched_at = data.get("_fetched_at", 0)
        age_days = (datetime.now().timestamp() - fetched_at) / 86400 if fetched_at else 999
        if age_days <= CACHE_EXPIRE_DAYS and items:
            return items
    except Exception:
        pass
    return []


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("JobsDB 自动投递助手 (PySide6)")
        self.resize(1100, 700)

        self.playwright = None
        self.browser = None
        self.context = None

        self.worker: Optional[JobsdbWorker] = None
        self._classification_fetcher: Optional[ClassificationFetcher] = None
        self._row_index: dict[tuple[int, int], int] = {}

        self._build_ui()
        self._apply_style()
        self._update_account_label()
        self._update_stats_display()
        self._update_external_jobs_display()
        self._on_mode_changed()
        self._start_classification_fetcher()
        if STATE_FILE.exists() and not _get_current_account_email():
            email = _extract_email_from_state_file()
            if email:
                _save_current_account_email(email)
                self._update_account_label()
                self._update_stats_display()

    # ---------------- UI 构建 ---------------- #
    def _build_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(16)

        # 顶部控制区
        controls_layout = QHBoxLayout()

        self.btn_login = QPushButton("首次登录 / 重新登录当前账号")
        self.btn_login_done = QPushButton("我已经在浏览器里登录完成")
        self.btn_switch_account = QPushButton("切换账号")
        self.btn_start = QPushButton("开始自动投递")
        self.btn_stop = QPushButton("停止")
        self.btn_pause = QPushButton("暂停")
        self.btn_resume = QPushButton("恢复")
        self.btn_stop.setEnabled(False)
        self.btn_pause.setEnabled(False)
        self.btn_resume.setEnabled(False)

        controls_layout.addWidget(self.btn_login)
        controls_layout.addWidget(self.btn_login_done)
        controls_layout.addWidget(self.btn_switch_account)
        controls_layout.addWidget(self.btn_start)
        controls_layout.addWidget(self.btn_stop)
        controls_layout.addWidget(self.btn_pause)
        controls_layout.addWidget(self.btn_resume)

        self.lbl_account = QLabel()
        self.lbl_account.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        controls_layout.addWidget(self.lbl_account, stretch=1)

        main_layout.addLayout(controls_layout)

        # 多页签切换
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)

        # 第一页：统计配置
        page1 = QWidget()
        page1_layout = QVBoxLayout(page1)
        page1_layout.setContentsMargins(0, 8, 0, 0)
        stats_group = QGroupBox("投递统计")
        stats_layout = QVBoxLayout(stats_group)
        self.lbl_account_email = QLabel("当前账号：未登录")
        self.lbl_account_email.setStyleSheet("color: #424245; font-size: 13px;")
        stats_layout.addWidget(self.lbl_account_email)
        stats_row = QHBoxLayout()
        self.lbl_stats = QLabel("今日: 0  近7天: 0  近30天: 0")
        self.lbl_stats.setStyleSheet("font-size: 15px; font-weight: 600; letter-spacing: 0.02em; color: #1d1d1f;")
        stats_row.addWidget(self.lbl_stats)
        self.btn_view_all_stats = QPushButton("查看所有账号统计")
        stats_row.addWidget(self.btn_view_all_stats)
        stats_row.addStretch()
        stats_layout.addLayout(stats_row)
        page1_layout.addWidget(stats_group)

        # 设置区
        settings_group = QGroupBox("投递设置")
        settings_layout = QFormLayout(settings_group)

        self.combo_mode = QComboBox()
        self.combo_mode.addItems(["推荐岗位模式", "职位关键词模式", "职位类别模式"])
        self.combo_mode.currentIndexChanged.connect(self._on_mode_changed)
        settings_layout.addRow("投递模式", self.combo_mode)

        self.txt_mode2_keyword = QLineEdit()
        self.txt_mode2_keyword.setPlaceholderText("例如：shopify, admin, digital marketing")
        settings_layout.addRow("职位关键词", self.txt_mode2_keyword)

        mode3_row = QHBoxLayout()
        self.combo_mode3_category = QComboBox()
        self.combo_mode3_category.setMinimumWidth(280)
        mode3_row.addWidget(self.combo_mode3_category)
        self.btn_refresh_classifications = QPushButton("刷新分类")
        mode3_row.addWidget(self.btn_refresh_classifications)
        mode3_row.addStretch()
        settings_layout.addRow("职位类别", mode3_row)

        self.txt_excluded_companies = QPlainTextEdit()
        self.txt_excluded_companies.setPlaceholderText(
            "输入需要跳过的公司关键字（每行一个，或用逗号分隔）。\n"
            "匹配规则：公司名包含该关键字（不区分大小写）则跳过。"
        )
        self.txt_excluded_companies.setFixedHeight(80)
        self.txt_excluded_companies.setPlainText(
            "MOMAX, AIA, Prudential, Manulife, AXA, FTLife, FWD, BOC Life, HSBC Life,\n"
            "Hang Seng Insurance, Standard Chartered, family office, i-CABLE Communications Limited"
        )

        self.spin_max_pages = QSpinBox()
        self.spin_max_pages.setRange(1, 200)
        self.spin_max_pages.setValue(10)
        self.spin_max_pages.setToolTip("最多处理多少页（防止无限翻页）。")

        self.chk_show_browser = QCheckBox("显示浏览器（调试更直观）")
        self.chk_show_browser.setChecked(True)

        self.spin_slowmo = QSpinBox()
        self.spin_slowmo.setRange(0, 2000)
        self.spin_slowmo.setValue(150)
        self.spin_slowmo.setToolTip("每一步操作的慢动作延迟（毫秒），用于观察流程。设为 0 表示不慢放。")

        self.combo_human_level = QComboBox()
        self.combo_human_level.addItems(["低（速度优先）", "中（推荐）", "高（更像真人）"])  # index: 0/1/2
        self.combo_human_level.setCurrentIndex(1)

        self.combo_experience_years = QComboBox()
        self.combo_experience_years.addItems(["0 年（无经验）", "1 年", "2 年", "3 年", "4 年", "5 年"])
        self.combo_experience_years.setCurrentIndex(2)  # 默认 3 年
        self.combo_experience_years.setToolTip("回答「有多少年经验」类问题时使用的年限。")

        self.combo_expected_salary = QComboBox()
        self.combo_expected_salary.addItems(
            ["16K", "17K", "18K", "19K", "20K", "22K", "25K", "28K", "30K"]
        )
        self.combo_expected_salary.setCurrentIndex(0)  # 默认 16K
        self.combo_expected_salary.setToolTip(
            "回答「What's your expected monthly basic salary?」时选择的薪资。"
        )

        settings_layout.addRow("经验年限", self.combo_experience_years)
        settings_layout.addRow("期望月薪", self.combo_expected_salary)
        settings_layout.addRow("排除公司（关键字）", self.txt_excluded_companies)
        settings_layout.addRow("最大页数", self.spin_max_pages)
        settings_layout.addRow("可视化调试", self.chk_show_browser)
        settings_layout.addRow("慢动作（ms）", self.spin_slowmo)
        settings_layout.addRow("人类化等级", self.combo_human_level)

        page1_layout.addWidget(settings_group)
        scroll1 = QScrollArea()
        scroll1.setWidget(page1)
        scroll1.setWidgetResizable(True)
        scroll1.setFrameShape(QFrame.Shape.NoFrame)
        scroll1.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self.tabs.addTab(scroll1, "统计配置")

        # 第二页：职位列表
        page2 = QWidget()
        page2_layout = QVBoxLayout(page2)
        page2_layout.setContentsMargins(0, 8, 0, 0)

        self.table = QTableView()
        self.table_model = QStandardItemModel(self)
        headers = [
            "页码",
            "序号",
            "职位标题",
            "公司",
            "地点",
            "薪资",
            "日期",
            "状态",
            "备注",
        ]
        self.table_model.setHorizontalHeaderLabels(headers)
        self.table.setModel(self.table_model)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setEditTriggers(QTableView.NoEditTriggers)
        page2_layout.addWidget(self.table)
        self.tabs.addTab(page2, "职位列表")

        # 第三页：日志
        page3 = QWidget()
        page3_layout = QVBoxLayout(page3)
        page3_layout.setContentsMargins(0, 8, 0, 0)
        self.log_widget = QPlainTextEdit()
        self.log_widget.setReadOnly(True)
        self.log_widget.setPlaceholderText("运行日志将在这里显示…")
        page3_layout.addWidget(self.log_widget)
        self.tabs.addTab(page3, "日志")

        # 第四页：外部投递待办
        page4 = QWidget()
        page4_layout = QVBoxLayout(page4)
        page4_layout.setContentsMargins(0, 8, 0, 0)
        external_group = QGroupBox("外部投递待办（需手动投递）")
        external_layout = QVBoxLayout(external_group)
        self.txt_external_jobs = QPlainTextEdit()
        self.txt_external_jobs.setPlaceholderText(
            "点击 Quick Apply 后跳转到非 JobsDB 站点的职位会记录在此。\n"
            "投递完成后可回来查看，手动去对应链接投递。"
        )
        self.txt_external_jobs.setReadOnly(True)
        external_layout.addWidget(self.txt_external_jobs)
        external_btns = QHBoxLayout()
        self.btn_clear_external = QPushButton("清除列表")
        self.btn_open_external = QPushButton("在浏览器中打开选中链接")
        external_btns.addWidget(self.btn_clear_external)
        external_btns.addWidget(self.btn_open_external)
        external_btns.addStretch()
        external_layout.addLayout(external_btns)
        page4_layout.addWidget(external_group)
        self.tabs.addTab(page4, "外部投递待办")

        main_layout.addWidget(self.tabs, stretch=1)

        # 信号连接
        self.btn_login.clicked.connect(self.on_login_clicked)
        self.btn_login_done.clicked.connect(self.on_login_done_clicked)
        self.btn_switch_account.clicked.connect(self.on_switch_account_clicked)
        self.btn_start.clicked.connect(self.on_start_clicked)
        self.btn_stop.clicked.connect(self.on_stop_clicked)
        self.btn_pause.clicked.connect(self.on_pause_clicked)
        self.btn_resume.clicked.connect(self.on_resume_clicked)
        self.btn_view_all_stats.clicked.connect(self._on_view_all_stats)
        self.btn_refresh_classifications.clicked.connect(
            lambda: self._start_classification_fetcher(force=True)
        )
        self.btn_clear_external.clicked.connect(self._on_clear_external_jobs)
        self.btn_open_external.clicked.connect(self._on_open_selected_external)

    def _apply_style(self) -> None:
        """Apple 风格：干净、留白、清晰字体。"""
        font_family = '"Segoe UI", "PingFang SC", "Microsoft YaHei", "Helvetica Neue", sans-serif'
        self.setStyleSheet(
            f"""
            QMainWindow {{
                background: #f5f5f7;
            }}
            QWidget {{
                font-family: {font_family};
                font-size: 14px;
                color: #1d1d1f;
            }}
            QLabel {{
                color: #1d1d1f;
                font-size: 14px;
                letter-spacing: 0.02em;
            }}
            QMessageBox QLabel {{ color: #1d1d1f; }}
            QMessageBox {{ background: #ffffff; }}

            QGroupBox {{
                background: #ffffff;
                color: #1d1d1f;
                border: none;
                border-radius: 12px;
                margin-top: 16px;
                padding: 20px 20px 16px 20px;
                font-size: 15px;
                font-weight: 500;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 20px;
                padding: 0 8px;
                background: #ffffff;
                font-size: 17px;
                font-weight: 600;
                letter-spacing: -0.02em;
                color: #1d1d1f;
            }}

            QPushButton {{
                background: #0071e3;
                color: white;
                border: none;
                border-radius: 10px;
                padding: 12px 20px;
                font-size: 14px;
                font-weight: 500;
                letter-spacing: -0.01em;
            }}
            QPushButton:hover {{
                background: #0077ed;
            }}
            QPushButton:pressed {{
                background: #006edb;
            }}
            QPushButton:disabled {{
                background: #d2d2d7;
                color: #86868b;
            }}

            QPlainTextEdit, QTableView {{
                background: #ffffff;
                color: #1d1d1f;
                border: 1px solid #d2d2d7;
                border-radius: 10px;
                padding: 12px;
                font-size: 13px;
                selection-background-color: #b3d7ff;
            }}
            QTableView {{
                gridline-color: #e8e8ed;
            }}
            QHeaderView::section {{
                background: #f5f5f7;
                color: #1d1d1f;
                padding: 12px 10px;
                border: none;
                border-bottom: 1px solid #d2d2d7;
                border-right: 1px solid #e8e8ed;
                font-size: 13px;
                font-weight: 600;
            }}

            QSpinBox, QLineEdit, QComboBox {{
                background: #ffffff;
                color: #1d1d1f;
                border: 1px solid #d2d2d7;
                border-radius: 8px;
                padding: 10px 14px;
                font-size: 14px;
            }}
            QSpinBox:focus, QLineEdit:focus, QComboBox:focus {{
                border-color: #0071e3;
            }}

            QCheckBox {{
                color: #1d1d1f;
                spacing: 8px;
                font-size: 14px;
            }}

            QFormLayout QLabel {{
                font-weight: 500;
                color: #424245;
            }}

            QTabWidget::pane {{
                border: none;
                background: transparent;
                top: -1px;
            }}
            QTabBar::tab {{
                background: transparent;
                color: #424245;
                padding: 12px 20px;
                margin-right: 4px;
                font-size: 14px;
                font-weight: 500;
            }}
            QTabBar::tab:selected {{
                color: #0071e3;
                border-bottom: 2px solid #0071e3;
            }}
            QTabBar::tab:hover:!selected {{
                color: #1d1d1f;
            }}
            """
        )

    def _update_account_label(self) -> None:
        if not STATE_FILE.exists():
            self.lbl_account.setText("当前账号：未登录")
            if hasattr(self, "lbl_account_email"):
                self.lbl_account_email.setText("当前账号：未登录")
            return
        email = _get_current_account_email()
        if email:
            txt = f"当前账号：{email}"
        else:
            txt = "当前账号：已登录（邮箱未识别）"
        self.lbl_account.setText(txt)
        if hasattr(self, "lbl_account_email"):
            self.lbl_account_email.setText(txt)

    def _on_mode_changed(self) -> None:
        mode = self.combo_mode.currentIndex()
        self.txt_mode2_keyword.setEnabled(mode == 1)
        self.combo_mode3_category.setEnabled(mode == 2)
        self.btn_refresh_classifications.setEnabled(mode == 2)

    def _update_external_jobs_display(self) -> None:
        account_id = _get_account_id()
        items = _load_external_jobs(account_id)
        if not items:
            self.txt_external_jobs.setPlainText("（暂无）")
            return
        lines = [f"{title}\n  {url}" for title, url in items]
        self.txt_external_jobs.setPlainText("\n\n".join(lines))

    def _on_external_job_detected(self, title: str, url: str) -> None:
        account_id = _get_account_id()
        _append_external_job(account_id, title, url)
        self._update_external_jobs_display()
        self.append_log(f"已记录外部投递：{title}")

    def _on_clear_external_jobs(self) -> None:
        account_id = _get_account_id()
        p = _external_jobs_file(account_id)
        if p.exists():
            try:
                p.unlink()
                self._update_external_jobs_display()
                self.append_log("已清除外部投递列表。")
            except Exception as e:
                self.append_log(f"清除失败：{e}")
        else:
            self._update_external_jobs_display()

    def _on_open_selected_external(self) -> None:
        import webbrowser
        text = self.txt_external_jobs.textCursor().selectedText() or self.txt_external_jobs.toPlainText()
        for part in text.split():
            part = part.strip()
            if part.startswith("http"):
                webbrowser.open(part)
                return
        QMessageBox.information(
            self, "提示",
            "请先选中包含链接的文字，再点击打开。",
        )

    def _update_stats_display(self) -> None:
        account_id = _get_account_id()
        today, d7, d30 = _stats_summary(account_id)
        self.lbl_stats.setText(f"今日: {today}  近7天: {d7}  近30天: {d30}")

    def _start_classification_fetcher(self, force: bool = False) -> None:
        cache = _load_classifications_from_cache()
        if cache:
            self._populate_mode3_combo(cache)
            if not force:
                return  # 缓存有效，且非强制刷新，则不再抓取
        if self._classification_fetcher is not None and self._classification_fetcher.isRunning():
            self.append_log("分类正在加载中，请稍候。")
            return
        self._classification_fetcher = ClassificationFetcher(str(CLASSIFICATIONS_CACHE))
        self._classification_fetcher.classifications_loaded.connect(self._on_classifications_loaded)
        self._classification_fetcher.log_message.connect(self.append_log)
        self.append_log("正在后台抓取职位分类…")
        self._classification_fetcher.start()

    def _on_classifications_loaded(self, items: list) -> None:
        self._populate_mode3_combo(items)

    def _populate_mode3_combo(self, items: list[dict[str, str]]) -> None:
        self.combo_mode3_category.clear()
        self.combo_mode3_category.addItem("-- 请选择 --", "")
        for item in items:
            name = item.get("name", "")
            slug = item.get("slug", "")
            if name and slug:
                self.combo_mode3_category.addItem(name, slug)

    def _on_view_all_stats(self) -> None:
        files = list(ACCOUNTS_DIR.glob("apply_stats_*.json")) if ACCOUNTS_DIR.exists() else []
        if not files:
            QMessageBox.information(self, "统计", "暂无任何账号的投递记录。")
            return
        lines = ["各账号投递统计：\n"]
        for p in sorted(files):
            aid = p.stem.replace("apply_stats_", "")
            if aid == "default":
                aid = "(未填账号标识)"
            t, d7, d30 = _stats_summary(aid)
            lines.append(f"{aid}: 今日 {t}，近7天 {d7}，近30天 {d30}")
        QMessageBox.information(self, "所有账号统计", "\n".join(lines))

    def append_log(self, message: str) -> None:
        self.log_widget.appendPlainText(message)
        # 自动滚动到底部
        self.log_widget.verticalScrollBar().setValue(
            self.log_widget.verticalScrollBar().maximum()
        )

    def _parse_excluded_companies(self) -> list[str]:
        raw = self.txt_excluded_companies.toPlainText()
        parts: list[str] = []
        for line in raw.splitlines():
            for p in line.split(","):
                p = p.strip()
                if p:
                    parts.append(p)
        # 去重但保持顺序
        seen: set[str] = set()
        out: list[str] = []
        for p in parts:
            key = p.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(p)
        return out

    # ---------------- 登录相关 ---------------- #
    def on_login_clicked(self) -> None:
        """
        打开带界面的浏览器，让用户手动登录 JobsDB。
        """
        try:
            from playwright.sync_api import sync_playwright  # type: ignore
        except ImportError:
            QMessageBox.warning(
                self,
                "缺少依赖",
                "未安装 Playwright。\n\n请先在命令行中执行：\n"
                "  pip install playwright\n  playwright install",
            )
            return

        # 若之前打开过登录浏览器，先关闭
        self._close_login_browser()

        self.append_log("正在启动浏览器，请稍候…")
        try:
            self.playwright = sync_playwright().start()
            self.browser = self.playwright.chromium.launch(headless=False)
            self.context = self.browser.new_context()
            page = self.context.new_page()
            page.goto("https://hk.jobsdb.com/hk", wait_until="load")

            self.append_log("已打开 JobsDB 首页，请在浏览器中完成登录。")
            QMessageBox.information(
                self,
                "请登录 JobsDB",
                "浏览器已打开 JobsDB 首页。\n\n"
                "请在弹出的浏览器中完成登录（包括 2FA）。\n"
                "登录完成后，回到本窗口点击：\n“我已经在浏览器里登录完成”。",
            )
        except Exception as e:  # noqa: BLE001
            self.append_log(f"启动浏览器时出错：{e}")
            self._close_login_browser()

    def on_login_done_clicked(self) -> None:
        """
        用户在浏览器里登录完成后，保存登录状态。
        """
        if self.context is None:
            QMessageBox.information(
                self,
                "尚未打开浏览器",
                "请先点击“首次登录 / 重新登录当前账号”打开浏览器并完成登录。",
            )
            return

        try:
            ACCOUNTS_DIR.mkdir(parents=True, exist_ok=True)
            self.context.storage_state(path=str(STATE_FILE))
            self.append_log(f"登录状态已保存到：{STATE_FILE}")
            email = _extract_email_from_context(self.context)
            if not email:
                email = _extract_email_from_state_file()
            if email:
                _save_current_account_email(email)
                self.append_log(f"已识别账号：{email}")
            else:
                _save_current_account_email("")
            QMessageBox.information(
                self,
                "登录完成",
                "登录状态已保存。\n之后点击“开始自动投递”即可在后台自动投递。",
            )
        except Exception as e:  # noqa: BLE001
            self.append_log(f"保存登录状态时出错：{e}")
            QMessageBox.warning(self, "保存失败", f"保存登录状态失败：\n{e}")
        finally:
            self._close_login_browser()
            self._update_account_label()
            self._update_stats_display()
            self._update_external_jobs_display()

    def on_switch_account_clicked(self) -> None:
        """
        切换账号：清除当前状态文件并重新走登录流程。
        """
        if STATE_FILE.exists():
            try:
                STATE_FILE.unlink()
                self.append_log("已清除当前账号的登录状态。")
            except Exception as e:  # noqa: BLE001
                self.append_log(f"清除登录状态时出错：{e}")
        if CURRENT_ACCOUNT_FILE.exists():
            try:
                CURRENT_ACCOUNT_FILE.unlink()
            except Exception:
                pass

        self._update_account_label()
        self._update_stats_display()
        self._update_external_jobs_display()

        QMessageBox.information(
            self,
            "切换账号",
            "当前账号登录状态已清除。\n\n"
            "接下来将打开浏览器，请使用新的 JobsDB 账号登录。\n"
            "登录后会自动识别邮箱并显示投递统计。",
        )
        self.on_login_clicked()

    def _close_login_browser(self) -> None:
        # 安全关闭登录用的浏览器
        try:
            if self.browser is not None:
                self.browser.close()
        except Exception:
            pass
        try:
            if self.playwright is not None:
                self.playwright.stop()
        except Exception:
            pass

        self.browser = None
        self.context = None
        self.playwright = None

    # ---------------- 自动投递 ---------------- #
    def on_start_clicked(self) -> None:
        if not STATE_FILE.exists():
            QMessageBox.information(
                self,
                "尚未登录",
                "尚未检测到登录状态文件。\n\n请先完成登录流程：\n"
                "1. 点击“首次登录 / 重新登录当前账号”并在浏览器中登录。\n"
                "2. 完成后点击“我已经在浏览器里登录完成”。",
            )
            return

        if self.worker is not None and self.worker.isRunning():
            QMessageBox.information(self, "正在运行", "自动投递线程已在运行中。")
            return

        mode = self.combo_mode.currentIndex()
        if mode == 1:
            keyword = self.txt_mode2_keyword.text().strip()
            if not keyword:
                QMessageBox.warning(
                    self, "缺少参数",
                    "职位关键词模式需要输入关键词（如 shopify、admin）。",
                )
                return
        elif mode == 2:
            slug = self.combo_mode3_category.currentData()
            if not slug:
                QMessageBox.warning(
                    self, "缺少参数",
                    "职位类别模式需要选择一个分类。",
                )
                return
        else:
            slug = ""

        self.table_model.removeRows(0, self.table_model.rowCount())
        self._row_index.clear()

        excluded = self._parse_excluded_companies()
        max_pages = int(self.spin_max_pages.value())
        show_browser = bool(self.chk_show_browser.isChecked())
        slow_mo_ms = int(self.spin_slowmo.value())
        human_level = int(self.combo_human_level.currentIndex())
        mode2_kw = self.txt_mode2_keyword.text().strip() if mode == 1 else ""
        mode3_slug = (self.combo_mode3_category.currentData() or "") if mode == 2 else ""
        experience_years = self.combo_experience_years.currentIndex()
        expected_salary = self.combo_expected_salary.currentText()  # 16K, 17K, ..., 30K

        self.append_log("开始自动投递（将逐页抓取并尝试投递）…")
        self.worker = JobsdbWorker(
            state_file=str(STATE_FILE),
            excluded_companies=excluded,
            max_pages=max_pages,
            show_browser=show_browser,
            slow_mo_ms=slow_mo_ms,
            human_level=human_level,
            mode_type=mode + 1,
            mode2_keyword=mode2_kw,
            mode3_category_slug=mode3_slug,
            experience_years=experience_years,
            expected_salary=expected_salary,
        )
        self.worker.jobs_loaded.connect(self.on_jobs_loaded)
        self.worker.job_status_changed.connect(self.on_job_status_changed)
        self.worker.log_message.connect(self.append_log)
        self.worker.external_job_detected.connect(self._on_external_job_detected)
        self.worker.finished.connect(self.on_worker_finished)

        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.btn_pause.setEnabled(True)
        self.btn_resume.setEnabled(False)

        self.worker.start()

    def on_stop_clicked(self) -> None:
        if self.worker is None or not self.worker.isRunning():
            return
        self.append_log("请求停止自动投递线程…")
        self.worker.request_stop()

    def on_pause_clicked(self) -> None:
        if self.worker is None or not self.worker.isRunning():
            return
        self.worker.request_pause()
        self.btn_pause.setEnabled(False)
        self.btn_resume.setEnabled(True)
        self.append_log("已暂停，点击「恢复」继续投递。")

    def on_resume_clicked(self) -> None:
        if self.worker is None or not self.worker.isRunning():
            return
        self.worker.request_resume()
        self.btn_resume.setEnabled(False)
        self.btn_pause.setEnabled(True)
        self.append_log("已恢复投递。")

    # ---------------- Worker 回调 ---------------- #
    def on_jobs_loaded(self, page_index: int, jobs: list) -> None:  # type: ignore[override]
        """
        Worker 抓取到一页职位后更新表格。
        """
        for i, job in enumerate(jobs, start=1):
            row_items = [
                QStandardItem(str(page_index)),
                QStandardItem(str(i)),
                QStandardItem(job.get("title", "") or ""),
                QStandardItem(job.get("company", "") or ""),
                QStandardItem(job.get("location", "") or ""),
                QStandardItem(job.get("salary", "") or ""),
                QStandardItem(job.get("date", "") or ""),
                QStandardItem("待投递"),
                QStandardItem(""),
            ]
            for item in row_items:
                item.setEditable(False)
            self.table_model.appendRow(row_items)
            self._row_index[(page_index, i)] = self.table_model.rowCount() - 1

        self.append_log(f"第 {page_index} 页职位列表已加载，共 {len(jobs)} 条。")

    def on_job_status_changed(
        self,
        page_index: int,
        job_index: int,
        status: str,
        message: str,
    ) -> None:  # type: ignore[override]
        row = self._row_index.get((page_index, job_index))
        if row is None:
            return
        if 0 <= row < self.table_model.rowCount():
            status_item = self.table_model.item(row, 7)
            remark_item = self.table_model.item(row, 8)
            if status_item is not None:
                status_item.setText(status)
            if remark_item is not None:
                remark_item.setText(message)
        if status == "成功":
            _increment_today(_get_account_id())
            self._update_stats_display()

    def on_worker_finished(self) -> None:  # type: ignore[override]
        self.append_log("自动投递线程已结束。")
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.btn_pause.setEnabled(False)
        self.btn_resume.setEnabled(False)
        self.worker = None


def main() -> None:
    app = QApplication(sys.argv)
    font = app.font()
    font.setFamily("Segoe UI, PingFang SC, Microsoft YaHei")
    font.setPointSize(10)
    app.setFont(font)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

