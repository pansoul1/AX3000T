"""Strict profiles: invalid combinations are rejected before creating a ROM."""
from __future__ import annotations
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src"
WORK = ROOT / ".work"
FEATURES = ("ssh", "sftp", "wol", "shellcrash", "custom_web_upgrade")
STOCK_SHA256 = "042ba08949e547007710caa43830e574a7a7f5964119af4c457409b2fa8b4bce"
STOCK_URL = "https://cdn.cnbj1.fds.api.mi-img.com/xiaoqiang/rom/rd03/miwifi_rd03_firmware_48abd_1.0.98.bin"
RELEASE_SHA256 = "2a0c57548e5e7b62139ebcf897438f18a6fbefcaa59324aef615cd09e0740a6a"


def load_profile(path: Path) -> dict:
    profile = json.loads(path.read_text(encoding="utf-8-sig"))
    return validate_profile(profile)


def validate_profile(profile: dict) -> dict:
    if set(profile) != {"name", "branding", "features"}:
        raise ValueError("Profile must contain exactly name, branding and features")
    name, branding, flags = (profile[k] for k in ("name", "branding", "features"))
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,47}", name):
        raise ValueError("Profile name must be a safe 1-48 character filename")
    if not isinstance(branding, str) or not 1 <= len(branding) <= 64 or any(ord(c) < 32 or c == "\x7f" for c in branding):
        raise ValueError("Branding must be 1-64 characters without control characters")
    if not isinstance(flags, dict) or set(flags) != set(FEATURES) or any(type(v) is not bool for v in flags.values()):
        raise ValueError("Every supported feature must be explicitly true or false")
    if flags["sftp"] and not flags["ssh"]:
        raise ValueError("SFTP requires SSH")
    if flags["shellcrash"] and not flags["ssh"]:
        raise ValueError("The integrated ShellCrash installer/menu requires SSH")
    return profile
