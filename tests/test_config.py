# -*- coding: utf-8 -*-
"""core.config 最小冒烟测试：分类/应用管理 + 配置导出/导入往返。

注意：本测试只覆盖 core.config 的纯内存逻辑，不读写用户真实配置
（launcher_config.json 位于 %APPDATA%），因此可安全重复运行。
"""
from core.config import Config


def _new_config():
    """构造一个干净的默认配置对象"""
    cfg = Config()
    cfg._init_defaults()
    return cfg


def test_default_categories():
    cfg = _new_config()
    assert cfg.categories == [
        "系统应用", "办公软件", "社交软件",
        "影音视频", "语言编程", "我的游戏",
    ]
    for cat in cfg.categories:
        assert cfg.get_apps(cat) == []


def test_add_category():
    cfg = _new_config()
    assert cfg.add_category("新分类") is True
    assert "新分类" in cfg.categories
    assert cfg.get_apps("新分类") == []
    # 重复 / 空名 / 纯空白名应失败
    assert cfg.add_category("新分类") is False
    assert cfg.add_category("") is False
    assert cfg.add_category("   ") is False


def test_rename_category():
    cfg = _new_config()
    cfg.add_app("系统应用", {"name": "A", "path": "C:/a.exe"})
    assert cfg.rename_category("系统应用", "系统") is True
    assert "系统" in cfg.categories
    assert "系统应用" not in cfg.categories
    # 应用应随分类迁移
    assert cfg.get_apps("系统") == [{"name": "A", "path": "C:/a.exe"}]
    # 重命名到已存在 / 不存在的应失败
    assert cfg.rename_category("系统", "办公软件") is False
    assert cfg.rename_category("不存在", "X") is False


def test_delete_category():
    cfg = _new_config()
    cfg.add_category("临时")
    # 第一个（默认）分类不可删
    assert cfg.delete_category("系统应用") is False
    assert cfg.delete_category("临时") is True
    assert "临时" not in cfg.categories


def test_add_app_dedup():
    cfg = _new_config()
    app = {"name": "A", "path": "C:/a.exe"}
    assert cfg.add_app("系统应用", app) is True
    # path 去重
    assert cfg.add_app("系统应用", dict(app)) is False
    assert len(cfg.get_apps("系统应用")) == 1


def test_remove_app():
    cfg = _new_config()
    cfg.add_app("系统应用", {"name": "A", "path": "C:/a.exe"})
    cfg.add_app("系统应用", {"name": "B", "path": "C:/b.exe"})
    assert cfg.remove_app("系统应用", {"name": "A", "path": "C:/a.exe"}) is True
    assert len(cfg.get_apps("系统应用")) == 1
    # path 为空时回退按 name 匹配
    assert cfg.remove_app("系统应用", {"name": "B", "path": ""}) is True
    assert cfg.get_apps("系统应用") == []


def test_get_folders():
    cfg = _new_config()
    cfg.add_app("系统应用", {"name": "文件夹", "type": "folder", "apps": []})
    cfg.add_app("系统应用", {"name": "普通", "path": "C:/x.exe"})
    folders = cfg.get_folders("系统应用")
    assert len(folders) == 1
    assert folders[0]["name"] == "文件夹"


def test_export_import_roundtrip(tmp_path):
    cfg = _new_config()
    cfg.add_app("系统应用", {"name": "A", "path": "C:/a.exe"})
    cfg.add_category("自定义")
    cfg.alpha = 0.8
    cfg.theme = "深色"
    cfg.minimize_to_tray = False

    out = tmp_path / "cfg_export.json"
    assert cfg.export_to(str(out)) is True
    assert out.exists()

    other = Config()
    assert other.import_from(str(out)) is True
    assert other.get_apps("系统应用") == [{"name": "A", "path": "C:/a.exe"}]
    assert "自定义" in other.categories
    assert other.alpha == 0.8
    assert other.theme == "深色"
    assert other.minimize_to_tray is False


def test_import_from_missing_file():
    other = Config()
    assert other.import_from("C:/no/such/file.json") is False
