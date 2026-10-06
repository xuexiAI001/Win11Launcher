# -*- coding: utf-8 -*-
"""
模块名：ui.context_menu
职责：右键菜单——应用菜单、文件夹菜单、空白菜单，明暗配色
依赖：core.constants, core.logger
"""

from PySide6.QtWidgets import QMenu
from PySide6.QtGui import QAction
from PySide6.QtCore import Qt

from core import constants as C
from core.logger import get_logger

logger = get_logger()


def menu_style(dark: bool) -> str:
    """菜单样式表（供右键菜单与托盘菜单共用）"""
    bg = C.color(C.COLOR_MENU_BG, dark)
    fg = C.color(C.COLOR_MENU_FG, dark)
    hover = C.color(C.COLOR_MENU_HOVER, dark)
    sep = C.color(C.COLOR_MENU_SEP, dark)
    border = C.color(C.COLOR_MENU_BORDER, dark)
    return (
        f"QMenu {{"
        f" background-color: {bg}; color: {fg};"
        f" border: 1px solid {border}; border-radius: {C.MENU_CORNER_RADIUS}px;"
        f" padding: 4px;"
        f" font-family: '{C.FONT_FAMILY}'; font-size: {C.FONT_MENU_SIZE}px;"
        f"}}"
        f"QMenu::item {{"
        f" padding: 6px 24px 6px 12px; border-radius: 4px;"
        f"}}"
        f"QMenu::item:selected {{ background-color: {hover}; }}"
        f"QMenu::separator {{ height: 1px; background: {sep}; margin: 3px 12px; }}"
    )


# 兼容旧调用名
_menu_style = menu_style


def build_app_menu(parent, app_data: dict, dark: bool, handlers: dict) -> QMenu:
    """构建应用卡片右键菜单

    Args:
        parent: 父控件
        app_data: 应用数据
        dark: 是否深色
        handlers: 回调字典，键为动作名
    """
    menu = QMenu(parent)
    menu.setStyleSheet(_menu_style(dark))

    def add(label, key, enabled=True):
        act = QAction(label, menu)
        act.setEnabled(enabled)
        if key and key in handlers:
            act.triggered.connect(lambda: handlers[key](app_data))
        menu.addAction(act)
        return act

    add("启动", "launch")
    add("管理员身份启动", "launch_admin")
    menu.addSeparator()

    # 移动分类子菜单
    move_menu = menu.addMenu("移动分类")
    move_menu.setStyleSheet(_menu_style(dark))
    for cat in handlers.get("categories", []):
        act = QAction(cat, move_menu)
        act.triggered.connect(
            lambda checked=False, c=cat: handlers["move_category"](app_data, c)
        )
        move_menu.addAction(act)

    # 移动到文件夹子菜单
    folder_menu = menu.addMenu("移动到文件夹")
    folder_menu.setStyleSheet(_menu_style(dark))
    for folder in handlers.get("folders", []):
        act = QAction(folder.get("name", ""), folder_menu)
        act.triggered.connect(
            lambda checked=False, f=folder: handlers["move_to_folder"](app_data, f)
        )
        folder_menu.addAction(act)
    if handlers.get("folders"):
        folder_menu.addSeparator()
    act = QAction("新建文件夹...", folder_menu)
    act.triggered.connect(lambda: handlers["create_folder"](app_data))
    folder_menu.addAction(act)

    if handlers.get("in_folder"):
        add("移出文件夹", "remove_from_folder")

    menu.addSeparator()
    add("更换图标", "change_icon")
    add("重命名", "rename")
    menu.addSeparator()
    add("删除应用", "delete_app")
    add("清空当前分类", "clear_category")
    menu.addSeparator()
    add("打开文件位置", "open_location")
    add("属性", "properties")
    menu.addSeparator()
    add("设置", "settings")

    return menu


def build_folder_menu(parent, app_data: dict, dark: bool, handlers: dict) -> QMenu:
    """构建文件夹卡片右键菜单"""
    menu = QMenu(parent)
    menu.setStyleSheet(_menu_style(dark))

    def add(label, key):
        act = QAction(label, menu)
        act.triggered.connect(lambda: handlers[key](app_data))
        menu.addAction(act)

    add("打开", "open_folder")
    add("重命名", "rename_folder")
    menu.addSeparator()
    add("删除文件夹", "delete_folder")
    return menu


def build_blank_menu(parent, dark: bool, handlers: dict) -> QMenu:
    """构建空白处右键菜单"""
    menu = QMenu(parent)
    menu.setStyleSheet(_menu_style(dark))

    new_menu = menu.addMenu("新建")
    new_menu.setStyleSheet(_menu_style(dark))
    for label, key in [("文件夹", "new_folder"), ("文本文档", "new_txt"),
                       ("Word 文档", "new_docx"), ("Excel 表格", "new_xlsx"),
                       ("PowerPoint 演示", "new_pptx")]:
        act = QAction(label, new_menu)
        act.triggered.connect(lambda checked=False, k=key: handlers[k]())
        new_menu.addAction(act)

    menu.addSeparator()
    act = QAction("添加应用...", menu)
    act.triggered.connect(lambda: handlers["add_app"]())
    menu.addAction(act)

    menu.addSeparator()
    act = QAction("设置", menu)
    act.triggered.connect(lambda: handlers["settings"]())
    menu.addAction(act)

    return menu
