import http.client,json,os,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch

from flowboard.aggregation import AggregationError,aggregate,aggregate_value
from flowboard.database import (SCHEMA_VERSION,_migration_v1,_migration_v2,_migration_v3,_migration_v4,_migration_v5,_migration_v6,_migration_v7,_migration_v8,_migration_v9,_migration_v10,connect,migrate)
from flowboard.service import ApiError,FlowboardService
from server import create_server
from test_secure_foundation import create_legacy_database


class AggregationTests(unittest.TestCase):
    def setUp(self):
        self.catalog={("core","status"):"status",("core","due"):"date",("core","board"):"board",("dynamic",7):"number",("dynamic",8):"tags"}
        self.rows=[{"status":"待开始","due":"2026-08-01","board_name":"Main","field_values":{"7":2,"8":[1,2]}},{"status":"已完成","due":"2026-08-08","board_name":"Main","field_values":{"7":4,"8":[2]}}]
    def spec(self,**changes):return {"version":1,"chart_type":"bar","dimension":{"kind":"core","key":"status"},"metric":{"op":"count"},"date_bucket":"none","top_n":20,"null_policy":"include",**changes}
    def test_count_numeric_date_tags_and_empty(self):
        result=aggregate(self.rows,self.spec(),[self.catalog]);self.assertEqual(result["categories"],["已完成","待开始"]);self.assertEqual(result["series"][0]["values"],[1,1])
        for op,expected in (("sum",6),("avg",3),("min",2),("max",4)):
            result=aggregate(self.rows,self.spec(dimension={"kind":"core","key":"board"},metric={"op":op,"field":{"kind":"dynamic","id":7}}),[self.catalog]);self.assertEqual(sum(result["series"][0]["values"]),expected)
        result=aggregate(self.rows,self.spec(chart_type="line",dimension={"kind":"core","key":"due"},date_bucket="week"),[self.catalog]);self.assertEqual(result["categories"],["2026-W31","2026-W32"])
        result=aggregate(self.rows,self.spec(dimension={"kind":"dynamic","id":8}),[self.catalog]);self.assertEqual(sum(result["series"][0]["values"]),3);self.assertEqual(result["meta"]["multi_value_rule"],"each_value_membership")
        self.assertTrue(aggregate([],self.spec(),[self.catalog])["empty"])
    def test_invalid_combinations_fail_closed(self):
        for spec in (self.spec(chart_type="pie",series={"kind":"core","key":"status"}),self.spec(chart_type="line"),self.spec(metric={"op":"sum","field":{"kind":"core","key":"status"}})):
            with self.assertRaises(AggregationError):aggregate(self.rows,spec,[self.catalog])
    def test_cross_board_dynamic_fields_require_explicit_source_mapping(self):
        rows=[{"source_key":"a","field_values":{"7":2}},{"source_key":"b","field_values":{"9":4}}];a={("dynamic",7):"number","__source_key__":"a"};b={("dynamic",9):"number","__source_key__":"b"};mapped={"kind":"mapped","by_source":{"a":{"kind":"dynamic","id":7},"b":{"kind":"dynamic","id":9}}};spec=self.spec(dimension={"kind":"core","key":"board"},metric={"op":"sum","field":mapped});rows[0]["board_name"]=rows[1]["board_name"]="all";a[("core","board")]=b[("core","board")]="board";self.assertEqual(aggregate(rows,spec,[a,b])["series"][0]["values"],[6])
        with self.assertRaises(AggregationError):aggregate(rows,self.spec(dimension={"kind":"core","key":"board"},metric={"op":"sum","field":{"kind":"dynamic","id":7}}),[a,b])
    def test_global_kpi_numeric_ops_empty_and_cross_source_mapping(self):
        rows=[{"source_key":"a","field_values":{"7":1}},{"source_key":"a","field_values":{"7":3}},{"source_key":"b","field_values":{"9":10}},{"source_key":"b","field_values":{"9":None}}];a={("core","board"):"board",("dynamic",7):"number","__source_key__":"a"};b={("core","board"):"board",("dynamic",9):"number","__source_key__":"b"};mapped={"kind":"mapped","by_source":{"a":{"kind":"dynamic","id":7},"b":{"kind":"dynamic","id":9}}}
        for op,expected in (("count",4),("sum",14),("avg",14/3),("min",1),("max",10)):
            metric={"op":op} if op=="count" else {"op":op,"field":mapped};result=aggregate_value(rows,self.spec(dimension={"kind":"core","key":"board"},metric=metric),[a,b]);self.assertAlmostEqual(result["value"],expected);self.assertEqual(result["meta"]["value_count"],4 if op=="count" else 3)
        empty=aggregate_value([{"source_key":"a","field_values":{"7":None}}],self.spec(dimension={"kind":"core","key":"board"},metric={"op":"avg","field":{"kind":"dynamic","id":7}}),[a]);self.assertTrue(empty["empty"]);self.assertIsNone(empty["value"])
    def test_high_cardinality_series_and_cells_fail_during_accumulation(self):
        catalog={**self.catalog,("dynamic",9):"tags"};spec=self.spec(series={"kind":"dynamic","id":9})
        with self.assertRaises(AggregationError) as caught:aggregate([{"status":"x","field_values":{"9":list(range(13))}}],spec,[catalog])
        self.assertEqual(caught.exception.code,"AGGREGATION_RESULT_LIMIT")
        rows=[{"status":f"d{i}","field_values":{"9":list(range(12))}} for i in range(167)]
        with self.assertRaises(AggregationError) as caught:aggregate(rows,spec,[catalog])
        self.assertEqual(caught.exception.code,"AGGREGATION_RESULT_LIMIT")


class DashboardHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.db=str(Path(self.temp.name)/"flowboard.db");create_legacy_database(self.db);os.environ["FLOWBOARD_INITIAL_PASSWORD"]="test-password";self.server=create_server("127.0.0.1",0,self.db);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.port=self.server.server_address[1]
    def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join(timeout=2);self.temp.cleanup()
    def request(self,method,path,body=None,cookie=None,csrf=None):
        conn=http.client.HTTPConnection("127.0.0.1",self.port);headers={"Content-Type":"application/json"}
        if cookie:headers["Cookie"]=cookie
        if csrf:headers["X-CSRF-Token"]=csrf
        conn.request(method,path,json.dumps(body).encode() if body is not None else None,headers);response=conn.getresponse();raw=response.read();reply=dict(response.getheaders());conn.close();return response.status,json.loads(raw or b"{}"),reply
    def login(self,user="u1"):
        status,payload,headers=self.request("POST","/api/auth/login",{"username":user,"password":"test-password"});self.assertEqual(status,200,payload);return headers["Set-Cookie"].split(";",1)[0],payload["csrf_token"]
    def test_board_chart_and_dashboard_five_widgets_acl_versions(self):
        cookie,csrf=self.login();status,boot,_=self.request("GET","/api/bootstrap?board_id=1",cookie=cookie);status_field=next(field for field in boot["fields"] if field.get("system_key")=="status");done_option=next(option["id"] for option in status_field["options"] if option["label"]=="已完成");query={"version":1,"filter":{"op":"and","children":[]},"sort":[]};spec={"version":1,"chart_type":"bar","dimension":{"kind":"core","key":"status"},"metric":{"op":"count"},"date_bucket":"none","top_n":20,"null_policy":"include"}
        status,result,_=self.request("POST","/api/boards/1/aggregate",{"query":query,"spec":spec},cookie,csrf);self.assertEqual(status,200,result);self.assertEqual(sum(result["series"][0]["values"]),result["meta"]["task_count"])
        status,dashboard,_=self.request("POST","/api/workspaces/1/dashboards",{"name":"I10 dashboard","scope":"shared","global_filters":{"version":1,"by_source":{}}},cookie,csrf);self.assertEqual(status,201,dashboard);did=dashboard["id"];dv=dashboard["version"]
        status,source,_=self.request("POST",f"/api/dashboards/{did}/sources",{"dashboard_version":dv,"source_key":"main","board_id":1,"query":query},cookie,csrf);self.assertEqual(status,201,source);dv=source["dashboard_version"]
        configs={"number":{"version":1,"source_keys":["main"],"spec":{**spec,"dimension":{"kind":"core","key":"board"}}},"chart":{"version":1,"source_keys":["main"],"spec":spec},"progress":{"version":1,"source_keys":["main"],"complete_values":["已完成"]},"calendar":{"version":1,"source_keys":["main"],"date_field":{"kind":"core","key":"due"},"limit":50},"table":{"version":1,"source_keys":["main"],"columns":["title","status"],"limit":50}}
        widgets=[]
        for index,(kind,config) in enumerate(configs.items()):
            status,widget,_=self.request("POST",f"/api/dashboards/{did}/widgets",{"dashboard_version":dv,"widget_type":kind,"title":kind,"config":config,"x":0,"y":index*2,"width":4,"height":2},cookie,csrf);self.assertEqual(status,201,widget);dv=widget["dashboard_version"];widgets.append((kind,widget))
        for kind,widget in widgets:
            status,payload,_=self.request("POST",f"/api/dashboards/{did}/widgets/{widget['id']}/data",{},cookie,csrf);self.assertEqual(status,200,payload);self.assertEqual(payload["type"],kind)
        status,updated,_=self.request("PATCH",f"/api/dashboards/{did}",{"version":dv,"global_filters":{"version":1,"by_source":{"main":{"field":{"kind":"dynamic","id":status_field["id"]},"operator":"equals","value":done_option}}}},cookie,csrf);self.assertEqual(status,200,updated);dv=updated["version"];status,filtered,_=self.request("POST",f"/api/dashboards/{did}/widgets/{widgets[0][1]['id']}/data",{},cookie,csrf);self.assertEqual(status,200,filtered);self.assertGreater(filtered["data"]["value"],0);self.assertLess(filtered["data"]["value"],result["meta"]["task_count"])
        stale=widgets[0][1];status,error,_=self.request("PATCH",f"/api/dashboards/{did}/widgets/{stale['id']}",{"version":stale["version"],"dashboard_version":dv-1,"x":1},cookie,csrf);self.assertEqual((status,error["error"]["code"]),(409,"VERSION_CONFLICT"))
        conn=connect(self.db);conn.execute("UPDATE workspace_memberships SET role='viewer' WHERE user_id='u2'");conn.commit();conn.close();viewer,viewer_csrf=self.login("u2");status,listing,_=self.request("GET","/api/workspaces/1/dashboards",cookie=viewer);self.assertIn(did,[item["id"] for item in listing["dashboards"]]);status,error,_=self.request("PATCH",f"/api/dashboards/{did}",{"version":dv,"name":"forbidden"},viewer,viewer_csrf);self.assertEqual(status,403,error)
    def test_private_source_revocation_is_generic(self):
        cookie,csrf=self.login();status,board,_=self.request("POST","/api/workspaces/1/boards",{"name":"Private source","access_type":"private","color":"blue"},cookie,csrf);self.assertEqual(status,201,board);bid=board["id"];status,dashboard,_=self.request("POST","/api/workspaces/1/dashboards",{"name":"Shared private","scope":"shared"},cookie,csrf);did=dashboard["id"];status,source,_=self.request("POST",f"/api/dashboards/{did}/sources",{"dashboard_version":1,"source_key":"private","board_id":bid,"query":{"version":1,"filter":{"op":"and","children":[]},"sort":[]}},cookie,csrf);status,widget,_=self.request("POST",f"/api/dashboards/{did}/widgets",{"dashboard_version":2,"widget_type":"number","title":"Secret","config":{"version":1,"source_keys":["private"],"spec":{"version":1,"chart_type":"bar","dimension":{"kind":"core","key":"board"},"metric":{"op":"count"},"date_bucket":"none","top_n":20,"null_policy":"include"}},"x":0,"y":0,"width":3,"height":2},cookie,csrf);self.assertEqual(status,201,widget)
        conn=connect(self.db);conn.execute("UPDATE workspace_memberships SET role='viewer' WHERE user_id='u2'");conn.commit();conn.close();viewer,viewer_csrf=self.login("u2");status,error,_=self.request("POST",f"/api/dashboards/{did}/widgets/{widget['id']}/data",{},viewer,viewer_csrf);self.assertEqual((status,error["error"]["code"]),(403,"WIDGET_SOURCE_UNAVAILABLE"));self.assertNotIn("Private source",json.dumps(error,ensure_ascii=False))
    def test_aggregation_limit_rejects_before_projection(self):
        cookie,csrf=self.login();conn=connect(self.db);group=conn.execute("SELECT id FROM groups_ WHERE board_id=1 LIMIT 1").fetchone()[0];existing=conn.execute("SELECT COUNT(*) FROM tasks t JOIN groups_ g ON g.id=t.group_id WHERE g.board_id=1").fetchone()[0]
        for index in range(2001-existing):conn.execute("INSERT INTO tasks(group_id,title,due,created_at,updated_at) VALUES (?,?,?,datetime('now'),datetime('now'))",(group,f"agg-{index}","未设置"))
        conn.commit();conn.close();spec={"version":1,"chart_type":"bar","dimension":{"kind":"core","key":"status"},"metric":{"op":"count"},"date_bucket":"none","top_n":20,"null_policy":"include"}
        with patch("flowboard.service.aggregate_rows") as projection:
            status,error,_=self.request("POST","/api/boards/1/aggregate",{"query":{"version":1,"filter":{"op":"and","children":[]},"sort":[]},"spec":spec},cookie,csrf);self.assertEqual((status,error["error"]["code"]),(422,"AGGREGATION_TASK_LIMIT"));projection.assert_not_called()
    def test_pagination_source_change_terminates_after_one_followup(self):
        service=FlowboardService(self.db);user={"id":"u1"};first={"total":201,"tasks":[{"owner_id":None,"field_values":{}} for _ in range(200)]};empty={"total":201,"tasks":[]}
        with patch.object(service,"query_tasks",side_effect=[first,empty]) as query:
            with self.assertRaises(ApiError) as caught:service._aggregation_inputs(user,[{"source_key":"main","board_id":1,"query":{"version":1,"filter":{"op":"and","children":[]},"sort":[]}}])
        self.assertEqual(caught.exception.code,"AGGREGATION_SOURCE_CHANGED");self.assertEqual(query.call_count,2)
        changed={"total":202,"tasks":[{"owner_id":None,"field_values":{}}]}
        with patch.object(service,"query_tasks",side_effect=[first,changed]) as query:
            with self.assertRaises(ApiError) as caught:service._aggregation_inputs(user,[{"source_key":"main","board_id":1,"query":{"version":1,"filter":{"op":"and","children":[]},"sort":[]}}])
        self.assertEqual(caught.exception.code,"AGGREGATION_SOURCE_CHANGED");self.assertEqual(query.call_count,2)
    def test_dashboard_source_widget_copy_soft_delete_restore_and_csrf(self):
        cookie,csrf=self.login();query={"version":1,"filter":{"op":"and","children":[]},"sort":[]};status,d,_=self.request("POST","/api/workspaces/1/dashboards",{"name":"Lifecycle","scope":"personal"},cookie,csrf);did=d["id"];status,source,_=self.request("POST",f"/api/dashboards/{did}/sources",{"dashboard_version":1,"source_key":"main","board_id":1,"query":query},cookie,csrf);dv=source["dashboard_version"]
        config={"version":1,"source_keys":["main"],"spec":{"version":1,"chart_type":"bar","dimension":{"kind":"core","key":"board"},"metric":{"op":"count"},"date_bucket":"none","top_n":20,"null_policy":"include"}};status,widget,_=self.request("POST",f"/api/dashboards/{did}/widgets",{"dashboard_version":dv,"widget_type":"number","title":"N","config":config,"x":0,"y":0,"width":3,"height":2},cookie,csrf);dv=widget["dashboard_version"]
        status,copy_widget,_=self.request("POST",f"/api/dashboards/{did}/widgets/{widget['id']}/copy",{"version":widget["version"],"dashboard_version":dv},cookie,csrf);self.assertEqual(status,201,copy_widget);dv=copy_widget["dashboard_version"];status,deleted,_=self.request("DELETE",f"/api/dashboards/{did}/widgets/{copy_widget['id']}",{"version":1,"dashboard_version":dv},cookie,csrf);self.assertEqual(status,200,deleted);dv=deleted["dashboard_version"];status,restored,_=self.request("POST",f"/api/dashboards/{did}/widgets/{copy_widget['id']}/restore",{"version":deleted["version"],"dashboard_version":dv},cookie,csrf);self.assertEqual(status,200,restored);dv=restored["dashboard_version"]
        status,deleted_source,_=self.request("DELETE",f"/api/dashboards/{did}/sources/{source['id']}",{"version":1,"dashboard_version":dv},cookie,csrf);self.assertEqual(status,200,deleted_source);dv=deleted_source["dashboard_version"];status,restored_source,_=self.request("POST",f"/api/dashboards/{did}/sources/{source['id']}/restore",{"version":deleted_source["version"],"dashboard_version":dv},cookie,csrf);self.assertEqual(status,200,restored_source);dv=restored_source["dashboard_version"]
        status,copy,_=self.request("POST",f"/api/dashboards/{did}/copy",{},cookie,csrf);self.assertEqual(status,201,copy);status,deleted_dashboard,_=self.request("DELETE",f"/api/dashboards/{copy['id']}",{"version":1},cookie,csrf);self.assertEqual(status,200,deleted_dashboard);status,restored_dashboard,_=self.request("POST",f"/api/dashboards/{copy['id']}/restore",{"version":deleted_dashboard["version"]},cookie,csrf);self.assertEqual(status,200,restored_dashboard)
        status,error,_=self.request("PATCH",f"/api/dashboards/{did}",{"version":dv,"name":"no csrf"},cookie);self.assertEqual((status,error["error"]["code"]),(403,"CSRF_INVALID"))
    def test_source_and_widget_limits_cover_add_copy_restore_without_mutation(self):
        cookie,csrf=self.login();query={"version":1,"filter":{"op":"and","children":[]},"sort":[]};status,d,_=self.request("POST","/api/workspaces/1/dashboards",{"name":"Limits","scope":"personal"},cookie,csrf);did=d["id"]
        status,doomed_source,_=self.request("POST",f"/api/dashboards/{did}/sources",{"dashboard_version":1,"source_key":"doomed","board_id":1,"query":query},cookie,csrf);status,deleted_source,_=self.request("DELETE",f"/api/dashboards/{did}/sources/{doomed_source['id']}",{"version":1,"dashboard_version":2},cookie,csrf);dv=deleted_source["dashboard_version"]
        conn=connect(self.db)
        for index in range(7):conn.execute("INSERT INTO dashboard_sources(dashboard_id,source_key,board_id,query_json,sort_order,created_at,updated_at) VALUES (?,?,?,?,?,datetime('now'),datetime('now'))",(did,f"s{index}",1,json.dumps(query),index))
        conn.commit();conn.close();status,last_source,_=self.request("POST",f"/api/dashboards/{did}/sources",{"dashboard_version":dv,"source_key":"s7","board_id":1,"query":query},cookie,csrf);self.assertEqual(status,201,last_source);dv=last_source["dashboard_version"]
        conn=connect(self.db);source_before=tuple(conn.execute("SELECT version,deleted_at FROM dashboard_sources WHERE id=?",(doomed_source["id"],)).fetchone());dashboard_before=conn.execute("SELECT version FROM dashboards WHERE id=?",(did,)).fetchone()[0];conn.close()
        for path,body in ((f"/api/dashboards/{did}/sources",{"dashboard_version":dv,"source_key":"overflow","board_id":1,"query":query}),(f"/api/dashboards/{did}/sources/{doomed_source['id']}/restore",{"version":deleted_source["version"],"dashboard_version":dv})):
            status,error,_=self.request("POST",path,body,cookie,csrf);self.assertEqual((status,error["error"]["code"]),(422,"DASHBOARD_SOURCE_LIMIT"))
        conn=connect(self.db);self.assertEqual(conn.execute("SELECT COUNT(*) FROM dashboard_sources WHERE dashboard_id=? AND deleted_at IS NULL",(did,)).fetchone()[0],8);self.assertEqual(tuple(conn.execute("SELECT version,deleted_at FROM dashboard_sources WHERE id=?",(doomed_source["id"],)).fetchone()),source_before);self.assertEqual(conn.execute("SELECT version FROM dashboards WHERE id=?",(did,)).fetchone()[0],dashboard_before);conn.close()
        config={"version":1,"source_keys":["s0"],"spec":{"version":1,"chart_type":"bar","dimension":{"kind":"core","key":"board"},"metric":{"op":"count"},"date_bucket":"none","top_n":20,"null_policy":"include"}};payload={"dashboard_version":dv,"widget_type":"number","title":"doomed","config":config,"x":0,"y":0,"width":3,"height":2};status,doomed_widget,_=self.request("POST",f"/api/dashboards/{did}/widgets",payload,cookie,csrf);dv=doomed_widget["dashboard_version"];status,deleted_widget,_=self.request("DELETE",f"/api/dashboards/{did}/widgets/{doomed_widget['id']}",{"version":1,"dashboard_version":dv},cookie,csrf);dv=deleted_widget["dashboard_version"]
        conn=connect(self.db)
        for index in range(19):conn.execute("INSERT INTO dashboard_widgets(dashboard_id,widget_type,title,config_json,x,y,width,height,sort_order,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,datetime('now'),datetime('now'))",(did,"number",f"w{index}",json.dumps(config),0,index*2,3,2,index))
        conn.commit();active_widget=conn.execute("SELECT id,version FROM dashboard_widgets WHERE dashboard_id=? AND deleted_at IS NULL ORDER BY id LIMIT 1",(did,)).fetchone();conn.close();payload.update({"dashboard_version":dv,"title":"last"});status,last_widget,_=self.request("POST",f"/api/dashboards/{did}/widgets",payload,cookie,csrf);self.assertEqual(status,201,last_widget);dv=last_widget["dashboard_version"]
        conn=connect(self.db);widget_before=tuple(conn.execute("SELECT version,deleted_at FROM dashboard_widgets WHERE id=?",(doomed_widget["id"],)).fetchone());dashboard_before=conn.execute("SELECT version FROM dashboards WHERE id=?",(did,)).fetchone()[0];conn.close()
        attempts=((f"/api/dashboards/{did}/widgets",{**payload,"dashboard_version":dv,"title":"overflow"}),(f"/api/dashboards/{did}/widgets/{active_widget['id']}/copy",{"version":active_widget["version"],"dashboard_version":dv}),(f"/api/dashboards/{did}/widgets/{doomed_widget['id']}/restore",{"version":deleted_widget["version"],"dashboard_version":dv}))
        for path,body in attempts:
            status,error,_=self.request("POST",path,body,cookie,csrf);self.assertEqual((status,error["error"]["code"]),(422,"DASHBOARD_WIDGET_LIMIT"))
        conn=connect(self.db);self.assertEqual(conn.execute("SELECT COUNT(*) FROM dashboard_widgets WHERE dashboard_id=? AND deleted_at IS NULL",(did,)).fetchone()[0],20);self.assertEqual(tuple(conn.execute("SELECT version,deleted_at FROM dashboard_widgets WHERE id=?",(doomed_widget["id"],)).fetchone()),widget_before);self.assertEqual(conn.execute("SELECT version FROM dashboards WHERE id=?",(did,)).fetchone()[0],dashboard_before);conn.close()


