"""Bounded, read-only FDT/FIT and UBI validators, independent of image generator."""
from __future__ import annotations

import hashlib
import struct
import zlib

PEB = 131072
DATA_OFFSET = 4096
LEB = PEB - DATA_OFFSET
LAYOUT_ID = 0x7FFFEFFF


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def cstring(data):
    return data.split(b"\0", 1)[0].decode("ascii", "replace")


def parse_fdt(data):
    require(len(data) >= 40, "Truncated FDT header")
    magic, size, so, strings_offset, reserve_offset, version, last, cpu, string_size, struct_size = struct.unpack_from(
        ">10I", data
    )
    require(magic == 0xD00DFEED and 40 <= size <= len(data), "Invalid FDT header/size")
    require(version in (16, 17) and last <= version, "Unsupported FDT version")
    require(40 <= so <= size and so + struct_size <= size, "FDT structure out of bounds")
    require(strings_offset + string_size <= size, "FDT strings out of bounds")
    strings = data[strings_offset:strings_offset + string_size]
    nodes = {}
    stack = []
    p = so
    ended = False
    while p + 4 <= so + struct_size:
        token = struct.unpack_from(">I", data, p)[0]
        p += 4
        if token == 1:
            end = data.index(0, p, so + struct_size)
            stack.append(data[p:end].decode("ascii"))
            p = (end + 4) & ~3
            path = "/" + "/".join(stack[1:])
            require(path not in nodes, "Duplicate FDT node")
            nodes[path] = {}
        elif token == 2:
            require(bool(stack), "Unbalanced FDT nodes")
            stack.pop()
        elif token == 3:
            require(bool(stack) and p + 8 <= so + struct_size, "Invalid FDT property")
            length, no = struct.unpack_from(">II", data, p)
            p += 8
            require(no < len(strings) and p + length <= so + struct_size, "FDT property out of bounds")
            end = strings.index(0, no)
            name = strings[no:end].decode("ascii")
            path = "/" + "/".join(stack[1:])
            require(name not in nodes[path], "Duplicate FDT property")
            nodes[path][name] = data[p:p + length]
            p = (p + length + 3) & ~3
        elif token == 4:
            continue
        elif token == 9:
            require(not stack, "FDT root not closed")
            ended = True
            break
        else:
            raise ValueError(f"Unknown FDT token {token}")
    require(ended, "Missing FDT end")
    return size, nodes


def inspect_fit(data):
    size, nodes = parse_fdt(data)
    require("/images" in nodes and "/configurations" in nodes, "Not a FIT image")
    images = {}
    for path, props in nodes.items():
        if not path.startswith("/images/") or path.count("/") != 2:
            continue
        require("data" in props, "External FIT data requires separate handling")
        payload = props["data"]
        checked = []
        for hash_path, hash_props in nodes.items():
            if not hash_path.startswith(path + "/") or "algo" not in hash_props:
                continue
            algorithm = cstring(hash_props["algo"])
            expected = hash_props.get("value")
            if algorithm in ("sha1", "sha256", "sha512", "md5"):
                actual = hashlib.new(algorithm, payload).digest()
            elif algorithm == "crc32":
                actual = struct.pack(">I", zlib.crc32(payload))
            else:
                raise ValueError(f"Unsupported FIT hash: {algorithm}")
            require(actual == expected, f"FIT hash mismatch: {hash_path}")
            checked.append(algorithm)
        require(checked, f"FIT image missing hash: {path}")
        images[path] = {
            "bytes": len(payload), "sha256": sha256(payload), "verified_hashes": checked,
            "type": cstring(props.get("type", b"")),
            "compression": cstring(props.get("compression", b"")),
        }
    require(bool(images), "FIT contains no image payloads")
    default = cstring(nodes["/configurations"].get("default", b""))
    require("/configurations/" + default in nodes, "Missing default FIT configuration")
    return {"fit_bytes": size, "sha256": sha256(data[:size]), "default_configuration": default, "images": images}, nodes


def inspect_squashfs(data):
    require(len(data) >= 96 and data[:4] == b"hsqs", "Missing SquashFS superblock")
    inode_count, mtime, block_size = struct.unpack_from("<III", data, 4)
    compression = struct.unpack_from("<H", data, 20)[0]
    major, minor = struct.unpack_from("<HH", data, 28)
    size = struct.unpack_from("<Q", data, 40)[0]
    require(major == 4 and 96 <= size <= len(data), "Invalid SquashFS version/size")
    return {"filesystem_bytes": size, "inode_count": inode_count, "mtime": mtime,
            "block_size": block_size, "compression_id": compression, "version": f"{major}.{minor}",
            "sha256": sha256(data[:size])}


def ubi_crc(data):
    # UBI stores Linux crc32_le(~0, data), without the final complement.
    return zlib.crc32(data) ^ 0xFFFFFFFF


def check_crc(record, context):
    require(len(record) >= 4, "Truncated CRC record")
    require(ubi_crc(record[:-4]) == struct.unpack_from(">I", record, len(record) - 4)[0],
            f"CRC mismatch: {context}")


