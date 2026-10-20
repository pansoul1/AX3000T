# AX3000T 社区固件

基于 **小米 AX3000T RD03 官方 1.0.98** 的离线定制工具与社区版 2.1 成品。保留官方系统主体，按需加入 SSH、SFTP、原生后台 WOL 和带内存保护的 ShellCrash，支持自定义网页版本文字。

**仅支持 RD03 和摘要锁定的官方 1.0.98。不支持 RD03v2、新版 AX3000T、RD23 或其他 ROM。** 这是社区项目，生成的包没有小米有效签名，也不是完整的 OpenWrt 源码工程。

## 第一次刷入：从纯官方系统开始

纯官方默认没有 SSH，后台也会拒绝定制包的签名。**不能直接上传这里的 `.bin`；必须先做准备，最后再到网页手动刷入。**

### 1. 准备电脑与路由器

- 路由器运行官方 **1.0.98**，已完成初始化，知道当前小米网页登录密码。其他版本先按厂商流程升级到对应 RD03 官方 1.0.98，本脚本不负责跨版本升级。
- Windows 电脑连接路由器 LAN，确认能打开小米后台。默认地址为 `192.168.31.1`；改过地址就替换命令中的 `-Router`。
- 电脑安装 **Python 3.10+** 和 **Git for Windows 或 Windows OpenSSH 客户端**，须同时有 `ssh.exe`、`scp.exe`。
- 保存本机可靠备份和恢复途径。准备和刷写期间停止代理服务，保持供电。

获取完整仓库：

```powershell
git clone https://github.com/pansoul1/AX3000T.git
cd AX3000T
```

也可从仓库页面 Code → Download ZIP，完整解压后在根目录打开 PowerShell。应能看到 `First-Flash.ps1`、`build.py`、`config`、`src` 和 `firmware`，不要只下载单个 PS 文件。

### 2. 运行首次准备脚本

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\First-Flash.ps1" -Router 192.168.31.1
```

默认使用仓库里的社区版 2.1 成品。脚本准备本机 Python 依赖、下载并核对固定官方基线和第三方工具，先校验镜像，再连接指定路由器。

按提示输入密码：

- **开启 SSH 时：**输入当前小米**网页登录密码**，输入过程隐藏。
- **传输和准备时：**输入当前可用的 **SSH 密码**。本次刚成功开启时就是上一步的网页登录密码；已有 SSH 则使用原先能登录的密码，可能要求输入多次。

脚本验证 SSH 确实能登录后，临时放行原厂 ROM 校验器的 RSA 判断。失败则停止；有报错时不要继续上传。

### 3. READY 后，在小米后台手动上传

保持路由器运行，在小米网页后台进入 **常用设置 → 系统状态 → 系统升级 → 手动升级**，选择：

```text
firmware/community-2.1/RD03-1.0.98-community-2.1-custom-web.bin
```

以脚本最后打印的完整路径为准，确认升级后等待刷写和重启完成。**运行 PS 只完成准备，不代表已经刷机；上传前重启会清掉临时准备，需要重新运行脚本。**

### 4. 刷后登录

重新连接路由器，登录小米后台检查网络。SSH/SFTP 用户名为 `root`，密码跟随**当前小米网页登录密码**，SFTP 使用同一个 22 端口。在原生后台“远程开机”标签管理 WOL。SSH 执行 `crash` 初始化 ShellCrash，再配置自己的 YAML 和启动方式；新装不会自动启动代理。

首次准备入口已做离线与模拟检查，**尚未完成新增的纯官方设备解锁链路和本次社区版成品的真机验收**。遇到问题保留输出，详见[刷入与恢复](src/docs/FLASHING.md)。

## 解锁 SSH 用的是谁的脚本

**漏洞利用来自第三方 XMiR-Patcher，本项目没有原创 SSH 漏洞。**

| 环节 | 来源 | 做什么 |
| --- | --- | --- |
| 首次开启 SSH 的方法 | [openwrt-xiaomi/xmir-patcher](https://github.com/openwrt-xiaomi/xmir-patcher/tree/16a46e350e3de2cb3415ab2cb652df53783998dc) 的 `connect5.py` | 通过原厂智能场景接口开启 SSH，仅调用此方法 |
| Windows 入口与适配 | 本项目 [First-Flash.ps1](First-Flash.ps1) 和 [unlock-stock-ssh.py](src/scripts/unlock-stock-ssh.py) | 检查 RD03/1.0.98、获取口令、验证 SSH，将上游临时 root 密码改成刚输入的网页登录密码 |
| 首刷 ROM 校验准备 | 本项目 [Prepare-WebUpgrade.ps1](src/scripts/Prepare-WebUpgrade.ps1) | 在已有 SSH 上临时绑定匹配的原生校验器补丁，保留型号、格式和 CRC 检查 |
| 真正刷写 | 用户在小米网页手动升级 | 上传脚本指定的 `.bin`，PS 不自动刷写 |

第三方工具不随仓库或 ROM 打包。入口按需下载固定提交并核对 SHA256，不使用浮动最新版。上游开启过程会临时改时间、智能场景、Dropbear/NVRAM 开关及 root 密码，失败可能留下部分变更。适配器收尾、固定摘要和恢复边界见[首刷细节](src/docs/FLASHING.md#第三方解锁来源与设备改动)；第三方署名与许可保留。

## 已有 SSH 或已刷过定制版

纯官方但已有可用 SSH，只跳过解锁，仍需要 ROM 准备：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\First-Flash.ps1" -Router 192.168.31.1 -SkipSshUnlock
```