class DashboardMigrationTests(unittest.TestCase):
    def test_v10_to_v11_backup_preserves_views_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as root:
            path=str(Path(root)/"v10.db");create_legacy_database(path);conn=connect(path)
            migrations=(_migration_v1,_migration_v2,_migration_v3,_migration_v4,_migration_v5,_migration_v6,_migration_v7,_migration_v8,_migration_v9,_migration_v10)
            for migration in migrations:migration(conn,"test-password") if migration is _migration_v1 else migration(conn)
            before=conn.execute("SELECT COUNT(*),COALESCE(SUM(version),0) FROM saved_views").fetchone();conn.close();backup=migrate(path,"test-password");self.assertTrue(Path(backup).exists());old=connect(backup);self.assertEqual(old.execute("PRAGMA user_version").fetchone()[0],10);old.close();conn=connect(path);self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0],SCHEMA_VERSION);self.assertEqual(tuple(conn.execute("SELECT COUNT(*),COALESCE(SUM(version),0) FROM saved_views").fetchone()),tuple(before));self.assertEqual(conn.execute("SELECT checksum FROM schema_migrations WHERE version=11").fetchone()[0],"flowboard-schema-v11");self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0],"ok");self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(),[]);conn.close();self.assertIsNone(migrate(path,"test-password"))

if __name__=="__main__":unittest.main()
