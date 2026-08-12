import hashlib
import json
import os
import shutil
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .database import SCHEMA_VERSION, connect


FORMAT_VERSION = 1


class OperationsError(RuntimeError):
    pass


def _sha256(path):
    digest=hashlib.sha256()
    with open(path,"rb") as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b""):digest.update(chunk)
    return digest.hexdigest()


def _safe_name(value):
    if not isinstance(value,str) or not value or value in {".",".."} or Path(value).name!=value or "/" in value or "\\" in value:
        raise OperationsError("unsafe attachment storage name")
    return value


def _plain_file(path):
    path=Path(path)
    if path.is_symlink() or not path.is_file():raise OperationsError(f"unsafe or missing file: {path.name}")
    return path


@contextmanager
def maintenance_lock(lock_path):
    path=Path(lock_path);path.parent.mkdir(parents=True,exist_ok=True)
    try:fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    except FileExistsError:raise OperationsError("maintenance lock is already held")
    try:
        os.write(fd,str(os.getpid()).encode("ascii"));os.close(fd);yield
    finally:
        try:path.unlink()
        except FileNotFoundError:pass


def create_backup(db_path,attachment_dir,backup_root,*,label="manual"):
    db_path=Path(db_path).resolve();attachment_dir=Path(attachment_dir).resolve();backup_root=Path(backup_root).resolve()
    if backup_root==attachment_dir or backup_root in attachment_dir.parents:raise OperationsError("backup root cannot contain the attachment source")
    backup_root.mkdir(parents=True,exist_ok=True);stamp=datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f");name=f"flowboard-{label}-{stamp}";staging=backup_root/f".{name}.staging-{uuid.uuid4().hex}";target=backup_root/name
    staging.mkdir();(staging/"attachments").mkdir();snapshot=staging/"flowboard.db"
    try:
        source=sqlite3.connect(db_path);dest=sqlite3.connect(snapshot)
        try:
            if source.execute("PRAGMA integrity_check").fetchone()[0]!="ok":raise OperationsError("source database integrity check failed")
            source.backup(dest)
        finally:dest.close();source.close()
        conn=connect(snapshot)
        try:
            schema=conn.execute("PRAGMA user_version").fetchone()[0]
            if schema>SCHEMA_VERSION:raise OperationsError("backup schema is newer than this application")
            rows=conn.execute("SELECT storage_name,size_bytes,sha256 FROM attachments ORDER BY storage_name").fetchall()
        finally:conn.close()
        attachments=[]
        for row in rows:
            storage=_safe_name(row["storage_name"]);source_file=_plain_file(attachment_dir/storage);actual=_sha256(source_file)
            if source_file.stat().st_size!=row["size_bytes"] or actual!=row["sha256"]:raise OperationsError(f"attachment checksum mismatch: {storage}")
            copied=staging/"attachments"/storage;shutil.copy2(source_file,copied);attachments.append({"storage_name":storage,"size":copied.stat().st_size,"sha256":actual})
        manifest={"format_version":FORMAT_VERSION,"schema_version":schema,"created_at":datetime.now(timezone.utc).isoformat(timespec="seconds"),"label":label,"database":{"name":"flowboard.db","size":snapshot.stat().st_size,"sha256":_sha256(snapshot)},"attachments":attachments}
        (staging/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,sort_keys=True,indent=2),encoding="utf-8")
        verify_backup(staging);os.replace(staging,target);return target
    except Exception:
        shutil.rmtree(staging,ignore_errors=True);raise


def verify_backup(package):
    package=Path(package).resolve()
    if package.is_symlink() or not package.is_dir():raise OperationsError("backup package must be a real directory")
    expected={"manifest.json","flowboard.db","attachments"};actual={item.name for item in package.iterdir()}
    if actual!=expected:raise OperationsError("backup package contains missing or unexpected members")
    manifest_path=_plain_file(package/"manifest.json");db_path=_plain_file(package/"flowboard.db");attachments_dir=package/"attachments"
    if attachments_dir.is_symlink() or not attachments_dir.is_dir():raise OperationsError("unsafe attachments directory")
    try:manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError,ValueError) as error:raise OperationsError("invalid backup manifest") from error
    if manifest.get("format_version")!=FORMAT_VERSION or not isinstance(manifest.get("database"),dict):raise OperationsError("unsupported backup format")
    if manifest.get("schema_version",SCHEMA_VERSION+1)>SCHEMA_VERSION:raise OperationsError("backup schema is newer than this application")
    database=manifest["database"]
    if database.get("name")!="flowboard.db" or db_path.stat().st_size!=database.get("size") or _sha256(db_path)!=database.get("sha256"):raise OperationsError("database checksum mismatch")
    conn=connect(db_path)
    try:
        if conn.execute("PRAGMA integrity_check").fetchone()[0]!="ok" or conn.execute("PRAGMA foreign_key_check").fetchall():raise OperationsError("backup database validation failed")
        if conn.execute("PRAGMA user_version").fetchone()[0]!=manifest["schema_version"]:raise OperationsError("manifest schema mismatch")
        referenced={row[0] for row in conn.execute("SELECT storage_name FROM attachments")}
    finally:conn.close()
    entries=manifest.get("attachments")
    if not isinstance(entries,list):raise OperationsError("invalid attachment manifest")
    names=[]
    for entry in entries:
        if not isinstance(entry,dict):raise OperationsError("invalid attachment entry")
        name=_safe_name(entry.get("storage_name"));names.append(name);path=_plain_file(attachments_dir/name)
        if path.stat().st_size!=entry.get("size") or _sha256(path)!=entry.get("sha256"):raise OperationsError(f"attachment checksum mismatch: {name}")
    if len(names)!=len(set(names)) or set(names)!=referenced or {item.name for item in attachments_dir.iterdir()}!=set(names):raise OperationsError("attachment manifest does not match database and package")
    return manifest


