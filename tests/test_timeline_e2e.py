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
        page.locator('[data-timeline-page="editor"] h2', has_text="浏览器项目").wait_for()
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
        page.locator('[data-timeline-page="editor"] h2', has_text="成员项目").wait_for()
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

    def test_timeline_cp2_local_draft_real_mouse_drag_context_and_discard(self):
        project_id = self.seed_timeline()
        context, page = self.login("u1")
        requests = []
        page.on("request", lambda request: requests.append((request.method, request.url)))
        self.physical_click(page, page.locator("#timelineBtn"))
        page.locator('[data-timeline-page="home"]').wait_for()
        self.physical_click(page, page.locator(f'[data-timeline-open="editor"][data-project-id="{project_id}"]'))
        page.locator('[data-timeline-page="editor"] .timeline-node').first.wait_for()
        baseline = len(requests)

        first = page.locator('.timeline-node[data-node-date="2026-08-01"]')
        page.evaluate("""() => { window.__timelineContextEvents=[]; const n=document.querySelector('.timeline-node[data-node-date="2026-08-01"]'); for(const type of ['mousedown','mouseup','contextmenu']) n.addEventListener(type,e=>window.__timelineContextEvents.push(e.type)) }""")
        self.physical_click(page, first, button="right")
        self.assertEqual(page.evaluate("window.__timelineContextEvents"), ["mousedown", "mouseup", "contextmenu"])
        menu = page.locator('[data-timeline-context]')
        self.assertFalse(menu.is_hidden())
        self.assertEqual(menu.locator('[role="menuitem"]').all_inner_texts(), ["拖拽—仅此节点", "拖拽（顺延）", "已完成", "未完成"])
        self.record_mouse_sequence(page, '[data-draft-action="cascade"]')
        self.physical_click(page, menu.locator('[data-draft-action="cascade"]'))
        self.assertEqual(page.evaluate("window.__timelineClicks"), ["mousedown", "mouseup", "click"])
        first = page.locator('.timeline-node[data-node-date="2026-08-01"]')
        page.evaluate("""() => { window.__timelineDragEvents=[]; const n=document.querySelector('.timeline-node[data-node-date="2026-08-01"]'); n.addEventListener('mousedown',e=>window.__timelineDragEvents.push(e.type)); document.addEventListener('mouseup',e=>window.__timelineDragEvents.push(e.type),{once:true}) }""")
        box = first.bounding_box()
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.mouse.down()
        page.mouse.move(box["x"] + box["width"] / 2 + 170, box["y"] + box["height"] / 2, steps=8)
        self.assertFalse(page.locator('.timeline-zoom-band').is_hidden())
        page.mouse.up()
        self.assertEqual(page.evaluate("window.__timelineDragEvents"), ["mousedown", "mouseup"])
        page.locator('[data-timeline-draft-count]', has_text="3 项草稿").wait_for()
        self.assertEqual(len(requests), baseline, "context selection and dragging must stay local")
        shifted = page.locator('.timeline-node[data-node-id="2"]').get_attribute("data-node-date")

        second_box = page.locator('.timeline-node[data-node-id="2"]').bounding_box()
        page.mouse.move(second_box["x"] + 5, second_box["y"] + 5)
        page.mouse.down(); page.mouse.move(second_box["x"] + 90, second_box["y"] + 5); page.mouse.up()
        self.assertEqual(page.locator('.timeline-node[data-node-id="2"]').get_attribute("data-node-date"), shifted, "mode is consumed after one drag")

        second = page.locator('.timeline-node[data-node-id="2"]')
        self.physical_click(page, second, button="right")
        self.physical_click(page, menu.locator('[data-draft-action="done"]'))
        self.assertEqual(page.locator('[data-timeline-draft-count]').inner_text(), "3 项草稿")
        self.physical_click(page, page.locator('[data-timeline-sort="stage"]'))
        self.assertEqual(page.locator('[data-timeline-sort="stage"]').get_attribute("aria-pressed"), "true")
        self.assertEqual(len(requests), baseline)

        page.on("dialog", lambda dialog: dialog.dismiss())
        self.physical_click(page, page.locator('[data-timeline-mode-target="home"]'))
        self.assertEqual(page.locator('[data-timeline-page="editor"]').count(), 1, "dismissed leave warning preserves editor draft")
        self.physical_click(page, page.locator('[data-timeline-discard]'))
        self.assertEqual(page.locator('[data-timeline-draft-count]').inner_text(), "0 项草稿")
        self.assertEqual(page.locator('.timeline-node[data-node-id="1"]').get_attribute("data-node-date"), "2026-08-01")

        page.evaluate("""() => { const b=document.createElement('button'); b.id='timeline-swallow-canary'; b.textContent='canary'; b.addEventListener('mousedown',()=>b.hidden=true); b.addEventListener('click',()=>window.__swallowedClick=true); document.body.appendChild(b); window.__swallowedClick=false }""")
        canary = page.locator('#timeline-swallow-canary')
        canary_box = canary.bounding_box()
        page.mouse.move(canary_box["x"] + 3, canary_box["y"] + 3); page.mouse.down(); page.mouse.up()
        self.assertFalse(page.evaluate("window.__swallowedClick"), "canary must detect a target hidden on mousedown swallowing click")
        self.assert_clean_browser(page)
        context.close()

    def test_timeline_cp3_submit_mixed_batch_refresh_review_correction_and_undo(self):
        project_id = self.seed_timeline()
        context, page = self.login("u1")
        batch_requests = []
        page.on("request", lambda request: batch_requests.append(request.post_data_json) if request.method == "POST" and request.url.endswith("/timeline/batches") else None)
        page.locator("#timelineBtn").click()
        page.locator(f'[data-timeline-open="editor"][data-project-id="{project_id}"]').click()
        page.locator('[data-timeline-page="editor"] .timeline-node').first.wait_for()

        first = page.locator('.timeline-node[data-node-date="2026-08-01"]')
        self.physical_click(page, first, button="right")
        self.physical_click(page, page.locator('[data-draft-action="cascade"]'))
        first = page.locator('.timeline-node[data-node-date="2026-08-01"]')
        box = first.bounding_box()
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.mouse.down(); page.mouse.move(box["x"] + box["width"] / 2 + 170, box["y"] + box["height"] / 2, steps=8); page.mouse.up()
        self.physical_click(page, page.locator('.timeline-node[data-node-id="2"]'), button="right")
        self.physical_click(page, page.locator('[data-draft-action="done"]'))
        self.assertEqual(page.locator('[data-timeline-context] [role="menuitem"]').count(), 4)
        self.physical_click(page, page.locator('[data-timeline-remove-last]'))

        answers = iter(["CP3 新节点", "2026-08-15", "测试", "parallel"])
        def answer_add(dialog): dialog.accept(next(answers))
        page.on("dialog", answer_add)
        self.physical_click(page, page.locator('[data-timeline-add]'))
        page.remove_listener("dialog", answer_add)
        page.locator('.timeline-node', has_text="测试 · 2026-08-15").wait_for()
        with page.expect_response(lambda response: response.request.method == "POST" and response.url.endswith("/timeline/batches")) as submitted:
            self.physical_click(page, page.locator('[data-timeline-submit]'))
        self.assertEqual(submitted.value.status, 200)
        self.assertEqual(len(batch_requests), 1, "update button must issue exactly one batch POST")
        request = batch_requests[0]["requests"][0]
        self.assertEqual((request["details"]["mode"], request["details"]["magnet"], request["details"]["zoom_band"]), ("cascade", "standard", "±10d×8"))
        self.assertTrue(any("date" in row.get("set", {}) for row in request["changes"]))
        self.assertTrue(any("done_at" in row.get("set", {}) for row in request["changes"]))
        self.assertTrue(any("create" in row for row in request["changes"]))
        self.assertTrue(any(row.get("remove") for row in request["changes"]))
        with page.expect_response(lambda response: response.url.endswith("/timeline/batches/undo")) as undone:
            self.physical_click(page, page.locator('[data-timeline-undo]'))
        self.assertEqual(undone.value.status, 200)
        db = connect(self.db_path)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM timeline_nodes WHERE project_id=? AND deleted_at IS NULL", (project_id,)).fetchone()[0], 4)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM timeline_nodes WHERE project_id=? AND name='CP3 新节点' AND deleted_at IS NULL", (project_id,)).fetchone()[0], 0)
        db.close()

        self.physical_click(page, page.locator('.timeline-node[data-node-id="2"]'), button="right")
        self.physical_click(page, page.locator('[data-draft-action="done"]'))
        with page.expect_response(lambda response: response.request.method == "POST" and response.url.endswith("/timeline/batches")) as persisted:
            self.physical_click(page, page.locator('[data-timeline-submit]'))
        self.assertEqual(persisted.value.status, 200)
        page.reload(); page.locator("#timelineBtn").click(); page.locator(f'[data-timeline-open="editor"][data-project-id="{project_id}"]').click()
        page.locator('.timeline-node[data-node-id="2"]').wait_for()
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
        page.locator('.timeline-node[data-node-id="2"]').wait_for()
        self.physical_click(page, page.locator('.timeline-node[data-node-id="2"]'), button="right")
        self.physical_click(page, page.locator('[data-draft-action="done"]'))
        db = connect(self.db_path)
        db.execute("UPDATE timeline_projects SET version=2 WHERE id=?", (project_id,)); db.commit(); db.close()
        stable = self.timeline_content_hash()
        with page.expect_response(lambda response: response.request.method == "POST" and response.url.endswith("/timeline/batches")) as conflict:
            self.physical_click(page, page.locator('[data-timeline-submit]'))
        self.assertEqual(conflict.value.status, 409)
        page.locator("#toast", has_text="已显示服务端最新时间线").wait_for()
        self.assertEqual(page.locator('[data-timeline-draft-count]').inner_text(), "0 项草稿")
        self.assertEqual(self.timeline_content_hash(), stable, "409 must write no timeline content")
        self.assertEqual(page.locator('[data-timeline-page="editor"] .timeline-node').count(), 4)
        self.assertTrue(any("409" in message for message in page.flowboard_console_errors))
        page.flowboard_console_errors.clear()
        self.assert_clean_browser(page); context.close()

        member_project_id = self.seed_timeline(created_by="u2", name="成员纠正项目")
        member_context, member_page = self.login("u2")
        member_page.locator("#timelineBtn").click(); member_page.locator(f'[data-timeline-open="editor"][data-project-id="{member_project_id}"]').click()
        member_page.locator('.timeline-node').first.wait_for()
        member_page.on("dialog", lambda dialog: dialog.accept("2026-07-20"))
        member_stable = self.timeline_content_hash()
        with member_page.expect_response(lambda response: response.url.endswith("/timeline/batches/initial-correction")) as denied:
            self.physical_click(member_page, member_page.locator('[data-timeline-correct]'))
        self.assertEqual(denied.value.status, 403)
        self.assertEqual(denied.value.json()["error"]["code"], "ADMIN_REQUIRED")
        self.assertEqual(self.timeline_content_hash(), member_stable)
        member_page.locator("#toast", has_text="仅管理员可纠正初始日期").wait_for()
        self.assertTrue(any("403" in message for message in member_page.flowboard_console_errors))
        member_page.flowboard_console_errors.clear()
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
        cards = page.locator("[data-dashboard-project]")
        starts = cards.locator("[data-calendar-start]").evaluate_all("nodes => nodes.map(node => node.dataset.calendarStart)")
        ends = cards.locator("[data-calendar-end]").evaluate_all("nodes => nodes.map(node => node.dataset.calendarEnd)")
        self.assertEqual(len(set(starts)), 1)
        self.assertEqual(len(set(ends)), 1)
        self.assertEqual(set(cards.locator(".timeline-today-line").evaluate_all("nodes => nodes.map(node => node.dataset.today)")), {today})
        self.assertTrue(all("今天" in text for text in cards.locator(".timeline-today-line span").all_inner_texts()))
        self.assertEqual(cards.locator(".timeline-today-line").first.evaluate("node => getComputedStyle(node).backgroundColor"), "rgb(229, 72, 77)")
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
        sort = page.locator('[data-timeline-sort-key]')
        self.physical_click(page, sort)
        page.keyboard.press("End")
        page.keyboard.press("Enter")
        page.locator('[data-timeline-sort-key]').wait_for()
        self.assertEqual(page.locator('[data-timeline-sort-key]').input_value(), "overdue")
        order = page.locator('[data-dashboard-project]').evaluate_all("nodes => nodes.map(node => Number(node.dataset.dashboardProject))")
        self.assertEqual(order[0], project_id, "overdue sort must put the largest count first")
        project_filter = page.locator('[data-timeline-filter]')
        box = project_filter.bounding_box()
        page.mouse.move(box["x"] + 15, box["y"] + 10); page.mouse.down(); page.mouse.up()
        page.locator('[data-timeline-filter]').wait_for()
        self.assertEqual(page.locator('[data-dashboard-project]').count(), 1)
        filtered_node = page.locator('[data-timeline-page="all"] .timeline-dashboard-node').first
        expected_node = filtered_node.get_attribute("data-node-id")
        node_box = filtered_node.bounding_box()
        center = {"x": node_box["x"] + node_box["width"] / 2, "y": node_box["y"] + node_box["height"] / 2}
        self.assertEqual(page.evaluate("point => document.elementFromPoint(point.x, point.y)?.closest('.timeline-dashboard-node')?.dataset.nodeId || null", center), expected_node, "sort/filter rerender must preserve the node's center hit target")
        page.evaluate("""() => { window.__filteredDashboardHits=[]; for (const type of ['mousedown','mouseup','contextmenu']) document.addEventListener(type,event=>window.__filteredDashboardHits.push({type,node:event.target.closest('.timeline-dashboard-node')?.dataset.nodeId||null}),{capture:true,once:true}) }""")
        self.physical_click(page, filtered_node, button="right")
        self.assertEqual(page.evaluate("window.__filteredDashboardHits"), [{"type":"mousedown","node":expected_node},{"type":"mouseup","node":expected_node},{"type":"contextmenu","node":expected_node}])
        self.assertFalse(page.locator('[data-timeline-page="all"] [data-timeline-context]').is_hidden())
        self.physical_click(page, page.locator('[data-timeline-page="all"] [data-draft-action="done"]'))
        self.assertEqual(filtered_node.get_attribute("data-dashboard-action"), "done")
        self.assertIn("is-context-target", filtered_node.get_attribute("class"))
        self.assertEqual(len(requests), baseline, "filter and sort stay client-side")
        self.assertEqual(self.timeline_content_hash(), stable_hash)
        self.assertEqual(page.locator('[data-timeline-sort-key] option').count(), 4)
        self.assert_clean_browser(page); context.close()

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
        node = page.locator('.timeline-node[data-node-id="2"]'); node.wait_for()
        self.physical_click(page, node, button="right")
        self.physical_click(page, page.locator('[data-draft-action="done"]'))
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
        self.assertFalse(page.locator('.timeline-node[data-node-id="2"]').get_attribute("class").endswith("is-draft"))
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
        sort = page.locator('[data-timeline-sort-key]')
        self.physical_click(page, sort); page.keyboard.press("End"); page.keyboard.press("Enter")
        self.assertEqual(page.locator('[data-timeline-sort-key]').input_value(), "overdue")
        project_filter = page.locator('[data-timeline-filter]')
        filter_box = project_filter.bounding_box()
        page.mouse.move(filter_box["x"] + 12, filter_box["y"] + 10); page.mouse.down(); page.mouse.up()
        page.locator('[data-timeline-filter]').wait_for()
        self.assertEqual(page.locator('[data-dashboard-project]').count(), 1)
        filtered = page.locator('[data-timeline-page="all"] .timeline-dashboard-node').first
        filtered_box = filtered.bounding_box()
        point = {"x": filtered_box["x"] + filtered_box["width"] / 2, "y": filtered_box["y"] + filtered_box["height"] / 2}
        self.assertIsNotNone(page.evaluate("point => document.elementFromPoint(point.x,point.y)?.closest('.timeline-dashboard-node')?.dataset.nodeId||null", point))
        self.physical_click(page, filtered, button="right")
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


if __name__ == "__main__":
    unittest.main()
