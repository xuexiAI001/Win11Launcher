# Win11Launcher 麒麟（银河麒麟 V10）离线构建套件

本目录提供一套**完全离线**的打包流程：在联网的 Windows 开发机上下载依赖 wheelhouse，
随项目一起拷贝到离线的麒麟机器，在麒麟机器上构建出可直接运行的目录和 `.deb` 安装包。

```
联网 Windows 机器                麒麟机器（离线）
─────────────────────           ─────────────────────
prepare_wheelhouse.py    ──USB──▶  build_on_kylin.sh ──▶ dist-linux/Win11Launcher/
（下载两架构 wheelhouse）                    │
                                            └──▶ make_deb.sh ──▶ win11launcher_1.1.0_amd64.deb
                                                                          │
                                                              sudo dpkg -i ──▶ 桌面菜单可用
```

---

## 一、环境结论（版本锁定的依据）

麒麟 V10 桌面版官方白皮书关键数据与本套件的选型：

| 项目 | 麒麟 V10 实际情况 | 本套件选型 |
| --- | --- | --- |
| 系统 Python | **3.8.10 / 3.8.2** | 全部依赖锁 cp38；源码已按 3.8 兼容（测试守卫 `tests/test_py38_compat.py`） |
| glibc（x86_64） | 2.31 | PySide6 轮子 `manylinux_2_28`（≤2.31 可运行） |
| glibc（ARM64 飞腾/鲲鹏） | 2.31 | PySide6 轮子 `manylinux_2_31` |
| glibc（龙芯 3A5000/3A6000、SW831） | 2.28 | **LoongArch64 无 PySide6 官方轮子，暂不支持**（见第六节） |
| Qt | 系统自带 Qt5，但本程序用 Qt6 | **不依赖系统 Qt**：PySide6 6.6.3.1 轮子内置 Qt6，PyInstaller 一并打包 |

**为什么 PySide6 锁 6.6.3.1 而不是开发机的 6.11.2？**

- 6.11.2 的 Linux 轮子是 `manylinux_2_34`(x86_64) / `manylinux_2_39`(aarch64)，
  麒麟的 glibc 只有 2.31/2.28，**装不上**；
- 6.7 及以上只发布 cp39 轮子，**不支持 Python 3.8**；
- **6.6.3.1 是同时满足「cp38 + manylinux_2_28(x86_64) / manylinux_2_31(aarch64)」的最新版本**，
  且应用只用到长期稳定的 Qt API（窗口/信号/SVG 渲染/调色板），与 6.11.2 行为一致。

完整依赖闭包与逐项理由见 [`requirements-linux.txt`](requirements-linux.txt)。

---

## 二、快速开始（3 步）

### 第 1 步：在联网的 Windows 机器上下载 wheelhouse

```bash
# 在项目根目录（Win11Launcher/）执行，用你本机的 Python 即可
python packaging/kylin/prepare_wheelhouse.py
```

- 默认同时下载 **x86_64 + aarch64** 两架构（各约 150 MB，合计约 300 MB）；
- 确定目标机器架构后可只下一个，体积减半：
  `python packaging/kylin/prepare_wheelhouse.py --arch x86_64`
  （兆芯/海光/Intel/AMD 选 x86_64；飞腾/鲲鹏选 aarch64）；
- 国内网络直连 pypi.org 可能很慢（大轮子仅十几 KB/s），建议换镜像源：
  `python packaging/kylin/prepare_wheelhouse.py --index-url https://mirrors.aliyun.com/pypi/simple`
  （阿里云 / 腾讯云 / 华为云 / USTC 均可；**清华 TUNA 镜像会拦截 pip 客户端返回 403，不要使用**）；
- 产物：`packaging/kylin/wheelhouse/<arch>/*.whl`（该目录不入 git，用 U 盘/内网拷贝）；
- 同时会自动补齐 `packaging/kylin/tools/` 下的离线 pip 引导物料（缺失时，
  锁 pip 25.0.1——最后支持 Python 3.8 的版本；已存在则跳过）。

### 第 2 步：拷贝到麒麟机器并构建

把**整个项目目录**（含 `packaging/kylin/wheelhouse`）拷贝到麒麟机器（U 盘/内网），然后：

```bash
bash packaging/kylin/build_on_kylin.sh
```

脚本自动完成：架构检测 → wheelhouse 检查 → Python 3.8 校验 → 建 venv
（缺 ensurepip 时自动用 tools/ 的 pip wheel 经 zipimport 离线引导，无需 apt/root）→
离线装依赖（`--no-index`）→ 导入冒烟 → PyInstaller 打包 → 产物校验 → 无头冒烟运行。

成功后产物在 `dist-linux/Win11Launcher/`，可直接双击 `Win11Launcher` 运行。

### 第 3 步：打包并安装 .deb

```bash
bash packaging/kylin/make_deb.sh
sudo dpkg -i packaging/kylin/win11launcher_*.deb
```

安装后：桌面菜单搜索"Win11Launcher"即可启动；命令行可输入 `win11launcher`。
卸载：`sudo dpkg -r win11launcher`（保留配置）或 `sudo dpkg -P win11launcher`（含配置）。

---

## 三、目录说明

