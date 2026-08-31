import os
import re
import tempfile
import threading
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright

from flowboard.database import connect
from flowboard.service import FlowboardService
from server import create_server
from test_secure_foundation import create_legacy_database


class I12E2E(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="flowboard-i12-e2e-");self.db=str(Path(self.temp.name)/"flowboard.db");create_legacy_database(self.db);os.environ["FLOWBOARD_INITIAL_PASSWORD"]="test-password";os.environ["FLOWBOARD_ATTACHMENT_DIR"]=str(Path(self.temp.name)/"blobs");self.server=create_server("127.0.0.1",0,self.db);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.base=f"http://127.0.0.1:{self.server.server_address[1]}";self.playwright=sync_playwright().start();self.browser=self.playwright.chromium.launch(headless=True)
        conn=connect(self.db);admin=dict(conn.execute("SELECT * FROM users WHERE id='u1'").fetchone());conn.execute("UPDATE boards SET name='Needle board' WHERE id=1");conn.execute("UPDATE tasks SET title='Needle task' WHERE id=1");conn.execute("UPDATE users SET name='Needle member' WHERE id='u2'");conn.commit();conn.close();service=FlowboardService(self.db);service.create_comment(admin,1,{"body":"Needle comment","mentions":[{"type":"user","user_id":"u2"}]});service.create_attachment(admin,1,{"name":"Needle-file.txt","content_type":"text/plain","content_base64":"eA=="})
    def tearDown(self):
        self.browser.close();self.playwright.stop();self.server.shutdown();self.server.server_close();self.thread.join(timeout=2);self.temp.cleanup();os.environ.pop("FLOWBOARD_INITIAL_PASSWORD",None);os.environ.pop("FLOWBOARD_ATTACHMENT_DIR",None)
    def login(self,user,width=1280):
        context=self.browser.new_context(viewport={"width":width,"height":844});page=context.new_page();page.goto(self.base);page.locator("#loginUser").fill(user);page.locator("#loginPassword").fill("test-password");page.locator("#loginForm button").click();page.locator(".task-row").first.wait_for();return context,page
    def test_two_context_realtime_fallback_notifications_search_audit_and_mobile(self):
        admin_context,admin=self.login("u1");member_context,member=self.login("u2")
        admin.wait_for_function("document.querySelector('#realtimeState').textContent.includes('实时')");member.wait_for_function("document.querySelector('#realtimeState').textContent.includes('实时')")
        before=member.evaluate("api('/api/tasks/1').then(x=>x.version)");admin.evaluate("api('/api/tasks/1').then(t=>api('/api/tasks/1','PATCH',{version:t.version,title:'Realtime Needle'}))");member.locator(".task-row",has_text="Realtime Needle").wait_for(timeout=10000)
        conflict=member.evaluate(f"api('/api/tasks/1','PATCH',{{version:{before},title:'stale pollution'}}).then(()=>200,e=>e.status)");self.assertEqual(conflict,409);self.assertNotIn("stale pollution",admin.evaluate("api('/api/tasks/1').then(x=>x.title)"))
        member.locator("#notificationBtn").click();task_notices=member.locator('#listModal.open .notification-item[data-task="1"]');mention=task_notices.filter(has=member.locator("span").filter(has_text=re.compile(r"^mention\.added · ")));changed=task_notices.filter(has=member.locator("span").filter(has_text=re.compile(r"^task\.changed · ")));mention.first.wait_for();changed.first.wait_for();self.assertEqual(mention.count(),1);self.assertGreaterEqual(changed.count(),1);self.assertIn("Realtime Needle",mention.first.text_content());self.assertIn("Realtime Needle",changed.first.text_content());member.locator("#readAllNotifications").click();member.wait_for_function("document.querySelector('#notificationCount').textContent === ''")
        admin.once("dialog",lambda dialog:dialog.accept("Needle"));admin.locator("#globalSearchBtn").click();admin.locator("#listModal.open").wait_for();self.assertEqual({admin.locator(".search-result b").nth(i).text_content().lower() for i in range(admin.locator(".search-result b").count())},{"board","task","comment","attachment","member"});admin.locator("#listModal [data-close]").click()
        admin.locator("#auditBtn").click();admin.locator("#listModal.open",has_text="task.field_values.updated").wait_for();self.assertTrue(admin.locator("a[href$='audit.csv']").is_visible());self.assertFalse(member.locator("#auditBtn").is_visible())
        member_context.route("**/events/stream*",lambda route:route.abort());member.reload();member.locator(".task-row").first.wait_for();member.wait_for_function("document.querySelector('#realtimeState').textContent.includes('轮询降级')",timeout=10000);admin.evaluate("api('/api/tasks/1').then(t=>api('/api/tasks/1','PATCH',{version:t.version,title:'Fallback Needle'}))");member.locator(".task-row",has_text="Fallback Needle").wait_for(timeout=12000)
        member_context.unroute("**/events/stream*");member.reload();member.locator(".task-row").first.wait_for();member.wait_for_function("document.querySelector('#realtimeState').textContent.includes('实时')",timeout=10000)
        mobile_context,mobile=self.login("u1",390);self.assertTrue(mobile.locator("#notificationBtn").is_visible());self.assertEqual(mobile.evaluate("document.documentElement.scrollWidth <= innerWidth"),True);mobile.locator("#notificationBtn").click();modal=mobile.locator("#listModal.open .task-modal");modal.wait_for();box=modal.bounding_box();self.assertIsNotNone(box);self.assertLessEqual(box["width"],390)
        admin_context.close();member_context.close();mobile_context.close()

    def test_audit_displays_beijing_time_without_rewriting_canonical_timestamp(self):
        conn=connect(self.db);conn.execute("INSERT INTO audit_log(source_key,workspace_id,actor_user_id,action_code,outcome,entity_type,entity_id,details_json,created_at) VALUES ('timezone-fixture',1,'u1','time.zone.fixture','success','task','1','{}','2026-08-31T02:30:00+00:00')");conn.commit();conn.close()
        context=self.browser.new_context(viewport={"width":1280,"height":844});page=context.new_page();page.goto(self.base);page.locator("#loginUser").fill("u1");page.locator("#loginPassword").fill("test-password");page.locator("#loginForm button").click();page.locator("#timelineView").wait_for(state="visible")
        page.evaluate("showAudit()")
        audit_fixture=page.locator("#listModal.open .audit-item",has_text="time.zone.fixture");audit_fixture.wait_for()
        self.assertEqual(audit_fixture.locator("small").inner_text(),"2026-08-31 10:30:00")
        raw=page.evaluate("api('/api/admin/workspaces/1/audit?limit=100').then(result => result.items.find(item => item.action_code === 'time.zone.fixture').created_at)")
        self.assertEqual(raw,"2026-08-31T02:30:00+00:00")
        context.close()


if __name__=="__main__":unittest.main()
