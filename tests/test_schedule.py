import http.client
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from flowboard.schedule import ScheduleError, critical_path, parse_day, project
from flowboard.database import (SCHEMA_VERSION,_migration_v1,_migration_v2,_migration_v3,_migration_v4,_migration_v5,
    _migration_v6,_migration_v7,_migration_v8,_migration_v9,connect,migrate)
from server import create_server
from test_secure_foundation import create_legacy_database


class ScheduleProjectionTests(unittest.TestCase):
    def test_fixed_dynamic_and_cross_year_projection(self):
        tasks=[{"id":1,"title":"A","group_id":1,"group_name":"G","parent_id":None,"subtask_order":0,"version":1,"start_date":"2026-12-30","due":"2027-01-02","field_values":{"8":{"start":"2026-02-01","end":"2026-02-03"}}},{"id":2,"title":"B","group_id":1,"group_name":"G","parent_id":1,"subtask_order":0,"version":1,"start_date":None,"due":"2026-08-02","field_values":{}}]
        scheduled,unscheduled,bounds=project(tasks,{"kind":"fixed"},{})
        self.assertEqual([4,1],[scheduled[0]["duration_days"],scheduled[1]["duration_days"]])
        self.assertEqual(bounds,{"start":"2026-08-02","end":"2027-01-02","span_days":154})
        dynamic,missing,_=project(tasks,{"kind":"dynamic","id":8},{8:"timeline"})
        self.assertEqual((dynamic[0]["start"],dynamic[0]["end"]),("2026-02-01","2026-02-03"));self.assertEqual([2],[item["id"] for item in missing])

    def test_invalid_dates_fail_closed_and_huge_range_is_bounded(self):
        base={"id":1,"title":"A","group_id":1,"group_name":"G","parent_id":None,"subtask_order":0,"version":1,"field_values":{}}
        for start,end in (("2026-02-30","2026-03-01"),("2026-03-02","2026-03-01"),("1899-01-01","1900-01-01")):
            scheduled,unscheduled,_=project([{**base,"start_date":start,"due":end}],{"kind":"fixed"},{})
            self.assertFalse(scheduled);self.assertEqual(len(unscheduled),1)
        with self.assertRaises(ScheduleError):project([{**base,"start_date":"2000-01-01","due":"2200-01-01"}],{"kind":"fixed"},{})
        self.assertIsNone(parse_day("2026-02-30"))

    def test_critical_path_filters_hidden_edges_and_blocks_cycles(self):
        tasks=[{"id":1,"duration_days":2},{"id":2,"duration_days":3},{"id":3,"duration_days":1}]
        result,edges=critical_path(tasks,[{"id":1,"predecessor_id":1,"successor_id":2},{"id":2,"predecessor_id":2,"successor_id":99}])
        self.assertEqual(result["task_ids"],[1,2]);self.assertEqual(len(edges),1)
        cycle,_=critical_path(tasks,[{"id":1,"predecessor_id":1,"successor_id":2},{"id":2,"predecessor_id":2,"successor_id":1}])
        self.assertTrue(cycle["blocked"]);self.assertEqual(cycle["diagnostic"]["code"],"DEPENDENCY_CYCLE")


class ScheduleHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.db=str(Path(self.temp.name)/"flowboard.db");create_legacy_database(self.db);os.environ["FLOWBOARD_INITIAL_PASSWORD"]="test-password";self.server=create_server("127.0.0.1",0,self.db);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.port=self.server.server_address[1]
    def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join(timeout=2);self.temp.cleanup()
    def request(self,method,path,body=None,cookie=None,csrf=None):
        conn=http.client.HTTPConnection("127.0.0.1",self.port);headers={"Content-Type":"application/json"}
        if cookie:headers["Cookie"]=cookie
        if csrf:headers["X-CSRF-Token"]=csrf
        conn.request(method,path,json.dumps(body).encode() if body is not None else None,headers);response=conn.getresponse();raw=response.read();headers=dict(response.getheaders());conn.close();return response.status,json.loads(raw or b"{}"),headers
    def login(self,user="u1"):
        status,payload,headers=self.request("POST","/api/auth/login",{"username":user,"password":"test-password"});self.assertEqual(status,200);return headers["Set-Cookie"].split(";",1)[0],payload["csrf_token"]
    def bootstrap(self,cookie):
        status,payload,_=self.request("GET","/api/bootstrap?board_id=1",cookie=cookie);self.assertEqual(status,200,payload);return payload
    def make_field(self,cookie,csrf,kind,name):
        boot=self.bootstrap(cookie);status,field,_=self.request("POST","/api/boards/1/fields",{"board_version":boot["board"]["version"],"name":name,"field_type":kind,"config":{},"options":[]},cookie,csrf);self.assertEqual(status,201,field);return field
    def test_schedule_read_write_conflicts_permissions_and_saved_views(self):
        cookie,csrf=self.login();status,boot,_=self.request("GET","/api/bootstrap?board_id=1",cookie=cookie);self.assertEqual(status,200);task=boot["groups"][0]["tasks"][0]
        body={"version":task["version"],"board_version":boot["board"]["version"],"source":{"kind":"fixed"},"start":"2026-08-01","end":"2026-08-03","dependency_policy":"none","successor_versions":{}}
        status,updated,_=self.request("POST",f"/api/tasks/{task['id']}/schedule",body,cookie,csrf);self.assertEqual(status,200,updated)
        status,conflict,_=self.request("POST",f"/api/tasks/{task['id']}/schedule",body,cookie,csrf);self.assertEqual((status,conflict["error"]["code"]),(409,"VERSION_CONFLICT"))
        presentation={"version":1,"source":{"kind":"fixed"},"scale":"week","show_dependencies":True,"show_critical_path":True,"baseline":"disabled"}
        status,result,_=self.request("POST","/api/boards/1/schedule",{"query":{"version":1,"filter":{"op":"and","children":[]},"sort":[]},"presentation":presentation},cookie,csrf);self.assertEqual(status,200,result);self.assertIn(task["id"],[item["id"] for item in result["tasks"]])
        status,view,_=self.request("POST","/api/boards/1/views",{"name":"Gantt","scope":"personal","view_type":"gantt","filter":{"op":"and","children":[]},"sort":[],"visible_fields":[],"column_order":["title"],"presentation":presentation,"is_default":False},cookie,csrf);self.assertEqual(status,201,view)
        conn=connect(self.db);conn.execute("UPDATE workspace_memberships SET role='viewer' WHERE user_id='u2'");conn.commit();conn.close()
        viewer_cookie,viewer_csrf=self.login("u2");status,denied,_=self.request("POST",f"/api/tasks/{task['id']}/schedule",{**body,"version":updated["version"],"board_version":updated["board_version"]},viewer_cookie,viewer_csrf);self.assertEqual(status,403,denied)

    def test_dynamic_date_and_timeline_successor_push_are_source_aware_atomic(self):
        cookie,csrf=self.login()
        for kind in ("date","timeline"):
            with self.subTest(kind=kind):
                field=self.make_field(cookie,csrf,kind,"Schedule "+kind);boot=self.bootstrap(cookie);main=boot["groups"][0]["tasks"][0];successor=boot["groups"][0]["tasks"][1]
                main_value="2026-08-01" if kind=="date" else {"start":"2026-08-01","end":"2026-08-03"};successor_value="2026-08-02" if kind=="date" else {"start":"2026-08-02","end":"2026-08-05"}
                status,main,_=self.request("PATCH",f"/api/tasks/{main['id']}",{"version":main["version"],"field_values":{str(field["id"]):main_value}},cookie,csrf);self.assertEqual(status,200,main)
                status,successor,_=self.request("PATCH",f"/api/tasks/{successor['id']}",{"version":successor["version"],"field_values":{str(field["id"]):successor_value}},cookie,csrf);self.assertEqual(status,200,successor)
                conn=connect(self.db);conn.execute("DELETE FROM task_dependencies");conn.execute("INSERT INTO task_dependencies(predecessor_id,successor_id,created_by,created_at) VALUES (?,?,?,datetime('now'))",(main["id"],successor["id"],"u1"));conn.commit();fixed_before=conn.execute("SELECT due FROM tasks WHERE id=?",(successor["id"],)).fetchone()[0];conn.close()
                boot=self.bootstrap(cookie);main=next(t for g in boot["groups"] for t in g["tasks"] if t["id"]==main["id"]);successor=next(t for g in boot["groups"] for t in g["tasks"] if t["id"]==successor["id"]);source={"kind":"dynamic","id":field["id"]};end="2026-08-10"
                body={"version":main["version"],"board_version":boot["board"]["version"],"source":source,"start":end,"end":end,"dependency_policy":"push_successors_once","successor_versions":{str(successor["id"]):successor["version"]}}
                status,result,_=self.request("POST",f"/api/tasks/{main['id']}/schedule",body,cookie,csrf);self.assertEqual(status,200,result);self.assertEqual(len(result["pushed_successors"]),1)
                current=self.bootstrap(cookie);changed=next(t for g in current["groups"] for t in g["tasks"] if t["id"]==successor["id"]);actual=changed["field_values"][str(field["id"])]
                self.assertEqual(actual,end if kind=="date" else {"start":"2026-08-10","end":"2026-08-13"});conn=connect(self.db);self.assertEqual(conn.execute("SELECT due FROM tasks WHERE id=?",(successor["id"],)).fetchone()[0],fixed_before);conn.close()
                stable=current;main=next(t for g in stable["groups"] for t in g["tasks"] if t["id"]==result["id"]);successor=next(t for g in stable["groups"] for t in g["tasks"] if t["id"]==successor["id"])
                no_op={"version":main["version"],"board_version":stable["board"]["version"],"source":source,"start":"2026-08-04","end":"2026-08-04","dependency_policy":"push_successors_once","successor_versions":{str(successor["id"]):successor["version"]}}
                status,result,_=self.request("POST",f"/api/tasks/{main['id']}/schedule",no_op,cookie,csrf);self.assertEqual(status,200,result);self.assertEqual(result["pushed_successors"],[])

    def test_atomic_versions_csrf_validation_and_task_bound(self):
        cookie,csrf=self.login();boot=self.bootstrap(cookie);main=boot["groups"][0]["tasks"][0];successor=boot["groups"][0]["tasks"][1];conn=connect(self.db);conn.execute("DELETE FROM task_dependencies");conn.execute("INSERT INTO task_dependencies(predecessor_id,successor_id,created_by,created_at) VALUES (?,?,?,datetime('now'))",(main["id"],successor["id"],"u1"));conn.commit();conn.close()
        body={"version":main["version"],"board_version":boot["board"]["version"],"source":{"kind":"fixed"},"start":"2026-09-01","end":"2026-09-02","dependency_policy":"push_successors_once","successor_versions":{str(successor["id"]):successor["version"]+1}}
        missing={**body,"successor_versions":{}}
        status,error,_=self.request("POST",f"/api/tasks/{main['id']}/schedule",missing,cookie,csrf);self.assertEqual((status,error["error"]["code"]),(428,"SUCCESSOR_VERSIONS_REQUIRED"))
        status,error,_=self.request("POST",f"/api/tasks/{main['id']}/schedule",body,cookie,csrf);self.assertEqual((status,error["error"]["code"]),(409,"VERSION_CONFLICT"));after=self.bootstrap(cookie);same=next(t for g in after["groups"] for t in g["tasks"] if t["id"]==main["id"]);self.assertEqual((same.get("start_date"),same["due"]),(None,main["due"]))
        status,error,_=self.request("POST",f"/api/tasks/{main['id']}/schedule",{**body,"successor_versions":{str(successor["id"]):successor["version"]}},cookie);self.assertEqual(status,403,error)
        for payload,code in (({"query":{},"presentation":{"version":1,"source":{"kind":"fixed"},"scale":"week","baseline":"disabled","bad":1}},"SCHEDULE_PRESENTATION_INVALID"),({"query":{"version":1,"filter":{"op":"and","children":[]},"sort":[]},"presentation":{"version":1,"source":{"kind":"dynamic","id":99999},"scale":"week","baseline":"disabled"}},"SCHEDULE_SOURCE_INVALID"),({"query":{},"presentation":{},"unknown":1},"UNKNOWN_FIELD")):
            status,error,_=self.request("POST","/api/boards/1/schedule",payload,cookie,csrf);self.assertEqual((status,error["error"]["code"]),(422,code))
        conn=connect(self.db);group=conn.execute("SELECT id FROM groups_ WHERE board_id=1 AND deleted_at IS NULL LIMIT 1").fetchone()[0];existing=conn.execute("SELECT COUNT(*) FROM tasks t JOIN groups_ g ON g.id=t.group_id WHERE g.board_id=1 AND t.deleted_at IS NULL AND t.archived_at IS NULL").fetchone()[0]
        for index in range(500-existing):conn.execute("INSERT INTO tasks(group_id,title,due,created_at,updated_at) VALUES (?,?,?,datetime('now'),datetime('now'))",(group,f"bounded-{index}","未设置"))
        conn.commit();conn.close();query={"version":1,"filter":{"op":"and","children":[]},"sort":[]};presentation={"version":1,"source":{"kind":"fixed"},"scale":"week","baseline":"disabled"}
        status,result,_=self.request("POST","/api/boards/1/schedule",{"query":query,"presentation":presentation},cookie,csrf);self.assertEqual((status,result["total"]),(200,500));conn=connect(self.db);conn.execute("INSERT INTO tasks(group_id,title,due,created_at,updated_at) VALUES (?,?,?,datetime('now'),datetime('now'))",(group,"bounded-501","未设置"));conn.commit();conn.close()
        with patch("flowboard.service.project_schedule") as projection:
            status,error,_=self.request("POST","/api/boards/1/schedule",{"query":query,"presentation":presentation},cookie,csrf);self.assertEqual((status,error["error"]["code"]),(422,"SCHEDULE_TASK_LIMIT"));projection.assert_not_called()


