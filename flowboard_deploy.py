"""Small, offline-friendly deployment entry points for a dedicated LAN host."""

import argparse
import json
import os
import re
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from flowboard.database import SCHEMA_VERSION, migrate
from flowboard.operations import create_backup, maintenance_lock, restore_backup, verify_backup


APP_ROOT = Path(__file__).resolve().parent
CONFIG_KEYS = {"format_version", "data_dir", "backup_dir", "host", "port", "secure_cookie", "release_ref"}


class DeploymentError(RuntimeError):
    pass


@dataclass(frozen=True)
class Settings:
    app: Path
    config: Path | None
    db: Path
    attachments: Path
    backups: Path
    host: str
    port: int
    secure_cookie: bool
    release_ref: str

    @property
    def lock(self):
        return self.db.parent / ".flowboard-host.lock"

    def environment(self):
        result = os.environ.copy()
        result.update(FLOWBOARD_DB=str(self.db), FLOWBOARD_ATTACHMENT_DIR=str(self.attachments),
                      FLOWBOARD_BACKUP_DIR=str(self.backups), FLOWBOARD_HOST=self.host,
                      FLOWBOARD_PORT=str(self.port), FLOWBOARD_SECURE_COOKIE="1" if self.secure_cookie else "")
        return result


def _path(value, base):
    path = Path(value).expanduser()
    return (path if path.is_absolute() else base / path).resolve()


def _inside(path, root):
    return path == root or root in path.parents


