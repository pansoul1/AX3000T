"""Build unsigned HDR1 ROMs offline; this module has no router or flash client."""
from __future__ import annotations
import json
import os
from pathlib import Path
import shutil
import subprocess
import uuid
from .config import SOURCE, WORK, STOCK_SHA256
from .containers import validate_hdr1, repack_hdr1, repack_ubi
from .filesystem import inventory, edit_tar
from .formats import sha256, require, inspect_ubi, inspect_fit, inspect_squashfs, public_ubi_report
from .patches import patch_dropbear, patch_verifier, patch_wol_header, patch_branding_footer, local_init, replace_once


def write_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def tool(name: str, tools_dir: Path | None) -> str:
    for folder in [tools_dir, WORK / "cache/tools"]:
        if folder and folder.is_dir():
            candidates = sorted(folder.rglob(name + (".exe" if os.name == "nt" else "")))
            if candidates:
                return str(candidates[0].resolve())
    result = shutil.which(name)
    require(bool(result), f"Missing {name}. Install squashfs-tools-ng, or pass --tools-dir.")
    return result


def stock_image(path: Path):
    original = path.read_bytes()
    require(sha256(original) == STOCK_SHA256, "Only the pinned official RD03 1.0.98 ROM is supported; input SHA256 differs")
    parts = validate_hdr1(original)
    ubi = inspect_ubi(parts["firmware_ubi.bin"])
    require(set(ubi["volumes"]) == {"kernel", "rootfs"}, "Unexpected stock UBI volumes")
    fit, _ = inspect_fit(ubi["volumes"]["kernel"]["payload"])
    root = ubi["volumes"]["rootfs"]["payload"]
    rows, fs = inventory(root)
    return original, parts, ubi, fit, root, rows, fs


def verify_assets() -> dict:
    # Manifest source paths are relative to src/, alongside the payload tree.
    manifest = json.loads((SOURCE / "payloads/manifest.json").read_text(encoding="utf-8"))
    for path, item in manifest.items():
        if "source" not in item:
            continue
        source = (SOURCE / item["source"]).resolve()
        require(source.is_relative_to((SOURCE / "payloads").resolve()), "Invalid payload source path")
        data = source.read_bytes()
        require(len(data) == item["bytes"] and sha256(data) == item["sha256"], "Payload checksum mismatch: " + path)
    return manifest


