"""Exercise first-flash failure gates with fake gateways; never contact a router."""
import contextlib
import importlib.util
import io
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "first_flash_unlock", Path(__file__).resolve().parents[1] / "scripts/unlock-stock-ssh.py"
)
unlock = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(unlock)


class FakeChannel:
    def __init__(self, status=0):
        self.command = None
        self.stdin = b""
        self.status = status

    def execute(self, command):
        self.command = command

    def write(self, data):
        # Exercise the adapter's partial-write handling.
        count = min(3, len(data))
        self.stdin += data[:count]
        return 0, count

    def send_eof(self):
        pass

    def wait_eof(self):
        pass

    def close(self):
        pass

    def wait_closed(self):
        pass

    def get_exit_status(self):
        return self.status


class FakeGateway:
    def __init__(self, model="RD03", version="1.0.98", channel_status=0):
        self.status = 1
        self.device_name = model
        self.rom_version = version
        self.ip_addr = "192.0.2.1"
        self.webpassword = "example-test-admin-password"
        self.passw = None
        self.channel = FakeChannel(channel_status)
        self.auth_calls = []
        self.closed = False
        self.freed = False
        self.memcfg = object()

    def get_ssh(self, **kwargs):
        return SimpleNamespace(open_session=lambda: self.channel)

    def check_ssh(self, ip, port, password, **kwargs):
        self.auth_calls.append((ip, port, password))
        return 0

    def ping(self, **kwargs):
        return True

    def shutdown(self):
        self.closed = True

    def free_memcfg(self):
        self.freed = True

    def detect_device(self):
        pass

    def web_login(self):
        pass


class FirstFlashTests(unittest.TestCase):
    def test_unknown_targets_rejected(self):
        for model, version in [("RD03v2", "1.0.98"), ("RD23", "1.0.98"), ("RD03", "1.0.64")]:
            with self.subTest(model=model, version=version), self.assertRaises(RuntimeError):
                unlock.require_target(FakeGateway(model, version))

    def test_password_travels_in_stdin_only(self):
        gateway = FakeGateway()
        password = gateway.webpassword
        unlock.replace_temporary_password(gateway, password)
        self.assertEqual(gateway.channel.command, "passwd root >/dev/null 2>&1")
        self.assertNotIn(password, gateway.channel.command)
        self.assertEqual(gateway.channel.stdin, ((password + "\n") * 2).encode())
        self.assertEqual(gateway.auth_calls, [(gateway.ip_addr, 22, password)])
        self.assertTrue(gateway.closed)

    def test_password_command_failure_stops_before_auth(self):
        gateway = FakeGateway(channel_status=1)
        with self.assertRaises(RuntimeError):
            unlock.replace_temporary_password(gateway, gateway.webpassword)
        self.assertFalse(gateway.auth_calls)
        self.assertTrue(gateway.closed)

    def test_failed_initial_ssh_does_not_run_password_command(self):
        gateway = FakeGateway()
        gateway.ping = lambda **kwargs: False
        with self.assertRaises(RuntimeError):
            unlock.finish_unlock(gateway, lambda command: self.fail("Unexpected fallback command"))
        self.assertIsNone(gateway.channel.command)

    def test_main_uses_only_connect5_and_clears_credentials(self):
        gateway = FakeGateway()
        imported = []

        def import_module(name, active_gateway):
            imported.append(name)
            active_gateway.post_connect(lambda command: self.fail("Unexpected boot/Telnet fallback"))

        upstream = SimpleNamespace(Gateway=lambda **kwargs: gateway, import_module=import_module)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "connect5.py").touch()
            (root / "gateway.py").touch()
            with patch.object(unlock.Path, "cwd", return_value=root), \
                 patch.object(unlock.sys, "argv", ["unlock-stock-ssh.py", "--router", "192.0.2.1"]), \
                 patch.dict(unlock.sys.modules, {"gateway": upstream}), \
                 patch.object(unlock.sys, "path", list(unlock.sys.path)), \
                 patch.object(unlock.getpass, "getpass", return_value=gateway.webpassword), \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                unlock.main()
        self.assertEqual(imported, ["connect5"])
        self.assertIn("SSH_UNLOCK_OK", output.getvalue())
        self.assertIsNone(gateway.webpassword)
        self.assertIsNone(gateway.passw)
        self.assertIsNone(gateway.memcfg)
        self.assertTrue(gateway.freed)

    def test_main_rejects_wrong_version_before_asking_for_password(self):
        gateway = FakeGateway(version="2.0.12")
        upstream = SimpleNamespace(Gateway=lambda **kwargs: gateway)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "connect5.py").touch()
            (root / "gateway.py").touch()
            with patch.object(unlock.Path, "cwd", return_value=root), \
                 patch.object(unlock.sys, "argv", ["unlock-stock-ssh.py", "--router", "192.0.2.1"]), \
                 patch.dict(unlock.sys.modules, {"gateway": upstream}), \
                 patch.object(unlock.sys, "path", list(unlock.sys.path)), \
                 patch.object(unlock.getpass, "getpass") as prompt, self.assertRaises(RuntimeError):
                unlock.main()
                self.fail("Unknown version accepted")
        prompt.assert_not_called()
        self.assertTrue(gateway.freed)


if __name__ == "__main__":
    unittest.main()
