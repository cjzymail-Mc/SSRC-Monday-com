import hashlib
import io
import json
import os
import tempfile
import threading
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

from flowboard.database import connect, migrate
from flowboard.transfer import make_xlsx, parse_upload
from server import create_server


class TimelineProductionE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="timeline-e2e-")
        self.db_path = str(Path(self.temp.name) / "flowboard.db")
        os.environ["FLOWBOARD_INITIAL_PASSWORD"] = "test-password"
        migrate(self.db_path, initial_password="test-password")
        db = connect(self.db_path)
        db.execute("INSERT INTO users SELECT 'u2','u2','成员',password_hash,NULL,NULL,1,'2026-01-01T00:00:00+00:00' FROM users WHERE id='u1'")
        db.execute("INSERT INTO workspace_memberships VALUES (1,'u2','member')")
        db.execute("INSERT INTO users SELECT 'u3','u3','只读',password_hash,NULL,NULL,1,'2026-01-01T00:00:00+00:00' FROM users WHERE id='u1'")
        db.execute("INSERT INTO workspace_memberships VALUES (1,'u3','viewer')")
        db.execute("INSERT INTO workspaces VALUES (2,'往返空间','2026-01-01T00:00:00+00:00',30)")
        db.execute("INSERT INTO users SELECT 'u4','u4','往返管理员',password_hash,NULL,NULL,1,'2026-01-01T00:00:00+00:00' FROM users WHERE id='u1'")
        db.execute("INSERT INTO workspace_memberships VALUES (2,'u4','admin')")
        db.commit()
        db.close()
        self.server = create_server("127.0.0.1", 0, self.db_path)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()
        os.environ.pop("FLOWBOARD_INITIAL_PASSWORD", None)

    def login(self, username):
        context = self.browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()
        page.flowboard_console_errors = []
        page.flowboard_page_errors = []
        page.flowboard_prelogin_session = []
        page.on("console", lambda message: page.flowboard_console_errors.append(message.text) if message.type == "error" else None)
        page.on("pageerror", lambda error: page.flowboard_page_errors.append(str(error)))
        page.on("response", lambda response: page.flowboard_prelogin_session.append(response.status) if response.url.endswith("/api/session") else None)
        page.goto(self.base)
        page.locator("#loginUser").fill(username)
        page.locator("#loginPassword").fill("test-password")
        page.locator("#loginForm button[type=submit]").click()
        identity = page.locator("#currentUser > span:not(.avatar)")
        identity.wait_for()
        self.assertEqual(identity.inner_text(), {"u1": "管理员", "u2": "成员", "u3": "只读", "u4": "往返管理员"}[username])
        page.locator("#loadState", has_text="刚刚同步").wait_for()
        self.assertEqual(page.flowboard_prelogin_session, [401])
        self.assertEqual(page.flowboard_page_errors, [])
        self.assertEqual(len(page.flowboard_console_errors), 1)
        self.assertIn("401", page.flowboard_console_errors[0])
        page.flowboard_console_errors.clear()
        page.flowboard_page_errors.clear()
        return context, page

    def assert_clean_browser(self, page):
        self.assertEqual(page.flowboard_page_errors, [])
        self.assertEqual(page.flowboard_console_errors, [])

    def seed_timeline(self, created_by="u1", name="CP2 草稿项目"):
        db = connect(self.db_path)
        try:
            now = "2026-08-20T00:00:00+00:00"
            cur = db.execute("INSERT INTO timeline_projects(workspace_id,name,created_by,version,created_at,updated_at) VALUES (1,?,?,1,?,?)", (name, created_by, now, now))
            project_id = cur.lastrowid
            for track, stage, name, date in (("main", "创意", "A1", "2026-08-01"), ("main", "设计", "A2", "2026-08-05"), ("main", "开发", "A3", "2026-08-09"), ("parallel", "测试", "P1", "2026-08-03")):
                db.execute("INSERT INTO timeline_nodes(project_id,track,stage,name,date,initial_date,remark,version,created_at,updated_at) VALUES (?,?,?,?,?,?,'',1,?,?)", (project_id, track, stage, name, date, date, now, now))
            db.commit()
            return project_id
        finally:
            db.close()

    def seed_cp4_dashboard_projects(self):
        today = datetime.now(timezone(timedelta(hours=8))).date()
        yesterday = today - timedelta(days=1)
        next_week = today + timedelta(days=8)
        db = connect(self.db_path)
        try:
            now = datetime.now(timezone.utc).isoformat()
            projects = []
            fixtures = (
                ("CP4 重叠双轨", (("main", "创意", "较早逾期节点", today - timedelta(days=2)), ("main", "创意", "逾期节点", yesterday), ("main", "设计", "主线重叠一", today), ("main", "开发", "主线重叠二", today), ("parallel", "测试", "并行重叠一", today), ("parallel", "量产", "并行重叠二", today))),
                ("CP4 较早项目", (("main", "创意", "较早开始", today - timedelta(days=20)), ("main", "设计", "下一节点", next_week))),
                ("CP4 临近项目", (("main", "创意", "今天启动", today), ("parallel", "应用迭代", "稍后节点", today + timedelta(days=2)))),
            )
            for project_name, nodes in fixtures:
                project = db.execute("INSERT INTO timeline_projects(workspace_id,name,created_by,version,created_at,updated_at) VALUES (1,?,'u1',1,?,?)", (project_name, now, now))
                project_id = project.lastrowid
                projects.append(project_id)
                for track, stage, node_name, node_date in nodes:
                    value = node_date.isoformat()
                    db.execute("INSERT INTO timeline_nodes(project_id,track,stage,name,date,initial_date,remark,version,created_at,updated_at) VALUES (?,?,?,?,?,?,'',1,?,?)", (project_id, track, stage, node_name, value, value, now, now))
            db.commit()
            return projects, today.isoformat()
        finally:
            db.close()

    def open_cp4_single(self, page, project_id):
        self.physical_click(page, page.locator("#timelineBtn"))
        page.locator('[data-timeline-page="home"]').wait_for()
        self.physical_click(page, page.locator(f'[data-timeline-open="single"][data-project-id="{project_id}"]'))
        page.locator(f'[data-timeline-page="single"] [data-dashboard-project="{project_id}"]').wait_for()

    def timeline_content_hash(self):
        db = connect(self.db_path)
        try:
            payload = {}
            for table in ("timeline_projects", "timeline_nodes", "timeline_change_batches", "timeline_node_changes"):
                payload[table] = [dict(row) for row in db.execute(f"SELECT * FROM {table} ORDER BY id")]
            return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()
        finally:
            db.close()

    @staticmethod
    def timeline_headers():
        return ["项目名称", "阶段", "轨道", "节点", "日期", "间隔", "状态", "备注"]

    @staticmethod
    def add_zip_entries(raw, entries):
        source = zipfile.ZipFile(io.BytesIO(raw))
        output = io.BytesIO()
        with source, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as target:
            for item in source.infolist():
                target.writestr(item, source.read(item.filename))
            for name, content in entries.items():
                target.writestr(name, content)
        return output.getvalue()

    @classmethod
    def two_sheet_xlsx(cls, raw):
        source = zipfile.ZipFile(io.BytesIO(raw))
        entries = {item.filename: source.read(item.filename) for item in source.infolist()}
        source.close()
        workbook = entries["xl/workbook.xml"].decode()
        workbook = workbook.replace("</sheets>", '<sheet name="Ignored" sheetId="2" r:id="rId2"/></sheets>')
        rels = entries["xl/_rels/workbook.xml.rels"].decode()
        rels = rels.replace("</Relationships>", '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/></Relationships>')
        entries["xl/workbook.xml"] = workbook
        entries["xl/_rels/workbook.xml.rels"] = rels
        entries["xl/worksheets/sheet2.xml"] = entries["xl/worksheets/sheet1.xml"]
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as target:
            for name, content in entries.items():
                target.writestr(name, content)
        return output.getvalue()

    def open_timeline_home(self, page):
        self.physical_click(page, page.locator("#timelineBtn"))
        page.locator('[data-timeline-page="home"]').wait_for()

    def upload_timeline(self, page, filename, raw, status=None, error_code=None):
        console_before = len(page.flowboard_console_errors)
        pageerror_before = len(page.flowboard_page_errors)
        predicate = lambda response: response.url.endswith("/timeline/imports/preview") and response.request.method == "POST"
        with page.expect_response(predicate) as pending:
            page.locator("[data-timeline-import-file]").set_input_files({"name": filename, "mimeType": "text/csv" if filename.endswith(".csv") else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "buffer": raw})
        response = pending.value
        if status is not None:
            self.assertEqual(response.status, status)
        if error_code is not None:
            self.assertTrue(response.url.endswith("/timeline/imports/preview"))
            self.assertEqual(response.status, 422)
            self.assertEqual(response.json()["error"]["code"], error_code)
            page.locator(f'[data-timeline-import-error="{error_code}"]').wait_for()
            expected_console = page.flowboard_console_errors[console_before:]
            self.assertEqual(len(expected_console), 1, f"{filename} must emit exactly one expected HTTP 422 console entry")
            self.assertIn("Failed to load resource", expected_console[0])
            self.assertIn("422", expected_console[0])
            self.assertEqual(page.flowboard_page_errors[pageerror_before:], [])
            del page.flowboard_console_errors[console_before:]
        return response

    def commit_timeline(self, page):
        button = page.locator("[data-timeline-import-commit]")
        self.record_mouse_sequence(page, "[data-timeline-import-commit]")
        with page.expect_response(lambda response: response.url.endswith("/timeline/imports/commit") and response.request.method == "POST") as pending:
            self.physical_click(page, button)
        self.assertEqual(page.evaluate("window.__timelineClicks"), ["mousedown", "mouseup", "click"])
        return pending.value

    @staticmethod
    def physical_click(page, locator, button="left"):
        box = locator.bounding_box()
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.mouse.down(button=button)
        page.mouse.up(button=button)

    @staticmethod
    def record_mouse_sequence(page, selector):
        page.evaluate("""selector => {
          window.__timelineClicks = [];
          const target = document.querySelector(selector);
          for (const type of ['mousedown', 'mouseup', 'click'])
            target.addEventListener(type, event => window.__timelineClicks.push(event.type));
        }""", selector)

    def test_admin_real_entry_modes_create_delete_and_refresh_persistence(self):
        context, page = self.login("u1")
        responses = []
        page.on("response", lambda response: responses.append((response.request.method, response.url, response.status)))
        self.record_mouse_sequence(page, "#timelineBtn")
        page.locator("#timelineBtn").click()
        page.locator('[data-timeline-page="home"]').wait_for()
        self.assertEqual(page.evaluate("window.__timelineClicks"), ["mousedown", "mouseup", "click"])

        page.locator('[data-timeline-create] input[name="name"]').fill("浏览器项目")
        page.locator('[data-timeline-create] button[type="submit"]').click()
        page.locator('[data-timeline-page="editor"] .timeline-sheet-project', has_text="浏览器项目").wait_for()
        self.assertTrue(any(method == "POST" and url.endswith("/api/workspaces/1/timeline/projects") and status == 201 for method, url, status in responses))
        self.assertTrue(any(method == "GET" and url.endswith("/api/workspaces/1/timeline") and status == 200 for method, url, status in responses))

        self.record_mouse_sequence(page, '[data-timeline-mode-target="single"]')
        page.locator('[data-timeline-mode-target="single"]').click()
        page.locator('[data-timeline-page="single"] > .timeline-project-card > header h2', has_text="浏览器项目").wait_for()
        self.assertEqual(page.evaluate("window.__timelineClicks"), ["mousedown", "mouseup", "click"])
        self.assertTrue(any(method == "GET" and "/api/timeline/projects/" in url and status == 200 for method, url, status in responses))
        page.locator('[data-timeline-mode-target="all"]').click()
        page.locator('[data-timeline-page="all"] .timeline-all').wait_for()

        page.reload()
        page.locator("#timelineBtn").click()
        page.locator('[data-timeline-page="home"]').wait_for()
        page.locator('[data-project-choice] strong', has_text="浏览器项目").wait_for()
        self.assertEqual(page.locator('[data-timeline-create] input[name="name"]').get_attribute("maxlength"), "200")
        stable = self.timeline_content_hash()
        console_before = len(page.flowboard_console_errors)
        page.locator('[data-timeline-create] input[name="name"]').fill("  浏览器项目  ")
        with page.expect_response(lambda response: response.request.method == "POST" and response.url.endswith("/api/workspaces/1/timeline/projects")) as duplicate:
            self.physical_click(page, page.locator('[data-timeline-create] button[type="submit"]'))
        self.assertEqual(duplicate.value.status, 422)
        self.assertEqual(duplicate.value.json()["error"]["code"], "NAME_CONFLICT")
        page.locator("#toast").wait_for()
        expected_console = page.flowboard_console_errors[console_before:]
        self.assertEqual(len(expected_console), 1)
        self.assertIn("422", expected_console[0])
        del page.flowboard_console_errors[console_before:]
        self.assertEqual(self.timeline_content_hash(), stable, "trimmed duplicate project create must write nothing")

        stale_context, stale_page = self.login("u1")
        self.open_timeline_home(stale_page)
        stale_choice = stale_page.locator('[data-project-choice]', has_text="浏览器项目")
        project_id = stale_choice.get_attribute("data-project-choice")
        self.physical_click(stale_page, stale_choice.locator('[data-timeline-open="single"]'))
        stale_page.locator(f'[data-dashboard-project="{project_id}"]').wait_for()
        page.on("dialog", lambda dialog: dialog.accept())
        project_choice = page.locator('[data-project-choice]', has_text="浏览器项目")
        with page.expect_response(lambda response: response.request.method == "DELETE" and "/api/workspaces/1/timeline/projects/" in response.url) as deleted_response:
            self.physical_click(page, project_choice.locator('[data-timeline-delete]'))
        self.assertEqual(deleted_response.value.status, 200)
        project_choice.wait_for(state="detached")
        self.assertEqual(page.locator('[data-project-choice] strong', has_text="浏览器项目").count(), 0)
        stale_console = len(stale_page.flowboard_console_errors)
        stale_pageerror = len(stale_page.flowboard_page_errors)
        with stale_page.expect_response(lambda response: response.url.endswith(f"/api/timeline/projects/{project_id}")) as deleted_get:
            self.physical_click(stale_page, stale_page.locator('[data-timeline-mode-target="editor"]'))
        self.assertEqual(deleted_get.value.status, 404)
        deleted_error = deleted_get.value.json()["error"]
        self.assertEqual(deleted_error["code"], "PROJECT_NOT_ACTIVE")
        self.assertTrue(isinstance(deleted_error["message"], str) and deleted_error["message"].strip())
        stale_page.wait_for_function("() => document.querySelector('#toast')?.classList.contains('show')")
        toast = stale_page.locator("#toast")
        self.assertTrue(toast.is_visible())
        self.assertEqual(toast.inner_text(), deleted_error["message"])
        expected_404_console = stale_page.flowboard_console_errors[stale_console:]
        self.assertEqual(len(expected_404_console), 1)
        self.assertIn("Failed to load resource", expected_404_console[0])
        self.assertIn("404", expected_404_console[0])
        self.assertEqual(stale_page.flowboard_page_errors[stale_pageerror:], [])
        del stale_page.flowboard_console_errors[stale_console:]
        self.assert_clean_browser(stale_page); stale_context.close()
        db = connect(self.db_path)
        try:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM timeline_projects WHERE name='浏览器项目' AND deleted_at IS NOT NULL").fetchone()[0], 1)
        finally:
            db.close()
        self.assert_clean_browser(page)
        context.close()

    def test_member_can_read_and_create_but_has_no_delete_control(self):
        context, page = self.login("u2")
        page.locator("#timelineBtn").click()
        page.locator('[data-timeline-page="home"]').wait_for()
        page.locator('[data-timeline-create] input[name="name"]').fill("成员项目")
        page.locator('[data-timeline-create] button[type="submit"]').click()
        page.locator('[data-timeline-page="editor"] .timeline-sheet-project', has_text="成员项目").wait_for()
        page.locator('[data-timeline-mode-target="single"]').click()
        page.locator('[data-timeline-page="single"] > .timeline-project-card > header h2', has_text="成员项目").wait_for()
        page.locator('[data-timeline-mode-target="home"]').click()
        self.assertEqual(page.locator('[data-timeline-delete]').count(), 0)
        self.assert_clean_browser(page)
        context.close()

    def test_viewer_is_denied_by_server_and_cannot_open_timeline(self):
        context, page = self.login("u3")
        denied = []
        page.on("response", lambda response: denied.append(response.status) if response.url.endswith("/api/workspaces/1/timeline") else None)
        page.locator("#timelineBtn").click()
        page.locator("#toast", has_text="资源不存在或不可访问").wait_for()
        self.assertEqual(denied, [403])
        self.assertTrue(page.locator("#timelineModal").evaluate("element => element.hidden"))
        self.assertEqual(page.flowboard_page_errors, [])
        self.assertEqual(len(page.flowboard_console_errors), 1)
        self.assertIn("403", page.flowboard_console_errors[0])
        page.flowboard_console_errors.clear()
        self.assert_clean_browser(page)
        context.close()

    def test_timeline_cp2_table_editor_local_draft_sort_interval_and_discard(self):
        project_id = self.seed_timeline()
        context, page = self.login("u1")
        requests = []
        page.on("request", lambda request: requests.append((request.method, request.url)))
        self.physical_click(page, page.locator("#timelineBtn"))
        page.locator('[data-timeline-page="home"]').wait_for()
        self.physical_click(page, page.locator(f'[data-timeline-open="editor"][data-project-id="{project_id}"]'))
        table = page.locator('[data-timeline-page="editor"] .timeline-sheet')
        table.wait_for()
        self.assertEqual(page.locator('[data-timeline-mode-target="editor"]').inner_text(), "时间表编辑器")
        self.assertEqual(table.locator("thead th").all_inner_texts(), ["#", "项目阶段", "轨道", "项目节点", "日期", "时间间隔（天）", "状态", "备注", "操作"])
        self.assertEqual(page.locator('[data-timeline-page="editor"] .timeline-canvas').count(), 0)
        self.assertEqual(page.locator('[data-timeline-page="editor"] .timeline-node').count(), 0)
        self.assertEqual(page.locator('[data-timeline-page="editor"] [data-timeline-context]').count(), 0)
        baseline = len(requests)

        self.physical_click(page, page.locator('[data-timeline-gap-toggle]'))
        self.assertTrue(table.locator('th[data-interval-column]').is_visible())
        self.assertEqual(table.locator('[data-editor-row="1"] [data-interval-column]').inner_text(), "—")
        self.assertEqual(table.locator('[data-editor-field="interval_days"][data-node-id="2"]').input_value(), "4")

        date_input = table.locator('[data-editor-field="date"][data-node-id="1"]')
        date_input.fill("2026-08-02")
        date_input.press("Tab")
        remark = table.locator('[data-editor-field="remark"][data-node-id="1"]')
        remark.fill("表内修改")
        remark.press("Tab")
        self.assertEqual(page.locator('[data-timeline-draft-count]').inner_text(), "1 项草稿")

        interval = table.locator('[data-editor-field="interval_days"][data-node-id="2"]')
        interval.fill("6")
        interval.press("Tab")
        table.locator('[data-editor-field="track"][data-node-id="2"]').select_option("parallel")
        self.assertTrue(table.locator('[data-editor-field="interval_days"][data-node-id="2"]').is_disabled(), "track change clears and disables incompatible interval intent")
        self.assertEqual(page.locator('[data-timeline-draft-count]').inner_text(), "2 项草稿")
        self.assertEqual(len(requests), baseline, "table edits, interval toggle and sorting must stay local")

        self.record_mouse_sequence(page, '[data-timeline-sort-toggle]')
        self.physical_click(page, page.locator('[data-timeline-sort-toggle]'))
        self.assertEqual(page.evaluate("window.__timelineClicks"), ["mousedown", "mouseup", "click"])
        self.assertIn("按六大阶段", page.locator('[data-timeline-sort-toggle]').inner_text())
        self.assertEqual(page.locator('[data-timeline-draft-count]').inner_text(), "2 项草稿")
        self.assertEqual(len(requests), baseline)

        page.on("dialog", lambda dialog: dialog.dismiss())
        self.physical_click(page, page.locator('[data-timeline-mode-target="home"]'))
        self.assertEqual(page.locator('[data-timeline-page="editor"]').count(), 1, "dismissed leave warning preserves table draft")
        self.physical_click(page, page.locator('[data-timeline-discard]'))
        self.assertEqual(page.locator('[data-timeline-draft-count]').inner_text(), "0 项草稿")
        self.assertEqual(page.locator('[data-editor-field="date"][data-node-id="1"]').input_value(), "2026-08-01")
        self.assertEqual(page.locator('[data-editor-field="track"][data-node-id="2"]').input_value(), "main")
        self.assert_clean_browser(page)
        context.close()

    def test_timeline_cp3_submit_mixed_batch_refresh_review_correction_and_undo(self):
        project_id = self.seed_timeline()
        context, page = self.login("u1")
        batch_requests = []
        page.on("request", lambda request: batch_requests.append(request.post_data_json) if request.method == "POST" and request.url.endswith("/timeline/batches") else None)
        page.locator("#timelineBtn").click()
        page.locator(f'[data-timeline-open="editor"][data-project-id="{project_id}"]').click()
        table = page.locator('[data-timeline-page="editor"] .timeline-sheet')
        table.wait_for()

        date = table.locator('[data-editor-field="date"][data-node-id="1"]')
        date.fill("2026-08-02"); date.press("Tab")
        self.physical_click(page, page.locator('[data-timeline-gap-toggle]'))
        interval = table.locator('[data-editor-field="interval_days"][data-node-id="2"]')
        interval.fill("6"); interval.press("Tab")
        table.locator('[data-editor-field="stage"][data-node-id="2"]').select_option("测试")
        name = table.locator('[data-editor-field="name"][data-node-id="2"]')
        name.fill("CP3 表格节点"); name.press("Tab")
        remark = table.locator('[data-editor-field="remark"][data-node-id="2"]')
        remark.fill("表格批量修改"); remark.press("Tab")
        table.locator('[data-editor-field="done_at"][data-node-id="2"]').select_option("true")
        self.physical_click(page, page.locator('[data-timeline-remove-node="4"]'))

        self.physical_click(page, page.locator('[data-timeline-add]'))
        new_row = page.locator('[data-editor-row^="-"]').first
        new_row.wait_for()
        new_row.locator('[data-editor-field="name"]').fill("CP3 新节点")
        new_row.locator('[data-editor-field="name"]').press("Tab")
        new_row.locator('[data-editor-field="date"]').fill("2026-08-15")
        new_row.locator('[data-editor-field="date"]').press("Tab")
        new_row.locator('[data-editor-field="stage"]').select_option("测试")
        new_row.locator('[data-editor-field="track"]').select_option("parallel")
        new_row.locator('[data-editor-field="remark"]').fill("新增行直接编辑")
        new_row.locator('[data-editor-field="remark"]').press("Tab")
        new_row.locator('[data-editor-field="done_at"]').select_option("true")
        self.assertEqual(page.locator('[data-timeline-draft-count]').inner_text(), "4 项草稿")
        with page.expect_response(lambda response: response.request.method == "POST" and response.url.endswith("/timeline/batches")) as submitted:
            self.physical_click(page, page.locator('[data-timeline-submit]'))
        self.assertEqual(submitted.value.status, 200)
        self.assertEqual(len(batch_requests), 1, "update button must issue exactly one batch POST")
        request = batch_requests[0]["requests"][0]
        self.assertEqual(request["trigger_source"], "editor")
        self.assertEqual((request["details"]["mode"], request["details"]["magnet"], request["details"]["zoom_band"]), ("cascade", "standard", "±10d×8"))
        self.assertTrue(any("date" in row.get("set", {}) for row in request["changes"]))
        self.assertTrue(any("interval_days" in row.get("set", {}) for row in request["changes"]))
        self.assertTrue(any("done_at" in row.get("set", {}) for row in request["changes"]))
        self.assertTrue(any({"stage", "name", "remark"}.issubset(row.get("set", {})) for row in request["changes"]))
        self.assertTrue(any("create" in row for row in request["changes"]))
        self.assertTrue(any(row.get("remove") for row in request["changes"]))
        with page.expect_response(lambda response: response.url.endswith("/timeline/batches/undo")) as undone:
            self.physical_click(page, page.locator('[data-timeline-undo]'))
        self.assertEqual(undone.value.status, 200)
        db = connect(self.db_path)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM timeline_nodes WHERE project_id=? AND deleted_at IS NULL", (project_id,)).fetchone()[0], 4)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM timeline_nodes WHERE project_id=? AND name='CP3 新节点' AND deleted_at IS NULL", (project_id,)).fetchone()[0], 0)
        db.close()

        page.locator('[data-editor-field="done_at"][data-node-id="2"]').select_option("true")
        with page.expect_response(lambda response: response.request.method == "POST" and response.url.endswith("/timeline/batches")) as persisted:
            self.physical_click(page, page.locator('[data-timeline-submit]'))
        self.assertEqual(persisted.value.status, 200)
        page.reload(); page.locator("#timelineBtn").click(); page.locator(f'[data-timeline-open="editor"][data-project-id="{project_id}"]').click()
        page.locator('[data-editor-row="2"]').wait_for()
        db = connect(self.db_path)
        self.assertIsNotNone(db.execute("SELECT done_at FROM timeline_nodes WHERE id=2").fetchone()[0])
        db.close()

        self.physical_click(page, page.locator('[data-timeline-review]'))
        page.locator('[data-timeline-review-panel] article').first.wait_for()
        self.assertIn("管理员", page.locator('[data-timeline-review-panel]').inner_text())
        self.assertIn("项变更", page.locator('[data-timeline-review-panel]').inner_text())
        correction_answer = iter(["2026-07-25"])
        def answer_correction(dialog): dialog.accept(next(correction_answer))
        page.on("dialog", answer_correction)
        with page.expect_response(lambda response: response.url.endswith("/timeline/batches/initial-correction")) as corrected:
            self.physical_click(page, page.locator('[data-timeline-correct]'))
        self.assertEqual(corrected.value.status, 200)
        self.assert_clean_browser(page)
        context.close()

    def test_timeline_cp3_conflict_latest_view_zero_write_and_member_correction_denied(self):
        project_id = self.seed_timeline()
        context, page = self.login("u1")
        page.locator("#timelineBtn").click(); page.locator(f'[data-timeline-open="editor"][data-project-id="{project_id}"]').click()
        page.locator('[data-editor-row="2"]').wait_for()
        page.locator('[data-editor-field="done_at"][data-node-id="2"]').select_option("true")
        db = connect(self.db_path)
        db.execute("UPDATE timeline_projects SET version=2 WHERE id=?", (project_id,)); db.commit(); db.close()
        stable = self.timeline_content_hash()
        with page.expect_response(lambda response: response.request.method == "POST" and response.url.endswith("/timeline/batches")) as conflict:
            self.physical_click(page, page.locator('[data-timeline-submit]'))
        self.assertEqual(conflict.value.status, 409)
        page.locator("#toast", has_text="已显示服务端最新时间表").wait_for()
        self.assertEqual(page.locator('[data-timeline-draft-count]').inner_text(), "0 项草稿")
        self.assertEqual(self.timeline_content_hash(), stable, "409 must write no timeline content")
        self.assertEqual(page.locator('[data-timeline-page="editor"] [data-editor-row]').count(), 4)
        self.assertTrue(any("409" in message for message in page.flowboard_console_errors))
        page.flowboard_console_errors.clear()
        self.assert_clean_browser(page); context.close()

        member_project_id = self.seed_timeline(created_by="u2", name="成员纠正项目")
        member_context, member_page = self.login("u2")
        member_page.locator("#timelineBtn").click(); member_page.locator(f'[data-timeline-open="editor"][data-project-id="{member_project_id}"]').click()
        member_page.locator('[data-editor-row]').first.wait_for()
        self.assertEqual(member_page.locator('[data-timeline-correct]').count(), 0, "admin-only correction must not be exposed to members")
        self.assertTrue(member_page.locator('[data-timeline-add]').is_visible(), "project creator can edit its table")

        self.physical_click(member_page, member_page.locator('[data-timeline-mode-target="home"]'))
        member_page.locator('[data-timeline-page="home"]').wait_for()
        self.physical_click(member_page, member_page.locator('[data-timeline-tab="team"]'))
        self.physical_click(member_page, member_page.locator(f'[data-timeline-member-open="{project_id}"]'))
        member_page.locator('[data-timeline-page="single"]').wait_for()
        self.physical_click(member_page, member_page.locator('[data-timeline-mode-target="editor"]'))
        member_page.locator('.timeline-sheet-readonly').wait_for()
        self.assertEqual(member_page.locator('[data-timeline-add]').count(), 0)
        self.assertEqual(member_page.locator('[data-timeline-submit]').count(), 0)
        self.assertEqual(member_page.locator('[data-timeline-correct]').count(), 0)
        self.assertTrue(member_page.locator('[data-editor-field]').first.is_disabled())
        self.assert_clean_browser(member_page); member_context.close()

    def test_timeline_single_dashboard_structure(self):
        (project_id, _, _), _today = self.seed_cp4_dashboard_projects()
        context, page = self.login("u1")
        self.open_cp4_single(page, project_id)
        card = page.locator(f'[data-dashboard-project="{project_id}"]')
        self.assertEqual(card.locator("h2").inner_text(), "CP4 重叠双轨")
        self.assertIn("当前阶段", card.locator(".timeline-summary").inner_text())
        self.assertEqual(card.locator('[data-track="main"]').count(), 1)
        self.assertEqual(card.locator('[data-track="parallel"]').count(), 1)
        self.assertEqual(card.locator(".timeline-editor").count(), 0, "dashboard must not embed the editor")
        self.assert_clean_browser(page); context.close()

    def test_timeline_shared_calendar_and_today_marker(self):
        (project_id, _, _), today = self.seed_cp4_dashboard_projects()
        context, page = self.login("u1")
        self.open_cp4_single(page, project_id)
        self.physical_click(page, page.locator('[data-timeline-mode-target="all"]'))
        page.locator('[data-timeline-page="all"] [data-shared-calendar="true"]').wait_for()
        portfolio = page.locator('[data-timeline-page="all"] .timeline-portfolio-chart')
        self.assertEqual(portfolio.count(), 1)
        self.assertEqual(portfolio.locator('.timeline-calendar').count(), 1)
        self.assertEqual(portfolio.locator('.timeline-today-line').count(), 1)
        self.assertEqual(page.locator('[data-timeline-page="all"] .timeline-project-card').count(), 0)
        cards = page.locator("[data-dashboard-project]")
        self.assertGreaterEqual(cards.count(), 2)
        self.assertTrue(portfolio.get_attribute("data-calendar-start"))
        self.assertTrue(portfolio.get_attribute("data-calendar-end"))
        self.assertEqual(portfolio.locator(".timeline-today-line").get_attribute("data-today"), today)
        self.assertIn("今天", portfolio.locator(".timeline-today-line span").inner_text())
        self.assertEqual(portfolio.locator(".timeline-today-line").evaluate("node => getComputedStyle(node).backgroundColor"), "rgb(229, 72, 77)")
        self.assert_clean_browser(page); context.close()

    def test_timeline_overlap_split_and_expand(self):
        (project_id, _, _), _today = self.seed_cp4_dashboard_projects()
        context, page = self.login("u1")
        self.open_cp4_single(page, project_id)
        card = page.locator(f'[data-dashboard-project="{project_id}"]')
        for track in ("main", "parallel"):
            lane = card.locator(f'[data-track="{track}"]')
            self.assertEqual(lane.get_attribute("data-overlap-rows"), "2")
            self.assertGreater(lane.locator('[data-row-index="1"][data-overlap-split="true"]').count(), 0)
        expand = card.locator('[data-timeline-expand$=":main"]')
        self.record_mouse_sequence(page, '[data-timeline-expand$=":main"]')
        self.physical_click(page, expand)
        expanded = card.locator('[data-track="main"]')
        expanded.wait_for()
        self.assertEqual(page.evaluate("window.__timelineClicks"), ["mousedown", "mouseup", "click"])
        self.assertEqual(expanded.locator('[data-row-index="1"]').get_attribute("data-overlap-split"), "false")
        self.assertEqual(expanded.locator('[data-timeline-expand]').get_attribute("aria-expanded"), "true")
        self.assert_clean_browser(page); context.close()

    def test_timeline_stage_intervals_semantics(self):
        (project_id, _, _), _today = self.seed_cp4_dashboard_projects()
        context, page = self.login("u1")
        self.open_cp4_single(page, project_id)
        card = page.locator(f'[data-dashboard-project="{project_id}"]')
        intervals = card.locator('[data-stage-interval]')
        self.assertGreaterEqual(intervals.count(), 5)
        design = card.locator('[data-stage-interval][data-stage="设计"].stage-design')
        production = card.locator('[data-stage-interval][data-stage="量产"].stage-production')
        self.assertEqual(design.count(), 1)
        self.assertEqual(production.count(), 1)
        self.assertEqual(design.locator("b").inner_text(), "设计")
        self.assertIn("阶段 设计", design.get_attribute("aria-label"))
        self.assertEqual(production.locator("b").inner_text(), "量产")
        self.assertIn("阶段 量产", production.get_attribute("aria-label"))
        self.assertEqual(intervals.first.evaluate("node => getComputedStyle(node).borderRadius"), "2px")
        self.assertTrue(intervals.evaluate_all("nodes => nodes.every(node => parseFloat(node.style.width) > 0)"), "every stage interval remains a continuous positive-width bar")
        self.assertTrue(all(text.strip() for text in intervals.locator("b").all_inner_texts()), "six-stage color must also have text labels")
        self.assertTrue(all(value for value in intervals.evaluate_all("nodes => nodes.map(node => node.dataset.nodeIds)")))
        self.assert_clean_browser(page); context.close()

    def test_timeline_dashboards_share_context_controller(self):
        (project_id, _, _), _today = self.seed_cp4_dashboard_projects()
        context, page = self.login("u1")
        requests = []
        page.on("request", lambda request: requests.append((request.method, request.url)))
        self.open_cp4_single(page, project_id)
        stable_hash = self.timeline_content_hash()
        baseline = len(requests)
        node = page.locator(f'[data-dashboard-project="{project_id}"] .timeline-dashboard-node').first
        expected_node = node.get_attribute("data-node-id")
        node_box = node.bounding_box()
        self.assertEqual(page.evaluate("point => document.elementFromPoint(point.x, point.y)?.closest('.timeline-dashboard-node')?.dataset.nodeId || null", {"x": node_box["x"] + node_box["width"] / 2, "y": node_box["y"] + node_box["height"] / 2}), expected_node)
        page.evaluate("""() => { window.__dashboardHitEvents=[]; for (const type of ['mousedown','mouseup','contextmenu']) document.addEventListener(type,event=>window.__dashboardHitEvents.push({type,node:event.target.closest('.timeline-dashboard-node')?.dataset.nodeId||null}),{capture:true,once:true}) }""")
        self.physical_click(page, node, button="right")
        self.assertEqual(page.evaluate("window.__dashboardHitEvents"), [{"type":"mousedown","node":expected_node},{"type":"mouseup","node":expected_node},{"type":"contextmenu","node":expected_node}])
        menu = page.locator('[data-timeline-context]')
        self.assertEqual(menu.locator('[role="menuitem"]').count(), 4)
        self.record_mouse_sequence(page, '[data-timeline-context] [data-draft-action="cascade"]')
        self.physical_click(page, menu.locator('[data-draft-action="cascade"]'))
        self.assertEqual(page.evaluate("window.__timelineClicks"), ["mousedown", "mouseup", "click"])
        self.assertIn("尚未写入服务器", page.locator('[data-dashboard-hint]').inner_text())
        self.assertEqual(len(requests), baseline, "dashboard context action must issue zero network requests")
        self.assertEqual(self.timeline_content_hash(), stable_hash)
        self.physical_click(page, page.locator('[data-timeline-mode-target="all"]'))
        page.locator('[data-timeline-page="all"] .timeline-dashboard-node').first.wait_for()
        baseline = len(requests)
        self.physical_click(page, page.locator('[data-timeline-page="all"] .timeline-dashboard-node').first, button="right")
        self.assertEqual(page.locator('[data-timeline-page="all"] [data-timeline-context] [role="menuitem"]').count(), 4)
        self.physical_click(page, page.locator('[data-timeline-page="all"] [data-draft-action="done"]'))
        self.assertIn("尚未写入服务器", page.locator('[data-timeline-page="all"] [data-dashboard-hint]').first.inner_text())
        self.assertEqual(len(requests), baseline)
        self.assertEqual(self.timeline_content_hash(), stable_hash)
        self.assert_clean_browser(page); context.close()

    def test_timeline_all_dashboard_filter_and_sort(self):
        (project_id, _, _), _today = self.seed_cp4_dashboard_projects()
        context, page = self.login("u1")
        requests = []
        page.on("request", lambda request: requests.append((request.method, request.url)))
        self.open_cp4_single(page, project_id)
        self.physical_click(page, page.locator('[data-timeline-mode-target="all"]'))
        page.locator('[data-timeline-page="all"] [data-dashboard-project]').first.wait_for()
        stable_hash = self.timeline_content_hash()
        baseline = len(requests)
        self.assertFalse(page.locator('.timeline-portfolio-head').is_hidden())
        self.assertTrue(page.locator('.tl-order-note').is_hidden())
        for selector in ('[data-timeline-filter]', '[data-timeline-sort-key]', '[data-portfolio-fit]', '[data-portfolio-zoom-out]', '[data-portfolio-zoom-in]'):
            self.assertTrue(page.locator(selector).is_hidden(), f"{selector} must stay hidden after the latest visual decision")
        self.assertFalse(page.locator('[data-portfolio-fullscreen]').is_hidden())
        self.assertEqual(page.locator('[data-dashboard-project]').count(), 3)
        node = page.locator('[data-timeline-page="all"] .timeline-dashboard-node').first
        expected_node = node.get_attribute("data-node-id")
        node_box = node.bounding_box()
        center = {"x": node_box["x"] + node_box["width"] / 2, "y": node_box["y"] + node_box["height"] / 2}
        self.assertEqual(page.evaluate("point => document.elementFromPoint(point.x, point.y)?.closest('.timeline-dashboard-node')?.dataset.nodeId || null", center), expected_node)
        self.physical_click(page, node, button="right")
        self.assertFalse(page.locator('[data-timeline-page="all"] [data-timeline-context]').is_hidden())
        self.physical_click(page, page.locator('[data-timeline-page="all"] [data-draft-action="done"]'))
        self.assertEqual(node.get_attribute("data-dashboard-action"), "done")
        self.assertIn("is-context-target", node.get_attribute("class"))
        self.assertEqual(len(requests), baseline, "hidden chrome and node draft action must stay client-side")
        self.assertEqual(self.timeline_content_hash(), stable_hash)
        self.assert_clean_browser(page); context.close()

    def test_timeline_portfolio_e_d4_p1_canvas(self):
        (project_id, _, _), today_value = self.seed_cp4_dashboard_projects()
        today = datetime.fromisoformat(today_value).date()
        db = connect(self.db_path)
        try:
            now = datetime.now(timezone.utc).isoformat()
            for index in range(9):
                created = db.execute("INSERT INTO timeline_projects(workspace_id,name,created_by,version,created_at,updated_at) VALUES (1,?,'u1',1,?,?)", (f"画布压力项目 {index + 1:02d}", now, now))
                node_date = (today + timedelta(days=index - 4)).isoformat()
                db.execute("INSERT INTO timeline_nodes(project_id,track,stage,name,date,initial_date,remark,version,created_at,updated_at) VALUES (?,?,?,?,?,?,'',1,?,?)", (created.lastrowid, "main", "开发", f"压力节点 {index + 1:02d}", node_date, node_date, now, now))
            db.commit()
        finally:
            db.close()

        context, page = self.login("u1")
        self.open_cp4_single(page, project_id)
        self.physical_click(page, page.locator('[data-timeline-mode-target="all"]'))
        chart = page.locator('[data-timeline-page="all"] .timeline-portfolio-chart')
        chart.wait_for()

        self.assertEqual(chart.get_attribute("data-calendar-start"), (today - timedelta(days=50)).isoformat())
        self.assertEqual(chart.get_attribute("data-calendar-end"), (today + timedelta(days=38)).isoformat())
        for layer in ("years", "quarters", "months", "days"):
            self.assertEqual(page.locator(f".timeline-e-{layer}").count(), 1)
        row_height = page.locator('.timeline-portfolio-project').first.bounding_box()["height"]
        self.assertGreaterEqual(row_height, 61)
        self.assertLessEqual(row_height, 63)
        overlap_project = page.locator(f'[data-dashboard-project="{project_id}"]')
        self.physical_click(page, overlap_project.locator('[data-timeline-expand$=":main"]'))
        self.assertGreater(overlap_project.bounding_box()["height"], 62)
        self.physical_click(page, overlap_project.locator('[data-timeline-expand$=":main"]'))
        self.assertLessEqual(overlap_project.bounding_box()["height"], 63)
        sticky = page.evaluate("""() => ({
          axis:getComputedStyle(document.querySelector('.timeline-portfolio-axis')).position,
          axisLabel:getComputedStyle(document.querySelector('.timeline-portfolio-axis-label')).position,
          meta:getComputedStyle(document.querySelector('.timeline-portfolio-meta')).position
        })""")
        self.assertEqual(sticky, {"axis": "sticky", "axisLabel": "sticky", "meta": "sticky"})

        self.assertFalse(page.locator('.timeline-portfolio-head').is_hidden())
        self.assertTrue(page.locator('.tl-order-note').is_hidden())
        axis_detail = page.locator('.timeline-portfolio-axis-detail')
        axis_box = axis_detail.bounding_box()
        page.mouse.move(axis_box["x"] + axis_box["width"] * .55, axis_box["y"] + 54)
        for _ in range(16):
            if float(chart.get_attribute("data-viewport-days")) <= 14:
                break
            page.mouse.wheel(0, -120)
            page.wait_for_timeout(30)
            chart = page.locator('[data-timeline-page="all"] .timeline-portfolio-chart')
            chart.wait_for()
        self.assertEqual(float(chart.get_attribute("data-viewport-days")), 14)

        scroll = page.locator('[data-portfolio-scroll]')
        page.evaluate("""el => { el.scrollLeft=(el.scrollWidth-el.clientWidth)*.55; el.scrollTop=80 }""", scroll.element_handle())
        page.wait_for_timeout(180)
        before_pan = scroll.evaluate("el => ({left:el.scrollLeft,top:el.scrollTop})")
        self.assertEqual(axis_detail.evaluate("el => getComputedStyle(el).cursor"), "grab")
        axis_box = axis_detail.bounding_box()
        page.mouse.move(axis_box["x"] + axis_box["width"] * .55, axis_box["y"] + 24)
        page.mouse.down()
        page.mouse.move(axis_box["x"] + axis_box["width"] * .55 + 90, axis_box["y"] + 74, steps=5)
        self.assertTrue(page.locator('.timeline-portfolio-card').evaluate("el => el.classList.contains('is-panning')"))
        page.mouse.up()
        after_pan = scroll.evaluate("el => ({left:el.scrollLeft,top:el.scrollTop})")
        self.assertLess(after_pan["left"], before_pan["left"])
        self.assertLess(after_pan["top"], before_pan["top"])
        self.assertEqual(page.locator('.timeline-pan-hud').count(), 0)
        keys = page.evaluate("Object.keys(localStorage).filter(key => key.startsWith('flowboard:timeline-viewport:'))")
        self.assertIn("flowboard:timeline-viewport:1:u1:all", keys)

        self.physical_click(page, page.locator('[data-timeline-tag-context="uncategorized"]'))
        page.locator('[data-timeline-tag-context="uncategorized"].active').wait_for()
        uncategorized_days = float(page.locator('.timeline-portfolio-chart').get_attribute("data-viewport-days"))
        self.assertGreater(uncategorized_days, 14)
        axis_detail = page.locator('.timeline-portfolio-axis-detail')
        axis_box = axis_detail.bounding_box()
        page.mouse.move(axis_box["x"] + axis_box["width"] * .55, axis_box["y"] + 54)
        page.mouse.wheel(0, -120)
        page.locator('[data-timeline-tag-context="uncategorized"].active').wait_for()
        keys = page.evaluate("Object.keys(localStorage).filter(key => key.startsWith('flowboard:timeline-viewport:'))")
        self.assertIn("flowboard:timeline-viewport:1:u1:uncategorized", keys)
        self.physical_click(page, page.locator('[data-timeline-tag-context="all"]'))
        page.locator('[data-timeline-tag-context="all"].active').wait_for()
        self.assertEqual(float(page.locator('.timeline-portfolio-chart').get_attribute("data-viewport-days")), 14)

        scroll = page.locator('[data-portfolio-scroll]')
        node = page.locator('[data-timeline-page="all"] .timeline-dashboard-node').first
        node.evaluate("el => el.scrollIntoView({block:'center',inline:'center'})")
        page.wait_for_timeout(180)
        node_box = node.bounding_box()
        hit_node_id = page.evaluate("point => document.elementFromPoint(point.x,point.y)?.closest('.timeline-dashboard-node')?.dataset.nodeId || null", {"x": node_box["x"] + node_box["width"] / 2, "y": node_box["y"] + node_box["height"] / 2})
        self.assertEqual(hit_node_id, node.get_attribute("data-node-id"))
        self.physical_click(page, node, button="right")
        page.locator('[data-timeline-page="all"] [data-timeline-context]').wait_for(state="visible")
        self.physical_click(page, page.locator('[data-timeline-page="all"] [data-draft-action="cascade"]'))
        node_box = node.bounding_box()
        scroll_box = scroll.bounding_box()
        edge_before = scroll.evaluate("el => el.scrollLeft")
        page.mouse.move(node_box["x"] + node_box["width"] / 2, node_box["y"] + node_box["height"] / 2)
        page.mouse.down()
        page.mouse.move(scroll_box["x"] + scroll_box["width"] - 12, node_box["y"] + node_box["height"] / 2, steps=8)
        guides = page.locator('[data-portfolio-drag-guides]')
        self.assertFalse(guides.is_hidden())
        self.assertTrue(guides.locator('.target-label').inner_text())
        self.assertEqual(page.locator('.timeline-e-month.is-target').count(), 1)
        self.assertEqual(page.locator('.timeline-e-day-tick.is-target').count(), 1)
        page.wait_for_timeout(520)
        self.assertGreater(scroll.evaluate("el => el.scrollLeft"), edge_before)
        page.mouse.up()
        page.locator('[data-portfolio-drag-guides]').wait_for(state="hidden")
        self.assert_clean_browser(page)
        context.close()

    def test_timeline_v18_archive_mask_cluster_single_pan_and_fullscreen(self):
        (project_id, _, _), _today = self.seed_cp4_dashboard_projects()
        context, page = self.login("u1")
        self.open_cp4_single(page, project_id)

        single = page.locator('[data-timeline-page="single"] [data-single-scroll]')
        chart = single.locator('.timeline-single-chart')
        chart.wait_for()
        self.assertEqual(chart.locator('.timeline-past-mask').count(), 2)
        self.assertEqual(
            chart.locator('.timeline-past-mask').first.evaluate("el => getComputedStyle(el).backgroundColor"),
            "rgba(255, 255, 255, 0.8)",
        )
        initial_days = float(chart.get_attribute("data-viewport-days"))
        box = single.bounding_box()
        page.mouse.move(box["x"] + box["width"] * .72, box["y"] + 36)
        page.mouse.wheel(0, -120)
        page.wait_for_function(
            "before => Number(document.querySelector('.timeline-single-chart').dataset.viewportDays) < before",
            arg=initial_days,
        )
        single = page.locator('[data-timeline-page="single"] [data-single-scroll]')
        for _ in range(5):
            dimensions = single.evaluate("el => ({client:el.clientWidth,scroll:el.scrollWidth})")
            if dimensions["scroll"] > dimensions["client"] + 40:
                break
            box = single.bounding_box()
            page.mouse.move(box["x"] + box["width"] * .72, box["y"] + 36)
            page.mouse.wheel(0, -120)
            page.wait_for_timeout(50)
            single = page.locator('[data-timeline-page="single"] [data-single-scroll]')
        dimensions = single.evaluate("el => ({client:el.clientWidth,scroll:el.scrollWidth})")
        self.assertGreater(dimensions["scroll"], dimensions["client"] + 40)
        ruler = single.locator('.timeline-month-ruler')
        page.evaluate("el => { el.scrollLeft=(el.scrollWidth-el.clientWidth)*.55 }", single.element_handle())
        before = single.evaluate("el => ({left:el.scrollLeft,top:el.scrollTop})")
        ruler_box = ruler.bounding_box()
        page.mouse.move(ruler_box["x"] + ruler_box["width"] * .55, ruler_box["y"] + ruler_box["height"] / 2)
        page.mouse.down()
        page.mouse.move(ruler_box["x"] + ruler_box["width"] * .55 + 80, ruler_box["y"] + ruler_box["height"] / 2 + 30, steps=5)
        page.mouse.up()
        after = single.evaluate("el => ({left:el.scrollLeft,top:el.scrollTop})")
        self.assertLess(after["left"], before["left"])
        self.assertEqual(after["top"], before["top"], "single-project canvas must never pan vertically")

        self.physical_click(page, page.locator('[data-timeline-mode-target="all"]'))
        portfolio = page.locator('[data-timeline-page="all"] .timeline-portfolio-chart')
        portfolio.wait_for()
        self.assertFalse(page.locator('[data-portfolio-fullscreen]').is_hidden())
        self.physical_click(page, page.locator('[data-portfolio-fullscreen]'))
        page.locator('.timeline-portfolio-card.is-fullscreen').wait_for()
        self.physical_click(page, page.locator('[data-portfolio-fullscreen]'))
        self.assertEqual(page.locator('.timeline-portfolio-card.is-fullscreen').count(), 0)

        crowded = page.locator('.timeline-node-cluster[title*="较早逾期节点"][title*="逾期节点"]')
        self.assertEqual(crowded.count(), 1)
        axis = page.locator('.timeline-portfolio-axis-detail')
        axis_box = axis.bounding_box()
        page.mouse.move(axis_box["x"] + axis_box["width"] * .45, axis_box["y"] + 80)
        for _ in range(16):
            if float(page.locator('.timeline-portfolio-chart').get_attribute("data-viewport-days")) <= 14:
                break
            page.mouse.wheel(0, -120)
            page.wait_for_timeout(30)
        self.assertEqual(page.locator('.timeline-dashboard-node[aria-label^="节点 较早逾期节点，"]').count(), 1)
        self.assertEqual(page.locator('.timeline-dashboard-node[aria-label^="节点 逾期节点，"]').count(), 1)

        row = page.locator(f'[data-dashboard-project="{project_id}"]')
        row.locator('.timeline-row-menu summary').click()
        page.once("dialog", lambda dialog: dialog.accept())
        with page.expect_response(lambda response: response.request.method == "POST" and response.url.endswith(f"/timeline/projects/{project_id}/archive")) as archived:
            row.locator(f'[data-timeline-archive="{project_id}"]').click()
        self.assertEqual(archived.value.status, 200)
        page.locator(f'[data-timeline-page="all"] [data-dashboard-project="{project_id}"]').wait_for(state="detached")

        self.physical_click(page, page.locator('[data-timeline-tag-context="archived"]'))
        page.locator('[data-timeline-tag-context="archived"].active').wait_for()
        archived_row = page.locator(f'[data-timeline-page="all"] [data-dashboard-project="{project_id}"]')
        archived_row.wait_for()
        self.assertIn("已归档 · 只读", archived_row.inner_text())
        self.assertEqual(archived_row.locator('[data-dashboard-submit], [data-timeline-archive], [data-timeline-context]').count(), 0)
        archived_axis = page.locator('.timeline-portfolio-axis-detail')
        archived_axis_box = archived_axis.bounding_box()
        page.mouse.move(archived_axis_box["x"] + archived_axis_box["width"] * .55, archived_axis_box["y"] + 80)
        page.mouse.wheel(0, -120)
        page.wait_for_timeout(80)
        self.assertIn("flowboard:timeline-viewport:1:u1:archived", page.evaluate("Object.keys(localStorage).join('|')"))

        self.physical_click(page, page.locator('#archivedBtn'))
        archive_page_row = page.locator(f'[data-timeline-page="archived"] .tl-archive-row:has-text("CP4 重叠双轨")')
        archive_page_row.wait_for()
        self.assertEqual(page.locator('[data-timeline-page="archived"] .timeline-portfolio-chart').count(), 0)
        with page.expect_response(lambda response: response.request.method == "POST" and response.url.endswith(f"/timeline/projects/{project_id}/unarchive")) as unarchived:
            self.physical_click(page, archive_page_row.locator('[data-timeline-unarchive]'))
        self.assertEqual(unarchived.value.status, 200)
        archive_page_row.wait_for(state="detached")
        self.physical_click(page, page.locator('#timelineBtn'))
        page.locator(f'[data-timeline-page="home"] [data-project-choice="{project_id}"]').wait_for()
        self.assert_clean_browser(page)
        context.close()

    def test_timeline_dashboard_risk_markers(self):
        (project_id, _, _), _today = self.seed_cp4_dashboard_projects()
        context, page = self.login("u1")
        self.open_cp4_single(page, project_id)
        markers = page.locator(f'[data-dashboard-project="{project_id}"] .timeline-risk-markers')
        self.assertEqual(markers.locator(".overdue").count(), 1)
        self.assertEqual(markers.locator(".this-week").count(), 1)
        classes = markers.locator(".timeline-risk").evaluate_all("nodes => nodes.map(node => node.className)")
        self.assertIn("overdue", classes[0])
        self.assertIn("this-week", classes[1])
        self.assertIn("逾期", markers.locator(".overdue").inner_text())
        self.assertIn("本周", markers.locator(".this-week").inner_text())
        self.assert_clean_browser(page); context.close()

    def test_timeline_excel_preview_commit_real_file(self):
        context, page = self.login("u1")
        self.open_timeline_home(page)
        raw = make_xlsx(self.timeline_headers(), [
            ["CP5 导入", "创意", "main", "概念", "2026-08-01", "", "已完成", "保留完成状态"],
            ["CP5 导入", "设计", "parallel", "方案", "2026-08-03", "", "进行中", "将重算"],
        ])
        response = self.upload_timeline(page, "timeline.xlsx", raw, 201)
        preview = page.locator("[data-timeline-preview-id]")
        preview.wait_for()
        payload = response.json()
        self.assertEqual(preview.get_attribute("data-timeline-preview-id"), str(payload["batch_id"]))
        self.assertIn("CP5 导入：2 个节点", preview.inner_text())
        self.assertIn("状态将按日期重算，仅『已完成』保留", preview.inner_text())
        self.assertTrue(page.locator("[data-timeline-import-commit]").is_enabled())
        committed = self.commit_timeline(page)
        self.assertEqual(committed.status, 201)
        page.locator(".timeline-import-success").wait_for()
        db = connect(self.db_path)
        try:
            rows = list(db.execute("SELECT n.name,n.done_at FROM timeline_nodes n JOIN timeline_projects p ON p.id=n.project_id WHERE p.name='CP5 导入' ORDER BY n.id"))
            self.assertIsNotNone(rows[0]["done_at"])
            self.assertIsNone(rows[1]["done_at"])
        finally:
            db.close()
        self.assert_clean_browser(page); context.close()

    def test_timeline_import_errors_are_actionable(self):
        self.seed_timeline(name="已有项目")
        context, page = self.login("u1")
        self.open_timeline_home(page)
        stable = self.timeline_content_hash()
        commits = []
        page.on("request", lambda request: commits.append(request.url) if request.url.endswith("/timeline/imports/commit") else None)
        conflict = make_xlsx(self.timeline_headers(), [
            ["已有项目", "创意", "main", "A", "2026-08-01", "", "", ""],
            ["新项目", "设计", "main", "B", "2026-08-02", "", "", ""],
            ["已有项目", "测试", "parallel", "C", "2026-08-03", "", "", ""],
        ])
        self.upload_timeline(page, "conflict.xlsx", conflict, 422, "NAME_CONFLICT")
        error = page.locator('[data-timeline-import-error="NAME_CONFLICT"]')
        error.wait_for()
        self.assertEqual(error.locator("[data-import-error-row]").count(), 2)
        self.assertIn("已有项目", error.inner_text())
        self.assertFalse(page.locator("[data-timeline-import-commit]").is_enabled())
        invalids = (
            ("duplicate.xlsx", make_xlsx(self.timeline_headers(), [["重复", "创意", "main", "N", "2026-08-01", "", "", ""], ["重复", "创意", "main", "N", "2026-08-01", "", "", ""]]), "VALIDATION_ERROR", "第 2 行重复"),
            ("enum.xlsx", make_xlsx(self.timeline_headers(), [["枚举", "未知", "main", "N", "2026-08-01", "", "", ""]]), "VALIDATION_ERROR", "row"),
            ("date.xlsx", make_xlsx(self.timeline_headers(), [["日期", "创意", "main", "N", "not-a-date", "", "", ""]]), "VALIDATION_ERROR", "row"),
        )
        for filename, raw, code, marker in invalids:
            response = self.upload_timeline(page, filename, raw, 422, code)
            page.locator(f'[data-timeline-import-error="{code}"]').wait_for()
            self.assertFalse(page.locator("[data-timeline-import-commit]").is_enabled())
            self.assertIn(marker, json.dumps(response.json(), ensure_ascii=False))
        self.assertEqual(commits, [])
        self.assertEqual(self.timeline_content_hash(), stable)
        self.assert_clean_browser(page); context.close()

    def test_timeline_import_warnings_multisheet_and_csv_date(self):
        context, page = self.login("u1")
        self.open_timeline_home(page)
        raw = make_xlsx(self.timeline_headers(), [["多表项目", "创意", "main", "A", "2026-08-01", "", "未开始", ""]])
        self.upload_timeline(page, "multi.xlsx", self.two_sheet_xlsx(raw), 201)
        warnings = page.locator(".timeline-import-warnings")
        warnings.wait_for()
        self.assertIn("仅导入第一个 sheet", warnings.inner_text())
        self.assertIn("仅『已完成』保留", warnings.inner_text())
        csv_raw = (",".join(self.timeline_headers()) + "\nCSV日期,创意,main,A,46234,,,\n").encode()
        self.upload_timeline(page, "dates.csv", csv_raw, 422, "VALIDATION_ERROR")
        error = page.locator(".timeline-import-error")
        error.wait_for()
        self.assertIn("改用 .xlsx 导入", error.inner_text())
        self.assertFalse(page.locator("[data-timeline-import-commit]").is_enabled())
        self.assert_clean_browser(page); context.close()

    def test_timeline_import_status_warning_and_commit_gate(self):
        context, page = self.login("u1")
        self.open_timeline_home(page)
        stable = self.timeline_content_hash()
        commits = []
        page.on("request", lambda request: commits.append(request.url) if request.url.endswith("/timeline/imports/commit") else None)
        good = make_xlsx(self.timeline_headers(), [["状态项目", "创意", "main", "A", "2026-08-01", "", "已完成", ""]])
        self.upload_timeline(page, "status.xlsx", good, 201)
        self.assertIn("仅『已完成』保留", page.locator(".timeline-import-warnings").inner_text())
        self.assertTrue(page.locator("[data-timeline-import-commit]").is_enabled())
        invalid = make_xlsx(self.timeline_headers(), [["坏状态", "创意", "main", "A", "2026-08-01", "", "暂停", ""]])
        self.upload_timeline(page, "bad-status.xlsx", invalid, 422, "VALIDATION_ERROR")
        self.assertIn("已完成/未开始/进行中", page.locator(".timeline-import-error").inner_text())
        self.assertFalse(page.locator("[data-timeline-import-commit]").is_enabled())
        self.assertEqual(commits, [])
        self.assertEqual(self.timeline_content_hash(), stable)
        self.assert_clean_browser(page); context.close()

    def test_timeline_export_decodes_server_bytes_and_hash(self):
        self.seed_timeline(name="导出源项目")
        context, page = self.login("u1")
        self.open_timeline_home(page)
        responses = []
        page.on("response", lambda response: responses.append(response) if response.url.endswith("/timeline/export") else None)
        self.record_mouse_sequence(page, "[data-timeline-export]")
        with page.expect_response(lambda response: response.url.endswith("/timeline/export") and response.request.method == "POST"):
            self.physical_click(page, page.locator("[data-timeline-export]"))
        self.assertEqual(page.evaluate("window.__timelineClicks"), ["mousedown", "mouseup", "click"])
        link = page.locator("[data-timeline-download]")
        link.wait_for()
        exported = responses[-1].json()
        with page.expect_download() as pending:
            self.physical_click(page, link)
        download = pending.value
        raw = Path(download.path()).read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), exported["sha256"])
        self.assertEqual(parse_upload("timeline.xlsx", raw)["headers"], self.timeline_headers())
        self.assertIn(exported["sha256"], page.locator(".timeline-export-ready").inner_text())
        self.assert_clean_browser(page); context.close()

    def test_timeline_export_reimport_new_workspace(self):
        self.seed_timeline(name="跨空间往返")
        source_context, source = self.login("u1")
        self.open_timeline_home(source)
        with source.expect_response(lambda response: response.url.endswith("/timeline/export")):
            self.physical_click(source, source.locator("[data-timeline-export]"))
        link = source.locator("[data-timeline-download]"); link.wait_for()
        with source.expect_download() as pending:
            self.physical_click(source, link)
        raw = Path(pending.value.path()).read_bytes()
        source_context.close()
        context, page = self.login("u4")
        self.open_timeline_home(page)
        self.upload_timeline(page, "timeline.xlsx", raw, 201)
        self.assertIn("跨空间往返", page.locator(".timeline-project-summary").inner_text())
        self.assertEqual(self.commit_timeline(page).status, 201)
        page.locator(".timeline-import-success").wait_for()
        db = connect(self.db_path)
        try:
            project = db.execute("SELECT id FROM timeline_projects WHERE workspace_id=2 AND name='跨空间往返'").fetchone()
            self.assertIsNotNone(project)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM timeline_nodes WHERE project_id=?", (project["id"],)).fetchone()[0], 4)
        finally:
            db.close()
        self.assert_clean_browser(page); context.close()

    def test_timeline_import_file_safety_and_strict_headers(self):
        context, page = self.login("u1")
        self.open_timeline_home(page)
        stable = self.timeline_content_hash()
        headers = self.timeline_headers()
        valid = make_xlsx(headers, [["安全", "创意", "main", "N", "2026-08-01", "", "", ""]])
        formula = self.add_zip_entries(valid, {})
        source = zipfile.ZipFile(io.BytesIO(formula)); entries = {item.filename: source.read(item.filename) for item in source.infolist()}; source.close()
        sheet = entries["xl/worksheets/sheet1.xml"].decode().replace('<c r="A2" t="inlineStr"><is><t xml:space="preserve">安全</t></is></c>', '<c r="A2"><f>1+1</f><v>2</v></c>')
        entries["xl/worksheets/sheet1.xml"] = sheet
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as target:
            for name, content in entries.items(): target.writestr(name, content)
        boundary_rows = [[f"边界{i}", "创意", "main", "N", "2026-08-01", "x" * 10000 if i == 0 else "", "", ""] for i in range(1000)]
        self.upload_timeline(page, "boundary.xlsx", make_xlsx(headers, boundary_rows), 201)
        self.assertIn("1000 行", page.locator("[data-timeline-preview-id]").inner_text())
        self.assertTrue(page.locator("[data-timeline-import-commit]").is_enabled())
        self.assertEqual(self.timeline_content_hash(), stable)
        cases = [
            ("large.csv", b"x" * 1_500_001, "IMPORT_FILE_TOO_LARGE"),
            ("bomb.xlsx", self.add_zip_entries(valid, {"padding.bin": b"x" * 12_000_001}), "IMPORT_XLSX_BOMB"),
            ("rows.xlsx", make_xlsx(headers, [[f"P{i}", "创意", "main", "N", "2026-08-01", "", "", ""] for i in range(1001)]), "IMPORT_TOO_MANY_ROWS"),
            ("cell.xlsx", make_xlsx(headers, [["长格", "创意", "main", "N", "2026-08-01", "", "", "x" * 10001]]), "IMPORT_CELL_TOO_LONG"),
            ("formula.xlsx", output.getvalue(), "IMPORT_FORMULA_FORBIDDEN"),
            ("macro.xlsx", self.add_zip_entries(valid, {"xl/vbaProject.bin": b"macro"}), "IMPORT_XLSX_UNSAFE"),
            ("external.xlsx", self.add_zip_entries(valid, {"xl/externalLinks/externalLink1.xml": b"<x/>"}), "IMPORT_XLSX_UNSAFE"),
            ("headers.xlsx", make_xlsx(headers[::-1], [["", "", "", "", "2026-08-01", "main", "创意", "错序"]]), "IMPORT_HEADERS_MISMATCH"),
            ("duplicate-header.xlsx", make_xlsx([*headers[:-1], headers[-2]], [["重复表头", "创意", "main", "N", "2026-08-01", "", "", ""]]), "IMPORT_DUPLICATE_HEADER"),
        ]
        commits = []
        page.on("request", lambda request: commits.append(request.url) if request.url.endswith("/timeline/imports/commit") else None)
        for filename, raw, code in cases:
            self.upload_timeline(page, filename, raw, 422, code)
            page.locator(f'[data-timeline-import-error="{code}"]').wait_for()
            self.assertFalse(page.locator("[data-timeline-import-commit]").is_enabled(), filename)
            self.assertEqual(self.timeline_content_hash(), stable, filename)
        self.assertEqual(commits, [])
        self.assert_clean_browser(page); context.close()

    def test_timeline_journey_edit_submit_refresh_undo(self):
        project_id = self.seed_timeline(name="CP6 编辑提交撤销")
        context, page = self.login("u1")
        routes = []
        page.on("response", lambda response: routes.append((response.request.method, response.url, response.status)) if "/timeline" in response.url else None)
        self.physical_click(page, page.locator("#timelineBtn"))
        page.locator('[data-timeline-page="home"]').wait_for()
        self.physical_click(page, page.locator(f'[data-timeline-open="editor"][data-project-id="{project_id}"]'))
        row = page.locator('[data-editor-row="2"]'); row.wait_for()
        row.locator('[data-editor-field="done_at"]').select_option("true")
        self.assertEqual(page.locator('[data-timeline-draft-count]').inner_text(), "1 项草稿")
        with page.expect_response(lambda response: response.request.method == "POST" and response.url.endswith("/timeline/batches")) as submitted:
            self.physical_click(page, page.locator('[data-timeline-submit]'))
        self.assertEqual(submitted.value.status, 200)
        self.assertEqual(page.locator('[data-timeline-draft-count]').inner_text(), "0 项草稿")
        self.assertTrue(page.locator('[data-timeline-undo]').is_enabled())
        db = connect(self.db_path)
        try:
            self.assertIsNotNone(db.execute("SELECT done_at FROM timeline_nodes WHERE id=2 AND project_id=?", (project_id,)).fetchone()[0])
            self.assertEqual(db.execute("SELECT COUNT(*) FROM timeline_change_batches WHERE project_id=? AND change_kind!='undo'", (project_id,)).fetchone()[0], 1)
        finally:
            db.close()
        with page.expect_response(lambda response: response.request.method == "POST" and response.url.endswith("/timeline/batches/undo")) as undone:
            self.physical_click(page, page.locator('[data-timeline-undo]'))
        self.assertEqual(undone.value.status, 200)
        db = connect(self.db_path)
        try:
            self.assertIsNone(db.execute("SELECT done_at FROM timeline_nodes WHERE id=2 AND project_id=?", (project_id,)).fetchone()[0])
            self.assertEqual(db.execute("SELECT COUNT(*) FROM timeline_change_batches WHERE project_id=? AND change_kind='undo' AND undone_batch_id IS NOT NULL", (project_id,)).fetchone()[0], 1)
        finally:
            db.close()
        page.reload()
        self.physical_click(page, page.locator("#timelineBtn"))
        page.locator('[data-timeline-page="home"]').wait_for()
        self.physical_click(page, page.locator(f'[data-timeline-open="editor"][data-project-id="{project_id}"]'))
        self.assertNotIn("is-draft", page.locator('[data-editor-row="2"]').get_attribute("class") or "")
        self.assertFalse(page.locator('[data-timeline-undo]').is_enabled(), "undo lifetime must not survive refresh")
        self.assertEqual(sum(1 for method, url, status in routes if method == "POST" and url.endswith("/timeline/batches") and status == 200), 1)
        self.assertEqual(sum(1 for method, url, status in routes if method == "POST" and url.endswith("/timeline/batches/undo") and status == 200), 1)
        self.assert_clean_browser(page); context.close()

    def test_timeline_journey_dashboards(self):
        (project_id, _, _), today = self.seed_cp4_dashboard_projects()
        context, page = self.login("u1")
        requests = []
        page.on("request", lambda request: requests.append((request.method, request.url)))
        self.open_cp4_single(page, project_id)
        stable = self.timeline_content_hash()
        baseline = len(requests)
        card = page.locator(f'[data-dashboard-project="{project_id}"]')
        self.assertEqual(card.locator('[data-track="main"]').count(), 1)
        self.assertEqual(card.locator('[data-track="parallel"]').count(), 1)
        self.assertEqual(card.locator('.timeline-today-line').get_attribute("data-today"), today)
        self.assertIn("今天", card.locator('.timeline-today-line').inner_text())
        self.assertGreater(card.locator('[data-stage-interval]').count(), 0)
        self.physical_click(page, card.locator('[data-timeline-expand]').first)
        self.assertEqual(card.locator('[data-timeline-expand]').first.get_attribute("aria-expanded"), "true")
        node = card.locator('.timeline-dashboard-node').first
        self.physical_click(page, node, button="right")
        self.assertEqual(page.locator('[data-timeline-context] [role="menuitem"]').count(), 4)
        self.physical_click(page, page.locator('[data-timeline-context] [data-draft-action="done"]'))
        self.assertIn("尚未写入服务器", card.locator('[data-dashboard-hint]').inner_text())
        self.physical_click(page, page.locator('[data-timeline-mode-target="all"]'))
        page.locator('[data-timeline-page="all"] [data-dashboard-project]').first.wait_for()
        self.assertFalse(page.locator('.timeline-portfolio-head').is_hidden())
        self.assertFalse(page.locator('[data-portfolio-fullscreen]').is_hidden())
        self.assertTrue(page.locator('.tl-order-note').is_hidden())
        node = page.locator('[data-timeline-page="all"] .timeline-dashboard-node').first
        node_box = node.bounding_box()
        point = {"x": node_box["x"] + node_box["width"] / 2, "y": node_box["y"] + node_box["height"] / 2}
        self.assertIsNotNone(page.evaluate("point => document.elementFromPoint(point.x,point.y)?.closest('.timeline-dashboard-node')?.dataset.nodeId||null", point))
        self.physical_click(page, node, button="right")
        self.physical_click(page, page.locator('[data-timeline-page="all"] [data-draft-action="cascade"]'))
        self.assertEqual(len(requests), baseline, "dashboard journey must remain read-only")
        self.assertEqual(self.timeline_content_hash(), stable)
        self.assert_clean_browser(page); context.close()

    def test_timeline_journey_import_export_reimport(self):
        source_context, source = self.login("u1")
        routes = []
        source.on("response", lambda response: routes.append((response.request.method, response.url, response.status)) if "/timeline/" in response.url else None)
        self.open_timeline_home(source)
        source_before = self.timeline_content_hash()
        raw = make_xlsx(self.timeline_headers(), [
            ["CP6 往返项目", "创意", "main", "起点", "2026-08-01", "", "已完成", ""],
            ["CP6 往返项目", "设计", "parallel", "并行", "2026-08-03", "", "进行中", ""],
        ])
        self.upload_timeline(source, "cp6.xlsx", raw, 201)
        source.locator('.timeline-project-summary', has_text="CP6 往返项目").wait_for()
        self.assertEqual(self.commit_timeline(source).status, 201)
        source.locator('.timeline-import-success').wait_for()
        self.assertNotEqual(self.timeline_content_hash(), source_before)
        with source.expect_response(lambda response: response.request.method == "POST" and response.url.endswith("/timeline/export")) as exported_response:
            self.physical_click(source, source.locator('[data-timeline-export]'))
        self.assertEqual(exported_response.value.status, 200)
        download_link = source.locator('[data-timeline-download]'); download_link.wait_for()
        with source.expect_download() as pending:
            self.physical_click(source, download_link)
        exported = Path(pending.value.path()).read_bytes()
        self.assertEqual(hashlib.sha256(exported).hexdigest(), exported_response.value.json()["sha256"])
        self.assertEqual([status for method, url, status in routes if method == "POST" and url.endswith("/timeline/imports/preview")], [201])
        self.assertEqual([status for method, url, status in routes if method == "POST" and url.endswith("/timeline/imports/commit")], [201])
        self.assert_clean_browser(source); source_context.close()

        target_context, target = self.login("u4")
        target_routes = []
        target.on("response", lambda response: target_routes.append((response.request.method, response.url, response.status)) if "/timeline/" in response.url else None)
        self.open_timeline_home(target)
        target_before = self.timeline_content_hash()
        self.upload_timeline(target, "timeline.xlsx", exported, 201)
        self.assertIn("CP6 往返项目", target.locator('.timeline-project-summary').inner_text())
        self.assertEqual(self.commit_timeline(target).status, 201)
        target.locator('.timeline-import-success').wait_for()
        self.assertNotEqual(self.timeline_content_hash(), target_before)
        db = connect(self.db_path)
        try:
            project = db.execute("SELECT id FROM timeline_projects WHERE workspace_id=2 AND name='CP6 往返项目'").fetchone()
            self.assertIsNotNone(project)
            rows = list(db.execute("SELECT name,done_at FROM timeline_nodes WHERE project_id=? ORDER BY id", (project["id"],)))
            self.assertEqual([row["name"] for row in rows], ["起点", "并行"])
            self.assertIsNotNone(rows[0]["done_at"])
            self.assertIsNone(rows[1]["done_at"])
        finally:
            db.close()
        self.assertEqual([status for method, url, status in target_routes if method == "POST" and url.endswith("/timeline/imports/preview")], [201])
        self.assertEqual([status for method, url, status in target_routes if method == "POST" and url.endswith("/timeline/imports/commit")], [201])
        self.assert_clean_browser(target); target_context.close()

    def test_timeline_light_tokens_and_redundant_labels(self):
        (project_id, _, _), _today = self.seed_cp4_dashboard_projects()
        context, page = self.login("u1")
        self.open_cp4_single(page, project_id)
        card = page.locator(f'[data-dashboard-project="{project_id}"]')
        self.assertEqual(card.evaluate("node => getComputedStyle(node).backgroundColor"), "rgb(255, 255, 255)")
        self.assertEqual(card.locator(".timeline-dashboard-detail").evaluate("node => getComputedStyle(node).backgroundColor"), "rgb(245, 245, 247)")
        self.assertEqual(page.locator('[data-theme], [data-dark-mode], .theme-toggle').count(), 0)
        labels = set(card.locator('[data-stage-interval] b').all_inner_texts())
        self.assertTrue({"创意", "设计", "开发", "测试", "量产"}.issubset(labels))
        self.assertIn("今天", card.locator(".timeline-today-line").inner_text())
        self.assert_clean_browser(page); context.close()

    def test_v17_shared_tags_and_personal_all_order_real_drag(self):
        project_ids = [self.seed_timeline(name=f"v17 项目 {index}") for index in range(1, 4)]
        context, page = self.login("u1")
        page.locator("#timelineTagsBtn").click()
        page.locator('[data-tag-create] input[name="name"]').fill("喜爱")
        with page.expect_response(lambda response: response.request.method == "POST" and response.url.endswith("/timeline/tags")) as created:
            page.locator('[data-tag-create] button[type="submit"]').click()
        self.assertEqual(created.value.status, 201)
        page.locator('.tl-tag-workbench h2', has_text="喜爱").wait_for()
        source = page.locator(f'[data-tag-project="{project_ids[0]}"]')
        target = page.locator('[data-tag-drop="included"]')
        with page.expect_response(lambda response: response.request.method == "PUT" and "/timeline/tags/" in response.url and "/projects/" in response.url) as added:
            source.drag_to(target)
        self.assertEqual(added.value.status, 200)
        page.locator(f'[data-tag-drop="included"] [data-tag-project="{project_ids[0]}"]').wait_for()
        self.assertEqual(page.locator('[data-tag-undo]').count(), 1)

        page.locator("#timelineBtn").click()
        mine_rows = page.locator('[data-order-list="mine"] > [data-order-project]')
        mine_rows.first.wait_for()
        self.assertEqual(mine_rows.count(), 3)
        mine_before = [int(value) for value in mine_rows.evaluate_all("nodes => nodes.map(node => node.dataset.orderProject)")]
        with page.expect_response(lambda response: response.request.method == "PUT" and response.url.endswith("/timeline/order")) as mine_ordered:
            mine_rows.nth(2).locator('.tl-order-grip').drag_to(mine_rows.nth(0))
        self.assertEqual(mine_ordered.value.status, 200)
        mine_after = [int(value) for value in page.locator('[data-order-list="mine"] > [data-order-project]').evaluate_all("nodes => nodes.map(node => node.dataset.orderProject)")]
        self.assertEqual(mine_after[0], mine_before[2])
        page.reload(); page.locator("#timelineBtn").click()
        page.locator('[data-order-list="mine"]').wait_for()
        self.assertEqual([int(value) for value in page.locator('[data-order-list="mine"] > [data-order-project]').evaluate_all("nodes => nodes.map(node => node.dataset.orderProject)")], mine_after)

        page.locator("#timelineAllBtn").click()
        page.locator('[data-timeline-tag-context="all"]').click()
        page.locator('.timeline-portfolio-chart').wait_for()
        self.assertEqual(page.locator('.timeline-portfolio-chart').count(), 1)
        rows = page.locator('[data-order-list="all"] > [data-order-project]')
        self.assertEqual(rows.count(), 3)
        before = [int(value) for value in rows.evaluate_all("nodes => nodes.map(node => node.dataset.orderProject)")]
        source_grip = rows.nth(2).locator('.tl-order-grip')
        page.evaluate("""window.__orderDragEvents=[];for(const type of ['dragstart','dragover','drop','dragend'])document.querySelector('#timelineBody').addEventListener(type,event=>{if(event.target.closest('.tl-order-grip,[data-order-list]'))window.__orderDragEvents.push(type)},true)""")
        with page.expect_response(lambda response: response.request.method == "PUT" and response.url.endswith("/timeline/order")) as ordered:
            source_grip.drag_to(rows.nth(0))
        self.assertEqual(ordered.value.status, 200)
        page.locator("#toast", has_text="你的项目顺序已保存").wait_for()
        after = [int(value) for value in page.locator('[data-order-list="all"] > [data-order-project]').evaluate_all("nodes => nodes.map(node => node.dataset.orderProject)")]
        self.assertEqual(after[0], before[2])
        events = page.evaluate("window.__orderDragEvents")
        self.assertEqual(events[0], "dragstart")
        self.assertIn("drop", events)
        self.assertEqual(events[-1], "dragend")
        requests = []
        page.on("request", lambda request: requests.append(request.url) if request.method == "PUT" and request.url.endswith("/timeline/order") else None)
        node = page.locator('.timeline-dashboard-node').first
        node_box = node.bounding_box(); row_box = page.locator('[data-order-list="all"] > [data-order-project]').nth(1).bounding_box()
        page.mouse.move(node_box["x"] + node_box["width"] / 2, node_box["y"] + node_box["height"] / 2)
        page.mouse.down(); page.mouse.move(row_box["x"] + 20, row_box["y"] + 8, steps=10); page.mouse.up(); page.wait_for_timeout(250)
        self.assertEqual(requests, [], "timeline node/row content must not start personal order drag")
        self.assert_clean_browser(page); context.close()

        member_context, member_page = self.login("u2")
        member_page.locator("#timelineAllBtn").click()
        member_page.locator('.timeline-portfolio-chart').wait_for()
        member_order = [int(value) for value in member_page.locator('[data-order-list="all"] > [data-order-project]').evaluate_all("nodes => nodes.map(node => node.dataset.orderProject)")]
        self.assertEqual(member_order, project_ids)
        self.assertNotEqual(member_order, after)
        self.assert_clean_browser(member_page); member_context.close()


if __name__ == "__main__":
    unittest.main()