已运行内置 `custom_web_upgrade=true` 的定制版，可直接在小米后台上传正确 RD03 系统包，无需重复 PS 准备。这个开关默认开启；关闭它、恢复原生校验器或刷回官方后，不能沿用这一结论。

`-Rom` 指定本地官方基线，`-Firmware` 指定自建包，`-Python`/`-SshPath` 指定工具。`-CheckOnly` 只检查本地材料，不下载、不连接路由器，须提前准备依赖和镜像。完整用法见[刷入说明](src/docs/FLASHING.md)。

## 2.1 成品和目录

- [社区版 2.1 固件](firmware/community-2.1/RD03-1.0.98-community-2.1-custom-web.bin)
- [SHA256SUMS](firmware/community-2.1/SHA256SUMS)
- [成品说明与构建报告](firmware/community-2.1/README.md)

根目录主要文件夹保持三个：

```text
config/         功能开关、自定义版本文字
src/            构建源码、运行文件、辅助脚本、文档与许可
firmware/       成品、配置、校验值和构建报告
First-Flash.ps1 首次准备入口
build.py        离线构建入口
```

本机缓存、环境和中间文件集中在 `.work/`，不上传 Git。内部目录见[开发说明](src/docs/DEVELOPMENT.md)。

## 可以定制什么

| 配置项 | 默认 | 作用 |
| --- | --- | --- |
| `ssh` | 开 | 原厂 Dropbear + 管理密码认证桥，用户名 `root`，无固定密码 |
| `sftp` | 开 | 补充 SFTP 子系统，共用 SSH 认证和端口，依赖 `ssh` |
| `wol` | 开 | 原生小米后台增加“远程开机”标签、设备列表及唤醒操作 |
| `shellcrash` | 开 | 预置 ShellCrash 1.9.4、Mihomo 1.19.17、精简 MRS 与内存保护，依赖 `ssh` |
| `custom_web_upgrade` | 开 | 放行原生校验器 RSA 判断，保留机型、格式、CRC，方便后续后台升级 |
| `branding` | `AX3000T 社区固件 2.1` | 自定义网页版本文字和构建标记，不伪改官方更新元数据 |

ShellCrash 首次执行 `crash` 才将脚本初始化到 `/data`，核心从只读 ROM 运行，不再在 `/tmp` 展开约 29.5 MiB 核心。没有节点、订阅或私人 YAML。关闭开关只影响新 ROM，不会删除设备 `/data` 中过去安装的插件和配置。

## 自己构建

