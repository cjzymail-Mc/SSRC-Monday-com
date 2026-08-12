import http.client
import json
import shutil
import tempfile
import threading
import unittest
from pathlib import Path

import flowboard.database as database
from flowboard.database import connect, migrate
from flowboard.service import ApiError, FlowboardService
from server import create_server
from test_secure_foundation import create_legacy_database


class I12ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.db=Path(self.temp.name)/"flowboard.db";shutil.copy2(Path(__file__).parents[1]/"flowboard.db",self.db);migrate(self.db);self.service=FlowboardService(self.db)
        conn=connect(self.db);self.admin=dict(conn.execute("SELECT * FROM users WHERE id='u1'").fetchone());self.member=dict(conn.execute("SELECT * FROM users WHERE id='u2'").fetchone());conn.close()
    def tearDown(self):self.temp.cleanup()

    def _event(self,conn,key,board_id=1,action=None):
        conn.execute("INSERT INTO realtime_events(event_key,workspace_id,board_id,task_id,actor_user_id,action_code,created_at) VALUES (?,1,?,1,'u1',?,?)",(key,board_id,action or key,"2026-08-03T00:00:00+00:00"))
        return conn.execute("SELECT id FROM realtime_events WHERE event_key=?",(key,)).fetchone()[0]

    def test_notification_projection_due_idempotence_read_and_acl_revocation(self):
        comment=self.service.create_comment(self.admin,1,{"body":"notify","mentions":[{"type":"user","user_id":"u2"}]})
        self.service.process_notifications_once(now="2026-08-03T00:00:00+00:00");self.service.process_notifications_once(now="2026-08-03T00:00:00+00:00")
        listing=self.service.notifications(self.member,1);self.assertEqual(sum(item["kind"]=="mention.added" for item in listing["items"]),1)
        item=next(item for item in listing["items"] if item["kind"]=="mention.added");self.assertIsNone(item["read_at"]);self.service.read_notification(self.member,item["id"],{"version":item["version"]});self.assertIsNotNone(self.service.notifications(self.member,1)["items"][0]["read_at"])
        conn=connect(self.db);conn.execute("UPDATE tasks SET due='2026-08-03' WHERE id=1");conn.execute("INSERT OR REPLACE INTO task_subscriptions(task_id,user_id,state,source,version,created_at,updated_at) VALUES (1,'u2','following','manual',1,'x','x')");conn.commit();conn.close()
        self.service.process_notifications_once(now="2026-08-03T12:00:00+00:00");self.service.process_notifications_once(now="2026-08-03T12:00:00+00:00")
        conn=connect(self.db);self.assertEqual(conn.execute("SELECT COUNT(*) FROM notifications WHERE recipient_user_id='u2' AND event_key LIKE 'due:%'").fetchone()[0],1);conn.execute("UPDATE boards SET access_type='private' WHERE id=1");conn.execute("DELETE FROM board_memberships WHERE board_id=1 AND user_id='u2'");conn.commit();conn.close()
        hidden=self.service.notifications(self.member,1);self.assertEqual(hidden["items"],[]);self.assertEqual(hidden["unread"],0)

    def test_global_search_five_types_special_input_and_acl(self):
        self.service.create_comment(self.admin,1,{"body":"Needle comment"});self.service.create_attachment(self.admin,1,{"name":"Needle-file.txt","content_type":"text/plain","content_base64":"eA=="})
        conn=connect(self.db);conn.execute("UPDATE boards SET name='Needle board' WHERE id=1");conn.execute("UPDATE tasks SET title='Needle task' WHERE id=1");conn.execute("UPDATE users SET name='Needle member' WHERE id='u2'");conn.commit();conn.close()
        result=self.service.global_search(self.admin,1,"Needle",limit=50);self.assertEqual({item["type"] for item in result["items"]},{"board","task","comment","attachment","member"})
        self.assertEqual(self.service.global_search(self.admin,1,"%_")["items"],[]);self.assertEqual(self.service.global_search(self.admin,1,"   ")["items"],[])
        with self.assertRaises(ApiError):self.service.global_search(self.admin,1,"x"*101)
        conn=connect(self.db);conn.execute("UPDATE boards SET access_type='private' WHERE id=1");conn.commit();conn.close();self.assertEqual({item["type"] for item in self.service.global_search(self.member,1,"Needle",limit=50)["items"]},{"member"})

    def test_realtime_cursor_audit_permissions_and_csv_formula_safety(self):
        initial=self.service.realtime_poll(self.member,1);task=self.service.task_detail(self.admin,1);self.service.update_task(self.admin,1,{"version":task["version"],"title":"Realtime changed"});delta=self.service.realtime_poll(self.member,1,cursor=initial["cursor"])
        self.assertTrue(any(event["action"]=="task.field_values.updated" and event["actor_user_id"]=="u1" for event in delta["events"]));self.assertGreater(delta["cursor"],initial["cursor"])
        audit=self.service.audit(self.admin,1);self.assertTrue(any(item["action_code"]=="task.field_values.updated" for item in audit["items"]))
        with self.assertRaises(ApiError) as caught:self.service.audit(self.member,1)
        self.assertEqual(caught.exception.status,403)
        conn=connect(self.db);conn.execute("INSERT INTO audit_log(source_key,workspace_id,action_code,outcome,entity_type,entity_id,details_json,created_at) VALUES ('formula',1,'csv.test','success','task','=cmd','{}','2026')");conn.commit();conn.close();self.assertIn("'=cmd",self.service.audit_csv(self.admin,1))

    def test_realtime_raw_scan_pages_visible_events_without_loss_or_duplicates(self):
        conn=connect(self.db);start=conn.execute("SELECT COALESCE(MAX(id),0) FROM realtime_events WHERE workspace_id=1").fetchone()[0];expected=[self._event(conn,f"page-{i}") for i in range(5)];conn.commit();conn.close()
        cursor=start;seen=[]
        for _ in range(4):
            page=self.service.realtime_poll(self.member,1,cursor=cursor,limit=2);self.assertGreaterEqual(page["cursor"],cursor);cursor=page["cursor"];seen.extend(event["id"] for event in page["events"])
        self.assertEqual(seen,expected);self.assertEqual(len(seen),len(set(seen)))
        exhausted=self.service.realtime_poll(self.member,1,cursor=cursor,limit=2);self.assertEqual(exhausted["events"],[]);self.assertEqual(exhausted["cursor"],cursor)

    def test_realtime_hidden_windows_advance_and_later_visible_event_is_reachable(self):
        conn=connect(self.db);conn.execute("INSERT INTO boards(workspace_id,name,description,color,access_type,version,created_at) VALUES (1,'Hidden','','purple','private',1,'2026')");hidden_board=conn.execute("SELECT last_insert_rowid()").fetchone()[0];start=conn.execute("SELECT COALESCE(MAX(id),0) FROM realtime_events WHERE workspace_id=1").fetchone()[0]
        hidden=[];visible=[]
        for i in range(7):
            hidden.append(self._event(conn,f"hidden-{i}",hidden_board,action=f"secret.action.{i}"))
            if i in (1,4):visible.append(self._event(conn,f"visible-{i}",1))
        conn.commit();conn.close();cursor=start;seen=[];empty_progress=0
        for _ in range(8):
            previous=cursor;page=self.service.realtime_poll(self.member,1,cursor=cursor,limit=2);cursor=page["cursor"]
            if not page["events"] and cursor>previous:empty_progress+=1
            seen.extend(page["events"])
            if cursor==previous:break
        self.assertEqual([event["id"] for event in seen],visible);self.assertGreater(empty_progress,0)
        encoded=json.dumps(seen);self.assertFalse(any(event_id in [event["id"] for event in seen] for event_id in hidden));self.assertNotIn("secret.action",encoded);self.assertTrue(all(event["board_id"]!=hidden_board for event in seen))

    def test_realtime_revocation_after_cursor_does_not_block_later_permitted_event(self):
        start=self.service.realtime_poll(self.member,1)["cursor"];conn=connect(self.db);conn.execute("UPDATE boards SET access_type='private' WHERE id=1");conn.execute("DELETE FROM board_memberships WHERE board_id=1 AND user_id='u2'");revoked=self._event(conn,"revoked-after-cursor",1,"secret.revoked")
        conn.execute("INSERT INTO boards(workspace_id,name,description,color,access_type,version,created_at) VALUES (1,'Allowed','','purple','open',1,'2026')");allowed_board=conn.execute("SELECT last_insert_rowid()").fetchone()[0];allowed=self._event(conn,"allowed-after-revoke",allowed_board,"allowed.update");conn.commit();conn.close()
        first=self.service.realtime_poll(self.member,1,cursor=start,limit=1);self.assertEqual(first["events"],[]);self.assertEqual(first["cursor"],revoked)
        second=self.service.realtime_poll(self.member,1,cursor=first["cursor"],limit=1);self.assertEqual([event["id"] for event in second["events"]],[allowed]);self.assertNotIn("secret.revoked",json.dumps(second))

    def test_v13_to_v14_backup_restore_and_idempotence(self):
        path=Path(self.temp.name)/"v13.db";create_legacy_database(path);conn=connect(path);database._migration_v1(conn,"test-password")
        for version in range(2,14):getattr(database,f"_migration_v{version}")(conn)
        before={name:conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0] for name in ("tasks","comments","activity","collaboration_events")};conn.close();backup=migrate(path);self.assertTrue(Path(backup).name.startswith("v13-pre-v15-"));old=connect(backup);self.assertEqual(old.execute("PRAGMA user_version").fetchone()[0],13);old.close();conn=connect(path)
        self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0],15);self.assertEqual(conn.execute("SELECT checksum FROM schema_migrations WHERE version=14").fetchone()[0],"flowboard-schema-v14");self.assertEqual(conn.execute("SELECT checksum FROM schema_migrations WHERE version=15").fetchone()[0],"flowboard-schema-v15");self.assertEqual(before,{name:conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0] for name in before});self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0],"ok");self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(),[]);count=conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0];conn.close();self.assertIsNone(migrate(path));conn=connect(path);self.assertEqual(conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0],count);conn.close()


