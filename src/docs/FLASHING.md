# 刷入与恢复

## 开始前

确认设备是 **RD03**，不是 RD03v2/RD23，并保留本机的可靠备份和恢复途径。纯官方 1.0.98 可以从根目录 `First-Flash.ps1` 开始，依次尝试开启 SSH 与临时放行 ROM 校验；已有 SSH 则可跳过开启步骤。该入口不支持其他版本的通用解锁，也不写 FIP、BL2 或校准分区。

当前是定制 ROM 时，先保存私人配置。刷机前停止 ShellCrash，避免上传和升级占用内存；不要在构建、上传或刷写过程中启用大内存代理服务。

检查准备上传的文件：

```powershell
Get-FileHash ".\firmware\pansoul-2.1\RD03-1.0.98-pansoul2.1-web.bin" -Algorithm SHA256
```

归档成品应匹配其 `SHA256SUMS`；自行构建则匹配相应输出目录的校验值。

## 已运行 2.1 内置校验器

从小米后台选择手动升级，上传同机型的 `*-web.bin` 系统升级包。若后台提示验证失败，先看完整错误，核查当前校验器与包来源；不要跳过机型或 CRC 检查强行写入。

2.1 内置补丁只去除原生包校验器对有效小米 RSA 签名的要求，保留机型、HDR1、CRC 和组件提取检查。它不生成小米签名，不能保证其他型号或其他升级程序接受该包。

## 首次从纯官方 1.0.98 刷入

### 没有 SSH：使用完整入口

先完成小米首次初始化，准备 Python 3.10+、OpenSSH/Git，以及能访问该路由器的电脑。在仓库根目录执行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\First-Flash.ps1" -Router 192.168.31.1
```

默认使用 `firmware/pansoul-2.1/` 中的成品。可传 `-Firmware` 指定自己生成的包，`-Rom` 指定本地官方基线，`-Python` 或 `-SshPath` 指定工具位置。缺少官方基线时会从固定地址下载并验证；缺少主机依赖时会创建 `.work/venv` 并安装 `requirements.txt`。

所有本地镜像检查通过后才探测路由器。若已有 SSH，不运行开启代码，直接进入下一步；否则下载外部 XMiR-Patcher 的固定快照，核对归档 SHA256 后在独立 `.work/cache/first-flash-*` 目录解压。

- 固定提交：`16a46e350e3de2cb3415ab2cb652df53783998dc`
- 快照 SHA256：`b33edcf1b5a6406d12428d681e0e117a86826a56fae7ed03ac99c1fc556bdc56`
- 上游项目：[openwrt-xiaomi/xmir-patcher](https://github.com/openwrt-xiaomi/xmir-patcher/tree/16a46e350e3de2cb3415ab2cb652df53783998dc)
- 外部运行时：快照自带的 Windows x64 Python 3.8 与依赖，仅运行此开启步骤；固件构建仍用本机 Python 3.10+。

适配器只导入该快照的 `connect5.py` 智能场景方法，不运行完整菜单、不尝试其他型号或备用漏洞。它在读取到 RD03 和 1.0.98 后才要求隐藏输入网页登录密码并登录后台；其他型号/版本停止。

该上游方法会临时调整路由器时间、创建后删除测试智能场景、修改 Dropbear 启动门槛、提交 `ssh_en`/`telnet_en` NVRAM 开关，并暂时将 root SSH 口令设为 `root`。中断或接口失败可能留下部分改动。项目适配器替换上游收尾函数，避免其 UART/启动等待参数修改与 Telnet 回退；随后通过已认证 SSH 的标准输入把口令改成当前网页登录密码，再验证登录。密码不写入本地配置或命令参数。若失败且口令更换未确认，脚本会提示临时口令可能仍为 `root`，此时应先在可信局域网内处理登录密码。

**这里使用的是纯官方系统的一次开启方法。** 刷入定制包后“SSH 密码持续跟随网页登录密码”的行为由 ROM 内认证桥实现；首次准备的密码修改本身没有这种同步能力。上游工具不由本仓库重新授权，下载和运行依赖信任其固定快照。

`-CheckOnly` 模式要求 Python 依赖和两个镜像已经在本地，仅验证镜像，不下载也不接触路由器。此次新增入口做了离线/模拟检查，没有新增从纯官方设备开启 SSH 的真机验收；失败时不会继续挂载 ROM 校验器，不能把 API 返回成功当作 SSH 已成功。

### 已有 SSH：只做 ROM 校验准备

可以使用同一入口加 `-SkipSshUnlock`，或在仓库根目录、已安装 Python 依赖后直接执行下面原有 PS 脚本，替换地址与文件路径：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\src\scripts\Prepare-WebUpgrade.ps1" -Router 192.168.31.1 -Rom ".\miwifi_rd03_firmware_48abd_1.0.98.bin" -Firmware ".\firmware\pansoul-2.1\RD03-1.0.98-pansoul2.1-web.bin"
```

