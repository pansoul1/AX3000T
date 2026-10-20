#!/usr/bin/env python3
"""RD03 1.0.98 adapter for the hash-pinned external XMiR-Patcher connect5.

Executed by the verified snapshot's Windows Python runtime from its own folder.
No firmware writer, bootloader installer or generic fallback is imported.
This file deliberately remains compatible with the upstream Python 3.8 runtime.
"""
import argparse
import getpass
import ipaddress
from pathlib import Path
import sys
import types


def require_target(gateway):
    if gateway.status < 1:
        raise RuntimeError("Cannot identify an initialized Xiaomi router.")
    if gateway.device_name != "RD03" or gateway.rom_version != "1.0.98":
        raise RuntimeError("SSH bootstrap only supports RD03 official 1.0.98; no unlock attempted.")


def replace_temporary_password(gateway, password):
    """Send the new password only over SSH stdin, never through command arguments."""
    session = gateway.get_ssh(contimeout=5)
    if session is None:
        raise RuntimeError("Cannot open the verified SSH session to replace the temporary password.")
    channel = session.open_session()
    payload = ((password + "\n") * 2).encode("utf-8")
    try:
        channel.execute("passwd root >/dev/null 2>&1")
        sent = 0
        while sent < len(payload):
            _, count = channel.write(payload[sent:])
            if count <= 0:
                raise RuntimeError("Could not send the new password over SSH stdin.")
            sent += count
        channel.send_eof()
        channel.wait_eof()
        channel.close()
        channel.wait_closed()
        if channel.get_exit_status() != 0:
            raise RuntimeError("The router rejected the replacement SSH password.")
    finally:
        payload = b""
        gateway.shutdown()
    if gateway.check_ssh(gateway.ip_addr, 22, password, contimeout=4, timeout=5) != 0:
        raise RuntimeError("SSH login with the admin password could not be confirmed.")
    gateway.passw = password


def finish_unlock(gateway, exec_cmd, contimeout=20, passw="root"):
    """Replace upstream post_connect: verify SSH; do not set boot/UART or use Telnet."""
    gateway.use_ssh = True
    gateway.ssh_port = 22
    gateway.passw = passw
    if not gateway.ping(verbose=0, contimeout=contimeout):
        raise RuntimeError("SSH authentication failed after connect5. No fallback or ROM preparation.")
    try:
        replace_temporary_password(gateway, gateway.webpassword)
    except Exception:
        print("SSH password update was not confirmed. The upstream temporary password may still be 'root'.")
        print("Stop here and change it from a trusted LAN before continuing.")
        raise
    print("SSH_UNLOCK_OK: port 22 authenticated; use root and your current web admin password.")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--router", required=True, type=ipaddress.IPv4Address)
    args = parser.parse_args()
    tool_root = Path.cwd()
    if not (tool_root / "connect5.py").is_file() or not (tool_root / "gateway.py").is_file():
        raise RuntimeError("Run through First-Flash.ps1 with the verified external snapshot.")
    sys.path.insert(0, str(tool_root))
    import gateway as upstream
    # XMiR stores its address in config.txt, and its passwords only in shared memory.
    # The caller provides a fresh ignored work folder for every run.
    gateway = upstream.Gateway(detect_device=False, detect_ssh=False, load_cfg=False)
    try:
        gateway.ip_addr = str(args.router)
        gateway.detect_device()
        require_target(gateway)
        print("TARGET_OK: RD03 1.0.98. Only the smartcontroller SSH method will be attempted.")
        password = getpass.getpass("Xiaomi web admin password (hidden): ")
        if not password or password != password.strip() or any(c in password for c in "\r\n\x00"):
            raise RuntimeError("A nonempty admin password without edge whitespace or newlines is required.")
        gateway.webpassword = password
        password = None
        gateway.web_login()
        gateway.post_connect = types.MethodType(finish_unlock, gateway)
        upstream.import_module("connect5", gateway)
        if gateway.check_ssh(gateway.ip_addr, 22, gateway.passw, contimeout=4, timeout=5) != 0:
            raise RuntimeError("Final authenticated SSH check failed; ROM preparation must not continue.")
    finally:
        gateway.webpassword = None
        gateway.passw = None
        gateway.shutdown()
        gateway.free_memcfg()
        gateway.memcfg = None


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("SSH_UNLOCK_FAILED: " + type(error).__name__ + ": " + str(error), file=sys.stderr)
        sys.exit(1)
