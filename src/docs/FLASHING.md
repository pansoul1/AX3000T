# 刷入与恢复

## 先判断自己在哪一步

仅支持 **RD03 官方 1.0.98** 基线，不支持 RD03v2/RD23。首次使用前保存本机备份、确认恢复途径、停止代理并保持供电。

| 当前状态 | 怎么做 |
| --- | --- |
| 纯官方 1.0.98，没有 SSH | 根目录 `First-Flash.ps1` 衔接第三方解锁和本项目 ROM 准备，READY 后网页手动上传 |
| 官方 1.0.98，已有 SSH | 同一入口加 `-SkipSshUnlock`，准备后网页手动上传 |
| 已刷含 `custom_web_upgrade=true` 的定制版 | 小米后台直接上传正确 RD03 系统包，通常不再需要准备 |
| 其他型号或官方版本 | 此入口不支持，不要绕过型号/摘要限制 |

## 第一次从纯官方 1.0.98 刷入

### 1. 准备电脑和完整仓库

电脑接路由器 LAN，确认能打开小米网页，路由器已完成初始化。准备 Python 3.10+ 和 Windows OpenSSH/Git for Windows，须有 `ssh.exe`、`scp.exe`。

```powershell
git clone https://github.com/pansoul1/AX3000T.git
cd AX3000T
```

也可在仓库页面 Code → Download ZIP，完整解压后从根目录打开 PowerShell。不要只下载一个 PS，它依赖同仓库代码、payload 和成品。

### 2. 执行 PS 准备入口

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\First-Flash.ps1" -Router 192.168.31.1
```

改过地址就替换 `-Router`。默认包为 `firmware/community-2.1/RD03-1.0.98-community-2.1-custom-web.bin`。

脚本先校验镜像、机型、CRC、UBI/FIT/SquashFS 和内核。缺官方基线则从固定小米 CDN 下载并核对摘要，缺 Python 依赖则在 `.work/venv` 安装，需要联网下载依赖及固定外部工具。

已有 SSH 就跳过解锁。否则使用下文第三方方法，提示网页登录密码时输入**当前小米网页登录密码**，输入隐藏。成功后，传输和准备阶段可能多次要求 **SSH 密码**：刚开启时是上一步网页登录密码，已有 SSH 则用原先能登录的口令。

之后检查实际 SSH 认证、设备型号、内存、当前校验器摘要和传输摘要，再临时绑定 `/bin/mkxqimage`。**不刷写、不重启、不改防火墙、不写 FIP/BL2/校准分区。** 失败则停止，不把 API 的 `code:0` 当作准备成功。

### 3. READY 后网页手动上传

保持路由器运行，在小米网页后台进入 **常用设置 → 系统状态 → 系统升级 → 手动升级**，选择脚本最后打印的文件：

```text
firmware/community-2.1/RD03-1.0.98-community-2.1-custom-web.bin
```

确认是同一个 `.bin`，按网页提示升级，等待刷写和重启完成。**PS 输出 READY 仅表示可以开始上传，运行 PS 本身没有完成刷机。**

上传前重启会清掉 RAM 临时准备，此时须重新运行入口。刷入 `custom_web_upgrade=true` 后，补丁才在 ROM，重启仍保留。补丁只放行小米 RSA 来源判断，保留 RD03 型号、HDR1、CRC 和组件提取检查，不生成小米签名。

### 4. 刷后检查

- 重新连接，登录小米网页，确认 LAN 和 Wi-Fi 可上网。
- SSH：`root` 和当前网页登录密码。旧 Dropbear 需要时使用 `ssh -o HostKeyAlgorithms=+ssh-rsa root@路由器地址`。
- SFTP：同一账号及 22 端口，可读写 `/data`。
- WOL：后台“远程开机”添加设备，实际验证开机。
- ShellCrash：SSH 执行 `crash` 初始化，上传 YAML、配置模式后再启动，新装不开机自启。
- 实测 Mesh、NFC 和长期稳定性，保留程序不代表全部功能验收。

首刷适配器仅做离线/模拟检查，本次社区版未新增真机验收，不沿用旧成品的运行报告。由旧定制版升级时，中性版更换了 ShellCrash 集成标记；首次集成会备份原脚本并关闭代理自启，需要先停核心，检查设置后再手动启用。

## 第三方解锁来源与设备改动

**开启方法来自第三方 openwrt-xiaomi/xmir-patcher 的 `connect5.py`，不是本项目原创漏洞。** 本项目写的是 `First-Flash.ps1` 入口、`unlock-stock-ssh.py` 适配器及 `Prepare-WebUpgrade.ps1` ROM 准备脚本。

- 上游：[XMiR-Patcher 固定提交](https://github.com/openwrt-xiaomi/xmir-patcher/tree/16a46e350e3de2cb3415ab2cb652df53783998dc)
- 提交：`16a46e350e3de2cb3415ab2cb652df53783998dc`
- 下载 ZIP SHA256：`b33edcf1b5a6406d12428d681e0e117a86826a56fae7ed03ac99c1fc556bdc56`
- 运行时：快照自带 Windows x64 Python 3.8 和依赖，仅用于开启步骤，构建仍用本机 Python 3.10+。

入口核对归档后每次解压到新 `.work/cache/first-flash-*`，只导入 `connect5.py` 智能场景方法，不运行完整菜单、不试其他型号或备用漏洞。适配器读到 RD03/1.0.98 且已初始化才继续。

上游会临时调整路由器时间、创建后删除测试智能场景、修改 Dropbear 门槛、提交 `ssh_en`/`telnet_en` NVRAM 开关，并暂时把 root SSH 密码设为 `root`。中断或失败可能留下部分变更。

本项目替换上游收尾，跳过 UART/启动等待参数修改与 Telnet 回退，通过已认证 SSH channel 标准输入把临时口令改成刚输入的网页登录密码，再验证登录。密码不写本地配置或命令参数。若更换未确认，输出提示可能仍为 `root`，应先在可信局域网处理密码，不继续上传。

首刷准备只更换一次密码，刷后持续同步网页登录密码由 ROM 的认证桥实现。第三方代码、依赖沿用原来源和许可，不由本项目 MIT 重新授权。

## 其他用法

### 已有 SSH

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\First-Flash.ps1" -Router 192.168.31.1 -SkipSshUnlock
```