def inspect_ubi(data):
    require(bool(data) and len(data) % PEB == 0, "UBI image not aligned to 128 KiB")
    tables = []
    volumes = {}
    blocks = {}
    eof = 0
    image_sequence = set()
    for peb_index in range(len(data) // PEB):
        peb = data[peb_index * PEB:(peb_index + 1) * PEB]
        ec = peb[:64]
        require(ec[:4] == b"UBI#" and ec[4] == 1, f"Invalid UBI EC header at PEB {peb_index}")
        check_crc(ec, f"PEB {peb_index} EC header")
        vid_offset, data_offset, sequence = struct.unpack_from(">III", ec, 16)
        require((vid_offset, data_offset) == (2048, 4096), "Unexpected UBI geometry")
        image_sequence.add(sequence)
        if ec[5:8] == b"EOF":
            require(peb[64:] == b"\xff" * (PEB - 64), "EOF block contains unexpected payload")
            eof += 1
            continue
        require(eof == 0, "Data follows UBI EOF blocks")
        vid = peb[vid_offset:vid_offset + 64]
        require(vid[:4] == b"UBI!" and vid[4] == 1, f"Invalid UBI VID header at PEB {peb_index}")
        check_crc(vid, f"PEB {peb_index} VID header")
        volume_id, lnum = struct.unpack_from(">II", vid, 8)
        require(vid[5] in (1, 2), "Unknown UBI volume type")
        if volume_id == LAYOUT_ID:
            require(lnum in (0, 1), "Invalid layout volume block number")
            require(vid[7] == 5, "Layout volume not reject-compatible")
            table = peb[data_offset:data_offset + 128 * 172]
            for volume in range(128):
                record = table[volume * 172:(volume + 1) * 172]
                check_crc(record, f"volume table record {volume}")
            tables.append((lnum, table))
        else:
            require(volume_id < 128 and (volume_id, lnum) not in blocks, "Duplicate/invalid UBI block")
            require(vid[5] == 1 and vid[6] == 0, "Unexpected static/copy volume in factory image")
            require(struct.unpack_from(">I", vid, 28)[0] == 0, "Nonzero UBI data padding unsupported")
            blocks[(volume_id, lnum)] = peb[data_offset:]
    require(len(image_sequence) == 1, "Mixed UBI image sequences")
    require(len(tables) == 2 and {i for i, _ in tables} == {0, 1}, "Missing redundant UBI volume tables")
    require(tables[0][1] == tables[1][1], "UBI volume tables differ")
    table = tables[0][1]
    for volume_id in range(128):
        record = table[volume_id * 172:(volume_id + 1) * 172]
        count, alignment, padding, kind, update, name_len = struct.unpack_from(">IIIBBH", record)
        if count == 0:
            continue
        require(alignment == 1 and padding == 0 and kind == 1 and update == 0,
                "Unexpected UBI volume attributes")
        require(0 < name_len <= 127, "Invalid UBI volume name length")
        name = record[16:16 + name_len].decode("ascii")
        require(name not in volumes, "Duplicate UBI volume name")
        indices = sorted(n for v, n in blocks if v == volume_id)
        require(indices == list(range(len(indices))) and len(indices) <= count, "Missing/out-of-bounds LEBs")
        payload = b"".join(blocks[(volume_id, i)] for i in indices)
        volumes[name] = {"volume_id": volume_id, "reserved_ebs": count,
                         "type": kind, "autoresize": bool(record[144] & 1),
                         "payload": payload, "payload_sha256": sha256(payload),
                         "payload_ebs": len(indices)}
    require(all(any(v["volume_id"] == volume for v in volumes.values()) for volume, _ in blocks),
            "Data belongs to undefined volume")
    return {"image_bytes": len(data), "peb_size": PEB, "vid_offset": 2048,
            "data_offset": DATA_OFFSET, "leb_size": LEB,
            "image_sequence": next(iter(image_sequence)), "eof_markers": eof,
            "pebs": len(data) // PEB, "volumes": volumes}


def public_ubi_report(report):
    result = {key: value for key, value in report.items() if key != "volumes"}
    result["volumes"] = {name: {key: value for key, value in volume.items() if key != "payload"}
                         for name, volume in report["volumes"].items()}
    return result


def xiaomi_components(data):
    require(data[:4] == b"HDR1", "Not Xiaomi HDR1 package")
    components = {}
    for offset in struct.unpack_from("<8I", data, 16):
        if not offset:
            continue
        require(offset + 48 <= len(data) and data[offset:offset + 4] == b"\xbe\xba\x00\x00",
                "Invalid Xiaomi component header")
        size = struct.unpack_from("<I", data, offset + 8)[0]
        name = cstring(data[offset + 16:offset + 48])
        require(name and name not in components and offset + 48 + size <= len(data),
                "Invalid Xiaomi component length/name")
        components[name] = data[offset + 48:offset + 48 + size]
    require(bool(components), "No Xiaomi components")
    return components
