# 小米 AX3000T · pansoul 定制固件

基于 **小米 AX3000T RD03 官方 1.0.98** 的离线定制工具与 pansoul 2.1 历史成品。保留官方系统主体，按需加入 SSH、SFTP、原生后台 WOL 和带内存保护的 ShellCrash。

项目仓库：[pansoul1/AX3000T](https://github.com/pansoul1/AX3000T)。

本项目不是小米官方项目，也不是完整的 OpenWrt 源码工程。构建器修改用户自行取得的官方 ROM，重新生成未获小米签名的系统升级包。**仅支持已锁定 SHA256 的 RD03 1.0.98，不支持 RD03v2、新版 AX3000T、RD23 或其他版本的 ROM。**

## 目录怎么用

根目录的主要文件夹只有三个：

```text
config/       改功能开关、自定义版本文字
src/          构建源码、运行文件、辅助脚本、详细说明与许可
firmware/     pansoul 2.1 成品、校验值和验证报告
README.md     使用说明
build.py      统一构建入口
First-Flash.ps1  纯官方系统首次刷入准备
```

日常只需看本页、编辑 `config/` 或取用 `firmware/`。下载缓存、Python 环境、中间文件和新构建结果统一放在 `.work/`，不提交 Git；`.github/` 用于自动检查。源码内部目录见[开发说明](src/docs/DEVELOPMENT.md)。

## 直接使用 2.1 成品

- [RD03-1.0.98-pansoul2.1-web.bin](firmware/pansoul-2.1/RD03-1.0.98-pansoul2.1-web.bin)
- [SHA256SUMS](firmware/pansoul-2.1/SHA256SUMS)
- [成品说明与验证范围](firmware/pansoul-2.1/README.md)

这个文件是原样归档的 2.1 成品，SHA256：

```text
d3a3709631bf41858ca96845e4da22e5f2f17c07faee41dc8a47b8f7ece0997f
```

**纯官方系统默认没有 SSH，后台也不能直接通过定制包的签名检查。** 首次刷入请使用下面的 PS 入口；已运行 2.1 内置校验器的设备可以直接在后台手动上传同机型的正确系统包。详见[刷入与恢复](src/docs/FLASHING.md)。`build.py` 只做离线构建，`First-Flash.ps1` 则会连接指定的路由器做准备。

## 纯官方系统第一次怎么刷

先完成小米后台初始化，电脑接路由器 LAN 或其 Wi-Fi，确认可以访问后台。安装 Python 3.10+ 和 Windows OpenSSH 或 Git，在仓库根目录执行：

```powershell
git clone https://github.com/pansoul1/AX3000T.git
cd AX3000T
```

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\First-Flash.ps1" -Router 192.168.31.1
```

这条命令默认使用仓库里的 2.1 成品，执行顺序为：

1. 准备本地 Python 依赖；缺少官方基线 ROM 时从固定小米 CDN 下载并核对 SHA256，再检查定制包格式、机型、CRC 和内核。
2. 如果 22 端口已有 SSH，就跳过开启步骤；否则下载并核对固定版本的外部 XMiR-Patcher，调用 `smartcontroller/connect5` 方法。按隐藏提示输入**当前小米网页登录密码**，只接受 RD03 1.0.98。
3. 上游开启过程中会短暂设置 SSH 口令为 `root`；适配器立即通过加密 SSH 标准输入改为刚才的网页登录密码，并验证登录。失败则停止，不继续 ROM 准备。
4. 运行已有 `Prepare-WebUpgrade.ps1`，临时绑定原生 ROM 校验器补丁。按提示输入**当前可用的 SSH 密码**；刚成功开启时即网页登录密码，旧 SSH 则使用原先的密码。
5. 看到 `READY` 后，保持路由器运行，在小米后台手动上传显示路径对应的 `.bin`。

**PS 入口不会替你刷写或重启。** SSH 开启依赖该官方版本的接口，不能保证每台设备都成功；本次只做脚本离线与模拟检查，首次开启链路尚未新增真机验收。若失败，保留报错，不应继续上传。涉及的时间/智能场景/NVRAM 变更和详细边界见[首次准备说明](src/docs/FLASHING.md#首次从纯官方-1098-刷入)。

使用自己的新包、已有官方 ROM 或已有 SSH 时，可传入对应参数：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\First-Flash.ps1" -Router 192.168.31.1 -Rom ".\miwifi_rd03_firmware_48abd_1.0.98.bin" -Firmware ".\自己的定制包.bin" -SkipSshUnlock
```

`-SkipSshUnlock` 表示已有可用 SSH；没有 SSH 时不要加。`-CheckOnly` 只检查本地官方 ROM 与定制包，不下载、不连接路由器，也不执行开启 SSH 或放行校验的步骤。

## 可以选哪些功能

| 配置项 | 默认 | 作用与边界 |
| --- | --- | --- |
| `ssh` | 开 | 启用原厂 Dropbear，用户名 `root`，密码跟随当前小米网页登录密码；不内置固定密码 |
| `sftp` | 开 | 补充 SFTP 子系统，使用同一个 SSH 端口和账号；依赖 `ssh` |
| `wol` | 开 | 在原生小米后台增加“远程开机”标签，保存、删除设备并发送唤醒包 |
| `shellcrash` | 开 | 预置 ShellCrash 1.9.4、Mihomo 1.19.17、精简 MRS 规则与内存保护；依赖 `ssh` |
| `custom_web_upgrade` | 开 | 修改原生 ROM 校验器的 RSA 判断，便于以后从后台升级定制包；仍检查机型、格式与 CRC |
| `branding` | `pansoul 定制版本 2.1` | 自定义网页底部的版本文字和构建标记；不伪改官方更新元数据 |

ShellCrash 的“预置”指程序和离线安装材料在 ROM 中。第一次执行 `crash` 时安装脚本到 `/data`，**不会因此自动启动代理**，也不提供节点、订阅或 YAML。核心从只读 ROM 运行，不再把约 29.5 MiB 的核心展开到 `/tmp`。

关闭某个功能会从新生成的 ROM 中排除对应程序和入口。已有 `/data` 中的旧插件、启动项和配置不由离线构建器删除；因此关闭开关不等于卸载设备上过去安装的插件。

## 自己构建

需要 Python 3.10+、[squashfs-tools-ng 1.3.2](https://github.com/AgentD/squashfs-tools-ng/releases/tag/v1.3.2) 的 `sqfs2tar` 与 `tar2sqfs`。Windows 原生构建已检查；Linux 的相同工具链路径受支持，但本次没有 Linux 完整构建实测。不是传统 `squashfs-tools` 的 `mksquashfs` 命令。

在仓库根目录执行：

```powershell
python -m venv .work/venv
.\.work\venv\Scripts\python.exe -m pip install -r requirements.txt
```

准备官方 ROM，可从固定地址下载：

```powershell
Invoke-WebRequest -Uri "https://cdn.cnbj1.fds.api.mi-img.com/xiaoqiang/rom/rd03/miwifi_rd03_firmware_48abd_1.0.98.bin" -OutFile "miwifi_rd03_firmware_48abd_1.0.98.bin"
Get-FileHash ".\miwifi_rd03_firmware_48abd_1.0.98.bin" -Algorithm SHA256
```

必须匹配：

```text
042ba08949e547007710caa43830e574a7a7f5964119af4c457409b2fa8b4bce
```

也可以显式运行 `python build.py fetch-stock`，下载结果放在 `.work/cache/`。构建命令不会偷偷下载或替换依赖。上面的版本是本项目已验证的基线，不代表小米最新版本。

将官方工具包解压到 `.work/cache/tools/`，或者通过 `--tools-dir` 指定解压目录；也可把两个工具放入 PATH。工具需要其同目录的 DLL/动态库。先查看构建计划，再生成固件：

```powershell
.\.work\venv\Scripts\python.exe -X utf8 build.py plan --rom ".\miwifi_rd03_firmware_48abd_1.0.98.bin" --profile config/pansoul-2.1.json
.\.work\venv\Scripts\python.exe -X utf8 build.py build --rom ".\miwifi_rd03_firmware_48abd_1.0.98.bin" --profile config/pansoul-2.1.json --tools-dir "C:\Tools\squashfs-tools-ng" --output .work/output/my-build
```

输出目录必须尚不存在，避免覆盖其他构建。不传 `--output` 时默认使用 `.work/output/配置名称/`。产物包括：

```text
.work/output/my-build/
  RD03-1.0.98-pansoul-2.1-custom-web.bin
  SHA256SUMS
  profile.json
  build-report.json
  filesystem-inventory.json
```

`-custom-web.bin` 是小米后台升级包，不是直接写某个 MTD 分区的裸镜像。不要拿它执行 `mtd write`。

## 修改定制选项

复制一个 JSON 配置再编辑即可。`config/minimal.json` 只保留 SSH、SFTP 和后续定制包升级能力；`config/wol-only.json` 只加入 WOL，关闭 SSH/SFTP/ShellCrash 和签名放行。

```json
{
  "name": "my-home",
  "branding": "我的家庭路由器",
  "features": {
    "ssh": true,
    "sftp": true,
    "wol": true,
    "shellcrash": false,
    "custom_web_upgrade": true
  }
}
```

也支持命令行覆盖：

```powershell
.\.work\venv\Scripts\python.exe -X utf8 build.py build --rom ".\miwifi_rd03_firmware_48abd_1.0.98.bin" --no-shellcrash --no-wol --branding "我的定制版本" --name my-router --tools-dir "C:\Tools\squashfs-tools-ng" --output .work/output/my-router
```

关闭 SSH 时，需要同时关闭 SFTP 与 ShellCrash。非法依赖组合、未知机型、输入摘要不匹配、补丁位置不匹配和容量超限都会终止构建。

当前模块化构建会额外写入可配置网页版本文字和 `profile.json`，文件布局也可能与旧构建不同。**不能把新生成物宣称为归档 2.1 成品的相同文件**；两者各有自己的校验值和验证报告。自定义组合尚未刷入真机测试。

## 改了什么，保留了什么

归档 2.1 相对于指定官方包只修改四个原有文件：Dropbear 启动脚本、导航模板、OOM 策略和 ROM 校验器；其余功能通过新增文件提供。模块化构建再修改网页底部版本文字。完整清单见[实现说明](src/docs/ARCHITECTURE.md)和[历史差异记录](src/docs/historical-2.1-diff.json)。

构建器逐文件比较未计划修改的原有内容和元数据，并检查内核卷完全一致。因此保留官方内核、无线驱动、原有后台、Mesh/NFC 相关程序、App/云端组件及原有系统功能。**保留程序不等于已完成所有功能验收**：Mesh 漫游、NFC 碰一碰、真实唤醒、家庭代理流量和长期稳定性仍需实际使用验证。

不包含 FIP/U-Boot、BL2、Factory、Bdata、设备校准信息、私人配置或整机备份；不扩大分区、不修改官方网络配置、不主动放开 WAN 防火墙。此项目也不移植小米 Mesh 到 OpenWrt。

## 使用与风险

- 首次刷入前确认机型是 RD03，并保留本机分区备份和可用恢复途径。停电、错误硬件版本、不兼容启动链或刷写中断可能导致无法启动。
- `custom_web_upgrade` 放行小米 RSA 来源签名。CRC 只能发现损坏，不能证明固件可信；启用后只上传来源可信且已核对 SHA256 的包。它不关闭安全启动、插件签名、所有降级限制或所有型号检查。
- SSH 提供 root 权限，SFTP 能修改系统文件；两者共用网页登录密码。原厂较旧的 Dropbear 可能需要客户端额外启用 `ssh-rsa`。防火墙规则保持原样，项目不承诺 WAN 可访问。
- 路由器约 256 MiB 内存，ShellCrash 可能仍因复杂规则、连接数或其他服务占用而停止。内存保护优先拒绝启动或停止核心，不保证绝不 OOM；规则转换会改变部分 DNS/GeoIP 行为，详见[内存保护](src/docs/ARCHITECTURE.md#shellcrash-与内存保护)。
- 官方在线升级或恢复原厂 ROM 会替换只读定制功能；恢复出厂可能清除 `/data` 中的设备列表、SSH 主机密钥和代理配置。旧 `/data` 启动项也可能在刷回官方后继续生效，回退时需单独核查。
- 此处的代码许可不覆盖整份小米 ROM。第三方程序保留其各自许可与来源，见 [第三方说明](src/THIRD_PARTY_NOTICES.md)。

## 检查与开发

```powershell
.\.work\venv\Scripts\python.exe -X utf8 build.py check-assets
.\.work\venv\Scripts\python.exe -X utf8 -m unittest discover -s src/tests -v
.\.work\venv\Scripts\python.exe -X utf8 build.py verify --image "firmware/pansoul-2.1/RD03-1.0.98-pansoul2.1-web.bin" --stock ".\miwifi_rd03_firmware_48abd_1.0.98.bin"
```

校验通过只表示离线格式与文件检查通过，不代表已刷写、已启动或完成长期运行测试。新增设备/官方版本必须重新审查格式、分区布局、认证 ABI 和升级流程，不能删掉摘要检查后直接刷。

目录与二进制来源见[开发说明](src/docs/DEVELOPMENT.md)。WOL 的 Go 后端和 SSH 认证桥的 C 源码已包含；ShellCrash 集成脚本、Lua 控制器、网页模板和 SFTP 包来源也已提供。先前设计中的新版浅色后台尚未完成或集成，不属于本次仓库与成品功能。
