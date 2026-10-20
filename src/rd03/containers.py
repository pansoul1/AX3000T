"""Repack only the stock HDR1 system component and its two UBI volumes."""
from __future__ import annotations
import struct
import zlib
from .formats import PEB, LEB, DATA_OFFSET, LAYOUT_ID, require, check_crc, ubi_crc, inspect_ubi, xiaomi_components


def validate_hdr1(data: bytes) -> dict:
    require(len(data) >= 144 + 272 and data[:4] == b"HDR1", "Not a complete Xiaomi HDR1 image")
    signature = struct.unpack_from("<I", data, 4)[0]
    require(signature == len(data) - 272, "Unexpected signature segment length/offset")
    require(struct.unpack_from("<I", data, 8)[0] == (zlib.crc32(data[12:]) ^ 0xffffffff), "HDR1 CRC mismatch")
    require(struct.unpack_from("<HH", data, 12) == (0, 75), "Only Xiaomi RD03 (model 75) is supported")
    offsets = [x for x in struct.unpack_from("<8I", data, 16) if x]
    require(len(offsets) == 2 and offsets[0] == 144, "Unexpected HDR1 component layout")
    end = 144
    for offset in offsets:
        require(offset == end and offset + 48 <= signature, "HDR1 gap/overlap/out-of-bounds section")
        end = offset + 48 + struct.unpack_from("<I", data, offset + 8)[0]
        require(end <= signature, "HDR1 section overlaps signature")
    require(end == signature, "Unexpected trailing HDR1 component data")
    parts = xiaomi_components(data)
    require(set(parts) == {"xiaoqiang_version", "firmware_ubi.bin"}, "Unexpected bootloader or other component")
    return parts


def repack_hdr1(original: bytes, firmware: bytes) -> bytes:
    parts = validate_hdr1(original)
    second = struct.unpack_from("<I", original, 20)[0]
    out = bytearray(original[:second + 48])
    struct.pack_into("<I", out, second + 8, len(firmware))
    out.extend(firmware)
    sign = len(out)
    old_sign = struct.unpack_from("<I", original, 4)[0]
    out.extend(original[old_sign:old_sign + 16])
    out.extend(bytes(256))  # Explicitly unsigned, never pretend to preserve a vendor signature.
    struct.pack_into("<I", out, 4, sign)
    struct.pack_into("<I", out, 8, zlib.crc32(out[12:]) ^ 0xffffffff)
    result = bytes(out)
    final = validate_hdr1(result)
    require(final["xiaoqiang_version"] == parts["xiaoqiang_version"], "Stock update metadata changed")
    return result


def repack_ubi(original: bytes, rootfs: bytes) -> bytes:
    """Reuse geometry/headers from a validated official image; never resize NAND slots."""
    info = inspect_ubi(original)
    require(set(info["volumes"]) == {"kernel", "rootfs"}, "Unexpected UBI volume set")
    require(info["eof_markers"] == 5, "Expected the Xiaomi 5 EOF marker convention")
    root_id = info["volumes"]["rootfs"]["volume_id"]
    kernel_id = info["volumes"]["kernel"]["volume_id"]
    require((kernel_id, root_id) == (0, 1), "Unexpected UBI volume ids")
    layouts, kernels, root_template, eof = [], [], None, []
    for index in range(len(original) // PEB):
        peb = original[index * PEB:(index + 1) * PEB]
        if peb[5:8] == b"EOF":
            eof.append(peb)
            continue
        vid = peb[2048:2112]
        vid_id = struct.unpack_from(">I", vid, 8)[0]
        if vid_id == LAYOUT_ID:
            layouts.append(peb)
        elif vid_id == kernel_id:
            kernels.append(peb)
        elif vid_id == root_id and root_template is None:
            root_template = peb
    require(root_template is not None, "Missing rootfs block template")
    count = (len(rootfs) + LEB - 1) // LEB
    result = []
    for peb in layouts:
        patched = bytearray(peb)
        start = DATA_OFFSET + root_id * 172
        struct.pack_into(">I", patched, start, count)
        struct.pack_into(">I", patched, start + 168, ubi_crc(patched[start:start + 168]))
        result.append(bytes(patched))
    result.extend(kernels)
    for number in range(count):
        head = bytearray(root_template[:DATA_OFFSET])
        struct.pack_into(">I", head, 2048 + 12, number)
        struct.pack_into(">I", head, 2048 + 60, ubi_crc(head[2048:2048 + 60]))
        chunk = rootfs[number * LEB:(number + 1) * LEB]
        result.append(bytes(head) + chunk + b"\xff" * (LEB - len(chunk)))
    result.extend(eof)
    out = b"".join(result)
    final = inspect_ubi(out)
    require(len(out) <= 34 * 1024 ** 2, "Image exceeds the original 34 MiB system slot")
    require(final["volumes"]["kernel"]["payload"] == info["volumes"]["kernel"]["payload"], "Kernel volume changed")
    require(final["volumes"]["rootfs"]["payload"].startswith(rootfs), "Rootfs repack mismatch")
    return out
