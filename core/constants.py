# -*- coding: utf-8 -*-
"""
模块名：core.constants
职责：全局常量——窗口尺寸、配色表、字体、分类默认值、路径
依赖：无
"""

import os
import sys

from core.paths import get_appdata_dir

APP_NAME = "Win11Launcher"

# 应用版本号：deb 打包 / 关于信息共用（make_deb.sh 会读取此值）
APP_VERSION = "1.1.0"

# ============================================================
# 路径
# ============================================================
APPDATA_DIR = get_appdata_dir()
CONFIG_FILE = os.path.join(APPDATA_DIR, "launcher_config.json")
ICON_CACHE_DIR = os.path.join(APPDATA_DIR, "icon_cache")

# ============================================================
# 界面缩放（放大缩小）
# ============================================================
# 缩放作用于整 UI：窗口 / 卡片 / 图标 / 字号 / 菜单按同一系数等比放大缩小。
# 默认 1.0 —— 与历史版本逐像素一致；用户经 Ctrl+滚轮或设置滑块调整。
UI_SCALE_DEFAULT = 1.0
UI_SCALE_MIN = 0.8
UI_SCALE_MAX = 1.6
UI_SCALE_STEP = 0.1

_scale = UI_SCALE_DEFAULT

# 基准设计值（缩放 = 1.0 时的原始尺寸）；缩放时整体按比例重算。
# 注意：GRID_COLUMNS / FOLDER_GRID_COLUMNS 等布局数量不缩放（保持网格结构）。
_BASE = {
    # 窗口
    "WINDOW_WIDTH": 1060, "WINDOW_HEIGHT": 700,
    # 网格与卡片
    "ICON_SIZE": 48, "ITEM_WIDTH": 100, "ITEM_HEIGHT": 100,
    "GRID_PADDING": 16, "GRID_EXTRA_PADDING": 120,
    # 字体
    "FONT_TITLE_SIZE": 18, "FONT_TAB_SIZE": 13, "FONT_CARD_NAME_BASE": 11,
    "FONT_CARD_NAME_MIN": 8, "FONT_MENU_SIZE": 13, "FONT_STATUS_SIZE": 12,
    "FONT_FOLDER_TITLE_SIZE": 15,
    # 尺寸细节
    "TITLEBAR_HEIGHT": 36,
    "CARD_CORNER_RADIUS": 8, "ICON_CORNER_RADIUS": 8,
    "TAB_WIDTH": 100, "TAB_HEIGHT": 36, "TAB_SPACING": 4, "TAB_CORNER_RADIUS": 8,
    "MENU_ITEM_HEIGHT": 30, "MENU_CORNER_RADIUS": 4,
    "MENU_WIDTH_APP": 195, "MENU_WIDTH_FOLDER": 150,
    "MENU_WIDTH_SUB_CATEGORY": 140, "MENU_WIDTH_SUB_FOLDER": 160,
    "FOLDER_WINDOW_WIDTH": 500, "FOLDER_WINDOW_HEIGHT": 400,
    # 卡片名换行估算宽度（原 app_card 内部硬编码值，收敛至此）
    "CARD_NAME_MAX_WIDTH": 90,
}


def _apply_scale():
    """按当前 _scale 重算全部可缩放常量（模块属性，读取方自动生效）"""
    g = globals()
    for name, base in _BASE.items():
        g[name] = max(1, int(round(base * _scale)))


_apply_scale()


def set_scale(factor: float):
    """设置界面缩放系数（自动夹取到 [UI_SCALE_MIN, UI_SCALE_MAX]）"""
    global _scale
    _scale = round(min(max(float(factor), UI_SCALE_MIN), UI_SCALE_MAX), 2)
    _apply_scale()


def get_scale() -> float:
    """当前缩放系数"""
    return _scale
LOG_FILE = os.path.join(APPDATA_DIR, "launcher.log")

# ============================================================
# 窗口
# ============================================================
WINDOW_TITLE = "Win11 Launchpad"
# WINDOW_WIDTH / WINDOW_HEIGHT 见 _BASE（随缩放重算）
WINDOW_ALPHA_DEFAULT = 0.96

