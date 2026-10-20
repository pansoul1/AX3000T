"""Small explicit stock-file edits, restricted to the pinned RD03 ROM."""
from __future__ import annotations
import html
import struct
from .formats import sha256, require


def replace_once(data: bytes, before: bytes, after: bytes) -> bytes:
    require(data.count(before) == 1, "Patch anchor is missing or ambiguous: " + repr(before[:90]))
    return data.replace(before, after, 1)


def patch_dropbear(data: bytes) -> bytes:
    gate = (b'\tflg_ssh=`nvram get ssh_en`\n'
            b'\tchannel=`/sbin/uci get /usr/share/xiaoqiang/xiaoqiang_version.version.CHANNEL`\n'
            b'\tif [ "$flg_ssh" != "1" -o "$channel" = "release" ]; then\n'
            b'\t\treturn 0\n\tfi')
    data = replace_once(data, gate,
        b'\t# User-owned firmware: enable SSH without changing Bdata or boot flags.\n'
        b'\t/usr/libexec/rd03-ssh-prepare || return 1')
    anchor = b'\tvalidate_section_dropbear "${1}" || {\n\t\techo "validation failed"\n\t\treturn 1\n\t}\n'
    policy = (b'\n\t# Firewall controls access; keep existing modem-side allow rules usable.\n'
              b'\tInterface=""\n\tPasswordAuth=1\n\tRootPasswordAuth=1\n\tRootLogin=1\n'
              b'\tenable=1\n\tGatewayPorts=0\n\tPort=22\n'
              b'\trsakeyfile=/data/rd03-ssh/dropbear_rsa_host_key\n')
    data = replace_once(data, anchor, anchor + policy)
    command = b'\tprocd_set_param command "$PROG" -F -P "$pid_file"'
    return replace_once(data, command, command + b'\n\tprocd_set_param env LD_PRELOAD=/usr/lib/rd03-admin-auth.so')


def patch_verifier(data: bytes) -> bytes:
    require(sha256(data) == "d703fd0d3eab7ce8db6e26c96b9441f92df103c214af55ed6f77bc0b314f37ed", "Unknown native verifier")
    require(data[:4] == b"\x7fELF" and struct.unpack_from("<H", data, 18)[0] == 183, "Expected AArch64 ELF")
    phoff = struct.unpack_from("<Q", data, 32)[0]
    phsize, count = struct.unpack_from("<HH", data, 54)
    va, target = 0x2180, 0x227c
    segments = [struct.unpack_from("<IIQQQQQQ", data, phoff + phsize * i) for i in range(count)]
    segment = next(s for s in segments if s[0] == 1 and s[3] <= va < s[3] + s[5])
    offset = va - segment[3] + segment[2]
    require(data[offset:offset + 4] == bytes.fromhex("e1070054"), "Native branch mismatch")
    instruction = struct.pack("<I", 0x14000000 | (((target - va) // 4) & 0x3ffffff))
    result = data[:offset] + instruction + data[offset + 4:]
    require(sha256(result) == "f078bd7dfb4775441d3dab7d7b972a681798bcff1d36d139dcdfe9b2674ab47c", "Native patch result mismatch")
    return result


def patch_wol_header(data: bytes) -> bytes:
    lines = data.splitlines(keepends=True)
    result, count = [], 0
    for line in lines:
        result.append(line)
        if b'<li ' in line and b'"/prosetting"' in line:
            margin = ' style="margin-right: 0"' if b'"qos"' in line else ''
            addition = ('                    <li <%if string.find(REQUEST_URI, "/rd03wol") then%>class="active"<%end%>'
                        + margin + '><a href="<%=luci.dispatcher.build_url("web","rd03wol")%>"><%:远程开机%></a></li>\n')
            result.append(addition.encode())
            count += 1
    require(count == 3, "Expected exactly three native navigation branches")
    return b"".join(result)


def patch_branding_footer(data: bytes, branding: str) -> bytes:
    # Insert plain HTML text, never Lua or JavaScript code from a user profile.
    # Also neutralize the LuCI template delimiter even for adversarial names.
    safe = html.escape(branding, quote=True).replace("%", "&#37;")
    before = b'<%=romVersion%> <%=romChannel%>'
    return replace_once(data, before, safe.encode("utf-8"))


def local_init(wol: bool, shellcrash: bool) -> bytes:
    lines = ["#!/bin/sh /etc/rc.common", "START=18", "STOP=90", "start() {"]
    if wol:
        lines += [
            '    if [ "$(uci -q get firewall.rd03_wol.path)" = /data/rd03-wol/start.sh ]; then',
            '        uci -q delete firewall.rd03_wol',
            '        uci commit firewall',
            "        logger -t rd03-local 'Native WOL is built into ROM; retired the old addon hook.'",
            '    fi',
        ]
    if shellcrash:
        lines.append('    /usr/libexec/rd03-shellcrash-prepare --boot || logger -t rd03-memory "ShellCrash preparation held; stock network continues."')
    if not wol and not shellcrash:
        lines.append("    :")
    lines.append("}")
    return ("\n".join(lines) + "\n").encode()