也可在已安装依赖的仓库直接执行原 ROM 准备脚本：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\src\scripts\Prepare-WebUpgrade.ps1" -Router 192.168.31.1 -Rom ".\.work\cache\miwifi_rd03_firmware_48abd_1.0.98.bin" -Firmware ".\firmware\community-2.1\RD03-1.0.98-community-2.1-custom-web.bin"
```

它要求已有 SSH，没有开启 SSH 的功能。从固定官方 ROM 生成四字节分支补丁，核查当前校验器和包摘要。SCP 用旧协议，不要求官方已具备 SFTP。

### 指定镜像或工具

`-Firmware` 指定自建包，`-Rom` 指定官方基线，`-Python`/`-SshPath` 指定工具。找不到 SSH 时安装 Windows OpenSSH/Git，或传 `-SshPath "C:\...\ssh.exe"`，旁边须有 `scp.exe`。

仅校验本地材料（提前准备依赖与两个镜像）：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\First-Flash.ps1" -Rom ".\.work\cache\miwifi_rd03_firmware_48abd_1.0.98.bin" -CheckOnly
```

不下载、不连接路由器、不开启 SSH，也不表示已准备好升级。

### 中断、密钥或校验错误

主机密钥变化时先确认 IP 是同一台刚刷机的设备，再清理该地址旧记录并核对新指纹。脚本不会全局关闭主机验证。

网页校验失败时保留报错，核对校验器、包和准备状态，不绕过型号或 CRC 强写。上传前取消临时绑定，可在路由器 SSH 执行：

```sh
umount /bin/mkxqimage
```

只撤销 RAM 绑定，若 ROM 自身已打补丁，此命令不会恢复原厂程序。

## 回到官方

用可信且对应 RD03 的官方 ROM，经可用的正常升级或厂商恢复流程回退。官方升级替换系统及校验器，不等于所有分区和 `/data` 恢复原样。

项目不写 FIP/U-Boot/BL2，无法修复以前改过的启动器。`/data` 旧 SSH、ShellCrash、WOL 外挂及防火墙钩子须单独检查。恢复出厂会丢配置和设备列表，先备份。

无法启动时用自己验证过的恢复方式和本机备份。启动器、NAND 布局有差别，不照搬其他型号的 MTD 命令。
