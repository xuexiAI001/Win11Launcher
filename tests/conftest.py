# -*- coding: utf-8 -*-
"""pytest 全局夹具：隔离测试对用户真实数据的写入。

历史教训（2026-10-31）：
  测试用例曾直接调用 AppOpsMixin._move_app_to_category()，该方法内部会执行
  `config.save()`，于是在 offscreen 测试环境下把构造的假数据写进了用户真实的
  %APPDATA%\\Win11Launcher\\launcher_config.json，覆盖了用户启动台中原有的应用。

此后所有测试必须通过本夹具把配置文件重定向到临时目录：无论测试怎么 save()，
都只会写到 pytest 的 tmp_path，绝不碰用户的真实配置。
"""
import os

# 必须在任何 PySide 模块导入前设置，避免连接显示器
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

import core.config as config_mod
import core.constants as constants_mod


def pytest_configure(config):
    """注册 real_paths 标记：标记过的用例可访问真实路径常量（不做隔离）"""
    config.addinivalue_line(
        "markers",
        "real_paths: 允许访问真实路径/配置常量（用于校验路径解析自身的测试）",
    )


@pytest.fixture(autouse=True)
def isolate_real_config(request, tmp_path, monkeypatch):
    """把配置文件重定向到临时目录（自动应用于每一个测试用例）。

    core.config 中的 load()/save()/export_to()/import_from() 都引用模块级
    CONFIG_FILE，因此这里 patch core.config 的绑定即可生效。

    例外：被 @pytest.mark.real_paths 标记的用例（如校验
    constants.CONFIG_FILE 是否指向真实目录）需要真实常量，跳过隔离。
    """
    if request.node.get_closest_marker("real_paths") is not None:
        yield
        return
    tmp_cfg = tmp_path / "launcher_config.json"
    monkeypatch.setattr(constants_mod, "CONFIG_FILE", str(tmp_cfg))
    monkeypatch.setattr(config_mod, "CONFIG_FILE", str(tmp_cfg))
    yield
