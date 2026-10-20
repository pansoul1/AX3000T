"""Offline regression checks; no SSH, router access or flash operations."""
import copy
import itertools
import json
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rd03.config import ROOT, FEATURES, RELEASE_SHA256, load_profile, validate_profile
from rd03.builder import verify_assets, payload_plan
from rd03.containers import validate_hdr1, repack_hdr1, repack_ubi
from rd03.formats import inspect_ubi, sha256
from rd03.patches import patch_branding_footer, patch_verifier
from rd03.filesystem import inventory, normalize


class ProfileTests(unittest.TestCase):
    def test_profile_matrix(self):
        manifest = verify_assets()
        accepted = 0
        for values in itertools.product([False, True], repeat=len(FEATURES)):
            flags = dict(zip(FEATURES, values))
            profile = {"name": "test", "branding": "测试版本", "features": flags}
            valid = not ((flags["sftp"] or flags["shellcrash"]) and not flags["ssh"])
            if not valid:
                with self.assertRaises(ValueError):
                    validate_profile(profile)
                continue
            validate_profile(profile)
            additions = payload_plan(profile, manifest)
            self.assertEqual("/usr/libexec/CrashCore" in additions, flags["shellcrash"])
            self.assertEqual("/usr/bin/crash" in additions, flags["shellcrash"])
            self.assertEqual("/usr/libexec/rd03-wol-api" in additions, flags["wol"])
            self.assertEqual("/usr/lib/lua/luci/controller/rd03_wol.lua" in additions, flags["wol"])
            self.assertEqual("/usr/lib/rd03-admin-auth.so" in additions, flags["ssh"])
            self.assertEqual("/usr/libexec/sftp-server" in additions, flags["sftp"])
            self.assertEqual("/usr/share/rd03-local/WOL" in additions, flags["wol"])
            self.assertEqual("/usr/share/rd03-local/SHELLCRASH" in additions, flags["shellcrash"])
            init = additions.get("/etc/init.d/rd03-local", {}).get("data", b"")
            self.assertEqual(b"rd03-shellcrash-prepare" in init, flags["shellcrash"])
            self.assertEqual(b"firewall.rd03_wol" in init, flags["wol"])
            accepted += 1
        self.assertEqual(accepted, 20)

    def test_bad_names_flags_and_dependencies_fail(self):
        p = load_profile(ROOT / "config/minimal.json")
        for field, bad in [("name", "../outside"), ("branding", "line\nbreak"), ("features", {"ssh": "false"})]:
            candidate = copy.deepcopy(p)
            candidate[field] = bad
            with self.assertRaises(ValueError):
                validate_profile(candidate)

    def test_branding_is_text_not_a_template(self):
        result = patch_branding_footer(b"<%=romVersion%> <%=romChannel%>", '<%os.execute("x")%><script>')
        self.assertNotIn(b"<%", result)
        self.assertNotIn(b"<script>", result)
        self.assertIn(b"&lt;", result)

    def test_tar_paths(self):
        self.assertEqual(normalize("./.hidden"), "/.hidden")
        self.assertEqual(normalize("./etc/config"), "/etc/config")
        for path in ["/absolute", "../escape", "etc/../../escape"]:
            with self.assertRaises(ValueError):
                normalize(path)


class ReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = (ROOT / "firmware/community-2.1/RD03-1.0.98-community-2.1-custom-web.bin").read_bytes()
        cls.parts = validate_hdr1(cls.data)

    def test_published_release_checksum(self):
        self.assertEqual(sha256(self.data), RELEASE_SHA256)
        self.assertEqual(set(self.parts), {"xiaoqiang_version", "firmware_ubi.bin"})

    def test_native_branch_matches_release_verifier(self):
        info = inspect_ubi(self.parts["firmware_ubi.bin"])
        _, fs = inventory(info["volumes"]["rootfs"]["payload"])
        data = fs.get("/bin/mkxqimage").open().read()
        self.assertEqual(sha256(data), "f078bd7dfb4775441d3dab7d7b972a681798bcff1d36d139dcdfe9b2674ab47c")
        with self.assertRaises(ValueError):
            patch_verifier(data)  # Double patching must not silently succeed.

    def test_release_profile_and_feature_markers(self):
        info = inspect_ubi(self.parts["firmware_ubi.bin"])
        rows, fs = inventory(info["volumes"]["rootfs"]["payload"])
        expected = load_profile(ROOT / "config/community-2.1.json")
        self.assertEqual(json.loads(fs.get("/usr/share/rd03-local/profile.json").open().read()), expected)
        self.assertIn(expected["branding"].encode(), fs.get("/usr/lib/lua/luci/view/web/inc/footer.htm").open().read())
        for path in ("/usr/share/rd03-local/WOL", "/usr/share/rd03-local/SHELLCRASH"):
            self.assertIn(path, rows)
        for path in rows:
            self.assertNotIn("pansoul", path.lower())
        for path in ("/usr/share/rd03-local/BUILD.txt", "/usr/libexec/rd03-shellcrash-install",
                     "/usr/libexec/rd03-shellcrash-prepare", "/usr/bin/rd03-space-clean"):
            self.assertNotIn(b"pansoul", fs.get(path).open().read().lower())

    def test_ubi_repack_preserves_release_bytes(self):
        data = self.parts["firmware_ubi.bin"]
        root = inspect_ubi(data)["volumes"]["rootfs"]["payload"]
        self.assertEqual(repack_ubi(data, root), data)

    def test_unsigned_hdr1_roundtrip(self):
        self.assertEqual(repack_hdr1(self.data, self.parts["firmware_ubi.bin"]), self.data)

    def test_corrupt_images_rejected(self):
        for position in [0, 8, 14, 48, 512, len(self.data) - 1]:
            broken = bytearray(self.data)
            broken[position] ^= 1
            with self.assertRaises(ValueError):
                validate_hdr1(bytes(broken))

    def test_overflow_rejected(self):
        broken = bytearray(self.data)
        struct.pack_into("<I", broken, 4, len(broken) + 1024)
        with self.assertRaises(ValueError):
            validate_hdr1(bytes(broken))


if __name__ == "__main__":
    unittest.main()
