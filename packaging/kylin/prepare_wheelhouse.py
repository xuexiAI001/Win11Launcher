#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在**联网机器**（你的 Windows 开发机即可）上预下载麒麟离线安装所需的全部 wheel。

麒麟机器离网，无法现场 pip install；本脚本把依赖闭包（requirements-linux.txt）
按目标架构提前下载到本地 wheelhouse，随后随项目一起拷到麒麟机器，
由 build_on_kylin.sh 以 `--no-index` 方式离线安装。

用法（在项目任意目录下执行均可）：
    python packaging/kylin/prepare_wheelhouse.py                  # 下载 x86_64 + aarch64 两架构
    python packaging/kylin/prepare_wheelhouse.py --arch x86_64    # 只下载本机对应架构（体积减半）
    python packaging/kylin/prepare_wheelhouse.py --arch aarch64   # 飞腾 / 鲲鹏

国内网络直连 pypi.org 可能很慢（大轮子仅十几 KB/s），可改用镜像，例如：
    python packaging/kylin/prepare_wheelhouse.py \
        --index-url https://mirrors.aliyun.com/pypi/simple
（阿里云 / 腾讯云 / 华为云 / USTC 镜像均可；
 注意：清华 TUNA 镜像会拦截 pip 客户端（返回 403），不要使用）

产物：packaging/kylin/wheelhouse/<arch>/*.whl（约 150 MB / 架构）

说明：
  - 本脚本自身兼容 Python 3.8+，在 Windows / Linux 上行为一致；
  - 下载使用 pip 的交叉平台能力（--platform + --python-version），
    不会安装到当前环境，只落盘 wheel；
  - wheelhouse 体积较大，不纳入 git，请用 U 盘/内网拷贝整目录。
"""

import argparse
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_REQS = SCRIPT_DIR / "requirements-linux.txt"

# 目标架构 → pip 平台标签。
# x86_64：麒麟 glibc 2.31，manylinux_2_28 轮子可运行；附 manylinux2014 以覆盖
#         PyInstaller 等仍发布 manylinux2014 轮子的包（pip 允许一个 wheel
#         的任一平台标签命中给定的 --platform 之一）。
# aarch64：麒麟 ARM64（飞腾/鲲鹏）glibc 2.31，PySide6 6.6.3.1 的 arm64 轮子
#          恰为 manylinux_2_31。
ARCH_PLATFORMS = {
    "x86_64": ["manylinux_2_28_x86_64", "manylinux2014_x86_64"],
    "aarch64": ["manylinux_2_31_aarch64", "manylinux2014_aarch64"],
}


def download_arch(arch: str, py_version: str, reqs: Path, out_root: Path,
                  index_url: str) -> bool:
    platforms = ARCH_PLATFORMS[arch]
    out_dir = out_root / arch
    out_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, "-m", "pip", "download",
        "--disable-pip-version-check",
        "--no-deps",                     # requirements-linux.txt 已是完整闭包
        "--only-binary=:all:",           # 离线机器无法编译 sdist，只要 wheel
        "--python-version", py_version,
        "--index-url", index_url,
    ]
    for p in platforms:
        cmd += ["--platform", p]
    cmd += ["-r", str(reqs), "-d", str(out_dir)]

    print(f"[wheelhouse] 架构 {arch}（平台标签 {' / '.join(platforms)}，Python {py_version}）")
    print(f"[wheelhouse] 输出目录：{out_dir}")
    print(f"[wheelhouse] 执行：{' '.join(cmd)}\n")
    proc = subprocess.run(cmd)
    if proc.returncode != 0:
        print(f"\n[wheelhouse] 错误：{arch} 下载失败（pip 退出码 {proc.returncode}）")
        return False

    wheels = sorted(out_dir.glob("*.whl"))
    total_mb = sum(w.stat().st_size for w in wheels) / 1024 / 1024
    print(f"\n[wheelhouse] {arch} 完成：{len(wheels)} 个 wheel，共 {total_mb:.1f} MB")
    for w in wheels:
        print(f"    - {w.name} ({w.stat().st_size / 1024 / 1024:.1f} MB)")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="预下载麒麟离线安装所需的 wheelhouse（在联网机器上运行）"
    )
    parser.add_argument(
        "--arch",
        choices=["x86_64", "aarch64", "both"],
        default="both",
        help="目标架构，默认 both（x86_64 + aarch64）",
    )
    parser.add_argument(
        "--python-version",
        default="38",
        help="目标 Python 版本（麒麟为 3.8），默认 38。若改动需同步调整 "
             "requirements-linux.txt 中的版本锁",
    )
    parser.add_argument(
        "--reqs",
        type=Path,
        default=DEFAULT_REQS,
        help="依赖清单路径，默认取本脚本同目录的 requirements-linux.txt",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=SCRIPT_DIR / "wheelhouse",
        help="wheelhouse 输出根目录，默认 packaging/kylin/wheelhouse",
    )
    parser.add_argument(
        "--index-url",
        default="https://pypi.org/simple",
        help="pip 索引源，默认官方 PyPI。国内慢速网络可用阿里云镜像："
             "https://mirrors.aliyun.com/pypi/simple",
    )
    args = parser.parse_args()

    if not args.reqs.is_file():
        print(f"错误：找不到依赖清单 {args.reqs}")
        return 2

    arches = ["x86_64", "aarch64"] if args.arch == "both" else [args.arch]
    ok = True
    for arch in arches:
        ok = download_arch(arch, args.python_version, args.reqs, args.out,
                           args.index_url) and ok

    if not ok:
        return 1

    print("\n[wheelhouse] 全部完成。接下来：")
    print("  1. 将整个项目目录（含 packaging/kylin/wheelhouse）拷贝到麒麟机器（U 盘/内网）")
    print("  2. 在麒麟机器上执行：bash packaging/kylin/build_on_kylin.sh")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