class I12HttpTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.db=Path(self.temp.name)/"flowboard.db";shutil.copy2(Path(__file__).parents[1]/"flowboard.db",self.db);self.server=create_server("127.0.0.1",0,self.db);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.port=self.server.server_address[1];self.cookies={};self.csrf={}
        for user in ("u1","u2"):self._login(user)
    def tearDown(self):self.server.shutdown();self.server.server_close();self.temp.cleanup()
    def _request(self,user,method,path,body=None):
        headers={"Cookie":self.cookies.get(user,"")};raw=None
        if body is not None:raw=json.dumps(body).encode();headers["Content-Type"]="application/json";headers["X-CSRF-Token"]=self.csrf.get(user,"")
        conn=http.client.HTTPConnection("127.0.0.1",self.port,timeout=20);conn.request(method,path,raw,headers);response=conn.getresponse();data=response.read();headers=dict(response.getheaders());conn.close();return response.status,headers,data
    def _login(self,user):
        conn=http.client.HTTPConnection("127.0.0.1",self.port);raw=json.dumps({"username":user,"password":"flowboard"}).encode();conn.request("POST","/api/auth/login",raw,{"Content-Type":"application/json"});response=conn.getresponse();payload=json.loads(response.read());self.cookies[user]=response.getheader("Set-Cookie").split(";",1)[0];self.csrf[user]=payload["csrf_token"];conn.close()
    def test_http_auth_csrf_pagination_search_notifications_poll_and_audit(self):
        status,_,_=self._request("", "GET","/api/workspaces/1/search?q=x");self.assertEqual(status,401)
        status,_,_=self._request("u1","POST","/api/workspaces/1/notifications/read-all",{});self.assertEqual(status,200)
        status,_,raw=self._request("u1","GET","/api/workspaces/1/search?q=%25_&limit=51");self.assertEqual(status,422);self.assertIn(b"VALIDATION_ERROR",raw)
        status,_,raw=self._request("u2","GET","/api/admin/workspaces/1/audit");self.assertEqual(status,403)
        status,headers,raw=self._request("u1","GET","/api/admin/workspaces/1/audit.csv");self.assertEqual(status,200);self.assertIn("text/csv",headers["Content-Type"]);self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        status,_,raw=self._request("u1","GET","/api/workspaces/1/events/poll?cursor=0&limit=201");self.assertEqual(status,422)

    def test_sse_last_event_id_uses_same_bounded_cursor_as_poll(self):
        conn=connect(self.db);start=conn.execute("SELECT COALESCE(MAX(id),0) FROM realtime_events WHERE workspace_id=1").fetchone()[0];ids=[]
        for i in range(5):
            conn.execute("INSERT INTO realtime_events(event_key,workspace_id,board_id,task_id,actor_user_id,action_code,created_at) VALUES (?,1,1,1,'u1',?,?)",(f"http-page-{i}",f"http.page.{i}","2026"));ids.append(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        conn.commit();conn.close()
        status,_,raw=self._request("u1","GET",f"/api/workspaces/1/events/stream?cursor={start}&limit=2");self.assertEqual(status,200);text=raw.decode();self.assertIn(f"id: {ids[1]}",text);self.assertNotIn(f"id: {ids[-1]}\n",text)
        conn=http.client.HTTPConnection("127.0.0.1",self.port,timeout=20);conn.request("GET","/api/workspaces/1/events/stream?limit=2",headers={"Cookie":self.cookies["u1"],"Last-Event-ID":str(ids[1])});response=conn.getresponse();second=response.read().decode();conn.close();self.assertEqual(response.status,200);self.assertIn(f"id: {ids[3]}",second);self.assertNotIn(f"id: {ids[-1]}\n",second)
        status,_,raw=self._request("u1","GET",f"/api/workspaces/1/events/poll?cursor={ids[3]}&limit=2");payload=json.loads(raw);self.assertEqual(status,200);self.assertEqual(payload["cursor"],ids[4]);self.assertEqual([event["id"] for event in payload["events"]],[ids[4]])
        conn=connect(self.db);hidden_start=ids[-1];conn.execute("INSERT INTO boards(workspace_id,name,description,color,access_type,version,created_at) VALUES (1,'SSE Hidden','','purple','private',1,'2026')");hidden_board=conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        for i in range(2):conn.execute("INSERT INTO realtime_events(event_key,workspace_id,board_id,task_id,actor_user_id,action_code,created_at) VALUES (?,1,?,1,'u1',?,?)",(f"sse-hidden-{i}",hidden_board,f"secret.sse.{i}","2026"))
        hidden_last=conn.execute("SELECT last_insert_rowid()").fetchone()[0];conn.execute("INSERT INTO realtime_events(event_key,workspace_id,board_id,task_id,actor_user_id,action_code,created_at) VALUES ('sse-visible',1,1,1,'u1','visible.sse','2026')");visible_id=conn.execute("SELECT last_insert_rowid()").fetchone()[0];conn.commit();conn.close()
        status,_,raw=self._request("u2","GET",f"/api/workspaces/1/events/stream?cursor={hidden_start}&limit=2");progress=raw.decode();self.assertEqual(status,200);self.assertIn(f"id: {hidden_last}",progress);self.assertIn('"events": []',progress);self.assertNotIn("secret.sse",progress)
        conn=http.client.HTTPConnection("127.0.0.1",self.port,timeout=20);conn.request("GET","/api/workspaces/1/events/stream?limit=2",headers={"Cookie":self.cookies["u2"],"Last-Event-ID":str(hidden_last)});response=conn.getresponse();reached=response.read().decode();conn.close();self.assertEqual(response.status,200);self.assertIn(f"id: {visible_id}",reached);self.assertIn("visible.sse",reached)


if __name__=="__main__":unittest.main()
