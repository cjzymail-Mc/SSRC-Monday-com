import os
import tempfile
import threading
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright

from legacy_board_e2e import reload_legacy_board, reveal_legacy_board
from server import create_server
from test_secure_foundation import create_legacy_database


class CollaborationE2E(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="flowboard-collab-e2e-");self.db_path=str(Path(self.temp.name)/"flowboard.db");create_legacy_database(self.db_path)
        os.environ["FLOWBOARD_INITIAL_PASSWORD"]="test-password";os.environ["FLOWBOARD_ATTACHMENT_DIR"]=str(Path(self.temp.name)/"private-blobs");self.server=create_server("127.0.0.1",0,self.db_path);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.base=f"http://127.0.0.1:{self.server.server_address[1]}";self.playwright=sync_playwright().start();self.browser=self.playwright.chromium.launch(headless=True)

    def tearDown(self):
        self.browser.close();self.playwright.stop();self.server.shutdown();self.server.server_close();self.thread.join(timeout=2);self.temp.cleanup();os.environ.pop("FLOWBOARD_INITIAL_PASSWORD",None);os.environ.pop("FLOWBOARD_ATTACHMENT_DIR",None)

    def login(self,user,viewport):
        context=self.browser.new_context(viewport=viewport);page=context.new_page();page.goto(self.base);page.locator("#loginUser").fill(user);page.locator("#loginPassword").fill("test-password");page.locator("#loginForm button[type=submit]").click();reveal_legacy_board(page);return context,page

    @staticmethod
    def open_first(page):
        page.locator(".task-row").first.click();page.locator("#taskModal.open #commentInput").wait_for()

    def test_two_users_desktop_and_mobile_collaboration_journey(self):
        admin_context,admin=self.login("u1",{"width":1280,"height":800});self.open_first(admin);admin.locator("#commentInput").fill("E2E mention");admin.locator("#mentionInput").select_option("u2");admin.locator("#commentBtn").click();admin.locator("#taskModal.open",has_text="E2E mention").wait_for()
        stale_context,stale=self.login("u1",{"width":1100,"height":700});self.open_first(stale)
        admin.once("dialog",lambda dialog:dialog.accept("E2E edited"));admin.locator("[data-comment-edit]").first.click();admin.locator("#taskModal.open",has_text="E2E edited").wait_for();detail=admin.request.get(self.base+"/api/tasks/1").json();root=next(row for row in detail["comments"] if row["body"]=="E2E edited");self.assertEqual(root["version"],2);self.assertEqual([(row["mention_type"],row["user_id"]) for row in root["mentions"]],[("user","u2")])
        conflict=stale.evaluate(f"fetch('/api/comments/{root['id']}',{{method:'PATCH',headers:{{'Content-Type':'application/json','X-CSRF-Token':csrfToken}},body:JSON.stringify({{version:1,body:'stale pollution',mentions:[]}})}}).then(async r=>[r.status,await r.text()])");self.assertEqual(conflict[0],409,conflict[1])
        admin.locator("#attachmentInput").set_input_files({"name":"preview.txt","mimeType":"text/plain","buffer":b"mobile-safe-preview"});admin.locator("#attachmentBtn").click();admin.locator("#taskModal.open a",has_text="预览").wait_for();preview=admin.locator("#taskModal a",has_text="预览").get_attribute("href");response=admin.request.get(self.base+preview);self.assertEqual((response.status,response.text()),(200,"mobile-safe-preview"));self.assertIn("sandbox",response.headers["content-security-policy"])
        member_context,member=self.login("u2",{"width":1280,"height":800});self.open_first(member);self.assertTrue(member.locator("#taskModal",has_text="E2E edited").is_visible());self.assertEqual(member.locator("#subscriptionBtn").text_content(),"取消订阅")
        member.once("dialog",lambda dialog:dialog.accept("E2E reply"));member.locator("[data-comment-reply]").first.click();member.locator("#taskModal",has_text="E2E reply").wait_for()
        member.locator("#commentInput").fill("member comment");member.locator("#commentBtn").click();member.locator("#taskModal",has_text="member comment").wait_for()
        admin.once("dialog",lambda dialog:dialog.accept());admin.locator(f'[data-comment-delete="{root["id"]}"]').click();admin.locator("#taskModal.open",has_text="评论已删除").wait_for();self.assertTrue(admin.locator("#taskModal",has_text="E2E reply").is_visible());db=__import__("sqlite3").connect(self.db_path);before_stale_delete=tuple(db.execute("SELECT (SELECT COUNT(*) FROM comment_versions WHERE comment_id=?),(SELECT COUNT(*) FROM activity),(SELECT COUNT(*) FROM collaboration_events)",(root["id"],)).fetchone());db.close();stale_delete=stale.evaluate(f"fetch('/api/comments/{root['id']}',{{method:'DELETE',headers:{{'Content-Type':'application/json','X-CSRF-Token':csrfToken}},body:JSON.stringify({{version:2}})}}).then(r=>r.status)");self.assertEqual(stale_delete,409);detail=admin.request.get(self.base+"/api/tasks/1").json();deleted=next(row for row in detail["comments"] if row["id"]==root["id"]);self.assertIsNone(deleted["body"]);self.assertEqual(deleted["version"],3);self.assertFalse(any(row.get("body")=="stale pollution" for row in detail["comments"]));db=__import__("sqlite3").connect(self.db_path);self.assertEqual(tuple(db.execute("SELECT (SELECT COUNT(*) FROM comment_versions WHERE comment_id=?),(SELECT COUNT(*) FROM activity),(SELECT COUNT(*) FROM collaboration_events)",(root["id"],)).fetchone()),before_stale_delete);self.assertGreaterEqual(db.execute("SELECT COUNT(*) FROM collaboration_events WHERE comment_id=?",(root["id"],)).fetchone()[0],4);db.close()
        db=__import__("sqlite3").connect(self.db_path);db.execute("UPDATE workspace_memberships SET role='viewer' WHERE workspace_id=1 AND user_id='u2'");db.commit();db.close();reload_legacy_board(member);member.locator(".task-row").first.click();member.locator("#taskModal.open .task-modal").wait_for();self.assertEqual(member.locator("#taskModal .modal-comment").is_visible(),False);controls=member.locator("[data-comment-edit],[data-comment-delete],[data-comment-reply],[data-attachment-delete]");self.assertFalse(any(controls.nth(i).is_visible() for i in range(controls.count())));self.assertEqual(member.evaluate("fetch('/api/tasks/1/subscription',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrfToken},body:JSON.stringify({subscribed:true})}).then(r=>r.status)"),403)
        mobile_context,mobile=self.login("u1",{"width":390,"height":844});self.open_first(mobile);self.assertLessEqual(mobile.locator("#taskModal .task-modal").bounding_box()["width"],390);self.assertEqual(mobile.evaluate("document.documentElement.scrollWidth <= innerWidth"),True);self.assertTrue(mobile.evaluate("document.querySelector('#taskModal .task-modal').scrollHeight > document.querySelector('#taskModal .task-modal').clientHeight"));mobile.locator("#subscriptionBtn").click();mobile.wait_for_function("document.querySelector('#taskModal.open #subscriptionBtn')?.textContent === '订阅'");mobile.locator("#subscriptionBtn").click();mobile.wait_for_function("document.querySelector('#taskModal.open #subscriptionBtn')?.textContent === '取消订阅'");mobile.once("dialog",lambda dialog:dialog.accept("mobile reply"));mobile.locator("[data-comment-reply]").first.click();mobile.locator("#taskModal.open",has_text="mobile reply").wait_for();mobile.locator("#attachmentInput").set_input_files({"name":"mobile.txt","mimeType":"text/plain","buffer":b"mobile"});mobile.locator("#attachmentBtn").click();mobile.locator("#taskModal.open",has_text="mobile.txt").wait_for();mobile.once("dialog",lambda dialog:dialog.accept());mobile.locator('[data-attachment-delete]').last.click();mobile.locator("#taskModal.open",has_text="mobile.txt").wait_for(state="hidden")
        db=__import__("sqlite3").connect(self.db_path);db.execute("UPDATE boards SET access_type='private' WHERE id=1");db.commit();db.close();self.assertEqual(member.evaluate("fetch('/api/tasks/1').then(r=>r.status)"),403)
        admin_context.close();stale_context.close();member_context.close();mobile_context.close()


if __name__=="__main__":unittest.main()