# ============================================================
# 网格与卡片
# ============================================================
# ICON_SIZE / ITEM_WIDTH / ITEM_HEIGHT / GRID_PADDING / GRID_EXTRA_PADDING
# 见 _BASE（随缩放重算）
GRID_COLUMNS = 9

# ============================================================
# 分类
# ============================================================
DEFAULT_CATEGORIES = ["系统应用", "办公软件", "社交软件", "影音视频", "语言编程", "我的游戏"]

# ============================================================
# 配色表（浅色, 深色）
# ============================================================
COLOR_WINDOW_BG = ("#F3F3F3", "#1F1F1F")
COLOR_TITLE_TEXT = ("#1A1A1A", "#E0E0E0")

# 分类标签按钮
COLOR_TAB_ACTIVE_BG = ("#0078D4", "#005A9E")
COLOR_TAB_ACTIVE_FG = ("#FFFFFF", "#FFFFFF")
COLOR_TAB_INACTIVE_BG = ("#E8E8E8", "#2D2D2D")
COLOR_TAB_INACTIVE_FG = ("#1A1A1A", "#E0E0E0")

# 应用卡片
COLOR_CARD_BG = ("#FFFFFF", "#2D2D2D")
COLOR_CARD_HOVER_BG = ("#F0F8FF", "#3D3D3D")
COLOR_CARD_HOVER_BORDER = ("#0078D4", "#0078D4")
COLOR_CARD_CLICK_BG = ("#D0D0D0", "#4D4D4D")
COLOR_CARD_DRAG_BG = ("#0078D4", "#005A9E")
COLOR_CARD_NAME = ("#1A1A1A", "#E0E0E0")

# 图标底色
COLOR_ICON_APP_BG = ("#0078D4", "#005A9E")
COLOR_ICON_FOLDER_BG = ("#FFB900", "#D29200")

# 底部按钮
COLOR_BTN_PRIMARY_BG = ("#0078D4", "#005A9E")
COLOR_BTN_PRIMARY_FG = ("#FFFFFF", "#FFFFFF")
COLOR_BTN_SECONDARY_BG = ("#E8E8E8", "#2D2D2D")
COLOR_BTN_SECONDARY_FG = ("#1A1A1A", "#E0E0E0")
COLOR_STATUS_TEXT = ("#666666", "#888888")
COLOR_DANGER_BG = ("#E81123", "#C42B1C")

# 右键菜单
COLOR_MENU_BG = ("#FFFFFF", "#323232")
COLOR_MENU_FG = ("#1A1A1A", "#FFFFFF")
COLOR_MENU_HOVER = ("#E8F0FE", "#3D3D3D")
COLOR_MENU_SEP = ("#E5E5E5", "#3C3C3C")
COLOR_MENU_BORDER = ("#E0D8D0", "#454545")

# 文件夹弹窗
COLOR_FOLDER_BG = ("#F3F3F3", "#202020")
COLOR_EMPTY_TEXT = ("#888888", "#666666")

# 原生标题栏（DWM 用，需 RGB 元组）
TITLEBAR_RGB = ((243, 243, 243), (31, 31, 31))

# "已添加"标记
COLOR_ADDED_MARK = ("#107C10", "#6CCB5F")

# ============================================================
# 字体
# ============================================================
# FONT_TITLE_SIZE / FONT_TAB_SIZE / FONT_CARD_NAME_BASE / FONT_CARD_NAME_MIN /
# FONT_MENU_SIZE / FONT_STATUS_SIZE / FONT_FOLDER_TITLE_SIZE 见 _BASE（随缩放重算）
FONT_FAMILY = "Microsoft YaHei UI"


def resolve_font_family() -> str:
    """解析当前平台可用字体族（需 QApplication 已创建，供 main.py 启动时调用）。

    Windows：微软雅黑（原行为）；
    Linux（麒麟 UKUI）：按常见中文字体候选探测，均不可用时返回 ""
    （空串 = 交给 Qt 默认字体替换机制）。
    """
    if sys.platform == "win32":
        return "Microsoft YaHei UI"
    try:
        from PySide6.QtGui import QFontDatabase
        families = set(QFontDatabase.families())
        for cand in ("Noto Sans CJK SC", "Source Han Sans SC", "WenQuanYi Micro Hei",
                     "UKUI Sans", "Microsoft YaHei UI", "DejaVu Sans"):
            if cand in families:
                return cand
    except Exception:
        pass
    return ""

