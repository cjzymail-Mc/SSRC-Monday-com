"""Gate5 CP2 新增回归（只增不改删）：登录默认落「我的工作」主页 + 主页版式/入口。

依据 feature-01/11-GATE5_UX_REALIGNMENT_TASK.md §6/§12 与（Gate5静态稿·终稿）屏A。
独立 harness，不继承 test_timeline_e2e（避免父类用例被收集双跑）。
"""

import os
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

from flowboard.database import connect, migrate
from server import create_server


class Gate5HomeE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="gate5-home-e2e-")
        self.db_path = str(Path(self.temp.name) / "flowboard.db")
        os.environ["FLOWBOARD_INITIAL_PASSWORD"] = "test-password"
        migrate(self.db_path, initial_password="test-password")
        db = connect(self.db_path)
        db.execute("INSERT INTO users SELECT 'u2','u2','成员',password_hash,NULL,NULL,1,'2026-01-01T00:00:00+00:00' FROM users WHERE id='u1'")
        db.execute("INSERT INTO workspace_memberships VALUES (1,'u2','member')")
        db.execute("INSERT INTO users SELECT 'u3','u3','只读',password_hash,NULL,NULL,1,'2026-01-01T00:00:00+00:00' FROM users WHERE id='u1'")
        db.execute("INSERT INTO workspace_memberships VALUES (1,'u3','viewer')")
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
        page.on("console", lambda message: page.flowboard_console_errors.append(message.text) if message.type == "error" else None)
        page.on("pageerror", lambda error: page.flowboard_page_errors.append(str(error)))
        page.goto(self.base)
        page.locator("#loginUser").fill(username)
        page.locator("#loginPassword").fill("test-password")
        page.locator("#loginForm button[type=submit]").click()
        page.locator("#currentUser > span:not(.avatar)").wait_for()
        page.locator("#loadState", has_text="刚刚同步").wait_for()
        page.flowboard_console_errors.clear()
        page.flowboard_page_errors.clear()
        return context, page

    def assert_clean_browser(self, page):
        self.assertEqual(page.flowboard_page_errors, [])
        self.assertEqual(page.flowboard_console_errors, [])

    @staticmethod
    def physical_click(page, locator, button="left"):
        box = locator.bounding_box()
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.mouse.down(button=button)
        page.mouse.up(button=button)

    def seed_timeline(self, created_by="u1", name="落地项目"):
        db = connect(self.db_path)
        try:
            now = "2026-08-20T00:00:00+00:00"
            cur = db.execute("INSERT INTO timeline_projects(workspace_id,name,created_by,version,created_at,updated_at) VALUES (1,?,?,1,?,?)", (name, created_by, now, now))
            project_id = cur.lastrowid
            for track, stage, node_name, date in (("main", "创意", "A1", "2026-08-01"), ("main", "设计", "A2", "2026-08-05"), ("parallel", "测试", "P1", "2026-08-03")):
                db.execute("INSERT INTO timeline_nodes(project_id,track,stage,name,date,initial_date,remark,version,created_at,updated_at) VALUES (?,?,?,?,?,?,'',1,?,?)", (project_id, track, stage, node_name, date, date, now, now))
            db.commit()
            return project_id
        finally:
            db.close()

    def seed_cp4_dashboard_projects(self):
        today = datetime.now(timezone(timedelta(hours=8))).date()
        db = connect(self.db_path)
        try:
            now = datetime.now(timezone.utc).isoformat()
            projects = []
            fixtures = (
                ("CP4 重叠双轨", (("main", "创意", "主线一", today), ("main", "设计", "主线二", today), ("parallel", "测试", "并行一", today))),
                ("CP4 较早项目", (("main", "创意", "较早开始", today - timedelta(days=20)), ("main", "设计", "下一节点", today + timedelta(days=8)))),
            )
            for project_name, nodes in fixtures:
                cur = db.execute("INSERT INTO timeline_projects(workspace_id,name,created_by,version,created_at,updated_at) VALUES (1,?,'u1',1,?,?)", (project_name, now, now))
                project_id = cur.lastrowid
                projects.append(project_id)
                for track, stage, node_name, node_date in nodes:
                    value = node_date.isoformat()
                    db.execute("INSERT INTO timeline_nodes(project_id,track,stage,name,date,initial_date,remark,version,created_at,updated_at) VALUES (?,?,?,?,?,?,'',1,?,?)", (project_id, track, stage, node_name, value, value, now, now))
            db.commit()
            return projects, today.isoformat()
        finally:
            db.close()

    def test_gate5_default_lands_timeline_home_when_projects_exist(self):
        """有项目且可写：登录后默认落「我的工作」主页；经典看板区块隐藏但 #boardList 留在 DOM。"""
        self.seed_timeline(created_by="u1", name="落地项目")
        context, page = self.login("u1")
        page.locator('[data-timeline-page="home"]').wait_for()
        self.assertFalse(page.locator("#boardWorkspace").is_visible())
        self.assertFalse(page.locator(".breadcrumbs").is_visible())
        self.assertGreater(page.locator(".top-actions").bounding_box()["x"], 700)
        self.assertEqual(page.locator("#boardList").count(), 1)
        self.assertFalse(page.locator("#boardList").is_visible())
        self.assertTrue(page.locator("#dashboardBtn").is_visible())
        self.assertIn("落地项目", page.locator('[data-timeline-section="mine"]').inner_text())
        self.assertIn("我的项目", page.locator('[data-timeline-kpi="mine"]').inner_text())
        self.assert_clean_browser(page)
        # 返回按钮只能回「我的工作」，不得重新暴露经典看板。
        self.physical_click(page, page.locator("#timelineAllBtn"))
        page.locator('[data-timeline-page="all"]').wait_for()
        self.physical_click(page, page.locator("#timelineClose"))
        page.locator('[data-timeline-page="home"]').wait_for()
        self.assertFalse(page.locator("#boardWorkspace").is_visible())
        self.assert_clean_browser(page); context.close()

    def test_gate5_default_lands_empty_timeline_without_projects(self):
        """无时间线项目也默认进入时间管理空态，经典主页保持隐藏。"""
        context, page = self.login("u1")
        page.locator('[data-timeline-page="home"]').wait_for()
        self.assertFalse(page.locator("#boardWorkspace").is_visible())
        self.assertIn("暂无负责项目", page.locator('[data-timeline-section="mine"]').inner_text())
        self.assertEqual(page.locator('[data-timeline-create] input[name="name"]').get_attribute("maxlength"), "200")
        self.assert_clean_browser(page); context.close()

    def test_gate5_sidebar_collapses_to_icons_and_persists(self):
        """侧栏收起后仅保留图标，并记住个人偏好；项目菜单不再挂载。"""
        self.seed_timeline(created_by="u1", name="侧栏项目")
        context, page = self.login("u1")
        page.locator('[data-timeline-page="home"]').wait_for()
        self.assertEqual(page.locator("#timelineProjectNav").count(), 0)
        expanded_width = page.locator("#appSidebar").bounding_box()["width"]
        self.physical_click(page, page.locator("#sidebarToggle"))
        page.locator("#appSidebar.is-collapsed").wait_for()
        page.wait_for_timeout(360)
        sidebar_box = page.locator("#appSidebar").bounding_box()
        toggle_box = page.locator("#sidebarToggle").bounding_box()
        self.assertAlmostEqual(sidebar_box["width"], 64, delta=1)
        self.assertLess(sidebar_box["width"], expanded_width - 100)
        self.assertAlmostEqual(toggle_box["y"] + toggle_box["height"] / 2, sidebar_box["y"] + sidebar_box["height"] / 2, delta=2)
        self.assertAlmostEqual(toggle_box["width"], 27, delta=1)
        self.assertAlmostEqual(toggle_box["height"], 58, delta=1)
        self.assertGreater(float(page.locator("#sidebarToggle").evaluate("el => getComputedStyle(el).borderRadius").replace("px", "")), 20)
        self.assertFalse(page.locator("#timelineAllBtn .nav-label").is_visible())
        self.assertTrue(page.locator("#timelineAllBtn .nav-icon").is_visible())
        page.reload()
        page.locator("#appSidebar.is-collapsed").wait_for()
        self.assertFalse(page.locator("#boardWorkspace").is_visible())
        self.assert_clean_browser(page); context.close()

    def test_gate5_home_kpi_tabs_feed_and_drilldown(self):
        """主页版式：KPI 四格 + 分区标签 + 成员长条药丸下钻 + 右栏动态随标签联动。"""
        (project_id, _), _today = self.seed_cp4_dashboard_projects()
        for index in range(9):
            self.seed_timeline(created_by="u1", name=f"折叠压力项目 {index + 1:02d}")
        context, page = self.login("u1")
        page.locator('[data-timeline-page="home"]').wait_for()
        self.assertEqual(page.locator("#breadcrumbBoard").inner_text(), "我的工作")
        self.assertEqual(page.locator('[data-timeline-page="home"] h1').inner_text(), "我的工作")
        self.assertEqual(page.locator('[data-timeline-mode="home"] > .timeline-toolbar').count(), 0)
        self.assertEqual(page.locator('[data-timeline-mode="home"] > .timeline-transfer').count(), 0)
        self.assertEqual(page.locator(".tl-home-head [data-timeline-import-file]").count(), 1)
        self.assertEqual(page.locator(".tl-home-head [data-timeline-export]").count(), 1)
        self.assertTrue(page.locator(".tl-home-head [data-timeline-create]").is_visible())
        self.assertEqual(page.locator("[data-timeline-kpi]").count(), 4)
        kpi_widths = page.locator("[data-timeline-kpi]").evaluate_all("nodes => nodes.map(node => node.getBoundingClientRect().width)")
        self.assertLessEqual(max(kpi_widths) - min(kpi_widths), 1)
        self.assertIn("我的项目（11）", page.locator('[data-timeline-tab="mine"]').inner_text())
        self.assertEqual(page.locator('[data-timeline-section="mine"] [data-project-choice]').count(), 11)
        self.assertIn("今日团队动态", page.locator('[data-timeline-kpi="feed"]').inner_text())
        # 切到团队项目：成员长条 + 每项目一枚药丸（全 DOM 唯一下钻钩子）
        page.locator('[data-timeline-tab="team"]').click()
        self.assertFalse(page.locator('[data-timeline-section="team"]').is_hidden())
        self.assertGreaterEqual(page.locator(".tl-mrow").count(), 2)
        pill = page.locator(f'[data-timeline-member-open="{project_id}"]')
        self.assertEqual(pill.count(), 1)
        member_toggle = page.locator('[data-timeline-member-toggle]')
        self.assertEqual(member_toggle.count(), 1)
        self.assertIn("显示全部（剩余 1 个）", member_toggle.inner_text())
        self.assertEqual(page.locator('[data-timeline-section="team"] [data-timeline-member-open]:visible').count(), 10)
        self.physical_click(page, member_toggle)
        self.assertEqual(page.locator('[data-timeline-section="team"] [data-timeline-member-open]:visible').count(), 11)
        self.assertEqual(member_toggle.inner_text(), "收起项目")
        self.physical_click(page, member_toggle)
        self.assertEqual(page.locator('[data-timeline-section="team"] [data-timeline-member-open]:visible').count(), 10)
        self.assertIn("团队 · 最近 20 条", page.locator("[data-timeline-feed-scope]").inner_text())
        self.assertTrue(page.locator('[data-timeline-feed="team"]').is_visible())
        # 药丸下钻 → 单项目仪表盘
        self.physical_click(page, pill)
        page.locator(f'[data-timeline-page="single"] [data-dashboard-project="{project_id}"]').wait_for()
        # KPI 下钻：团队类 KPI → 团队项目标签
        page.locator('[data-timeline-mode-target="home"]').click()
        page.locator('[data-timeline-page="home"]').wait_for()
        page.locator('[data-timeline-kpi="members"]').click()
        page.locator('[data-timeline-section="team"]').wait_for(state="visible")
        self.assertTrue(page.locator('[data-timeline-section="mine"]').is_hidden())
        self.assertFalse(page.locator('[data-timeline-section="team"]').is_hidden())
        self.assert_clean_browser(page); context.close()

    def test_gate5_single_dashboard_visual_alignment_and_real_drag(self):
        """屏B：节点/阶段条同轴、长文案不常驻；右键一次性解锁后真实拖动、放大带、草稿与提交闭环。"""
        project_id = self.seed_timeline(created_by="u1", name="拖拽手感项目")
        context, page = self.login("u1")
        page.locator('[data-timeline-page="home"]').wait_for()
        self.physical_click(page, page.locator(f'[data-timeline-open="single"][data-project-id="{project_id}"]'))
        card = page.locator(f'[data-dashboard-project="{project_id}"]')
        card.wait_for()

        node = card.locator('.timeline-dashboard-node[data-node-date="2026-08-01"]')
        bar = card.locator('[data-stage-interval][data-stage="创意"]')
        node_box, bar_box = node.bounding_box(), bar.bounding_box()
        self.assertLessEqual(abs((node_box["y"] + node_box["height"] / 2) - (bar_box["y"] + bar_box["height"] / 2)), 1.5)
        tip = node.locator(":scope > span")
        self.assertTrue(tip.is_hidden(), "节点长名称默认不得常驻挤压年度轴")
        self.assertIsNone(node.get_attribute("title"), "节点信息只保留自定义悬停卡，不再叠加浏览器原生 title")
        self.assertGreaterEqual(card.locator(".timeline-month-ruler span").count(), 1)

        batch_requests = []
        page.on("request", lambda request: batch_requests.append(request) if request.method == "POST" and request.url.endswith("/timeline/batches") else None)
        node.hover()
        tip.wait_for(state="visible")
        self.physical_click(page, node, button="right")
        menu = card.locator("[data-timeline-context]")
        menu.wait_for(state="visible")
        tip.wait_for(state="hidden")
        self.assertTrue(node.evaluate("element => element.classList.contains('is-context-open')"))
        self.physical_click(page, card.locator('[data-draft-action="single"]'))
        self.assertTrue(menu.is_hidden())
        self.assertFalse(node.evaluate("element => element.classList.contains('is-context-open')"))
        node = card.locator('.timeline-dashboard-node[data-node-date="2026-08-01"]')
        box = node.bounding_box()
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.mouse.down()
        page.mouse.move(box["x"] + box["width"] / 2 + 70, box["y"] + box["height"] / 2, steps=6)
        loupe = card.locator("[data-dashboard-loupe]")
        self.assertFalse(loupe.is_hidden())
        self.assertEqual(loupe.locator(".timeline-loupe-scale i").count(), 21)
        self.assertIn("→", loupe.locator(".timeline-loupe-head").inner_text())
        self.assertEqual(batch_requests, [], "拖动期间保持零网络")
        page.mouse.up()

        card.locator('[data-dashboard-draft-count]', has_text="1 项草稿").wait_for()
        moved = card.locator('.timeline-dashboard-node[data-node-id="1"]').get_attribute("data-node-date")
        self.assertNotEqual(moved, "2026-08-01")
        self.assertEqual(card.locator(".timeline-dashboard-origin").count(), 1)
        self.assertEqual(batch_requests, [], "松手只落本地草稿")

        # 一次性解锁已消费：不重新右键时再次拖动不得改变草稿日期。
        node = card.locator('.timeline-dashboard-node[data-node-id="1"]')
        box = node.bounding_box()
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.mouse.down(); page.mouse.move(box["x"] + box["width"] / 2 + 70, box["y"] + box["height"] / 2); page.mouse.up()
        self.assertEqual(card.locator('.timeline-dashboard-node[data-node-id="1"]').get_attribute("data-node-date"), moved)

        with page.expect_response(lambda response: response.request.method == "POST" and response.url.endswith("/timeline/batches")) as saved:
            self.physical_click(page, card.locator(f'[data-dashboard-submit="{project_id}"]'))
        self.assertEqual(saved.value.status, 200)
        card.locator('[data-dashboard-draft-count]', has_text="0 项草稿").wait_for()
        self.assertEqual(len(batch_requests), 1)
        self.assert_clean_browser(page); context.close()

    def test_gate5_viewer_never_sees_classic_home_without_probe_noise(self):
        """只读成员不自动探测时间轴，经典主页仍保持彻底隐藏。"""
        self.seed_timeline(created_by="u1", name="只读可见项目")
        context, page = self.login("u3")
        self.assertFalse(page.locator("#boardWorkspace").is_visible())
        self.assert_clean_browser(page)
        self.assertTrue(page.locator("#timelineModal").evaluate("element => element.hidden"))
        with page.expect_response(lambda response: response.url.endswith("/api/workspaces/1/timeline")) as denied:
            self.physical_click(page, page.locator("#timelineBtn"))
        page.locator("#toast.show").wait_for()
        self.assertFalse(page.locator("#timelineView").is_visible())
        self.assertEqual(denied.value.status, 403)
        self.assertEqual(len(page.flowboard_console_errors), 1)
        self.assertIn("403", page.flowboard_console_errors[0])
        context.close()

    def test_gate5_delete_last_project_leaves_home_stable(self):
        """删掉最后一个项目后主页稳定呈现空态，无 JS 错误。"""
        self.seed_timeline(created_by="u1", name="最后项目")
        context, page = self.login("u1")
        page.locator('[data-timeline-page="home"]').wait_for()
        page.once("dialog", lambda dialog: dialog.accept())
        self.physical_click(page, page.locator("[data-timeline-delete]"))
        page.locator("[data-project-choice]").wait_for(state="detached")
        self.assertEqual(page.locator("[data-project-choice]").count(), 0)
        self.assertIn("暂无负责项目", page.locator('[data-timeline-section="mine"]').inner_text())
        self.assert_clean_browser(page); context.close()

    def test_gate5_url_board_param_cannot_restore_classic_home(self):
        """旧 ?board= 恢复参数不得重新暴露经典主页。"""
        self.seed_timeline(created_by="u1", name="恢复项目")
        context, page = self.login("u1")
        page.locator('[data-timeline-page="home"]').wait_for()
        page.goto(f"{self.base}/?board=1")
        page.locator('[data-timeline-page="home"]').wait_for()
        self.assertFalse(page.locator("#boardWorkspace").is_visible())
        self.assert_clean_browser(page); context.close()


if __name__ == "__main__":
    unittest.main()
