# AX3000T 社区固件 2.1

- 文件：`RD03-1.0.98-community-2.1-custom-web.bin`
- 基线：小米 RD03 官方 1.0.98；不支持 RD03v2/RD23。
- 配置：[profile.json](profile.json)，默认开启 SSH、SFTP、原生 WOL、ShellCrash 和后续定制包后台升级。
- 默认网页文字：`AX3000T 社区固件 2.1`，可通过构建配置修改。
- SHA256：`2a0c57548e5e7b62139ebcf897438f18a6fbefcaa59324aef615cd09e0740a6a`，另见 [SHA256SUMS](SHA256SUMS)。

## 第一次怎么刷

纯官方 1.0.98 默认没有 SSH，也不接受本包签名。请获取完整仓库，从根目录执行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\First-Flash.ps1" -Router 192.168.31.1
```

此入口调用第三方 XMiR-Patcher 的 `connect5.py` 开启 SSH，再执行本项目的 ROM 校验准备。输入提示要求的网页登录密码/SSH 密码，看到 READY 后保持路由器运行，在小米后台“常用设置 → 系统状态 → 系统升级 → 手动升级”上传本目录 `.bin`。PS 不自动刷写或重启。已有 SSH 可加 `-SkipSshUnlock`，已内置 ROM 校验补丁的定制版通常可直接网页升级。

完整步骤、来源归属、设备改动和回退见[刷入与恢复](../../src/docs/FLASHING.md)。

## 检查范围

[build-report.json](build-report.json) 记录真实输入、配置、容量和文件比较结果；[离线验收](../../src/docs/offline-build-checks.json) 记录功能组合与重复构建检查。新包内核和未计划修改的原厂节点保持一致，未包含引导器、校准分区、私人口令或订阅。

**本包仅离线验证，尚未刷入真机。** 首刷解锁适配器已完成离线与模拟检查。

SSH/SFTP 使用 `root` 和当前小米网页登录密码。ShellCrash 首次 `crash` 初始化后再自行配置；旧版升级可能要求先停止代理并重新确认启动设置。256 MiB 内存仍有限制，ROM 校验放行也降低来源验证门槛，只刷可信且摘要一致的包。

未获小米有效签名，厂商和第三方组件沿用其原有权利及许可，见[第三方说明](../../src/THIRD_PARTY_NOTICES.md)。