# ============================================================
# 尺寸细节
# ============================================================
# CARD_CORNER_RADIUS / ICON_CORNER_RADIUS / TAB_* / MENU_* / FOLDER_WINDOW_*
# 见 _BASE（随缩放重算）
# 卡片背景不透明度（0-255）：略小于 255，让底层亚克力轻微透出
CARD_BG_ALPHA = 210
SUBMENU_HOVER_DELAY_MS = 120

FOLDER_GRID_COLUMNS = 4

# ============================================================
# 快捷键
# ============================================================
DEFAULT_HOTKEY = "Ctrl+Shift+L"

# ============================================================
# 主题
# ============================================================
THEME_LIGHT = "浅色"
THEME_DARK = "深色"
THEME_SYSTEM = "跟随系统"
THEME_OPTIONS = [THEME_LIGHT, THEME_DARK, THEME_SYSTEM]


def color(pair, dark: bool) -> str:
    """从 (浅色, 深色) 配色对中取值"""
    return pair[1] if dark else pair[0]


# ============================================================
# 弹窗配色（不透明，避免亚克力透出导致的黑块/白块）
# ============================================================
COLOR_DIALOG_BG = ("#F3F3F3", "#202020")
COLOR_DIALOG_TEXT = ("#1A1A1A", "#E0E0E0")
COLOR_INPUT_BG = ("#FFFFFF", "#2D2D2D")
COLOR_INPUT_BORDER = ("#D0D0D0", "#454545")
COLOR_LIST_ROW_BG = ("#FFFFFF", "#2A2A2A")
COLOR_LIST_ROW_ALT = ("#F7F7F7", "#252525")


def dialog_qss(dark: bool) -> str:
    """生成弹窗统一主题样式表

    统一管理所有子控件背景，避免：
    - QScrollArea viewport 默认白底在深色下形成白块
    - 子控件未覆盖区域露出未初始化黑块
    """
    bg = color(COLOR_DIALOG_BG, dark)
    fg = color(COLOR_DIALOG_TEXT, dark)
    input_bg = color(COLOR_INPUT_BG, dark)
    input_border = color(COLOR_INPUT_BORDER, dark)
    btn_bg = color(COLOR_BTN_SECONDARY_BG, dark)
    btn_fg = color(COLOR_BTN_SECONDARY_FG, dark)
    primary_bg = color(COLOR_BTN_PRIMARY_BG, dark)
    primary_fg = color(COLOR_BTN_PRIMARY_FG, dark)
    hover = color(COLOR_MENU_HOVER, dark)

    return f"""
    QDialog {{ background-color: {bg}; }}
    QWidget {{ color: {fg}; }}
    QLabel {{ color: {fg}; background: transparent; }}
    QScrollArea {{ background: transparent; border: none; }}
    QScrollArea > QWidget > QWidget {{ background: transparent; }}
    QScrollArea > QWidget {{ background: transparent; }}
    QLineEdit, QComboBox, QSpinBox {{
        background-color: {input_bg}; color: {fg};
        border: 1px solid {input_border}; border-radius: 6px;
        padding: 4px 8px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {input_bg}; color: {fg};
        selection-background-color: {hover};
        border: 1px solid {input_border};
    }}
    QCheckBox {{ color: {fg}; background: transparent; spacing: 6px; }}
    QPushButton {{
        background-color: {btn_bg}; color: {btn_fg};
        border: none; border-radius: 6px; padding: 6px 14px;
    }}
    QPushButton:hover {{ background-color: {hover}; }}
    QPushButton[primary="true"] {{
        background-color: {primary_bg}; color: {primary_fg};
    }}
    QScrollBar:vertical {{
        width: 8px; background: transparent;
    }}
    QScrollBar::handle:vertical {{
        background: rgba(128,128,128,0.4);
        border-radius: 4px; min-height: 30px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: transparent;
    }}
    """