def validate_settings(settings, *, external=False):
    if not isinstance(settings.port, int) or isinstance(settings.port, bool) or not 1 <= settings.port <= 65535:
        raise DeploymentError("Port must be an integer between 1 and 65535")
    if not isinstance(settings.host, str) or not settings.host.strip():
        raise DeploymentError("Host must be a nonempty address")
    if not isinstance(settings.secure_cookie, bool):
        raise DeploymentError("secure_cookie must be true or false")
    if not isinstance(settings.release_ref, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", settings.release_ref):
        raise DeploymentError("release_ref must be a branch, tag or commit reference")
    if _inside(settings.db, settings.attachments) or _inside(settings.db, settings.backups):
        raise DeploymentError("Database, attachments and backups must use separate paths")
    if _inside(settings.attachments, settings.backups) or _inside(settings.backups, settings.attachments):
        raise DeploymentError("Attachments and backups must not contain each other")
    if external and (not settings.config or any(_inside(p, settings.app) for p in
                                              (settings.config, settings.db, settings.attachments, settings.backups))):
        raise DeploymentError("Dedicated host configuration and data must be outside the code checkout")
    return settings


def load_settings(config=None, *, env=None, app=APP_ROOT):
    env = os.environ if env is None else env
    app = Path(app).resolve()
    explicit = config or env.get("FLOWBOARD_CONFIG")
    path = _path(explicit, app) if explicit else app.parent / "flowboard-host.json"
    values = {}
    if path.exists():
        values = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(values, dict) or set(values) - CONFIG_KEYS or values.get("format_version") != 1:
            raise DeploymentError("Unsupported or unknown host configuration fields")
        if not all(isinstance(values.get(key), str) and values[key].strip() for key in ("data_dir", "backup_dir")):
            raise DeploymentError("Configuration requires data_dir and backup_dir")
        data = _path(values["data_dir"], path.parent)
        db, attachments = data / "flowboard.db", data / "attachments"
        backups = _path(values["backup_dir"], path.parent)
    elif explicit:
        raise DeploymentError(f"Host configuration not found: {path}")
    else:
        path = None
        db, attachments, backups = app / "flowboard.db", app / "flowboard-attachments", app / "backups"
    db = _path(env["FLOWBOARD_DB"], app) if env.get("FLOWBOARD_DB") else db
    attachments = _path(env["FLOWBOARD_ATTACHMENT_DIR"], app) if env.get("FLOWBOARD_ATTACHMENT_DIR") else attachments
    backups = _path(env["FLOWBOARD_BACKUP_DIR"], app) if env.get("FLOWBOARD_BACKUP_DIR") else backups
    port = int(env["FLOWBOARD_PORT"]) if env.get("FLOWBOARD_PORT") else values.get("port", 8080)
    secure = env["FLOWBOARD_SECURE_COOKIE"] == "1" if "FLOWBOARD_SECURE_COOKIE" in env else values.get("secure_cookie", False)
    return validate_settings(Settings(app, path, db, attachments, backups,
                                     env.get("FLOWBOARD_HOST") or values.get("host", "0.0.0.0"), port,
                                     secure, values.get("release_ref", "origin/main")))


def check_database(path, *, allow_older=False):
    if not path.is_file():
        raise DeploymentError(f"Database not found; install a verified backup first: {path}")
    conn = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    try:
        conn.execute("PRAGMA query_only=ON")
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = len(conn.execute("PRAGMA foreign_key_check").fetchall())
    finally:
        conn.close()
    if integrity != "ok" or foreign_keys:
        raise DeploymentError(f"Database validation failed: integrity={integrity}; foreign keys={foreign_keys}")
    if version > SCHEMA_VERSION or (not allow_older and version != SCHEMA_VERSION):
        raise DeploymentError(f"Database v{version}; code requires v{SCHEMA_VERSION}. Run the update/upgrade entry point")
    if allow_older and version < 12:
        raise DeploymentError("This deployment entry point requires an existing v12+ backup; legacy migration is separate")
    return {"schema_version": version, "integrity": integrity, "foreign_key_violations": foreign_keys}


def assert_stopped(settings):
    # The host lock also detects a managed server using this database on another port.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        if os.name == "nt":
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            probe.bind((settings.host, settings.port))
        except OSError as error:
            raise DeploymentError(f"Port {settings.port} is occupied. Stop the service with Ctrl+C before updating") from error


def new_record(settings, action):
    settings.backups.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = settings.backups / f"deployment-{stamp}-{uuid.uuid4().hex[:8]}.json"
    record = {"action": action, "started_at": datetime.now(timezone.utc).isoformat(),
              "status": "STARTED", "database": str(settings.db), "lock_owner": os.getpid()}
    save_record(path, record)
    return path, record


def save_record(path, record):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def git(app, *args):
    result = subprocess.run(["git", "-C", str(app), *args], capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=120)
    if result.returncode:
        reason = re.sub(r"(https?://)[^/\s]*@", r"\1***@", result.stderr.strip())
        raise DeploymentError(reason or "Git command failed")
    return result.stdout.strip()


def start(settings, *, check_only=False):
    validation = check_database(settings.db)
    print(json.dumps({"config": str(settings.config) if settings.config else None,
                      "database": str(settings.db), "port": settings.port, **validation}, ensure_ascii=False), flush=True)
    if check_only:
        return 0
    with maintenance_lock(settings.lock):
        assert_stopped(settings)
        settings.attachments.mkdir(parents=True, exist_ok=True)
        settings.backups.mkdir(parents=True, exist_ok=True)
        process = subprocess.Popen([sys.executable, "-u", str(settings.app / "server.py")],
                                   cwd=settings.app, env=settings.environment())
        try:
            address = "127.0.0.1" if settings.host == "0.0.0.0" else settings.host
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            deadline = time.monotonic() + 15
            ready = False
            while process.poll() is None and time.monotonic() < deadline:
                try:
                    with opener.open(f"http://{address}:{settings.port}/api/health", timeout=1) as response:
                        health = json.load(response)
                    if health.get("status") == "ok" and health.get("schema_version") == SCHEMA_VERSION:
                        ready = True
                        break
                except (OSError, ValueError):
                    time.sleep(0.15)
            if not ready:
                raise DeploymentError("Server did not become healthy; see startup output")
            print(f"[OK] Flowboard ready on port {settings.port}. Keep this window open; Ctrl+C stops it.", flush=True)
            return process.wait()
        except KeyboardInterrupt:
            return 0
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def install(args):
    explicit_config = args.config or os.environ.get("FLOWBOARD_CONFIG")
    config = _path(explicit_config, APP_ROOT) if explicit_config else APP_ROOT.parent / "flowboard-host.json"
    data = _path(args.data_dir, APP_ROOT) if args.data_dir else APP_ROOT.parent / "flowboard-data"
    backups = _path(args.backup_dir, APP_ROOT) if args.backup_dir else APP_ROOT.parent / "flowboard-backups"
    settings = validate_settings(Settings(APP_ROOT, config, data / "flowboard.db", data / "attachments",
                                          backups, args.host, args.port, False, args.ref), external=True)
    if config.exists() or settings.db.exists() or (settings.attachments.exists() and any(settings.attachments.iterdir())):
        raise DeploymentError("Existing host configuration or data found; installation will not overwrite it")
    manifest = verify_backup(Path(args.package).resolve())
    if not 12 <= manifest["schema_version"] <= SCHEMA_VERSION:
        raise DeploymentError("Backup schema is unsupported by this release")
    plan = {"format_version": 1, "data_dir": str(data), "backup_dir": str(backups),
            "host": args.host, "port": args.port, "secure_cookie": False, "release_ref": args.ref}
    if args.check:
        print(json.dumps({"configuration": str(config), "settings": plan, "backup_verified": True,
                          "python": sys.version.split()[0], "git": git(APP_ROOT, "--version")}, ensure_ascii=False, indent=2))
        return 0
    with maintenance_lock(settings.lock):
        assert_stopped(settings)
        record_path, record = new_record(settings, "install")
        try:
            # Retain a local package before migration even if the source was on removable media.
            restore_backup(args.package, settings.db, settings.attachments, safety_root=settings.backups)
            package = create_backup(settings.db, settings.attachments, settings.backups, label="before-install")
            record["backup_package"] = str(package)
            record["schema_before"] = manifest["schema_version"]
            save_record(record_path, record)
            if manifest["schema_version"] < SCHEMA_VERSION:
                migrate(settings.db)
            record.update(check_database(settings.db), status="READY")
            config.parent.mkdir(parents=True, exist_ok=True)
            with config.open("x", encoding="utf-8") as output:
                json.dump(plan, output, ensure_ascii=False, indent=2)
        except Exception as error:
            record.update(status="FAILED", error=str(error))
            raise
        finally:
            save_record(record_path, record)
    print(f"[OK] Installed. Configuration: {config}\nRecord: {record_path}")
    return 0


def finish_migration(settings, record_path, record):
    validation = check_database(settings.db, allow_older=True)
    verify_backup(record["backup_package"])
    if validation["schema_version"] < SCHEMA_VERSION:
        migrate(settings.db)
    record.update(check_database(settings.db), schema_after=SCHEMA_VERSION, status="READY")
    save_record(record_path, record)


def upgrade(settings):
    with maintenance_lock(settings.lock):
        assert_stopped(settings)
        validation = check_database(settings.db, allow_older=True)
        record_path, record = new_record(settings, "upgrade")
        try:
            record["schema_before"] = validation["schema_version"]
            record["backup_package"] = str(create_backup(settings.db, settings.attachments, settings.backups,
                                                         label="before-upgrade"))
            save_record(record_path, record)
            finish_migration(settings, record_path, record)
        except Exception as error:
            record.update(status="FAILED", error=str(error))
            save_record(record_path, record)
            raise
    print(f"[OK] Database ready. Record: {record_path}")
    return 0


def finish_update(settings, journal):
    record_path = Path(journal).resolve()
    if record_path.parent != settings.backups:
        raise DeploymentError("Update record must be in the configured backup directory")
    record = json.loads(record_path.read_text(encoding="utf-8"))
    if (record.get("status") != "CODE_UPDATED" or record.get("lock_owner") != os.getppid()
            or not settings.lock.exists() or settings.lock.read_text() != str(os.getppid())
            or record.get("database") != str(settings.db)):
        raise DeploymentError("The migration continuation requires the active update parent and its host lock")
    if git(settings.app, "rev-parse", "HEAD") != record.get("code_after"):
        raise DeploymentError("Code changed during the update")
    try:
        assert_stopped(settings)
        finish_migration(settings, record_path, record)
    except Exception as error:
        record.update(status="FAILED", error=str(error))
        save_record(record_path, record)
        raise
    return 0


def update(settings, *, ref=None, no_start=False):
    validate_settings(settings, external=True)
    target_ref = ref or settings.release_ref
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", target_ref):
        raise DeploymentError("Invalid release reference")
    if git(settings.app, "status", "--porcelain", "--untracked-files=all"):
        raise DeploymentError("Code checkout has local changes or untracked files. Preserve them and use a clean release checkout")
    git(settings.app, "symbolic-ref", "--quiet", "--short", "HEAD")
    before = git(settings.app, "rev-parse", "HEAD")
    with maintenance_lock(settings.lock):
        assert_stopped(settings)
        validation = check_database(settings.db, allow_older=True)
        record_path, record = new_record(settings, "update")
        try:
            record.update(code_before=before, release_ref=target_ref, schema_before=validation["schema_version"])
            record["backup_package"] = str(create_backup(settings.db, settings.attachments, settings.backups,
                                                         label="before-update"))
            save_record(record_path, record)
            git(settings.app, "fetch", "origin")
            target = git(settings.app, "rev-parse", "--verify", f"{target_ref}^{{commit}}")
            try:
                git(settings.app, "merge-base", "--is-ancestor", before, target)
            except DeploymentError as error:
                raise DeploymentError("Release is not a fast-forward of the service checkout; update stopped") from error
            git(settings.app, "cat-file", "-e", f"{target}:flowboard_deploy.py")
            git(settings.app, "cat-file", "-e", f"{target}:server.py")
            git(settings.app, "merge", "--ff-only", target)
            record.update(code_after=git(settings.app, "rev-parse", "HEAD"), status="CODE_UPDATED")
            save_record(record_path, record)
            # Git may rewrite equal-size Python files within one timestamp second.
            # Rebuild their caches so the fresh interpreter cannot read the old bytecode.
            compiled = subprocess.run([sys.executable, "-m", "compileall", "-q", "-f",
                                       str(settings.app / "flowboard"), str(settings.app / "server.py"),
                                       str(settings.app / "flowboard_deploy.py")], capture_output=True, text=True)
            if compiled.returncode:
                raise DeploymentError("New release failed Python compilation; keep the service stopped")
            # Restart the interpreter so schema and migrations come from the new code.
            result = subprocess.run([sys.executable, "-X", "utf8", str(settings.app / "flowboard_deploy.py"),
                                     "_finish-update", "--config", str(settings.config), "--journal", str(record_path)],
                                    cwd=settings.app, env=settings.environment())
            record = json.loads(record_path.read_text(encoding="utf-8"))
            if result.returncode or record.get("status") != "READY":
                raise DeploymentError(f"Migration/check failed. Keep the service stopped; inspect {record_path}")
        except Exception as error:
            record.update(status="FAILED", error=str(error))
            save_record(record_path, record)
            raise
    print(f"[OK] Updated. Record: {record_path}", flush=True)
    if no_start:
        return 0
    result = subprocess.call([sys.executable, "-X", "utf8", str(settings.app / "flowboard_deploy.py"),
                              "start", "--config", str(settings.config)], cwd=settings.app, env=settings.environment())
    if result:
        record.update(status="START_FAILED", error=f"Startup exited with code {result}")
        save_record(record_path, record)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="Flowboard dedicated-host install, start and update")
    commands = parser.add_subparsers(dest="command", required=True)
    start_parser = commands.add_parser("start", help="Check and run the configured service in this window")
    start_parser.add_argument("--check", action="store_true", help="Read-only database validation")
    init_parser = commands.add_parser("install", help="Create an external host configuration and import a verified backup")
    init_parser.add_argument("--package", required=True)
    init_parser.add_argument("--data-dir")
    init_parser.add_argument("--backup-dir")
    init_parser.add_argument("--host", default="0.0.0.0")
    init_parser.add_argument("--port", type=int, default=8080)
    init_parser.add_argument("--ref", default="origin/main")
    init_parser.add_argument("--check", action="store_true", help="Show the installation plan without creating data or configuration")
    update_parser = commands.add_parser("update", help="Back up, fast-forward the code, migrate/check and start")
    update_parser.add_argument("--ref", help="A tested release branch, tag or commit; defaults to host configuration")
    update_parser.add_argument("--no-start", action="store_true", help="Leave the service stopped after updating")
    upgrade_parser = commands.add_parser("upgrade", help="Back up and migrate/check installed code without Git or startup")
    finish_parser = commands.add_parser("_finish-update", help=argparse.SUPPRESS)
    finish_parser.add_argument("--journal", required=True)
    for command in (start_parser, init_parser, update_parser, upgrade_parser, finish_parser):
        command.add_argument("--config", help="Host JSON; defaults to FLOWBOARD_CONFIG or ../flowboard-host.json")
    args = parser.parse_args(argv)
    try:
        if sys.version_info < (3, 10):
            raise DeploymentError("Python 3.10 or later is required")
        if args.command == "install":
            return install(args)
        settings = load_settings(args.config)
        if args.command == "start":
            return start(settings, check_only=args.check)
        if args.command == "upgrade":
            return upgrade(settings)
        if args.command == "_finish-update":
            return finish_update(settings, args.journal)
        return update(settings, ref=args.ref, no_start=args.no_start)
    except (RuntimeError, OSError, ValueError, sqlite3.Error, subprocess.SubprocessError) as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
