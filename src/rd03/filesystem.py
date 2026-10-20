"""Preserve rootfs ownership, symlinks and special nodes through a tar stream."""
from __future__ import annotations
import copy
import io
from pathlib import Path, PurePosixPath
import tarfile
from dissect.squashfs import SquashFS
from .formats import sha256, require


def inventory(data: bytes):
    fs = SquashFS(io.BytesIO(data))
    todo, rows = [("/", fs.get("/"))], {}
    while todo:
        path, node = todo.pop()
        row = dict(type=node.type, mode=node.mode, uid=node.uid, gid=node.gid, mtime=node.header.mtime)
        if node.is_dir():
            todo.extend((path.rstrip("/") + "/" + child.name, child) for child in node.iterdir())
        elif node.is_file():
            payload = node.open().read()
            require(len(payload) == node.size, "Truncated rootfs file " + path)
            row.update(bytes=len(payload), sha256=sha256(payload))
        elif node.is_symlink():
            row["target"] = node.link
        elif node.is_device():
            row["rdev"] = node.header.rdev
        rows[path] = row
    return rows, fs


def normalize(name: str) -> str:
    posix = PurePosixPath(name)
    require(not posix.is_absolute() and ".." not in posix.parts, "Unsafe rootfs tar path")
    return "/" + str(posix) if str(posix) != "." else "/"


def edit_tar(source: Path, destination: Path, patches: dict, additions: dict, existing: dict, mtime: int):
    require(not set(additions).intersection(existing), "Payload collides with an official filesystem node")
    parents = set()
    for path in additions:
        parent = PurePosixPath(path).parent
        while str(parent) not in existing and str(parent) != "/":
            parents.add(str(parent))
            parent = parent.parent
    with tarfile.open(source, "r:") as src, tarfile.open(destination, "w", format=tarfile.PAX_FORMAT) as dst:
        seen = set()
        for old in src:
            member = copy.copy(old)
            path = normalize(member.name)
            require(path not in seen, "Duplicate official tar path " + path)
            seen.add(path)
            if path in patches:
                require(member.isfile(), "Attempted patch of a non-file node")
                data = patches[path]
                member.size = len(data)
                dst.addfile(member, io.BytesIO(data))
            elif member.isfile():
                dst.addfile(member, src.extractfile(old))
            else:
                dst.addfile(member)
        require(set(existing) == seen, "SquashFS-to-tar inventory differs from the official rootfs")
        for path in sorted(parents):
            member = tarfile.TarInfo(path.lstrip("/"))
            member.type, member.mode, member.mtime = tarfile.DIRTYPE, 0o755, mtime
            dst.addfile(member)
        for path, spec in sorted(additions.items()):
            member = tarfile.TarInfo(path.lstrip("/"))
            member.mode, member.mtime = spec["mode"], mtime
            if "target" in spec:
                member.type, member.linkname = tarfile.SYMTYPE, spec["target"]
                dst.addfile(member)
            else:
                member.size = len(spec["data"])
                dst.addfile(member, io.BytesIO(spec["data"]))
    return parents
