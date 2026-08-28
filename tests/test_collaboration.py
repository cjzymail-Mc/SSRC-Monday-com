import base64
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

import flowboard.database as database
from flowboard.database import connect, migrate
from flowboard.service import ApiError, FlowboardService
from test_secure_foundation import create_legacy_database


class CollaborationTests(unittest.TestCase):
    def setUp(self):
        self.root=tempfile.TemporaryDirectory(); self.db=Path(self.root.name)/"flowboard.db"
        create_legacy_database(self.db); migrate(self.db, initial_password="test-password")
        self.service=FlowboardService(self.db); db=connect(self.db); self.admin=dict(db.execute("SELECT * FROM users WHERE id='u1'").fetchone()); db.close()

    def tearDown(self):
        self.root.cleanup()

    def test_thread_mentions_edit_delete_subscription_and_outbox(self):
        root=self.service.create_comment(self.admin,1,{"body":"hello","mentions":[{"type":"user","user_id":"u2"}]})
        reply=self.service.create_comment(self.admin,1,{"body":"reply","parent_id":root["id"]})
        self.service.update_comment(self.admin,root["id"],{"version":1,"body":"edited","mentions":[{"type":"all"}]})
        self.service.delete_comment(self.admin,root["id"],{"version":2})
        detail=self.service.task_detail(self.admin,1)
        self.assertIsNone(next(x for x in detail["comments"] if x["id"]==root["id"])["body"])
        self.assertEqual(next(x for x in detail["comments"] if x["id"]==reply["id"])["parent_id"],root["id"])
        self.assertTrue(detail["subscription"]["subscribed"])
        db=connect(self.db); self.assertGreaterEqual(db.execute("SELECT COUNT(*) FROM collaboration_events").fetchone()[0],3); db.close()
        db=connect(self.db); self.assertEqual(db.execute("SELECT COUNT(*) FROM comment_versions WHERE comment_id=?",(root["id"],)).fetchone()[0],2); db.close()

    def test_private_attachment_validation_acl_and_soft_delete(self):
        created=self.service.create_attachment(self.admin,1,{"name":"note.txt","content_type":"text/plain","content_base64":base64.b64encode(b"safe text").decode()})
        meta,raw=self.service.attachment_content(self.admin,created["id"]); self.assertEqual(raw,b"safe text"); self.assertNotEqual(meta["storage_name"],"note.txt")
        self.service.delete_attachment(self.admin,created["id"],{"version":1})
        with self.assertRaises(ApiError): self.service.attachment_content(self.admin,created["id"])
        with self.assertRaises(ApiError): self.service.create_attachment(self.admin,1,{"name":"x.svg","content_type":"image/svg+xml","content_base64":base64.b64encode(b"<svg/>").decode()})

    def test_viewer_can_read_but_cannot_mutate_collaboration(self):
        db=connect(self.db); db.execute("UPDATE workspace_memberships SET role='viewer' WHERE workspace_id=1 AND user_id='u2'"); db.commit(); viewer=dict(db.execute("SELECT * FROM users WHERE id='u2'").fetchone()); db.close()
        self.service.task_detail(viewer,1)
        with self.assertRaises(ApiError) as caught: self.service.create_comment(viewer,1,{"body":"no"})
        self.assertEqual(caught.exception.status,403)

    def test_subscription_is_single_row_idempotent_and_manual_opt_out_is_sticky(self):
        first=self.service.set_subscription(self.admin,1,{"subscribed":False})
        second=self.service.set_subscription(self.admin,1,{"subscribed":False})
        self.assertEqual((first["state"],first["version"]),("opted_out",1))
        self.assertFalse(second["changed"]);self.assertEqual(second["version"],first["version"])
        self.service.create_comment(self.admin,1,{"body":"comment after opt-out","mentions":[{"type":"user","user_id":"u2"}]})
        db=connect(self.db)
        row=dict(db.execute("SELECT state,source,version FROM task_subscriptions WHERE task_id=1 AND user_id='u1'").fetchone())
        self.assertEqual(row,{"state":"opted_out","source":"manual","version":1})
        self.assertEqual(db.execute("SELECT COUNT(*) FROM task_subscriptions WHERE task_id=1 AND user_id='u1'").fetchone()[0],1)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM collaboration_events WHERE event_type='subscription.unsubscribed'").fetchone()[0],1)
        db.close()
        restored=self.service.set_subscription(self.admin,1,{"subscribed":True})
        self.assertEqual((restored["state"],restored["version"]),("following",2))
        db=connect(self.db);self.assertEqual(db.execute("SELECT source FROM task_subscriptions WHERE task_id=1 AND user_id='u1'").fetchone()[0],"manual");db.close()

    def test_omitted_mentions_are_preserved_and_stale_update_is_atomic(self):
        comment=self.service.create_comment(self.admin,1,{"body":"original","mentions":[{"type":"user","user_id":"u2"}]})
        self.service.update_comment(self.admin,comment["id"],{"version":1,"body":"body only"})
        detail=self.service.task_detail(self.admin,1);updated=next(row for row in detail["comments"] if row["id"]==comment["id"])
        self.assertEqual([(row["mention_type"],row["user_id"]) for row in updated["mentions"]],[("user","u2")])
        db=connect(self.db)
        before=tuple(db.execute("SELECT (SELECT COUNT(*) FROM activity),(SELECT COUNT(*) FROM collaboration_events),(SELECT COUNT(*) FROM comment_versions WHERE comment_id=?)",(comment["id"],)).fetchone())
        db.close()
        with self.assertRaises(ApiError) as caught:self.service.update_comment(self.admin,comment["id"],{"version":1,"body":"stale","mentions":[]})
        self.assertEqual(caught.exception.status,409)
        db=connect(self.db)
        after=tuple(db.execute("SELECT (SELECT COUNT(*) FROM activity),(SELECT COUNT(*) FROM collaboration_events),(SELECT COUNT(*) FROM comment_versions WHERE comment_id=?)",(comment["id"],)).fetchone())
        db.close();self.assertEqual(after,before)

    def test_v12_to_v14_subscription_merge_backup_restore_and_idempotence(self):
        root=Path(self.root.name)/"migration";root.mkdir();db_path=root/"v12.db";create_legacy_database(db_path);db=connect(db_path);database._migration_v1(db,"test-password")
        for version in range(2,13):getattr(database,f"_migration_v{version}")(db)
        db.close()
        db=connect(db_path)
        rows=[
            (1,"u1","manual",2,"2026-01-01", "2026-01-05"),(1,"u1","comment",7,"2026-01-02","2026-01-06"),
            (1,"u2","mention",3,"2026-01-02",None),(1,"u2","manual",5,"2026-01-01",None),
            (2,"u1","mention",8,"2026-02-03",None),(2,"u1","comment",4,"2026-02-02",None),(2,"u1","creator",2,"2026-02-01",None),
            (2,"u2","mention",6,"2026-03-02",None),(2,"u2","comment",4,"2026-03-01",None),
            (3,"u1","mention",3,"2026-04-01",None),(3,"u1","manual",99,"2026-03-01","2026-04-02")]
        db.executemany("INSERT INTO task_subscriptions(task_id,user_id,reason,version,created_at,deleted_at) VALUES (?,?,?,?,?,?)",rows)
        cur=db.execute("INSERT INTO comments(task_id,user_id,body,parent_id,version,created_at,updated_at) VALUES (3,'u1','migration sentinel',NULL,1,'2026-01-01','2026-01-01')");comment_id=cur.lastrowid;db.execute("INSERT INTO comment_versions(comment_id,version,body,edited_by,created_at) VALUES (?,1,'migration sentinel','u1','2026-01-01')",(comment_id,));db.execute("INSERT INTO comment_mentions(comment_id,target_key,user_id,mention_type,created_at) VALUES (?,'user:u2','u2','user','2026-01-01')",(comment_id,))
        cur=db.execute("INSERT INTO attachments(task_id,uploader_id,storage_name,original_name,content_type,size_bytes,sha256,preview_kind,created_at,updated_at) VALUES (3,'u1','sentinel.txt','sentinel.txt','text/plain',1,'x','text','2026-01-01','2026-01-01')");attachment_id=cur.lastrowid;db.execute("INSERT INTO collaboration_events(event_key,event_type,board_id,task_id,actor_id,comment_id,attachment_id,payload_json,created_at) VALUES ('migration-sentinel','comment.created',1,3,'u1',?,?, '{}','2026-01-01')",(comment_id,attachment_id))
        before={name:db.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0] for name in ("tasks","comments","attachments","collaboration_events")};db.commit();db.close()
        backup=migrate(db_path);self.assertIsNotNone(backup);self.assertTrue(Path(backup).name.startswith(f"v12-pre-v{database.SCHEMA_VERSION}-"))
        db=connect(db_path);merged=[tuple(row) for row in db.execute("SELECT task_id,user_id,state,source,version,created_at,updated_at FROM task_subscriptions ORDER BY task_id,user_id")]
        self.assertEqual(merged,[(1,"u1","opted_out","manual",7,"2026-01-01","2026-01-06"),(1,"u2","following","manual",5,"2026-01-01","2026-01-02"),(2,"u1","following","creator",8,"2026-02-01","2026-02-03"),(2,"u2","following","comment",6,"2026-03-01","2026-03-02"),(3,"u1","following","mention",99,"2026-03-01","2026-04-02")])
        self.assertEqual({name:db.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0] for name in before},before);self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0],database.SCHEMA_VERSION);self.assertEqual(db.execute("SELECT checksum FROM schema_migrations WHERE version=14").fetchone()[0],"flowboard-schema-v14");self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0],"ok");self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(),[]);db.close()
        restored=root/"restored-v12.db";shutil.copy2(backup,restored);check=sqlite3.connect(restored);self.assertEqual(check.execute("PRAGMA user_version").fetchone()[0],12);self.assertEqual(check.execute("PRAGMA integrity_check").fetchone()[0],"ok");self.assertEqual(check.execute("SELECT COUNT(*) FROM task_subscriptions").fetchone()[0],len(rows));check.close()
        backup_pattern=f"v12-pre-v{database.SCHEMA_VERSION}-*.db";backup_count=len(list((root/"backups").glob(backup_pattern)));self.assertIsNone(migrate(db_path));self.assertEqual(len(list((root/"backups").glob(backup_pattern))),backup_count)


if __name__=="__main__": unittest.main()
