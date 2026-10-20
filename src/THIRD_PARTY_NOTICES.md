# 第三方组件、来源与许可边界

本项目自己的 Python 构建器、项目专用脚本、文档和原创 WOL 实现采用根目录 MIT 许可；SSH 认证桥 C 文件已有的 0BSD 声明保留。此许可不覆盖整个成品 ROM，也不改变上游组件的权利和义务。

| 组件 | 使用版本/来源 | 许可与说明 |
| --- | --- | --- |
| 小米官方 ROM 与原有程序 | RD03 1.0.98，官方 CDN，输入 SHA256 固定 | 属于原厂固件及其各组件；不是本项目完整开源的源码，不适用本项目 MIT |
| ShellCrash | [1.9.4](https://github.com/juewuy/ShellCrash/releases/tag/1.9.4) 的发布归档 | GPLv3，见 `licenses/ShellCrash-LICENSE.txt`；发布脚本归档本身包含脚本源码 |
| ShellCrash 衍生模板 | `payloads/shellcrash/usr/share/rd03-memory/templates/` | 从上述版本修改，沿用 GPLv3；修改包括拒绝无保护的验证重试、固定核心与配置准备、失败时清理代理规则 |
| Mihomo | [v1.19.17](https://github.com/MetaCubeX/mihomo/tree/v1.19.17)，官方 ARM64 核心 | GPLv3，见 `licenses/Mihomo-LICENSE.txt`；[对应源码归档](https://github.com/MetaCubeX/mihomo/archive/refs/tags/v1.19.17.tar.gz) |
| CN MRS 规则 | [meta-rules-dat 固定提交](https://github.com/MetaCubeX/meta-rules-dat/tree/1852a7d214920d77c753293c49eb26a996e52081) | 保留数据集上游许可与来源；项目主分支取得的 GPLv3 文本在 `licenses/meta-rules-dat-LICENSE.txt`，具体数据还应按上游列出的来源说明处理 |
| OpenSSH SFTP | OpenWrt 24.10.2 `openssh-sftp-server 9.9_p2-r1` | OpenSSH 自身复合许可，见 `licenses/OpenSSH-LICENCE.txt`；包 URL/摘要和源码归档信息见 `sources/sftp/packages.json` |
| musl | OpenWrt 24.10.2 `1.2.5-r4` | musl 许可，见 `licenses/musl-COPYRIGHT.txt` |
| GCC 运行库 | OpenWrt 24.10.2 `libgcc1 13.3.0-r4` | GPLv3 与 GCC Runtime Library Exception，见 `licenses/GCC-*`；[GCC 13.3.0 源码](https://gcc.gnu.org/pub/gcc/releases/gcc-13.3.0/) |
| dissect.squashfs / cstruct / util | `requirements.txt` 中固定版本 | 作为主机构建依赖安装，未打进路由器 ROM；各包保留其上游许可 |
| squashfs-tools-ng | 1.3.2 | 外部工具链，未提交其程序；[上游许可说明](https://github.com/AgentD/squashfs-tools-ng/blob/v1.3.2/COPYING.md) |
| XMiR-Patcher | [固定提交 16a46e3](https://github.com/openwrt-xiaomi/xmir-patcher/tree/16a46e350e3de2cb3415ab2cb652df53783998dc)，仅首次准备使用 | 不随仓库或 ROM 分发；PS 入口按需下载并核对摘要，快照自带的主机 Python/依赖沿用上游各自声明。项目 MIT 仅覆盖原创适配器，不给上游代码重新授权 |

SFTP 使用 OpenWrt 发布的包，未把原厂 libc 替换掉。Mihomo 核心是上游二进制，不是本项目从零实现的代理程序。第三方摘要和版本记录不等于小米对定制包签名。

本仓库包含用户要求归档的完整定制 ROM，其中也有厂商二进制和第三方软件。公开发布时，代码许可、原厂固件的再分发范围以及 GPL 组件的对应源码/告知要求需要分别处理；不能用根目录 MIT 许可给整份 `.bin` 重新授权。