def list_backups(backup_root):
    root=Path(backup_root).resolve()
    if not root.exists():return []
    result=[]
    for item in sorted(root.iterdir(),reverse=True):
        if item.name.startswith("flowboard-") and item.is_dir() and not item.is_symlink():
            try:manifest=verify_backup(item);result.append({"name":item.name,"created_at":manifest["created_at"],"schema_version":manifest["schema_version"],"valid":True})
            except OperationsError as error:result.append({"name":item.name,"valid":False,"error":str(error)})
    return result


def apply_retention(backup_root,*,keep=10):
    if isinstance(keep,bool) or not isinstance(keep,int) or not 1<=keep<=365:raise OperationsError("keep must be between 1 and 365")
    root=Path(backup_root).resolve();valid=[]
    for item in sorted(root.iterdir(),reverse=True) if root.exists() else []:
        if item.name.startswith("flowboard-") and item.is_dir() and not item.is_symlink():
            try:verify_backup(item);valid.append(item)
            except OperationsError:continue
    removed=[]
    for item in valid[keep:]:shutil.rmtree(item);removed.append(item.name)
    return removed


def restore_backup(package,db_path,attachment_dir,*,safety_root=None,inject_failure=None):
    package=Path(package).resolve();manifest=verify_backup(package);db_path=Path(db_path).resolve();attachment_dir=Path(attachment_dir).resolve();safety_root=Path(safety_root or db_path.parent/"backups").resolve();lock=db_path.parent/".flowboard-maintenance.lock"
    with maintenance_lock(lock):
        safety=create_backup(db_path,attachment_dir,safety_root,label="pre-restore") if db_path.exists() else None
        stage_db=db_path.parent/f".{db_path.name}.restore-{uuid.uuid4().hex}";stage_attachments=attachment_dir.parent/f".{attachment_dir.name}.restore-{uuid.uuid4().hex}";old_db=db_path.parent/f".{db_path.name}.old-{uuid.uuid4().hex}";old_attachments=attachment_dir.parent/f".{attachment_dir.name}.old-{uuid.uuid4().hex}"
        db_moved=db_installed=attachments_moved=attachments_installed=False
        try:
            if inject_failure=="before_stage_copy":raise OperationsError("injected restore failure")
            shutil.copy2(package/"flowboard.db",stage_db)
            if inject_failure=="after_stage_db_copy":raise OperationsError("injected restore failure")
            shutil.copytree(package/"attachments",stage_attachments)
            if inject_failure=="after_stage":raise OperationsError("injected restore failure")
            if db_path.exists():os.replace(db_path,old_db);db_moved=True
            if inject_failure=="after_db_old":raise OperationsError("injected restore failure")
            os.replace(stage_db,db_path);db_installed=True
            if inject_failure=="after_db_install":raise OperationsError("injected restore failure")
            if attachment_dir.exists():os.replace(attachment_dir,old_attachments);attachments_moved=True
            if inject_failure=="after_attachment_old":raise OperationsError("injected restore failure")
            os.replace(stage_attachments,attachment_dir);attachments_installed=True
            if inject_failure=="after_attachment_install":raise OperationsError("injected restore failure")
            verify_database=connect(db_path)
            try:
                if verify_database.execute("PRAGMA integrity_check").fetchone()[0]!="ok" or verify_database.execute("PRAGMA foreign_key_check").fetchall():raise OperationsError("restored database validation failed")
            finally:verify_database.close()
            if inject_failure=="final_validation":raise OperationsError("injected final validation failure")
            if old_db.exists():old_db.unlink()
            if old_attachments.exists():shutil.rmtree(old_attachments)
            return {"restored":True,"schema_version":manifest["schema_version"],"safety_backup":str(safety) if safety else None}
        except Exception:
            if attachments_installed and attachment_dir.exists():shutil.rmtree(attachment_dir)
            if attachments_moved and old_attachments.exists():os.replace(old_attachments,attachment_dir)
            if db_installed and db_path.exists():db_path.unlink()
            if db_moved and old_db.exists():os.replace(old_db,db_path)
            raise
        finally:
            if stage_db.exists():stage_db.unlink()
            if stage_attachments.exists():shutil.rmtree(stage_attachments)
