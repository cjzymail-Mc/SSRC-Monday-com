import unittest
import test_timeline_http as harness
from flowboard.database import connect

class TeamCardsHTTP(unittest.TestCase):
    setUp=harness.TimelineHTTPTests.setUp
    tearDown=harness.TimelineHTTPTests.tearDown
    request=harness.TimelineHTTPTests.request
    login=harness.TimelineHTTPTests.login

    def test_bootstrap_roles_match_current_workspace_and_keep_permissions(self):
        self.assertEqual(self.request('GET','/api/bootstrap')[0],401)
        conn=connect(self.db_path)
        conn.execute("INSERT INTO workspaces(id,name,created_at) VALUES (2,'其他工作区','2026-10-09')")
        conn.execute("INSERT INTO workspace_memberships VALUES (2,'u2','admin')")
        conn.commit();conn.close()
        cookie,_=self.login('u2');status,payload,_=self.request('GET','/api/bootstrap',cookie=cookie)
        self.assertEqual(status,200);self.assertEqual(payload['workspace_id'],1)
        self.assertEqual({m['id']:m['role'] for m in payload['members']},{'u1':'admin','u2':'member','u3':'viewer'})
        self.assertFalse(payload['capabilities']['admin'])
        self.assertTrue(all('password_hash' not in m for m in payload['members']))

if __name__=='__main__':unittest.main()
