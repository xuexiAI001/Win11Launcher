# -*- coding: utf-8 -*-
"""Python 3.8 兼容守卫。

背景：麒麟 V10 桌面版自带 Python 3.8.10/3.8.2（官方白皮书数据），
源码必须能在 3.8 上直接 import。两类风险：

1. 语法层：PEP 604 联合类型（`X | None`）、match 语句等 3.10+ 语法；
   `ast.parse(feature_version=(3, 8))` 可直接拒绝。
2. 注解求值层：内置泛型（`list[str]` 等）与 PEP 604 在 3.8 上是**合法语法**，
   但函数签名/属性注解会在定义时求值而崩溃 —— 必须依赖
   `from __future__ import annotations` 惰性化。
3. 运行时 API 层：functools.cache、str.removeprefix 等 3.9+ API 黑名单。

本测试在开发机（高版本 Python）上运行，替麒麟机器提前把守兼容性。
"""

import ast
import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 不参与扫描的目录（构建产物 / 缓存 / VCS / 记忆库）
EXCLUDE_DIRS = {
    "build", "dist", "build_new", "dist_new", "__pycache__",
    ".git", ".workbuddy", "wheelhouse", "venv",
}

# 3.9+ 才有的运行时 API：在 3.8 上 import 或调用即失败
FORBIDDEN_APIS = [
    (r"\bfunctools\.cache\b", "functools.cache 需要 Python 3.9+"),
    (r"\.removeprefix\(", "str.removeprefix 需要 Python 3.9+"),
    (r"\.removesuffix\(", "str.removesuffix 需要 Python 3.9+"),
    (r"\bmath\.lcm\b", "math.lcm 需要 Python 3.9+"),
    (r"\bgraphlib\b", "graphlib 需要 Python 3.9+"),
    (r"\bzoneinfo\b", "zoneinfo 需要 Python 3.9+"),
    (r"\basyncio\.to_thread\b", "asyncio.to_thread 需要 Python 3.9+"),
]

# 3.9+ 类型注解写法（在 3.8 定义时求值会崩溃，需 future import 惰性化）
MODERN_ANNOTATION = re.compile(
    r"(?::\s*|->\s*)(?:list|dict|tuple|set|frozenset|type)\["
    r"|\|\s*(?:None|str|int|float|bool|bytes|dict|list|tuple)\b"
)


def _iter_py_files():
    self_name = Path(__file__).name
    for p in sorted(PROJECT_ROOT.rglob("*.py")):
        if EXCLUDE_DIRS & set(p.parts):
            continue
        if p.name == self_name:
            continue  # 守卫文件自身包含黑名单字样，跳过自扫描
        yield p


def test_all_files_parse_as_py38():
    """所有源码必须能按 Python 3.8 语法解析。"""
    bad = []
    scanned = 0
    for p in _iter_py_files():
        scanned += 1
        src = p.read_text(encoding="utf-8")
        try:
            ast.parse(src, filename=str(p), feature_version=(3, 8))
        except SyntaxError as e:
            bad.append(f"{p.relative_to(PROJECT_ROOT)}:{e.lineno}: {e.msg}")
    assert scanned > 20, f"扫描范围异常，仅覆盖 {scanned} 个文件"
    assert not bad, "以下文件包含 Python 3.8 不支持的语法（麒麟 python3.8 无法 import）：\n" + "\n".join(bad)


def test_no_python39_plus_runtime_apis():
    """禁止使用 3.9+ 才有的运行时 API。"""
    bad = []
    for p in _iter_py_files():
        src = p.read_text(encoding="utf-8")
        for pattern, reason in FORBIDDEN_APIS:
            for m in re.finditer(pattern, src):
                line = src[: m.start()].count("\n") + 1
                bad.append(f"{p.relative_to(PROJECT_ROOT)}:{line}: {reason}")
    assert not bad, "\n".join(bad)


def test_modern_annotations_have_future_import():
    """使用 3.9+ 注解写法的文件必须引入 from __future__ import annotations。

    Python 3.8 上 `list[str]` / `X | None` 会在函数定义或属性注解赋值时
    立即求值并抛 TypeError；future import 将其惰性化为字符串，
    是同时兼容 3.8~3.13 的最小改动。
    """
    bad = []
    for p in _iter_py_files():
        src = p.read_text(encoding="utf-8")
        if MODERN_ANNOTATION.search(src):
            if "from __future__ import annotations" not in src:
                first = src[: MODERN_ANNOTATION.search(src).start()].count("\n") + 1
                bad.append(
                    f"{p.relative_to(PROJECT_ROOT)}:{first}: 使用 3.9+ 注解但缺少 "
                    "`from __future__ import annotations`"
                )
    assert not bad, "\n".join(bad)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