class ScheduleMigrationTests(unittest.TestCase):
    def test_v9_to_latest_preserves_saved_views_backup_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as root:
            path=str(Path(root)/"v9.db");create_legacy_database(path);conn=connect(path)
            for migration in (_migration_v1,_migration_v2,_migration_v3,_migration_v4,_migration_v5,_migration_v6,_migration_v7,_migration_v8,_migration_v9):migration(conn,"test-password") if migration is _migration_v1 else migration(conn)
            conn.execute("INSERT INTO saved_views(board_id,owner_id,scope,view_type,name,filter_json,sort_json,visible_fields_json,column_order_json,is_default,version,created_at,updated_at,deleted_at,presentation_json) VALUES (1,'u1','personal','calendar','Legacy calendar','{\"op\":\"and\",\"children\":[]}','[]','[4]','[\"title\",4]',1,7,'a','b','deleted','{\"version\":1,\"date_field_id\":4}')");conn.commit();before=tuple(conn.execute("SELECT board_id,owner_id,scope,view_type,name,filter_json,sort_json,visible_fields_json,column_order_json,is_default,version,created_at,updated_at,deleted_at,presentation_json FROM saved_views WHERE name='Legacy calendar'").fetchone());conn.close()
            backup=migrate(path,"test-password");self.assertTrue(Path(backup).exists());backup_conn=connect(backup);self.assertEqual(backup_conn.execute("PRAGMA user_version").fetchone()[0],9);self.assertEqual(tuple(backup_conn.execute("SELECT board_id,owner_id,scope,view_type,name,filter_json,sort_json,visible_fields_json,column_order_json,is_default,version,created_at,updated_at,deleted_at,presentation_json FROM saved_views WHERE name='Legacy calendar'").fetchone()),before);backup_conn.close();conn=connect(path);self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0],SCHEMA_VERSION);self.assertEqual(tuple(conn.execute("SELECT board_id,owner_id,scope,view_type,name,filter_json,sort_json,visible_fields_json,column_order_json,is_default,version,created_at,updated_at,deleted_at,presentation_json FROM saved_views WHERE name='Legacy calendar'").fetchone()),before);self.assertEqual(conn.execute("SELECT checksum FROM schema_migrations WHERE version=10").fetchone()[0],"flowboard-schema-v10");self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0],"ok");self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(),[]);count=conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0];conn.close();self.assertIsNone(migrate(path,"test-password"));conn=connect(path);self.assertEqual(conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0],count);conn.close()


if __name__ == "__main__":unittest.main()
