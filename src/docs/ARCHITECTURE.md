# 实现说明

## 构建流程

```text
官方 RD03 1.0.98 HDR1 包（摘要白名单）
  → 验证 HDR1 / CRC / RD03 型号 / 组件边界
  → 验证 UBI 与原厂 FIT / SquashFS
  → sqfs2tar 导出带元数据的文件系统
  → 根据 JSON 配置修改少量文件并加入选中组件
  → tar2sqfs 重建 XZ SquashFS
  → 逐文件比较内容、权限、属主、时间戳、链接及设备节点
  → 沿用原 UBI 几何与头结构，重建两个系统卷
  → 检查 34 MiB 槽容量与 5 个 Xiaomi EOF 标记
  → 验证原内核卷完全一致，生成无小米有效签名的 HDR1
```

没有把整个文件系统先解压到 Windows NTFS 再重新打包，避免权限、符号链接和设备节点丢失。UBI 重建用 Python 完成，不依赖仅在开发机存在的定制 `ubinize.exe`。重复打包归档 2.1 的 UBI 可恢复相同字节，回归测试覆盖这一点。

仅输出版本信息 `xiaoqiang_version` 和系统 `firmware_ubi.bin` 两个组件。保留原内核、UBI 页面/擦除块几何、镜像序号、官方升级元数据及原系统槽上限；rootfs 卷占用会随所选组件变化，不改变 NAND 分区表。

## 官方文件修改

| 文件 | 启用条件 | 修改 |
| --- | --- | --- |
| `/etc/init.d/dropbear` | SSH | 移除 release/ssh_en 启动门槛，增加私有认证桥及持久主机密钥 |
| `/usr/lib/lua/luci/view/web/inc/header.htm` | WOL | 在原有路由/AP/Mesh 导航分支增加“远程开机” |
| `/etc/sysctl.conf` | ShellCrash | `vm.panic_on_oom=2` 改为 `0`，降低内存耗尽直接触发整机 panic 的风险 |
| `/bin/mkxqimage` | 定制包升级 | 将固定 AArch64 虚拟地址 `0x2180` 的条件跳转改为无条件跳转，跳过 RSA 判断 |
| `/usr/lib/lua/luci/view/web/inc/footer.htm` | 新构建器 | 将原版本显示替换为经过 HTML 转义的 `branding` 文本 |

最后一项不属于原样归档的 2.1；构建器没有冒充“同一摘要的历史成品”。所有其他官方文件必须与输入的内容和元数据一致，否则不交付 `.bin`。

## SSH 与 SFTP

原厂 Dropbear 仍是 SSH 服务端。只有它的 procd 进程加载认证桥 `/usr/lib/rd03-admin-auth.so`。认证桥只接受 `root`，通过固定 Lua 程序和管道验证当前小米管理员口令，不把密码作为 shell 命令或命令行参数拼接，也不改写 `/etc/shadow` 的长期密码记录。管理密码修改后，下一次 SSH 认证读取新的管理员摘要。

认证桥启动后清理加载环境，避免把 `LD_PRELOAD` 传到登录后的其他进程。未完成小米首次初始化、校验程序失败、空密码、超长输入和未知摘要格式均拒绝认证。

主机密钥在设备首次启动时生成到 `/data/rd03-ssh/`，镜像中不含开发者私钥。Dropbear 保留较旧的算法能力，因此现代客户端可能需要单地址启用 `HostKeyAlgorithms=+ssh-rsa`。脚本不关闭主机密钥验证。

SFTP 使用独立 musl / GCC 运行库启动 OpenWrt 提供的 OpenSSH 子系统，不替换原系统 libc。启动包装器清理 `LD_PRELOAD`；SFTP 与 SSH 共用认证和 22 端口。监听策略不负责打开防火墙；原有防火墙规则继续生效。

## WOL

- 控制器：`/usr/lib/lua/luci/controller/rd03_wol.lua`
- 页面：`/usr/lib/lua/luci/view/web/rd03wol.htm`
- 后端：`/usr/libexec/rd03-wol-api`
- 持久设备列表：`/data/rd03-wol/devices.json`

页面沿用小米 `htmlauth` 管理会话。后端通过固定 `nixio.exec` 启动，可接收经过编码的参数，不支持任意命令执行。写操作要求 POST 和 CSRF；MAC、设备名称、请求大小及发送速率由后端检查。唤醒成功只表示数据包已发送，不能据此断定电脑已启动。

WOL 仍需目标电脑 BIOS、网卡、电源状态及网络路径支持。它不包含 VPN、穿透或公网管理入口。现有小米 Mesh 程序不由 WOL 修改。

## ShellCrash 与内存保护

固定 ShellCrash 1.9.4 和 Mihomo v1.19.17。脚本归档、核心与精简规则都在只读 ROM，首次执行 `crash` 才将脚本初始化到 `/data/ShellCrash`，核心软链接到 ROM。启动准备不意味着开启代理；初次集成会留下关闭启动/错误标记供使用者配置后决定。

ROM 内的准备程序只识别已记录摘要的脚本版本。遇到不支持的升级、不同核心版本、自定义运行目录/COMMAND 或旧 watchdog 模式时拒绝自动套用，不将未知程序直接替换为旧模板。

配置处理写入独立的运行副本，保留用户原始 YAML。它不是完整的 YAML 语义重写器，只转换已审查的格式：

- 关闭 `fallback-filter` 中的 GeoIP/GeoSite 过滤。
- 将匹配形式的 `GEOIP,CN,DIRECT` 改为本地 `RULE-SET,rd03-cn-ip,DIRECT`。
- 对特定 ShellCrash `cn` provider 改用本地精简 MRS。
- 不覆盖用户自行定义的同名 provider；格式不明确时终止转换。

这会改变过滤与分流行为；MRS 数据集也不能宣称与任意旧版 MMDB/GeoSite 完全等价。没有把节点数量当作已经确认的唯一 OOM 原因。

核心通过 cgroup v1 内存控制器运行：启动前至少 56 MiB `MemAvailable`，限制根据当时可用内存减去 24 MiB 预留量计算，上限 80 MiB；Go 的 `GOMEMLIMIT=24MiB` 仅是软目标，不是总进程硬限额。系统剩余内存低于 24 MiB、核心退出或验证失败时停止核心并撤销代理流量规则，不无限 respawn。配置测试还受超时约束，兼容旧 BusyBox 的 `timeout -t`。

这些措施不能防止所有内存耗尽、内核/驱动故障或断电，也不能证明历史所有断网均由 U-Boot 引起。

## 关闭组件与数据

开关决定新 ROM 中是否包含对应程序，不会在构建时访问设备的 `/data`。从历史全量版改刷精简版时，旧的持久插件可能仍存在，必须在设备上核对。

`rd03-space-clean` 沿用只清理已知摘要旧 WOL 外挂的策略，保留设备列表，不进行广泛的官方目录精简。构建器不打包整机备份、MAC/序列号、主机私钥、管理口令或订阅信息。
