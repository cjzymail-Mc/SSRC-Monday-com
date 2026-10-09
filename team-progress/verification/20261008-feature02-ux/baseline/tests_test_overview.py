import json
import unittest
from datetime import date
from unittest.mock import patch

import test_timeline_http as http_harness
from overview_fixtures import seed_overview
from flowboard.database import connect
from flowboard.overview import project_overview
from flowboard.service import ApiError
from flowboard.timeline import TimelineService


class OverviewTests(unittest.TestCase):
    setUp = http_harness.TimelineHTTPTests.setUp
    tearDown = http_harness.TimelineHTTPTests.tearDown
    request = http_harness.TimelineHTTPTests.request
    login = http_harness.TimelineHTTPTests.login

    def seed(self):
        self.today=date(2026,10,8)
        self.ids=seed_overview(self.db_path,self.today)
        self.service=TimelineService(self.db_path)

    def overview(self, **filters):
        with patch.object(TimelineService,'_server_today',return_value=self.today):
            return project_overview(self.service,{'id':'u1'},1,{k:[v] for k,v in filters.items()})

    def test_filtered_counts_next_ties_and_current_stage_are_distinct(self):
        self.seed()
        result=self.overview()
        risk=next(p for p in result['projects'] if p['project_id']==self.ids['risk'])
        self.assertEqual(result['server_today'],'2026-10-08')
        self.assertEqual((result['range_start'],result['range_end']),('2026-10-05','2026-10-11'))
        self.assertEqual((risk['overdue_count'],risk['today_count'],risk['node_count'],risk['done_count']),(1,2,3,0))
        self.assertEqual(risk['next_nodes'][0]['name'],'鞋面材料确认')
        self.assertEqual(risk['current_stage'],'测试')
        self.assertEqual(len({p['project_id'] for p in result['projects']}),result['counts']['projects'])
        self.assertEqual(result['counts']['nodes'],sum(len(p['matched_nodes']) for p in result['projects']))
        conn=connect(self.db_path)
        conn.execute('UPDATE timeline_nodes SET done_at=? WHERE id=?',('2026-10-08',self.ids['overdue_node']))
        conn.commit();conn.close()
        risk=next(p for p in self.overview()['projects'] if p['project_id']==self.ids['risk'])
        self.assertEqual([n['track'] for n in risk['next_nodes']],['main','parallel'])
        self.assertEqual({n['date'] for n in risk['next_nodes']},{'2026-10-08'})

    def test_search_stage_track_completion_and_empty_project_semantics(self):
        self.seed()
        result=self.overview(completion='all')
        done=next(p for p in result['projects'] if p['project_id']==self.ids['done'])
        self.assertEqual((done['progress'],done['next_nodes']),(100,[]))
        self.assertNotIn(self.ids['empty'],[p['project_id'] for p in result['projects']])
        result=self.overview(q='耐磨',track='parallel',stage='测试')
        self.assertEqual(result['counts']['nodes'],1)
        self.assertEqual(result['projects'][0]['matched_nodes'][0]['name'],'鞋底耐磨测试')
        empty=self.overview(period='all',q='待录入')['projects'][0]
        self.assertEqual((empty['progress'],empty['next_nodes'],empty['current_stage']),(None,[],'未录入节点'))
        self.assertEqual(self.overview(q='不存在的项目')['counts']['projects'],0)
        self.assertEqual(self.overview(period='all',scope='mine',track='parallel')['counts']['nodes'],1)
        risk=next(p for p in self.overview(completion='all')['projects'] if p['project_id']==self.ids['risk'])
        self.assertEqual((risk['progress'],risk['done_count'],risk['node_count']),(25,1,4))

    def test_batch_sql_zero_writes_and_archive_deleted_workspace_isolation(self):
        self.seed()
        conn=connect(self.db_path)
        conn.execute("INSERT INTO workspaces(id,name,created_at) VALUES (2,'第二空间','2026-10-08')")
        conn.execute("INSERT INTO timeline_projects(workspace_id,name,created_by,created_at,updated_at) VALUES (2,'跨空间机密','u1','2026-10-08','2026-10-08')")
        conn.commit();conn.close()
        conn=connect(self.db_path);statements=[]
        conn.set_trace_callback(statements.append)
        with patch.object(self.service,'_db',return_value=conn):
            payload=self.overview(period='all',completion='all')
        raw=json.dumps(payload,ensure_ascii=False)
        for secret in ['归档项目机密','删除项目机密','删除节点机密','跨空间机密']:
            self.assertNotIn(secret,raw)
        self.assertEqual(sum(s.lstrip().upper().startswith('SELECT') for s in statements),3)
        self.assertFalse(any(s.lstrip().split()[0].upper() in ('INSERT','UPDATE','DELETE','ALTER','CREATE') for s in statements))
        with self.assertRaises(ApiError) as caught:
            project_overview(self.service,{'id':'u1'},2,{})
        self.assertEqual(caught.exception.status,403)

    def test_http_acl_my_scope_validation_and_static_allowlist(self):
        self.seed()
        path='/api/workspaces/1/timeline/overview'
        self.assertEqual(self.request('GET',path)[0],401)
        admin,_=self.login();member,csrf=self.login('u2');viewer,_=self.login('u3')
        self.assertEqual(self.request('GET',path,cookie=viewer)[0],403)
        self.assertEqual(self.request('GET',path.replace('/1/','/999/'),cookie=admin)[0],403)
        status,payload,_=self.request('GET',path+'?scope=mine&period=all',cookie=member)
        self.assertEqual(status,200)
        self.assertEqual({p['created_by'] for p in payload['projects']},{'u2'})
        status,payload,_=self.request('GET',path+'?period=all',cookie=member)
        other=next(p for p in payload['projects'] if p['created_by']=='u1')
        self.assertFalse(other['can_edit'])
        self.assertEqual(self.request('POST','/api/workspaces/1/timeline/batches',{'requests':[{'project_id':other['project_id'],'base_version':1,'changes':[{'node_id':other['matched_nodes'][0]['id'],'set':{'remark':'不得写入'}}]}]},cookie=member,csrf=csrf)[0],403)
        for query in ['period=invalid','period=','track=bad','scope=admin','period=all&period=week','unknown=1','unknown=','q='+'a'*101]:
            self.assertEqual(self.request('GET',path+'?'+query,cookie=admin)[0],422,query)
        import http.client
        for resource in ['/overview.css','/overview-ui.js']:
            connection=http.client.HTTPConnection('127.0.0.1',self.port)
            connection.request('GET',resource);response=connection.getresponse();response.read()
            self.assertEqual(response.status,200);connection.close()
        self.assertEqual(self.request('GET','/flowboard/overview.py',cookie=admin)[0],404)

    def test_temporal_month_week_and_next30_boundaries(self):
        self.seed()
        for today,start,end in [(date(2026,10,4),'2026-09-28','2026-10-04'),(date(2026,10,5),'2026-10-05','2026-10-11')]:
            self.today=today;result=self.overview()
            self.assertEqual((result['range_start'],result['range_end']),(start,end))
        self.today=date(2028,2,29)
        self.assertEqual(self.overview(period='month')['range_end'],'2028-02-29')
        self.assertEqual(self.overview(period='next30')['range_end'],'2028-03-29')


if __name__=='__main__':unittest.main()