| 文件 | 作用 |
| --- | --- |
| `requirements-linux.txt` | 依赖完整闭包 + 版本锁定理由（`--no-deps` 离线安装） |
| `prepare_wheelhouse.py` | 联网机器上运行，交叉下载两架构 wheelhouse |
| `build_on_kylin.sh` | 麒麟机器上一键构建（venv + 离线安装 + PyInstaller + 校验） |
| `win11launcher.spec` | Linux 专用 PyInstaller 配置（排除 Windows 专有模块/numpy） |
| `make_deb.sh` | 把构建产物打成 `.deb`（/opt 安装 + 桌面入口 + hicolor 图标） |
| `win11launcher.desktop` | 桌面菜单入口文件 |
| `tools/` | 离线引导物料：`pip` wheel（ensurepip 缺失时挂 PYTHONPATH 经 zipimport 引导，**需随项目一起拷贝**） |
| `wheelhouse/` | （运行 prepare 后生成）离线安装源，**不入 git** |
| `.venv-build/` | （运行 build 后生成）构建用虚拟环境，**不入 git** |

---

## 四、常见问题

**Q1：报错 `ensurepip is not available` 或 `No module named pip`**
麒麟最小化安装缺少 venv 组件。**当前版本脚本已全自动处理，无需任何手动操作**：
ensurepip 不可用时会自动切换 `--without-pip` + 本地 `tools/pip-*.whl`
（挂 PYTHONPATH 经 zipimport 运行，与 get-pip.py 内部机制相同）离线引导安装 pip
（不需要 root、不需要 apt、不需要联网）。引导前会对 wheel 做 CRC 完整性校验——
若报"完整性校验失败"，说明该文件在 U 盘/传输中损坏，重新拷贝 `tools/` 即可。

若引导仍失败（极端情况），或使用旧版套件：
- 手动清理残骸后重跑：`rm -rf packaging/kylin/.venv-build`
- 有软件源时安装 venv 组件：`sudo apt-get update && sudo apt-get install python3.8-venv python3-pip`
  （提示"无法定位软件包"就换 `python3-3.8-venv`）；
- 确认 `packaging/kylin/tools/` 下的 `pip-*.whl` 已随项目一起拷贝。

**Q2：脚本报 `检测到 Python 3.x，但 wheelhouse 是按 Python 3.8 准备的`**
wheelhouse 里 Pillow 10.4.0 仅提供 cp38 轮子（最后一个支持 3.8 的 Pillow）。
二选一：① 用 `python3.8` 跑脚本（脚本会优先自动选用 `python3.8`）；
② 在联网机器上 `python packaging/kylin/prepare_wheelhouse.py --python-version 39`
重新生成，并同步修改 `requirements-linux.txt`（Pillow 换成支持该版本的版本，
PySide6 仍需带 `manylinux_2_28` 轮子的版本）。

**Q3：启动时提示缺少 `libxcb-*` / `libxkbcommon` 等库**
程序打包了 Qt 自身，但 Qt 的平台插件依赖系统 X 客户端库。UKUI 桌面环境必然自带；
若为最小化安装，补上：`sudo apt-get install libxcb-xkb1 libxcb-icccm4 libxkbcommon0 libfontconfig1 libdbus-1-3`。

**Q4：全局快捷键（热键）不生效**
- 快捷键依赖 X11 会话（UKUI 默认即为 X11）。**Wayland 会话下 pynput 无法注册全局热键**，
  程序会静默禁用该功能，其余功能不受影响；
- 可在设置里重新设置热键并重启程序。

**Q5：图标显示为默认图标**
程序通过 freedesktop 图标主题解析 `.desktop` 图标（含 SVG 渲染）。个别应用若只提供了
位图图标且尺寸过小，属正常现象；开始菜单扫描结果可在设置里手动"扫描应用列表"刷新。

**Q6：想先不打包，直接跑源码验证**
在麒麟机器上装好依赖后（build 脚本第 1~5 步等价操作），直接：
`bash -c 'cd <项目目录> && .venv/bin/python main.py'`。
注意源码方式需要图标/配置目录可写（默认用 `~/.config/Win11Launcher`）。

---

## 五、与 Windows 版本的关系

- Windows 版本**零改动**：所有 Linux 逻辑均按 `sys.platform` 分流，
  Windows 走原有代码路径（有测试保证委托函数同一性）；
- 新增能力（缩放/最大化/全屏/深浅色跟随）在 Windows 上同样可用；
- 本套件只影响 Linux 侧打包，不参与 Windows 的 `Win11LauncherQt.spec` 构建。

---

## 六、架构支持矩阵

| 架构 | 代表 CPU | 支持情况 |
| --- | --- | --- |
| x86_64 | 兆芯 ZX-C/KX-5000/KX-6000、海光、Intel/AMD | ✅ 完整支持（manylinux_2_28 轮子 + 本机构建） |
| aarch64 | 飞腾 FT-2000+/4、鲲鹏 920 | ✅ 完整支持（manylinux_2_31 轮子 + 本机构建） |
| LoongArch64 | 龙芯 3A5000/3A6000 | ❌ PySide6 官方无 LoongArch 轮子，且麒麟龙芯版 glibc 2.28 |
| MIPS64 | 龙芯 3A4000 | ❌ 同上，无轮子 |

龙芯用户如需支持，唯一路径是在龙芯麒麟机器上从源码编译 PySide6（需整套 Qt6 构建链，
耗时数小时且版本需手动对齐），不在本套件覆盖范围内。

---

## 七、已知限制

1. **构建必须在麒麟（或同 glibc 版本的 Linux）机器上进行**：PyInstaller 不能交叉编译，
   在 Windows 上无法产出 Linux 可执行文件；
2. wheelhouse 按 glibc 2.28/2.31 准备，在**更高版本 glibc** 的机器上同样可以构建
   （向前兼容），产物也能在麒麟上运行；
3. Wayland 会话全局热键不可用（见 Q4）；
4. 程序数据目录为 `~/.config/Win11Launcher`（XDG 规范），与 Windows 的
   `%APPDATA%\Win11Launcher` 互不相同，配置不互通。
