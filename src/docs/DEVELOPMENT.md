# 开发与目录

```text
build.py                 命令行入口
First-Flash.ps1          从纯官方 1.0.98 开启 SSH 到网页升级准备
config/                  可直接编辑的功能组合
firmware/community-2.1/   社区版成品、配置与真实离线报告
src/
  rd03/                  Python 构建器、格式解析与补丁
  payloads/              固件内运行文件及摘要清单 manifest.json
  sources/               SSH C 源码、WOL Go 源码、上游来源记录
  scripts/               网页升级准备、运行程序编译与验收辅助
  tests/                 离线回归测试
  docs/                  实现、刷入、验收范围
  licenses/              第三方许可
  THIRD_PARTY_NOTICES.md  第三方说明
.work/                   本地工作材料，全部不进 Git
  cache/                 官方 ROM、工具链、下载材料
  venv/                  Python 虚拟环境
  build/                 构建中间文件
  output/                新构建结果
```

以上路径均相对于仓库根目录。`src/payloads/manifest.json` 中的 `source` 路径相对于 `src/`，因此清单仍使用 `payloads/...`。运行文件里的 `/data/...`、`/usr/...` 是路由器路径，与仓库整理无关。

固件构建依赖官方 ROM、仓库内版本锁定的 payload 以及 squashfs-tools-ng。不依赖开发者的临时目录、SSH 密码、个人订阅或已定制的旧固件。输出校验报告记录每次真实使用的配置和改动。

`First-Flash.ps1` 是独立的联机准备入口，不属于离线构建器。它使用锁定摘要的外部 XMiR-Patcher 快照及 `src/scripts/unlock-stock-ssh.py` 适配器，仅调用已限定的 RD03 1.0.98 智能场景开启方法。外部下载、运行时和会话目录只保存在 `.work/`，不进入源码或成品。快照来源与边界见 `src/sources/upstream.json` 和刷入说明。

## 本地构建工具

Python 依赖版本在 `requirements.txt`。推荐使用独立虚拟环境。Windows 已使用 squashfs-tools-ng 1.3.2 验证；下载工具时保留其动态库，指定 `--tools-dir` 可指向整个解压目录。

原生工具不会随源码被重新编译，Windows 工具和 Python 虚拟环境不提交到 Git。Linux/macOS 用户需自行安装兼容的 `sqfs2tar`/`tar2sqfs`；本次只做 Windows 完整构建，不宣称其他平台已验收。

源码相同、输入相同、配置相同、工具链相同时应能重复构建；更换压缩库/工具版本可能改变压缩后的摘要。

## 编译项目自己的运行程序

WOL 后端只依赖 Go 标准库，先运行源码测试，再交叉编译 Linux ARM64：

```powershell
python src/scripts/build-runtime.py wol
```

需要 Go 1.22+ 在 PATH。结果在 `.work/build/runtime/rd03-wol-api`，不会自动替换已锁定的 ROM payload。

SSH 桥可用 Zig 或适配原厂 ABI 的 AArch64 musl 编译器构建：

```powershell
python src/scripts/build-runtime.py ssh --cc zig
```

结果在 `.work/build/runtime/rd03-admin-auth.so`。对应 C 文件标记为 0BSD；Lua 口令检查和密钥准备程序在 `src/payloads/ssh/` 中。仓库默认使用已验证摘要的历史二进制。换编译器后即使源码一致，也必须重新验证 ELF 依赖、目标 libc/Dropbear 的 ABI、实际口令验证和 SFTP，不能只因“编译成功”就刷入。

手动修改运行文件后，需重新审查并更新 `src/payloads/manifest.json` 的 `sha256`、`bytes` 和权限，否则构建器会拒绝输入。Mihomo 版本还与准备脚本中的摘要/版本白名单、ShellCrash 模板相互约束，不能只替换一个核心文件。

ShellCrash 与其衍生模板受上游 GPLv3 许可约束。Mihomo、MRS 和 SFTP 组件的来源、许可与版本见 `src/sources/upstream.json`、`src/sources/sftp/packages.json` 和[第三方说明](../THIRD_PARTY_NOTICES.md)，不把这些二进制误标为本项目 MIT 代码。

## 扩展其他官方版本

当前构建器主动拒绝未知输入。新增版本至少需要：解析新包并核查分区几何/容量、比较内核与启动链、重审 Dropbear/口令存储/升级校验 ABI、审查 LuCI 路由与模板差异、重新固定所有补丁输入和输出摘要，再做有恢复条件的真机验证。

不要仅把 `STOCK_SHA256` 换成另一份 ROM 的摘要。RD03v2/RD23 也不能靠改文件名或放开型号检查获得兼容性。

## 公开与发布

`.gitignore` 排除了缓存、虚拟环境、新产物、常见订阅 YAML、环境文件和私钥。本仓库提供社区版 2.1 成品；发布新版本时带上 `SHA256SUMS`、配置及构建报告，注明验证范围。

项目远端为 [pansoul1/AX3000T](https://github.com/pansoul1/AX3000T)。公开内容包含源码、配置、说明、许可和社区版 2.1 成品；`.work/` 中的运行环境、下载缓存与临时记录不上传。原厂固件和厂商文件不因为放入仓库就成为本项目的 MIT 开源代码。
