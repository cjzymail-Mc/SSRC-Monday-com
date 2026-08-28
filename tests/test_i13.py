import json
import base64
import tempfile
import unittest
from pathlib import Path

from flowboard.database import SCHEMA_VERSION, connect, migrate
from flowboard.service import ApiError, FlowboardService
from test_secure_foundation import create_legacy_database


class I13BatchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.db=Path(self.temp.name)/"flowboard.db";create_legacy_database(self.db);migrate(self.db,initial_password="test-password");self.service=FlowboardService(self.db)
        conn=connect(self.db);self.admin=dict(conn.execute("SELECT * FROM users WHERE id='u1'").fetchone());self.viewer=dict(conn.execute("SELECT * FROM users WHERE id='u2'").fetchone());conn.execute("UPDATE workspace_memberships SET role='viewer' WHERE workspace_id=1 AND user_id='u2'");conn.commit();conn.close()

    def tearDown(self):self.temp.cleanup()

    def _new_tasks(self,count=2):
        return [self.service.create_task(self.admin,1,{"title":f"Batch {i}","description":f"Description {i}"}) for i in range(count)]

    def _items(self,ids):
        conn=connect(self.db);result=[{"id":task_id,"version":conn.execute("SELECT version FROM tasks WHERE id=?",(task_id,)).fetchone()[0]} for task_id in ids];conn.close();return result

    def test_v15_description_retention_and_five_atomic_batch_operations(self):
        conn=connect(self.db);self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0],SCHEMA_VERSION);self.assertEqual(conn.execute("SELECT checksum FROM schema_migrations WHERE version=15").fetchone()[0],"flowboard-schema-v15");self.assertEqual(conn.execute("SELECT trash_retention_days FROM workspaces WHERE id=1").fetchone()[0],30);conn.close()
        created=self._new_tasks();ids=[item["id"] for item in created]
        result=self.service.batch_tasks(self.admin,1,{"operation":"update","items":self._items(ids),"changes":{"priority":"高","description":"Bulk detail"}});self.assertEqual(result["updated"],2)
        self.service.batch_tasks(self.admin,1,{"operation":"assign","items":self._items(ids),"changes":{"owner_id":"u2"}})
        group=self.service.create_group(self.admin,1,{"name":"Batch target"});conn=connect(self.db);group_version=conn.execute("SELECT version FROM groups_ WHERE id=?",(group["id"],)).fetchone()[0];conn.close()
        self.service.batch_tasks(self.admin,1,{"operation":"move","items":self._items(ids),"target_group_id":group["id"],"target_group_version":group_version})
        self.service.batch_tasks(self.admin,1,{"operation":"archive","items":self._items(ids)})
        conn=connect(self.db);conn.execute("UPDATE tasks SET archived_at=NULL,archived_by=NULL WHERE id IN (?,?)",ids);conn.commit();conn.close()
        self.service.batch_tasks(self.admin,1,{"operation":"delete","items":self._items(ids)})
        conn=connect(self.db);rows=conn.execute("SELECT priority,description,owner_id,group_id,deleted_at FROM tasks WHERE id IN (?,?) ORDER BY id",ids).fetchall();self.assertTrue(all(tuple(row[:4])==("高","Bulk detail","u2",group["id"]) and row[4] for row in rows))
        actions={row[0]:row[1] for row in conn.execute("SELECT action_code,COUNT(*) FROM activity WHERE task_id IN (?,?) AND action_code LIKE 'task.batch_%' GROUP BY action_code",ids)};self.assertEqual(actions,{"task.batch_archived":2,"task.batch_assigned":2,"task.batch_deleted":2,"task.batch_moved":2,"task.batch_updated":2})
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM audit_log WHERE action_code LIKE 'task.batch_%' AND entity_id IN (?,?)",tuple(map(str,ids))).fetchone()[0],10);self.assertEqual(conn.execute("SELECT COUNT(*) FROM realtime_events WHERE action_code LIKE 'task.batch_%' AND task_id IN (?,?)",ids).fetchone()[0],10);conn.close()

    def test_stale_duplicate_viewer_and_cross_workspace_fail_without_any_mutation_or_events(self):
        ids=[item["id"] for item in self._new_tasks()];conn=connect(self.db);before=[tuple(row) for row in conn.execute("SELECT id,title,version,group_id,sort_order FROM tasks WHERE id IN (?,?) ORDER BY id",ids)];events=conn.execute("SELECT COUNT(*) FROM activity").fetchone()[0];conn.close()
        stale=self._items(ids);stale[1]["version"]+=1
        with self.assertRaises(ApiError) as caught:self.service.batch_tasks(self.admin,1,{"operation":"update","items":stale,"changes":{"title":"must roll back"}})
        self.assertEqual(caught.exception.status,409)
        with self.assertRaises(ApiError) as duplicate:self.service.batch_tasks(self.admin,1,{"operation":"delete","items":[self._items(ids)[0],self._items(ids)[0]]})
        self.assertEqual(duplicate.exception.code,"DUPLICATE_TASK")
        with self.assertRaises(ApiError) as forbidden:self.service.batch_tasks(self.viewer,1,{"operation":"assign","items":self._items(ids),"changes":{"owner_id":"u2"}})
        self.assertEqual(forbidden.exception.status,403)
        conn=connect(self.db);self.assertEqual(before,[tuple(row) for row in conn.execute("SELECT id,title,version,group_id,sort_order FROM tasks WHERE id IN (?,?) ORDER BY id",ids)]);self.assertEqual(conn.execute("SELECT COUNT(*) FROM activity").fetchone()[0],events);conn.close()

    def test_expired_trash_requires_admin_preview_hash_confirmation_and_keeps_audit(self):
        created=self.service.create_task(self.admin,1,{"title":"Purge task"});self.service.create_attachment(self.admin,created["id"],{"name":"purge.txt","content_type":"text/plain","content_base64":base64.b64encode(b"purge bytes").decode()});self.service.delete_task(self.admin,created["id"],{"version":created["version"]});conn=connect(self.db);conn.execute("UPDATE tasks SET deleted_at='2020-01-01T00:00:00+00:00' WHERE id=?",(created["id"],));audit_before=conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0];conn.commit();conn.close()
        with self.assertRaises(ApiError) as denied:self.service.trash_purge_preview(self.viewer,1)
        self.assertEqual(denied.exception.status,403);preview=self.service.trash_purge_preview(self.admin,1);self.assertIn(created["id"],preview["tasks"]);self.assertEqual(preview["counts"]["attachments"],1)
        with self.assertRaises(ApiError) as bad:self.service.trash_purge(self.admin,1,{"as_of":preview["as_of"],"plan_hash":preview["plan_hash"],"confirmation":"wrong"})
        self.assertEqual(bad.exception.code,"PURGE_CONFIRMATION_INVALID");conn=connect(self.db);self.assertIsNotNone(conn.execute("SELECT id FROM tasks WHERE id=?",(created["id"],)).fetchone());conn.close()
        result=self.service.trash_purge(self.admin,1,{"as_of":preview["as_of"],"plan_hash":preview["plan_hash"],"confirmation":preview["confirmation"]});self.assertTrue(result["purged"]);self.assertTrue((Path(self.temp.name)/"backups"/result["safety_backup"]).exists());conn=connect(self.db);self.assertIsNone(conn.execute("SELECT id FROM tasks WHERE id=?",(created["id"],)).fetchone());self.assertGreaterEqual(conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0],audit_before);self.assertIsNotNone(conn.execute("SELECT id FROM audit_log WHERE action_code='trash.purged'").fetchone());self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(),[]);conn.close()

    def test_admin_backup_api_surface_is_verified_and_viewer_is_denied(self):
        created=self.service.create_admin_backup(self.admin,1);self.assertTrue(created["verified"]);self.assertEqual(created["restore_mode"],"offline_cli_only")
        listing=self.service.backups(self.admin,1);self.assertEqual(listing["backups"][0]["name"],created["name"]);self.assertTrue(listing["backups"][0]["valid"])
        verified=self.service.verify_admin_backup(self.admin,1,created["name"]);self.assertTrue(verified["verified"]);self.assertEqual(verified["schema_version"],SCHEMA_VERSION)
        with self.assertRaises(ApiError) as denied:self.service.backups(self.viewer,1)
        self.assertEqual(denied.exception.status,403)
        with self.assertRaises(ApiError) as traversal:self.service.verify_admin_backup(self.admin,1,"../flowboard-evil")
        self.assertEqual(traversal.exception.status,422)


if __name__=="__main__":unittest.main()
