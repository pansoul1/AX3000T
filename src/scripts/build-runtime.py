#!/usr/bin/env python3
"""Compile runtime source into .work/build/runtime, leaving pinned payloads unchanged."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("component", choices=["wol", "ssh"])
parser.add_argument("--cc", default="zig", help="AArch64 musl C compiler, or zig")
args = parser.parse_args()
out = ROOT / ".work/build/runtime"
out.mkdir(parents=True, exist_ok=True)
if args.component == "wol":
    env = os.environ.copy()
    go = shutil.which("go")
    if not go:
        parser.error("Install Go 1.22+ and place go in PATH")
    subprocess.run([go, "test", "./..."], cwd=ROOT / "src/sources/wol", check=True, env=env)
    env.update(GOOS="linux", GOARCH="arm64", CGO_ENABLED="0")
    subprocess.run([go, "build", "-trimpath", "-ldflags=-s -w -buildid=", "-o", str(out / "rd03-wol-api"), "."],
                   cwd=ROOT / "src/sources/wol", check=True, env=env)
else:
    command = [args.cc]
    if Path(args.cc).stem == "zig":
        command += ["cc", "-target", "aarch64-linux-musl"]
    command += ["-shared", "-fPIC", "-Os", "-s", "-Wall", "-Wextra", "-Werror",
                str(ROOT / "src/sources/ssh/rd03-admin-auth.c"), "-o", str(out / "rd03-admin-auth.so")]
    subprocess.run(command, check=True)
print(f"Compiled {args.component} to {out}. Pinned payloads and manifest were not changed.")
print("Review ABI/runtime behavior before replacing a payload and updating its checksum.")
