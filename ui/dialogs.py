# -*- coding: utf-8 -*-
"""
模块名：ui.dialogs
职责：设置面板、分类管理、各类确认对话框
依赖：core.constants, core.logger, ui.window_effects
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QComboBox, QSlider, QCheckBox, QScrollArea, QWidget, QMessageBox,
    QFileDialog, QInputDialog
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from core import constants as C
from core.logger import get_logger
from ui import window_effects

logger = get_logger()


class SettingsDialog(QDialog):
    """设置面板"""

    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.config = main_window.config
        self.dark = main_window.dark

        self.setWindowTitle("设置")
        self.setFixedSize(500, 560)
        self._center()
        self._setup_ui()
        window_effects.apply_acrylic(self, self.config.alpha)

    def _c(self, pair) -> str:
        return C.color(pair, self.dark)

    def _center(self):
        screen = self.screen().availableGeometry()
        self.move((screen.width() - 500) // 2, (screen.height() - 560) // 2)

    def _setup_ui(self):
        # 统一主题样式表：一次性定义所有子控件外观，避免白块/黑块
        self.setStyleSheet(C.dialog_qss(self.dark))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 15, 30, 15)
        layout.setSpacing(10)

        title = QLabel("设置")
        font = QFont(C.FONT_FAMILY, 20)
        font.setBold(True)
        title.setFont(font)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # 快捷键
        row = QHBoxLayout()
        row.addWidget(QLabel("启动快捷键:"))
        self.hotkey_edit = QLineEdit(self.config.__dict__.get("hotkey", C.DEFAULT_HOTKEY))
        self.hotkey_edit.setFixedSize(150, 32)
        row.addWidget(self.hotkey_edit)
        row.addStretch(1)
        layout.addLayout(row)

        # 最小化到托盘
        self.tray_check = QCheckBox("关闭时最小化到托盘")
        self.tray_check.setChecked(True)
        layout.addWidget(self.tray_check)

        # 主题
        row = QHBoxLayout()
        row.addWidget(QLabel("主题颜色:"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(C.THEME_OPTIONS)
        self.theme_combo.setCurrentText(self.config.theme)
        self.theme_combo.setFixedSize(120, 32)
        row.addWidget(self.theme_combo)
        row.addStretch(1)
        layout.addLayout(row)

        # 透明度
        row = QHBoxLayout()
        row.addWidget(QLabel("窗口透明度:"))
        self.alpha_slider = QSlider(Qt.Horizontal)
        self.alpha_slider.setRange(50, 100)
        self.alpha_slider.setValue(int(self.config.alpha * 100))
        self.alpha_slider.setFixedWidth(200)
        self.alpha_label = QLabel(f"{int(self.config.alpha * 100)}%")
        self.alpha_slider.valueChanged.connect(
            lambda v: self.alpha_label.setText(f"{v}%")
        )
        row.addWidget(self.alpha_slider)
        row.addWidget(self.alpha_label)
        row.addStretch(1)
        layout.addLayout(row)

        # 开机自启
        self.autostart_check = QCheckBox("开机自启动")
        from services.autostart import is_autostart_enabled
        self.autostart_check.setChecked(is_autostart_enabled())
        layout.addWidget(self.autostart_check)

        # 管理分类
        self.cat_btn = QPushButton("管理分类...")
        self.cat_btn.setFixedHeight(36)
        self.cat_btn.clicked.connect(self._open_category_manager)
        layout.addWidget(self.cat_btn)

        # 导入导出
        row = QHBoxLayout()
        export_btn = QPushButton("导出配置")
        export_btn.setFixedHeight(32)
        export_btn.clicked.connect(self._export_config)
        import_btn = QPushButton("导入配置")
        import_btn.setFixedHeight(32)
        import_btn.clicked.connect(self._import_config)
        row.addWidget(export_btn)
        row.addWidget(import_btn)
        layout.addLayout(row)

        # 查看已扫描应用
        self.scan_btn = QPushButton("查看已扫描应用（开始菜单）")
        self.scan_btn.setFixedHeight(32)
        self.scan_btn.clicked.connect(self._open_scanned_apps)
        layout.addWidget(self.scan_btn)

        layout.addStretch(1)

        # 保存/取消
        row = QHBoxLayout()
        row.addStretch(1)
        save_btn = QPushButton("保存设置")
        save_btn.setFixedSize(120, 36)
        save_btn.clicked.connect(self._save)
        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedSize(120, 36)
        cancel_btn.clicked.connect(self.reject)
        row.addWidget(save_btn)
        row.addWidget(cancel_btn)
        layout.addLayout(row)

    def _open_category_manager(self):
        dlg = CategoryManagerDialog(self.main_window)
        dlg.exec()

    def _open_scanned_apps(self):
        dlg = ScannedAppsDialog(self.main_window)
        dlg.exec()

    def _export_config(self):
        path, _ = QFileDialog.getSaveFileName(self, "导出配置", "launcher_config.json",
                                              "JSON 文件 (*.json)")
        if path and self.config.export_to(path):
            QMessageBox.information(self, "导出成功", f"配置已导出到:\n{path}")

    def _import_config(self):
        path, _ = QFileDialog.getOpenFileName(self, "导入配置", "", "JSON 文件 (*.json)")
        if not path:
            return
        ret = QMessageBox.question(self, "导入配置",
                                   "导入将覆盖当前配置，确定继续吗？",
                                   QMessageBox.Yes | QMessageBox.No)
        if ret != QMessageBox.Yes:
            return
        if self.config.import_from(path):
            self.config.save()
            QMessageBox.information(self, "导入成功", "配置已导入，重启后完全生效")

    def _save(self):
        """保存设置"""
        self.config.theme = self.theme_combo.currentText()
        self.config.alpha = self.alpha_slider.value() / 100.0
        self.config.__dict__["hotkey"] = self.hotkey_edit.text().strip()

        from services.autostart import set_autostart
        set_autostart(self.autostart_check.isChecked())

        self.config.save()
        # 主题立即生效（窗口背景、标题栏、标签、卡片、弹窗）
        self.main_window.apply_theme()
        self.main_window.show_message("设置已保存")
        self.accept()


class CategoryManagerDialog(QDialog):
    """分类管理"""

    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.config = main_window.config
        self.dark = main_window.dark

        self.setWindowTitle("分类管理")
        self.setFixedSize(460, 440)
        self._center()
        self._setup_ui()
        window_effects.apply_acrylic(self, self.config.alpha)

    def _c(self, pair) -> str:
        return C.color(pair, self.dark)

    def _center(self):
        screen = self.screen().availableGeometry()
        self.move((screen.width() - 460) // 2, (screen.height() - 440) // 2)

    def _setup_ui(self):
        # 统一主题样式表
        self.setStyleSheet(C.dialog_qss(self.dark))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 15, 30, 15)
        layout.setSpacing(10)

        title = QLabel("分类管理")
        font = QFont(C.FONT_FAMILY, 18)
        font.setBold(True)
        title.setFont(font)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFixedHeight(260)
        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setAlignment(Qt.AlignTop)
        self.scroll.setWidget(self.list_container)
        layout.addWidget(self.scroll)

        # 添加区
        row = QHBoxLayout()
        self.new_edit = QLineEdit()
        self.new_edit.setPlaceholderText("输入新分类名称...")
        self.new_edit.setFixedHeight(32)
        self.new_edit.returnPressed.connect(self._add_category)
        add_btn = QPushButton("+ 添加")
        add_btn.setFixedSize(70, 32)
        add_btn.clicked.connect(self._add_category)
        row.addWidget(self.new_edit)
        row.addWidget(add_btn)
        layout.addLayout(row)

        close_btn = QPushButton("关闭")
        close_btn.setFixedSize(100, 32)
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, 0, Qt.AlignCenter)

        self._render_list()

    def _render_list(self):
        """渲染分类列表"""
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)

        for i, cat in enumerate(self.config.categories):
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            count = len(self.config.get_apps(cat))
            label = QLabel(f"{cat}  ({count})")
            label.setFixedWidth(220)
            rl.addWidget(label)

            if i == 0:
                default_label = QLabel("默认")
                default_label.setStyleSheet(f"color: {self._c(C.COLOR_STATUS_TEXT)};")
                rl.addWidget(default_label)
            else:
                rename_btn = QPushButton("重命名")
                rename_btn.setFixedSize(60, 26)
                rename_btn.clicked.connect(lambda checked=False, c=cat: self._rename(c))
                del_btn = QPushButton("删除")
                del_btn.setFixedSize(50, 26)
                del_btn.clicked.connect(lambda checked=False, c=cat: self._delete(c))
                rl.addWidget(rename_btn)
                rl.addWidget(del_btn)

            rl.addStretch(1)
            self.list_layout.addWidget(row)

    def _add_category(self):
        name = self.new_edit.text().strip()
        if not name:
            return
        if self.config.add_category(name):
            self.config.save()
            self.new_edit.clear()
            self._render_list()
            self.main_window._setup_tabs_refresh()
        else:
            QMessageBox.warning(self, "提示", "分类已存在或名称为空")

    def _rename(self, cat: str):
        name, ok = QInputDialog.getText(self, "重命名分类", "新名称:", text=cat)
        if not ok or not name.strip():
            return
        if self.config.rename_category(cat, name.strip()):
            self.config.save()
            self._render_list()
            self.main_window._setup_tabs_refresh()

    def _delete(self, cat: str):
        count = len(self.config.get_apps(cat))
        ret = QMessageBox.question(
            self, "删除分类",
            f"确定要删除分类「{cat}」吗？\n该分类下有 {count} 个应用，将一并删除。",
            QMessageBox.Yes | QMessageBox.No
        )
        if ret != QMessageBox.Yes:
            return
        if self.config.delete_category(cat):
            self.config.save()
            self._render_list()
            self.main_window._setup_tabs_refresh()


class ScannedAppsDialog(QDialog):
    """已扫描应用（开始菜单）——带复选框批量添加到指定分类"""

    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.config = main_window.config
        self.dark = main_window.dark

        self.setWindowTitle("已扫描应用")
        self.setFixedSize(620, 600)
        self._center()

        # 图标异步加载器（独立实例，回调只服务本对话框）
        from services.icon_loader import IconLoader
        self.icon_loader = IconLoader()
        self.icon_loader.icon_ready.connect(self._on_icon_ready)
        self.icon_labels: dict[str, QLabel] = {}
        self._icon_map: dict[int, str] = {}

        self._setup_ui()
        window_effects.apply_acrylic(self, self.config.alpha)

    def _c(self, pair) -> str:
        return C.color(pair, self.dark)

    def _center(self):
        screen = self.screen().availableGeometry()
        self.move((screen.width() - 620) // 2, (screen.height() - 600) // 2)

    def _setup_ui(self):
        from services.install_monitor import scan_start_menu_names

        # 统一主题样式表
        self.setStyleSheet(C.dialog_qss(self.dark))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(8)

        # 扫描开始菜单
        self.apps = sorted(scan_start_menu_names())
        self.setWindowTitle(f"已扫描应用（共 {len(self.apps)} 个）")

        # 已添加位置映射：应用名 -> [分类 或 分类/文件夹]
        self.added_map: dict[str, list[str]] = {}
        for cat, cat_apps in self.config.app_config.items():
            for app in cat_apps:
                if app.get("type") == "folder":
                    fname = app.get("name", "")
                    for sub in app.get("apps", []):
                        nm = sub.get("name", "")
                        if nm:
                            self.added_map.setdefault(nm, []).append(f"{cat}/{fname}")
                else:
                    nm = app.get("name", "")
                    if nm:
                        self.added_map.setdefault(nm, []).append(cat)
        self.added_count = sum(1 for nm in self.apps if nm in self.added_map)

        # 顶部统计
        self.count_label = QLabel()
        font = QFont(C.FONT_FAMILY, 12)
        font.setBold(True)
        self.count_label.setFont(font)
        layout.addWidget(self.count_label)

        # 全选 / 取消全选
        row = QHBoxLayout()
        select_all_btn = QPushButton("全选")
        select_all_btn.setFixedSize(80, 28)
        select_all_btn.clicked.connect(self._select_all)
        deselect_btn = QPushButton("取消全选")
        deselect_btn.setFixedSize(80, 28)
        deselect_btn.clicked.connect(self._deselect_all)
        row.addWidget(select_all_btn)
        row.addWidget(deselect_btn)
        row.addStretch(1)
        layout.addLayout(row)

        # 可滚动列表
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setAlignment(Qt.AlignTop)
        self.list_layout.setSpacing(2)
        self.scroll.setWidget(self.list_container)
        layout.addWidget(self.scroll, 1)

        self.checkboxes: dict[str, QCheckBox] = {}
        self._render_list()

        # 底部：分类选择 + 添加
        bottom = QHBoxLayout()
        bottom.addWidget(QLabel("添加到分类："))
        self.cat_combo = QComboBox()
        self.cat_combo.addItems(self.config.categories)
        self.cat_combo.setFixedSize(120, 30)
        bottom.addWidget(self.cat_combo)
        self.add_btn = QPushButton("添加选中")
        self.add_btn.setFixedSize(100, 30)
        self.add_btn.setEnabled(False)
        self.add_btn.clicked.connect(self._batch_add)
        bottom.addWidget(self.add_btn)
        close_btn = QPushButton("关闭")
        close_btn.setFixedSize(80, 30)
        close_btn.clicked.connect(self.accept)
        bottom.addWidget(close_btn)
        bottom.addStretch(1)
        layout.addLayout(bottom)

        self._update_count()

    def _render_list(self):
        """渲染应用列表"""
        for idx, name in enumerate(self.apps, 1):
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(4, 0, 4, 0)
            rl.setSpacing(6)

            cb = QCheckBox()
            cb.stateChanged.connect(self._update_count)
            self.checkboxes[name] = cb
            rl.addWidget(cb)

            # 图标占位（异步加载后填充）
            icon_label = QLabel()
            icon_label.setFixedSize(24, 24)
            icon_label.setAlignment(Qt.AlignCenter)
            rl.addWidget(icon_label)
            self.icon_labels[name] = icon_label

            label = QLabel(f"{idx:3d}.  {name}")
            label.setFont(QFont(C.FONT_FAMILY, 11))
            rl.addWidget(label)
            rl.addStretch(1)

            locations = self.added_map.get(name, [])
            if locations:
                loc_text = "已添加 · " + "、".join(locations[:3])
                if len(locations) > 3:
                    loc_text += f" 等{len(locations)}处"
                loc_label = QLabel(loc_text)
                loc_label.setFont(QFont(C.FONT_FAMILY, 9))
                loc_label.setStyleSheet("color: #107C10;")
                rl.addWidget(loc_label)

            self.list_layout.addWidget(row)

        # 异步加载图标
        self._load_icons()

    def _load_icons(self):
        """为列表中的应用异步加载图标"""
        from services.install_monitor import find_lnk_by_name
        from services.app_info import get_app_info

        theme = "dark" if self.dark else "light"
        for name in self.apps:
            lnk = find_lnk_by_name(name)
            if not lnk:
                continue
            info = get_app_info(lnk)
            if not info or not info.get("path"):
                continue
            # 用独立 dict 作为标识，回调时按 id 定位 label
            self._icon_map[id(info)] = name
            self.icon_loader.load(info, size=24, is_folder=False, theme=theme)

    def _on_icon_ready(self, app_data: dict, pixmap):
        """图标就绪：填充到对应行"""
        name = self._icon_map.get(id(app_data))
        if not name:
            return
        label = self.icon_labels.get(name)
        if label is None:
            return
        import shiboken6
        if not shiboken6.isValid(label):
            return
        target = label.width()
        if target > 0 and pixmap.width() != target:
            pixmap.setDevicePixelRatio(pixmap.width() / target)
        label.setPixmap(pixmap)

    def _selected(self) -> list[str]:
        return [name for name, cb in self.checkboxes.items() if cb.isChecked()]

    def _update_count(self):
        selected = len(self._selected())
        self.count_label.setText(
            f"共 {len(self.apps)} 个 · 已添加 {self.added_count} 个 · 已选中 {selected} 个"
        )
        self.add_btn.setEnabled(selected > 0)

    def _select_all(self):
        for cb in self.checkboxes.values():
            cb.setChecked(True)

    def _deselect_all(self):
        for cb in self.checkboxes.values():
            cb.setChecked(False)

    def _batch_add(self):
        """批量添加选中应用到指定分类"""
        from services.install_monitor import find_lnk_by_name
        from services.app_info import get_app_info

        selected = self._selected()
        if not selected:
            return
        cat = self.cat_combo.currentText()
        added = 0
        skipped = 0
        for name in selected:
            lnk = find_lnk_by_name(name)
            if not lnk:
                skipped += 1
                continue
            info = get_app_info(lnk)
            if not info or not info.get("path"):
                skipped += 1
                continue
            if self.config.add_app(cat, info):
                added += 1
            else:
                skipped += 1

        self.config.save()
        self.main_window._card_cache.pop(cat, None)
        if cat == self.config.current_category:
            self.main_window._refresh_grid()
        self.main_window.show_message(f"成功添加 {added} 个，跳过 {skipped} 个已存在")
        self.accept()
