import base64
import hashlib
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from flowboard.database import SCHEMA_VERSION, connect, migrate
from flowboard.operations import OperationsError, apply_retention, create_backup, restore_backup, verify_backup
from flowboard.service import FlowboardService


class I13OperationsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.db=self.root/"flowboard.db";self.attachments=self.root/"blobs";self.backups=self.root/"safe-backups";shutil.copy2(Path(__file__).parents[1]/"flowboard.db",self.db);migrate(self.db);self.previous=os.environ.get("FLOWBOARD_ATTACHMENT_DIR");os.environ["FLOWBOARD_ATTACHMENT_DIR"]=str(self.attachments);self.service=FlowboardService(self.db);conn=connect(self.db);self.admin=dict(conn.execute("SELECT * FROM users WHERE id='u1'").fetchone());conn.close()

    def tearDown(self):
        if self.previous is None:os.environ.pop("FLOWBOARD_ATTACHMENT_DIR",None)
        else:os.environ["FLOWBOARD_ATTACHMENT_DIR"]=self.previous
        self.temp.cleanup()

    def _seed(self):
        detail=self.service.task_detail(self.admin,1);self.service.update_task(self.admin,1,{"version":detail["version"],"description":"backup sentinel"});self.service.create_comment(self.admin,1,{"body":"backup comment"});attachment=self.service.create_attachment(self.admin,1,{"name":"backup.txt","content_type":"text/plain","content_base64":base64.b64encode(b"backup bytes").decode()});return attachment

    def test_backup_manifest_corruption_retention_and_real_restore_with_blob(self):
        attachment=self._seed();package=create_backup(self.db,self.attachments,self.backups);manifest=verify_backup(package);self.assertEqual(manifest["schema_version"],SCHEMA_VERSION);self.assertEqual(len(manifest["attachments"]),1)
        conn=connect(self.db);conn.execute("UPDATE tasks SET description='changed after backup' WHERE id=1");storage=conn.execute("SELECT storage_name FROM attachments WHERE id=?",(attachment["id"],)).fetchone()[0];conn.execute("UPDATE attachments SET size_bytes=?,sha256=? WHERE id=?",(len(b"changed"),hashlib.sha256(b"changed").hexdigest(),attachment["id"]));conn.commit();conn.close();(self.attachments/storage).write_bytes(b"changed")
        restored=restore_backup(package,self.db,self.attachments,safety_root=self.backups);self.assertTrue(restored["restored"]);conn=connect(self.db);self.assertEqual(conn.execute("SELECT description FROM tasks WHERE id=1").fetchone()[0],"backup sentinel");self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0],"ok");self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(),[]);conn.close();self.assertEqual((self.attachments/storage).read_bytes(),b"backup bytes")
        damaged=create_backup(self.db,self.attachments,self.backups,label="damaged");(damaged/"flowboard.db").write_bytes(b"not sqlite")
        with self.assertRaises(OperationsError):verify_backup(damaged)
        outside=self.root/"outside.keep";outside.write_text("keep",encoding="utf-8");removed=apply_retention(self.backups,keep=1);self.assertTrue(removed);self.assertEqual(outside.read_text(encoding="utf-8"),"keep");self.assertTrue(damaged.exists())

    def test_restore_injected_failure_rolls_back_current_database_and_attachment(self):
        attachment=self._seed();package=create_backup(self.db,self.attachments,self.backups);conn=connect(self.db);conn.execute("UPDATE tasks SET description='current protected' WHERE id=1");storage=conn.execute("SELECT storage_name FROM attachments WHERE id=?",(attachment["id"],)).fetchone()[0];conn.execute("UPDATE attachments SET size_bytes=?,sha256=? WHERE id=?",(len(b"current bytes"),hashlib.sha256(b"current bytes").hexdigest(),attachment["id"]));conn.commit();conn.close();(self.attachments/storage).write_bytes(b"current bytes")
        points=("before_stage_copy","after_stage_db_copy","after_stage","after_db_old","after_db_install","after_attachment_old","after_attachment_install","final_validation")
        for point in points:
            with self.subTest(point=point):
                with self.assertRaises(OperationsError):restore_backup(package,self.db,self.attachments,safety_root=self.backups,inject_failure=point)
                conn=connect(self.db);self.assertEqual(conn.execute("SELECT description FROM tasks WHERE id=1").fetchone()[0],"current protected");self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0],"ok");self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(),[]);conn.close();self.assertTrue(self.attachments.is_dir());self.assertEqual((self.attachments/storage).read_bytes(),b"current bytes");self.assertFalse((self.root/".flowboard-maintenance.lock").exists());self.assertEqual(list(self.root.glob(".*.restore-*"))+list(self.root.glob(".*.old-*")),[])
        safety=[item for item in self.backups.iterdir() if item.name.startswith("flowboard-pre-restore-")];self.assertEqual(len(safety),len(points))
        for item in safety:self.assertEqual(verify_backup(item)["schema_version"],SCHEMA_VERSION)

    def test_restore_failure_preserves_originally_missing_targets(self):
        self._seed();package=create_backup(self.db,self.attachments,self.backups);missing_root=self.root/"new-target";missing_root.mkdir();missing_db=missing_root/"flowboard.db";missing_attachments=missing_root/"blobs"
        with self.assertRaises(OperationsError):restore_backup(package,missing_db,missing_attachments,safety_root=self.backups,inject_failure="after_attachment_install")
        self.assertFalse(missing_db.exists());self.assertFalse(missing_attachments.exists());self.assertFalse((missing_root/".flowboard-maintenance.lock").exists());self.assertEqual(list(missing_root.glob(".*.restore-*"))+list(missing_root.glob(".*.old-*")),[])


if __name__=="__main__":unittest.main()