def payload_plan(profile, manifest):
    flags = profile["features"]
    additions = {}
    skip = {"/etc/init.d/rd03-local", "/etc/rc.d/S18rd03-local", "/usr/share/rd03-local/BUILD.txt"}
    for path, item in manifest.items():
        if path in skip:
            continue
        if path.endswith("/PANSOUL1") and not flags["wol"]:
            continue
        if path.endswith("/PANSOUL2") and not flags["shellcrash"]:
            continue
        if item["module"] != "common" and not flags[item["module"]]:
            continue
        if "source" in item:
            additions[path] = {"data": (SOURCE / item["source"]).read_bytes(), "mode": item["mode"] & 0o7777}
        elif "target" in item:
            additions[path] = {"target": item["target"], "mode": item["mode"] & 0o7777}
    if flags["wol"] or flags["shellcrash"]:
        additions["/etc/init.d/rd03-local"] = {"data": local_init(flags["wol"], flags["shellcrash"]), "mode": 0o755}
        additions["/etc/rc.d/S18rd03-local"] = {"target": "../init.d/rd03-local", "mode": 0o777}
    label = profile["branding"] + "\nXiaomi RD03 stock 1.0.98; unsigned community build.\n"
    label += "Features: " + ", ".join(k for k, v in flags.items() if v) + "\n"
    additions["/usr/share/rd03-local/BUILD.txt"] = {"data": label.encode(), "mode": 0o644}
    additions["/usr/share/rd03-local/profile.json"] = {
        "data": (json.dumps(profile, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode(), "mode": 0o644}
    return additions


def planned_changes(profile, fs):
    flags = profile["features"]
    read = lambda p: fs.get(p).open().read()
    patches = {}
    if flags["ssh"]:
        patches["/etc/init.d/dropbear"] = patch_dropbear(read("/etc/init.d/dropbear"))
    if flags["wol"]:
        p = "/usr/lib/lua/luci/view/web/inc/header.htm"
        patches[p] = patch_wol_header(read(p))
    if flags["shellcrash"]:
        p = "/etc/sysctl.conf"
        patches[p] = replace_once(read(p), b"vm.panic_on_oom=2", b"vm.panic_on_oom=0")
    if flags["custom_web_upgrade"]:
        patches["/bin/mkxqimage"] = patch_verifier(read("/bin/mkxqimage"))
    p = "/usr/lib/lua/luci/view/web/inc/footer.htm"
    patches[p] = patch_branding_footer(read(p), profile["branding"])
    return patches


def run_tool(command, log: Path, env=None, source=None, target=None):
    with log.open("wb") as errors:
        proc = subprocess.run(command, stdin=source, stdout=target or errors, stderr=errors, env=env)
    require(proc.returncode == 0, f"Tool failed ({proc.returncode}); see {log.name}")


def build(rom: Path, profile: dict, output: Path, tools_dir: Path | None = None):
    manifest = verify_assets()
    original, parts, ubi, fit, root, rows, fs = stock_image(rom)
    patches, additions = planned_changes(profile, fs), payload_plan(profile, manifest)
    sq = inspect_squashfs(root)
    # Resolve the toolchain before creating a partially built output directory.
    exporter, compressor = tool("sqfs2tar", tools_dir), tool("tar2sqfs", tools_dir)
    require(not output.exists(), "Output directory already exists; choose a new --output path")
    output.mkdir(parents=True)
    work = WORK / "build" / (profile["name"] + "-" + uuid.uuid4().hex[:12])
    work.mkdir(parents=True)
    (work / "original.squashfs").write_bytes(root)
    print("Exporting the official filesystem with ownership and special nodes...", flush=True)
    with (work / "original.tar").open("wb") as dst:
        run_tool([exporter, "--no-skip", "--root-becomes", ".", str(work / "original.squashfs")], work / "sqfs2tar.log", target=dst)
    directories = edit_tar(work / "original.tar", work / "rootfs.tar", patches, additions, rows, sq["mtime"])
    env = os.environ.copy()
    env["SOURCE_DATE_EPOCH"] = str(sq["mtime"])
    print("Compressing the selected features...", flush=True)
    with (work / "rootfs.tar").open("rb") as src:
        run_tool([compressor, "--no-skip", "--compressor", "xz", "--comp-extra", "dictsize=262144,level=9",
                  "--block-size", "262144", "--force", "--quiet", str(work / "rootfs.squashfs")],
                 work / "tar2sqfs.log", env=env, source=src)
    new_root = (work / "rootfs.squashfs").read_bytes()
    new_rows, new_fs = inventory(new_root)
    print("Checking every official file, payload and filesystem attribute...", flush=True)
    for path, row in rows.items():
        require(path in new_rows, "Official node was removed: " + path)
        if path in patches:
            require(new_fs.get(path).open().read() == patches[path], "Patched file differs: " + path)
            metadata = lambda r: {k: v for k, v in r.items() if k not in ("bytes", "sha256")}
            require(metadata(new_rows[path]) == metadata(row), "Patched file metadata changed: " + path)
        else:
            require(new_rows[path] == row, "Unplanned official file change: " + path)
    require(set(new_rows) - set(rows) == set(additions) | directories, "Unexpected added filesystem nodes")
    for path, spec in additions.items():
        row = new_rows[path]
        require((row["mode"] & 0o7777) == spec["mode"] and row["uid"] == row["gid"] == 0 and row["mtime"] == sq["mtime"], "Wrong payload metadata: " + path)
        if "data" in spec:
            require(new_fs.get(path).open().read() == spec["data"], "Wrong payload content: " + path)
        else:
            require(row["target"] == spec["target"], "Wrong payload link: " + path)
    new_sq = inspect_squashfs(new_root)
    size = (new_sq["filesystem_bytes"] + 1023) & ~1023
    padded = new_root[:new_sq["filesystem_bytes"]] + bytes(size - new_sq["filesystem_bytes"])
    raw = repack_ubi(parts["firmware_ubi.bin"], padded)
    final_ubi = inspect_ubi(raw)
    require(inventory(final_ubi["volumes"]["rootfs"]["payload"])[0] == new_rows, "UBI rootfs inventory differs")
    result = repack_hdr1(original, raw)
    name = f'RD03-1.0.98-{profile["name"]}-custom-web.bin'
    # Deliver the ROM only after all offline verification has passed.
    (output / name).write_bytes(result)
    (output / "SHA256SUMS").write_text(sha256(result) + "  " + name + "\n", encoding="ascii", newline="\n")
    report = {
        "profile": profile, "stock_sha256": STOCK_SHA256, "sha256": sha256(result), "bytes": len(result),
        "ubi": public_ubi_report(final_ubi), "system_slot_bytes": 34 * 1024 ** 2,
        "slot_margin_bytes": 34 * 1024 ** 2 - len(raw), "squashfs": new_sq,
        "kernel_identical": True, "kernel_fit": fit,
        "changed_stock_files": sorted(patches), "added_files_and_links": sorted(additions),
        "added_directories": sorted(directories), "removed_stock_nodes": [],
        "all_other_official_content_and_metadata_identical": True,
        "components": sorted(validate_hdr1(result)), "vendor_signature_valid": False,
        "private_configuration_included": False, "hardware_test": "NOT PERFORMED for this newly generated ROM",
        "toolchain": {"sqfs2tar": Path(exporter).name, "tar2sqfs": Path(compressor).name},
    }
    write_json(output / "build-report.json", report)
    write_json(output / "profile.json", profile)
    write_json(output / "filesystem-inventory.json", new_rows)
    print(f"Built {output / name}\nSHA256: {sha256(result)}\nSlot margin: {report['slot_margin_bytes']} bytes", flush=True)
    return report
