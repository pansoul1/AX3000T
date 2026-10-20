#!/usr/bin/env python3
"""Offline RD03 firmware builder. Run --help; nothing is flashed by this program."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from rd03.config import ROOT, WORK, FEATURES, STOCK_SHA256, STOCK_URL, load_profile, validate_profile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("build", "plan"):
        p = sub.add_parser(name, help="Build a ROM" if name == "build" else "Check input and list the selected changes")
        p.add_argument("--rom", type=Path, required=True, help="Official RD03 1.0.98 HDR1 .bin")
        p.add_argument("--profile", type=Path, default=ROOT / "config/community-2.1.json")
        p.add_argument("--branding", help="Web footer and build label; no password or account information")
        p.add_argument("--name", help="Safe build output name")
        for flag in FEATURES:
            p.add_argument("--" + flag.replace("_", "-"), action=argparse.BooleanOptionalAction, default=None)
        if name == "build":
            p.add_argument("--output", type=Path, help="New destination directory (must not exist)")
            p.add_argument("--tools-dir", type=Path, help="squashfs-tools-ng directory, searched recursively")
    p = sub.add_parser("verify", help="Verify HDR1 CRC, RD03 model, UBI, FIT and SquashFS")
    p.add_argument("--image", type=Path, required=True)
    p.add_argument("--stock", type=Path, help="Also compare the kernel against the pinned official ROM")
    p = sub.add_parser("fetch-stock", help="Explicitly download the hash-pinned official image; no router connection")
    p.add_argument("--output", type=Path, default=WORK / "cache/miwifi_rd03_firmware_48abd_1.0.98.bin")
    p = sub.add_parser("prepare-web", help="Generate local files for a one-time SSH preparation; no router connection")
    p.add_argument("--rom", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    sub.add_parser("check-assets", help="Verify every bundled runtime payload against its manifest")
    args = parser.parse_args()
    if args.command == "fetch-stock":
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if args.output.exists():
            if hashlib.sha256(args.output.read_bytes()).hexdigest() == STOCK_SHA256:
                print("Already present; official ROM SHA256 passed.")
                return
            raise ValueError("Destination exists with a different checksum; choose a new output path")
        partial = args.output.with_suffix(args.output.suffix + ".part")
        with urllib.request.urlopen(STOCK_URL, timeout=60) as response, partial.open("wb") as f:
            while chunk := response.read(1024 * 1024):
                f.write(chunk)
        if hashlib.sha256(partial.read_bytes()).hexdigest() != STOCK_SHA256:
            raise ValueError("Downloaded official image checksum differs; .part was retained for inspection")
        partial.replace(args.output)
        print(f"Official ROM verified: {args.output}")
        return
    from rd03.builder import build, stock_image, verify_assets, planned_changes, payload_plan, write_json
    from rd03.containers import validate_hdr1
    from rd03.formats import inspect_ubi, inspect_fit, inspect_squashfs, sha256, require, public_ubi_report
    from rd03.filesystem import inventory
    if args.command == "check-assets":
        assets = verify_assets()
        print(f"Runtime payload checksums passed: {sum('source' in v for v in assets.values())} files")
    elif args.command in ("build", "plan"):
        profile = load_profile(args.profile)
        for flag in FEATURES:
            if getattr(args, flag) is not None:
                profile["features"][flag] = getattr(args, flag)
        for field in ("branding", "name"):
            if getattr(args, field) is not None:
                profile[field] = getattr(args, field)
        validate_profile(profile)
        if args.command == "build":
            destination = args.output or WORK / "output" / profile["name"]
            build(args.rom.resolve(), profile, destination.resolve(), args.tools_dir)
        else:
            _, _, _, _, _, _, fs = stock_image(args.rom)
            payloads = payload_plan(profile, verify_assets())
            print(json.dumps({"profile": profile, "changed_stock_files": sorted(planned_changes(profile, fs)),
                              "payload_files_and_links": sorted(payloads),
                              "uncompressed_payload_bytes": sum(len(p.get("data", b"")) for p in payloads.values()),
                              "router_actions": [], "stock_sha256_verified": True}, ensure_ascii=False, indent=2))
    elif args.command == "verify":
        data = args.image.read_bytes()
        parts = validate_hdr1(data)
        ubi = inspect_ubi(parts["firmware_ubi.bin"])
        require(set(ubi["volumes"]) == {"kernel", "rootfs"}, "Unexpected UBI volumes")
        require(len(parts["firmware_ubi.bin"]) <= 34 * 1024 ** 2 and ubi["eof_markers"] == 5, "Slot size / EOF mismatch")
        fit, _ = inspect_fit(ubi["volumes"]["kernel"]["payload"])
        sq = inspect_squashfs(ubi["volumes"]["rootfs"]["payload"])
        rows, _ = inventory(ubi["volumes"]["rootfs"]["payload"])
        if args.stock:
            baseline = stock_image(args.stock)[2]
            require(ubi["volumes"]["kernel"]["payload"] == baseline["volumes"]["kernel"]["payload"], "Kernel differs from official ROM")
        print(json.dumps({"sha256": sha256(data), "bytes": len(data), "ubi": public_ubi_report(ubi),
                          "fit": fit, "squashfs": sq, "filesystem_nodes": len(rows),
                          "kernel_compared": bool(args.stock), "vendor_rsa_verified": False,
                          "hardware_test": "not performed"}, ensure_ascii=False, indent=2))
    elif args.command == "prepare-web":
        from rd03.preparation import prepare
        prepare(args.rom, args.output)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, ImportError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
