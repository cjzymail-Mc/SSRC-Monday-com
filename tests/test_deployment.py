import base64
from contextlib import closing
import http.client
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import flowboard_deploy as deploy
from flowboard.database import SCHEMA_VERSION, connect, migrate
from flowboard.operations import create_backup, verify_backup
from flowboard.service import FlowboardService
from test_secure_foundation import create_legacy_database


ROOT = Path(__file__).resolve().parents[1]


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        (ROOT / "local-test-data").mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="deploy-test-", dir=ROOT / "local-test-data")
        self.root = Path(self.temp.name)
        self.app = self.root / "app"
        self.app.mkdir()
        shutil.copytree(ROOT / "flowboard", self.app / "flowboard", ignore=shutil.ignore_patterns("__pycache__"))
        for name in ("flowboard_deploy.py", "server.py", "index.html", "start-flowboard.cmd", "install-flowboard.cmd", "update-flowboard.cmd"):
            shutil.copy2(ROOT / name, self.app / name)
        (self.app / ".gitignore").write_text("__pycache__/\n*.pyc\n", encoding="utf-8")
        self.config = self.root / "host 配置.json"
        self.data = self.root / "正式 数据"
        self.backups = self.root / "备份"
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            self.port = probe.getsockname()[1]
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("FLOWBOARD_")}
        self.env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
        self.source = self.root / "source.db"
        create_legacy_database(self.source)
        migrate(self.source, initial_password="deployment-test-password")
        self.source_blobs = self.root / "source-blobs"
        with patch.dict(os.environ, {"FLOWBOARD_ATTACHMENT_DIR": str(self.source_blobs)}):
            service = FlowboardService(self.source)
            with closing(connect(self.source)) as conn:
                admin = dict(conn.execute("SELECT * FROM users WHERE id='u1'").fetchone())
            service.create_attachment(admin, 1, {"name": "部署附件.txt", "content_type": "text/plain",
                                                 "content_base64": base64.b64encode(b"deployment blob sentinel").decode()})
        self.package = create_backup(self.source, self.source_blobs, self.root / "source-backups")

    def tearDown(self):
        self.temp.cleanup()

    def command(self, *args, expected=0):
        result = subprocess.run([sys.executable, "-X", "utf8", str(self.app / "flowboard_deploy.py"), *args],
                                cwd=self.app, env=self.env, capture_output=True, text=True, encoding="utf-8", timeout=40)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def install(self):
        return self.command("install", "--package", str(self.package), "--config", str(self.config),
                            "--data-dir", str(self.data), "--backup-dir", str(self.backups),
                            "--host", "127.0.0.1", "--port", str(self.port))

    def settings(self):
        return deploy.load_settings(self.config, env={}, app=self.app)

    def init_git(self):
        self.git("init", "--initial-branch=main")
        self.git("config", "user.name", "Deployment Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "core.autocrlf", "false")
        self.git("add", ".")
        self.git("commit", "-m", "Fixture baseline")
        remote = self.root / "remote.git"
        subprocess.run(["git", "init", "--bare", str(remote)], env=self.env, check=True, capture_output=True)
        self.git("remote", "add", "origin", str(remote))
        self.git("push", "-u", "origin", "main")

    def git(self, *args):
        result = subprocess.run(["git", "-C", str(self.app), *args], env=self.env, capture_output=True,
                                text=True, encoding="utf-8", errors="replace", timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def version_19(self):
        with closing(connect(self.data / "flowboard.db")) as conn:
            conn.execute("DROP TABLE timeline_member_orders")
            conn.execute("DELETE FROM schema_migrations WHERE version=20")
            conn.execute("PRAGMA user_version=19")
            conn.commit()

    def test_configuration_relative_paths_environment_and_missing_file(self):
        self.config.write_text(json.dumps({"format_version": 1, "data_dir": "正式 数据", "backup_dir": "备份",
                                           "port": 8082, "secure_cookie": True}), encoding="utf-8")
        settings = deploy.load_settings(self.config, app=self.app, env={"FLOWBOARD_PORT": "8091", "FLOWBOARD_SECURE_COOKIE": ""})
        self.assertEqual(settings.db, self.data / "flowboard.db")
        self.assertEqual(settings.port, 8091)
        self.assertFalse(settings.secure_cookie)
        with self.assertRaises(deploy.DeploymentError):
            deploy.load_settings(self.root / "missing.json", app=self.app, env={})
        self.assertFalse((self.app / "flowboard.db").exists())

    def test_install_dry_run_then_real_restore_preserves_accounts_and_blobs(self):
        args = ("install", "--package", str(self.package), "--config", str(self.config),
                "--data-dir", str(self.data), "--backup-dir", str(self.backups), "--port", str(self.port))
        self.command(*args, "--check")
        self.assertFalse(self.config.exists())
        self.assertFalse(self.data.exists())
        self.command(*args)
        with closing(connect(self.source)) as before, closing(connect(self.data / "flowboard.db")) as after:
            self.assertEqual(before.execute("SELECT id,username,password_hash FROM users ORDER BY id").fetchall(),
                             after.execute("SELECT id,username,password_hash FROM users ORDER BY id").fetchall())
            storage = after.execute("SELECT storage_name FROM attachments").fetchone()[0]
            self.assertEqual(after.execute("SELECT COUNT(*) FROM tasks").fetchone()[0], 5)
        self.assertEqual((self.data / "attachments" / storage).read_bytes(), b"deployment blob sentinel")
        self.command(*args, expected=3)
        records = list(self.backups.glob("deployment-*.json"))
        self.assertEqual(len(records), 1)
        record = json.loads(records[0].read_text(encoding="utf-8"))
        self.assertEqual(record["status"], "READY")
        self.assertEqual(len(verify_backup(record["backup_package"])["attachments"]), 1)

    def test_install_rejects_corrupt_package_and_data_in_code_checkout(self):
        (self.package / "flowboard.db").write_bytes(b"corrupt")
        self.command("install", "--package", str(self.package), "--config", str(self.config),
                     "--data-dir", str(self.data), "--backup-dir", str(self.backups), expected=3)
        self.assertFalse(self.config.exists())
        self.assertFalse(self.data.exists())
        self.command("install", "--package", str(self.package), "--config", str(self.app / "host.json"), expected=3)

    def test_missing_database_and_schema_mismatch_do_not_initialize(self):
        self.install()
        self.version_19()
        self.command("start", "--config", str(self.config), "--check", expected=3)
        self.assertEqual(deploy.check_database(self.data / "flowboard.db", allow_older=True)["schema_version"], 19)
        missing = deploy.Settings(self.app, None, self.root / "absent.db", self.root / "blobs", self.root / "safe", "127.0.0.1", self.port, False, "origin/main")
        with self.assertRaises(deploy.DeploymentError):
            deploy.start(missing, check_only=True)
        self.assertFalse(missing.db.exists())

    def test_legacy_launcher_preserves_explicit_environment_paths(self):
        self.env.update(FLOWBOARD_DB=str(self.source), FLOWBOARD_ATTACHMENT_DIR=str(self.source_blobs),
                        FLOWBOARD_BACKUP_DIR=str(self.root / "legacy-safe"), FLOWBOARD_PORT=str(self.port))
        checked = self.command("start", "--check")
        self.assertEqual(json.loads(checked.stdout)["database"], str(self.source))
        self.assertFalse((self.app / "flowboard.db").exists())

    def test_upgrade_real_v19_keeps_a_restorable_backup_and_business_data(self):
        self.install()
        self.version_19()
        self.command("upgrade", "--config", str(self.config))
        self.command("start", "--config", str(self.config), "--check")
        record = next(json.loads(p.read_text(encoding="utf-8")) for p in self.backups.glob("deployment-*.json")
                      if json.loads(p.read_text(encoding="utf-8"))["action"] == "upgrade")
        self.assertEqual(record["schema_before"], 19)
        self.assertEqual(record["schema_after"], 20)
        self.assertEqual(verify_backup(record["backup_package"])["schema_version"], 19)
        with closing(connect(self.data / "flowboard.db")) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0], 5)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM attachments").fetchone()[0], 1)

    def test_busy_port_and_active_host_lock_block_mutations(self):
        self.install()
        before = {p.name for p in self.backups.iterdir()}
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", self.port))
            listener.listen()
            self.command("upgrade", "--config", str(self.config), expected=3)
        self.assertEqual(before, {p.name for p in self.backups.iterdir()})
        self.settings().lock.write_text("protected-owner", encoding="ascii")
        self.command("upgrade", "--config", str(self.config), expected=3)
        self.assertEqual(self.settings().lock.read_text(), "protected-owner")
        self.settings().lock.unlink()

    def test_fast_forward_update_uses_the_new_code_schema_and_preserves_config(self):
        self.install()
        self.version_19()
        database_py = self.app / "flowboard" / "database.py"
        current_source = database_py.read_text(encoding="utf-8")
        database_py.write_text(current_source.replace("SCHEMA_VERSION = 20", "SCHEMA_VERSION = 19"), encoding="utf-8")
        self.init_git()
        before = self.git("rev-parse", "HEAD")
        database_py.write_text(current_source, encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-m", "Fixture release v20")
        target = self.git("rev-parse", "HEAD")
        self.git("push", "origin", "main")
        # Rewind this disposable fixture branch to simulate the old service checkout.
        self.git("checkout", "-B", "service", before)
        config_before = self.config.read_bytes()
        self.command("update", "--config", str(self.config), "--no-start")
        self.assertEqual(self.git("rev-parse", "HEAD"), target)
        self.assertEqual(self.config.read_bytes(), config_before)
        self.assertEqual(deploy.check_database(self.data / "flowboard.db")["schema_version"], SCHEMA_VERSION)
        record = next(json.loads(p.read_text(encoding="utf-8")) for p in self.backups.glob("deployment-*.json")
                      if json.loads(p.read_text(encoding="utf-8"))["action"] == "update")
        self.assertEqual((record["code_before"], record["code_after"]), (before, target))
        self.assertEqual((record["schema_before"], record["schema_after"]), (19, 20))
        self.assertEqual(verify_backup(record["backup_package"])["schema_version"], 19)

    def test_dirty_and_divergent_checkout_are_preserved(self):
        self.install()
        self.init_git()
        (self.app / "server.py").write_text("protected local changes", encoding="utf-8")
        self.command("update", "--config", str(self.config), "--no-start", expected=3)
        self.assertEqual((self.app / "server.py").read_text(), "protected local changes")
        self.git("add", ".")
        self.git("commit", "-m", "Fixture local divergence")
        before = self.git("rev-parse", "HEAD")
        self.command("update", "--config", str(self.config), "--no-start", expected=3)
        self.assertEqual(self.git("rev-parse", "HEAD"), before)
        self.assertEqual(deploy.check_database(self.data / "flowboard.db")["schema_version"], 20)

    def test_failed_migration_retains_backup_and_does_not_start_or_reset_code(self):
        self.install()
        self.version_19()
        database_py = self.app / "flowboard" / "database.py"
        source = database_py.read_text(encoding="utf-8")
        database_py.write_text(source.replace("SCHEMA_VERSION = 20", "SCHEMA_VERSION = 19"), encoding="utf-8")
        self.init_git()
        before = self.git("rev-parse", "HEAD")
        broken = source.replace("def _migration_v20(conn):", "def _migration_v20(conn):\n    raise RuntimeError('fixture migration failure')")
        database_py.write_text(broken, encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-m", "Fixture failing release")
        target = self.git("rev-parse", "HEAD")
        self.git("push", "origin", "main")
        self.git("checkout", "-B", "service", before)
        self.command("update", "--config", str(self.config), expected=3)
        self.assertEqual(self.git("rev-parse", "HEAD"), target)
        self.assertEqual(deploy.check_database(self.data / "flowboard.db", allow_older=True)["schema_version"], 19)
        record = next(json.loads(p.read_text(encoding="utf-8")) for p in self.backups.glob("deployment-*.json")
                      if json.loads(p.read_text(encoding="utf-8"))["action"] == "update")
        self.assertEqual(record["status"], "FAILED")
        self.assertEqual(verify_backup(record["backup_package"])["schema_version"], 19)
        self.assertFalse(self.settings().lock.exists())
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", self.port))

    def test_real_cmd_launcher_health_and_unauthenticated_negative(self):
        self.assert_live_service("start")

    def test_restart_recovers_a_legacy_stale_lock_and_serves_existing_data(self):
        self.assert_live_service("start", stale_lock=True)

    def test_abrupt_exit_releases_os_lock_and_preserves_active_owner(self):
        marker = self.data / ".flowboard-host.lock"
        code = ("import os, sys; from pathlib import Path; from flowboard_deploy import host_lock; "
                "\nwith host_lock(Path(sys.argv[1])):\n"
                " print(os.getpid(), flush=True)\n sys.stdin.readline()\n os._exit(0)\n")
        owner = subprocess.Popen([sys.executable, "-X", "utf8", "-c", code, str(marker)],
                                 cwd=self.app, env=self.env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual(owner.stdout.readline().strip(), str(owner.pid))
            with self.assertRaises(deploy.DeploymentError):
                with deploy.host_lock(marker):
                    self.fail("A concurrent launcher acquired the active lock")
            self.assertEqual(marker.read_text(), str(owner.pid))
        finally:
            owner.communicate("exit\n", timeout=10)
        self.assertEqual(owner.returncode, 0)
        self.assertTrue(marker.exists())  # Abrupt exit bypasses Python cleanup.
        with deploy.host_lock(marker):
            self.assertEqual(marker.read_text(), str(os.getpid()))
        self.assertFalse(marker.exists())

    def test_legacy_live_owner_is_protected_and_reused_windows_pid_is_recovered(self):
        marker = self.data / ".flowboard-host.lock"
        marker.parent.mkdir(parents=True)
        marker.write_text(str(os.getpid()), encoding="ascii")
        with self.assertRaises(deploy.DeploymentError):
            with deploy.host_lock(marker):
                self.fail("An existing legacy owner was displaced")
        self.assertEqual(marker.read_text(), str(os.getpid()))
        if os.name == "nt":
            # Simulate a previous boot's marker whose PID now belongs to this newer process.
            os.utime(marker, (1, 1))
            with deploy.host_lock(marker):
                self.assertEqual(marker.read_text(), str(os.getpid()))
            self.assertFalse(marker.exists())

    def test_update_automatically_starts_and_reads_external_attachments(self):
        self.assert_live_service("update")

    def assert_live_service(self, action, *, stale_lock=False):
        self.install()
        if stale_lock:
            code = ("import os, sys; from flowboard.operations import maintenance_lock; "
                    "\nwith maintenance_lock(sys.argv[1]): os._exit(0)\n")
            exited = subprocess.run([sys.executable, "-c", code, str(self.settings().lock)],
                                    cwd=self.app, env=self.env, capture_output=True, timeout=10)
            self.assertEqual(exited.returncode, 0, exited.stderr)
            self.assertTrue(self.settings().lock.exists())
        if action == "update":
            self.init_git()
        env = dict(self.env, FLOWBOARD_CONFIG=str(self.config), FLOWBOARD_PYTHON=sys.executable)
        if os.name == "nt":
            checked = subprocess.run(["cmd", "/d", "/c", "start-flowboard.cmd", "--check"], cwd=self.app,
                                     env=env, capture_output=True, text=True, timeout=20)
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
        output = self.root / "server-output.log"
        with output.open("w", encoding="utf-8") as stream:
            command = (["cmd", "/d", "/c", "start-flowboard.cmd"] if os.name == "nt" and action == "start" else
                       [sys.executable, "-X", "utf8", str(self.app / "flowboard_deploy.py"), action, "--config", str(self.config)])
            process = subprocess.Popen(command, cwd=self.app, env=env,
                                       stdout=stream, stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    self.assertIsNone(process.poll(), output.read_text(encoding="utf-8"))
                    try:
                        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=1)
                        conn.request("GET", "/api/health")
                        response = conn.getresponse()
                        self.assertEqual(response.status, 200)
                        self.assertEqual(json.loads(response.read())["schema_version"], 20)
                        conn.close()
                        break
                    except OSError:
                        time.sleep(0.1)
                else:
                    self.fail(output.read_text(encoding="utf-8"))
                self.command("start", "--config", str(self.config), expected=3)
                for path, expected in (("/api/bootstrap", 401), ("/api/attachments/1/content", 401), ("/flowboard.db", 404), ("/", 200)):
                    conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=2)
                    conn.request("GET", path)
                    self.assertEqual(conn.getresponse().status, expected)
                    conn.close()
                conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=2)
                conn.request("POST", "/api/auth/login", json.dumps({"username": "u1", "password": "deployment-test-password"}),
                             {"Content-Type": "application/json"})
                response = conn.getresponse()
                self.assertEqual(response.status, 200)
                cookie = response.getheader("Set-Cookie").split(";", 1)[0]
                response.read()
                conn.close()
                conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=2)
                conn.request("GET", "/api/attachments/1/content", headers={"Cookie": cookie})
                response = conn.getresponse()
                self.assertEqual(response.status, 200)
                self.assertEqual(response.read(), b"deployment blob sentinel")
                conn.close()
            finally:
                # A console may be unavailable in CI. Stop only this fixture's owned process tree.
                if process.poll() is None:
                    if os.name == "nt":
                        stopped = subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                                 capture_output=True, text=True, timeout=10)
                        self.assertEqual(stopped.returncode, 0, stopped.stdout + stopped.stderr)
                    else:
                        process.send_signal(__import__("signal").SIGINT)
                process.wait(timeout=10)


if __name__ == "__main__":
    unittest.main()
