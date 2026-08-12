import os
import tempfile
import threading
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright

from server import create_server
from test_secure_foundation import create_legacy_database


class I13E2E(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="flowboard-i13-e2e-");self.db=str(Path(self.temp.name)/"flowboard.db");create_legacy_database(self.db);os.environ["FLOWBOARD_INITIAL_PASSWORD"]="test-password";os.environ["FLOWBOARD_ATTACHMENT_DIR"]=str(Path(self.temp.name)/"blobs");os.environ["FLOWBOARD_BACKUP_DIR"]=str(Path(self.temp.name)/"backups");self.server=create_server("127.0.0.1",0,self.db);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.base=f"http://127.0.0.1:{self.server.server_address[1]}";self.playwright=sync_playwright().start();self.browser=self.playwright.chromium.launch(headless=True)

    def tearDown(self):
        self.browser.close();self.playwright.stop();self.server.shutdown();self.server.server_close();self.thread.join(timeout=2);self.temp.cleanup()
        for key in ("FLOWBOARD_INITIAL_PASSWORD","FLOWBOARD_ATTACHMENT_DIR","FLOWBOARD_BACKUP_DIR"):os.environ.pop(key,None)

    def login(self,width):
        context=self.browser.new_context(viewport={"width":width,"height":844});page=context.new_page();page.goto(self.base);page.locator("#loginUser").fill("u1");page.locator("#loginPassword").fill("test-password");page.locator("#loginForm button").click();page.locator(".task-row").first.wait_for();return context,page

    def test_mobile_atomic_batch_and_admin_backup_surface(self):
        context,page=self.login(390);selectors=page.locator("[data-select-task]");self.assertGreaterEqual(selectors.count(),2);selected_ids=[int(selectors.nth(i).get_attribute("data-select-task")) for i in range(2)];selectors.nth(0).click();page.locator("[data-select-task]").nth(1).click();page.locator("#batchBar:not([hidden])").wait_for();self.assertIn("已选 2 项",page.locator("#batchCount").text_content());self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
        answers=iter(["priority","高"]);page.on("dialog",lambda dialog:dialog.accept(next(answers)))
        with page.expect_response(lambda response:response.request.method=="POST" and response.url.endswith("/api/workspaces/1/tasks/batch")) as captured:page.locator('[data-batch="update"]').click()
        response=captured.value;request=response.request.post_data_json;result=response.json();self.assertEqual(request["operation"],"update");self.assertEqual(request["changes"],{"priority":"高"});self.assertEqual(result["updated"],2);self.assertEqual([item["id"] for item in result["items"]],sorted(selected_ids));page.wait_for_function("document.querySelector('#batchBar').hidden")
        health=page.evaluate("fetch('/api/health').then(r=>r.json())");self.assertEqual(health,{"status":"ok","schema_version":15})
        backup=page.evaluate("api('/api/admin/workspaces/1/backups','POST',{})");self.assertTrue(backup["verified"]);self.assertEqual(backup["restore_mode"],"offline_cli_only");self.assertTrue(page.evaluate("api('/api/admin/workspaces/1/backups').then(x=>x.backups[0].valid)"));context.close()


if __name__=="__main__":unittest.main()
