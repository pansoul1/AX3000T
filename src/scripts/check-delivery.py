#!/usr/bin/env python3
"""Check built feature combinations and their exact difference from the official ROM."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from rd03.builder import stock_image, planned_changes, payload_plan, verify_assets
from rd03.containers import validate_hdr1
from rd03.filesystem import inventory
from rd03.formats import inspect_ubi, require, sha256

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--stock", type=Path, required=True)
parser.add_argument("--build", type=Path, action="append", required=True, help="Generated output directory; repeatable")
parser.add_argument("--report", type=Path)
args = parser.parse_args()
_, _, official_ubi, _, _, official_rows, fs = stock_image(args.stock)
manifest = verify_assets()
reports = []
for folder in args.build:
    profile = json.loads((folder / "profile.json").read_text(encoding="utf-8"))
    images = list(folder.glob("*.bin"))
    require(len(images) == 1, "Expected one output image")
    data = images[0].read_bytes()
    parts = validate_hdr1(data)
    ubi = inspect_ubi(parts["firmware_ubi.bin"])
    rows, output_fs = inventory(ubi["volumes"]["rootfs"]["payload"])
    require(ubi["volumes"]["kernel"]["payload"] == official_ubi["volumes"]["kernel"]["payload"], "Kernel differs")
    planned, additions = planned_changes(profile, fs), payload_plan(profile, manifest)
    changed = []
    for path, value in official_rows.items():
        require(path in rows, "Official node removed")
        if value != rows[path]:
            changed.append(path)
            require(path in planned and output_fs.get(path).open().read() == planned[path], "Unexpected stock modification")
    require(set(changed) == set(planned), "Planned stock modification missing")
    flags = profile["features"]
    for feature, path in [("ssh", "/usr/lib/rd03-admin-auth.so"), ("sftp", "/usr/libexec/sftp-server"),
                          ("wol", "/usr/libexec/rd03-wol-api"), ("shellcrash", "/usr/libexec/CrashCore")]:
        require((path in rows) == flags[feature], "Disabled feature leaked into rootfs: " + feature)
    report = {
        "name": profile["name"], "profile": profile, "sha256": sha256(data), "bytes": len(data),
        "system_ubi_bytes": len(parts["firmware_ubi.bin"]), "kernel_identical": True,
        "changed_stock_files": sorted(changed), "selected_payloads_verified": len(additions),
        "disabled_components_absent": True, "original_stock_nodes_removed": [],
        "hardware_test": "NOT PERFORMED",
    }
    reports.append(report)
    print(f'{report["name"]}: verified, {len(data)} bytes, kernel identical, disabled components absent')
if args.report:
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps({"kind": "offline acceptance", "builds": reports}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