该脚本：

1. 本地验证官方输入、待上传包的 HDR1/CRC/机型、UBI、FIT 和内核一致性。
2. 从匹配的官方 ROM 生成 4 字节判断补丁，不下载或运行不明路由器程序。
3. 通过 SSH 检查内存，传输包和补丁并核对 SHA256。
4. 检查当前设备型号、当前校验器摘要，再用修改后的原生程序验证包。
5. 临时绑定 `/bin/mkxqimage`；**不刷写、不重启、不改防火墙、不安装持久启动项**。

看到 `READY` 后，保持路由器运行，回到小米网页手动上传同一个 `.bin`。重启会清掉这次 RAM 准备；刷入含 `custom_web_upgrade=true` 的 ROM 后，修改在 ROM 中才会随启动保留。

若找不到 SSH，可安装 Windows OpenSSH 或 Git，或传入 `-SshPath "C:\...\ssh.exe"`。可用 `-Python` 指定解释器；默认优先选择仓库 `.work/venv`。程序会要求当前真正可登录的 SSH 密码，不记录密码。

若 SSH 提示主机密钥变化，先确认 IP 对应同一台刚刷机的设备，再清理该地址的旧记录并重新核对指纹。脚本不会全局关闭 SSH 主机验证。

上传前取消临时绑定，可在路由器 SSH 执行：

```sh
umount /bin/mkxqimage
```

这只撤销当前 RAM 的绑定。若固件里已内置补丁，卸载绑定不会恢复 ROM 自身的原厂校验器。

## 刷后功能检查

- 小米后台可正常登录，路由功能正常。
- SSH：用户名 `root`，密码为当前网页登录密码。旧 Dropbear 需要时使用 `ssh -o HostKeyAlgorithms=+ssh-rsa root@路由器地址`。
- SFTP：同一账号和 22 端口；可读写 `/data`。
- WOL：登录后台后出现“远程开机”，添加测试设备并实际验证开机。
- ShellCrash：SSH 输入 `crash` 进入菜单，上传自己的 YAML、设置代理模式后再启动。新装不应自动启动代理。
- 用实际终端检查 Wi-Fi、LAN、Mesh、NFC；观察内存和长期稳定性。

## 回到官方

使用该设备对应的可信官方 RD03 ROM，通过当前可用的正常升级或厂商恢复流程回退。原厂升级包会替换系统及校验器，但不能据此断言设备所有分区和 `/data` 都已恢复原厂。

本项目从不包含或写入 FIP/U-Boot/BL2，所以无法替你修复原先改过的启动器。已有 `/data` 中的 SSH、ShellCrash、WOL 外挂或防火墙启动钩子需单独检查。恢复出厂会丢失用户配置和设备列表，先备份再操作。

不能启动时，采用**自己已验证可用**的原厂恢复方式和本机备份。不同启动器、NAND 分区布局和安全启动状态有差别，不要照搬其他型号的 MTD 写入命令。
