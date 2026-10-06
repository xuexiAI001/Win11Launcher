# -*- coding: utf-8 -*-
"""
模块名：core.config
职责：配置的加载/保存/导出/导入，原子写入 + .bak 备份
依赖：core.constants, core.logger
"""

import os
import json
import shutil
from typing import Any

from core.constants import CONFIG_FILE, DEFAULT_CATEGORIES, WINDOW_ALPHA_DEFAULT, THEME_SYSTEM
from core.logger import get_logger

logger = get_logger()


class Config:
    """应用配置：应用列表、分类、透明度、主题"""

    def __init__(self):
        self.app_config: dict[str, list[dict]] = {}
        self.categories: list[str] = list(DEFAULT_CATEGORIES)
        self.alpha: float = WINDOW_ALPHA_DEFAULT
        self.theme: str = THEME_SYSTEM
        self.minimize_to_tray: bool = True
        self.current_category: str = self.categories[0]
        self._init_defaults()

    def _init_defaults(self):
        """初始化默认结构"""
        for cat in self.categories:
            self.app_config.setdefault(cat, [])

    # ------------------------------------------------------------
    # 加载 / 保存
    # ------------------------------------------------------------
    def load(self) -> None:
        """从文件加载配置"""
        try:
            os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
            if not os.path.exists(CONFIG_FILE):
                logger.debug(f"配置文件不存在，使用默认配置: {CONFIG_FILE}")
                return

            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)

            loaded = data.get("app_config", {})
            if isinstance(data.get("categories"), list) and data["categories"]:
                self.categories = data["categories"]

            for cat in self.categories:
                self.app_config.setdefault(cat, [])
                if isinstance(loaded.get(cat), list):
                    self.app_config[cat] = loaded[cat]

            if "alpha" in data:
                try:
                    self.alpha = float(data["alpha"])
                except (TypeError, ValueError):
                    pass

            if "theme" in data:
                self.theme = data["theme"]

            if "minimize_to_tray" in data:
                self.minimize_to_tray = bool(data["minimize_to_tray"])

            if self.current_category not in self.categories:
                self.current_category = self.categories[0]

            logger.debug(f"配置已加载: {CONFIG_FILE}")
        except Exception as e:
            logger.warning(f"加载配置失败: {e}")

    def save(self) -> None:
        """保存配置（原子写入 + 备份）"""
        try:
            os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
            data = {
                "app_config": self.app_config,
                "categories": self.categories,
                "alpha": self.alpha,
                "theme": self.theme,
                "minimize_to_tray": self.minimize_to_tray,
            }
            tmp_path = CONFIG_FILE + '.tmp'
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, CONFIG_FILE)
            try:
                shutil.copy2(CONFIG_FILE, CONFIG_FILE + '.bak')
            except Exception:
                pass
            logger.debug(f"配置已保存: {CONFIG_FILE}")
        except Exception as e:
            logger.warning(f"保存配置失败: {e}")

    # ------------------------------------------------------------
    # 导出 / 导入
    # ------------------------------------------------------------
    def export_to(self, path: str) -> bool:
        """导出配置到指定文件"""
        try:
            import time
            data = {
                "version": "1.0",
                "export_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "app_config": self.app_config,
                "categories": self.categories,
                "alpha": self.alpha,
                "theme": self.theme,
                "minimize_to_tray": self.minimize_to_tray,
            }
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.debug(f"配置已导出: {path}")
            return True
        except Exception as e:
            logger.warning(f"导出配置失败: {e}")
            return False

    def import_from(self, path: str) -> bool:
        """从指定文件导入配置"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data.get("categories"), list) and data["categories"]:
                self.categories = data["categories"]
            self.app_config = {}
            loaded = data.get("app_config", {})
            for cat in self.categories:
                self.app_config[cat] = loaded.get(cat, []) if isinstance(loaded.get(cat), list) else []
            if "alpha" in data:
                try:
                    self.alpha = float(data["alpha"])
                except (TypeError, ValueError):
                    pass
            if "theme" in data:
                self.theme = data["theme"]
            if "minimize_to_tray" in data:
                self.minimize_to_tray = bool(data["minimize_to_tray"])
            if self.current_category not in self.categories:
                self.current_category = self.categories[0]
            logger.debug(f"配置已导入: {path}")
            return True
        except Exception as e:
            logger.warning(f"导入配置失败: {e}")
            return False

    # ------------------------------------------------------------
    # 分类操作
    # ------------------------------------------------------------
    def add_category(self, name: str) -> bool:
        """添加分类"""
        name = name.strip()
        if not name or name in self.categories:
            return False
        self.categories.append(name)
        self.app_config[name] = []
        return True

    def rename_category(self, old: str, new: str) -> bool:
        """重命名分类"""
        new = new.strip()
        if not new or new in self.categories or old not in self.categories:
            return False
        idx = self.categories.index(old)
        self.categories[idx] = new
        self.app_config[new] = self.app_config.pop(old, [])
        if self.current_category == old:
            self.current_category = new
        return True

    def delete_category(self, name: str) -> bool:
        """删除分类（第一个分类不可删）"""
        if name not in self.categories or self.categories.index(name) == 0:
            return False
        self.categories.remove(name)
        self.app_config.pop(name, None)
        if self.current_category == name:
            self.current_category = self.categories[0]
        return True

    # ------------------------------------------------------------
    # 应用操作
    # ------------------------------------------------------------
    def get_apps(self, category: str) -> list[dict]:
        """获取某分类的应用列表"""
        return self.app_config.get(category, [])

    def add_app(self, category: str, app: dict) -> bool:
        """添加应用（按 path 去重）"""
        apps = self.app_config.setdefault(category, [])
        path = app.get("path", "")
        if any(a.get("path") == path for a in apps):
            return False
        apps.append(app)
        return True

    def remove_app(self, category: str, app: dict) -> bool:
        """删除应用（按 path 匹配，回退按 name）"""
        apps = self.app_config.get(category, [])
        path = app.get("path", "")
        for i, a in enumerate(apps):
            if a.get("path") == path or (not path and a.get("name") == app.get("name")):
                apps.pop(i)
                return True
        return False

    def get_folders(self, category: str) -> list[dict]:
        """获取某分类下的所有文件夹"""
        return [a for a in self.app_config.get(category, []) if a.get("type") == "folder"]
