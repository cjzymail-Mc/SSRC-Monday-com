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

    def extend_cp4_stage_intervals(self, project_id):
        """Give the interval-visual tests positive-width, boundary-overlapping runs."""
        today = datetime.now(timezone(timedelta(hours=8))).date()
        day_one = (today + timedelta(days=1)).isoformat()
        day_two = (today + timedelta(days=2)).isoformat()
        now = datetime.now(timezone.utc).isoformat()
        db = connect(self.db_path)
        try:
            for name in ("主线重叠二", "并行重叠二"):
                db.execute(
                    "UPDATE timeline_nodes SET date=?,initial_date=? WHERE project_id=? AND name=?",
                    (day_one, day_one, project_id, name),
                )
            for track, stage, name, value in (
                ("main", "设计", "主线重叠一续", day_one),
                ("main", "开发", "主线重叠二续", day_two),
                ("parallel", "测试", "并行重叠一续", day_one),
                ("parallel", "量产", "并行重叠二续", day_two),
            ):
                db.execute(
                    "INSERT INTO timeline_nodes(project_id,track,stage,name,date,initial_date,remark,version,created_at,updated_at) VALUES (?,?,?,?,?,?,'',1,?,?)",
                    (project_id, track, stage, name, value, value, now, now),
                )
            db.commit()
        finally:
            db.close()

    def open_cp4_single(self, page, project_id):
        self.physical_click(page, page.locator("#timelineBtn"))
        page.locator('[data-timeline-page="home"]').wait_for()
        self.physical_click(page, page.locator(f'[data-timeline-open="single"][data-project-id="{project_id}"]'))
        page.locator(f'[data-timeline-page="single"] [data-dashboard-project="{project_id}"]').wait_for()

    def zoom_single_until_node_visible(self, page):
        scroll = page.locator('[data-timeline-page="single"] [data-portfolio-scroll]')
        axis = scroll.locator('.timeline-portfolio-axis-detail')
        for _ in range(8):
            if scroll.locator('.timeline-dashboard-node').count():
                return
            box = axis.bounding_box()
            page.mouse.move(box["x"] + box["width"] * .45, box["y"] + box["height"] * .65)
            page.mouse.wheel(0, -120)
            page.wait_for_timeout(80)
        self.assertGreater(scroll.locator('.timeline-dashboard-node').count(), 0)

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
    def timeline_export_headers():
        return ["项目名称", "阶段", "主线/并行", "节点", "日期", "状态", "备注"]

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
        if page.locator('#timelineModal [data-timeline-import-file]').count() == 0:
            self.physical_click(page, page.locator('[data-timeline-import-open]'))
            page.locator('#timelineModal [data-timeline-import-file]').wait_for()
        predicate = lambda response: response.url.endswith("/timeline/imports/preview") and response.request.method == "POST"
        with page.expect_response(predicate) as pending:
            page.locator("#timelineModal [data-timeline-import-file]").set_input_files({"name": filename, "mimeType": "text/csv" if filename.endswith(".csv") else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "buffer": raw})
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

    def test_week_and_month_are_shared_portfolio_scopes(self):
        today = datetime.now(timezone(timedelta(hours=8))).date()
        month_start = today.replace(day=1)
        month_end = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
        db = connect(self.db_path)
        try:
            now = datetime.now(timezone.utc).isoformat()
            for name, done_at in (("范围活跃项目", None), ("范围内仅完成项目", now)):
                project = db.execute("INSERT INTO timeline_projects(workspace_id,name,created_by,version,created_at,updated_at) VALUES (1,?,'u1',1,?,?)", (name, now, now))
                value = today.isoformat()
                db.execute("INSERT INTO timeline_nodes(project_id,track,stage,name,date,initial_date,done_at,remark,created_at,updated_at) VALUES (?,'main','设计','范围节点',?,?,?,'',?,?)", (project.lastrowid, value, value, done_at, now, now))
            db.commit()
        finally:
            db.close()

        context, page = self.login("u1")
        nav_ids = page.locator(".main-nav > button").evaluate_all("items => items.map(item => item.id)")
        self.assertLess(nav_ids.index("timelineBtn"), nav_ids.index("timelineWeekBtn"))
        self.assertLess(nav_ids.index("timelineWeekBtn"), nav_ids.index("timelineMonthBtn"))
        self.assertLess(nav_ids.index("timelineMonthBtn"), nav_ids.index("timelineAllBtn"))
        self.assertTrue(page.locator("#timelineWeekBtn").evaluate("el => el.classList.contains('nav-child')"))
        self.assertTrue(page.locator("#timelineMonthBtn").evaluate("el => el.classList.contains('nav-child')"))

        self.physical_click(page, page.locator("#timelineMonthBtn"))
        chart = page.locator('[data-timeline-page="month"] .timeline-portfolio-chart')
        chart.wait_for()
        self.assertEqual(chart.get_attribute("data-calendar-start"), month_start.isoformat())
        self.assertEqual(chart.get_attribute("data-calendar-end"), month_end.isoformat())
        self.assertEqual(float(chart.get_attribute("data-full-days")), float((month_end - month_start).days))
        self.assertEqual(float(chart.get_attribute("data-viewport-days")), float((month_end - month_start).days))
        self.assertEqual(page.locator('.timeline-portfolio-meta strong', has_text="范围活跃项目").count(), 1)
        self.assertEqual(page.locator('.timeline-portfolio-meta strong', has_text="范围内仅完成项目").count(), 0)
        month_row = page.locator('[data-timeline-page="month"] .timeline-portfolio-project', has_text="范围活跃项目")
        self.assertEqual(month_row.locator('.timeline-node-flag').count(), 0)
        self.physical_click(page, month_row.locator('.timeline-portfolio-meta strong'))
        self.assertEqual(month_row.locator('.timeline-node-flag').count(), 1)
        month_flag = month_row.locator('.timeline-node-flag').first
        self.physical_click(page, month_flag, button="right")
        month_flag_menu = page.locator('[data-timeline-page="month"] [data-timeline-context]')
        month_flag_menu.wait_for(state="visible")
        self.assertEqual(month_flag_menu.get_attribute('data-node-id'), month_flag.get_attribute('data-node-id'))
        self.assertEqual(month_flag_menu.get_attribute('data-project-id'), month_flag.get_attribute('data-project-id'))
        page.keyboard.press('Escape')
        month_flag_menu.wait_for(state="hidden")
        page.locator('[data-portfolio-zoom-out]').evaluate("el => el.click()")
        self.assertEqual(float(chart.get_attribute("data-viewport-days")), float((month_end - month_start).days), "month view must not zoom beyond its month")
        page.locator('[data-portfolio-zoom-in]').evaluate("el => el.click()")
        page.wait_for_function("full => Number(document.querySelector('[data-timeline-page=month] .timeline-portfolio-chart').dataset.viewportDays) < full", arg=(month_end - month_start).days)
        page.locator('[data-portfolio-cancel-zoom]').wait_for(state="visible")
        self.physical_click(page, page.locator('[data-portfolio-cancel-zoom]'))
        page.wait_for_function("full => Number(document.querySelector('[data-timeline-page=month] .timeline-portfolio-chart').dataset.viewportDays) === full", arg=(month_end - month_start).days)

        self.physical_click(page, page.locator("#timelineWeekBtn"))
        page.locator('[data-timeline-page="week"] .timeline-portfolio-chart').wait_for()
        self.assertEqual(page.locator('[data-timeline-page="week"] [data-portfolio-zoom-in]').count(), 0)
        self.assertEqual(page.locator('.timeline-portfolio-meta strong', has_text="范围活跃项目").count(), 1)
        self.assertEqual(page.locator('.timeline-portfolio-meta strong', has_text="范围内仅完成项目").count(), 0)
        week_row = page.locator('[data-timeline-page="week"] .timeline-portfolio-project', has_text="范围活跃项目")
        self.assertEqual(week_row.locator('.timeline-node-flag').count(), 0)
        self.physical_click(page, week_row.locator('.timeline-portfolio-meta strong'))
        week_node = week_row.locator('.timeline-dashboard-node').first
        week_key = week_node.get_attribute('data-node-flag-key')
        week_node.hover()
        self.assertTrue(week_row.locator(
            f'.timeline-node-flag[data-node-flag-key="{week_key}"]'
        ).evaluate("el => el.classList.contains('is-probed')"))
        week_flag = week_row.locator(f'.timeline-node-flag[data-node-flag-key="{week_key}"]')
        week_probe = week_row.locator(f'.timeline-node-flag-hit.is-active[data-node-flag-key="{week_key}"]')
        week_flag_target = week_probe if week_probe.is_visible() else week_flag
        week_flag_target.scroll_into_view_if_needed()
        week_target_point = week_flag_target.evaluate("""target => {
          const rect = target.getBoundingClientRect();
          const left = Math.max(0, Math.ceil(rect.left));
          const right = Math.min(innerWidth - 1, Math.floor(rect.right));
          const top = Math.max(0, Math.ceil(rect.top));
          const bottom = Math.min(innerHeight - 1, Math.floor(rect.bottom));
          for (let y = top + 2; y <= bottom - 2; y += 2) {
            for (let x = left + 2; x <= right - 2; x += 2) {
              const owner = document.elementFromPoint(x, y)?.closest('.timeline-node-flag,.timeline-node-flag-hit');
              if (owner?.dataset.nodeFlagKey === target.dataset.nodeFlagKey) return {x, y};
            }
          }
          return {x: null, y: null, rect: {left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom}, viewport: {width: innerWidth, height: innerHeight}};
        }""")
        self.assertIsNotNone(week_target_point["x"], week_target_point)
        page.mouse.move(week_target_point["x"], week_target_point["y"])
        self.assertEqual(page.evaluate("point => document.elementFromPoint(point.x, point.y)?.closest('.timeline-node-flag,.timeline-node-flag-hit')?.dataset.nodeFlagKey", week_target_point), week_key)
        page.mouse.down(button="right")
        page.mouse.up(button="right")
        week_flag_menu = page.locator('[data-timeline-page="week"] [data-timeline-context]')
        week_flag_menu.wait_for(state="visible")
        self.assertEqual(week_flag_menu.get_attribute('data-node-id'), week_node.get_attribute('data-node-id'))
        self.assertEqual(week_flag_menu.get_attribute('data-project-id'), week_node.get_attribute('data-project-id'))
        page.keyboard.press('Escape')
        week_flag_menu.wait_for(state="hidden")

        self.physical_click(page, page.locator("#timelineAllBtn"))
        page.locator('[data-timeline-page="all"] .timeline-portfolio-chart').wait_for()
        self.assertEqual(page.locator('.timeline-portfolio-meta strong', has_text="范围活跃项目").count(), 1)
        self.assertEqual(page.locator('.timeline-portfolio-meta strong', has_text="范围内仅完成项目").count(), 1)
        self.assert_clean_browser(page)
        context.close()

    def test_week_and_month_reorder_visible_subset_updates_full_personal_order(self):
        today = datetime.now(timezone(timedelta(hours=8))).date()
        next_month = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
        outside_scope = (next_month.replace(day=28) + timedelta(days=4)).replace(day=1)
        db = connect(self.db_path)
        try:
            now = datetime.now(timezone.utc).isoformat()
            project_ids = []
            for index, name in enumerate(("锚点 A", "锚点 B", "锚点 C", "锚点 D", "锚点 E")):
                project = db.execute(
                    "INSERT INTO timeline_projects(workspace_id,name,created_by,version,created_at,updated_at) VALUES (1,?,'u1',1,?,?)",
                    (name, now, now),
                )
                project_ids.append(project.lastrowid)
                node_date = today if index in (0, 2, 4) else outside_scope
                value = node_date.isoformat()
                db.execute(
                    "INSERT INTO timeline_nodes(project_id,track,stage,name,date,initial_date,remark,version,created_at,updated_at) VALUES (?,'main','设计',?,?,?,'',1,?,?)",
                    (project.lastrowid, f"节点 {name[-1]}", value, value, now, now),
                )
            db.commit()
        finally:
            db.close()

        def visible_ids():
            return [int(value) for value in page.locator('[data-order-list="all"] > [data-order-project]').evaluate_all(
                "nodes => nodes.map(node => node.dataset.orderProject)"
            )]

        def drag_before(source_id, target_id):
            source = page.locator(f'[data-order-list="all"] > [data-order-project="{source_id}"] .tl-order-grip')
            target = page.locator(f'[data-order-list="all"] > [data-order-project="{target_id}"]')
            source_box, target_box = source.bounding_box(), target.bounding_box()
            with page.expect_response(lambda response: response.request.method == "PUT" and response.url.endswith("/timeline/order")) as pending:
                page.mouse.move(source_box["x"] + source_box["width"] / 2, source_box["y"] + source_box["height"] / 2)
                page.mouse.down()
                page.mouse.move(target_box["x"] + target_box["width"] / 2, target_box["y"] + 2, steps=12)
                page.mouse.up()
            self.assertEqual(pending.value.status, 200)
            page.locator("#toast", has_text="你的项目顺序已保存").wait_for()
            return [int(value) for value in pending.value.json()["project_ids"]]

        a, b, c, d, e = project_ids
        context, page = self.login("u1")
        self.physical_click(page, page.locator("#timelineWeekBtn"))
        page.locator('[data-timeline-page="week"] .timeline-portfolio-chart').wait_for()
        self.assertEqual(visible_ids(), [a, c, e])

        saved = drag_before(e, a)
        self.assertEqual(saved, [e, a, b, c, d], "hidden projects keep their relative positions around the visible anchor")
        self.assertEqual(visible_ids(), [e, a, c], "week view must keep the saved order after rerender")

        self.physical_click(page, page.locator("#timelineAllBtn"))
        page.locator('[data-timeline-page="all"] .timeline-portfolio-chart').wait_for()
        self.assertEqual(visible_ids(), [e, a, b, c, d])

        self.physical_click(page, page.locator("#timelineMonthBtn"))
        page.locator('[data-timeline-page="month"] .timeline-portfolio-chart').wait_for()
        self.assertEqual(visible_ids(), [e, a, c])
        saved = drag_before(c, e)
        self.assertEqual(saved, [c, e, a, b, d])
        self.assertEqual(visible_ids(), [c, e, a], "month view must keep the saved order after rerender")

        self.physical_click(page, page.locator("#timelineAllBtn"))
        page.locator('[data-timeline-page="all"] .timeline-portfolio-chart').wait_for()
        self.assertEqual(visible_ids(), [c, e, a, b, d])
        self.assert_clean_browser(page)
        context.close()

    def test_admin_real_entry_modes_create_delete_and_refresh_persistence(self):
        context, page = self.login("u1")
        responses = []
        page.on("response", lambda response: responses.append((response.request.method, response.url, response.status)))
        self.record_mouse_sequence(page, "#timelineBtn")
        page.locator("#timelineBtn").click()
        page.locator('[data-timeline-page="home"]').wait_for()
        self.assertEqual(page.evaluate("window.__timelineClicks"), ["mousedown", "mouseup", "click"])

        self.physical_click(page, page.locator('[data-timeline-create-open]'))
        page.locator('#timelineModal [data-timeline-create]').wait_for()
        page.locator('#timelineModal input[name="name"]').fill("浏览器项目")
        page.locator('#timelineModal button[type="submit"]').click()
        page.locator('[data-timeline-page="editor"] > .timeline-project-card > header h2', has_text="浏览器项目").wait_for()
        self.assertTrue(any(method == "POST" and url.endswith("/api/workspaces/1/timeline/projects") and status == 201 for method, url, status in responses))
        self.assertTrue(any(method == "GET" and url.endswith("/api/workspaces/1/timeline") and status == 200 for method, url, status in responses))

        self.record_mouse_sequence(page, '[data-timeline-mode-target="single"]')
        page.locator('[data-timeline-mode-target="single"]').click()
        page.locator('[data-timeline-page="single"] > .timeline-project-card > header h2', has_text="浏览器项目").wait_for()
        self.assertEqual(page.evaluate("window.__timelineClicks"), ["mousedown", "mouseup", "click"])
        self.assertTrue(any(method == "GET" and "/api/timeline/projects/" in url and status == 200 for method, url, status in responses))
        page.locator('#timelineAllBtn').click()
        page.locator('[data-timeline-page="all"] .timeline-all').wait_for()

        page.reload()
        page.locator("#timelineBtn").click()
        page.locator('[data-timeline-page="home"]').wait_for()
        page.locator('[data-project-choice] strong', has_text="浏览器项目").wait_for()
        self.assertEqual(page.locator('.tl-home-head input[name="name"]').count(), 0)
        self.physical_click(page, page.locator('[data-timeline-create-open]'))
        duplicate_form = page.locator('#timelineModal [data-timeline-create]')
        duplicate_form.wait_for()
        self.assertEqual(duplicate_form.locator('input[name="name"]').get_attribute("maxlength"), "200")
        stable = self.timeline_content_hash()
        console_before = len(page.flowboard_console_errors)
        create_posts_before = len([item for item in responses if item[0] == "POST" and item[1].endswith("/api/workspaces/1/timeline/projects")])
        duplicate_form.locator('input[name="name"]').fill("  浏览器项目  ")
        self.physical_click(page, duplicate_form.locator('button[type="submit"]'))
        duplicate_form.locator('[data-timeline-create-error]', has_text="项目名称已存在").wait_for()
        page.wait_for_timeout(200)
        create_posts_after = len([item for item in responses if item[0] == "POST" and item[1].endswith("/api/workspaces/1/timeline/projects")])
        self.assertEqual(create_posts_after, create_posts_before, "known duplicate must be rejected before POST")
        self.assertEqual(page.flowboard_console_errors[console_before:], [])
        self.assertEqual(self.timeline_content_hash(), stable, "trimmed duplicate project create must write nothing")
        self.physical_click(page, duplicate_form.locator('[data-timeline-create-cancel]').last)

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

    def test_project_rename_is_inline_on_home_and_single_dashboard(self):
        project_id = self.seed_timeline(name="重命名前")
        context, page = self.login("u1")
        self.open_timeline_home(page)

        row = page.locator(f'[data-project-choice="{project_id}"]')
        row.wait_for()
        row.hover()
        self.physical_click(page, row.locator('[data-timeline-rename-start]'))
        home_form = row.locator('[data-project-rename-form]')
        home_form.wait_for()
        self.assertTrue(home_form.is_visible())
        self.assertEqual(page.locator('#timelineModal:not([hidden])').count(), 0)
        home_form.locator('input[name="name"]').fill("主页重命名")
        with page.expect_response(lambda response: response.request.method == "PATCH" and response.url.endswith(f"/timeline/projects/{project_id}")) as home_response:
            self.physical_click(page, home_form.locator('button[type="submit"]'))
        self.assertEqual(home_response.value.status, 200)
        page.locator(f'[data-project-choice="{project_id}"] strong', has_text="主页重命名").wait_for()

        self.physical_click(page, page.locator(f'[data-project-choice="{project_id}"] [data-timeline-open="single"]'))
        page.locator(f'[data-timeline-page="single"] [data-dashboard-project="{project_id}"]').wait_for()
        pencil = page.locator('[data-timeline-page="single"] [data-timeline-rename-start]')
        title_line = page.locator('[data-timeline-page="single"] .timeline-project-title-line')
        page.mouse.move(2, 2)
        page.wait_for_timeout(180)
        self.assertEqual(pencil.evaluate("element => getComputedStyle(element).opacity"), "0")
        title_line.hover()
        page.wait_for_timeout(180)
        self.assertEqual(pencil.evaluate("element => getComputedStyle(element).opacity"), "1")
        self.physical_click(page, pencil)
        single_form = page.locator('[data-timeline-page="single"] [data-project-rename-form]')
        single_form.wait_for()
        self.assertTrue(single_form.is_visible())
        self.assertEqual(page.locator('#timelineModal:not([hidden])').count(), 0)
        single_form.locator('input[name="name"]').fill("单项目现场重命名")
        with page.expect_response(lambda response: response.request.method == "PATCH" and response.url.endswith(f"/timeline/projects/{project_id}")) as single_response:
            self.physical_click(page, single_form.locator('button[type="submit"]'))
        self.assertEqual(single_response.value.status, 200)
        page.locator('[data-timeline-page="single"] > .timeline-project-card > header h2', has_text="单项目现场重命名").wait_for()

        db = connect(self.db_path)
        try:
            saved = db.execute("SELECT name,version FROM timeline_projects WHERE id=?", (project_id,)).fetchone()
            self.assertEqual((saved["name"], saved["version"]), ("单项目现场重命名", 3))
            self.assertEqual(db.execute("SELECT COUNT(*) FROM timeline_change_batches WHERE project_id=?", (project_id,)).fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM audit_log WHERE action_code='timeline.project_renamed' AND entity_id=?", (str(project_id),)).fetchone()[0], 2)
        finally:
            db.close()
        self.assert_clean_browser(page)
        context.close()

    def test_member_can_read_and_create_but_has_no_delete_control(self):
        context, page = self.login("u2")
        page.locator("#timelineBtn").click()
        page.locator('[data-timeline-page="home"]').wait_for()
        self.physical_click(page, page.locator('[data-timeline-create-open]'))
        page.locator('#timelineModal input[name="name"]').fill("成员项目")
        page.locator('#timelineModal button[type="submit"]').click()
        page.locator('[data-timeline-page="editor"] > .timeline-project-card > header h2', has_text="成员项目").wait_for()
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
        self.assertEqual(table.locator("thead th").all_inner_texts(), ["", "#", "项目阶段", "轨道", "项目节点", "日期", "时间间隔（天）", "状态", "备注", "操作"])
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

        leave_dialogs = []
        def handle_leave_dialog(dialog):
            leave_dialogs.append(dialog.message)
            if len(leave_dialogs) == 1:
                dialog.dismiss()
            else:
                dialog.accept()
        page.on("dialog", handle_leave_dialog)
        self.physical_click(page, page.locator('[data-timeline-mode-target="home"]'))
        self.assertEqual(page.locator('[data-timeline-page="editor"]').count(), 1, "dismissed leave warning preserves table draft")
        self.physical_click(page, page.locator('[data-timeline-mode-target="home"]'))
        page.locator('[data-timeline-page="home"]').wait_for()
        self.assertEqual(leave_dialogs, ['有尚未提交的项目时间表草稿，确定放弃并离开？'] * 2)
        self.physical_click(page, page.locator(f'[data-timeline-open="editor"][data-project-id="{project_id}"]'))
        page.locator('[data-timeline-page="editor"] .timeline-sheet').wait_for()
        self.assertEqual(page.locator('[data-timeline-draft-count]').inner_text(), "0 项草稿")
        self.assertEqual(page.locator('[data-editor-field="date"][data-node-id="1"]').input_value(), "2026-08-01")
        self.assertEqual(page.locator('[data-editor-field="track"][data-node-id="2"]').input_value(), "main")
        self.physical_click(page, page.locator('[data-timeline-mode-target="home"]'))
        page.locator('[data-timeline-page="home"]').wait_for()
        self.assertEqual(len(leave_dialogs), 2, "accepted discard clears the draft so later navigation does not prompt again")
        self.assert_clean_browser(page)
        context.close()

    def test_timeline_editor_batch_c_stage_track_status_delete_save_and_undo(self):
        project_id = self.seed_timeline()
        context, page = self.login("u1")
        batch_requests = []
        page.on("request", lambda request: batch_requests.append(request.post_data_json) if request.method == "POST" and request.url.endswith("/timeline/batches") else None)
        page.locator("#timelineBtn").click()
        page.locator(f'[data-timeline-open="editor"][data-project-id="{project_id}"]').click()
        table = page.locator('[data-timeline-page="editor"] .timeline-sheet')
        table.wait_for()
        dock = page.locator('[data-editor-batch-dock]')
        self.assertTrue(dock.is_hidden())
        self.assertEqual(table.locator('[data-editor-select-node]').count(), 4)

        table.locator('[data-editor-select-all]').check()
        self.assertEqual(dock.locator('[data-editor-batch-count]').inner_text(), "4")
        self.assertTrue(table.locator('[data-editor-select-all]').is_checked())
        table.locator('[data-editor-select-all]').uncheck()
        self.assertTrue(dock.is_hidden())

        table.locator('[data-editor-select-node="2"]').check()
        self.physical_click(page, page.locator('[data-timeline-add]'))
        single_insert_rows = page.locator('[data-editor-row]').evaluate_all("rows => rows.map(row => row.dataset.editorRow)")
        single_anchor_index = single_insert_rows.index("2")
        self.assertTrue(int(single_insert_rows[single_anchor_index + 1]) < 0, "single selection inserts directly below its node")
        self.physical_click(page, page.locator('[data-timeline-discard]'))
        table = page.locator('[data-timeline-page="editor"] .timeline-sheet')
        dock = page.locator('[data-editor-batch-dock]')

        table.locator('[data-editor-select-node="1"]').check()
        table.locator('[data-editor-select-node="3"]').check()
        self.physical_click(page, page.locator('[data-timeline-add]'))
        inserted_rows = page.locator('[data-editor-row]').evaluate_all("rows => rows.map(row => row.dataset.editorRow)")
        anchor_index = inserted_rows.index("3")
        inserted_id = inserted_rows[anchor_index + 1]
        self.assertTrue(int(inserted_id) < 0, "new node must be inserted directly below the visually last selected node")
        inserted_row = page.locator(f'[data-editor-row="{inserted_id}"]')
        self.assertEqual(inserted_row.locator('[data-editor-field="stage"]').input_value(), "开发")
        self.assertEqual(inserted_row.locator('[data-editor-field="track"]').input_value(), "main")
        self.assertTrue(page.locator('[data-editor-batch-dock]').is_hidden(), "selection clears after contextual insertion")
        self.physical_click(page, page.locator('[data-timeline-discard]'))
        table = page.locator('[data-timeline-page="editor"] .timeline-sheet')
        dock = page.locator('[data-editor-batch-dock]')

        def select_nodes(*node_ids):
            for node_id in node_ids:
                table.locator(f'[data-editor-select-node="{node_id}"]').check()

        def apply_batch(field, value):
            dock.locator('[data-editor-batch-field]').select_option(field)
            dock.locator('[data-editor-batch-value]').select_option(value)
            confirm = dock.locator('[data-editor-batch-confirm]')
            self.assertFalse(confirm.is_disabled())
            self.assertEqual(confirm.evaluate("el => getComputedStyle(el).backgroundColor"), "rgb(217, 45, 63)")
            self.physical_click(page, confirm)
            table.wait_for()

        select_nodes(1, 2)
        self.assertEqual(dock.locator('[data-editor-batch-field] option').all_inner_texts(), ["选择字段…", "项目阶段", "轨道", "状态"])
        dock.locator('[data-editor-batch-field]').select_option("done_at")
        self.assertEqual(dock.locator('[data-editor-batch-value] option').all_inner_texts(), ["选择对应值…", "已完成", "未完成（按日期自动判断）"])
        dock.locator('[data-editor-batch-field]').select_option("stage")
        self.assertEqual(dock.locator('[data-editor-batch-value] option').all_inner_texts(), ["选择对应值…", "创意", "设计", "开发", "测试", "量产", "应用迭代"])
        dock.locator('[data-editor-batch-value]').select_option("测试")
        self.physical_click(page, dock.locator('[data-editor-batch-confirm]'))
        table.wait_for()
        self.assertEqual(table.locator('[data-editor-field="stage"][data-node-id="1"]').input_value(), "测试")
        self.assertEqual(table.locator('[data-editor-field="stage"][data-node-id="2"]').input_value(), "测试")
        self.assertEqual(page.locator('[data-timeline-draft-count]').inner_text(), "2 项草稿")
        self.assertEqual(batch_requests, [], "batch editing must remain local until the existing Save action")
        self.physical_click(page, page.locator('[data-timeline-discard]'))

        table = page.locator('[data-timeline-page="editor"] .timeline-sheet')
        dock = page.locator('[data-editor-batch-dock]')
        select_nodes(1, 2)
        apply_batch("track", "parallel")
        self.assertEqual(table.locator('[data-editor-field="track"][data-node-id="1"]').input_value(), "parallel")
        self.assertEqual(table.locator('[data-editor-field="track"][data-node-id="2"]').input_value(), "parallel")
        self.physical_click(page, page.locator('[data-timeline-discard]'))

        table = page.locator('[data-timeline-page="editor"] .timeline-sheet')
        dock = page.locator('[data-editor-batch-dock]')
        select_nodes(1, 2)
        apply_batch("done_at", "true")
        self.assertEqual(table.locator('[data-editor-field="done_at"][data-node-id="1"]').input_value(), "true")
        self.assertEqual(table.locator('[data-editor-field="done_at"][data-node-id="2"]').input_value(), "true")
        with page.expect_response(lambda response: response.request.method == "POST" and response.url.endswith("/timeline/batches")) as status_saved:
            self.physical_click(page, page.locator('[data-timeline-submit]'))
        self.assertEqual(status_saved.value.status, 200)
        self.assertEqual(len(batch_requests[0]["requests"][0]["changes"]), 2)

        table = page.locator('[data-timeline-page="editor"] .timeline-sheet')
        dock = page.locator('[data-editor-batch-dock]')
        select_nodes(3, 4)
        self.physical_click(page, dock.locator('[data-editor-batch-delete]'))
        delete_overlay = page.locator('[data-editor-batch-delete-overlay]')
        self.assertTrue(delete_overlay.is_visible())
        self.assertEqual(delete_overlay.locator('[data-editor-batch-delete-count]').inner_text(), "2")
        self.physical_click(page, delete_overlay.locator('[data-editor-batch-delete-confirm]'))
        self.assertEqual(page.locator('[data-editor-row="3"], [data-editor-row="4"]').count(), 0)
        self.assertEqual(page.locator('[data-timeline-draft-count]').inner_text(), "2 项草稿")
        with page.expect_response(lambda response: response.request.method == "POST" and response.url.endswith("/timeline/batches")) as delete_saved:
            self.physical_click(page, page.locator('[data-timeline-submit]'))
        self.assertEqual(delete_saved.value.status, 200)
        self.assertEqual(len(batch_requests), 2)
        self.assertEqual(sum(1 for change in batch_requests[1]["requests"][0]["changes"] if change.get("remove")), 2)
        db = connect(self.db_path)
        try:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM timeline_nodes WHERE project_id=? AND deleted_at IS NULL", (project_id,)).fetchone()[0], 2)
        finally:
            db.close()
        with page.expect_response(lambda response: response.url.endswith("/timeline/batches/undo")) as undone:
            self.physical_click(page, page.locator('[data-timeline-undo]'))
        self.assertEqual(undone.value.status, 200)
        self.assertEqual(page.locator('[data-editor-row]').count(), 4)
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

        self.assertEqual(page.locator('[data-timeline-review], [data-timeline-correct], [data-timeline-review-panel]').count(), 0)
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
        page.evaluate("""() => { const header=document.createElement('header'); header.innerHTML='<button id="timelineClose">←</button>'; document.querySelector('#timelineView>.timeline-shell').prepend(header) }""")
        self.assertFalse(page.locator('.timeline-shell>header').is_visible())
        self.open_cp4_single(page, project_id)
        card = page.locator('[data-timeline-page="single"] > .timeline-project-card')
        self.assertEqual(card.locator("h2").inner_text(), "CP4 重叠双轨")
        self.assertIn("当前", card.locator(".tl-proj-kpi").inner_text())
        self.assertEqual(card.locator(".timeline-summary, .timeline-single-caption, .timeline-dashboard-footer").count(), 0)
        self.assertEqual(card.get_by_text("PROJECT · 时间管理", exact=True).count(), 0)
        self.assertEqual(card.get_by_text("审计 · 预留", exact=True).count(), 0)
        self.assertEqual(card.locator('[data-timeline-mode-target="all"]').count(), 0)
        self.assertNotIn("阶段分界", card.locator(".tl-legend").inner_text())
        blank_calendar = card.locator('[data-e-calendar]')
        self.assertEqual(blank_calendar.inner_text(), "")
        self.assertEqual(blank_calendar.evaluate("el => getComputedStyle(el).height"), "18px")
        self.assertEqual(page.locator('.timeline-shell>header, #timelineClose').count(), 0)
        self.assertEqual(page.evaluate("typeof removeLegacyTimelineBackRows"), "function")
        self.assertEqual(card.locator('[data-track="main"]').count(), 1)
        self.assertEqual(card.locator('[data-track="parallel"]').count(), 1)
        self.assertEqual(card.locator('.timeline-portfolio-card.is-single-profile[data-canvas-profile="single"]').count(), 1)
        self.assertEqual(card.locator('.timeline-portfolio-chart').count(), 1)
        self.assertEqual(card.locator('[data-portfolio-focus-project]').count(), 0)
        self.assertAlmostEqual(card.locator('.timeline-portfolio-project').bounding_box()["height"], 190, delta=1)
        self.assertEqual(card.locator('.timeline-node-flag').count(), card.locator('.timeline-dashboard-node').count())
        single_node = card.locator('.timeline-dashboard-node').first
        normal_node_width = single_node.locator('i').evaluate("el => Number(getComputedStyle(el).width.slice(0,-2))")
        single_key = single_node.get_attribute('data-node-flag-key')
        single_flag = card.locator(f'.timeline-node-flag[data-node-flag-key="{single_key}"]')
        single_node.hover()
        self.assertTrue(single_flag.evaluate("el => el.classList.contains('is-probed')"))
        self.assertTrue(page.locator('[data-timeline-node-tooltip]').is_hidden())
        card.locator('.timeline-portfolio-axis-label').hover()
        self.assertFalse(single_flag.evaluate("el => el.classList.contains('is-probed')"))
        single_probe = card.locator(f'.timeline-node-flag-hit.is-active[data-node-flag-key="{single_key}"]')
        single_flag_target = single_probe if single_probe.is_visible() else single_flag
        single_flag_target.hover(position={"x": 4, "y": 8})
        self.assertTrue(single_flag.evaluate("el => el.classList.contains('is-probed')"), "hovering the flag itself must promote that exact flag")
        self.physical_click(page, single_flag_target, button="right")
        single_flag_menu = card.locator('[data-timeline-context]')
        single_flag_menu.wait_for(state="visible")
        self.assertEqual(single_flag_menu.get_attribute('data-node-id'), single_node.get_attribute('data-node-id'))
        self.assertEqual(single_flag_menu.get_attribute('data-project-id'), single_node.get_attribute('data-project-id'))
        self.assertEqual(single_flag_menu.locator('[role="menuitem"]').all_inner_texts(), ['拖拽（仅当前节点）', '拖拽（顺延）', '已完成', '未完成', '编辑备注', '删除节点'])
        self.physical_click(page, single_flag_menu.locator('[data-draft-action="cascade"]'))
        single_flag_menu.wait_for(state="hidden")
        self.assertTrue(single_node.evaluate("el => el.classList.contains('is-armed')"), "flag menu actions must target the underlying node")
        self.assertTrue(single_flag.evaluate("el => el.classList.contains('is-armed')"), "the visual flag must mirror the underlying node's selected state")
        selected_sizes = single_flag.evaluate("""el => { const flag=getComputedStyle(el),name=getComputedStyle(el.querySelector('b')),date=getComputedStyle(el.querySelector('small')),node=getComputedStyle(document.querySelector(`.timeline-dashboard-node[data-node-flag-key="${el.dataset.nodeFlagKey}"] i`)); return {flag:Number(flag.fontSize.slice(0,-2)),name:Number(name.fontSize.slice(0,-2)),date:Number(date.fontSize.slice(0,-2)),nodeWidth:Number(node.width.slice(0,-2))} }""")
        self.assertGreater(selected_sizes["flag"], 8.5)
        self.assertGreater(selected_sizes["name"], 8.5)
        self.assertGreater(selected_sizes["date"], 6.5)
        self.assertEqual(selected_sizes["nodeWidth"], normal_node_width, "selected styling must not enlarge the node circle")
        single_geometry = card.locator('.timeline-portfolio-project').evaluate("""row => {
          const rr=row.getBoundingClientRect(),flags=[...row.querySelectorAll('.timeline-node-flag')].map(el=>el.getBoundingClientRect());
          return {top:Math.min(...flags.map(r=>r.top))-rr.top,bottom:rr.bottom-Math.max(...flags.map(r=>r.bottom))};
        }""")
        self.assertGreaterEqual(single_geometry["top"], -1)
        self.assertGreaterEqual(single_geometry["bottom"], -1)
        self.assertAlmostEqual(single_geometry["top"], single_geometry["bottom"], delta=6)
        self.assertGreaterEqual(single_geometry["top"], 20, "single dashboard should retain more outer whitespace than the portfolio row")
        self.assertGreaterEqual(single_geometry["bottom"], 20, "single dashboard should retain more outer whitespace than the portfolio row")
        axis_label = card.locator('.timeline-portfolio-axis-label')
        self.assertEqual(axis_label.inner_text(), "")
        self.assertAlmostEqual(axis_label.bounding_box()["width"], 73.333, delta=1)
        self.assertAlmostEqual(card.locator('.timeline-portfolio-meta').bounding_box()["width"], 73.333, delta=1)
        labels = card.locator('.timeline-single-track-key > span')
        self.assertEqual(labels.count(), 2)
        for label in labels.all():
            style = label.evaluate("""el => { const s=getComputedStyle(el), parent=getComputedStyle(el.closest('.timeline-portfolio-meta')); return {
              parentPosition:parent.position,parentLeft:parent.left,parentZIndex:Number(parent.zIndex),display:s.display,
              placeItems:s.placeItems,textAlign:s.textAlign,background:s.backgroundColor,
              bottomBorder:s.borderBottomWidth
            }}""")
            self.assertEqual(style["parentPosition"], "sticky")
            self.assertEqual(style["parentLeft"], "0px")
            self.assertGreater(style["parentZIndex"], 0)
            self.assertEqual(style["display"], "grid")
            self.assertIn("center", style["placeItems"])
            self.assertEqual(style["textAlign"], "center")
            self.assertEqual(style["background"], "rgb(255, 255, 255)")
            self.assertEqual(style["bottomBorder"], "6px")
            self.assertTrue(label.evaluate("""el => { const r=el.getBoundingClientRect(); const hit=document.elementFromPoint(r.left+r.width/2,r.top+r.height/2); return hit===el||el.contains(hit) }"""))
        track_alignment = card.evaluate("""root => {
          const center=el=>{const r=el.getBoundingClientRect();return r.top+r.height/2},labels=[...root.querySelectorAll('.timeline-single-track-key > span')],main=root.querySelector('.timeline-stage-lane[data-track="main"]'),parallel=root.querySelector('.timeline-stage-lane[data-track="parallel"]');
          return {mainLabel:center(labels[0]),parallelLabel:center(labels[1]),mainLane:center(main),parallelLane:center(parallel)};
        }""")
        self.assertAlmostEqual(track_alignment["mainLabel"], track_alignment["mainLane"], delta=1)
        self.assertAlmostEqual(track_alignment["parallelLabel"], track_alignment["parallelLane"], delta=1)
        self.assertAlmostEqual(track_alignment["parallelLane"] - track_alignment["mainLane"], 44, delta=1)
        self.assertEqual(card.locator(".timeline-editor").count(), 0, "dashboard must not embed the editor")
        header_before = card.locator(":scope > header").bounding_box()
        tabs_before = card.locator(":scope > .timeline-project-tabs").bounding_box()
        self.physical_click(page, card.locator('[data-timeline-mode-target="editor"]'))
        editor_card = page.locator('[data-timeline-page="editor"] > .timeline-project-card[data-project-shell="editor"]')
        editor_card.locator('.timeline-sheet').wait_for()
        self.assertEqual(editor_card.locator(":scope > header h2").inner_text(), "CP4 重叠双轨")
        self.assertIn("当前", editor_card.locator(":scope > header .tl-proj-kpi").inner_text())
        self.assertEqual(editor_card.locator('.timeline-sheet-head, .timeline-sheet-project').count(), 0)
        self.assertEqual(editor_card.get_by_text("PROJECT · 时间管理", exact=True).count(), 0)
        header_after = editor_card.locator(":scope > header").bounding_box()
        tabs_after = editor_card.locator(":scope > .timeline-project-tabs").bounding_box()
        self.assertAlmostEqual(header_after["y"], header_before["y"], delta=1)
        self.assertAlmostEqual(header_after["height"], header_before["height"], delta=1)
        self.assertAlmostEqual(tabs_after["y"], tabs_before["y"], delta=1)
        self.assertAlmostEqual(tabs_after["height"], tabs_before["height"], delta=1)
        self.assert_clean_browser(page); context.close()

    def test_timeline_shared_calendar_and_today_marker(self):
        (project_id, _, _), today = self.seed_cp4_dashboard_projects()
        context, page = self.login("u1")
        self.open_cp4_single(page, project_id)
        self.physical_click(page, page.locator('#timelineAllBtn'))
        page.locator('[data-timeline-page="all"] [data-shared-calendar="true"]').wait_for()
        portfolio = page.locator('[data-timeline-page="all"] .timeline-portfolio-chart')
        self.assertEqual(portfolio.count(), 1)
        self.assertEqual(portfolio.locator('.timeline-calendar').count(), 1)
        self.assertEqual(portfolio.locator('.timeline-calendar').inner_text(), "")
        self.assertEqual(portfolio.locator('.timeline-calendar').evaluate("el => getComputedStyle(el).height"), "18px")
        self.assertEqual(portfolio.locator('.timeline-today-line').count(), 1)
        self.assertEqual(page.locator('[data-timeline-page="all"] .timeline-project-card').count(), 0)
        cards = page.locator("[data-dashboard-project]")
        self.assertGreaterEqual(cards.count(), 2)
        self.assertTrue(portfolio.get_attribute("data-calendar-start"))
        self.assertTrue(portfolio.get_attribute("data-calendar-end"))
        self.assertEqual(portfolio.locator(".timeline-today-line").get_attribute("data-today"), today)
        self.assertIn("今天", portfolio.locator(".timeline-portfolio-today-label").inner_text())
        self.assertEqual(portfolio.locator(".timeline-today-line").evaluate("node => getComputedStyle(node).backgroundColor"), "rgb(229, 72, 77)")
        self.assert_clean_browser(page); context.close()

    def test_past_only_parallel_project_keeps_masks_in_single_and_portfolio(self):
        today = datetime.now(timezone(timedelta(hours=8))).date()
        db = connect(self.db_path)
        try:
            now = datetime.now(timezone.utc).isoformat()
            created = db.execute(
                "INSERT INTO timeline_projects(workspace_id,name,created_by,version,created_at,updated_at) VALUES (1,'历史并行项目','u1',1,?,?)",
                (now, now),
            )
            project_id = created.lastrowid
            for index, node_date in enumerate((today - timedelta(days=30), today - timedelta(days=1)), 1):
                value = node_date.isoformat()
                db.execute(
                    "INSERT INTO timeline_nodes(project_id,track,stage,name,date,initial_date,remark,version,created_at,updated_at) VALUES (?,'parallel','测试',?,?,?,'',1,?,?)",
                    (project_id, f"历史节点 {index}", value, value, now, now),
                )
            db.commit()
        finally:
            db.close()

        context, page = self.login("u1")
        self.open_cp4_single(page, project_id)
        single = page.locator('[data-timeline-page="single"] .timeline-portfolio-chart')
        single.wait_for()
        self.assertEqual(single.locator('.timeline-past-mask').count(), 2)
        single_today_x = single.locator('.timeline-today-line').bounding_box()["x"]
        for mask in single.locator('.timeline-past-mask').all():
            box = mask.bounding_box()
            self.assertAlmostEqual(box["x"] + box["width"], single_today_x, delta=1)
        self.assertTrue(all(node["x"] <= single_today_x + 1 for node in single.locator('.timeline-dashboard-node').evaluate_all(
            "els => els.map(el => ({x:el.getBoundingClientRect().x}))"
        )))
        self.assertTrue(all(stage["right"] <= single_today_x + 1 for stage in single.locator('.timeline-stage').evaluate_all(
            "els => els.map(el => ({right:el.getBoundingClientRect().right}))"
        )))

        self.physical_click(page, page.locator('#timelineAllBtn'))
        row = page.locator(f'[data-timeline-page="all"] [data-dashboard-project="{project_id}"]')
        row.wait_for()
        self.assertEqual(row.locator('.timeline-past-mask').count(), 2)
        portfolio_today_x = page.locator('[data-timeline-page="all"] .timeline-today-line').bounding_box()["x"]
        for mask in row.locator('.timeline-past-mask').all():
            box = mask.bounding_box()
            self.assertAlmostEqual(box["x"] + box["width"], portfolio_today_x, delta=1)
        self.assertTrue(all(node["x"] <= portfolio_today_x + 1 for node in row.locator('.timeline-dashboard-node').evaluate_all(
            "els => els.map(el => ({x:el.getBoundingClientRect().x}))"
        )))
        self.assertTrue(all(stage["right"] <= portfolio_today_x + 1 for stage in row.locator('.timeline-stage').evaluate_all(
            "els => els.map(el => ({right:el.getBoundingClientRect().right}))"
        )))
        self.assert_clean_browser(page); context.close()

    def test_timeline_overlap_split_and_expand(self):
        (project_id, _, _), _today = self.seed_cp4_dashboard_projects()
        self.extend_cp4_stage_intervals(project_id)
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
        self.extend_cp4_stage_intervals(project_id)
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
        single_card = page.locator(f'[data-dashboard-project="{project_id}"]')
        self.assertEqual(single_card.locator('.timeline-dashboard-actions').count(), 0)
        single_card.locator('.timeline-portfolio-meta').hover()
        self.assertEqual(single_card.locator('.timeline-dashboard-actions').count(), 0, "hover alone must not expose single-project draft actions")
        self.physical_click(page, single_card.locator('.timeline-portfolio-meta'), button="right")
        idle_single_menu = page.locator('[data-portfolio-undo-menu]')
        idle_single_menu.wait_for(state="visible")
        self.assertEqual(idle_single_menu.locator('[data-portfolio-undo-action]').inner_text(), '撤销')
        self.assertTrue(idle_single_menu.locator('[data-portfolio-undo-action]').is_disabled())
        page.keyboard.press('Escape')
        idle_single_menu.wait_for(state="hidden")
        self.zoom_single_until_node_visible(page)
        node = page.locator(f'[data-dashboard-project="{project_id}"] .timeline-dashboard-node').first
        expected_node = node.get_attribute("data-node-id")
        node_box = node.bounding_box()
        self.assertEqual(page.evaluate("point => document.elementFromPoint(point.x, point.y)?.closest('.timeline-dashboard-node')?.dataset.nodeId || null", {"x": node_box["x"] + node_box["width"] / 2, "y": node_box["y"] + node_box["height"] / 2}), expected_node)
        page.evaluate("""() => { window.__dashboardHitEvents=[]; for (const type of ['mousedown','mouseup','contextmenu']) document.addEventListener(type,event=>window.__dashboardHitEvents.push({type,node:event.target.closest('.timeline-dashboard-node')?.dataset.nodeId||null}),{capture:true,once:true}) }""")
        self.physical_click(page, node, button="right")
        self.assertEqual(page.evaluate("window.__dashboardHitEvents"), [{"type":"mousedown","node":expected_node},{"type":"mouseup","node":expected_node},{"type":"contextmenu","node":expected_node}])
        menu = page.locator('[data-timeline-context]')
        self.assertEqual(menu.locator('[role="menuitem"]').count(), 6)
        self.record_mouse_sequence(page, '[data-timeline-context] [data-draft-action="cascade"]')
        self.physical_click(page, menu.locator('[data-draft-action="cascade"]'))
        self.assertEqual(page.evaluate("window.__timelineClicks"), ["mousedown", "mouseup", "click"])
        self.assertEqual(page.locator(f'[data-dashboard-project="{project_id}"] .timeline-dashboard-node.is-armed').count(), 1)
        self.assertEqual(single_card.locator('.timeline-dashboard-actions').count(), 0, "arming drag without changing a date must not expose actions")
        self.assertEqual(len(requests), baseline, "dashboard context action must issue zero network requests")
        self.assertEqual(self.timeline_content_hash(), stable_hash)
        self.physical_click(page, page.locator('[data-timeline-mode-target="editor"]'))
        page.locator('[data-timeline-page="editor"]').wait_for()
        self.physical_click(page, page.locator('[data-timeline-mode-target="single"]'))
        page.locator('[data-timeline-page="single"]').wait_for()
        self.assertEqual(page.locator(f'[data-dashboard-project="{project_id}"] .timeline-dashboard-node.is-armed').count(), 0, "leaving a dashboard without a drag must clear its transient selected state")
        node = page.locator(f'[data-dashboard-project="{project_id}"] .timeline-dashboard-node[data-node-id="{expected_node}"]')
        self.physical_click(page, node, button="right")
        menu = page.locator('[data-timeline-context]')
        self.physical_click(page, menu.locator('[data-draft-action="cascade"]'))
        flag = page.locator(f'[data-dashboard-project="{project_id}"] .timeline-node-flag[data-node-id="{expected_node}"]')
        flag_box = flag.bounding_box()
        page.mouse.move(flag_box["x"] + flag_box["width"] / 2, flag_box["y"] + flag_box["height"] / 2)
        page.mouse.down()
        page.mouse.move(flag_box["x"] + flag_box["width"] / 2 - 70, flag_box["y"] + flag_box["height"] / 2, steps=6)
        page.mouse.up()
        dragged_actions = page.locator('[data-single-dashboard-draft-actions]')
        dragged_actions.wait_for()
        pending_node = page.locator(f'[data-dashboard-project="{project_id}"] .timeline-dashboard-node[data-node-id="{expected_node}"]')
        pending_flag = page.locator(f'[data-dashboard-project="{project_id}"] .timeline-node-flag[data-node-id="{expected_node}"]')
        self.assertTrue(pending_node.evaluate("el => el.classList.contains('is-drag-pending') && el.classList.contains('is-emphasized') && !el.classList.contains('is-armed')"))
        self.assertTrue(pending_flag.evaluate("el => el.classList.contains('is-drag-pending') && el.classList.contains('is-emphasized') && !el.classList.contains('is-armed')"))
        self.assertEqual(dragged_actions.locator('button').first.inner_text(), '放弃')
        self.assertRegex(dragged_actions.locator('[data-dashboard-submit]').inner_text(), r'^更新 \d+$')
        self.physical_click(page, page.locator(f'[data-dashboard-project="{project_id}"] .timeline-portfolio-meta'), button="right")
        blocked_menu = page.locator('[data-portfolio-undo-menu]')
        blocked_menu.wait_for(state="visible")
        self.assertEqual(blocked_menu.locator('[data-portfolio-undo-action]').inner_text(), '请先更新或放弃草稿')
        self.assertTrue(blocked_menu.locator('[data-portfolio-undo-action]').is_disabled())
        page.keyboard.press('Escape')
        blocked_menu.wait_for(state="hidden")
        self.physical_click(page, dragged_actions.locator('[data-dashboard-discard]'))
        dragged_actions.wait_for(state="detached")
        single_card = page.locator(f'[data-dashboard-project="{project_id}"]')
        self.assertEqual(single_card.locator('.is-drag-pending,.is-emphasized').count(), 0, "discarding the draft must clear the persistent drag emphasis")
        node = single_card.locator(f'.timeline-dashboard-node[data-node-id="{expected_node}"]')
        self.physical_click(page, node, button="right")
        self.physical_click(page, page.locator('[data-timeline-context] [data-draft-action="done"]'))
        single_actions = page.locator('[data-single-dashboard-draft-actions]')
        single_actions.wait_for()
        self.assertTrue(single_actions.is_visible())
        dock_metrics = single_actions.evaluate("""el => { const r=el.getBoundingClientRect(),main=document.querySelector('.main-content').getBoundingClientRect(); return {position:getComputedStyle(el).position,center:r.left+r.width/2,mainCenter:main.left+main.width/2,bottom:innerHeight-r.bottom} }""")
        self.assertEqual(dock_metrics["position"], "fixed")
        self.assertAlmostEqual(dock_metrics["center"], dock_metrics["mainCenter"], delta=2)
        self.assertAlmostEqual(dock_metrics["bottom"], 22, delta=2)
        dashboard_leave_dialogs = []
        def accept_dashboard_leave(dialog):
            dashboard_leave_dialogs.append(dialog.message)
            dialog.accept()
        page.on("dialog", accept_dashboard_leave)
        self.physical_click(page, page.locator('[data-timeline-mode-target="home"]'))
        page.locator('[data-timeline-page="home"]').wait_for()
        self.assertEqual(dashboard_leave_dialogs, ['有尚未提交的项目时间表草稿，确定放弃并离开？'])
        self.assertFalse(page.evaluate("timelineHasDraft()"))
        self.physical_click(page, page.locator('#timelineBtn'))
        self.assertEqual(len(dashboard_leave_dialogs), 1, "confirmed dashboard discard must not prompt again from home")
        self.physical_click(page, page.locator('#timelineAllBtn'))
        page.locator('[data-timeline-page="all"] .timeline-dashboard-node').first.wait_for()
        baseline = len(requests)
        first_row = page.locator('[data-timeline-page="all"] [data-dashboard-project]').first
        self.assertEqual(first_row.locator('.timeline-portfolio-actions').count(), 0)
        first_row.locator('.timeline-portfolio-meta').hover()
        self.assertEqual(first_row.locator('.timeline-portfolio-actions').count(), 0, "hover alone must not expose all-project row actions")
        self.assertEqual(page.locator('[data-timeline-page="all"] .timeline-row-menu, [data-timeline-page="all"] [data-timeline-archive]').count(), 0)
        self.physical_click(page, first_row.locator('.timeline-portfolio-meta'), button="right")
        idle_all_menu = page.locator('[data-portfolio-undo-menu]')
        idle_all_menu.wait_for(state="visible")
        self.assertEqual(idle_all_menu.locator('[data-portfolio-undo-action]').inner_text(), '撤销')
        self.assertTrue(idle_all_menu.locator('[data-portfolio-undo-action]').is_disabled())
        page.keyboard.press('Escape')
        idle_all_menu.wait_for(state="hidden")
        all_node = page.locator('[data-timeline-page="all"] .timeline-dashboard-node').first
        all_project_id = all_node.get_attribute("data-project-id")
        self.physical_click(page, all_node, button="right")
        self.assertEqual(page.locator('[data-timeline-page="all"] [data-timeline-context] [role="menuitem"]').count(), 6)
        self.physical_click(page, page.locator('[data-timeline-page="all"] [data-draft-action="done"]'))
        all_actions = page.locator(f'[data-timeline-page="all"] [data-dashboard-project="{all_project_id}"] .timeline-portfolio-actions')
        all_actions.wait_for()
        self.assertTrue(all_actions.is_visible())
        self.assertEqual(all_actions.locator('button').all_inner_texts(), ['放弃', '更新 1'])
        self.assertEqual(all_actions.locator('[data-dashboard-undo]').count(), 0)
        self.assertIn("尚未写入服务器", page.locator(f'[data-timeline-page="all"] [data-dashboard-project="{all_project_id}"] [data-dashboard-hint]').inner_text())
        self.assertEqual(len(requests), baseline)
        self.assertEqual(self.timeline_content_hash(), stable_hash)
        with page.expect_response(lambda response: response.request.method == "POST" and response.url.endswith("/timeline/batches")) as updated:
            self.physical_click(page, all_actions.locator('[data-dashboard-submit]'))
        self.assertEqual(updated.value.status, 200)
        all_actions.wait_for(state="detached")
        self.assertEqual(page.locator(f'[data-timeline-page="all"] [data-dashboard-project="{all_project_id}"] .timeline-portfolio-actions').count(), 0)
        page.locator('[data-timeline-page="all"] .timeline-portfolio-axis-detail').hover()
        undo_meta = page.locator(f'[data-timeline-page="all"] [data-dashboard-project="{all_project_id}"] .timeline-portfolio-meta')
        undo_meta.hover()
        self.assertEqual(page.locator(f'[data-timeline-page="all"] [data-dashboard-project="{all_project_id}"] .timeline-portfolio-actions').count(), 0, "project-column hover must never reveal undo")
        self.physical_click(page, undo_meta, button="right")
        undo_menu = page.locator('[data-portfolio-undo-menu]')
        undo_menu.wait_for(state="visible")
        self.assertEqual(undo_menu.locator('[data-portfolio-undo-action]').inner_text(), '撤销')
        self.assertEqual(undo_menu.locator('[data-portfolio-undo-action]').evaluate("el => getComputedStyle(el).color"), 'rgb(216, 52, 69)')
        with page.expect_response(lambda response: response.request.method == "POST" and response.url.endswith("/timeline/batches/undo")) as undone:
            self.physical_click(page, undo_menu.locator('[data-portfolio-undo-action]'))
        self.assertEqual(undone.value.status, 200)
        undo_menu.wait_for(state="hidden")
        self.assert_clean_browser(page); context.close()

    def test_dashboard_hover_date_insert_remark_and_delete_share_draft_pipeline(self):
        (project_id, _, _), _today = self.seed_cp4_dashboard_projects()
        context, page = self.login("u1")
        self.open_cp4_single(page, project_id)
        self.zoom_single_until_node_visible(page)
        stable_hash = self.timeline_content_hash()
        main_plot = page.locator(f'[data-dashboard-project="{project_id}"] [data-track="main"] .timeline-stage-plot')
        plot_box = main_plot.bounding_box()
        scroll_box = page.locator('[data-timeline-page="single"] [data-portfolio-scroll]').bounding_box()
        insert_x = max(plot_box["x"] + 35, min(plot_box["x"] + plot_box["width"] * .78, scroll_box["x"] + scroll_box["width"] - 45))
        insert_y = plot_box["y"] + plot_box["height"] - 9
        page.mouse.move(insert_x, insert_y)
        guide = page.locator('[data-timeline-page="single"] [data-dashboard-date-guide]')
        guide.wait_for(state="visible")
        inserted_date = guide.locator("b").inner_text()
        self.assertRegex(inserted_date, r"^\d{4}-\d{2}-\d{2}$")
        self.assertEqual(guide.evaluate("el => getComputedStyle(el).borderLeftStyle"), "dashed")
        guide_label = guide.locator("b")
        self.assertEqual(guide_label.evaluate("el => getComputedStyle(el).backgroundColor"), "rgba(255, 255, 255, 0.97)")
        self.assertIn(guide_label.get_attribute("data-placement"), ("above-left", "above-right", "below-left", "below-right"))

        visible_node = page.locator(f'[data-dashboard-project="{project_id}"] .timeline-dashboard-node').first
        visible_node.hover()
        guide.wait_for(state="hidden")
        self.assertTrue(guide_label.is_hidden(), "node tooltip owns hover feedback, so the moving date label must retreat")
        page.mouse.move(insert_x, insert_y)
        guide.wait_for(state="visible")
        self.assertEqual(guide.locator("b").inner_text(), inserted_date)

        page.mouse.down(button="right"); page.mouse.up(button="right")
        insert_menu = page.locator('[data-dashboard-insert-menu]')
        insert_menu.wait_for(state="visible")
        self.assertEqual(insert_menu.locator('[data-dashboard-insert-action] strong').inner_text(), "插入节点")
        self.assertIn(inserted_date, insert_menu.locator('[data-dashboard-insert-context]').inner_text())
        self.assertTrue(guide_label.is_hidden(), "D3 hover label retreats while the insert menu owns the date context")
        self.assertEqual(guide.evaluate("el => getComputedStyle(el).borderLeftStyle"), "solid")
        self.physical_click(page, insert_menu.locator('[data-dashboard-insert-action]'))
        editor = page.locator('[data-dashboard-node-editor]')
        editor.wait_for(state="visible")
        self.assertEqual(editor.locator('[data-dashboard-node-editor-title]').inner_text(), "插入到主线")
        self.assertIn(inserted_date, editor.locator('[data-dashboard-node-editor-context]').inner_text())
        self.assertTrue(editor.locator('[data-dashboard-node-remark-field]').is_hidden())
        self.assertIn("is-quick-insert", editor.get_attribute("class"))
        self.assertLess(editor.bounding_box()["width"], 300, "insert uses the approved D mini bubble instead of the modal-sized editor")
        self.assertEqual(editor.evaluate("el => getComputedStyle(el).backgroundColor"), "rgba(0, 0, 0, 0)")
        editor.locator('input[name="name"]').fill("右键快速节点")
        self.physical_click(page, editor.locator('button[type="submit"]'))
        editor.wait_for(state="hidden")
        inserted = page.locator(f'[data-dashboard-project="{project_id}"] .timeline-dashboard-node[data-node-id^="-"]')
        inserted.wait_for()
        self.assertEqual(inserted.locator('[data-node-tooltip-source] b').inner_text(), "右键快速节点")
        self.assertEqual(self.timeline_content_hash(), stable_hash, "quick insert must remain a local draft before update")

        existing = page.locator(f'[data-dashboard-project="{project_id}"] .timeline-dashboard-node:not([data-node-id^="-"])').first
        edited_node_id = int(existing.get_attribute("data-node-id"))
        self.physical_click(page, existing, button="right")
        menu = page.locator('[data-timeline-context]')
        menu.wait_for(state="visible")
        self.physical_click(page, menu.locator('[data-draft-action="remark"]'))
        editor = page.locator('[data-dashboard-node-editor]')
        editor.wait_for(state="visible")
        self.assertEqual(editor.locator('[data-dashboard-node-editor-title]').inner_text(), "编辑备注")
        self.assertTrue(editor.locator('[data-dashboard-node-name-field]').is_hidden())
        editor.locator('textarea[name="remark"]').fill("来自仪表盘的多行备注\n第二行")
        self.physical_click(page, editor.locator('button[type="submit"]'))
        editor.wait_for(state="hidden")

        removable = page.locator(f'[data-dashboard-project="{project_id}"] .timeline-dashboard-node:not([data-node-id="{edited_node_id}"]):not([data-node-id^="-"])').first
        removed_node_id = int(removable.get_attribute("data-node-id"))
        self.physical_click(page, removable, button="right")
        remove_action = page.locator('[data-timeline-context] [data-draft-action="remove"]')
        self.assertEqual(remove_action.inner_text(), "删除节点")
        self.assertEqual(remove_action.evaluate("el => getComputedStyle(el).color"), "rgb(216, 52, 69)")
        self.physical_click(page, remove_action)
        page.locator(f'[data-dashboard-project="{project_id}"] .timeline-dashboard-node[data-node-id="{removed_node_id}"]').wait_for(state="detached")
        actions = page.locator('[data-single-dashboard-draft-actions]')
        actions.wait_for()
        self.assertEqual(actions.locator('[data-dashboard-submit]').inner_text(), "更新 3")
        self.assertEqual(self.timeline_content_hash(), stable_hash, "remark and delete must remain local drafts before update")

        with page.expect_response(lambda response: response.request.method == "POST" and response.url.endswith("/timeline/batches")) as submitted:
            self.physical_click(page, actions.locator('[data-dashboard-submit]'))
        self.assertEqual(submitted.value.status, 200)
        db = connect(self.db_path)
        try:
            inserted_row = db.execute("SELECT track,stage,date,deleted_at FROM timeline_nodes WHERE project_id=? AND name='右键快速节点'", (project_id,)).fetchone()
            self.assertEqual((inserted_row["track"], inserted_row["date"], inserted_row["deleted_at"]), ("main", inserted_date, None))
            self.assertTrue(inserted_row["stage"])
            self.assertEqual(db.execute("SELECT remark FROM timeline_nodes WHERE id=?", (edited_node_id,)).fetchone()["remark"], "来自仪表盘的多行备注\n第二行")
            self.assertIsNotNone(db.execute("SELECT deleted_at FROM timeline_nodes WHERE id=?", (removed_node_id,)).fetchone()["deleted_at"])
        finally:
            db.close()
        self.assert_clean_browser(page); context.close()

    def test_timeline_all_dashboard_filter_and_sort(self):
        (project_id, _, _), _today = self.seed_cp4_dashboard_projects()
        context, page = self.login("u1")
        requests = []
        page.on("request", lambda request: requests.append((request.method, request.url)))
        self.open_cp4_single(page, project_id)
        self.physical_click(page, page.locator('#timelineAllBtn'))
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

    def test_timeline_all_dashboard_system_my_projects_context(self):
        self.seed_cp4_dashboard_projects()
        member_project_id = self.seed_timeline(created_by="u2", name="成员二负责项目")
        context, page = self.login("u2")
        self.open_cp4_single(page, member_project_id)
        self.physical_click(page, page.locator('#timelineAllBtn'))
        nav = page.locator('[data-timeline-page="all"] .tl-tag-filter')
        nav.wait_for()
        system_labels = nav.locator('[data-timeline-tag-context]').evaluate_all(
            "els => els.slice(0,4).map(el => el.childNodes[0].textContent.trim())"
        )
        self.assertEqual(system_labels, ["全部", "我的项目", "未分类", "已归档项目"])
        mine = nav.locator('[data-timeline-tag-context="mine"]')
        self.assertEqual(mine.get_attribute("data-tag-id"), "")
        self.assertEqual(mine.locator("small").inner_text(), "1")
        self.physical_click(page, mine)
        page.locator('[data-timeline-tag-context="mine"].active').wait_for()
        rows = page.locator('[data-timeline-page="all"] [data-dashboard-project]')
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.first.get_attribute("data-dashboard-project"), str(member_project_id))
        self.assertEqual(page.locator('[data-timeline-page="all"] [data-tag-rename], [data-timeline-page="all"] [data-tag-delete]').count(), 0)
        self.assert_clean_browser(page); context.close()

    def test_timeline_portfolio_e_d4_p1_canvas(self):
        (project_id, _, _), today_value = self.seed_cp4_dashboard_projects()
        self.extend_cp4_stage_intervals(project_id)
        today = datetime.fromisoformat(today_value).date()
        db = connect(self.db_path)
        try:
            now = datetime.now(timezone.utc).isoformat()
            for index in range(9):
                created = db.execute("INSERT INTO timeline_projects(workspace_id,name,created_by,version,created_at,updated_at) VALUES (1,?,'u1',1,?,?)", (f"画布压力项目 {index + 1:02d}", now, now))
                node_date = (today + timedelta(days=index - 4)).isoformat()
                db.execute("INSERT INTO timeline_nodes(project_id,track,stage,name,date,initial_date,remark,version,created_at,updated_at) VALUES (?,?,?,?,?,?,'',1,?,?)", (created.lastrowid, "main", "开发", f"压力节点 {index + 1:02d}", node_date, node_date, now, now))
            dense = db.execute("INSERT INTO timeline_projects(workspace_id,name,created_by,version,created_at,updated_at) VALUES (1,'极密集旗标项目','u1',1,?,?)", (now, now))
            dense_project_id = dense.lastrowid
            dense_date = today.isoformat()
            for index in range(24):
                db.execute("INSERT INTO timeline_nodes(project_id,track,stage,name,date,initial_date,remark,version,created_at,updated_at) VALUES (?,'main','开发',?,?,?,?,1,?,?)", (dense_project_id, f"极密集节点 {index + 1:02d}", dense_date, dense_date, '', now, now))
            adaptive = db.execute("INSERT INTO timeline_projects(workspace_id,name,created_by,version,created_at,updated_at) VALUES (1,'自适应旗标项目','u1',1,?,?)", (now, now))
            adaptive_project_id = adaptive.lastrowid
            for index in range(7):
                node_date = (today + timedelta(days=index * 2 - 4)).isoformat()
                db.execute("INSERT INTO timeline_nodes(project_id,track,stage,name,date,initial_date,remark,version,created_at,updated_at) VALUES (?,'parallel','测试',?,?,?,?,1,?,?)", (adaptive_project_id, f"碳板力值测试（第{index + 1}次）", node_date, node_date, '', now, now))
            db.commit()
        finally:
            db.close()

        context, page = self.login("u1")
        self.open_cp4_single(page, project_id)
        self.physical_click(page, page.locator('#timelineAllBtn'))
        chart = page.locator('[data-timeline-page="all"] .timeline-portfolio-chart')
        chart.wait_for()

        self.assertEqual(chart.get_attribute("data-calendar-start"), (today - timedelta(days=50)).isoformat())
        self.assertEqual(chart.get_attribute("data-calendar-end"), (today + timedelta(days=38)).isoformat())
        for layer in ("years", "months", "days"):
            self.assertEqual(page.locator(f".timeline-e-{layer}").count(), 1)
        self.assertEqual(page.locator(".timeline-e-quarters").count(), 0)
        self.assertEqual(page.locator(".timeline-shared-caption").count(), 0)
        row_height = page.locator('.timeline-portfolio-project').first.bounding_box()["height"]
        self.assertGreaterEqual(row_height, 47)
        self.assertLessEqual(row_height, 49)
        first_meta = page.locator('.timeline-portfolio-meta').first
        self.assertEqual(first_meta.evaluate("el => getComputedStyle(el).backgroundColor"), "rgb(255, 255, 255)")
        self.assertEqual(first_meta.evaluate("el => getComputedStyle(el).borderBottomWidth"), "6px")
        overlap_project = page.locator(f'[data-dashboard-project="{project_id}"]')
        self.physical_click(page, overlap_project.locator('[data-timeline-expand$=":main"]'))
        self.assertGreater(overlap_project.bounding_box()["height"], 48)
        self.physical_click(page, overlap_project.locator('[data-timeline-expand$=":main"]'))
        self.assertLessEqual(overlap_project.bounding_box()["height"], 49)
        self.assertEqual(page.locator('.timeline-portfolio-axis-label span').count(), 0)
        self.assertEqual(page.locator('.timeline-track-label.is-portfolio-label strong').count(), 0)
        parallel_bar = overlap_project.locator('[data-track="parallel"] .timeline-stage').first
        self.assertEqual(parallel_bar.evaluate("el => getComputedStyle(el).height"), "3px")
        self.assertEqual(parallel_bar.evaluate("el => getComputedStyle(el).opacity"), "1")
        self.assertEqual(parallel_bar.evaluate("el => getComputedStyle(el).backgroundColor"), "rgb(217, 140, 0)")
        self.assertEqual(overlap_project.locator('.timeline-past-mask').first.evaluate("el => getComputedStyle(el).display"), "block")
        self.assertNotEqual(
            parallel_bar.evaluate("el => getComputedStyle(el).backgroundColor"),
            chart.locator('.timeline-today-line').evaluate("el => getComputedStyle(el).backgroundColor"),
        )

        scroll = page.locator('[data-portfolio-scroll]')
        today_label = page.locator('.timeline-portfolio-today-label')
        label_top = today_label.bounding_box()["y"]
        label_box = today_label.bounding_box()
        line_box = chart.locator('.timeline-today-line').bounding_box()
        self.assertAlmostEqual(label_box["x"] + label_box["width"] / 2, line_box["x"] + line_box["width"] / 2, delta=1)
        scroll.evaluate("el => el.scrollTop=120")
        page.wait_for_timeout(120)
        self.assertAlmostEqual(today_label.bounding_box()["y"], label_top, delta=1, msg="today label must remain pinned while projects scroll")
        scroll.evaluate("el => el.scrollTop=0")

        detail = overlap_project.locator('.timeline-portfolio-detail')
        self.assertTrue(detail.is_hidden())
        overlap_project.locator('.timeline-portfolio-meta strong').hover()
        page.wait_for_timeout(800)
        self.assertTrue(detail.is_hidden(), "current/upcoming detail must stay hidden before the one-second dwell")
        page.wait_for_timeout(350)
        self.assertTrue(detail.is_visible(), "current/upcoming detail must appear after the one-second dwell")
        risk = overlap_project.locator('.timeline-portfolio-risk')
        risk.hover()
        self.assertTrue(risk.locator('b').is_visible(), "risk red dot must reveal red text immediately")
        self.assertIn("逾期", risk.locator('b').inner_text())
        self.assertIn("本周", risk.locator('b').inner_text())

        unfocused_node = overlap_project.locator(
            '.timeline-dashboard-node, .timeline-node-cluster'
        ).first
        self.assertEqual(overlap_project.locator('.timeline-node-flag').count(), 0)
        unfocused_node.hover()
        self.assertFalse(page.locator('[data-timeline-node-tooltip]').is_hidden(), "collapsed row must keep the existing node tooltip")

        self.physical_click(page, overlap_project.locator('.timeline-portfolio-meta strong'))
        page.wait_for_timeout(220)
        self.assertGreaterEqual(overlap_project.bounding_box()["height"], 167)
        self.assertLessEqual(overlap_project.bounding_box()["height"], 169)
        self.assertEqual(overlap_project.locator('.timeline-node-flag').count(), overlap_project.locator('.timeline-dashboard-node').count())
        focused_node = overlap_project.locator('.timeline-dashboard-node').first
        focused_key = focused_node.get_attribute('data-node-flag-key')
        focused_flag = overlap_project.locator(f'.timeline-node-flag[data-node-flag-key="{focused_key}"]')
        other_flag = overlap_project.locator(
            f'.timeline-node-flag:not(.is-density-hidden):not([data-node-flag-key="{focused_key}"])'
        ).first
        focused_node.hover()
        self.assertTrue(focused_flag.evaluate("el => el.classList.contains('is-probed')"))
        if other_flag.count():
            self.assertFalse(other_flag.evaluate("el => el.classList.contains('is-probed')"))
            other_key = other_flag.get_attribute('data-node-flag-key')
            other_probe = overlap_project.locator(f'.timeline-node-flag-hit.is-active[data-node-flag-key="{other_key}"]')
            self.assertTrue(other_probe.is_visible(), "overlapping flags must expose a non-overlapping pointer probe")
            other_probe.hover(position={"x": 4, "y": 8})
            self.assertTrue(other_flag.evaluate("el => el.classList.contains('is-probed')"), "hovering a flag must promote that exact flag")
            self.assertFalse(focused_flag.evaluate("el => el.classList.contains('is-probed')"))
            self.physical_click(page, other_probe, button="right")
            flag_menu = page.locator('[data-timeline-page="all"] [data-timeline-context]')
            flag_menu.wait_for(state="visible")
            self.assertEqual(flag_menu.get_attribute('data-node-id'), other_flag.get_attribute('data-node-id'))
            self.assertEqual(flag_menu.get_attribute('data-project-id'), other_flag.get_attribute('data-project-id'))
            self.assertEqual(flag_menu.locator('[role="menuitem"]').count(), 6)
            page.keyboard.press('Escape')
            flag_menu.wait_for(state="hidden")
        self.assertTrue(page.locator('[data-timeline-node-tooltip]').is_hidden(), "expanded row must replace the node tooltip with its flag")
        flag_geometry = overlap_project.evaluate("""row => {
          const rr=row.getBoundingClientRect(),byTrack=track=>[...row.querySelectorAll(`.timeline-node-flag[data-node-track="${track}"]`)].filter(el=>getComputedStyle(el).visibility!=='hidden').map(el=>el.getBoundingClientRect()),main=byTrack('main'),parallel=byTrack('parallel'),all=[...main,...parallel];
          const parallelDots=[...row.querySelectorAll('.timeline-stage-lane[data-track="parallel"] .timeline-dashboard-node i')].map(el=>el.getBoundingClientRect()),parallelAxes=[...row.querySelectorAll('.timeline-stage-lane[data-track="parallel"] .timeline-stage')].map(el=>el.getBoundingClientRect());
          const overlapRatios=[main,parallel].flatMap(rects=>{const sorted=rects.slice().sort((a,b)=>a.left-b.left);return sorted.slice(1).map((rect,index)=>Math.max(0,sorted[index].right-rect.left)/rect.width)});
          const probeOverlapCount=[...row.querySelectorAll('.timeline-stage-lane')].reduce((count,lane)=>{const rects=[...lane.querySelectorAll('.timeline-node-flag-hit.is-active')].map(el=>el.getBoundingClientRect()).sort((a,b)=>a.left-b.left);return count+rects.slice(1).filter((rect,index)=>rect.left<rects[index].right-.5).length},0);
          const parallelTop=Math.min(...parallel.map(r=>r.top));
          return {top:Math.min(...all.map(r=>r.top))-rr.top,bottom:rr.bottom-Math.max(...all.map(r=>r.bottom)),maxOverlapRatio:Math.max(0,...overlapRatios),probeOverlapCount,nodeClearance:parallelTop-Math.max(...parallelDots.map(r=>r.bottom)),axisClearance:parallelTop-Math.max(...parallelAxes.map(r=>r.bottom))};
        }""")
        self.assertGreaterEqual(flag_geometry["top"], -1, "main flags must stay inside the expanded row")
        self.assertGreaterEqual(flag_geometry["bottom"], -1, "parallel flags must stay inside the expanded row")
        self.assertAlmostEqual(flag_geometry["top"], flag_geometry["bottom"], delta=6, msg="expanded row must keep symmetric outer whitespace")
        self.assertLessEqual(flag_geometry["maxOverlapRatio"], .51, "visible flags must retain at least half of their horizontal width")
        self.assertEqual(flag_geometry["probeOverlapCount"], 0, "overlapping flags must own disjoint pointer probe regions")
        self.assertGreaterEqual(flag_geometry["nodeClearance"], -1, "parallel flags must begin below their node circles")
        self.assertGreaterEqual(flag_geometry["axisClearance"], 0, "parallel flags must not cover the parallel axis")
        flag_layer = focused_flag.evaluate("el => Number(getComputedStyle(el).zIndex)")
        mask_layer = overlap_project.locator('.timeline-past-mask').first.evaluate("el => Number(getComputedStyle(el).zIndex)")
        today_layer = chart.locator('.timeline-portfolio-today').evaluate("el => Number(getComputedStyle(el).zIndex)")
        self.assertGreater(flag_layer, mask_layer)
        self.assertLess(flag_layer, today_layer)
        probe_layer = overlap_project.locator('.timeline-node-flag-hit.is-active').first.evaluate("el => Number(getComputedStyle(el).zIndex)")
        self.assertGreater(probe_layer, flag_layer)
        self.assertLess(probe_layer, today_layer)
        second_project = page.locator('.timeline-portfolio-project').nth(1)
        self.physical_click(page, second_project.locator('.timeline-portfolio-meta strong'))
        page.wait_for_timeout(220)
        self.assertEqual(page.locator('.timeline-portfolio-project.is-focused').count(), 1)
        self.assertLessEqual(overlap_project.bounding_box()["height"], 49)
        self.assertGreaterEqual(second_project.bounding_box()["height"], 167)
        self.assertLessEqual(second_project.bounding_box()["height"], 169)
        dense_project = page.locator(f'[data-dashboard-project="{dense_project_id}"]')
        dense_project.scroll_into_view_if_needed()
        self.assertEqual(dense_project.locator('.timeline-node-flag').count(), 0)
        self.physical_click(page, dense_project.locator('.timeline-portfolio-meta strong'))
        page.wait_for_function("id => document.querySelectorAll(`[data-dashboard-project=\"${id}\"] .timeline-node-flag.is-density-hidden`).length >= 1", arg=dense_project_id)
        dense_flags = dense_project.locator('.timeline-node-flag')
        dense_horizontal = dense_project.evaluate("""row => {
          const plot=row.querySelector('.timeline-stage-plot').getBoundingClientRect(),flags=[...row.querySelectorAll('.timeline-node-flag')],visible=flags.filter(el=>getComputedStyle(el).visibility!=='hidden'),rects=visible.map(el=>el.getBoundingClientRect()).sort((a,b)=>a.left-b.left);
          const overlapRatios=rects.slice(1).map((rect,index)=>Math.max(0,rects[index].right-rect.left)/rect.width);
          return {inside:rects.every(rect=>rect.left>=plot.left-1&&rect.right<=plot.right+1),visible:visible.map(el=>el.dataset.nodeId),hidden:flags.filter(el=>getComputedStyle(el).visibility==='hidden').length,overlapRatios,firstShift:parseFloat(visible[0].style.getPropertyValue('--timeline-node-flag-shift'))};
        }""")
        self.assertTrue(dense_horizontal["inside"], "adaptive layout must keep visible flags inside the plot")
        self.assertEqual(len(dense_horizontal["visible"]), 3, "a dense exact-date crowd should retain the maximum flags that keep at least half visible")
        self.assertEqual(dense_horizontal["hidden"], 21)
        self.assertTrue(any(ratio > .05 for ratio in dense_horizontal["overlapRatios"]))
        self.assertTrue(all(ratio <= .51 for ratio in dense_horizontal["overlapRatios"]))
        self.assertGreaterEqual(dense_horizontal["firstShift"], -0.5, "the first flag must not be pushed before its first node")
        self.assertEqual(dense_horizontal["visible"][0], dense_flags.first.get_attribute('data-node-id'))
        self.assertEqual(dense_horizontal["visible"][-1], dense_flags.last.get_attribute('data-node-id'))
        dense_probe = dense_flags.nth(6)
        dense_probe_key = dense_probe.get_attribute('data-node-flag-key')
        self.assertTrue(dense_probe.evaluate("el => getComputedStyle(el).visibility === 'hidden'"))
        dense_project.locator(f'.timeline-dashboard-node[data-node-flag-key="{dense_probe_key}"]').focus()
        self.assertTrue(dense_project.locator(f'.timeline-node-flag[data-node-flag-key="{dense_probe_key}"]').evaluate("el => el.classList.contains('is-probed')"))
        self.assertTrue(dense_project.locator(f'.timeline-node-flag[data-node-flag-key="{dense_probe_key}"]').is_visible())
        self.assertEqual(dense_project.locator('.timeline-node-flag.is-probed').count(), 1)

        adaptive_project = page.locator(f'[data-dashboard-project="{adaptive_project_id}"]')
        adaptive_project.scroll_into_view_if_needed()
        self.physical_click(page, adaptive_project.locator('.timeline-portfolio-meta strong'))
        page.wait_for_function("id => document.querySelectorAll(`[data-dashboard-project=\"${id}\"] .timeline-node-flag.is-density-hidden`).length >= 1", arg=adaptive_project_id)
        adaptive_summary = adaptive_project.evaluate("""row => {
          const flags=[...row.querySelectorAll('.timeline-node-flag')],visible=flags.filter(el=>getComputedStyle(el).visibility!=='hidden'),rects=visible.map(el=>el.getBoundingClientRect()).sort((a,b)=>a.left-b.left),overlapRatios=rects.slice(1).map((rect,index)=>Math.max(0,rects[index].right-rect.left)/rect.width);
          return {visible:visible.map(el=>el.dataset.nodeId),first:flags[0].dataset.nodeId,last:flags.at(-1).dataset.nodeId,firstShift:parseFloat(flags[0].style.getPropertyValue('--timeline-node-flag-shift')),overlapRatios};
        }""")
        self.assertGreaterEqual(len(adaptive_summary["visible"]), 2)
        self.assertLess(len(adaptive_summary["visible"]), 7)
        self.assertEqual(adaptive_summary["visible"][0], adaptive_summary["first"], "adaptive sampling must preserve the first temporal endpoint")
        self.assertEqual(adaptive_summary["visible"][-1], adaptive_summary["last"], "adaptive sampling must preserve the last temporal endpoint")
        self.assertGreaterEqual(adaptive_summary["firstShift"], -0.5, "the first parallel flag must start at or after its node")
        self.assertTrue(any(ratio > 0.05 for ratio in adaptive_summary["overlapRatios"]), "moderately crowded flags should be allowed to overlap")
        self.assertTrue(all(ratio <= 0.51 for ratio in adaptive_summary["overlapRatios"]), "no visible flag may be covered by more than half its width")
        adaptive_middle = adaptive_project.locator('.timeline-node-flag.is-density-hidden').first
        adaptive_middle_key = adaptive_middle.get_attribute('data-node-flag-key')
        adaptive_middle = adaptive_project.locator(f'.timeline-dashboard-node[data-node-flag-key="{adaptive_middle_key}"]')
        adaptive_middle.hover()
        self.assertTrue(adaptive_project.locator(f'.timeline-node-flag[data-node-flag-key="{adaptive_middle_key}"]').is_visible(), "hovering a hidden flag's node must temporarily reveal that exact flag")
        for _ in range(6):
            page.locator('[data-timeline-page="all"] [data-portfolio-zoom-in]').evaluate("el => el.click()")
            page.wait_for_timeout(80)
        page.wait_for_function("id => [...document.querySelectorAll(`[data-dashboard-project=\"${id}\"] .timeline-node-flag`)].every(el => getComputedStyle(el).visibility !== 'hidden')", arg=adaptive_project_id)
        self.assertEqual(adaptive_project.locator('.timeline-node-flag:visible').count(), 7, "zooming in must automatically restore flags when enough width becomes available")
        self.physical_click(page, page.locator('[data-timeline-page="all"] [data-portfolio-cancel-zoom]'))
        page.wait_for_function("() => { const chart=document.querySelector('[data-timeline-page=\"all\"] .timeline-portfolio-chart'); return chart && Number(chart.dataset.viewportDays) === Number(chart.dataset.fullDays) }")
        sticky = page.evaluate("""() => ({
          axis:getComputedStyle(document.querySelector('.timeline-portfolio-axis')).position,
          axisLabel:getComputedStyle(document.querySelector('.timeline-portfolio-axis-label')).position,
          meta:getComputedStyle(document.querySelector('.timeline-portfolio-meta')).position
        })""")
        self.assertEqual(sticky, {"axis": "sticky", "axisLabel": "sticky", "meta": "sticky"})

        self.assertFalse(page.locator('.timeline-portfolio-head').is_hidden())
        self.assertTrue(page.locator('.tl-order-note').is_hidden())
        scroll = page.locator('[data-portfolio-scroll]')

        def pointer_date_at(client_x):
            return page.evaluate(
                """x => {
                  const scroll=document.querySelector('[data-portfolio-scroll]');
                  const chart=scroll.querySelector('.timeline-portfolio-chart');
                  const axis=chart.querySelector('.timeline-e-axis');
                  const scrollRect=scroll.getBoundingClientRect();
                  const chartRect=chart.getBoundingClientRect();
                  const axisRect=axis.getBoundingClientRect();
                  const leftWidth=Math.max(0,Math.round(axisRect.left-chartRect.left));
                  const rightWidth=Math.max(0,Math.round(chartRect.right-axisRect.right));
                  const available=Math.max(320,scroll.clientWidth-leftWidth-rightWidth);
                  const ratio=Math.max(0,Math.min(1,(x-scrollRect.left-leftWidth)/available));
                  const days=Number(chart.dataset.viewportDays);
                  const rangeStart=new Date(`${chart.dataset.calendarStart}T00:00:00Z`).getTime();
                  const rangeEnd=new Date(`${chart.dataset.calendarEnd}T00:00:00Z`).getTime();
                  const plotRatio=Math.max(0,Math.min(1,(scroll.scrollLeft+(x-scrollRect.left)-leftWidth)/axisRect.width));
                  return {
                    time:rangeStart+(rangeEnd-rangeStart)*plotRatio,
                    leftWidth,
                    available,
                    axisOffset:Math.round(axisRect.left-chartRect.left),
                    rightWidth,
                    ratio,
                    plotRatio,
                    days,
                    center:chart.dataset.viewportCenter,
                    centerMs:Number(chart.dataset.viewportCenterMs),
                    scrollLeft:scroll.scrollLeft,
                    scrollClientWidth:scroll.clientWidth,
                    chartWidth:chartRect.width
                  };
                }""",
                client_x,
            )

        cancel_zoom = page.locator('[data-portfolio-cancel-zoom]')
        self.assertEqual(cancel_zoom.count(), 1)
        self.assertTrue(cancel_zoom.is_hidden())
        scroll.evaluate("el => { el.scrollTop=80 }")
        page.wait_for_timeout(180)
        scroll_box = scroll.bounding_box()
        geometry = pointer_date_at(scroll_box["x"] + scroll_box["width"] / 2)
        client_x = scroll_box["x"] + geometry["leftWidth"] + geometry["available"] * .35
        page.mouse.move(client_x, scroll_box["y"] + 126)
        page.mouse.wheel(0, -120)
        cancel_zoom.wait_for(state="visible")
        self.assertEqual(cancel_zoom.inner_text(), "取消缩放")
        self.assertEqual(cancel_zoom.evaluate("el => getComputedStyle(el).backgroundColor"), "rgb(229, 72, 77)")
        self.assertLess(cancel_zoom.bounding_box()["x"], page.locator('[data-portfolio-fullscreen]').bounding_box()["x"])
        self.physical_click(page, cancel_zoom)
        page.wait_for_function(
            "() => { const c=document.querySelector('.timeline-portfolio-chart'), b=document.querySelector('[data-portfolio-cancel-zoom]'); return Number(c.dataset.viewportDays) === Number(c.dataset.fullDays) && b?.hidden }"
        )
        self.assertAlmostEqual(page.locator('[data-portfolio-scroll]').evaluate("el => el.scrollTop"), 80, delta=2)

        # AUD-01: three screen-space anchors must retain the same represented date
        # after a wheel zoom.  The project column is wider than the old 220 px
        # constant, so this guards the real rendered geometry rather than a mock.
        for anchor_ratio in (.2, .5, .8):
            page.locator('[data-portfolio-fit]').evaluate("el => el.click()")
            page.wait_for_function(
                "() => { const c=document.querySelector('.timeline-portfolio-chart'); return Number(c.dataset.viewportDays) === Number(c.dataset.fullDays) }"
            )
            scroll_box = scroll.bounding_box()
            geometry = pointer_date_at(scroll_box["x"] + scroll_box["width"] / 2)
            client_x = scroll_box["x"] + geometry["leftWidth"] + geometry["available"] * anchor_ratio
            before_anchor = pointer_date_at(client_x)
            before_days = float(page.locator('.timeline-portfolio-chart').get_attribute("data-viewport-days"))
            page.mouse.move(client_x, scroll_box["y"] + 126)
            page.mouse.wheel(0, -120)
            page.wait_for_function(
                "before => Number(document.querySelector('.timeline-portfolio-chart').dataset.viewportDays) < before",
                arg=before_days,
            )
            after_anchor = pointer_date_at(client_x)
            drift_days = abs(after_anchor["time"] - before_anchor["time"]) / 86400000
            self.assertLessEqual(
                drift_days,
                .15,
                f"zoom anchor {anchor_ratio:.0%} drifted by {drift_days:.2f} days",
            )

        self.physical_click(page, page.locator('[data-portfolio-fullscreen]'))
        page.locator('.timeline-portfolio-card.is-fullscreen').wait_for()
        page.locator('[data-portfolio-fit]').evaluate("el => el.click()")
        page.wait_for_function(
            "() => { const c=document.querySelector('.timeline-portfolio-chart'); return Number(c.dataset.viewportDays) === Number(c.dataset.fullDays) }"
        )
        page.wait_for_timeout(200)
        for zoom_level in range(3):
            scroll = page.locator('[data-portfolio-scroll]')
            scroll_box = scroll.bounding_box()
            geometry = pointer_date_at(scroll_box["x"] + scroll_box["width"] / 2)
            client_x = scroll_box["x"] + geometry["leftWidth"] + geometry["available"] * .5
            before_anchor = pointer_date_at(client_x)
            before_days = float(page.locator('.timeline-portfolio-chart').get_attribute("data-viewport-days"))
            page.mouse.move(client_x, scroll_box["y"] + 126)
            page.mouse.wheel(0, -120)
            page.wait_for_function(
                "before => Number(document.querySelector('.timeline-portfolio-chart').dataset.viewportDays) < before",
                arg=before_days,
            )
            after_anchor = pointer_date_at(client_x)
            drift_days = abs(after_anchor["time"] - before_anchor["time"]) / 86400000
            self.assertLessEqual(
                drift_days,
                .15,
                f"fullscreen zoom level {zoom_level + 1} drifted by {drift_days:.2f} days; before={before_anchor}; after={after_anchor}",
            )
        self.physical_click(page, page.locator('[data-portfolio-fullscreen]'))
        page.wait_for_function("() => !document.querySelector('.timeline-portfolio-card')?.classList.contains('is-fullscreen')")
        scroll = page.locator('[data-portfolio-scroll]')

        initial_days = float(chart.get_attribute("data-viewport-days"))
        page.locator('.timeline-portfolio-meta').first.hover()
        page.mouse.wheel(0, 420)
        page.wait_for_timeout(180)
        self.assertGreater(scroll.evaluate("el => el.scrollTop"), 0, "wheel over the project column must scroll project rows")
        self.assertEqual(float(page.locator('[data-timeline-page="all"] .timeline-portfolio-chart').get_attribute("data-viewport-days")), initial_days, "project-column wheel must not zoom the calendar")
        scroll.evaluate("el => { el.scrollTop=0 }")
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
        self.assertEqual(keys, [], "zoom memory is temporarily disabled")

        self.physical_click(page, page.locator('[data-timeline-tag-context="uncategorized"]'))
        page.locator('[data-timeline-tag-context="uncategorized"].active').wait_for()
        uncategorized_chart = page.locator('.timeline-portfolio-chart')
        uncategorized_days = float(uncategorized_chart.get_attribute("data-viewport-days"))
        self.assertEqual(uncategorized_days, float(uncategorized_chart.get_attribute("data-full-days")))
        axis_detail = page.locator('.timeline-portfolio-axis-detail')
        axis_box = axis_detail.bounding_box()
        page.mouse.move(axis_box["x"] + axis_box["width"] * .55, axis_box["y"] + 54)
        page.mouse.wheel(0, -120)
        page.locator('[data-timeline-tag-context="uncategorized"].active').wait_for()
        keys = page.evaluate("Object.keys(localStorage).filter(key => key.startsWith('flowboard:timeline-viewport:'))")
        self.assertEqual(keys, [])
        self.physical_click(page, page.locator('[data-timeline-tag-context="all"]'))
        page.locator('[data-timeline-tag-context="all"].active').wait_for()
        restored_chart = page.locator('.timeline-portfolio-chart')
        self.assertEqual(float(restored_chart.get_attribute("data-viewport-days")), float(restored_chart.get_attribute("data-full-days")))

        scroll = page.locator('[data-portfolio-scroll]')
        for _ in range(2):
            before_days = float(page.locator('.timeline-portfolio-chart').get_attribute("data-viewport-days"))
            page.locator('[data-portfolio-zoom-in]').evaluate("el => el.click()")
            page.wait_for_function(
                "before => Number(document.querySelector('.timeline-portfolio-chart').dataset.viewportDays) < before",
                arg=before_days,
            )
        node = page.locator('[data-timeline-page="all"] .timeline-dashboard-node').first
        node.evaluate("el => el.scrollIntoView({block:'center',inline:'center'})")
        page.wait_for_timeout(180)
        edge_room = scroll.evaluate("el => ({current:el.scrollLeft,max:el.scrollWidth-el.clientWidth})")
        if edge_room["max"] - edge_room["current"] < 100:
            scroll.evaluate("el => { el.scrollLeft=Math.max(0,el.scrollWidth-el.clientWidth-140) }")
            page.wait_for_timeout(80)
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
        guide_label = guides.locator('.target-label')
        self.assertRegex(guide_label.inner_text(), r'^\d{4}-\d{2}-\d{2} \| [+-]?\d+天$')
        self.assertEqual(guide_label.locator('.target-delta').evaluate("el => getComputedStyle(el).color"), "rgb(255, 77, 90)")
        self.assertGreater(int(guides.evaluate("el => getComputedStyle(el).zIndex")), int(page.locator('.timeline-portfolio-today').evaluate("el => getComputedStyle(el).zIndex")))
        self.assertTrue(guide_label.evaluate("""el => { const r=el.getBoundingClientRect(),previous=el.style.pointerEvents;el.style.pointerEvents='auto';const hit=document.elementFromPoint(r.left+r.width/2,r.top+r.height/2);el.style.pointerEvents=previous;return hit===el||el.contains(hit) }"""), "drag target label must paint above the sticky axis, masks and nodes")
        self.assertEqual(page.locator('.timeline-e-month.is-target').count(), 1)
        self.assertEqual(page.locator('.timeline-e-day-tick.is-target').count(), 1)
        self.assertEqual(page.locator('.timeline-e-day-tick.is-target').inner_text(), "", "drag target must not render the duplicate short-date badge")
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

        single = page.locator('[data-timeline-page="single"] [data-portfolio-scroll]')
        chart = single.locator('.timeline-portfolio-chart')
        chart.wait_for()
        self.assertEqual(chart.locator('.timeline-past-mask').count(), 2)
        self.assertEqual(
            chart.locator('.timeline-past-mask').first.evaluate("el => getComputedStyle(el).backgroundColor"),
            "rgba(255, 255, 255, 0.7)",
        )
        initial_days = float(chart.get_attribute("data-viewport-days"))
        self.assertEqual(initial_days, float(chart.get_attribute("data-full-days")))
        label_before = chart.locator('.timeline-single-track-key').bounding_box()
        box = single.bounding_box()
        page.mouse.move(box["x"] + box["width"] * .72, box["y"] + 36)
        page.mouse.wheel(0, -120)
        page.wait_for_function(
            "before => Number(document.querySelector('[data-timeline-page=single] .timeline-portfolio-chart').dataset.viewportDays) < before",
            arg=initial_days,
        )
        cancel_zoom = page.locator('[data-timeline-page="single"] [data-portfolio-cancel-zoom]')
        cancel_zoom.wait_for(state="visible")
        cancel_box = cancel_zoom.bounding_box()
        transfer_box = page.locator('[data-timeline-page="single"] .timeline-project-tab-actions').bounding_box()
        self.assertIsNotNone(cancel_box)
        self.assertIsNotNone(transfer_box)
        self.assertGreaterEqual(cancel_box["y"], transfer_box["y"] + transfer_box["height"], "cancel zoom must sit below import/export actions instead of being covered by them")
        single = page.locator('[data-timeline-page="single"] [data-portfolio-scroll]')
        label_after = single.locator('.timeline-single-track-key').bounding_box()
        self.assertAlmostEqual(label_after["width"], label_before["width"], delta=.5)
        self.assertAlmostEqual(label_after["x"], label_before["x"], delta=.5)
        single_labels = single.locator('.timeline-e-day-tick b').evaluate_all(
            "els => els.map(el => { const r=el.getBoundingClientRect(); return {left:r.left,right:r.right,text:el.textContent.trim()} }).filter(x => x.text).sort((a,b) => a.left-b.left)"
        )
        self.assertGreater(len(single_labels), 2)
        self.assertTrue(all(current["right"] <= following["left"] + 0.5 for current, following in zip(single_labels, single_labels[1:])))
        self.assertEqual(single.locator('.timeline-e-quarters').count(), 0)
        single_calendar_colors = single.evaluate("""el => ({
          years:getComputedStyle(el.querySelector('.timeline-e-years')).backgroundColor,
          months:getComputedStyle(el.querySelector('.timeline-e-month')).backgroundColor,
          days:getComputedStyle(el.querySelector('.timeline-e-days')).backgroundColor
        })""")
        self.assertEqual(single_calendar_colors["years"], "rgb(38, 60, 98)")
        self.assertNotEqual(single_calendar_colors["months"], "rgba(0, 0, 0, 0)")
        self.assertEqual(single.locator('.timeline-portfolio-today').evaluate("el => getComputedStyle(el).top"), "0px")
        self.assertGreater(int(single.locator('.timeline-portfolio-today').evaluate("el => getComputedStyle(el).zIndex")), 1100)
        for _ in range(5):
            dimensions = single.evaluate("el => ({client:el.clientWidth,scroll:el.scrollWidth})")
            if dimensions["scroll"] > dimensions["client"] + 40:
                break
            box = single.bounding_box()
            page.mouse.move(box["x"] + box["width"] * .72, box["y"] + 36)
            page.mouse.wheel(0, -120)
            page.wait_for_timeout(50)
            single = page.locator('[data-timeline-page="single"] [data-portfolio-scroll]')
        dimensions = single.evaluate("el => ({client:el.clientWidth,scroll:el.scrollWidth})")
        self.assertGreater(dimensions["scroll"], dimensions["client"] + 40)
        ruler = single.locator('.timeline-e-axis')
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

        self.physical_click(page, page.locator('#timelineAllBtn'))
        portfolio = page.locator('[data-timeline-page="all"] .timeline-portfolio-chart')
        portfolio.wait_for()
        self.assertEqual(float(portfolio.get_attribute("data-viewport-days")), float(portfolio.get_attribute("data-full-days")))
        portfolio_labels = portfolio.locator('.timeline-e-day-tick b').evaluate_all(
            "els => els.map(el => { const r=el.getBoundingClientRect(); return {left:r.left,right:r.right,text:el.textContent.trim()} }).filter(x => x.text).sort((a,b) => a.left-b.left)"
        )
        self.assertGreater(len(portfolio_labels), 2)
        self.assertTrue(all(current["right"] <= following["left"] + 0.5 for current, following in zip(portfolio_labels, portfolio_labels[1:])))
        portfolio_calendar_colors = portfolio.evaluate("""el => ({
          years:getComputedStyle(el.querySelector('.timeline-e-years')).backgroundColor,
          months:getComputedStyle(el.querySelector('.timeline-e-month')).backgroundColor,
          days:getComputedStyle(el.querySelector('.timeline-e-days')).backgroundColor
        })""")
        self.assertEqual(portfolio_calendar_colors, single_calendar_colors)
        self.assertEqual(page.locator('.timeline-shared-caption').count(), 0)
        self.assertEqual(portfolio.locator('.timeline-e-quarters').count(), 0)
        self.assertEqual(portfolio.locator('.timeline-portfolio-today').evaluate("el => getComputedStyle(el).top"), "0px")
        self.assertGreater(int(portfolio.locator('.timeline-portfolio-today').evaluate("el => getComputedStyle(el).zIndex")), 1100)
        self.assertFalse(page.locator('[data-portfolio-fullscreen]').is_hidden())
        self.physical_click(page, page.locator('[data-portfolio-fullscreen]'))
        page.locator('.timeline-portfolio-card.is-fullscreen').wait_for()
        uncategorized_context = page.locator('.timeline-portfolio-card.is-fullscreen [data-timeline-tag-context="uncategorized"]')
        self.physical_click(page, uncategorized_context)
        page.locator('.timeline-portfolio-card.is-fullscreen [data-timeline-tag-context="uncategorized"].active').wait_for()
        fullscreen_chart = page.locator('.timeline-portfolio-card.is-fullscreen .timeline-portfolio-chart')
        self.assertEqual(float(fullscreen_chart.get_attribute("data-viewport-days")), float(fullscreen_chart.get_attribute("data-full-days")))
        self.assertEqual(page.locator('.timeline-portfolio-card.is-fullscreen').count(), 1)
        self.assertEqual(page.locator('.timeline-portfolio-card.is-fullscreen').evaluate("el => getComputedStyle(el).display"), "grid")
        cluster = page.locator('.timeline-portfolio-card.is-fullscreen .timeline-node-cluster[aria-label*="较早逾期节点"][aria-label*="逾期节点"]')
        self.assertEqual(cluster.count(), 1)
        self.assertIsNone(cluster.get_attribute("title"), "dense clusters must not create a second, uncontrolled browser tooltip")
        self.assertEqual(cluster.get_attribute("tabindex"), "0")
        cluster.hover()
        cluster_tip = page.locator('[data-timeline-node-tooltip]')
        cluster_tip.wait_for(state="visible")
        cluster_metrics = cluster_tip.evaluate("""el => {
          const r=el.getBoundingClientRect(),axis=document.querySelector('.timeline-portfolio-card.is-fullscreen .timeline-portfolio-axis')?.getBoundingClientRect(),meta=document.querySelector('.timeline-portfolio-card.is-fullscreen .timeline-portfolio-project:has(.timeline-node-cluster[aria-describedby="timelineNodeTooltip"]) .timeline-portfolio-meta')?.getBoundingClientRect();
          const overlaps=(a,b)=>Boolean(a&&b&&a.left<b.right&&a.right>b.left&&a.top<b.bottom&&a.bottom>b.top);
          const previous=el.style.pointerEvents;el.style.pointerEvents='auto';const hit=document.elementFromPoint(r.left+r.width/2,r.top+r.height/2);el.style.pointerEvents=previous;
          return {topmost:hit===el||el.contains(hit),axisOverlap:overlaps(r,axis),metaOverlap:overlaps(r,meta),left:r.left,right:r.right,top:r.top,bottom:r.bottom,width:innerWidth,height:innerHeight};
        }""")
        self.assertTrue(cluster_metrics["topmost"], "cluster tooltip must paint above all dashboard layers")
        self.assertFalse(cluster_metrics["axisOverlap"], "cluster tooltip must stay below the sticky calendar axis")
        self.assertFalse(cluster_metrics["metaOverlap"], "cluster tooltip must stay right of the sticky project column")
        self.assertGreaterEqual(cluster_metrics["left"], 0)
        self.assertLessEqual(cluster_metrics["right"], cluster_metrics["width"])
        self.assertGreaterEqual(cluster_metrics["top"], 0)
        self.assertLessEqual(cluster_metrics["bottom"], cluster_metrics["height"])
        layers = page.evaluate("""() => Object.fromEntries(Object.entries({tooltip:'[data-timeline-node-tooltip]',menu:'[data-timeline-context]',guides:'[data-portfolio-drag-guides]',loupe:'[data-dashboard-loupe]',today:'.timeline-portfolio-today',past:'.timeline-past-mask',axis:'.timeline-portfolio-axis',meta:'.timeline-portfolio-meta'}).map(([key,selector])=>[key,Number(getComputedStyle(document.querySelector('.timeline-portfolio-card.is-fullscreen '+selector)||document.querySelector(selector)).zIndex)||0]))""")
        self.assertGreater(layers["tooltip"], layers["menu"])
        self.assertGreater(layers["menu"], layers["guides"])
        self.assertEqual(layers["guides"], layers["loupe"])
        self.assertGreater(layers["guides"], layers["today"])
        self.assertGreater(layers["today"], layers["past"])
        self.assertGreater(layers["past"], layers["axis"])
        self.assertGreater(layers["axis"], layers["meta"])
        page.mouse.move(10, 10)
        cluster_tip.wait_for(state="hidden")
        self.physical_click(page, page.locator('[data-portfolio-fullscreen]'))
        self.assertEqual(page.locator('.timeline-portfolio-card.is-fullscreen').count(), 0)

        crowded = page.locator('.timeline-node-cluster[aria-label*="较早逾期节点"][aria-label*="逾期节点"]')
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
        self.assertEqual(row.locator('.timeline-row-menu, [data-timeline-archive]').count(), 0, "all-project rows must not expose archive")
        self.open_cp4_single(page, project_id)
        single_card = page.locator('[data-timeline-page="single"] > .timeline-project-card')
        single_card.locator('.tl-project-menu summary').click()
        self.assertEqual(single_card.locator(f'[data-timeline-archive="{project_id}"]').count(), 1, "archive remains available on the single-project page")
        page.once("dialog", lambda dialog: dialog.accept())
        with page.expect_response(lambda response: response.request.method == "POST" and response.url.endswith(f"/timeline/projects/{project_id}/archive")) as archived:
            single_card.locator(f'[data-timeline-archive="{project_id}"]').click()
        self.assertEqual(archived.value.status, 200)
        page.locator('[data-timeline-page="home"]').wait_for()

        self.physical_click(page, page.locator('#timelineAllBtn'))
        page.locator('[data-timeline-page="all"] .timeline-portfolio-chart').wait_for()

        self.physical_click(page, page.locator('[data-timeline-tag-context="archived"]'))
        page.locator('[data-timeline-tag-context="archived"].active').wait_for()
        archived_chart = page.locator('.timeline-portfolio-chart')
        self.assertEqual(float(archived_chart.get_attribute("data-viewport-days")), float(archived_chart.get_attribute("data-full-days")))
        archived_row = page.locator(f'[data-timeline-page="all"] [data-dashboard-project="{project_id}"]')
        archived_row.wait_for()
        self.assertIn("已归档 · 只读", archived_row.inner_text())
        self.assertEqual(archived_row.locator('[data-dashboard-submit], [data-timeline-archive], [data-timeline-context]').count(), 0)
        archived_axis = page.locator('.timeline-portfolio-axis-detail')
        archived_axis_box = archived_axis.bounding_box()
        page.mouse.move(archived_axis_box["x"] + archived_axis_box["width"] * .55, archived_axis_box["y"] + 80)
        page.mouse.wheel(0, -120)
        page.wait_for_timeout(80)
        self.assertNotIn("flowboard:timeline-viewport:", page.evaluate("Object.keys(localStorage).join('|')"))

        self.physical_click(page, page.locator('#archivedBtn'))
        archive_page_row = page.locator(f'[data-timeline-page="archived"] .tl-archive-row:has-text("CP4 重叠双轨")')
        archive_page_row.wait_for()
        self.assertEqual(page.locator('.timeline-shell>header, #timelineClose').count(), 0)
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
        markers = page.locator('[data-timeline-page="single"] > .timeline-project-card > header .timeline-risk-markers')
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
        page.wait_for_function("document.querySelector('#timelineModal').hidden")
        page.locator("#toast", has_text="导入完成").wait_for()
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
        self.physical_click(page, page.locator("[data-timeline-export]"))
        page.locator('#timelineModal [data-timeline-export-run]').wait_for()
        self.record_mouse_sequence(page, "[data-timeline-export-run]")
        with page.expect_response(lambda response: response.url.endswith("/timeline/export") and response.request.method == "POST"):
            self.physical_click(page, page.locator("[data-timeline-export-run]"))
        self.assertEqual(page.evaluate("window.__timelineClicks"), ["mousedown", "mouseup", "click"])
        link = page.locator("[data-timeline-download]")
        link.wait_for()
        exported = responses[-1].json()
        with page.expect_download() as pending:
            self.physical_click(page, link)
        download = pending.value
        raw = Path(download.path()).read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), exported["sha256"])
        self.assertEqual(parse_upload("timeline.xlsx", raw)["headers"], self.timeline_export_headers())
        page.wait_for_function("document.querySelector('#timelineModal').hidden")
        self.assert_clean_browser(page); context.close()

    def test_timeline_export_reimport_new_workspace(self):
        self.seed_timeline(name="跨空间往返")
        source_context, source = self.login("u1")
        self.open_timeline_home(source)
        self.physical_click(source, source.locator("[data-timeline-export]"))
        source.locator('#timelineModal [data-timeline-export-run]').wait_for()
        with source.expect_response(lambda response: response.url.endswith("/timeline/export")):
            self.physical_click(source, source.locator("[data-timeline-export-run]"))
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
        page.wait_for_function("document.querySelector('#timelineModal').hidden")
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
        save_button = page.locator('[data-timeline-submit]')
        self.assertEqual(save_button.inner_text(), "保存")
        self.assertAlmostEqual(save_button.bounding_box()["width"], 120, delta=1)
        self.assertTrue(save_button.is_disabled())
        self.assertTrue(page.locator('[data-timeline-discard]').is_hidden())
        self.assertTrue(page.locator('[data-timeline-undo]').is_hidden())
        self.assertEqual(page.locator('[data-timeline-review], [data-timeline-correct]').count(), 0)
        row.locator('[data-editor-field="done_at"]').select_option("true")
        self.assertEqual(page.locator('[data-timeline-draft-count]').inner_text(), "1 项草稿")
        self.assertTrue(page.locator('[data-timeline-discard]').is_visible())
        self.assertTrue(page.locator('[data-timeline-undo]').is_hidden())
        self.assertFalse(save_button.is_disabled())
        with page.expect_response(lambda response: response.request.method == "POST" and response.url.endswith("/timeline/batches")) as submitted:
            self.physical_click(page, save_button)
        self.assertEqual(submitted.value.status, 200)
        self.assertEqual(page.locator('[data-timeline-draft-count]').inner_text(), "0 项草稿")
        self.assertTrue(page.locator('[data-timeline-discard]').is_hidden())
        self.assertTrue(page.locator('[data-timeline-undo]').is_visible())
        self.assertEqual(page.locator('[data-timeline-undo]').inner_text(), "撤销")
        self.assertTrue(page.locator('[data-timeline-submit]').is_disabled())
        db = connect(self.db_path)
        try:
            self.assertIsNotNone(db.execute("SELECT done_at FROM timeline_nodes WHERE id=2 AND project_id=?", (project_id,)).fetchone()[0])
            self.assertEqual(db.execute("SELECT COUNT(*) FROM timeline_change_batches WHERE project_id=? AND change_kind!='undo'", (project_id,)).fetchone()[0], 1)
        finally:
            db.close()
        with page.expect_response(lambda response: response.request.method == "POST" and response.url.endswith("/timeline/batches/undo")) as undone:
            self.physical_click(page, page.locator('[data-timeline-undo]'))
        self.assertEqual(undone.value.status, 200)
        self.assertTrue(page.locator('[data-timeline-undo]').is_hidden())
        self.assertTrue(page.locator('[data-timeline-discard]').is_hidden())
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
        self.assertTrue(page.locator('[data-timeline-undo]').is_hidden(), "undo lifetime must not survive refresh")
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
        self.assertEqual(page.locator('[data-timeline-page="single"] .timeline-today-line').get_attribute("data-today"), today)
        self.assertIn("今天", page.locator('[data-timeline-page="single"] .timeline-portfolio-today-label').inner_text())
        self.assertGreater(card.locator('[data-stage-interval]').count(), 0)
        self.physical_click(page, card.locator('[data-timeline-expand]').first)
        self.assertEqual(card.locator('[data-timeline-expand]').first.get_attribute("aria-expanded"), "true")
        self.zoom_single_until_node_visible(page)
        node = card.locator('.timeline-dashboard-node').first
        self.physical_click(page, node, button="right")
        self.assertEqual(page.locator('[data-timeline-context] [role="menuitem"]').count(), 6)
        self.physical_click(page, page.locator('[data-timeline-context] [data-draft-action="done"]'))
        single_draft_actions = page.locator('[data-single-dashboard-draft-actions]')
        self.assertTrue(single_draft_actions.is_visible())
        self.assertIn("放弃", single_draft_actions.inner_text())
        self.assertIn("更新", single_draft_actions.inner_text())
        leave_dialogs = []
        def accept_dashboard_leave(dialog):
            leave_dialogs.append(dialog.message)
            dialog.accept()
        page.once("dialog", accept_dashboard_leave)
        self.physical_click(page, page.locator('#timelineAllBtn'))
        page.locator('[data-timeline-page="all"] [data-dashboard-project]').first.wait_for()
        self.assertEqual(leave_dialogs, ['有尚未提交的项目时间表草稿，确定放弃并离开？'])
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
        source.wait_for_function("document.querySelector('#timelineModal').hidden")
        self.assertNotEqual(self.timeline_content_hash(), source_before)
        self.physical_click(source, source.locator('[data-timeline-export]'))
        source.locator('#timelineModal [data-timeline-export-run]').wait_for()
        with source.expect_response(lambda response: response.request.method == "POST" and response.url.endswith("/timeline/export")) as exported_response:
            self.physical_click(source, source.locator('[data-timeline-export-run]'))
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
        target.wait_for_function("document.querySelector('#timelineModal').hidden")
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
        self.extend_cp4_stage_intervals(project_id)
        context, page = self.login("u1")
        self.open_cp4_single(page, project_id)
        card = page.locator('[data-timeline-page="single"] > .timeline-project-card')
        canvas = card.locator('.timeline-portfolio-chart')
        self.assertEqual(card.evaluate("node => getComputedStyle(node).backgroundColor"), "rgb(255, 255, 255)")
        self.assertEqual(canvas.evaluate("node => getComputedStyle(node).backgroundColor"), "rgb(245, 245, 247)")
        self.assertEqual(page.locator('[data-theme], [data-dark-mode], .theme-toggle').count(), 0)
        labels = set(card.locator('[data-stage-interval] b').all_inner_texts())
        self.assertTrue({"创意", "设计", "开发", "测试", "量产"}.issubset(labels))
        self.assertIn("今天", card.locator(".timeline-portfolio-today-label").inner_text())
        self.assert_clean_browser(page); context.close()

    def test_v17_shared_tags_and_personal_all_order_real_drag(self):
        project_ids = [self.seed_timeline(name=f"v17 项目 {index}") for index in range(1, 4)]
        context, page = self.login("u1")
        page.locator("#timelineTagsBtn").click()
        self.assertEqual(page.locator('.timeline-shell>header, #timelineClose').count(), 0)
        page.locator('[data-tag-create-open]').click()
        page.locator('[data-timeline-tag-create] input[name="name"]').fill("喜爱")
        with page.expect_response(lambda response: response.request.method == "POST" and response.url.endswith("/timeline/tags")) as created:
            page.locator('[data-timeline-tag-create] button[type="submit"]').click()
        self.assertEqual(created.value.status, 201)
        page.locator('.tl-tag-workbench h2', has_text="喜爱").wait_for()

        active_row = page.locator('.tl-tag-row.active')
        active_row.hover()
        active_row.locator('[data-tag-rename-open]').click()
        active_row.locator('[data-tag-rename-form] input[name="name"]').fill("喜爱更新")
        with page.expect_response(lambda response: response.request.method == "PATCH" and "/timeline/tags/" in response.url) as renamed:
            active_row.locator('[data-tag-rename-form] button[type="submit"]').click()
        self.assertEqual(renamed.value.status, 200)
        page.locator('.tl-tag-workbench h2', has_text="喜爱更新").wait_for()

        page.locator('[data-tag-create-open]').click()
        page.locator('[data-timeline-tag-create] input[name="name"]').fill("临时删除")
        with page.expect_response(lambda response: response.request.method == "POST" and response.url.endswith("/timeline/tags")) as temporary:
            page.locator('[data-timeline-tag-create] button[type="submit"]').click()
        self.assertEqual(temporary.value.status, 201)
        page.locator('.tl-tag-workbench h2', has_text="临时删除").wait_for()
        active_row = page.locator('.tl-tag-row.active')
        active_row.hover()
        delete_open = active_row.locator('[data-tag-delete-open]')
        delete_style = delete_open.evaluate("node => ({size: parseFloat(getComputedStyle(node).fontSize), weight: Number(getComputedStyle(node).fontWeight)})")
        self.assertGreaterEqual(delete_style["size"], 20)
        self.assertGreaterEqual(delete_style["weight"], 800)
        delete_open.click()
        with page.expect_response(lambda response: response.request.method == "DELETE" and "/timeline/tags/" in response.url) as deleted:
            active_row.locator('[data-tag-delete]').click()
        self.assertEqual(deleted.value.status, 200)
        page.locator('.tl-tag-workbench h2', has_text="喜爱更新").wait_for()

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
        self.assertIn("active", page.locator('[data-timeline-tag-context="mine"]').get_attribute("class") or "", "fresh portfolio entry defaults to My Projects")
        page.locator('[data-timeline-tag-context="all"]').click()
        page.locator('.timeline-portfolio-chart').wait_for()
        page.locator("#timelineWeekBtn").click()
        self.assertIn("active", page.locator('[data-timeline-tag-context="all"]').get_attribute("class") or "", "manual tag selection persists across portfolio entries")
        page.locator("#timelineAllBtn").click()
        self.assertEqual(page.locator('.timeline-portfolio-chart').count(), 1)
        rows = page.locator('[data-order-list="all"] > [data-order-project]')
        self.assertEqual(rows.count(), 3)
        before = [int(value) for value in rows.evaluate_all("nodes => nodes.map(node => node.dataset.orderProject)")]
        source_grip = rows.nth(2).locator('.tl-order-grip')
        page.evaluate("""() => { window.__orderAnimations=[]; const nativeAnimate=Element.prototype.animate; Element.prototype.animate=function(frames,options){ if(this.matches?.('[data-order-project]'))window.__orderAnimations.push({frames:[...frames].map(frame=>frame.transform||''),duration:Number(options?.duration)||0,easing:options?.easing||''}); return nativeAnimate.call(this,frames,options) } }""")
        source_box, target_box = source_grip.bounding_box(), rows.nth(0).bounding_box()
        page.mouse.move(source_box["x"] + source_box["width"] / 2, source_box["y"] + source_box["height"] / 2)
        page.evaluate("""window.__orderPointerEvents=[];for(const type of ['pointerdown','pointermove','pointerup'])document.addEventListener(type,event=>{if(type==='pointerup'||event.target.closest?.('.tl-order-grip'))window.__orderPointerEvents.push(type)},true)""")
        with page.expect_response(lambda response: response.request.method == "PUT" and response.url.endswith("/timeline/order")) as ordered:
            page.mouse.down()
            page.mouse.move(target_box["x"] + target_box["width"] / 2, target_box["y"] + target_box["height"] / 2, steps=12)
            drag_float = page.locator('.timeline-order-drag-float')
            drag_float.wait_for()
            self.assertEqual(drag_float.evaluate("node => getComputedStyle(node).opacity"), "1", "custom D drag layer remains fully opaque")
            self.assertEqual(drag_float.evaluate("node => getComputedStyle(node).transform"), "none", "custom D drag layer has no scale or rotation")
            page.mouse.up()
        self.assertEqual(ordered.value.status, 200)
        page.locator("#toast", has_text="你的项目顺序已保存").wait_for()
        self.assertEqual(page.locator('.timeline-order-drag-float').count(), 0)
        after = [int(value) for value in page.locator('[data-order-list="all"] > [data-order-project]').evaluate_all("nodes => nodes.map(node => node.dataset.orderProject)")]
        self.assertEqual(after[0], before[2])
        events = page.evaluate("window.__orderPointerEvents")
        self.assertEqual(events[0], "pointerdown")
        self.assertIn("pointermove", events)
        self.assertEqual(events[-1], "pointerup")
        motions = page.evaluate("window.__orderAnimations")
        self.assertTrue(any(motion["duration"] == 90 and motion["easing"] == "linear" and motion["frames"][-1] == "translateY(0)" for motion in motions), "D motion uses a real 90ms linear FLIP displacement")
        self.assertFalse(any("scale" in frame or "rotate" in frame for motion in motions for frame in motion["frames"]), "D motion has no scale, rotation or bounce")
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
        self.assertIn("active", member_page.locator('[data-timeline-tag-context="mine"]').get_attribute("class") or "", "tag memory is isolated by user")
        member_page.locator('[data-timeline-tag-context="all"]').click()
        member_page.locator('[data-timeline-tag-context="all"].active').wait_for()
        member_page.locator('.timeline-portfolio-chart').wait_for()
        member_order = [int(value) for value in member_page.locator('[data-order-list="all"] > [data-order-project]').evaluate_all("nodes => nodes.map(node => node.dataset.orderProject)")]
        self.assertEqual(member_order, project_ids)
        self.assertNotEqual(member_order, after)
        self.assert_clean_browser(member_page); member_context.close()


if __name__ == "__main__":
    unittest.main()