需要 Python 3.10+ 和 [squashfs-tools-ng 1.3.2](https://github.com/AgentD/squashfs-tools-ng/releases/tag/v1.3.2) 的 `sqfs2tar`/`tar2sqfs`。解压工具链到 `.work/cache/tools/` 并保留动态库，或指定 `--tools-dir`。Windows 原生构建已检查，其他平台本次未完整构建实测。

在仓库根目录执行：

```powershell
python -m venv .work/venv
.\.work\venv\Scripts\python.exe -m pip install -r requirements.txt
.\.work\venv\Scripts\python.exe -X utf8 build.py fetch-stock
.\.work\venv\Scripts\python.exe -X utf8 build.py plan --rom .work/cache/miwifi_rd03_firmware_48abd_1.0.98.bin --profile config/community-2.1.json
.\.work\venv\Scripts\python.exe -X utf8 build.py build --rom .work/cache/miwifi_rd03_firmware_48abd_1.0.98.bin --profile config/community-2.1.json --output .work/output/my-build
```

`fetch-stock` 显式下载固定官方基线并核对下列摘要；基线不代表小米最新版本。`build` 本身离线运行，不连接路由器。

```text
官方基线 SHA256：042ba08949e547007710caa43830e574a7a7f5964119af4c457409b2fa8b4bce
```

输出目录必须尚不存在。产物含 `.bin`、`SHA256SUMS`、`profile.json`、`build-report.json`、`filesystem-inventory.json`。`*-custom-web.bin` 是后台升级包，**不要拿它执行 `mtd write`**。

复制 JSON 配置编辑即可；`config/minimal.json` 只保留 SSH/SFTP 和定制包升级能力，`config/wol-only.json` 只加入 WOL。示例：

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

也可用 `--no-shellcrash --no-wol --branding "我的定制版本" --name my-router` 覆盖配置。关闭 SSH 时需同时关闭 SFTP 与 ShellCrash。非法组合、未知 ROM、摘要或补丁不匹配、容量超限都会停止构建。

## 改了什么，保留了什么

全量版只修改五个原厂文件：Dropbear 启动脚本、导航模板、OOM 策略、ROM 校验器、网页版本文字，其他功能以新增文件提供。逐个检查未计划修改的原厂节点及元数据，内核卷必须完全一致。见[实现说明](src/docs/ARCHITECTURE.md)与[离线验收记录](src/docs/offline-build-checks.json)。

保留官方内核、无线驱动、原有后台、Mesh/NFC、App/云端相关程序。保留文件不等于完成所有功能验收：漫游、碰一碰、实际 WOL、家庭代理流量和长期稳定性仍需真机检查。

不含 FIP/U-Boot、BL2、Factory、Bdata、校准信息、主机私钥、用户密码或整机备份，不改 NAND 分区或官方网络配置，不主动放开 WAN 防火墙。

## 风险与回退

- 错误硬件、停电、刷写中断或不兼容启动链可能导致无法启动。保留自己的备份和已验证恢复方式。
- 启用 `custom_web_upgrade` 后，CRC 不能证明来源可信，只上传可信且核对摘要的包。补丁不关闭安全启动、插件验签或所有降级限制。
- SSH/SFTP 有 root 权限，管理密码也用于 SSH。旧 Dropbear 可能需要客户端为该地址启用 `ssh-rsa`；不保证 WAN 可访问。
- 256 MiB 内存仍有限制。cgroup、监测和精简规则不能保证绝不 OOM，转换会改变部分 DNS/GeoIP 行为，见[内存保护](src/docs/ARCHITECTURE.md#shellcrash-与内存保护)。
- 刷回官方或在线升级会替换 ROM 定制功能，恢复出厂可能清除 `/data` 中的配置和密钥。旧 `/data` 启动钩子须单独检查，刷回官方不等于整机所有内容恢复原样。
- 代码许可只覆盖相应源码，不给整份小米 ROM 重新授权；第三方许可见[来源说明](src/THIRD_PARTY_NOTICES.md)。

## 检查与开发

```powershell
.\.work\venv\Scripts\python.exe -X utf8 build.py check-assets
.\.work\venv\Scripts\python.exe -X utf8 -m unittest discover -s src/tests -v
.\.work\venv\Scripts\python.exe -X utf8 build.py verify --image firmware/community-2.1/RD03-1.0.98-community-2.1-custom-web.bin --stock .work/cache/miwifi_rd03_firmware_48abd_1.0.98.bin
```

校验通过表示离线检查通过，不代表已刷写或真机验收。WOL Go 后端、SSH C 认证桥、集成脚本和组件来源已提供。先前暂停的新后台设计未集成，仍沿用小米后台。
