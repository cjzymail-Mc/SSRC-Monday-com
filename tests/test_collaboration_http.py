import base64
import http.client
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path

from flowboard.database import connect
from server import create_server
from test_secure_foundation import create_legacy_database


class CollaborationHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="flowboard-collab-http-");self.db_path=str(Path(self.temp.name)/"flowboard.db")
        create_legacy_database(self.db_path);os.environ["FLOWBOARD_INITIAL_PASSWORD"]="test-password";os.environ["FLOWBOARD_ATTACHMENT_DIR"]=str(Path(self.temp.name)/"private-blobs")
        self.server=create_server("127.0.0.1",0,self.db_path);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.port=self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=2);self.temp.cleanup();os.environ.pop("FLOWBOARD_INITIAL_PASSWORD",None);os.environ.pop("FLOWBOARD_ATTACHMENT_DIR",None)

    def request(self,method,path,body=None,*,cookie=None,csrf=None):
        conn=http.client.HTTPConnection("127.0.0.1",self.port,timeout=5);headers={"Content-Type":"application/json"}
        if cookie:headers["Cookie"]=cookie
        if csrf:headers["X-CSRF-Token"]=csrf
        raw=json.dumps(body).encode() if body is not None else None;conn.request(method,path,raw,headers);response=conn.getresponse();content=response.read();result=(response.status,{k.lower():v for k,v in response.getheaders()},content);conn.close();return result

    def login(self,user="u1"):
        status,headers,raw=self.request("POST","/api/auth/login",{"username":user,"password":"test-password"});self.assertEqual(status,200);payload=json.loads(raw);return headers["set-cookie"],payload["csrf_token"]

    def oversized_request(self,path,cookie,csrf):
        conn=http.client.HTTPConnection("127.0.0.1",self.port,timeout=5);conn.putrequest("POST",path);conn.putheader("Content-Type","application/json");conn.putheader("Cookie",cookie);conn.putheader("X-CSRF-Token",csrf);conn.putheader("Content-Length","2100001");conn.endheaders();response=conn.getresponse();status=response.status;response.read();conn.close();return status

    def test_http_csrf_state_machine_events_preview_and_acl(self):
        cookie,csrf=self.login();before=connect(self.db_path);counts=tuple(before.execute("SELECT (SELECT COUNT(*) FROM comments),(SELECT COUNT(*) FROM collaboration_events)").fetchone());before.close()
        self.assertEqual(self.request("POST","/api/tasks/1/comments",{"body":"blocked"},cookie=cookie)[0],403)
        db=connect(self.db_path);self.assertEqual(tuple(db.execute("SELECT (SELECT COUNT(*) FROM comments),(SELECT COUNT(*) FROM collaboration_events)").fetchone()),counts);db.close()
        status,_,raw=self.request("POST","/api/tasks/1/comments",{"body":"hello","mentions":[{"type":"user","user_id":"u2"}]},cookie=cookie,csrf=csrf);self.assertEqual(status,201);comment=json.loads(raw)
        self.assertEqual(self.request("POST","/api/tasks/1/subscription",{"subscribed":False},cookie=cookie,csrf=csrf)[0],200)
        self.assertEqual(self.request("POST","/api/tasks/1/comments",{"body":"respect opt-out"},cookie=cookie,csrf=csrf)[0],201)
        status,_,raw=self.request("GET","/api/tasks/1",cookie=cookie);self.assertEqual(status,200);self.assertFalse(json.loads(raw)["subscription"]["subscribed"])
        status,_,raw=self.request("POST","/api/tasks/1/subscription",{"subscribed":True},cookie=cookie,csrf=csrf);self.assertEqual(status,200);self.assertEqual(json.loads(raw)["state"],"following")
        status,_,_=self.request("PATCH",f"/api/comments/{comment['id']}",{"version":1,"body":"edited","mentions":[{"type":"all"}]},cookie=cookie,csrf=csrf);self.assertEqual(status,200)
        self.assertEqual(self.request("PATCH",f"/api/comments/{comment['id']}",{"version":1,"body":"stale","mentions":[]},cookie=cookie,csrf=csrf)[0],409)
        content=base64.b64encode(b"safe <b>text</b>").decode();status,_,raw=self.request("POST","/api/tasks/1/attachments",{"name":"note.txt","content_type":"text/plain","content_base64":content},cookie=cookie,csrf=csrf);self.assertEqual(status,201);attachment=json.loads(raw)
        status,headers,raw=self.request("GET",f"/api/attachments/{attachment['id']}/content?preview=1",cookie=cookie);self.assertEqual((status,raw),(200,b"safe <b>text</b>"));self.assertTrue(headers["content-disposition"].startswith("inline"));self.assertIn("sandbox",headers["content-security-policy"]);self.assertEqual(headers["x-content-type-options"],"nosniff")
        db=connect(self.db_path);storage=db.execute("SELECT storage_name FROM attachments WHERE id=?",(attachment["id"],)).fetchone()[0];events={row[0] for row in db.execute("SELECT event_type FROM collaboration_events")};self.assertTrue({"comment.created","comment.updated","mention.added","mention.removed","subscription.unsubscribed","attachment.created"}<=events);db.close()
        self.assertEqual(self.request("GET",f"/flowboard-attachments/{storage}",cookie=cookie)[0],404)
        db=connect(self.db_path);db.execute("UPDATE workspace_memberships SET role='viewer' WHERE user_id='u2'");db.commit();db.close();viewer_cookie,viewer_csrf=self.login("u2")
        for method,path,body in (("POST","/api/tasks/1/comments",{"body":"no"}),("POST","/api/tasks/1/subscription",{"subscribed":True}),("POST","/api/tasks/1/attachments",{"name":"x.txt","content_type":"text/plain","content_base64":base64.b64encode(b"x").decode()})):
            self.assertEqual(self.request(method,path,body,cookie=viewer_cookie,csrf=viewer_csrf)[0],403)
        db=connect(self.db_path);db.execute("UPDATE boards SET access_type='private' WHERE id=1");db.commit();db.close();self.assertEqual(self.request("GET",f"/api/attachments/{attachment['id']}/content",cookie=viewer_cookie)[0],403)

    def test_attachment_attack_matrix_and_failure_atomicity(self):
        cookie,csrf=self.login();bad_names=["../x.txt","C:\\x.txt","x/y.txt","x\x00.txt","x\n.txt","." ]
        db=connect(self.db_path);before=tuple(db.execute("SELECT (SELECT COUNT(*) FROM attachments),(SELECT COUNT(*) FROM activity),(SELECT COUNT(*) FROM collaboration_events)").fetchone());db.close()
        for name in bad_names:
            with self.subTest(name=repr(name)):self.assertEqual(self.request("POST","/api/tasks/1/attachments",{"name":name,"content_type":"text/plain","content_base64":base64.b64encode(b"x").decode()},cookie=cookie,csrf=csrf)[0],422)
        attacks=[("x.svg","image/svg+xml",b"<svg/>"),("x.png","image/png",b"not png"),("x.txt","text/plain",b"\x00binary"),("x.pdf","application/pdf",b"<html>")]
        for name,mime,value in attacks:
            with self.subTest(name=name):self.assertEqual(self.request("POST","/api/tasks/1/attachments",{"name":name,"content_type":mime,"content_base64":base64.b64encode(value).decode()},cookie=cookie,csrf=csrf)[0],415)
        db=connect(self.db_path);self.assertEqual(tuple(db.execute("SELECT (SELECT COUNT(*) FROM attachments),(SELECT COUNT(*) FROM activity),(SELECT COUNT(*) FROM collaboration_events)").fetchone()),before);db.close();blob_root=Path(os.environ["FLOWBOARD_ATTACHMENT_DIR"]);self.assertFalse(blob_root.exists() and any(blob_root.iterdir()))

    def test_complete_acl_event_preview_limit_and_request_boundary_matrix(self):
        cookie,csrf=self.login();viewer_cookie,viewer_csrf=self.login("u2")
        status,_,raw=self.request("POST","/api/tasks/1/comments",{"body":"root","mentions":[{"type":"user","user_id":"u2"}]},cookie=cookie,csrf=csrf);self.assertEqual(status,201);root=json.loads(raw)
        status,_,raw=self.request("POST","/api/tasks/1/comments",{"body":"reply","parent_id":root["id"]},cookie=cookie,csrf=csrf);self.assertEqual(status,201);reply=json.loads(raw)
        status,_,_=self.request("PATCH",f"/api/comments/{root['id']}",{"version":1,"body":"edited","mentions":[]},cookie=cookie,csrf=csrf);self.assertEqual(status,200)
        status,_,_=self.request("DELETE",f"/api/comments/{root['id']}",{"version":2},cookie=cookie,csrf=csrf);self.assertEqual(status,200)
        status,_,raw=self.request("GET","/api/tasks/1",cookie=cookie);detail=json.loads(raw);deleted=next(row for row in detail["comments"] if row["id"]==root["id"]);self.assertIsNone(deleted["body"]);self.assertEqual(next(row for row in detail["comments"] if row["id"]==reply["id"])["parent_id"],root["id"])
        self.assertEqual(self.request("POST","/api/tasks/1/subscription",{"subscribed":False},cookie=cookie,csrf=csrf)[0],200);self.assertEqual(self.request("POST","/api/tasks/1/subscription",{"subscribed":True},cookie=cookie,csrf=csrf)[0],200)
        png=b"\x89PNG\r\n\x1a\n"+b"safe";status,_,raw=self.request("POST","/api/tasks/1/attachments",{"name":"安全 图.png","content_type":"image/png","content_base64":base64.b64encode(png).decode()},cookie=cookie,csrf=csrf);self.assertEqual(status,201);image=json.loads(raw)
        status,headers,body=self.request("GET",f"/api/attachments/{image['id']}/content?preview=1",cookie=cookie);self.assertEqual((status,body),(200,png));self.assertIn("inline",headers["content-disposition"]);self.assertIn("filename*=UTF-8''",headers["content-disposition"]);self.assertEqual(headers["cache-control"],"private, no-store")
        pdf=b"%PDF-1.4\n%%EOF";status,_,raw=self.request("POST","/api/tasks/1/attachments",{"name":"doc.pdf","content_type":"application/pdf","content_base64":base64.b64encode(pdf).decode()},cookie=cookie,csrf=csrf);self.assertEqual(status,201);pdf_meta=json.loads(raw);self.assertEqual(self.request("GET",f"/api/attachments/{pdf_meta['id']}/content?preview=1",cookie=cookie)[0],415)
        for index in range(18):self.assertEqual(self.request("POST","/api/tasks/1/attachments",{"name":f"f{index}.txt","content_type":"text/plain","content_base64":base64.b64encode(str(index).encode()).decode()},cookie=cookie,csrf=csrf)[0],201)
        db=connect(self.db_path);before=tuple(db.execute("SELECT (SELECT COUNT(*) FROM attachments WHERE deleted_at IS NULL),(SELECT COUNT(*) FROM activity),(SELECT COUNT(*) FROM collaboration_events)").fetchone());db.close();blobs={p.name for p in Path(os.environ["FLOWBOARD_ATTACHMENT_DIR"]).iterdir()}
        self.assertEqual(self.request("POST","/api/tasks/1/attachments",{"name":"overflow.txt","content_type":"text/plain","content_base64":base64.b64encode(b"overflow").decode()},cookie=cookie,csrf=csrf)[0],422)
        db=connect(self.db_path);after=tuple(db.execute("SELECT (SELECT COUNT(*) FROM attachments WHERE deleted_at IS NULL),(SELECT COUNT(*) FROM activity),(SELECT COUNT(*) FROM collaboration_events)").fetchone());db.close();self.assertEqual(after,before);self.assertEqual({p.name for p in Path(os.environ["FLOWBOARD_ATTACHMENT_DIR"]).iterdir()},blobs)
        self.assertEqual(self.request("DELETE",f"/api/attachments/{image['id']}",{"version":1},cookie=cookie,csrf=csrf)[0],200);self.assertEqual(self.oversized_request("/api/tasks/1/attachments",cookie,csrf),413)
        db=connect(self.db_path);db.execute("UPDATE workspace_memberships SET role='viewer' WHERE workspace_id=1 AND user_id='u2'");db.commit();db.close()
        viewer_ops=(("POST","/api/tasks/1/comments",{"body":"no","parent_id":reply["id"]}),("PATCH",f"/api/comments/{reply['id']}",{"version":1,"body":"no"}),("DELETE",f"/api/comments/{reply['id']}",{"version":1}),("DELETE",f"/api/attachments/{pdf_meta['id']}",{"version":1}),("POST","/api/tasks/1/subscription",{"subscribed":False}))
        for method,path,body in viewer_ops:self.assertEqual(self.request(method,path,body,cookie=viewer_cookie,csrf=viewer_csrf)[0],403)
        db=connect(self.db_path);events={row[0] for row in db.execute("SELECT event_type FROM collaboration_events")};actions={row[0] for row in db.execute("SELECT action_code FROM activity")};self.assertTrue({"comment.deleted","attachment.deleted","subscription.subscribed"}<=events);self.assertTrue({"comment.deleted","attachment.deleted","subscription.subscribed"}<=actions);db.execute("UPDATE boards SET access_type='private' WHERE id=1");db.commit();db.close()
        self.assertEqual(self.request("GET","/api/tasks/1",cookie=viewer_cookie)[0],403);self.assertEqual(self.request("GET",f"/api/attachments/{pdf_meta['id']}/content",cookie=viewer_cookie)[0],403)


if __name__=="__main__":unittest.main()
